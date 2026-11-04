#!/usr/bin/env python3
"""Translate owned AIR-shaped bitcode, validate SPIR-V and execute it on host Lavapipe."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
APP=Path(__file__).resolve().parent


def check_layout(data):
    layout=data['layout']
    sets=layout['sets']
    if data['kind']!='compute' or len(sets)!=1 or sets[0]['set']!=0:raise ValueError('Fixture set interface changed')
    bindings=sets[0]['bindings']
    if len(bindings)!=1 or (bindings[0]['binding'],bindings[0]['ty'],bindings[0]['count'])!=(0,7,1):raise ValueError('Fixture storage buffer interface changed')
    push=layout['push_constants']
    if len(push)!=1 or (push[0]['offset'],push[0]['size'],push[0]['stages'])!=(0,4,32):raise ValueError('Fixture push constants changed')
    stages=data['stages']
    if len(stages)!=1 or stages[0]['entry_point']!='main':raise ValueError('Fixture entry changed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--translator',type=Path,required=True)
    p.add_argument('--ndk',type=Path,default=Path('/home/egor/Android/Sdk/ndk/28.2.13676358'));args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):raise ValueError('Invalid run name')
    out=ROOT/'artifacts/metal-fixture'/args.run
    if out.resolve()!=out:raise ValueError('Run path cannot use symlinks')
    out.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'VK_ICD_FILENAMES':'/usr/share/vulkan/icd.d/lvp_icd.x86_64.json'}
    llvm=args.ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-as';validator=args.ndk/'shader-tools/linux-x86_64/spirv-val'
    report={'schema_version':1,'kind':'host-test','origin':'local-host','outcome':'inconclusive','recorded_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'commands':[],'native_s24_verified':False,'apple_metal_reference':False,'translator_sha256':hashlib.sha256(args.translator.read_bytes()).hexdigest()}
    def run(argv):
        x=subprocess.run([str(a) for a in argv],cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
        report['commands'].append({'argv':[str(a) for a in argv],'exit_code':x.returncode,'stdout':x.stdout,'stderr':x.stderr})
        if x.returncode:raise RuntimeError(x.stderr or x.stdout)
        return x.stdout
    try:
        run([llvm,'--version'])
        run([llvm,APP/'fixtures/write_marker.ll','-o',out/'write_marker.air'])
        run([args.translator.resolve(),out/'write_marker.air',out/'write_marker.spv','--profile',APP/'fixtures/host-profile.json','--function','write_marker','--emit-meta',out/'meta.json'])
        check_layout(json.loads((out/'meta.json').read_text()))
        run([validator,'--target-env','vulkan1.2',out/'write_marker.spv'])
        run(['c++','-std=c++17','-O2','-Wno-missing-field-initializers',APP/'run_compute.cpp','-lvulkan','-o',out/'run_compute'])
        actual=json.loads(run([out/'run_compute',out/'write_marker.spv']))
        if actual!={'environment':'host-vulkan','expected':9212400,'actual':9212400,'guard_words_intact':True,'outcome':'pass'}:raise ValueError('Compute reference/guard mismatch')
        report.update(outcome='pass',result=actual,summary='Owned synthetic AIR-shaped fixture translated, independently SPIR-V validated and executed with exact host output')
        report['sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [APP/'fixtures/write_marker.ll',APP/'fixtures/host-profile.json',out/'write_marker.spv',out/'meta.json']}
    except Exception as error:report.update(outcome='fail',error=str(error))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
