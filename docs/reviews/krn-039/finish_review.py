#!/usr/bin/env python3
"""Bind completed leased guest results to prior independent static review. No guests."""
import argparse,datetime,hashlib,json,os,re,struct,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from macho import Object
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];IMPL=MAIN/'worktrees/krn-039-20261105'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def parts(raw):
 magic,length=struct.unpack_from('<II',raw);assert magic==0x50554e58 and length==len(raw)-8;at=8;out={}
 while at<len(raw):
  name,n,reserved=struct.unpack_from('<16sII',raw,at);at+=24;assert reserved==0 and n<=len(raw)-at;name=name.rstrip(b'\0').decode()
  if not name:assert n==0 and at==len(raw);break
  assert name not in out;out[name]=raw[at:at+n];at+=n+(-n%16)
 assert at==len(raw) and set(out)=={'kernel','cmdline'};return out
p=argparse.ArgumentParser();p.add_argument('--guest',type=Path,required=True);a=p.parse_args();OUT=ROOT/'artifacts/rev-kernel-des/20261106-final1';OUT.mkdir(parents=True,exist_ok=False)
for n in ['finish_review.py','macho.py']:(OUT/n).write_bytes((ROOT/'docs/reviews/krn-039'/n).read_bytes())
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),experiment='REVKDES-002',commit='8c3797d62efe6a800b9daa48fa01d8008b25b691',compiler_executed=False,test_binary_executed=False,QEMU_executed_by_reviewer=False,commands=[],final_integration_review_complete=False)
try:
 ledger=read(MAIN/'state/lab.json');ex=ledger['experiments'];ex=ex.values() if isinstance(ex,dict) else ex;plan=next(x for x in ex if x['id']=='REVKDES-002');assert plan['status']=='planned' and plan['task']=='REV-022' and plan['owner']=='codex-team-review-kernel-des-20261105-cl';(OUT/'actual-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 parents={}
 for name,expected in [('20261106-source1','668353568d5cb560fc273ac37c267c5b98280c83c7cb5647ba1909ec3998dd28'),('20261106-native4','75a451969b3ed3d9022ff891e288c391b23b856f7c651f65f81271c502f94021'),('20261106-arch2','070aac84287a97d67564aa99c3afd46df7879633742ab1b1f7af81f8f83585d0')]:
  path=ROOT/'artifacts/rev-kernel-des'/name/'evidence.json';assert sha(path)==expected;e=read(path);assert e['outcome']=='pass'
  for f,h in e['sha256'].items():assert sha(MAIN/f)==h,f
  parents[name]=dict(path=str(path.relative_to(MAIN)),sha256=expected)
 native=read(ROOT/'artifacts/rev-kernel-des/20261106-native4/evidence.json');arch=read(ROOT/'artifacts/rev-kernel-des/20261106-arch2/evidence.json')
 for f,h in native['audited_shared_inputs'].items():assert sha(MAIN/f)==h,f
 assert sha(a.guest)=='99cb37b8eba4980fecafa596caffbabbd14663d61d0e8ae9327120187892aff4'
 guest=read(a.guest);assert guest['commit']=='8c3797d62efe6a800b9daa48fa01d8008b25b691' and guest['outcome']=='pass' and guest['genuine_selected_caller_executed'] and not guest['full_provider_startup_executed'] and not guest['full_kernel_qualified'] and not guest['native_device_qualified']
 prepared=MAIN/guest['prepared_parent']['path'];assert sha(prepared)==guest['prepared_parent']['sha256']==arch['prepared']['sha256'];prep=read(prepared)
 for cap in [guest,prep]:
  for f,h in cap['sha256'].items():assert sha(MAIN/f)==h,f
 assert set(guest['requested_cases'])=={'positive','wrong-cookie','corrupt-answer','original-caller','panic','spin'} and len(guest['guest_cases'])==len(guest['commands'])==6 and all(x['accepted'] for x in guest['guest_cases'])
 for path,h in guest['qualified_inputs']['reports'].items():assert sha(MAIN/path)==h
 for name in ['qemu','shim']:assert sha(guest['qualified_inputs'][name])==guest['qualified_inputs']['pins'][name+'_sha256']
 normal_path=MAIN/prep['images']['patched']['path'];normal=Object(normal_path);raw=normal_path.read_bytes();control=normal.named['_kdes_control'];section=normal.sections[control['section']-1];offset=section['offset']+control['value']-section['addr'];assert normal.read('_kdes_control','<I')==(0x4b444553,)
 for label,value in [('corrupt-answer',1),('panic',2),('spin',3)]:
  expected=bytearray(raw);struct.pack_into('<I',expected,offset,value);assert bytes(expected)==(MAIN/prep['images'][label]['path']).read_bytes()
 added_offsets=[x for x in read(IMPL/'artifacts/kernel-des/native-esp-clear1/evidence.json')['table_observation'] if x['field'].startswith(('ccdes_','cctdes_'))]
 assert len(added_offsets)==10
 for image_row in prep['images'].values():
  obj=Object(MAIN/image_row['path'])
  for field in added_offsets:assert obj.read('_test_table','<Q',field['offset'])==(obj.named[field['target']]['value'],)
 records=[]
 for case,command in zip(guest['guest_cases'],guest['commands']):
  name=case['case'];assert command['after']['owned_processes']==[] and command['peak_total_owned_rss_bytes']<=512*1024**2
  assert command['argv'][command['argv'].index('-m')+1]=='256' and '-accel' in command['argv'] and 'tcg' in command['argv']
  payload=Path(command['argv'][command['argv'].index('-initrd')+1]);assert sha(payload)==case['payload_sha256'];blobs=parts(payload.read_bytes());image=MAIN/case['image'];assert sha(image)==case['image_sha256'] and blobs['kernel']==image.read_bytes()
  expected_cookie=b'cpus=1 xts_cookie='+ (b'wrong' if name=='wrong-cookie' else b'owned-adapter-v1');assert blobs['cmdline'].rstrip(b'\0')==expected_cookie
  console=a.guest.parent/(name+'.log');assert sha(console)==case['console_sha256'];text=console.read_text();obj=Object(image)
  if name!='wrong-cookie':
   m=re.search(r'KDES MAPPED pc=(0x[0-9a-f]+) mode=(0x[0-9a-f]+) init=(0x[0-9a-f]+)',text);assert m
   mode=obj.named['_s24_kernel_des_cbc_encrypt']['value'];callback=obj.read('_s24_kernel_des_cbc_encrypt','<Q',16)[0];assert tuple(int(m[i],16) for i in [1,2,3])==(obj.named['_mapped_entry']['value'],mode,callback)
   assert all(v>=0xfffffff007000000 for v in [mode,callback,obj.named['_mapped_entry']['value']])
  if name=='positive':
   m=re.search(r'KDES CALLER PASS vectors=(0x[0-9a-f]+) esp_cases=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=0x0',text);assert m and tuple(int(m[i],16) for i in [1,2,3])==(1964,120,47520);assert 'KDES ESP ASSERT' not in text
  elif name=='wrong-cookie':assert 'REJECT command-cookie' in text and 'KDES MAPPED' not in text and 'KDES CALLER PASS' not in text
  elif name=='corrupt-answer':
   m=re.search(r'KDES CALLER FAIL vectors=(0x[0-9a-f]+) esp_cases=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=(0x[0-9a-f]+)',text);assert m and tuple(int(m[i],16) for i in [1,2,3])==(1,0,16);assert int(m[4],16)==guest['negative_expected_locations']['corrupt_answer_source_line']
  elif name=='original-caller':assert 'KDES ESP BASELINE SUCCESS cases=0xc' in text and 'KDES ESP ASSERT line='+hex(arch['negative_original_marker_line'])+' case=0xd' in text and 'KDES CALLER PASS' not in text
  elif name=='panic':assert 'KDES SYNTHETIC PANIC' in text and 'KDES ESP ASSERT' not in text and 'KDES CALLER PASS' not in text
  else:assert command['outcome']=='timeout' and 'KDES SPIN CONTROL' in text and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' not in text
  if name!='spin':assert command['outcome']=='pass' and command['exit_code']==0 and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in text
  records.append(dict(case=name,console_sha256=sha(console),payload_sha256=sha(payload),outcome=command['outcome'],exit_code=command['exit_code'],seconds=command['elapsed_seconds'],peak_total_owned_rss_bytes=command['peak_total_owned_rss_bytes'],owned_children_after=command['after']['owned_processes']))
 old_attempts=[]
 for label in ['caller-guest1','caller-guest2','caller-guest3']:
  path=IMPL/'artifacts/kernel-des'/label/'evidence.json';e=read(path);assert e['outcome']=='fail' and not any(x['accepted'] for x in e['guest_cases'])
  for c in e['commands']:assert c['after']['owned_processes']==[]
  old_attempts.append(dict(path=str(path.relative_to(MAIN)),sha256=sha(path),outcome=e['outcome'],error=e.get('error'),accepted_cases=0))
 reviewer_history=[]
 for path in sorted((ROOT/'artifacts/rev-kernel-des').glob('*/evidence.json')):
  if path.parent!=OUT:reviewer_history.append(dict(path=str(path.relative_to(MAIN)),sha256=sha(path),outcome=read(path)['outcome'],error=read(path).get('error')))
 report.update(outcome='pass',summary='Bounded independent native DES/ESP review: source ownership and unobserved production clearing findings resolved; full corrected six-case actual caller evidence agrees, no reviewer compiler/guest or full native claim',final_integration_review_complete=True,independent_static_parents=parents,actual_guest=dict(path=str(a.guest.relative_to(MAIN)),sha256=sha(a.guest),commit=guest['commit'],plan=guest['planning_record'],lease_grant=guest['lease_grant'],prepared_parent=guest['prepared_parent'],cases=records,expected_checks=47520,selected_vectors=1964,ESP_cases=120),retained_failed_guest_attempts=old_attempts,reviewer_history=reviewer_history,findings=dict(initial_scratch_NULL_packet_leak='resolved in selected production source and actual failure/ownership fixture cases',initial_allocation_error_local_clear_bypass='resolved by common genuine clearing',production_bzero_IV_elision='resolved by retained unobserved cc_clear calls/strong existing provider chain',remaining_actionable_P0_P1_P2=[]),limitations=dict(full_provider_startup=False,full_ESP_or_network=False,genuine_allocator_system=False,kernel_MMU_qualification=False,full_kernel_link=False,native_device=False,general_private_Apple_ABI=False,FIPS=False,side_channel_qualification=False),checks=[dict(name=n,pass_check=True) for n in ['actual-plans-and-independent-static-parents','all-production-source-native-object-clearing-and-architecture-assertion-bindings','actual-six-leased-guests-and-raw-payload-console-counter-controls','preserved-three-failed-guest-attempts-and-reviewer-corrections','real-owned-cleanup-and-resource-observations','bounded-finding-resolution-with-native-private-gates-explicit']])
except Exception as error:report.update(error=repr(error),traceback=traceback.format_exc())
report['artifacts']=[str(x.relative_to(MAIN)) for x in sorted(OUT.rglob('*')) if x.is_file() and x.name!='evidence.json'];report['sha256']={str(x.relative_to(MAIN)):sha(x) for x in sorted(OUT.rglob('*')) if x.is_file() and x.name!='evidence.json'};(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','final_integration_review_complete']}));raise SystemExit(report['outcome']!='pass')
