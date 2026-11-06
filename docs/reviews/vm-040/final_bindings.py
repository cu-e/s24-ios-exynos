#!/usr/bin/env python3
"""Read-only final original/correction capsule and index binding check."""
import hashlib,importlib.util,json,resource
from pathlib import Path
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');HERE=Path(__file__).resolve().parent
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
rows=[]
def bind(p,h):
 actual=sha(p);rows.append({'path':str(p),'sha256':actual,'expected_sha256':h,'bytes':p.stat().st_size});assert actual==h,str(p)
r={'kind':'read-only-host-binding-check','outcome':'fail','bindings':rows,'compiler_executed':False,'QEMU_executed':False,'guest_executed':False}
try:
 capsules=[('worktrees/vm-040-eh-20261106/artifacts/avf-kernel-boot/measurement-9efba94-1/evidence.json','08b82cb55c6d8dd593bfd28b8ae6bed95bf515e7967b2d633c8d23c508504271'),('worktrees/vm-040-lease-20261106/artifacts/avf-kernel-boot/lease-4f5fa22-1/evidence.json','af030005d05a00a4f68e6995f78abb624b1f325f512600e5832f52228960f110'),('worktrees/vm-040-lease-20261106/artifacts/avf-kernel-boot/fdt-4f5fa22-1/evidence.json','872a33cf0af56a5a7051fc4dc9c175a7b99e9a5ead6a828a6df4eb98700cd16c'),('worktrees/vm-040-consumer-20261106/artifacts/avf-kernel-boot/consumer-c8bd677-1/evidence.json','0da4671e19d14bd1df6f853a39425e3aa95c14996ff7bb51783a5530ba0a9d1e')]
 for name,h in capsules:
  p=MAIN/name;bind(p,h);x=json.loads(p.read_text());assert x['outcome']=='pass'
  for n,h in {**x['artifact_sha256'],**x['source_sha256']}.items():bind(MAIN/n,h)
 for x in json.loads((HERE/'initial-artifact-index.json').read_text()):bind(Path(x['path']),x['sha256'])
 tool=MAIN/'worktrees/vm-040-consumer-20261106/tools/run/avf_kernel_boot.py';bind(tool,'233da39b23ea8986e83db6bfdceb8f23c52b0c6ac044f7f1d5f30d451e145c06')
 spec=importlib.util.spec_from_file_location('final_consumer',tool);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 peer=MAIN/'worktrees/vm-040-lease-20261106/artifacts/avf-kernel-boot/fdt-4f5fa22-1/process-qmp-peer'
 rec=json.loads((peer/'record.json').read_text());raw=(peer/'input-fdt.dtb').read_bytes()
 checked=c.fdt_contract(c.fdt(raw),{'payload_base':0x48000000},{'size':64})
 events=[x['message']for x in rec['qmp']if x['direction']=='received'and'event'in x['message']]
 assert rec['guest_started']is False and rec['live_owned_pids']==[] and rec['host_signals']==[]
 assert next(x for x in events if x['event']=='SHUTDOWN')['data']=={'guest':False,'reason':'host-qmp-quit'}
 r['historical_corrected_peer']={'captured_by_tool_sha256':'341d813ca808cfdc9490a692dc4eb1261bf494c1964c19e4f653df130063bdc2','final_current_parser_accepts_same_bytes':True,'input_fdt_sha256':sha(peer/'input-fdt.dtb'),'source_control_only':True,'guest_started':False,'events':events,'contract':checked}
 r['outcome']='pass'
except Exception as e:r['error']={'type':type(e).__name__,'message':str(e)}
r['proc_self_VmHWM_bytes']=int(next(x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmHWM:')).split()[1])*1024
out=HERE/'runs/final-bindings-1';out.mkdir(parents=True,exist_ok=False);(out/'report.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'outcome':r['outcome'],'bindings':len(rows),'error':r.get('error')}));raise SystemExit(0 if r['outcome']=='pass'else 1)
