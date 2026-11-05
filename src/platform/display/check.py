#!/usr/bin/env python3
"""Owned host sanitizer plus compile-only ARM display/input checks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[3]
SRC=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--host-clang',type=Path,default=Path('/home/egor/.local/bin/clang'))
    p.add_argument('--clang',type=Path,default=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'))
    args=p.parse_args()
    if not args.run.replace('-','').replace('_','').isalnum() or len(args.run)>80:raise ValueError('Invalid run name')
    out=ROOT/'artifacts/display-contract'/args.run
    if out.resolve()!=out:raise ValueError('Run must not use symlinks')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='inconclusive',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),commands=[],sha256={},
                device_io=False,native_driver_built=False,apple_sdk_used=False,aarch64_executed=False)
    try:
        snapshot=out/'source';snapshot.mkdir()
        for name in ['contract.h','contract.c','fixture.c','layout.cpp','profile.json','check.py']:
            shutil.copyfile(SRC/name,snapshot/name)
            report['sha256'][str((SRC/name).relative_to(ROOT))]=hashlib.sha256((SRC/name).read_bytes()).hexdigest()
        def run(argv,env=None):
            argv=[str(a) for a in argv]
            try:r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,env=env,timeout=45)
            except subprocess.TimeoutExpired as error:
                report['commands'].append(dict(argv=argv,exit_code=None,timeout=True));raise RuntimeError('Process deadline exceeded') from error
            report['commands'].append(dict(argv=argv,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
            if r.returncode:raise RuntimeError(r.stderr or r.stdout)
            return r.stdout
        flags=['-Wall','-Wextra','-Werror','-Wpedantic']
        for compiler in ['cc',args.host_clang,args.clang]:run([compiler,'--version'])
        run(['cc','-std=c11',*flags,'-c',snapshot/'contract.c','-o',out/'host.o'])
        run(['cc','-std=c++17',*flags,'-c',snapshot/'layout.cpp','-o',out/'host-layout.o'])
        run([args.host_clang,'-std=c11',*flags,'-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined',snapshot/'contract.c',snapshot/'fixture.c','-o',out/'fixture'])
        result=json.loads(run([out/'fixture'],env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}))
        if result!=dict(outcome='pass',synthetic_cases=4096,device_io=False):raise ValueError('Fixture result mismatch')
        report['result']=result;report['object_headers']={}
        for target,label in [('aarch64-none-elf','elf'),('arm64-apple-ios16.5','macho')]:
            for name,standard in [('contract.c','-std=c11'),('layout.cpp','-std=c++17')]:
                obj=out/(label+'-'+name+'.o')
                run([args.clang,'--target='+target,'-ffreestanding',standard,*flags,'-c',snapshot/name,'-o',obj])
                detail=run([args.clang.parent/'llvm-readobj','--file-headers',obj])
                if ('elf64-littleaarch64' if label=='elf' else 'Mach-O arm64') not in detail:raise ValueError('Unexpected object format')
                report['object_headers'][obj.name]=detail
        for product in out.iterdir():
            if product.is_file():report['sha256'][str(product.relative_to(ROOT))]=hashlib.sha256(product.read_bytes()).hexdigest()
        report.update(outcome='pass',summary='Owned layout/coordinate/versioned-input host model passes sanitizers and four ARM object checks; no presentation or HID dispatch')
    except Exception as error:report.update(outcome='fail',error=str(error))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','summary','result','error']},indent=2))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
