#!/usr/bin/env python3
"""Focused actual-artifact and real-pathname regression controls; never build."""
import argparse
import ast
from datetime import datetime,timezone
import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--main',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
spec=importlib.util.spec_from_file_location('adapter',ROOT/'tools/build/avf_guest_components.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=m.canonical_path(a.out)
if not out.is_relative_to(ROOT/'artifacts/avf-guest-components') or out.exists():raise ValueError('Fresh owned control directory required')
ledger=m.load(a.main/'state/lab.json')
if not any(e['id']=='AVFCOMP-002' and e['status']=='planned' and e['owner']=='codex-guest-next-executor-20261106-dz' for e in ledger['experiments']):raise ValueError('Register focused experiment first')
out.mkdir(parents=True);checks=[];start=time.monotonic();report={'kind':'host-test','origin':'local-host','outcome':'fail','task':'VM-036','experiment':'AVFCOMP-002','recorded_at':datetime.now(timezone.utc).isoformat(),'argv':sys.orig_argv,'checks':checks,'source_sha256':m.sha(Path(m.__file__)),'control_sha256':m.sha(Path(__file__)),'compiler_executed':False,'archiver_executed':False,'loader_executed':False,'guest_executed':False,'historical_native_artifacts_are_only_parser_controls':True}
def check(name,fn,reject=False):
 try:r=fn()
 except (ValueError,PermissionError,OSError,struct.error) as error:
  if not reject:raise
  checks.append({'name':name,'outcome':'pass','actual_rejection':str(error),'error_type':type(error).__name__});return
 if reject:raise AssertionError('Incorrectly admitted '+name)
 checks.append({'name':name,'outcome':'pass'});return r

def member(name,body,bsd=False):
 rawname=b''
 if bsd or len(name)>15:
  raw=name.encode();rawname=raw+b'\0'*((-len(raw))%8)+b'\0'*4;label='#1/'+str(len(rawname))
 else:label=name+'/'
 payload=rawname+body
 header=label.ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(payload)).ljust(10)+'`\n'
 if len(header)!=60:raise AssertionError('Invalid control header')
 return header.encode()+payload+(b'\n' if len(payload)%2 else b'')

def indexed(name,body):
 width=8 if '_64' in name else 4;word='<Q' if width==8 else '<I';pair='<QQ' if width==8 else '<II';strings=b'___firehose_buffer_create\0';strings+=b'\0'*((-len(strings))%8)
 def toc(offset):return struct.pack(word,2*width)+struct.pack(pair,0,offset)+struct.pack(word,len(strings))+strings
 offset=8+len(member(name,toc(0),True))
 return b'!<arch>\n'+member(name,toc(offset),True)+member('provider.o',body)
