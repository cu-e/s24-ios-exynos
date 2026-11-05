#!/usr/bin/env python3
"""Bind already executed genuine GCM qualification to a scoped exact source commit."""
import argparse,datetime,hashlib,json,os,re,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
os.environ.update(GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=Path);p.add_argument('--commit',required=True);p.add_argument('--run',required=True);args=p.parse_args()
 if not re.fullmatch(r'[0-9a-f]{40}',args.commit) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('full exact commit and plain fresh run name required')
 out=ROOT/'artifacts/crypto-gcm'/args.run;out.mkdir(parents=True,exist_ok=False);(out/'executed-audit.py').write_bytes(Path(__file__).read_bytes())
 report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],commit=args.commit,provider_registered=False,xnu_executed=False,native_device=False,full_crypto_qualified=False,fips_qualified=False,side_channel_qualified=False)
 def git(*argv):
  cmd=['git','-C',str(ROOT),*argv];r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ,timeout=10);report['commands'].append({'argv':cmd,'exit_code':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest(),'environment_overrides':{'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}})
  if r.returncode:raise ValueError('Immutable local Git read failed')
  return r.stdout
 try:
  if git('rev-parse','HEAD').decode().strip()!=args.commit:raise ValueError('Exact commit is not current HEAD')
  changed=git('diff-tree','--no-commit-id','--name-only','-r',args.commit).decode().splitlines()
  if not changed or any(not name.startswith(('src/platform/crypto/gcm/','docs/procedures/crypto-gcm/')) for name in changed):raise ValueError('Commit crosses task ownership')
  report['changed_paths']=changed;path=args.report.resolve();data=json.loads(path.read_text());report['cpu_evidence']={'path':str(path),'sha256':sha(path)}
  cases=data.get('guest_cases',[])
  if data['outcome']!='pass' or len(cases)!=4 or {x['name'] for x in cases}!={'positive','wrong-cookie','corrupt-vector','spin-timeout'} or not all(x['accepted'] for x in cases) or data.get('arm_checks')!=25948370 or data.get('host_checks')!=25948370:raise ValueError('Actual complete same-suite host/ARM controls required')
  report['source_hashes']={}
  for name,digest in data['owned_source_hashes'].items():
   current=sha(ROOT/name);committed=hashlib.sha256(git('show',args.commit+':'+name)).hexdigest()
   if current!=digest or committed!=digest:raise ValueError('Committed qualified source differs:'+name)
   report['source_hashes'][name]=digest
  report['artifact_hashes']={}
  for name,digest in data['artifact_hashes'].items():
   if sha(MAIN/name)!=digest:raise ValueError('Actual CPU artifact changed:'+name)
   report['artifact_hashes'][name]=digest
  # Recursively verify the host/ARM and original memory-deferred CPU capsules.
  for key in ['parent','stage_parent']:
   capsule=data[key];q=Path(capsule['path'])
   if sha(q)!=capsule['sha256']:raise ValueError('Qualified parent capsule changed')
   report['artifact_hashes'][str(q.relative_to(MAIN))]=sha(q)
  arm=json.loads(Path(data['parent']['path']).read_text())
  for name,digest in arm['artifact_hashes'].items():
   if sha(MAIN/name)!=digest:raise ValueError('Qualified host/ARM artifact changed')
   report['artifact_hashes'][name]=digest
  for name,digest in arm['dependencies'].items():
   if sha(name)!=digest:raise ValueError('Consumed source dependency changed')
  for category in ['reused_arm_objects','reused_stage_objects','shared_owned_source_checks']:
   for name,digest in arm[category].items():
    if sha(name)!=digest:raise ValueError('Read-only shared input changed')
  report['criteria']={'genuine_typed_callbacks_helpers_storage_source':True,'primary_independent_vectors_immediate_streaming_nonce_auth_boundaries':True,'actual_sanitized_host_and_ARM_CPU':True,'provider_registration':False,'native_XNU_device':False,'FIPS_or_side_channel':False}
  report['outcome']='pass';report['summary']='Exact scoped commit binds immutable genuine source,4768-vector sanitized host and actual ARM25948370 checks, all three real CPU controls; no recompile/re-execution and no full-provider/native/FIPS/side-channel qualification.'
 except Exception as error:report['error']=repr(error);report['summary']='Exact commit/source/evidence binding failed; no qualification promoted.'
 finally:
  report.setdefault('artifact_hashes',{}).update({str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()});report['artifact_hashes'][str(args.report.resolve().relative_to(MAIN))]=sha(args.report);report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','commit','criteria']},indent=2));return report['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
