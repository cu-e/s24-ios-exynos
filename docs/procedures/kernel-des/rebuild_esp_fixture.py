#!/usr/bin/env python3
"""Rebuild only changed owned ESP fixture assertions; retain real native/guest objects."""
import argparse,copy,datetime,hashlib,importlib.util,json,os,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',LC_ALL='C',PYTHONUTF8='1')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);a=p.parse_args();m=a.root.resolve()
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh run name')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'builder.py').write_bytes(Path(__file__).read_bytes());runner=module('des_runner',WT/'src/platform/crypto/des/check.py');runner.ENV_OVERRIDES|={'LC_ALL':'C','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};runner.CHILD_ENV=dict(os.environ)|runner.ENV_OVERRIDES;builder=module('image_reader',WT/'docs/procedures/kernel-des/prepare_caller.py');sys.path.insert(0,str(WT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 r={'task':'KRN-039','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'checks':[],'parents':{},'fixture_components':[],'guest_executed':False,'full_provider_startup_executed':False,'full_kernel_qualified':False,'native_device_qualified':False}
 def check(n,ok,**d):
  r['checks'].append(dict(name=n,passed=bool(ok),**d))
  if not ok:raise ValueError(n)
 def run(argv,label):
  v=runner.run(argv,out,label,30,256);r['commands'].append(v);check('command-'+label,v['exit_code']==0 and v['outcome']=='pass');return v
 try:
  state=load(m/'state/lab.json');t=next(x for x in state['tasks'] if x['id']=='KRN-039');e=next(x for x in state['experiments'] if x['id']==a.experiment);check('owned-active-prospective-plan',t['owner']==e['owner']=='codex-team-kernel-des-20261105-ci' and t['status']=='in_progress' and e['task']=='KRN-039' and e['status']=='planned');r['planning_record']=e
  old=load(a.parent);check('passed-image-parent',old['outcome']=='pass' and old['guest_images_ready'])
  for path,digest in old['sha256'].items():check('retained-artifact-'+path,sha(m/path)==digest)
  for path,digest in old['source_inputs'].items():
   if path not in ['fixtures/public/xnu-kernel-des/esp_fixture.c',str(Path(__file__).relative_to(WT))]:check('unchanged-owned-input-'+path,sha(WT/path)==digest)
  for key in ['vectors','accepted_runtime','byte_runtime','linker','retained_components','original_source_read']:r[key]=copy.deepcopy(old[key])
  r['parents']=copy.deepcopy(old['parents']);r['parents']['retained-images']={'path':str(a.parent.relative_to(m)),'sha256':sha(a.parent)}
  for row in r['retained_components']:check('unchanged-real-native-'+row['id'],sha(m/row['output'])==row['output_sha256'])
  r['source_inputs']=dict(old['source_inputs']);r['source_inputs']['fixtures/public/xnu-kernel-des/esp_fixture.c']=sha(WT/'fixtures/public/xnu-kernel-des/esp_fixture.c');r['source_inputs'][str(Path(__file__).relative_to(WT))]=sha(__file__)
  argv=['git','-C',str(m/'references/apple-xnu'),'show','c54f35ca767986246321eb901baf8f5ff7923f6a:bsd/netinet6/ipsec.h'];child=subprocess.run(argv,env=ENV,capture_output=True,timeout=10);digest=hashlib.sha256(child.stdout).hexdigest();check('exact-selected-IPSEC-header',child.returncode==0 and digest==sha(m/'references/apple-xnu/bsd/netinet6/ipsec.h'));r['alignment_header']={'argv':argv,'exit_code':child.returncode,'sha256':digest,'policy':'__ARM__ selects32-bit alignment copy; actual ARM64 branch permits direct unaligned access; no macro/profile override'}
  marker='/* BEGIN OWNED FOCUSED FIXTURE */';text=(WT/'fixtures/public/xnu-kernel-des/esp_fixture.c').read_text();objects={}
  for row in old['fixture_components']:
   label=Path(row['output']).stem
   if label not in ['esp-patched','esp-original']:
    check('unchanged-guest-fortify-'+label,sha(m/row['source'])==row['source_sha256'] and sha(m/row['output'])==row['output_sha256']);r['fixture_components'].append(dict(row,reused_from=r['parents']['retained-images']));continue
   source=(m/row['source']).read_text();check('exact-fixture-boundary-'+label,source.count(marker)==1);source=source.split(marker)[0]+marker+'\n'+text;path=out/(label+'.c');path.write_text(source);dest=out/(label+'.o');args=list(row['argv']);args[args.index(str(m/row['source']))]=str(path);args[args.index('-o')+1]=str(dest);args[args.index('-MF')+1]=str(dest.with_suffix('.d'));check('no-forced-32bit-feature-'+label,not any(x.startswith('-D__ARM__') for x in args));run(args,'compile-'+label)
   obj=ObjectData(dest);check('actual-ARM64-alignment-policy-'+label,obj.value('_kdes_esp_alignment_policy','<4Q')==(1,0,4,1));r.setdefault('alignment_policy_objects',{})[label]={'values':obj.value('_kdes_esp_alignment_policy','<4Q'),'record_layout':obj.value('_kdes_esp_record_layout','<9Q')};r['fixture_components'].append(dict(row,source=str(path.relative_to(m)),source_sha256=sha(path),output=str(dest.relative_to(m)),output_sha256=sha(dest),argv=args));objects[label]=dest
  images={}
  for label in ['patched','original']:
   oldesp=m/next(x['output'] for x in old['fixture_components'] if x['output'].endswith('/esp-'+label+'.o'));oldimage=m/old['images'][label]['path'];link=list(next(x['argv'] for x in old['commands'] if '-static' in x['argv'] and str(oldimage)==str(x['argv'][-1])));link[link.index(str(oldesp))]=str(objects['esp-'+label]);dest=out/(label+'.macho');link[-1]=str(dest);run(link,'link-'+label);images[label]={'path':str(dest.relative_to(m)),'sha256':sha(dest),'mapping_proof':builder.Image(dest).proof()}
  data=bytearray((m/images['patched']['path']).read_bytes());proof=images['patched']['mapping_proof'];check('owned-control-word',struct.unpack_from('<I',data,proof['control_word_offset'])==(0x4b444553,))
  for label,value in [('corrupt-answer',1),('panic',2),('spin',3)]:
   raw=bytearray(data);struct.pack_into('<I',raw,proof['control_word_offset'],value);dest=out/(label+'.macho');dest.write_bytes(raw);images[label]={'path':str(dest.relative_to(m)),'sha256':sha(dest),'mapping_proof':builder.Image(dest).proof(),'control_word':value}
  r['images']=images;r['guest_images_ready']=True;r['outcome']='pass'
 except Exception as error:r['error']=repr(error)
 finally:
  r['resource_admission_wait_seconds']=runner.RESOURCE_WAIT_USED;r['sha256']={str(p.relative_to(m)):sha(p) for p in out.rglob('*') if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k)for k in ['outcome','error','guest_images_ready']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
