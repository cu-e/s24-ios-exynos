"""Host tests for tools/ios/udif.py (IOS-004).

Evidence class: host-test. Every image here is built by the writer in this file from the public description of the
UDIF layout (back-to-front: data fork, XML property list with ``blkx``/``mish`` tables, 512-byte ``koly`` trailer,
big-endian).  The writer shares no code with the reader.  LZFSE chunks are made from hand-built ``bvx-`` streams and
from vectors made by the pinned reference encoder (tests/fixtures/lzfse_vectors.json); no Apple data is used.
"""
import bz2
import hashlib
import importlib.util
import io
import json
import lzma
import plistlib
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ud = _load("udif_under_test", "tools/ios/udif.py")
lz = _load("lzfse_for_udif_tests", "tools/ios/lzfse_py.py")
VECTORS = json.loads((ROOT / "tests/fixtures/lzfse_vectors.json").read_text())["vectors"]

S = 512
T_ZERO, T_RAW, T_IGNORE, T_COMMENT = 0, 1, 2, 0x7FFFFFFE
T_ADC, T_ZLIB, T_BZ2, T_LZFSE, T_LZMA, T_END = 0x80000004, 0x80000005, 0x80000006, 0x80000007, 0x80000008, 0xFFFFFFFF


def lzfse_raw_stream(payload):
    return b"bvx-" + struct.pack("<I", len(payload)) + payload + b"bvx$"


def lzfse_vector_padded(name):
    """Encoder-made stream plus a stored block so that the output is a whole number of sectors."""
    enc = bytes.fromhex(VECTORS[name]["encoded_hex"])
    raw = lz.decode(enc)
    pad = (-len(raw)) % S
    assert enc[-4:] == b"bvx$"
    stream = enc[:-4] + (b"bvx-" + struct.pack("<I", pad) + bytes(pad) if pad else b"") + b"bvx$"
    expected = raw + bytes(pad)
    assert len(expected) % S == 0
    return stream, expected


def make_chunk_payload(kind, data):
    """(type, sectors, stored bytes, expected output) for a sector-multiple ``data``."""
    assert len(data) % S == 0
    n = len(data) // S
    if kind == T_RAW:
        return T_RAW, n, data, data
    if kind == T_ZLIB:
        return T_ZLIB, n, zlib.compress(data), data
    if kind == T_BZ2:
        return T_BZ2, n, bz2.compress(data), data
    if kind == T_LZMA:
        return T_LZMA, n, lzma.compress(data), data
    if kind == T_LZFSE:
        return T_LZFSE, n, lzfse_raw_stream(data), data
    raise AssertionError(kind)


def mish(first, chunks, data_offset=0, version=1):
    """Block table.  ``chunks`` = list of (type, sector (relative), sectors, comp offset, comp length)."""
    count = sum(c[2] for c in chunks if c[0] not in (T_COMMENT, T_END))
    head = b"mish" + struct.pack(">IQQQ", version, first, count, data_offset)
    head += struct.pack(">II", 2048, 0) + bytes(24) + struct.pack(">II", 0, 0) + bytes(128)
    head += struct.pack(">I", len(chunks) + 1)
    assert len(head) == 204
    body = b"".join(struct.pack(">IIQQQQ", t, 0, sec, n, off, ln) for t, sec, n, off, ln in chunks)
    body += struct.pack(">IIQQQQ", T_END, 0, count, 0, 0, 0)
    return head + body


