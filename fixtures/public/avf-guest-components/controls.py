#!/usr/bin/env python3
"""Finite source-only controls. Synthetic bytes never count as a new object build."""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import struct
import sys
import time
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]

def main():
 p=argparse.ArgumentParser();p.add_argument('--main',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
 spec=importlib.util.spec_from_file_location('adapter',ROOT/'tools/build/avf_guest_components.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
 out=v.canonical_path(a.out);allowed=ROOT/'artifacts/avf-guest-components'
 if not out.is_relative_to(allowed) or out==allowed or out.exists():raise ValueError('Fresh owned control directory required')
 ledger=v.load(a.main/'state/lab.json')
 if not any(e['id']=='AVFCOMP-001' and e['owner']=='codex-guest-next-executor-20261106-dz' and e['status']=='planned' for e in ledger['experiments']):raise ValueError('Register source experiment first')
 out.mkdir(parents=True);started=time.monotonic();checks=[]
 report={'kind':'host-test','origin':'local-host','outcome':'fail','task':'VM-036','recorded_at':datetime.now(timezone.utc).isoformat(),'commands':[{'argv':sys.argv,'exit_code':None}],'checks':checks,'compiler_executed':False,'archive_tool_executed':False,'guest_executed':False,'synthetic_cases_are_hardware_evidence':False,'source_sha256':v.sha(Path(v.__file__)),'control_sha256':v.sha(Path(__file__))}
 def check(name,fn,reject=False):
  try:r=fn()
  except (ValueError,FileNotFoundError,KeyError,struct.error) as error:
   if not reject:raise
   checks.append({'name':name,'outcome':'pass','actual_rejection':str(error)});return
  if reject:raise AssertionError('Incorrectly admitted '+name)
  checks.append({'name':name,'outcome':'pass'});return r
 try:
  cases={}
  for kind in ['firehose','pthread']:
   cases[kind]=check(kind+' exact original four-command source unit',lambda k=kind:v.prepare(a.main,k))
   policy,h,unit,commands,index,target=cases[kind]
   rawsource=v.load(a.main/policy['pins'][kind+'_source']['path'])
   if kind=='pthread':
    producer=v.module(a.main/policy['pins']['pthread_producer']['path'],policy['pins']['pthread_producer']['sha256'],'test_execution_predicate')
    changed=copy.deepcopy(rawsource);changed['translation_units'][0]['argv_template'].append('-UDEBUG');check('pthread changed canonical full source plan',lambda:producer.validate_plan(changed),True)
   for label,mutate in [('append response',lambda x:x.append('@hostile.rsp')),('append plugin',lambda x:x.extend(['-Xclang','-load','bad.so'])),('prepend override',lambda x:x.insert(1,'-UDEBUG')),('drop option',lambda x:x.pop(1)),('source substitution',lambda x:x.__setitem__(next(i for i,a in enumerate(x) if a.endswith('.c')),'/wrong.c')),('compiler substitution',lambda x:x.__setitem__(0,'/usr/bin/cc')),('extra include',lambda x:x.extend(['-I','/tmp/headers'])),('output escape',lambda x:x.__setitem__(x.index('-o')+1,str(target/'../escape.o')))]:
    changed=copy.deepcopy(unit);mutate(changed['commands'][0]['argv']);check(kind+' '+label,lambda d=changed:v.validate_commands(kind,d,rawsource,target),True)
   for flag in ['-DMACH_ASSERT=1','-DDEBUG=1'] if kind=='pthread' else ['-DDEVELOPMENT=1']:
    changed=copy.deepcopy(unit);argv=changed['commands'][0]['argv']
    actual=next((x for x in argv if x==flag or x.startswith(flag.split('=')[0]+'=')),None)
    if actual:argv.remove(actual)
    else:argv.append('-U'+flag[2:].split('=')[0])
    check(kind+' altered '+flag,lambda d=changed:v.validate_commands(kind,d,rawsource,target),True)
   changed=copy.deepcopy(unit);changed['commands'][0]['cwd']='/';check(kind+' changed cwd',lambda:v.validate_commands(kind,changed,rawsource,target),True)
   changed=copy.deepcopy(unit);changed['commands'].pop();check(kind+' failed/missing compile continuation',lambda:v.validate_commands(kind,changed,rawsource,target),True)
   changed=copy.deepcopy(unit);changed['commands'][3]['argv'][4]='/nonexistent-filelist';check(kind+' changed filelist',lambda:v.validate_commands(kind,changed,rawsource,target),True)
   fake=out/(kind+'-raw-plan.json');fake.write_text('{}')
   check(kind+' raw source hash',lambda:v.load(fake,policy['pins'][kind+'_source']['sha256']),True)
   # Live original authority check, no mkdir. Use a synthetic exact local
   # ledger copy only for negative cases; source plan has no execute grant.
   args=SimpleNamespace(main=a.main,task=policy['components'][kind]['task'],owner=policy['components'][kind]['owner'],experiment='AVFFH-001' if kind=='firehose' else 'AVFPTH-003')
   check(kind+' original owner authority',lambda:v.owner_authority(ledger,policy['components'][kind],args,target))
   bad=copy.copy(args);bad.owner='wrong-owner';check(kind+' wrong owner',lambda:v.owner_authority(ledger,policy['components'][kind],bad,target),True)
   bad=copy.copy(args);bad.task='VM-036';check(kind+' generic executor task',lambda:v.owner_authority(ledger,policy['components'][kind],bad,target),True)
   bad=copy.copy(args);bad.experiment='AVFCOMP-001';check(kind+' other experiment',lambda:v.owner_authority(ledger,policy['components'][kind],bad,target),True)
   altered=copy.deepcopy(ledger);next(t for t in altered['tasks'] if t['id']==args.task)['paths']=[];check(kind+' absent literal scope',lambda:v.owner_authority(altered,policy['components'][kind],args,target),True)
   check(kind+' sibling output scope',lambda:v.owner_authority(ledger,policy['components'][kind],args,a.main/'artifacts/escape'),True)
   # Actual real namespace preparation; no upstream/header review repeated.
   cache=h.Digests();inputs=check(kind+' actual reduced namespace',lambda:v.snapshot(commands,index,h,target,cache));v.write(out/(kind+'-input-bindings.json'),inputs)
   for c in commands:
    check(kind+' ELF and search namespace '+c['id'],lambda row=c:v.runtime_snapshot(Path(row['argv'][0]),Path(row['cwd']),unit,h,cache))
   report.setdefault('original_units',{})[kind]={'path':policy['pins'][kind+'_unit']['path'],'sha256':policy['pins'][kind+'_unit']['sha256'],'argv_sha256':[c['argv_sha256'] for c in commands],'namespace_sha256':inputs['sha256'],'files':len(inputs['files'])}
  helper=cases['pthread'][1]
  local=out/'real-fs';local.mkdir();source=local/'source.c';source.write_text('/* source-only filesystem control */\n');header=local/'header.h';header.write_text('/* header */\n')
  target=out/'not-created-execution';commands=[{'argv':['cc','-I',str(local)],'cwd':str(local),'source':str(source)}]*3
  index={str(p):v.sha(p) for p in [source,header]};cache=helper.Digests();base=check('real filesystem namespace baseline',lambda:v.snapshot(commands,index,helper,target,cache))
  header.write_text('/* header */\n');check('same-byte real input rewrite invalidates attempt',lambda:v.unchanged_namespace(v.snapshot(commands,index,helper,target,cache),base),True)
  header.write_text('/* changed header */\n');check('changed real include',lambda:v.snapshot(commands,index,helper,target,cache),True);header.write_text('/* header */\n')
  shadow=local/'new.h';shadow.write_text('/* new shadow */\n');check('new real include shadow',lambda:v.snapshot(commands,index,helper,target,cache),True);shadow.unlink()
  header.unlink();check('missing real include',lambda:v.snapshot(commands,index,helper,target,cache),True);header.write_text('/* header */\n')
  filelink=local/'alias.h';filelink.symlink_to(header);symlink_index={**index,str(filelink):v.sha(header)};check('file symlink escape',lambda:v.snapshot(commands,symlink_index,helper,target,cache),True);filelink.unlink()
  linked=local/'linked';linked.symlink_to(out,target_is_directory=True);check('directory symlink escape',lambda:v.snapshot(commands,index,helper,target,cache),True);linked.unlink()
  check('output parent traversal',lambda:v.canonical_path(out/'artifacts/../escape'),True)
  link=out/'alias';link.symlink_to(local,target_is_directory=True);check('output symlink ancestry',lambda:v.canonical_path(link/'new'),True);link.unlink()
  obj=out/'dependency-object.o';obj.write_bytes(b'synthetic dependency fixture');dep=out/'dependency-object.d';dep.write_text(str(obj)+': '+str(source)+' '+str(header)+'\n');command={'depfile':str(dep),'cwd':str(local),'object':str(obj),'source':str(source)}
  inputs={'files':index};check('real dependency parser source/target',lambda:v.verify_dependencies(command,inputs,helper,helper.Digests()))
  header.write_text('/* changed header */\n');check('changed real dependency',lambda:v.verify_dependencies(command,inputs,helper,helper.Digests()),True);header.write_text('/* header */\n')
  dep.write_text('/wrong.o: '+str(source)+'\n');check('wrong dependency target',lambda:v.verify_dependencies(command,inputs,helper,helper.Digests()),True)
  dep.write_text(str(obj)+': '+str(header)+'\n');check('dependency omits actual source',lambda:v.verify_dependencies(command,inputs,helper,helper.Digests()),True)
  state={str(obj):{'sha256':v.sha(obj),'depfile':str(dep),'depfile_sha256':v.sha(dep),'dependencies':{str(source):v.sha(source)}}}
  check('current accepted output set',lambda:v.accepted_outputs(state,helper.Digests()))
  dep.write_text('changed dependency bytes');check('changed prior accepted depfile',lambda:v.accepted_outputs(state,helper.Digests()),True)
  closed=out/'closed-output';closed.mkdir();check('fresh closed output namespace',lambda:v.output_entries(closed,cases['pthread'][3],0))
  (closed/'header.h').write_text('new shadow');check('new owned cwd header shadow',lambda:v.output_entries(closed,cases['pthread'][3],0),True)
  # Genuine previously produced VM018 guest object as parser witness only.
  witness=a.main/'worktrees/vm-018-20261106/artifacts/avf-object-shards/platform-support/execute-001/objects/pexpert/bootargs.o'
  detail=check('read-only genuine prior ARM64 object parser witness',lambda:v.object_details(witness,helper));report['prior_object_witness']={'path':str(witness),'sha256':v.sha(witness),'reused_as_component':False,'raw_symbols':len(detail['symbols'])}
  for name,data in [('truncated',witness.read_bytes()[:20]),('wrongcpu',witness.read_bytes()[:4]+struct.pack('<I',0x1000007)+witness.read_bytes()[8:])]:
   path=out/(name+'.o');path.write_bytes(data);check(name+' object',lambda path=path:v.object_details(path,helper),True)
  check('required metadata missing',lambda:helper.macho(witness,require_metadata=True),True)
  def arfile(path,members):
   with path.open('wb') as f:
    f.write(b'!<arch>\n')
    for name,data in members:
     header=(name+'/').ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(data)).ljust(10)+'`\n';f.write(header.encode());f.write(data)
     if len(data)%2:f.write(b'\n')
  member=out/'one.o';member.write_bytes(witness.read_bytes());archive=out/'synthetic.a';accepted={str(member):{'sha256':v.sha(member),'definitions':['_fixture']}};cmd={'archive':str(archive),'members':[str(member)]}
  arfile(archive,[('__.SYMDEF',b''),('one.o',member.read_bytes())]);check('synthetic ar index/order/bytes parser',lambda:v.inspect_archive(cmd,accepted))
  for name,members in [('missing',[]),('probe',[('probe.o',member.read_bytes())]),('duplicate',[('one.o',member.read_bytes())]*2),('wrongbytes',[('one.o',b'native-or-corrupt')])]:
   arfile(archive,members);check('synthetic '+name+' archive',lambda:v.inspect_archive(cmd,accepted),True)
  arfile(archive,[('one.o',member.read_bytes())]);member.write_bytes(b'changed');check('changed inspected output before archive',lambda:v.inspect_archive(cmd,accepted),True)
  archive.write_bytes(b'!<arch>\nshort');check('truncated archive',lambda:v.archive_members(archive),True)
  for name,record in [('failed',{'outcome':'fail','exit_code':1}),('deferred',{'outcome':'resource-deferred','exit_code':None}),('live survivor',{'outcome':'pass','exit_code':0,'child_started':True,'after':{'owned_processes':[{'state':'S'}]}})]:check(name+' cannot continue',lambda r=record:v.success(r),True)
  check('clean successful process record',lambda:v.success({'outcome':'pass','exit_code':0,'child_started':True,'after':{'owned_processes':[]}}))
  # Cwd runtime shadows are actual temporary files. No loader is executed.
  unit=cases['pthread'][2];compiler=Path(cases['pthread'][3][0]['argv'][0]);cache=helper.Digests()
  runtime=check('real ELF runtime prospective mapping',lambda:v.runtime_snapshot(compiler,out,unit,helper,cache));shadow=out/'libc.so.6';shadow.write_bytes(b'unqualified')
  check('real cwd library shadow',lambda:v.runtime_snapshot(compiler,out,unit,helper,cache),True);shadow.unlink()
  changed=copy.deepcopy(unit);changed['ELF_runtime']['host_runtime_candidates']['libc.so.6']['sha256']='0'*64;check('stale runtime pin',lambda:v.runtime_snapshot(compiler,out,changed,helper,cache),True)
  check('incomplete actual loader mapping',lambda:v.loaded_runtime('linux-vdso.so.1 (0x0)\n',runtime),True)
  report.update(outcome='pass',summary={'checks_passed':len(checks),'compiler_or_archiver_commands':0,'component_objects_produced':0,'prior_object_witness_only':True});report['commands'][0]['exit_code']=0
 except Exception as e:
  report['error']=str(e);report['commands'][0]['exit_code']=1;raise
 finally:
  report.update(elapsed_seconds=time.monotonic()-started,current_image_memory=helper.actual_controller_memory() if 'helper' in locals() else {},inherited_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
  v.write(out/'evidence.json',report)
 print(json.dumps(report['summary']))
if __name__=='__main__':main()
