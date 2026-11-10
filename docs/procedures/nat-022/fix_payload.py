#!/usr/bin/env python3
"""Round the SWEETXNU payload header's adt_size up to a multiple of 8 (NAT-026). Host only.

Why: native run 004 stopped at the NAT-020 loader's `(p->adt_size & 7)` header check. mkpayload.py writes
adt_size = len(adt) = 13956 although the ADT is followed by zero padding up to 16 bytes, and loader.c
requires a multiple of 8. This changes only that u64 field, in a copy; the loader is not touched.

usage: fix_payload.py SRC DST      (refuses to write unless every precondition below holds)

Preconditions, all checked: SWEETXNU magic, version 1; the bytes between the old and the new end of the
ADT exist in the file and are zero; no segment file range overlaps those bytes; the new adt_size is
still inside the file. The u64 at header offset 40 is the only byte range that differs in DST.
"""
from pathlib import Path
import hashlib, json, struct, sys

ADT_OFF_FIELD, ADT_SIZE_FIELD, SEGS = 32, 40, 0x2a8

def fix(data):
    d = bytearray(data)
    if d[:8] != b'SWEETXNU' or struct.unpack_from('<I', d, 8)[0] != 1:
        raise SystemExit('not a version 1 SWEETXNU payload')
    nsegs = struct.unpack_from('<I', d, 12)[0]
    adt_off, adt_size = struct.unpack_from('<QQ', d, ADT_OFF_FIELD)
    if adt_off & 7:
        raise SystemExit('adt_off is not 8-aligned; not a padding problem')
    new = (adt_size + 7) & ~7
    if new == adt_size:
        raise SystemExit('adt_size already a multiple of 8; nothing to fix')
    if adt_off + new > len(d):
        raise SystemExit('padded ADT would run past the end of the payload')
    if any(d[adt_off + adt_size:adt_off + new]):
        raise SystemExit('bytes after the ADT are not zero; refusing to claim them as ADT')
    for i in range(nsegs):
        file_off, file_size = struct.unpack_from('<QQ', d, SEGS + 32 * i + 16)
        if file_off < adt_off + new and file_off + file_size > adt_off + adt_size:
            raise SystemExit(f'segment {i} file range overlaps the padding')
    struct.pack_into('<Q', d, ADT_SIZE_FIELD, new)
    return bytes(d), dict(field='adt_size', header_offset=ADT_SIZE_FIELD, old=adt_size, new=new,
                          reason='loader.c: (p->adt_size & 7) fails with "bad payload header"',
                          base_sha256=hashlib.sha256(data).hexdigest(),
                          fixed_sha256=hashlib.sha256(bytes(d)).hexdigest())

def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out, info = fix(src.read_bytes())
    if dst.exists():
        raise SystemExit('refusing to overwrite ' + str(dst))
    dst.write_bytes(out)
    print(json.dumps(info, indent=1))

if __name__ == '__main__':
    main()