def build_udif(partitions, image_sectors=None, data_fork_length_zero=False, segments=1, mutate=None):
    """partitions = list of (name, first_sector, [chunk specs]).  A chunk spec is (type, sectors, stored) where
    ``stored`` is the compressed bytes (b"" for zero/ignore).  Returns (file bytes, expected partition bytes list)."""
    fork = bytearray()
    entries, expected = [], []
    last_end = 0
    for i, (name, first, specs) in enumerate(partitions):
        chunks, sec, out = [], 0, bytearray()
        for t, n, stored, exp in specs:
            if t in (T_ZERO, T_IGNORE):
                chunks.append((t, sec, n, 0, 0))
                if n * S <= 1 << 20:
                    out += bytes(n * S)
                else:
                    out = None                    # expected bytes not materialised for huge runs
            elif t == T_COMMENT:
                chunks.append((t, sec, 0, 0, 0))
            else:
                chunks.append((t, sec, n, len(fork), len(stored)))
                fork += stored
                if out is not None:
                    out += exp
            sec += n
        table = mish(first, chunks)
        entries.append({"Attributes": "0x0050", "CFName": name, "Data": table, "ID": str(i - 1 if i else -1), "Name": name})
        expected.append(None if out is None else bytes(out))
        last_end = max(last_end, first + sec)
    plist = plistlib.dumps({"resource-fork": {"blkx": entries}}, fmt=plistlib.FMT_XML)
    trailer = bytearray(512)
    trailer[0:4] = b"koly"
    struct.pack_into(">II", trailer, 4, 4, 512)
    struct.pack_into(">I", trailer, 12, 1)
    struct.pack_into(">QQ", trailer, 24, 0, 0 if data_fork_length_zero else len(fork))
    struct.pack_into(">II", trailer, 56, 1, segments)
    struct.pack_into(">QQ", trailer, 216, len(fork), len(plist))
    struct.pack_into(">I", trailer, 488, 2)
    struct.pack_into(">Q", trailer, 492, image_sectors if image_sectors is not None else last_end)
    blob = bytearray(bytes(fork) + plist + bytes(trailer))
    if mutate:
        mutate(blob, len(fork), len(plist))
    return bytes(blob), expected


def pattern(n, seed):
    state = seed
    out = bytearray()
    for _ in range(n):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(state >> 16 & 0xFF)
    return bytes(out)