try:
 helperpath=a.main/'worktrees/vm-035-20261106/tools/build/avf_kernel_objects.py'
 h=m.module(helperpath,'5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8','real_helper')
 guest=a.main/'worktrees/vm-018-20261106/artifacts/avf-object-shards/platform-support/execute-001/objects/pexpert/bootargs.o'
 native=a.main/'artifacts/xnu-kernel-firehose-headers/contracts-session2/genuine-provider.o'
 layout=a.main/'artifacts/xnu-kernel-firehose-headers/contracts-session2/provider-layout.o'
 llvm_archive=a.main/'artifacts/xnu-kernel-firehose-headers/contracts-session2/current-profile-libfirehose_kernel.a'
 real_archive=a.main/'artifacts/xnu-macho-tools/macho-session4/fixtures/libfixture.a'
 tool=a.main/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool'
 report['historical_inputs']={str(p):m.sha(p) for p in [guest,native,layout,real_archive,llvm_archive,tool]}
 target=out/'provider.o';replacement=out/'replacement.o';command={'id':'firehose/provider','object':str(target)}
 shutil.copyfile(guest,target)
 check('actual guest negative object lacks provider definition',lambda:m.inspect_object(command,'firehose',h),True)
 shutil.copyfile(native,replacement);called=[]
 def swap_after_real_validation(path,**kwargs):
  info=h.macho(path,**kwargs);called.append(str(path));os.replace(replacement,target);return info
 check('P2-1 actual pathname swap cannot borrow native provider symbols',lambda:m.inspect_object(command,'firehose',SimpleNamespace(macho=swap_after_real_validation)),True)
 if len(called)!=1 or not called[0].startswith('/proc/self/fd/') or m.sha(target)!=m.sha(native):raise AssertionError('Actual sealed snapshot/path replacement did not occur')
 check('helper saw sealed fd while actual source pathname was replaced',lambda:None)
 # A valid parser witness remains bound to its bytes even if its original path
 # changes after validation; it can never authorize different archive bytes.
 shutil.copyfile(native,target);shutil.copyfile(guest,replacement)
 info=check('captured native parser witness stays internally consistent',lambda:m.inspect_object(command,'firehose',SimpleNamespace(macho=swap_after_real_validation)))
 if info['sha256']!=m.sha(native) or m.sha(target)!=m.sha(guest) or not info['snapshot_sealed']:raise AssertionError('Mixed snapshot identity')
 arc=out/'race.a';arc.write_bytes(b'!<arch>\n'+member('provider.o',target.read_bytes()))
 check('captured good metadata cannot authorize restored bad guest member',lambda:m.inspect_archive({'archive':str(arc),'members':[str(target)]},{str(target):info}),True)
 # The underlying snapshot denies writes independent of mutable path aliases.
 shutil.copyfile(native,target);denials=[]
 def write_attempt(path,**kwargs):
  fd=int(Path(path).name)
  try:os.pwrite(fd,b'X',0)
  except OSError as error:
   if error.errno!=errno.EPERM:raise
   denials.append(error.errno)
  else:raise AssertionError('Sealed snapshot remained writable')
  return h.macho(path,**kwargs)
 check('actual sealed memfd refuses pwrite',lambda:m.object_details(target,SimpleNamespace(macho=write_attempt)))
 if denials!=[errno.EPERM]:raise AssertionError('Missing real seal denial')
 # All section bytes, including probe bytes, are captured before closing fd.
 shutil.copyfile(layout,target);shutil.copyfile(guest,replacement)
 sections=check('actual historical probe bytes survive original path replacement',lambda:m.object_details(target,SimpleNamespace(macho=swap_after_real_validation)))
 original_sections=m.object_details(layout,h)
 if sections['sha256']!=m.sha(layout) or sections['sections']!=original_sections['sections'] or not any('captured_data_hex'in s for s in sections['sections']):raise AssertionError('Probe payload borrowed another pathname')
 bad=out/'truncated.o';bad.write_bytes(guest.read_bytes()[:20]);check('truncated object remains rejected',lambda:m.object_details(bad,h),True)
 bad.write_bytes(guest.read_bytes()[:4]+struct.pack('<I',0x1000007)+guest.read_bytes()[8:]);check('wrong CPU object remains rejected',lambda:m.object_details(bad,h),True)
 # Real source-built historical archive is only a format witness.
 parsed=check('actual historical cctools archive TOC structure',lambda:m.archive_members(real_archive,True));report['historical_archive_format_witness']=parsed
 check('unselected LLVM archive layout is not relabeled as cctools',lambda:m.archive_members(llvm_archive),True)
 provenance=a.main/'artifacts/xnu-macho-tools/macho-session4/report.json'
 report['historical_cctools_provenance']={'path':str(provenance),'sha256':m.sha(provenance)}
 if not parsed['toc_name']:raise AssertionError('Historical witness has no real TOC')
 body=native.read_bytes();shutil.copyfile(native,target);accepted={str(target):m.inspect_object(command,'firehose',h)}
 for name in sorted(m.TOC_NAMES):
  arc.write_bytes(indexed(name,body));check('genuine-format synthetic '+name,lambda:m.inspect_archive({'archive':str(arc),'members':[str(target)]},accepted))
  arc.write_bytes(b'!<arch>\n'+member(name,b'foreign payload',True)+member('provider.o',body));check('malformed known TOC '+name,lambda:m.archive_members(arc),True)
 arc.write_bytes(b'!<arch>\n'+member('provider.o',body)+member('__.SYMDEF_bad',b'foreign non-symbol-table payload'))
 check('P2-2 exact extraordinary reserved prefix counterexample',lambda:m.inspect_archive({'archive':str(arc),'members':[str(target)]},accepted),True)
 good=indexed('__.SYMDEF',body)
 # Offset/string/count corruption uses real small archive bytes only.
 for label,mutator in [('foreign offset',lambda b:b.__setitem__(slice(8+60+20+8,8+60+20+12),struct.pack('<I',1))),('bad table size',lambda b:b.__setitem__(slice(8+60+20,8+60+20+4),struct.pack('<I',7))),('bad string index',lambda b:b.__setitem__(slice(8+60+20+4,8+60+20+8),struct.pack('<I',0xffffffff)))]:
  changed=bytearray(good);mutator(changed);arc.write_bytes(changed);check(label,lambda:m.archive_members(arc),True)
 toc=member('__.SYMDEF',struct.pack('<II',0,0));arc.write_bytes(b'!<arch>\n'+toc+toc+member('provider.o',body));check('duplicate genuine TOC',lambda:m.archive_members(arc),True)
 arc.write_bytes(b'!<arch>\n'+member('provider.o',body)+toc);check('nonleading genuine TOC',lambda:m.archive_members(arc),True)
 arc.write_bytes(b'!<arch>\n'+member('__.SYMDEF',struct.pack('<II',0,8)+b'FOREIGN!',True)+member('provider.o',body));check('unreferenced foreign TOC payload',lambda:m.archive_members(arc),True)
 for extent in ['-1','0','+1','999999']:
  header=('#1/'+extent).ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+'4'.ljust(10)+'`\n';arc.write_bytes(b'!<arch>\n'+header.encode()+b'tiny')
  check('bounded BSD name extent '+extent,lambda:m.archive_members(arc),True)
 arc.write_bytes(b'!<arch>\nshort');check('truncated ar header',lambda:m.archive_members(arc),True)
 # Reproduce P2-3 on a non-executed owned copy of the real qualified ELF.
 unit=m.load(a.main/'worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/bounded-plan-session1/plan.json','1243849185135bb9ab7f861faf4d8fe2fed0c9dcae1e57165a2e9ff7a86008dc')
 copied=out/'archiver-control-copy';shutil.copyfile(tool,copied);cache=h.Digests()
 before=check('owned actual ELF bytes and stable identity are bound',lambda:m.runtime_snapshot(copied,out,unit,h,cache))
 if before['executable']['sha256']!=m.sha(copied) or str(copied) not in before['host_file_bindings']:raise AssertionError('Executable absent from actual content/identity binding')
 with copied.open('ab') as stream:stream.write(b'UNQUALIFIED_TOOL_BYTE_CHANGE')
 check('P2-3 append to real owned tool copy rejected after command boundary',lambda:m.runtime_snapshot(copied,out,unit,h,cache),True)
 shutil.copyfile(tool,copied);same=check('same-byte ELF rewrite valid content but new identity',lambda:m.runtime_snapshot(copied,out,unit,h,cache))
 if same==before or same['executable']['sha256']!=before['executable']['sha256']:raise AssertionError('Same-byte file identity change was hidden')
 replacement=out/'changed-tool';replacement.write_bytes(copied.read_bytes()+b'changed');original_elf=m.elf
 def elf_then_swap(path,stream=None):
  facts=original_elf(path,stream)
  if Path(path)==copied:os.replace(replacement,copied)
  return facts
 m.elf=elf_then_swap
 try:check('actual ELF pathname replacement during parse fails closed',lambda:m.runtime_snapshot(copied,out,unit,h,cache),True)
 finally:m.elf=original_elf
 if m.sha(tool)!=report['historical_inputs'][str(tool)]:raise AssertionError('Original host tool changed')
 check('actual qualified tool untouched and never executed',lambda:None)
 # Prove narrow scope and retain the accepted process quarantine.
 oldpath=a.main/'worktrees/vm-036-dz-fix1-20261106/tools/build/avf_guest_components.py';old=m.module(oldpath,'5152e733f95da9b0d2a01da6e1eb9b1b22d9bd75bc47187387e19d29e515d718','old')
 def functions(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 olds,news=functions(oldpath),functions(Path(m.__file__))
 changed={name for name in olds if olds[name]!=news.get(name)}
 if changed!={'elf','runtime_snapshot','object_details','inspect_object','archive_members','inspect_archive'}:raise AssertionError('Unexpected old function changes '+str(changed))
 if m.load(m.POLICY,m.POLICY_SHA256)['prospective_process']['independently_accepted'] is not False:raise AssertionError('Quarantined process policy changed')
 check('only six reviewed boundaries changed; execute/quarantine unchanged',lambda:None)
 baseline=a.main/'worktrees/vm-036-dz-fix1-20261106/artifacts/avf-guest-components/handoff-002/evidence.json';prior=m.load(baseline,'7d6cd9a2246f53ce428cf71b40bc019650f6a14a44ad46e56d456e2fa28413d7')
 for path,digest in {**prior['artifact_hashes'],**prior['source_bindings']}.items():
  if m.sha(a.main/path)!=digest:raise AssertionError('Prior frozen artifact/source changed')
 check('all125 prior artifacts and frozen5152 source bindings preserved',lambda:None)
 report.update(outcome='pass',summary={'checks_passed':len(checks),'historical_baseline_checks_reused':88,'historical_followup_checks_reused':12,'new_component_products':0,'compiler_or_archiver_or_loader_commands':0},prior_evidence=str(baseline),prior_evidence_sha256=m.sha(baseline))
except BaseException as error:
 report['failure']={'type':type(error).__name__,'message':str(error)};raise
finally:
 report.update(elapsed_seconds=time.monotonic()-start,current_image_memory=h.actual_controller_memory() if 'h' in locals() else {})
 m.write(out/'evidence.json',report)
print(json.dumps(report['summary']))
