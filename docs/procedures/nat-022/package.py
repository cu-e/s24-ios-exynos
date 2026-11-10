#!/usr/bin/env python3
"""Package the NAT-022 canary Image into a RECOVERY image with the NAT-006 builder.

Host only: reads the pinned stock RECOVERY, writes a new directory, never opens
a phone. Refuses an existing output directory.
usage: package.py --image canary-plain/Image --out artifacts/nat-022/package-001
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, struct, sys

ROOT = Path(__file__).resolve().parents[3]
STOCK_SHA = '96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'

def sha(b): return hashlib.sha256(b).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location('nat006', ROOT / 'tools/build/e1s_recovery.py')
    h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    stock = (ROOT / h.STOCK_RECOVERY).read_bytes()
    assert sha(stock) == STOCK_SHA and len(stock) == h.PARTITION_SIZE
    kernel = a.image.read_bytes()
    assert kernel[56:60] == b'ARM\x64' and len(kernel) == struct.unpack_from('<Q', kernel, 16)[0]
    img, layout = h.build_recovery(stock, kernel, h.newc_cpio([h.PLACEHOLDER]))
    assert len(img) == len(stock) == h.PARTITION_SIZE
    # Which 4 KiB pages differ from stock (host fact about the file, not about the phone).
    diff = [i for i in range(0, len(img), 4096) if img[i:i + 4096] != stock[i:i + 4096]]
    assert kernel in img, 'canary Image not found verbatim in the package'
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'recovery.img').write_bytes(img)
    (a.out / 'package.json').write_text(json.dumps({
        'kind': 'host-test', 'device_used': False, 'flashed': False,
        'source_image': str(a.image), 'source_image_sha256': sha(kernel),
        'recovery_sha256': sha(img), 'size': len(img),
        'stock_sha256': STOCK_SHA, 'layout': layout,
        'differing_4k_pages': len(diff), 'first_last_pages': [diff[0] * 1, diff[-1]] if diff else [],
        'canary_image_offset': img.find(kernel)}, indent=1, default=str))
    print(sha(img), len(diff), 'differing pages; canary at', img.find(kernel))

if __name__ == '__main__':
    main()
