#!/usr/bin/env python3
"""NAT-077: pad a root image to the 16 KiB multiple the delivery path needs and record both SHA-256 values.

  pad_root.py SOURCE DEST [--record RECORD.json] [--unit 16384] [--expect-padded-bytes N]

SOURCE is the donor-built system.apfs (2,475,712,512 bytes: a multiple of 4096 but not of 16 KiB). DEST receives the same bytes followed
by zeros up to the next multiple of --unit (default 16 KiB, the XNU page size of the payload kernel and the unit of tools/ios/root_send.py).
The record holds sizes and SHA-256 values only, never file contents.

Refusals (nothing is written): a SOURCE size that is zero or not a multiple of 4096 (an APFS container block is 4096 bytes; a size that is
not one means a truncated or foreign file); a unit that is not a power-of-two multiple of 4096; a DEST that exists, that is the same file
as SOURCE, or that lies outside the repository's artifacts/ directory (Apple-derived data must not land where `git add` would take it);
an --expect-padded-bytes that does not match. The result is verified by reading DEST back: the first SOURCE-size bytes must hash to the
SOURCE digest and everything after them must be zero.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = (ROOT / "artifacts").resolve()
BLOCK = 4096
DEFAULT_UNIT = 16384
READ = 8 << 20


class PadError(SystemExit):
    pass


def padded_size(size, unit=DEFAULT_UNIT):
    """The size after padding; raises PadError for a size or unit this tool refuses."""
    if unit < BLOCK or unit % BLOCK or unit & (unit - 1):
        raise PadError("unit %d is not a power-of-two multiple of %d" % (unit, BLOCK))
    if size <= 0 or size % BLOCK:
        raise PadError("source size %d is not a positive multiple of %d bytes: refusing to pad (truncated or foreign file?)" % (size, BLOCK))
    return -(-size // unit) * unit


def file_sha256(path, limit=None):
    h, left = hashlib.sha256(), limit
    with open(path, "rb") as f:
        while left is None or left > 0:
            b = f.read(READ if left is None else min(READ, left))
            if not b:
                break
            h.update(b)
            if left is not None:
                left -= len(b)
    return h.hexdigest()


def tail_is_zero(path, start):
    with open(path, "rb") as f:
        f.seek(start)
        while True:
            b = f.read(READ)
            if not b:
                return True
            if b.count(0) != len(b):
                return False


def check_dest(dest):
    d = Path(dest)
    try:
        resolved = d.resolve(strict=False)
    except OSError as e:
        raise PadError("cannot resolve %s: %s" % (dest, e))
    if ARTIFACTS not in resolved.parents:
        raise PadError("%s is outside %s: Apple-derived data stays under artifacts/" % (dest, ARTIFACTS))
    if os.path.lexists(d):
        raise PadError("%s exists: pick a new name" % dest)


def pad(src, dest, unit=DEFAULT_UNIT, expect_padded=None):
    """-> record dict. Copies SOURCE to DEST (a reflink when the filesystem has them), extends it with zeros, then verifies by reading back."""
    size = os.stat(src).st_size
    out_size = padded_size(size, unit)
    if expect_padded is not None and out_size != expect_padded:
        raise PadError("padded size would be %d, expected %d" % (out_size, expect_padded))
    check_dest(dest)
    src_sha = file_sha256(src)
    fout = open(dest, "xb")			# raises if DEST appeared meanwhile: nothing of ours to clean up then
    try:
        with open(src, "rb") as fin, fout:
            try:
                import fcntl
                fcntl.ioctl(fout.fileno(), 0x40049409, fin.fileno())		# FICLONE
            except OSError:
                shutil.copyfileobj(fin, fout, READ)
            fout.truncate(out_size)						# zero-extends
            fout.flush()
            os.fsync(fout.fileno())
        if os.stat(dest).st_size != out_size:
            raise PadError("destination has %d bytes, expected %d" % (os.stat(dest).st_size, out_size))
        if file_sha256(dest, size) != src_sha or not tail_is_zero(dest, size):
            raise PadError("read-back check failed: the destination is not SOURCE followed by zeros")
        padded_sha = file_sha256(dest)
    except BaseException:
        os.unlink(dest)
        raise
    return {
        "source_bytes": size, "source_sha256": src_sha,
        "padded_bytes": out_size, "padded_sha256": padded_sha,
        "pad_bytes": out_size - size, "unit": unit,
        "padded_sectors_512": out_size // 512, "padded_pages": out_size // unit,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("dest")
    ap.add_argument("--record", type=Path)
    ap.add_argument("--unit", type=int, default=DEFAULT_UNIT)
    ap.add_argument("--expect-padded-bytes", type=int)
    a = ap.parse_args(argv)
    rec = pad(a.source, a.dest, a.unit, a.expect_padded_bytes)
    text = json.dumps(rec, indent=2, sort_keys=True) + "\n"
    if a.record:
        a.record.write_text(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
