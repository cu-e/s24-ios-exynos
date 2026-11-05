#!/usr/bin/env python3
"""Final read-only provenance/control binding; no compiler or algorithm replay."""
import datetime,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent;WT=ROOT/'worktrees/krn-036-20261105'
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
r=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=[],inputs={},commands=[])
def check(name,ok):
 r['checks'].append(dict(name=name,passed=bool(ok)))
 if not ok:raise AssertionError(name)
def bind(p,digest=None):
 p=Path(p);value=sha(p);r['inputs'][str(p)]=value;check('hash-'+str(p),digest is None or value==digest);return p
def git(repo,*args):
 state=load(ROOT/'state/lab.json');plan=next(x for x in state['experiments']if x['id']=='REVCTS3-001');check('prospective-source-audit-plan',plan['status']=='planned'and plan['owner']=='codex-team-review-cts3-20261105-ck')
 argv=['git','-C',str(repo),*args];v=subprocess.run(argv,capture_output=True,timeout=15,env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0'));r['commands'].append(dict(argv=argv,exit_code=v.returncode,stdout_sha256=hashlib.sha256(v.stdout).hexdigest(),stderr_sha256=hashlib.sha256(v.stderr).hexdigest(),environment_overrides={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}));check('git-read',v.returncode==0);return v.stdout
try:
 focused=load(bind(BASE/'runs/session5/evidence.json','2060ca2dced40a3307360426fe0692737569e5813ac546a64d25b87467d473cb'));check('focused-pass',focused['outcome']=='pass'and focused['focused_checks']==7722 and focused['focused_records']==12)
 for name in ['session1','session2','session3','session4','session5']:
  report=load(bind(BASE/'runs'/name/'evidence.json'));snapshot=BASE/'runs'/name/'reviewer.py';source_name='review.py'if name in ['session1','session2']else'focused_run.py';wanted=next(v for k,v in report['reviewer_source_hashes'].items()if Path(k).name==source_name);bind(snapshot,wanted)
  for p,digest in report['artifacts'].items():bind(ROOT/p,digest)
  for p in (BASE/'runs'/name).glob('*.admission.json'):
   admission=load(bind(p));check('unchanged-resource-policy',admission['floor_KiB']==4*1024**2 and admission['consecutive_samples_required']==3 and admission['per_command_wait_limit_seconds']==45 and admission['total_wait_limit_seconds']==180)
   if admission['admitted']:
    samples=[json.loads(line)for line in p.with_name(p.name.replace('.admission.json','.admission.samples.jsonl')).read_text().splitlines()];check('stable-launch-admission',admission['MemAvailable_final_KiB']>=4*1024**2 and len(samples)>=3 and all(x['MemAvailable_KiB']>=4*1024**2 for x in samples[-3:]))
 raw=load(bind(WT/'artifacts/crypto-cts3/cpu-final1/evidence.json','a95b5c69a14519bc2cfc2da8dea025a684bda3a82647b27e66d93d90109afc57'));host_dir=WT/'artifacts/crypto-cts3/host-arm2';host=load(host_dir/'evidence.json')
 check('actual-host-check-marker','CTS3 HOST PASS vectors=381 cbc16=18 checks=28794 failure_line=0'in bind(host_dir/'host-tests.log').read_text())
 for name,marker in [('asan-heap','ERROR: AddressSanitizer: heap-buffer-overflow'),('ubsan-overflow','runtime error: signed integer overflow')]:
  record=load(bind(host_dir/(name+'.json')));check('actual-detector-'+name,record['exit_code']!=0 and record['outcome']=='fail'and marker in bind(host_dir/(name+'.log')).read_text())
 for row in host['profile_rejections']:
  name='reject-'+row['macro'];record=load(bind(host_dir/(name+'.json')));check('real-profile-negative-'+row['macro'],record['exit_code']!=0 and record['outcome']=='fail'and '-D'+row['macro']in record['argv']and'Unqualified fixture AES profile'in bind(host_dir/(name+'.log')).read_text())
 typed=load(bind(host_dir/'typed-return-negative.json'));check('actual-selected-type-error',typed['exit_code']!=0 and'error: incompatible function pointer types'in bind(host_dir/'typed-return-negative.log').read_text()and'ccpad_cts3_crypt_fn_t'in(host_dir/'typed-return-negative.log').read_text())
 for name,digest in raw['selected_header_checks'].items():check('genuine-selected-header-'+name,hashlib.sha256(git(ROOT/'references/apple-xnu','show','c54f35ca767986246321eb901baf8f5ff7923f6a:'+name)).hexdigest()==digest)
 changed=git(ROOT,'diff','--name-only','89ff8f2a6f616c5a3662f8e91cb54396318eb405','80ee7fde7b7a67310a8eecdb1a015aa6aa8081ad','--','src/platform/crypto/cts3').decode().splitlines();check('qualification-only-source-continuation',changed==['src/platform/crypto/cts3/check.py','src/platform/crypto/cts3/production.json'])
 changed=git(ROOT,'diff','--name-only','80ee7fde7b7a67310a8eecdb1a015aa6aa8081ad','b9fa5ca8ecae38d42474bd02dfa5324aac937238').decode().splitlines();check('metadata-only-final-commit',changed==['docs/procedures/crypto-cts3/README.md','docs/procedures/crypto-cts3/handoff.md','docs/procedures/crypto-cts3/qualified-evidence.json'])
 parser=ROOT/'tools/build/xnu_kernel_syscalls.py';check('shared-parser-unchanged',parser.read_bytes()==git(ROOT,'show','aac27cfbc0d71b34eda33ddf366c72427507ae0b:tools/build/xnu_kernel_syscalls.py'))
 qualifier=bind(WT/'docs/procedures/crypto-cts3/qualified-evidence.json');check('final-committed-capsule',qualifier.read_bytes()==git(ROOT,'show','b9fa5ca8ecae38d42474bd02dfa5324aac937238:docs/procedures/crypto-cts3/qualified-evidence.json'))
 compact=load(qualifier);check('external-gates-preserved',not compact['native_kernel_provider_qualified']and not compact['provider_registered']and not compact['private_Apple_ABI_qualified']and not compact['FIPS_qualified']and not compact['side_channel_qualified']and not compact['native_device_executed'])
 r['outcome']='pass';r['summary']='Final frozen source, selected declarations, real negative controls, immutable reviewer source snapshots and stable resource admissions verified; no replay'
except Exception as error:r['error']=repr(error)
r['auditor_sha256']=sha(__file__);(BASE/'final-binding.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k)for k in ['outcome','error','summary']},indent=2));raise SystemExit(r['outcome']!='pass')
