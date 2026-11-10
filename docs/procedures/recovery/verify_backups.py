#!/usr/bin/env python3
"""NAT-001: verify the dated boot-chain backups of the owner's S24 on the host. No device access.

Re-hashes every image in the backup directory, parses Android boot image headers, recomputes the AVB
hash-descriptor digests that the stock-signed vbmeta records (sha256(salt || image[:image_size])) and
looks for Magisk's .backup/.magisk entry in the init_boot ramdisk. Writes manifest.json next to the
images (outside Git) and prints it. The images themselves are Samsung firmware and stay out of Git.

  verify_backups.py --dir devices/recovery/backups/2026-11-10
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

PARTITIONS = ['boot', 'init_boot', 'vendor_boot', 'recovery', 'dtbo', 'vbmeta', 'vbmeta_system']


def boot_header(data):
    if data[:8] == b'ANDROID!':
        version = struct.unpack_from('<I', data, 40)[0]
        if version >= 3:  # v3/v4: kernel_size, ramdisk_size, os_version, header_size, reserved[4], header_version
            kernel, ramdisk, os_version = struct.unpack_from('<3I', data, 8)
            return dict(magic='ANDROID!', header_version=version, kernel_size=kernel, ramdisk_size=ramdisk, page_size=4096,
                        os_version=os_version)
        kernel, _, ramdisk, _, second, _, _, page, version, os_version = struct.unpack_from('<10I', data, 8)
        info = dict(magic='ANDROID!', header_version=version, kernel_size=kernel, ramdisk_size=ramdisk, second_size=second,
                    page_size=page, os_version=os_version, board=data[48:64].split(b'\0')[0].decode(errors='replace'))
        if version >= 2:
            info['dtb_size'] = struct.unpack_from('<I', data, 1648)[0]
        return info
    if data[:8] == b'VNDRBOOT':
        # vendor_boot_img_hdr_v4: name[16] at 2080, header_size 2096, dtb_size 2100, dtb_addr 2104
        version, page = struct.unpack_from('<2I', data, 8)
        dtb_size = struct.unpack_from('<I', data, 2100)[0]
        return dict(magic='VNDRBOOT', header_version=version, page_size=page, dtb_size=dtb_size,
                    board=data[2080:2096].split(b'\0')[0].decode(errors='replace'))
    if data[:4] == b'AVB0':
        return dict(magic='AVB0')
    return dict(magic=data[:8].hex())


def lz4_legacy(data):
    """Decompresses the lz4 legacy frame format used for Android ramdisks."""
    if data[:4] != b'\x02\x21\x4c\x18':
        return None
    out, i = bytearray(), 4
    while i + 4 <= len(data):
        size = struct.unpack_from('<I', data, i)[0]
        i += 4
        if size == 0x184c2102:
            continue
        if size == 0 or i + size > len(data):
            break
        src, j, block = data[i:i + size], 0, bytearray()
        while j < len(src):
            token = src[j]; j += 1
            lit = token >> 4
            if lit == 15:
                while True:
                    b = src[j]; j += 1; lit += b
                    if b != 255:
                        break
            block += src[j:j + lit]; j += lit
            if j >= len(src):
                break
            off = src[j] | src[j + 1] << 8; j += 2
            match = token & 15
            if match == 15:
                while True:
                    b = src[j]; j += 1; match += b
                    if b != 255:
                        break
            start = len(block) - off
            for k in range(match + 4):
                block.append(block[start + k])
        out += block
        i += size
    return bytes(out)


def ramdisk_of(data, info):
    if info.get('magic') != 'ANDROID!' or not info.get('ramdisk_size'):
        return None
    page = info['page_size']
    off = page + (info['kernel_size'] + page - 1) // page * page
    return data[off:off + info['ramdisk_size']]


def avb_descriptors(vbmeta):
    text = subprocess.run(['avbtool', 'info_image', '--image', str(vbmeta)], capture_output=True, text=True, check=True).stdout
    found = []
    for block in text.split('Hash descriptor:')[1:]:
        block = block.split('descriptor:')[0]
        get = lambda key: re.search(rf'{key}:\s+(\S+)', block).group(1)
        found.append(dict(partition=get('Partition Name'), image_size=int(get('Image Size')), salt=get('Salt'), digest=get('Digest')))
    chains = re.findall(r'Chain Partition descriptor:\s+Partition Name:\s+(\S+)', text)
    hashtrees = re.findall(r'Hashtree descriptor:(?:.|\n)*?Partition Name:\s+(\S+)', text)
    algorithm = re.search(r'Algorithm:\s+(\S+)', text).group(1)
    flags = int(re.search(r'^Flags:\s+(\d+)', text, re.M).group(1))
    return dict(algorithm=algorithm, flags=flags, hash=found, chain=chains, hashtree=hashtrees)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', required=True)
    args = parser.parse_args()
    root = Path(args.dir)
    manifest = dict(schema_version=1, directory=str(root), images={}, avb={}, findings={})
    for name in PARTITIONS:
        path = root / f'{name}.img'
        data = path.read_bytes()
        info = boot_header(data)
        manifest['images'][name] = dict(size=len(data), sha256=hashlib.sha256(data).hexdigest(), header=info)
        if name == 'init_boot':
            rd = ramdisk_of(data, info)
            cpio = lz4_legacy(rd) if rd else None
            manifest['findings']['init_boot_magisk'] = bool(cpio and b'.backup/.magisk' in cpio)
    images = {name: (root / f'{name}.img').read_bytes() for name in PARTITIONS}
    avb = avb_descriptors(root / 'vbmeta.img')
    for d in avb['hash']:
        img = images.get(d['partition'])
        got = hashlib.sha256(bytes.fromhex(d['salt']) + img[:d['image_size']]).hexdigest() if img else None
        d['actual'] = got
        d['matches'] = got == d['digest']
    manifest['avb'] = avb
    manifest['findings']['stock_per_vbmeta'] = sorted(d['partition'] for d in avb['hash'] if d['matches'])
    manifest['findings']['avb_mismatch'] = sorted(d['partition'] for d in avb['hash'] if not d['matches'])
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