def sample_image():
    data1 = pattern(S * 4, 1)
    data2 = pattern(S * 3, 2)
    data3 = (b"abc" * 1000)[:S * 5]
    data4 = pattern(S * 2, 3)
    data5 = pattern(S * 2, 4)
    lz_stream, lz_expected = lzfse_vector_padded("lzfse-text")
    parts = [
        ("MBR", 0, [make_chunk_payload(T_RAW, data4)]),
        ("Apple_APFS", 4, [make_chunk_payload(T_RAW, data1), (T_ZERO, 2, b"", b""),
                           make_chunk_payload(T_ZLIB, data2), (T_COMMENT, 0, b"", b""),
                           (T_IGNORE, 3, b"", b""), make_chunk_payload(T_BZ2, data3),
                           make_chunk_payload(T_LZMA, data5), make_chunk_payload(T_LZFSE, data1),
                           (T_LZFSE, len(lz_expected) // S, lz_stream, lz_expected)]),
    ]
    return build_udif(parts)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.blob, self.expected = sample_image()
        self.u = ud.Udif(io.BytesIO(self.blob))

    def test_partition_table_matches_what_was_written(self):
        self.assertEqual([p.name for p in self.u.partitions], ["MBR", "Apple_APFS"])
        self.assertEqual([p.first_sector for p in self.u.partitions], [0, 4])
        self.assertEqual([p.byte_size for p in self.u.partitions], [len(e) for e in self.expected])
        hist = self.u.partitions[1].chunk_histogram()
        self.assertEqual(hist, {"raw": 1, "zero": 1, "zlib": 1, "ignore": 1, "bzip2": 1, "lzma": 1, "lzfse": 2})

    def test_every_partition_reads_back_exactly(self):
        for i, exp in enumerate(self.expected):
            with self.subTest(partition=i):
                self.assertEqual(self.u.read(i, 0, len(exp)), exp)
                self.assertEqual(b"".join(self.u.iter_partition(i, block=700)), exp)

    def test_reads_that_start_and_end_anywhere_in_a_small_window_match(self):
        exp = self.expected[1]
        for start in list(range(0, 5 * S, 97)) + [len(exp) - 3]:
            for length in (1, 7, 511, 512, 513, 1500):
                with self.subTest(start=start, length=length):
                    self.assertEqual(self.u.read(1, start, length), exp[start:start + length])

    def test_read_is_clipped_at_the_end_and_empty_beyond_it(self):
        exp = self.expected[1]
        self.assertEqual(self.u.read(1, len(exp) - 10, 1000), exp[-10:])
        self.assertEqual(self.u.read(1, len(exp), 5), b"")
        self.assertEqual(self.u.read(1, len(exp) + 99, 5), b"")
        self.assertEqual(self.u.read(1, 0, 0), b"")

    def test_partition_reader_is_a_seekable_file(self):
        r = self.u.partition_reader(1)
        exp = self.expected[1]
        self.assertEqual(r.read(10), exp[:10])
        self.assertEqual(r.tell(), 10)
        r.seek(-20, 2)
        self.assertEqual(r.read(), exp[-20:])
        r.seek(S * 6 + 5)
        r.seek(3, 1)
        self.assertEqual(r.read(4), exp[S * 6 + 8:S * 6 + 12])
        with self.assertRaises(ValueError):
            r.seek(-1)

    def test_decode_cache_is_bounded(self):
        u = ud.Udif(io.BytesIO(self.blob), cache_chunks=2)
        u.read(1, 0, len(self.expected[1]))
        self.assertLessEqual(len(u._cache), 2)

    def test_negative_arguments_are_refused(self):
        with self.assertRaises(ud.UdifError):
            self.u.read(1, -1, 4)
        with self.assertRaises(ud.UdifError):
            self.u.read(9, 0, 4)
        with self.assertRaises(ud.UdifError):
            self.u.read(1, 0, -4)

    def test_info_reports_sizes_and_chunk_types(self):
        info = self.u.info()
        self.assertEqual(info["partitions"][1]["bytes"], len(self.expected[1]))
        self.assertEqual(info["partitions"][1]["chunk_types"]["lzfse"], 2)
        self.assertEqual(info["sector_count"], 4 + len(self.expected[1]) // S)

    def test_trailer_with_zero_data_fork_length_still_reads(self):
        blob, exp = build_udif([("p", 0, [make_chunk_payload(T_ZLIB, pattern(S * 3, 9))])], data_fork_length_zero=True)
        self.assertEqual(ud.Udif(io.BytesIO(blob)).read(0, 0, 10 * S), exp[0])


class LargeRuns(unittest.TestCase):
    def test_a_ten_gigabyte_zero_run_is_read_by_slice(self):
        sectors = 20_000_000
        blob, _ = build_udif([("p", 0, [make_chunk_payload(T_RAW, pattern(S, 5)), (T_IGNORE, sectors, b"", b"")])],
                             image_sectors=sectors + 1)
        u = ud.Udif(io.BytesIO(blob))
        self.assertEqual(u.partitions[0].byte_size, (sectors + 1) * S)
        self.assertEqual(u.read(0, S + 9_000_000_000, 16), bytes(16))
        self.assertEqual(u.read(0, S - 4, 8), pattern(S, 5)[-4:] + bytes(4))

    def test_a_stored_chunk_larger_than_the_decode_limit_is_read_by_slice(self):
        old = ud.MAX_CHUNK_BYTES
        ud.MAX_CHUNK_BYTES = 1024
        try:
            data = pattern(S * 8, 6)
            blob, _ = build_udif([("p", 0, [make_chunk_payload(T_RAW, data)])])
            u = ud.Udif(io.BytesIO(blob))
            self.assertEqual(u.read(0, 700, 2000), data[700:2700])
            blob, _ = build_udif([("p", 0, [make_chunk_payload(T_ZLIB, data)])])
            with self.assertRaisesRegex(ud.UdifError, "chunk limit"):
                ud.Udif(io.BytesIO(blob))
        finally:
            ud.MAX_CHUNK_BYTES = old


class Containers(unittest.TestCase):
    def test_stored_zip_member_is_read_in_place_and_deflated_is_refused(self):
        blob, exp = sample_image()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.ipsw"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("before.bin", b"x" * 123)
                z.writestr(zipfile.ZipInfo("stored.dmg"), blob, compress_type=zipfile.ZIP_STORED)
                z.writestr(zipfile.ZipInfo("deflated.dmg"), blob, compress_type=zipfile.ZIP_DEFLATED)
            u, close = ud.open_path("%s:stored.dmg" % path)
            self.assertEqual(u.read(1, 0, len(exp[1])), exp[1])
            close()
            with self.assertRaisesRegex(ud.UdifError, "compressed"):
                ud.open_path("%s:deflated.dmg" % path)

    def test_plain_file_path(self):
        blob, exp = sample_image()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a:b.dmg"
            path.write_bytes(blob)
            u, close = ud.open_path(str(path))
            self.assertEqual(u.read(0, 0, 64), exp[0][:64])
            close()


def patch(offset_fn, fmt, value):
    def go(blob, fork_len, plist_len):
        struct.pack_into(fmt, blob, offset_fn(fork_len, plist_len), value)
    return go


def trailer_at(rel):
    return lambda fork_len, plist_len: fork_len + plist_len + rel


class Rejections(unittest.TestCase):
    def setUp(self):
        self.parts = [("p", 0, [make_chunk_payload(T_RAW, pattern(S * 2, 7)), make_chunk_payload(T_ZLIB, pattern(S * 3, 8))])]

    def assertRefused(self, blob, pattern_=None):
        if pattern_:
            with self.assertRaisesRegex(ud.UdifError, pattern_):
                ud.Udif(io.BytesIO(blob))
        else:
            with self.assertRaises(ud.UdifError):
                ud.Udif(io.BytesIO(blob))

    def table_mutation(self, edit):
        """Rebuild the image with a mutated block table (edit receives and returns the table bytes)."""
        blob, _ = build_udif(self.parts)
        u = ud.Udif(io.BytesIO(blob))
        plist_bytes = blob[u.xml_offset:u.xml_offset + u.xml_length]
        pl = plistlib.loads(plist_bytes)
        pl["resource-fork"]["blkx"][0]["Data"] = edit(bytes(pl["resource-fork"]["blkx"][0]["Data"]))
        new = plistlib.dumps(pl, fmt=plistlib.FMT_XML)
        body = blob[:u.xml_offset] + new
        trailer = bytearray(blob[-512:])
        struct.pack_into(">Q", trailer, 224, len(new))
        return bytes(body + trailer)

    def test_trailer_faults(self):
        good, _ = build_udif(self.parts)
        self.assertRefused(good[:100], "smaller than")
        self.assertRefused(good[:-1])
        self.assertRefused(b"", "smaller than")
        bad = bytearray(good)
        bad[-512:-508] = b"kolx"
        self.assertRefused(bytes(bad), "koly")
        bad = bytearray(good)
        struct.pack_into(">I", bad, len(good) - 512 + 4, 5)
        self.assertRefused(bytes(bad), "version")
        bad = bytearray(good)
        struct.pack_into(">I", bad, len(good) - 512 + 8, 256)
        self.assertRefused(bytes(bad), "header size")
        bad = bytearray(good)
        struct.pack_into(">Q", bad, len(good) - 512 + 216, len(good))
        self.assertRefused(bytes(bad), "property list")
        bad = bytearray(good)
        struct.pack_into(">Q", bad, len(good) - 512 + 224, 0)
        self.assertRefused(bytes(bad), "property list")
        bad = bytearray(good)
        struct.pack_into(">Q", bad, len(good) - 512 + 224, 1 << 40)
        self.assertRefused(bytes(bad), "property list")
        bad = bytearray(good)
        struct.pack_into(">Q", bad, len(good) - 512 + 32, 1 << 40)
        self.assertRefused(bytes(bad), "data fork")
        bad = bytearray(good)
        struct.pack_into(">Q", bad, len(good) - 512 + 24, (1 << 64) - 4)
        self.assertRefused(bytes(bad), "data fork")

    def test_segmented_images_are_refused(self):
        blob, _ = build_udif(self.parts, segments=2)
        self.assertRefused(blob, "segmented")

    def test_property_list_faults(self):
        good, _ = build_udif(self.parts)
        u = ud.Udif(io.BytesIO(good))
        for mutate in (lambda p: b"not a plist" + p[11:], lambda p: plistlib.dumps({"x": 1}),
                       lambda p: plistlib.dumps({"resource-fork": {"blkx": []}}),
                       lambda p: plistlib.dumps({"resource-fork": {"blkx": [{"Name": "a"}]}}),
                       lambda p: plistlib.dumps({"resource-fork": {"blkx": "no"}})):
            new = mutate(good[u.xml_offset:u.xml_offset + u.xml_length])
            trailer = bytearray(good[-512:])
            struct.pack_into(">Q", trailer, 224, len(new))
            with self.subTest(new=new[:20]):
                self.assertRefused(good[:u.xml_offset] + new + bytes(trailer))

    def test_block_table_faults(self):
        def setat(off, fmt, val):
            def edit(t):
                t = bytearray(t)
                struct.pack_into(fmt, t, off, val)
                return bytes(t)
            return edit
        chunk0 = 204
        cases = {
            "no 'mish' signature": lambda t: b"xxxx" + t[4:],
            "block table is": lambda t: t[:100],
            "version": setat(4, ">I", 2),
            "outside the image": setat(16, ">Q", 1 << 40),
            "do not fit": setat(200, ">I", 5000),
            "starts at sector": setat(chunk0 + 40 + 8, ">Q", 99),         # second chunk, wrong start sector
            "run past the partition": setat(chunk0 + 16, ">Q", 99),       # first chunk, too many sectors
            "outside the data fork": setat(chunk0 + 24, ">Q", 1 << 40),
            "unknown chunk type": setat(chunk0, ">I", 0x12345678),
            "ADC": setat(chunk0, ">I", T_ADC),
            "raw chunk of": setat(chunk0 + 32, ">Q", 5),                  # raw chunk length != sectors*512
        }
        for message, edit in cases.items():
            with self.subTest(message=message):
                self.assertRefused(self.table_mutation(edit), message)

    def test_chunks_must_cover_the_partition(self):
        def drop_last_chunk(t):
            t = bytearray(t)
            struct.pack_into(">I", t, 200, 1)      # only the first chunk is listed
            return bytes(t)
        self.assertRefused(self.table_mutation(drop_last_chunk), "cover")

    def test_comment_chunk_with_sectors_and_zero_chunk_with_data_are_refused(self):
        def comment(t):
            t = bytearray(t)
            struct.pack_into(">I", t, 204, T_COMMENT)
            return bytes(t)
        self.assertRefused(self.table_mutation(comment), "comment")

        def zero_with_data(t):
            t = bytearray(t)
            struct.pack_into(">I", t, 204, T_ZERO)
            return bytes(t)
        self.assertRefused(self.table_mutation(zero_with_data), "carries")

    def test_overlapping_partitions_are_refused(self):
        a = make_chunk_payload(T_RAW, pattern(S * 4, 1))
        blob, _ = build_udif([("a", 0, [a]), ("b", 2, [a])])
        self.assertRefused(blob, "inside the previous partition")

    def test_partition_beyond_the_image_is_refused(self):
        blob, _ = build_udif([("a", 0, [make_chunk_payload(T_RAW, pattern(S * 4, 1))])], image_sectors=3)
        self.assertRefused(blob, "outside the image")

    def test_chunk_that_decodes_to_the_wrong_length_is_refused_when_read(self):
        data = pattern(S * 2, 2)
        blob, _ = build_udif([("a", 0, [(T_ZLIB, 3, zlib.compress(data), data)])])      # claims 3 sectors, holds 2
        u = ud.Udif(io.BytesIO(blob))
        with self.assertRaisesRegex(ud.UdifError, "decoded to"):
            u.read(0, 0, 10)

    def test_decompression_bomb_is_cut_at_the_claimed_size(self):
        bomb = zlib.compress(bytes(50_000_000), 9)
        blob, _ = build_udif([("a", 0, [(T_ZLIB, 1, bomb, bytes(S))])])
        u = ud.Udif(io.BytesIO(blob))
        with self.assertRaisesRegex(ud.UdifError, "decoded to"):
            u.read(0, 0, 10)
        bomb = bz2.compress(bytes(20_000_000), 9)
        blob, _ = build_udif([("a", 0, [(T_BZ2, 1, bomb, bytes(S))])])
        with self.assertRaisesRegex(ud.UdifError, "decoded to"):
            ud.Udif(io.BytesIO(blob)).read(0, 0, 10)
        bomb = lzma.compress(bytes(20_000_000))
        blob, _ = build_udif([("a", 0, [(T_LZMA, 1, bomb, bytes(S))])])
        with self.assertRaisesRegex(ud.UdifError, "decoded to"):
            ud.Udif(io.BytesIO(blob)).read(0, 0, 10)

    def test_decoders_are_bounded_by_the_claimed_size_not_by_the_stream(self):
        import tracemalloc

        def bomb(compressobj, total=200 * 1024 * 1024):
            zeros = bytes(1 << 20)
            out = [compressobj.compress(zeros) for _ in range(total >> 20)]
            out.append(compressobj.flush())
            return b"".join(out)

        cases = ((T_ZLIB, bomb(zlib.compressobj(9))), (T_BZ2, bomb(bz2.BZ2Compressor(9))),
                 (T_LZMA, bomb(lzma.LZMACompressor())))
        for kind, stream in cases:
            blob, _ = build_udif([("a", 0, [(kind, 1, stream, bytes(S))])])
            u = ud.Udif(io.BytesIO(blob))
            tracemalloc.start()
            try:
                with self.assertRaisesRegex(ud.UdifError, "decoded to"):
                    u.read(0, 0, 10)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            with self.subTest(kind=kind):
                self.assertLess(peak, len(stream) + 32 * 1024 * 1024)   # lzma keeps an 8 MiB dictionary; the bomb is 200 MiB

    def test_each_codec_reports_garbage_as_udif_error(self):
        for kind in (T_ZLIB, T_BZ2, T_LZMA, T_LZFSE):
            blob, _ = build_udif([("a", 0, [(kind, 1, b"\x01garbage that is no stream" * 3, bytes(S))])])
            u = ud.Udif(io.BytesIO(blob))
            with self.subTest(kind=kind):
                with self.assertRaises(ud.UdifError):
                    u.read(0, 0, 10)

    def test_lzfse_stream_with_more_output_than_claimed_is_refused(self):
        stream = lzfse_raw_stream(bytes(S * 2))
        blob, _ = build_udif([("a", 0, [(T_LZFSE, 1, stream, bytes(S))])])
        with self.assertRaisesRegex(ud.UdifError, "decoded to"):
            ud.Udif(io.BytesIO(blob)).read(0, 0, 10)

    def test_truncations_of_a_small_image_never_escape_as_another_exception(self):
        blob, _ = build_udif(self.parts)
        for cut in range(len(blob)):
            with self.subTest(cut=cut):
                try:
                    u = ud.Udif(io.BytesIO(blob[:cut]))
                    u.read(0, 0, 10 * S)
                except ud.UdifError:
                    pass

    def test_single_byte_corruption_never_escapes_as_another_exception(self):
        blob, exp = build_udif(self.parts)
        state = 99
        for i in range(400):
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            pos = state % len(blob)
            bad = bytearray(blob)
            bad[pos] ^= 1 << (state >> 8) % 8
            with self.subTest(pos=pos):
                try:
                    u = ud.Udif(io.BytesIO(bytes(bad)))
                    out = b"".join(u.iter_partition(0, 1000))
                    self.assertLessEqual(len(out), 1 << 20)
                except ud.UdifError:
                    pass


class WindowTests(unittest.TestCase):
    def test_window_clips_and_seeks(self):
        w = ud.Window(io.BytesIO(bytes(range(100))), 10, 20)
        self.assertEqual(w.read(5), bytes(range(10, 15)))
        self.assertEqual(w.read(), bytes(range(15, 30)))
        self.assertEqual(w.read(5), b"")
        w.seek(-3, 2)
        self.assertEqual(w.read(), bytes(range(27, 30)))
        w.seek(2)
        w.seek(3, 1)
        self.assertEqual(w.tell(), 5)
        with self.assertRaises(ValueError):
            w.seek(-1)


if __name__ == "__main__":
    unittest.main()
