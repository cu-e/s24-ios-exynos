#!/usr/bin/env python3
"""Rebuild a host-only hardened image from the preserved NAT-006 source/payload."""
from pathlib import Path
import subprocess,sys,runpy,json,hashlib
root=Path.cwd(); out=Path(sys.argv[1]).resolve(); src=out/'source'; ld=out/'loader'; ld.mkdir(exist_ok=True)
base=runpy.run_path('worktrees/nat-006-recovery-image-20261110/tools/build/e1s_recovery.py')
commands=[]
def run(args):
    args=list(map(str,args)); r=subprocess.run(args,capture_output=True,text=True)
    commands.append(dict(argv=args,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
    (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    if r.returncode: raise RuntimeError(r.stderr)
    return r.stdout
files=base['LOADER_FILES'][:]
if (src/'shim/e1s-xnu/recovery_guard.c').exists(): files+=['s5e9945.c','recovery_guard.c']
objects=[]
for f in files:
    obj=ld/(f+'.o'); objects.append(obj)
    run(['zig','cc','-target','aarch64-freestanding',*base['CFLAGS'],'-c',src/'shim/e1s-xnu'/f,'-o',obj])
    if f.endswith('.c'):
        rel=run(['readelf','-rW',obj]); assert 'R_AARCH64_ABS' not in rel,f
run(['zig','cc','-target','aarch64-freestanding','-static','-nostdlib','-Wl,--build-id=none','-Wl,-T,'+str(src/'shim/e1s-xnu/loader.ld'),*objects,'-o',ld/'loader.elf'])
run(['zig','objcopy','-O','binary',ld/'loader.elf',ld/'Image'])
run(['python3','-I',src/'tools/e1s/fix_image.py',ld/'Image'])
payload=root/'artifacts/nat-006/build-002/payload.bin'
run(['python3','-I',src/'tools/e1s/append_payload.py','--loader',ld/'Image','--payload',payload,'--output',out/'Image.payload'])
stock=(root/base['STOCK_RECOVERY']).read_bytes(); assert base['sha256'](stock)==base['STOCK_RECOVERY_SHA256']
ramdisk=base['newc_cpio']([base['PLACEHOLDER']])
image,_=base['build_recovery'](stock,(out/'Image.payload').read_bytes(),ramdisk)
(out/'recovery.img').write_bytes(image)
run(['python3','-I','worktrees/nat-006-recovery-image-20261110/docs/procedures/nat-006/verify_image.py','--image',out/'recovery.img','--stock',root/base['STOCK_RECOVERY'],'--kernel',root/base['KERNEL'],'--restore-dir',root/'artifacts/nat-006/build-002/restore','--dtb',root/'devices/e1s-fdt/2026-11-10/runtime.dtb','--out',out/'verify.json'])
print('PASS: rebuilt RECOVERY, independent verifier, all C ABS relocations absent')
