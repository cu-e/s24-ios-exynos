#!/usr/bin/env python3
"""Build NAT-022 images on the host. Never opens a phone or writes a partition.

  build.py --out DIR [--loader-source COPY_OF_build-003/source]
  build.py --check-only      (build to a temp dir, verify, discard)
Outputs: canary-plain/Image, canary-fault/Image, canary-trig/Image (DECON0 kick, MK_TRIG=1), canary-trig-fault/Image (kick + BRK, MK_TRIG=1), [loader-diag/Image(.payload), loader-diag-trig-hold/Image(.payload): stage markers with a kick and a dwell, halted at pre-jump, never executes the payload; loader-diag-trig-hold-adt8/Image(.payload): the same loader Image with the payload header's adt_size rounded up to 8 by fix_payload.py (NAT-026; run 004 stopped on that check); loader-diag-trig-hold-adt8-aln/Image(.payload): that image with adt_patch.c's 64-bit ADT accesses split into aligned 32-bit accesses by patch_loader.py --adt-aligned (NAT-027; run 005 took an alignment fault in adt_set_dram); loader-diag-xnu-entry/Image(.payload): that image plus the NAT-028 stub at the kernel copy's entry, which the loader jumps to (the stub draws STAGE 0x50 and holds; no kernel instruction runs)].
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, shutil, struct, subprocess, sys, tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
B3 = ROOT / 'artifacts/nat-020/build-003'
FLAGS = ['-target', 'aarch64-freestanding', '-O2', '-g0', '-ffreestanding', '-fno-builtin',
         '-fno-stack-protector', '-fno-pic', '-fno-zero-initialized-in-bss', '-mstrict-align',
         '-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror']
log = []
payload_fixes = {}

def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    log.append({'argv': [str(a) for a in argv], 'exit_code': p.returncode, 'stderr': p.stderr[-2000:]})
    if p.returncode:
        raise SystemExit(f'{argv[0]} failed:\n{p.stderr}')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def pad_image(path):
    d = Path(path).read_bytes()
    assert d[56:60] == b'ARM\x64', 'missing arm64 magic'
    size = struct.unpack_from('<Q', d, 16)[0]
    assert 64 <= size <= 16 << 20 and len(d) <= size, 'bad image_size'
    Path(path).write_bytes(d + b'\0' * (size - len(d)))

def link(objs, ld, elf, img):
    run(['zig', 'cc', '-target', 'aarch64-freestanding', '-static', '-nostdlib', '-Wl,--build-id=none',
         f'-Wl,-T,{ld}', *objs, '-o', elf])
    run(['zig', 'objcopy', '-O', 'binary', elf, img])
    pad_image(img)

def build_canary(out, name, fault, trig=False, fault_round=None):
    d = out / name; d.mkdir(parents=True)
    o = []
    for src, extra in (('canary.S', []), ('markerlib.c', [f'-DMK_TRIG={int(trig)}'] + ([f'-DMK_FAULT_ROUND={fault_round}'] if fault_round is not None else [])),
                       ('canary.c', [f'-DCANARY_FAULT={int(fault)}'])):
        obj = d / (src + '.o')
        run(['zig', 'cc', *FLAGS, *extra, f'-I{HERE/"src"}', '-c', HERE / 'src' / src, '-o', obj])
        o.append(obj)
    link(o, HERE / 'src/canary.ld', d / 'canary.elf', d / 'Image')
    return d / 'Image'

def _fix_payload():
    spec = importlib.util.spec_from_file_location('fix_payload', HERE / 'fix_payload.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.fix

def build_loader(out, source, name='loader-diag', trig_hold=False, fix_adt=False, adt_aligned=False, xnu_entry=False):
    d = out / name; d.mkdir(parents=True)
    src = d / 'source'
    shutil.copytree(source, src, ignore=shutil.ignore_patterns('out', '.git'))
    run([sys.executable, '-I', HERE / 'patch_loader.py', src] + (['--trig-hold'] if trig_hold else []) +
        (['--adt-aligned'] if adt_aligned else []) + (['--xnu-entry'] if xnu_entry else []))
    e = src / 'shim/e1s-xnu'
    shutil.copy(HERE / 'src/marker.h', e); shutil.copy(HERE / 'src/markerlib.c', e)
    names = ['start.S', 'loader.c', 'ui.c', 'adt_patch.c', 'gic.c', 'fdt.c', 'guard.c', 's5e9945.c', 'markerlib.c']
    if xnu_entry:
        for f in ('xnu_entry.h', 'xnu_entry.c', 'xnu_stub.S'):
            shutil.copy(HERE / 'src' / f, e)
        names += ['xnu_entry.c', 'xnu_stub.S']
    objs = []
    for c in names:
        obj = d / (c + '.o')
        extra = ['-DMK_TRIG=1', '-DMK_LOADER=1'] + (['-DMK_XNU_ENTRY=1'] if xnu_entry else []) if trig_hold and c == 'markerlib.c' else []
        run(['zig', 'cc', *[f for f in FLAGS if f != '-Werror'], *extra, f'-I{e}', '-c', e / c, '-o', obj])
        objs.append(obj)
    link(objs, e / 'loader.ld', d / 'loader.elf', d / 'Image')
    payload = B3 / 'payload.bin'
    if payload.exists() and fix_adt:
        fixed, info = _fix_payload()(payload.read_bytes())
        payload = d / 'payload.adt8.bin'
        payload.write_bytes(fixed)
        payload_fixes[name] = info
    if payload.exists():
        run([sys.executable, '-I', src / 'tools/e1s/append_payload.py', '--loader', d / 'Image',
             '--payload', payload, '--output', d / 'Image.payload'])
    return d / 'Image'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out'); ap.add_argument('--loader-source'); ap.add_argument('--check-only', action='store_true')
    a = ap.parse_args()
    tmp = tempfile.TemporaryDirectory() if a.check_only else None
    out = Path(tmp.name) / 'o' if tmp else Path(a.out)
    if out.exists(): raise SystemExit('refusing existing output directory')
    out.mkdir(parents=True)
    imgs = {'canary-plain': build_canary(out, 'canary-plain', False),
            'canary-fault': build_canary(out, 'canary-fault', True),
            'canary-trig': build_canary(out, 'canary-trig', False, trig=True),
            'canary-trig-fault': build_canary(out, 'canary-trig-fault', True, trig=True, fault_round=0)}
    if a.loader_source:
        imgs['loader-diag'] = build_loader(out, Path(a.loader_source))
        imgs['loader-diag-trig-hold'] = build_loader(out, Path(a.loader_source), 'loader-diag-trig-hold', trig_hold=True)
        imgs['loader-diag-trig-hold-adt8'] = build_loader(out, Path(a.loader_source), 'loader-diag-trig-hold-adt8', trig_hold=True, fix_adt=True)
        imgs['loader-diag-trig-hold-adt8-aln'] = build_loader(out, Path(a.loader_source), 'loader-diag-trig-hold-adt8-aln', trig_hold=True, fix_adt=True, adt_aligned=True)
        imgs['loader-diag-xnu-entry'] = build_loader(out, Path(a.loader_source), 'loader-diag-xnu-entry', trig_hold=True, fix_adt=True, adt_aligned=True, xnu_entry=True)
    for n, p in imgs.items():
        d = Path(p).read_bytes()
        assert d[56:60] == b'ARM\x64' and struct.unpack_from('<Q', d, 8)[0] == 0x80000
        assert len(d) == struct.unpack_from('<Q', d, 16)[0] and len(d) < 1 << 20, n
    if a.check_only:
        print('ok', {n: Path(p).stat().st_size for n, p in imgs.items()}); return
    (out / 'build.json').write_text(json.dumps({
        'kind': 'host-test', 'device_used': False, 'flashed': False,
        'images': {n: {'path': str(Path(p).relative_to(out)), 'sha256': sha(p), 'bytes': Path(p).stat().st_size} for n, p in imgs.items()},
        'image_payloads': {n: {'path': str((Path(p).parent / 'Image.payload').relative_to(out)), 'sha256': sha(Path(p).parent / 'Image.payload'),
                               'bytes': (Path(p).parent / 'Image.payload').stat().st_size}
                           for n, p in imgs.items() if (Path(p).parent / 'Image.payload').exists()},
        'payload_fixes': payload_fixes,
        'commands': log}, indent=1))
    print(json.dumps({n: sha(p) for n, p in imgs.items()}, indent=1))

if __name__ == '__main__':
    main()
