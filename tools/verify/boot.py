#!/usr/bin/env python3
"""Independent boot-v4/Image bounds checks. Structural checks never authorize device boot."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import tarfile

PAGE = 4096
LIMIT = 64 << 20
FOOTER = b'SEANDROIDENFORCE'


def spans(ranges, reserved=()):
    ordered = sorted(ranges)
    for i, (start, size) in enumerate(ordered):
        if start < 0 or size <= 0 or start + size > 1 << 64:
            raise ValueError('Invalid or overflowing physical range')
        if i and ordered[i-1][0] + ordered[i-1][1] > start:
            raise ValueError('Overlapping physical ranges')
        if any(start < r + n and r < start + size for r, n in reserved):
            raise ValueError('Range intersects reserved memory')
    return ordered


def entrypoint(address, segments):
    """Require an entry in a nonempty file-backed executable segment, not BSS or a gap."""
    spans([(base, size) for base, size, _, _ in segments])
    if any(file_size < 0 or file_size > size for _, size, file_size, _ in segments):
        raise ValueError('Segment file size exceeds its memory range')
    if not any(executable and base <= address < base + file_size
               for base, _, file_size, executable in segments):
        raise ValueError('Entry address is not backed by executable bytes')
    return address


def inspect(data):
    if len(data) < PAGE + 64 + len(FOOTER) or len(data) > LIMIT:
        raise ValueError('Boot image size outside bounds')
    if data[:8] != b'ANDROID!': raise ValueError('Not an Android boot image')
    kernel, ramdisk, _, header = struct.unpack_from('<4I', data, 8)
    version = struct.unpack_from('<I', data, 40)[0]
    signature = struct.unpack_from('<I', data, 1580)[0]
    if version != 4 or header != 1584 or ramdisk or signature:
        raise ValueError('Expected unsigned kernel-only v4/1584 packaging')
    end = PAGE + kernel
    footer = PAGE + ((kernel + PAGE - 1) // PAGE) * PAGE
    if kernel < 64 or end > len(data) or footer + len(FOOTER) != len(data):
        raise ValueError('Kernel/footer bounds or trailing bytes invalid')
    if any(data[1584:PAGE]) or any(data[end:footer]):
        raise ValueError('Unexpected nonzero padding')
    if data[footer:] != FOOTER: raise ValueError('Missing Samsung footer')
    image = data[PAGE:end]
    if image[56:60] != b'ARM\x64': raise ValueError('Missing AArch64 Image magic')
    text_offset, image_size = struct.unpack_from('<2Q', image, 8)
    if image_size != kernel: raise ValueError('Image size disagrees with boot header')
    return dict(header_version=version, kernel_size=kernel, image_size=image_size, text_offset=text_offset,
                image_sha256=hashlib.sha256(image).hexdigest(), structural_checks='pass',
                xnu_payload_verified=False, hardware_boot_verified=False,
                limitation='Packaging only; payload/ADT, firmware matching and live memory require separate checks')


def inspect_tar(data, expected_boot):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) != 1 or members[0].name != 'boot.img' or not members[0].isfile() or members[0].size > LIMIT:
            raise ValueError('Expected exactly one regular boot.img tar member')
        if archive.extractfile(members[0]).read() != expected_boot:
            raise ValueError('Tar contents differ from the inspected boot image')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--tar', type=Path)
    args = p.parse_args()
    if args.image.stat().st_size > LIMIT: raise ValueError('Image too large')
    data = args.image.read_bytes(); result = inspect(data)
    if args.tar:
        if args.tar.stat().st_size > LIMIT + 10240: raise ValueError('Tar too large')
        inspect_tar(args.tar.read_bytes(), data); result['tar_matches'] = True
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try: main()
    except (ValueError,OSError,tarfile.TarError) as error: raise SystemExit(str(error))
