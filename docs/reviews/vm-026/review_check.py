#!/usr/bin/env python3
"""REV-031 bounded independent byte and immutable source controls; never boots XNU."""
import argparse, hashlib, importlib.util, json, os, pathlib, resource, signal, struct, subprocess, sys, time
from datetime import datetime, timezone
P = pathlib.Path
ap=argparse.ArgumentParser(); ap.add_argument('--main',type=P,required=True); ap.add_argument('--producer',type=P,required=True); ap.add_argument('--out',type=P,required=True); a=ap.parse_args()
resource.setrlimit(resource.RLIMIT_AS,(256<<20,256<<20)); signal.alarm(120)
a.out.mkdir(parents=True,exist_ok=False)
started=time.monotonic(); commands=[]; bindings={}
def sha(p):
    with P(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def bound(p):
    p=P(p); h=sha(p); bindings[str(p)]=h; return h
def git(repo,*args):
    argv=['/usr/bin/git','-C',str(repo),*args]
    r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'})
    i=len(commands); (a.out/f'command-{i}.stdout').write_bytes(r.stdout); (a.out/f'command-{i}.stderr').write_bytes(r.stderr)
    commands.append({'argv':argv,'exit_code':r.returncode,'stdout':str(a.out/f'command-{i}.stdout'),'stderr':str(a.out/f'command-{i}.stderr')}); assert r.returncode==0,commands[-1]; return r.stdout
freeze='ffd08db8616f7a486762b951dc69a9ace8716dea'; final='a47a378dac38a0e86f6e7abd66c12f28390fa245'
tool=a.producer/'tools/build/avf_guest_boot_memory.py'; pins_path=a.producer/'fixtures/public/avf-guest-boot-memory/source-pins.json'
for rel,commit in [('tools/build/avf_guest_boot_memory.py',freeze),('fixtures/public/avf-guest-boot-memory/source-pins.json',freeze),('docs/procedures/avf-guest-boot-memory/evidence.json',final),('docs/procedures/avf-guest-boot-memory/handoff.md',final)]:
    assert git(a.producer,'show',f'{commit}:{rel}')==(a.producer/rel).read_bytes(); bound(a.producer/rel)
assert sha(tool)=='e2623a3a1aadd5dc1e3a592ff174eae36ee46eb0091bd53d90d0f4e700a86948'
pins=json.loads(pins_path.read_text()); source_checks=[]
for path,row in pins['scion'].items():
    b=git(a.main/'references/scion-avf','show',pins['scion_commit']+':'+path)
    h=hashlib.sha256(b).hexdigest(); blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    assert h==row['sha256'] and blob==row['git_blob_sha1']
    dest=a.out/'pinned-scion'/path; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(b); bound(dest)
    source_checks.append({'source':path,'sha256':h,'git_blob_sha1':blob})
prepared=a.main/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2'
assert bound(prepared/'prepared-component.json')==pins['prepared_component_sha256']
for path,row in pins['prepared_xnu'].items(): assert bound(prepared/'source/xnu'/path)==row['sha256']
qemu=a.main/'worktrees/vm-004-20261105/artifacts/qemu-host/release-10.2.0'
assert bound(qemu/'source-manifest.json')==pins['qemu']['source_manifest_sha256']
for path,row in pins['qemu']['files'].items(): assert bound(qemu/'source/qemu-10.2.0'/path)==row['sha256']
shim=a.main/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/Image'; assert bound(shim)==pins['qualified_shim']['sha256']
header=shim.read_bytes()[:64]; assert header[56:60]==b'ARM\x64'; assert struct.unpack_from('<QQ',header,8)==(0,0x1c000)
owner=json.loads((a.producer/'docs/procedures/avf-guest-boot-memory/evidence.json').read_text())
for rel,h in owner['artifact_hashes'].items(): assert bound(a.main/rel)==h
for rel in owner['artifacts']: bound(a.main/rel)
assert bound(a.producer/'artifacts/avf-guest-boot-memory/final-ffd08db/matrix.json')==owner['matrix_sha256']
assert len(owner['commands'])==7 and owner['cli_results']['source-only']['outcome']=='inconclusive'
assert sorted(x['exit_code'] for x in owner['commands'])==[0,0,0,2,2,2,2]
spec=importlib.util.spec_from_file_location('candidate',tool); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
# This independently declares Mach-O/XNUP format bytes. It is not a real kernel or reusable boot artifact.
VA=0xfffffff007000000
text=struct.pack('<II16sQQQQIIII',0x19,72,b'__TEXT',VA,0x4000,0,0x4000,7,5,0,0)
sec=struct.pack('<16s16sQQ8I',b'__kalloc_type',b'__DATA_CONST',VA+0x4000,16,0x4000,3,0,0,0,0,0,0)
data=struct.pack('<II16sQQQQIIII',0x19,152,b'__DATA_CONST',VA+0x4000,0x4000,0x4000,16,3,3,1,0)+sec
regs=[0]*34; regs[32]=VA+0x800
thread=struct.pack('<4I34Q',5,288,6,68,*regs); cmds=text+data+thread
image=(struct.pack('<8I',0xfeedfacf,0x100000c,0,2,3,len(cmds),0,0)+cmds).ljust(0x4010,b'\0')
body=struct.pack('<16sII',b'kernel',len(image),0)+image+b'\0'*(-len(image)%16)+bytes(24)
original=struct.pack('<II',0x50554e58,len(body))+body
base=32; pc_at=base+32+72+152+16+32*8; probes=[]
report={'commands':[]}; rules=m.source_rules(a.main,report)
plan={'ram_base':0x40000000,'ram_size':256<<20,'shim_base':0x40200000,'shim_image_size':0x1c000,'fdt_base':0x48200000,'fdt_size':0x10000,'payload_base':0x48000000,'fdt_bootargs':''}
def probe(name,changes=(),expected=None):
    b=bytearray(original)
    for fmt,offset,value in changes: struct.pack_into(fmt,b,offset,value)
    path=a.out/(name+'.xnup'); path.write_bytes(b); bound(path)
    try:
        pkg=m.payload(path); parsed=m.macho(path,pkg['entries']['kernel']); q=m.qemu_plan(plan,pkg,plan['shim_image_size']); result=m.layout_check(plan,parsed,pkg,rules)
        row={'case':name,'accepted':True,'entry_va':parsed['entry_va'],'entry_physical':result['entry_physical'],'entry_mod4':parsed['entry_va']%4,'window':result['window'],'topOfKernelData':result['topOfKernelData']}
    except (ValueError,UnicodeError,struct.error) as e: row={'case':name,'accepted':False,'error':str(e)}
    if expected is not None: assert row['accepted']==expected,row
    probes.append(row)
probe('independent-format-positive',expected=True)
probe('unaligned-pc-plus1',[('<Q',pc_at,VA+0x801)],True)
probe('unaligned-pc-plus2',[('<Q',pc_at,VA+0x802)],True)
probe('unaligned-pc-plus3',[('<Q',pc_at,VA+0x803)],True)
probe('aligned-pc-plus4',[('<Q',pc_at,VA+0x804)],True)
probe('pc-in-bss',[('<Q',pc_at,VA+0x4010)],False)
probe('pc-at-text-end',[('<Q',pc_at,VA+0x4000)],False)
probe('overlapping-vm',[('<Q',base+32+72+24,VA+0x3000)],False)
probe('file-offset-outside-entry',[('<Q',base+32+40,0x8000)],False)
probe('xnup-length-mismatch',[('<I',4,len(original))],False)
# Independent arithmetic from pinned shim constants: 256 MiB RAM - 512 KiB panic, round down32MiB.
assert probes[0]['window']==[0x40000000,0x4e000000] and probes[0]['topOfKernelData']==0x4301c000
for name,p in [('ram-overflow',{**plan,'ram_base':(1<<64)-4096}),('false-qemu-placement',{**plan,'fdt_base':0x48400000})]:
    pkg=m.payload(a.out/'independent-format-positive.xnup'); im=m.macho(a.out/'independent-format-positive.xnup',pkg['entries']['kernel'])
    try: m.qemu_plan(p,pkg,p['shim_image_size']); m.layout_check(p,im,pkg,rules)
    except ValueError as e: probes.append({'case':name,'accepted':False,'error':str(e)})
    else: raise AssertionError(name+' unexpectedly accepted')
# Genuine ARM64 start source establishes 4-byte instruction-aligned entry and 16KiB translation constraints; no CPU execution.
status=P('/proc/self/status').read_text(); hwm=next(x for x in status.splitlines() if x.startswith('VmHWM:'))
result={'recorded_at':datetime.now(timezone.utc).isoformat(),'task':'REV-031','experiment':'REVBOOTMEM-001','kind':'host-test','origin':'local-host','outcome':'fail','summary':'Three independently mutated unaligned LC_UNIXTHREAD PCs pass exact static preflight; source/producer binding and remaining focused controls pass. No compile or guest.','candidate_commit':freeze,'producer_metadata_commit':final,'commands':commands,'sources':source_checks,'qualified_shim_image_size':0x1c000,'producer_artifact_hashes_verified':len(owner['artifact_hashes']),'probes':probes,'bindings':bindings,'elapsed_seconds':time.monotonic()-started,'memory':hwm,'compiler_executed':False,'qemu_executed':False,'limitations':['Owned synthetic format fixtures are not XNU.','No final real kernel image, runtime FDT/MMU/allocator or256MiB sufficiency measured.','No native Exynos/iOS/privateABI proof.']}
(a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps({'outcome':result['outcome'],'counterexamples':3,'focused_cases':len(probes),'artifact':str(a.out/'result.json'),'seconds':result['elapsed_seconds'],'memory':hwm}))
