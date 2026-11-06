#!/usr/bin/env python3
"""Bound frozen public source bodies and future commands, without running tools."""
import hashlib
import json
from pathlib import Path
import time
from datetime import datetime, timezone

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = MAIN/'worktrees/gpu-012-20261106'
HERE = Path(__file__).resolve().parent
OUT = HERE/'runs/intake1'
FILES = {}
CHECKS = []

def read(p, expected=None):
    data = p.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if expected and sha != expected:
        raise ValueError('Changed frozen input: '+str(p))
    FILES[str(p.relative_to(MAIN))] = sha
    return data

def check(value, label):
    if not value:
        raise ValueError(label)
    CHECKS.append(label)

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    samples=[]
    for n in range(3):
        mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','SwapFree:'))}
        samples.append(mem)
        check(mem['MemAvailable']>=4*1024**3,'stable4GiB-'+str(n))
        if n<2:time.sleep(1)
    started=time.monotonic()
    source_plan=WT/'artifacts/gpu-userclient/source-4/plan/plan.json'
    plan=json.loads(read(source_plan,'eb688252e2d8af9c8f941662672f5430a5ec9f0bba15c6b59a0e4c66dc0a9863'))
    comp=MAIN/'worktrees/vm-007-20261105/artifacts/avf-kernel-source/compose-final-ed9fdbf/composition-manifest.json'
    composed=json.loads(read(comp,'3c04c89c13f1d2c00fc8d101de4481063acf247d4cc793b71f2ef79aa5a2bdd4'))
    rows={r['path']:r for r in composed['profiles']['qemu']['files']}
    root=MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2/source/xnu'
    selected={str(Path(d['path']).relative_to(root)):d for d in plan['genuine_declarations']}
    selected['iokit/Kernel/IOUserClient.cpp']={}
    for rel,d in selected.items():
        r=rows[rel];data=read(root/rel,r['sha256'])
        oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        check(oid==r['oid'],'complete canonical Git body: '+rel)
        if d:check(d['canonical_git_blob_sha1']==oid and d['sha256']==r['sha256'],'plan canonical binding: '+rel)
    manifest=MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json'
    genuine={r['id']:r for r in json.loads(read(manifest,'afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd'))}
    local={'adapter':WT/'src/platform/gpu/native/userclient/SGPUUserClient.cpp',
           'policy':WT/'src/platform/gpu/native/userclient/Policy.cpp',
           'dispatcher':WT/'src/platform/gpu/abi/sgpu_abi.c'}
    for c in plan['target_compile_plan']:
        r=genuine[c['derived_from']];a=list(r['next_owned_compile_argv_template'])
        a[a.index(r['bound_source'])]=str(local[c['name']])
        a[a.index('-o')+1]=c['output']
        dep=str(source_plan.parent/'dependencies'/f"{c['name']}.d")
        a[a.index('-MF')+1]=dep
        a=['-I'+r['cwd'] if x=='-I.' else x for x in a]
        if c['name']=='dispatcher' and not any(x.startswith('-std=') for x in a):a.insert(1,'-std=gnu11')
        check(a==c['argv'],'exact declared argv transformation: '+c['name'])
        check(c['cwd']==str(source_plan.parent/'work'),'explicit owned target cwd: '+c['name'])
    for r in plan['owned_sources']+plan['inputs']:
        if str(r['path']).startswith(str(WT)):
            read(Path(r['path']),r['sha256'])
    check(plan['execution_authorized'] is False and plan['compiler_executed'] is False and plan['host_controls_executed'] is False and plan['guest_executed'] is False,'unmeasured source-plan boundaries')
    report={'kind':'host-test','origin':'local-host','outcome':'pass','task':'INT-003',
      'owner':'codex-integrator-platform-20261106-cn','experiment':'PLATGPU-001',
      'recorded_at':datetime.now(timezone.utc).isoformat(),'source_tip':'de6c14afef8e2de29f06cc16ede6023ef0824f5c',
      'summary':'Bounded GPU012 public-body/future-recipe intake passes; no product compilation or runtime acceptance.',
      'commands':[{'argv':['python3','-B','-s',str(Path(__file__))],'exit_code':0}],
      'checks':CHECKS,'elapsed_seconds':time.monotonic()-started,'admission':samples,
      'proc_status':[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))],
      'artifacts':list(FILES),'artifact_sha256':FILES,
      'intake_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'compiler_sanitizer_loader_guest_device_executed':False,
      'virtual_overrides_native_ABI_or_hardware_qualified':False,
      'next':'Refresh future execution/process/runtime/namespace/resource admission before a separate root compile lease; retain inconclusive producer task.'}
    (OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'checks':len(CHECKS),'files':len(FILES),'proc_status':report['proc_status'],
                      'elapsed_seconds':report['elapsed_seconds'],'evidence_sha256':hashlib.sha256((OUT/'evidence.json').read_bytes()).hexdigest()}))

if __name__=='__main__':main()
