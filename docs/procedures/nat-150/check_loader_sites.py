#!/usr/bin/env python3
"""NAT-150 (after NAT-151): the loader's own checkpoint checks, compiled for the host, on a built image's payload.

The loader holds kernel virtual addresses as constants: the five LOADER_CHECKPOINT sites of start.s (ckpt.c), the slot (ckpt.h),
loader_jump, _set_mmu_ttb, loader_return_entered, _invalid_ttep and arm_vm_init's set_mmu_ttb call (ckpt3.h). NAT-151 failed because
the scG kernel moved five sites, loader_jump and _set_mmu_ttb (start.patch inserts code before them) while the loader kept the old
addresses: the loader's checks read other instructions and the loader took an exception before the kernel ran.

This runs nat036_check() (ckpt.c + ckpt3.c with -DNAT031_HOST, the NAT-036 host harness's build) from the image's own loader source
tree on the image's own payload: the window the loader copies the kernel into, built from the payload's segment table. rc 0 is the
loader's own verdict that every constant matches the kernel; anything else is the code the loader would fail with (or the trap it
would take). Also lists each constant against the kernel's symbols.

  python3 -B docs/procedures/nat-150/check_loader_sites.py --build artifacts/nat-150/build-001 --image loader-diag-xnu-scG-md1
"""
import argparse
import ctypes
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VIRT = 0xfffffff004000000
UPTO = 0x3e00000
STUB, STUB_END = 0x9e2d80000, 0x9e2d80140         # the NAT-036 host test's stub range (inside one 2 MiB block)
STOPS = (11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16)
RC = {0: 'ok', 1: 'NAT031_SLOT_BAD', 2: 'NAT031_SITE_BAD', 3: 'NAT036_LIST_BAD', 4: 'NAT036_BLOCK_BAD', 5: 'NAT036_JUMP_BAD',
      6: 'NAT036_SETTTB_BAD', 7: 'NAT036_FLAG_BAD', 8: 'NAT059_VMTTB_BAD'}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def constants(src):
    """The kernel VAs the loader source holds, by name."""
    out = {}
    ck = (src / 'ckpt.c').read_text()
    sites = re.search(r'\{([^}]*0xfffffff0[^}]*)\}', ck)[1]
    for i, v in enumerate(re.findall(r'0x([0-9a-f]{16})ULL', sites), 1):
        out['site%d' % i] = int(v, 16)
    for f in ('ckpt.h', 'ckpt3.h'):
        for name, v in re.findall(r'#define\s+(\w+_VA)\s+0x([0-9a-f]{16})ULL', (src / f).read_text()):
            out[name] = int(v, 16)
    return out


def run(build, image):
    build = Path(build)
    src = build / image / 'source/shim/e1s-xnu'
    ap = load('nat150_ap_chk', ROOT / 'docs/procedures/nat-029/analyze_payload.py')
    pay = ap.Payload(str(build / image / 'payload.adt8.bin'))
    buf = bytearray(UPTO)
    for vm, vs, fo, fs in pay.segs:
        off = vm - pay.virt_base
        if off < UPTO:
            n = min(fs, UPTO - off)
            buf[off:off + n] = pay.b[fo:fo + n]
    with tempfile.TemporaryDirectory() as t:
        so = Path(t) / 'ckpt3.so'
        subprocess.run(['cc', '-O1', '-Wall', '-Wextra', '-Werror', '-DNAT031_HOST', '-fsanitize=alignment',
                        '-fsanitize-undefined-trap-on-error', '-shared', '-fPIC', '-I%s' % src, str(src / 'ckpt.c'), str(src / 'ckpt3.c'),
                        '-o', str(so)], check=True)
        # in a child process: a wrong constant can make the check read outside the window (NAT-151's trap on the phone)
        code = ('import ctypes,sys\nlib=ctypes.CDLL(sys.argv[1]);data=open(sys.argv[2],"rb").read()\n'
                'buf=(ctypes.c_char*len(data)).from_buffer_copy(data)\nu64,u32=ctypes.c_uint64,ctypes.c_uint32\n'
                'lib.nat036_check.argtypes=[ctypes.c_size_t,u64,u64,u64,ctypes.c_void_p,u32,ctypes.POINTER(u32)]\n'
                'stops=bytes(%r);a=(ctypes.c_uint8*len(stops))(*stops);bad=u32(99)\n'
                'rc=lib.nat036_check(ctypes.addressof(buf),%d,%d,%d,ctypes.addressof(a),len(stops),ctypes.byref(bad))\n'
                'print(rc,bad.value)\n') % (bytes(STOPS), VIRT, STUB, STUB_END)
        img = Path(t) / 'window.bin'
        img.write_bytes(bytes(buf))
        p = subprocess.run([sys.executable, '-c', code, str(so), str(img)], capture_output=True, text=True)
    if p.returncode != 0:
        result = dict(rc=None, verdict='trap (child exit %d)' % p.returncode, bad=None)
    else:
        rc, bad = map(int, p.stdout.split())
        result = dict(rc=rc, verdict=RC.get(rc, '?'), bad=bad)
    return result, constants(src)


def symbolize(kernel_dir, consts):
    vi = load('nat150_vi_chk', ROOT / 'fixtures/public/e1s-native-link-image/verify_image.py')
    u = sorted(Path(kernel_dir).glob('link*/kernel/kernel.unstripped'))[0]
    syms = sorted((int(l.split()[0], 16), l.split()[2]) for l in vi.tool('nm', '-n', str(u)).splitlines() if len(l.split()) == 3)
    out = {}
    for name, va in consts.items():
        best = max((s for s in syms if s[0] <= va), default=None)
        out[name] = '%s+0x%x' % (best[1], va - best[0]) if best else None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--build', required=True)
    ap.add_argument('--image', required=True)
    ap.add_argument('--kernel-dir')
    a = ap.parse_args()
    res, consts = run(a.build, a.image)
    out = dict(check=res, constants={k: hex(v) for k, v in consts.items()})
    if a.kernel_dir:
        out['symbols'] = symbolize(a.kernel_dir, consts)
    print(json.dumps(out, indent=1))
    return 0 if res['rc'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
