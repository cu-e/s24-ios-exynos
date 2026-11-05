"""Read-only lineage check for preserved historical and continuation reports."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
PROD=MAIN/'worktrees/vm-025-admission-20261106'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0')
commands=[]
def git(*args):
 p=subprocess.run(['git',*args],cwd=MAIN,env=ENV,capture_output=True,timeout=15,check=True)
 commands.append({'argv':['git',*args],'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr).hexdigest()})
 return p.stdout
p=PROD/'docs/procedures/avf-guest-pid1/admission-002-evidence.json';d=json.loads(p.read_text())
prior='3fdc1f0ae467792135c32eea57a486cbbb58612c';current='1610ed23e716a8f5c229d6d77677142f96cb7995';tip='cdcaebaf759d4f4a62a20959fda5bd024ceb203f'
assert git('rev-parse',tip+'^').decode().strip()==current
assert git('rev-parse',current+'^').decode().strip()==prior
prior_sha=hashlib.sha256(git('show',prior+':tools/build/avf_guest_pid1.py')).hexdigest()
current_sha=hashlib.sha256(git('show',current+':tools/build/avf_guest_pid1.py')).hexdigest()
reports=[]
for c in d['preserved_prior_commands']:
 args=c['argv'];path=Path(args[args.index('--out')+1])/'report.json';r=json.loads(path.read_text())
 assert r['implementation_sha256']==prior_sha
 assert c['exit_code']==c['expected_exit']==r['exit_code']
 assert not r['compiler_executed'] and not r['guest_executed']
 reports.append({'path':str(path.relative_to(MAIN)),'exit':r['exit_code'],'outcome':r['outcome'],'implementation_sha256':r['implementation_sha256']})
assert len(reports)==11 and sum(x['exit']!=0 for x in reports)==10
positive=MAIN/'worktrees/vm-025-20261106/artifacts/avf-guest-pid1/admission-3fdc1f0-2/reviewed-positive/report.json';old=json.loads(positive.read_text())
assert len(old['controls'])==17 and all(x['outcome']=='rejected' for x in old['controls'])
fresh=MAIN/'worktrees/vm-025-admission-20261106/artifacts/avf-guest-pid1/admission-continuation-1610ed2/positive/report.json';r=json.loads(fresh.read_text())
assert r['implementation_sha256']==current_sha and r['exit_code']==0 and r['abi_admission']=='compiled-only' and len(r['inputs'])==41
assert all(r[k] is False for k in ['guest_executed','compiler_executed','pid1_observed','native_device_qualified','runtime_syscalls_qualified','stack_signing_console_qualified'])
failed=MAIN/'worktrees/vm-025-20261106/artifacts/avf-guest-pid1/admission-3fdc1f0/driver-setup-failure.json'
result={'outcome':'pass','commands':commands,'prior_implementation_sha256':prior_sha,'continuation_implementation_sha256':current_sha,'preserved_prior_cli_reports':reports,'preserved_prior_image_mutation_rejections':17,'fresh_continuation':{'path':str(fresh.relative_to(MAIN)),'outcome':r['outcome'],'exit_code':r['exit_code'],'abi_admission':r['abi_admission'],'inputs':len(r['inputs'])},'preserved_driver_setup_failure':json.loads(failed.read_text())}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'outcome':'pass','prior_reports':11,'preserved_negative_exits':10,'image_mutations':17,'fresh_positive_compiled_only':True}))
