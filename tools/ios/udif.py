#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only UDIF (Apple ``.dmg``) reader for the IOS-004 host tooling.

Evidence class of anything built on this file: host tooling. It parses the container; it does not interpret the
filesystem inside (that is IOS-005) and it executes nothing from the image.

Format (from the public descriptions of UDIF; the numbers below are the reader's only source of truth):

* The file is laid out back to front: the data fork (compressed chunks), an XML property list, and a 512-byte
  trailer that starts with ``koly``.  All integers are big-endian.
* The trailer holds the data-fork offset/length and the property list offset/length, and the image's sector count.
* The property list holds ``resource-fork/blkx``: one entry per partition, each a ``Data`` blob that is a ``mish``
  block table: the first sector and sector count of the partition inside the image, a data offset, and a list of
  40-byte chunk descriptors (type, sector, sector count, compressed offset, compressed length).  Chunk sectors are
  relative to the table's first sector; chunk offsets are relative to the table's data offset.
* Chunk types: 0 zero fill, 1 stored as is, 2 unallocated (reads as zeros), 0x7ffffffe comment (no data),
  0x80000005 zlib, 0x80000006 bzip2, 0x80000007 LZFSE, 0x80000008 LZMA, 0xffffffff end of table.  0x80000004
  (ADC) is refused by name: no image in scope uses it and no sample exists to test an implementation against.

Every damaged or hostile input ends in :class:`UdifError`.  No chunk is decoded before its descriptor is checked
(sector range inside the partition, compressed range inside the data fork, output size under ``MAX_CHUNK_BYTES``),
and every decoded chunk must have exactly the length its descriptor claims.

Usage::

    python3 tools/ios/udif.py info IMAGE.dmg
    python3 tools/ios/udif.py info IPSW.ipsw:096-04088-077.dmg      # a stored (uncompressed) member, read in place
    python3 tools/ios/udif.py read IMAGE.dmg PARTITION OFFSET LENGTH  # hex dump of decompressed bytes
"""
import bz2
import importlib.util
import lzma
import plistlib
import struct
import sys
import zipfile
import zlib
from collections import OrderedDict
from pathlib import Path

SECTOR = 512
TRAILER_SIZE = 512
MAX_CHUNK_BYTES = 64 * 1024 * 1024      # a chunk bigger than this is refused before decoding
MAX_PLIST_BYTES = 64 * 1024 * 1024
MAX_CHUNKS_PER_TABLE = 4 * 1024 * 1024
MISH_HEADER = 204
CHUNK_SIZE = 40

CHUNK_ZERO = 0x00000000
CHUNK_RAW = 0x00000001
CHUNK_IGNORE = 0x00000002
CHUNK_ADC = 0x80000004
CHUNK_ZLIB = 0x80000005
CHUNK_BZIP2 = 0x80000006
CHUNK_LZFSE = 0x80000007
CHUNK_LZMA = 0x80000008
CHUNK_COMMENT = 0x7FFFFFFE
CHUNK_END = 0xFFFFFFFF

CHUNK_NAMES = {
    CHUNK_ZERO: "zero", CHUNK_RAW: "raw", CHUNK_IGNORE: "ignore", CHUNK_ADC: "adc", CHUNK_ZLIB: "zlib",
    CHUNK_BZIP2: "bzip2", CHUNK_LZFSE: "lzfse", CHUNK_LZMA: "lzma", CHUNK_COMMENT: "comment", CHUNK_END: "end",
}
_NO_DATA = (CHUNK_ZERO, CHUNK_IGNORE)


class UdifError(Exception):
    """The input is not a UDIF image this reader accepts."""


def _load_lzfse():
    spec = importlib.util.spec_from_file_location("lzfse_py", Path(__file__).with_name("lzfse_py.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_lzfse = None


class Chunk:
    __slots__ = ("type", "sector", "sectors", "offset", "length")

    def __init__(self, type_, sector, sectors, offset, length):
        self.type, self.sector, self.sectors, self.offset, self.length = type_, sector, sectors, offset, length

    @property
    def name(self):
        return CHUNK_NAMES.get(self.type, "0x%08x" % self.type)

    @property
    def out_bytes(self):
        return self.sectors * SECTOR


class Partition:
    """One ``blkx`` entry.  ``first_sector`` is absolute in the image; chunk sectors are made absolute too."""

    def __init__(self, index, name, ident, first_sector, sectors, chunks):
        self.index, self.name, self.id = index, name, ident
        self.first_sector, self.sectors, self.chunks = first_sector, sectors, chunks
        self._starts = [c.sector for c in chunks]

    @property
    def byte_start(self):
        return self.first_sector * SECTOR

    @property
    def byte_size(self):
        return self.sectors * SECTOR

    def chunk_histogram(self):
        hist = {}
        for c in self.chunks:
            hist[c.name] = hist.get(c.name, 0) + 1
        return hist

    def find_chunk(self, sector):
        lo, hi = 0, len(self.chunks)
        while lo < hi:
            mid = (lo + hi) // 2
            c = self.chunks[mid]
            if sector < c.sector:
                hi = mid
            elif sector >= c.sector + c.sectors:
                lo = mid + 1
            else:
                return mid
        raise UdifError("sector %d is not covered by a chunk of partition %d" % (sector, self.index))


class Window:
    """A read-only byte window ``[start, start+length)`` of a file object (a stored member of a zip, for example)."""

    def __init__(self, fileobj, start, length):
        self.f, self.start, self.length = fileobj, start, length
        self.pos = 0

    def seek(self, off, whence=0):
        base = {0: 0, 1: self.pos, 2: self.length}.get(whence)
        if base is None:
            raise ValueError("bad whence")
        new = base + off
        if new < 0:
            raise ValueError("negative seek")
        self.pos = new
        return new

    def tell(self):
        return self.pos

    def read(self, n=-1):
        remaining = max(0, self.length - self.pos)
        if n is None or n < 0 or n > remaining:
            n = remaining
        self.f.seek(self.start + self.pos)
        data = self.f.read(n)
        self.pos += len(data)
        return data


def open_ipsw_member(zip_path, member):
    """Return (Window, raw file object) for a *stored* zip member; refuse a compressed one by name."""
    zf = zipfile.ZipFile(zip_path)
    info = zf.getinfo(member)
    if info.compress_type != zipfile.ZIP_STORED:
        raise UdifError("zip member %r is compressed (type %d); extract it first" % (member, info.compress_type))
    raw = open(zip_path, "rb")
    raw.seek(info.header_offset)
    head = raw.read(30)
    if len(head) != 30 or head[:4] != b"PK\x03\x04":
        raise UdifError("bad local header for zip member %r" % member)
    name_len, extra_len = struct.unpack_from("<HH", head, 26)
    return Window(raw, info.header_offset + 30 + name_len + extra_len, info.file_size), raw


def _safe_decode(kind, data, want):
    """Decode one compressed chunk to exactly ``want`` bytes or raise UdifError.  Bounded by ``want``."""
    try:
        if kind == CHUNK_ZLIB:
            d = zlib.decompressobj()
            out = d.decompress(data, want + 1)
        elif kind == CHUNK_BZIP2:
            d = bz2.BZ2Decompressor()
            out = d.decompress(data, want + 1)
        elif kind == CHUNK_LZMA:
            d = lzma.LZMADecompressor()
            out = d.decompress(data, want + 1)
        elif kind == CHUNK_LZFSE:
            global _lzfse
            if _lzfse is None:
                _lzfse = _load_lzfse()
            out = _lzfse.decode(data)
        else:
            raise UdifError("no decoder for chunk type 0x%08x" % kind)
    except UdifError:
        raise
    except Exception as exc:                       # zlib.error, OSError, EOFError, LzfseError, LZMAError ...
        raise UdifError("%s chunk does not decode: %s" % (CHUNK_NAMES.get(kind, kind), exc)) from exc
    if len(out) != want:
        raise UdifError("%s chunk decoded to %d bytes, descriptor says %d" % (CHUNK_NAMES.get(kind), len(out), want))
    return bytes(out)


def _parse_mish(blob, index, image_sectors, fork_lo, fork_hi):
    if len(blob) < MISH_HEADER:
        raise UdifError("blkx %d: block table is %d bytes, header needs %d" % (index, len(blob), MISH_HEADER))
    if blob[:4] != b"mish":
        raise UdifError("blkx %d: no 'mish' signature" % index)
    version, first, count, data_off = struct.unpack_from(">IQQQ", blob, 4)
    if version != 1:
        raise UdifError("blkx %d: block table version %d, only 1 is known" % (index, version))
    n_chunks = struct.unpack_from(">I", blob, 200)[0]
    if n_chunks > MAX_CHUNKS_PER_TABLE or MISH_HEADER + n_chunks * CHUNK_SIZE > len(blob):
        raise UdifError("blkx %d: %d chunks do not fit in the %d-byte table" % (index, n_chunks, len(blob)))
    if first > image_sectors or count > image_sectors - first:
        raise UdifError("blkx %d: sectors [%d,+%d) are outside the image (%d sectors)" % (index, first, count, image_sectors))
    chunks, expect = [], 0
    for i in range(n_chunks):
        t, _comment, sec, nsec, off, length = struct.unpack_from(">IIQQQQ", blob, MISH_HEADER + i * CHUNK_SIZE)
        if t == CHUNK_END:
            break
        if t == CHUNK_COMMENT:
            if nsec:
                raise UdifError("blkx %d chunk %d: comment chunk with %d sectors" % (index, i, nsec))
            continue
        if t == CHUNK_ADC:
            raise UdifError("blkx %d chunk %d: ADC compression is not implemented" % (index, i))
        if t not in CHUNK_NAMES or t in (CHUNK_END, CHUNK_COMMENT):
            raise UdifError("blkx %d chunk %d: unknown chunk type 0x%08x" % (index, i, t))
        if sec != expect:
            raise UdifError("blkx %d chunk %d: starts at sector %d, previous chunk ended at %d" % (index, i, sec, expect))
        if t not in _NO_DATA and t != CHUNK_RAW and nsec * SECTOR > MAX_CHUNK_BYTES:
            raise UdifError("blkx %d chunk %d: %d sectors exceed the %d-byte chunk limit" % (index, i, nsec, MAX_CHUNK_BYTES))
        if nsec > count - sec:
            raise UdifError("blkx %d chunk %d: sectors [%d,+%d) run past the partition (%d sectors)" % (index, i, sec, nsec, count))
        if t in _NO_DATA:
            if length:
                raise UdifError("blkx %d chunk %d: %s chunk carries %d data bytes" % (index, i, CHUNK_NAMES[t], length))
            absolute = 0
        else:
            absolute = data_off + off
            if absolute < fork_lo or length > fork_hi - fork_lo or absolute > fork_hi - length:
                raise UdifError("blkx %d chunk %d: data [%d,+%d) is outside the data fork" % (index, i, absolute, length))
            if t == CHUNK_RAW and length != nsec * SECTOR:
                raise UdifError("blkx %d chunk %d: raw chunk of %d bytes for %d sectors" % (index, i, length, nsec))
        chunks.append(Chunk(t, first + sec, nsec, absolute, length))
        expect = sec + nsec
    if expect != count:
        raise UdifError("blkx %d: chunks cover %d sectors, the table says %d" % (index, expect, count))
    return first, count, chunks


class Udif:
    def __init__(self, fileobj, size=None, cache_chunks=8):
        self.f = fileobj
        if size is None:
            fileobj.seek(0, 2)
            size = fileobj.tell()
        self.size = size
        if size < TRAILER_SIZE:
            raise UdifError("file is %d bytes, smaller than the 512-byte trailer" % size)
        t = self._pread(size - TRAILER_SIZE, TRAILER_SIZE)
        if t[:4] != b"koly":
            raise UdifError("no 'koly' trailer signature")
        version, hdr = struct.unpack_from(">II", t, 4)
        if version != 4 or hdr != TRAILER_SIZE:
            raise UdifError("trailer version %d header size %d (expected 4 and 512)" % (version, hdr))
        self.flags = struct.unpack_from(">I", t, 12)[0]
        self.data_fork_offset, self.data_fork_length = struct.unpack_from(">QQ", t, 24)
        self.segment_number, self.segment_count = struct.unpack_from(">II", t, 56)
        xml_off, xml_len = struct.unpack_from(">QQ", t, 216)
        self.image_variant = struct.unpack_from(">I", t, 488)[0]
        self.sector_count = struct.unpack_from(">Q", t, 492)[0]
        if self.segment_count > 1:
            raise UdifError("segmented image (%d segments)" % self.segment_count)
        body = size - TRAILER_SIZE
        if xml_len == 0 or xml_len > MAX_PLIST_BYTES or xml_off > body or xml_len > body - xml_off:
            raise UdifError("property list [%d,+%d) is outside the file" % (xml_off, xml_len))
        if self.data_fork_offset > body or self.data_fork_length > body - self.data_fork_offset:
            raise UdifError("data fork [%d,+%d) is outside the file" % (self.data_fork_offset, self.data_fork_length))
        self.xml_offset, self.xml_length = xml_off, xml_len
        fork_lo = self.data_fork_offset
        # An image whose trailer leaves the data-fork length at 0 still has data: bound by the plist start.
        fork_hi = fork_lo + self.data_fork_length if self.data_fork_length else min(xml_off, body)
        try:
            plist = plistlib.loads(self._pread(xml_off, xml_len))
            entries = plist["resource-fork"]["blkx"]
        except Exception as exc:
            raise UdifError("property list has no resource-fork/blkx: %s" % exc) from exc
        if not isinstance(entries, list) or not entries:
            raise UdifError("blkx is empty")
        self.partitions = []
        prev_end = 0
        for i, e in enumerate(entries):
            try:
                blob = bytes(e["Data"])
                name = str(e.get("Name", e.get("CFName", "")))
                ident = int(e.get("ID", i))
            except Exception as exc:
                raise UdifError("blkx %d is malformed: %s" % (i, exc)) from exc
            first, count, chunks = _parse_mish(blob, i, self.sector_count, fork_lo, fork_hi)
            if first < prev_end:
                raise UdifError("blkx %d starts at sector %d inside the previous partition (ends %d)" % (i, first, prev_end))
            prev_end = first + count
            self.partitions.append(Partition(i, name, ident, first, count, chunks))
        self._cache = OrderedDict()
        self._cache_max = max(1, cache_chunks)

    def _pread(self, off, n):
        self.f.seek(off)
        data = self.f.read(n)
        if len(data) != n:
            raise UdifError("short read: wanted %d bytes at %d, got %d" % (n, off, len(data)))
        return data

    def chunk_data(self, chunk):
        """Decompressed bytes of one chunk (cached)."""
        key = (chunk.sector, chunk.offset)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        want = chunk.out_bytes
        if chunk.type in _NO_DATA:
            if want > MAX_CHUNK_BYTES:
                raise UdifError("refusing to materialise a %d-byte zero run" % want)
            out = bytes(want)
        elif chunk.type == CHUNK_RAW:
            if want > MAX_CHUNK_BYTES:
                raise UdifError("refusing to cache a %d-byte stored chunk" % want)
            out = self._pread(chunk.offset, chunk.length)
        else:
            out = _safe_decode(chunk.type, self._pread(chunk.offset, chunk.length), want)
        self._cache[key] = out
        if len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return out

    def part(self, index):
        if not isinstance(index, int) or not 0 <= index < len(self.partitions):
            raise UdifError("no partition %r" % (index,))
        return self.partitions[index]

    def read(self, index, offset, length):
        """``length`` decompressed bytes at byte ``offset`` of partition ``index`` (clipped at the end)."""
        p = self.part(index)
        if offset < 0 or length < 0:
            raise UdifError("negative offset or length")
        end = min(offset + length, p.byte_size)
        if offset >= end:
            return b""
        out = bytearray()
        pos = offset
        # Chunk sectors in Partition are absolute; the partition-relative sector is what the caller's offset means.
        while pos < end:
            sector_abs = p.first_sector + pos // SECTOR
            c = p.chunks[p.find_chunk(sector_abs)]
            within = pos - (c.sector - p.first_sector) * SECTOR
            if c.type in _NO_DATA:                 # runs of zeros can be huge: never materialise the whole run
                take = min(end - pos, c.out_bytes - within)
                out += bytes(take)
            elif c.type == CHUNK_RAW:              # stored chunks can be tens of MiB: read just the slice
                take = min(end - pos, c.out_bytes - within)
                out += self._pread(c.offset + within, take)
            else:
                data = self.chunk_data(c)
                take = min(end - pos, len(data) - within)
                out += data[within:within + take]
            pos += take
        return bytes(out)

    def partition_reader(self, index):
        return PartitionReader(self, index)

    def iter_partition(self, index, block=1 << 20):
        """Stream a whole partition in ``block``-byte pieces (bounded memory)."""
        p = self.part(index)
        pos = 0
        while pos < p.byte_size:
            n = min(block, p.byte_size - pos)
            yield self.read(index, pos, n)
            pos += n

    def info(self):
        parts = []
        for p in self.partitions:
            parts.append({"index": p.index, "name": p.name, "id": p.id, "first_sector": p.first_sector,
                          "sectors": p.sectors, "bytes": p.byte_size, "chunks": len(p.chunks),
                          "chunk_types": p.chunk_histogram(),
                          "compressed_bytes": sum(c.length for c in p.chunks)})
        return {"file_bytes": self.size, "sector_count": self.sector_count, "image_variant": self.image_variant,
                "data_fork": [self.data_fork_offset, self.data_fork_length], "partitions": parts}


class PartitionReader:
    """A seekable file-like view of one partition's decompressed bytes."""

    def __init__(self, udif, index):
        self.u, self.i = udif, index
        self.size = udif.part(index).byte_size
        self.pos = 0

    def seek(self, off, whence=0):
        base = {0: 0, 1: self.pos, 2: self.size}.get(whence)
        if base is None:
            raise ValueError("bad whence")
        if base + off < 0:
            raise ValueError("negative seek")
        self.pos = base + off
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        data = self.u.read(self.i, self.pos, n)
        self.pos += len(data)
        return data


def open_path(spec):
    """``FILE`` or ``IPSW:member``; returns (Udif, closer)."""
    if ":" in spec and not Path(spec).exists():
        zip_path, member = spec.rsplit(":", 1)
        win, raw = open_ipsw_member(zip_path, member)
        return Udif(win, win.length), raw.close
    f = open(spec, "rb")
    return Udif(f), f.close


def main(argv):
    import json
    if len(argv) >= 3 and argv[1] == "info":
        u, close = open_path(argv[2])
        print(json.dumps(u.info(), indent=1))
        close()
        return 0
    if len(argv) == 6 and argv[1] == "read":
        u, close = open_path(argv[2])
        data = u.read(int(argv[3]), int(argv[4], 0), int(argv[5], 0))
        for i in range(0, len(data), 16):
            row = data[i:i + 16]
            print("%08x  %-47s  %s" % (i, " ".join("%02x" % b for b in row),
                                       "".join(chr(b) if 32 <= b < 127 else "." for b in row)))
        close()
        return 0
    print(__doc__.split("Usage::")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except UdifError as exc:
        print("udif: %s" % exc, file=sys.stderr)
        sys.exit(1)
