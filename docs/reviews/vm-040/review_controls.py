#!/usr/bin/env python3
"""Independent frozen VM040 source/parser/record controls; no guest/compiler."""
import copy,hashlib,importlib.util,json,resource,socket,struct,sys,time
from pathlib import Path
from unittest.mock import patch
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');P=MAIN/'worktrees/vm-040-eh-20261106';HERE=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def main():
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
 out=HERE/'runs/source-controls-1';out.mkdir(parents=True,exist_ok=False)
 r={'kind':'independent-source-host-controls','checks':[],'rejections':[],'bindings':[],'kernel_executed':False,'QEMU_executed':False,'compiler_executed':False,'outcome':'fail'}
 def check(n,v,**extra):
  r['checks'].append({'name':n,'passed':bool(v),**extra})
  if not v:raise ValueError(n)
 def bind(p,h):
  check('binding:'+str(p),sha(p)==h);r['bindings'].append({'path':str(p),'sha256':h,'bytes':p.stat().st_size})
 def reject(n,fn):
  try:fn()
  except(ValueError,OSError,TypeError,KeyError,struct.error)as e:r['rejections'].append({'name':n,'error':str(e)});return
  raise ValueError('Unexpected acceptance:'+n)
 try:
  for f,h in [('tools/run/avf_kernel_boot.py','82dc4f31e0a43431e49741bc26368ff81c3820a21985a97fef82c11f6f9e6589'),('fixtures/public/avf-kernel-boot/inputs.json','d302c61daaf6bea3a90d29ead6b02f00a5cc4fb5c1e34eec5b4fd63dd596a637'),('docs/procedures/avf-kernel-boot/handoff.md','336e4bd87019420f2033316993111156de9d4b38a75881fd631f7830dfdc3a13'),('docs/procedures/avf-kernel-boot/evidence.json','8262406bb0d684fba7e1b3e31b9cd1e6bad8fba347d968e2e04cbae1ad644083')]:bind(P/f,h)
  raw=P/'artifacts/avf-kernel-boot/measurement-9efba94-1/evidence.json';bind(raw,'08b82cb55c6d8dd593bfd28b8ae6bed95bf515e7967b2d633c8d23c508504271');ev=json.loads(raw.read_text())
  for path,h in {**ev['artifact_sha256'],**ev['source_sha256']}.items():bind(MAIN/path,h)
  spec=importlib.util.spec_from_file_location('frozen_vm040',P/'tools/run/avf_kernel_boot.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);pins=c.read_json(c.FIXTURE)
  check('closed-image-allowlist',pins['image_admissions']==[])
  for row in [*pins['helpers'].values(),*pins['bindings'],pins['vm022_plan'],pins['qemu'],pins['shim']]:
   p=c.binding(MAIN,row);check('actual-pin:'+str(p),sha(p)==row['sha256'])
  with patch.object(c.subprocess,'Popen',side_effect=AssertionError('No process may start for absent image')):
   reject('absent-image-before-any-child',lambda:c.prepare(MAIN,'current',HERE/'not-created'))
  check('no-absent-image-output',(HERE/'not-created').exists()is False)
  stopped=c.Stop();stopped.request('review Stop')
  reject('Stop-before-prepare',lambda:c.prepare(MAIN,'current',HERE/'not-created',stopped))
  for n,b in [('duplicate',b'{"x":1,"x":2}'),('nonfinite',b'{"x":NaN}')]:reject('json-'+n,lambda:c.decode_json(b))
  local=out/'local';local.mkdir();f=local/'bound';f.write_bytes(b'reviewer-control');row={'path':'bound','sha256':sha(f),'size':f.stat().st_size}
  check('valid-private-binding',c.binding(local,row)==f);f.write_bytes(b'changed');reject('changed-private-binding',lambda:c.binding(local,row));(local/'alias').symlink_to('bound');reject('alias-binding',lambda:c.inside(local,'alias'));reject('traversal-binding',lambda:c.inside(local,'../bound'))
  package=c.read_json(c.binding(MAIN,pins['vm022_plan']),bound=16<<20)
  check('real-object-plan1080',len(package['ordered_object_map'])==1080)
  reject('incomplete-object-lineage',lambda:c.object_lineage(MAIN,{'objects':[]},package['ordered_object_map'],c.Stop()))
  full='debug=0x8 rd=md0 '+c.APPEND;c.combined_arguments(full)
  reject('append-only-not-full-args',lambda:c.combined_arguments(c.APPEND));reject('conflicting-args',lambda:c.combined_arguments(full+' avf_exit=0'))
  fd=P/'artifacts/avf-kernel-boot/controls-9efba94-1/fdt/authored-input.dtb';data=fd.read_bytes();c.fdt(data)
  for n,b in [('truncation',data[:-1]),('wrongmagic',b'\0'*4+data[4:])]:reject('fdt-'+n,lambda:c.fdt(b))
  props=c.fdt(data);bad=dict(props);bad[('/psci','method')]=b'smc\0';reject('fdt-smc',lambda:c.fdt_contract(bad,{'payload_base':0x48000000},{'size':64}))
  # Independent socket messages: no threads, processes or QEMU are necessary.
  for n,msg,action in [('boolean-id',b'{"return":{},"id":true}\n','command'),('wrong-id',b'{"return":{},"id":99}\n','command'),('scalar',b'[]\n','receive'),('bad-event-data',b'{"event":"SHUTDOWN","data":true}\n','receive')]:
   a,b=socket.socketpair()
   try:
    b.sendall(msg);q=c.QMP(a,lambda:None,[]);reject('QMP-'+n,lambda:q.command('query-status')if action=='command'else q.receive())
   finally:a.close();b.close()
  a,b=socket.socketpair()
  try:
   q=c.QMP(a,lambda:None,[]);reject('QMP-forbidden-quit',lambda:q.command('quit'));reject('QMP-bool-size',lambda:q.command('pmemsave',{'val':0x48000000,'size':True,'filename':'input-fdt.dtb'}))
  finally:a.close();b.close()
  captured=c.read_json(P/'artifacts/avf-kernel-boot/controls-9efba94-1/process-qmp-peer/record.json')
  events=[x['message']for x in captured['qmp']if x['direction']=='received'and'event'in x['message']]
  check('actual-host-peer-is-not-guest',captured['guest_started']is False and captured['input_fdt']['Apple_serialized_tree']is False and next(x for x in events if x['event']=='SHUTDOWN')['data']=={'guest':False,'reason':'host-qmp-quit'}and captured['live_owned_pids']==[])
  # AUTHORed observation contrast; never genuine-kernel data.
  text=('avfboot: HakiOS XNU boot for crosvm/AVF and QEMU virt\navfboot: boot-args: '+full+'\navfboot: jumping to XNU at 0xfffffff007004000\nDarwin Kernel Version authored-control\nVM002: pid=1 ostype=Darwin owned-entry=v1\navf: kernel panic: panic(initproc exited)\navf: powering off (PSCI SYSTEM_OFF)\n').encode()
  record={'resume_observed':True,'cont_acknowledged_at':'author-control','input_fdt':{'authored':True},'exit_code':0,'live_owned_pids':[],'stop_reason':None,'host_signals':[],'timed_out':False,'guest_started':True,'elapsed_seconds':.1,'deadline_seconds':1,'combined_boot_args':full}
  guest=[{'event':'SHUTDOWN','data':{'guest':True,'reason':'guest-shutdown'}}]
  ans=c.assess_observations(text,guest,record);check('authored-positive-never-qualifies',ans['classification']=='consistent-observations-awaiting-review'and ans['genuine_kernel_qualified']is False and ans['pid1_runtime_qualified']is False and ans['PSCI_instruction_traced']is False)
  cases=[('actual-host-peer-shutdown',text,events,record),('repeated-banner',text+b'Darwin Kernel Version again',guest,record),('duplicate-shutdown',text,guest+guest,record),('timeout',text,guest,{**record,'timed_out':True}),('host-signal',text,guest,{**record,'host_signals':['SIGTERM']}),('wrong-final-args',text,guest,{**record,'combined_boot_args':c.APPEND}),('nan-time',text,guest,{**record,'elapsed_seconds':float('nan')}),('bool-exit',text,guest,{**record,'exit_code':False})]
  for n,raw,events,h in cases:check('observation-'+n,c.assess_observations(raw,events,h)['classification']=='inconclusive')
  r['outcome']='pass'
 except Exception as e:r['error']={'type':type(e).__name__,'message':str(e)}
 r['proc_self_VmHWM_bytes']=int(next(x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmHWM:')).split()[1])*1024;r['reviewer_sha256']=sha(__file__)
 save(out/'report.json',r);print(json.dumps({'outcome':r['outcome'],'checks':len(r['checks']),'rejections':len(r['rejections']),'bindings':len(r['bindings']),'error':r.get('error')}));return 0 if r['outcome']=='pass'else 1
if __name__=='__main__':raise SystemExit(main())
