#!/usr/bin/env python3
"""NAT-064 host check: rebuild the existing payload with the pinned mkpayload.py and show what a ramdisk changes.

Reads only files that exist in the project (artifacts/nat-020/build-003, artifacts/nat-062/package-001 neighbours);
writes only below --out. Nothing here touches the phone.

  python3 -I docs/procedures/nat-064/compare_payloads.py --out artifacts/nat-064/compare --json OUT.json
"""
import argparse, hashlib, json, os, struct, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
B20 = os.path.join(ROOT, 'artifacts/nat-020/build-003')
SRC = os.path.join(B20, 'source')
MKPAYLOAD = os.path.join(SRC, 'tools/e1s/xnu/mkpayload.py')
KERNEL = os.path.join(B20, 'kernel.no-storage')
ADT = os.path.join(B20, 'e1s.adt')
PAYLOAD20 = os.path.join(B20, 'payload.bin')
NAT62_PAYLOAD = os.path.join(ROOT, 'artifacts/nat-064/rebuild/nat062-payload.bin')  # copy of the NAT-062 patched payload
RAMDISK = os.path.join(ROOT, 'artifacts/nat-064/stage0/sweet-init')
CMD_OFF, CMD_LEN, SEG_TABLE = 0x48, 608, 0x2a8


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def header(b):
    magic, ver, nsegs = struct.unpack_from('<8sII', b, 0)
    virt_base, entry, adt_off, adt_size, kend, phys_base, mem_size = struct.unpack_from('<7Q', b, 0x10)
    cmd = b[CMD_OFF:CMD_OFF + CMD_LEN].split(b'\0')[0].decode()
    segs = [struct.unpack_from('<4Q', b, SEG_TABLE + 32 * i) for i in range(nsegs)]
    return dict(magic=magic.decode(), version=ver, nsegs=nsegs, virt_base=hex(virt_base), entry=hex(entry),
                adt_off=adt_off, adt_size=adt_size, adt_size_mod8=adt_size % 8, kernel_end_va=hex(kend),
                phys_base=hex(phys_base), mem_size=hex(mem_size), cmdline=cmd, size=len(b),
                segs=[dict(vmaddr=hex(a), vmsize=hex(s), file_off=o, file_size=n) for a, s, o, n in segs])


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return dict(argv=[os.path.relpath(a, ROOT) if os.path.isabs(a) else a for a in args], exit_code=r.returncode,
                stdout=r.stdout.strip().splitlines()[:30], stderr=r.stderr.strip()[-400:])


def diff_ranges(a, b, limit=20):
    n = min(len(a), len(b))
    out, i = [], 0
    while i < n and len(out) < limit:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--json', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    p20 = open(PAYLOAD20, 'rb').read()
    h20 = header(p20)
    res = dict(inputs={os.path.relpath(p, ROOT): sha(p) for p in (MKPAYLOAD, KERNEL, ADT, PAYLOAD20, NAT62_PAYLOAD, RAMDISK)},
               nat020_payload=h20, steps=[])

    # 1. rebuild without ramdisk with the command line stored in the existing payload
    out1 = os.path.join(a.out, 'rebuild-noramdisk.bin')
    st = run([sys.executable, '-I', MKPAYLOAD, KERNEL, ADT, out1, '--cmdline', h20['cmdline']])
    st['sha256'] = sha(out1)
    st['equal_to_nat020_payload'] = open(out1, 'rb').read() == p20
    res['steps'].append(dict(name='rebuild-noramdisk', **st))

    # 2. same with the NAT-062 command line; compare to the NAT-062 patched payload
    p62 = open(NAT62_PAYLOAD, 'rb').read()
    h62 = header(p62)
    out2 = os.path.join(a.out, 'rebuild-nat062-cmdline.bin')
    st = run([sys.executable, '-I', MKPAYLOAD, KERNEL, ADT, out2, '--cmdline', h62['cmdline']])
    b2 = open(out2, 'rb').read()
    st['sha256'] = sha(out2)
    st['equal_to_nat062_payload'] = b2 == p62
    st['diff_ranges_vs_nat062_payload(offset,len)'] = diff_ranges(b2, p62)
    st['rebuilt_header'] = header(b2)
    res['nat062_payload'] = h62
    res['steps'].append(dict(name='rebuild-with-nat062-cmdline', **st))

    # 3. with the stage-0 ramdisk; the NAT-062 command line already starts with rd=md0 (NAT-063 panicked on exactly that),
    #    the two boot-args of the upstream userland smoke test are added for the ad-hoc signed test binary
    cmd3 = h62['cmdline'] + ' launchdsuffix=release cs_enforcement_disable=1'
    out3 = os.path.join(a.out, 'rebuild-ramdisk.bin')
    st = run([sys.executable, '-I', MKPAYLOAD, KERNEL, ADT, out3, '--cmdline', cmd3, '--ramdisk', RAMDISK])
    b3 = open(out3, 'rb').read()
    st['sha256'] = sha(out3)
    st['header'] = header(b3)
    st['size_delta_vs_nat062_payload'] = len(b3) - len(p62)
    st['adt_size_delta_vs_nat062_payload'] = st['header']['adt_size'] - h62['adt_size']
    st['ramdisk_bytes'] = os.path.getsize(RAMDISK)
    res['steps'].append(dict(name='rebuild-with-ramdisk', **st))
    json.dump(res, open(a.json, 'w'), indent=1, sort_keys=True)
    print(json.dumps({s['name']: {k: s[k] for k in s if k.startswith('equal') or k in ('exit_code', 'sha256')} for s in res['steps']}, indent=1))


main()
