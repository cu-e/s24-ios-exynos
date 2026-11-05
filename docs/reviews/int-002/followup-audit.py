"""Verify the exact RSS-only production delta and preserved failing artifacts."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
PROD=MAIN/'worktrees/int-kernel-20261106'
BASE='4bea9b59d1d24c2f7f53f4028769b6e420be556e'
TIP='6b4464c639efa4f1de359abe870b6be3ee0c0458'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
commands=[]
def git(*args):
 p=subprocess.run(['git',*args],cwd=MAIN,env=ENV,capture_output=True,check=True)
 commands.append({'argv':['git',*args],'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr).hexdigest()})
 return p.stdout
cap=PROD/'artifacts/integration-gate/as-fix-1/evidence.json'
assert sha(cap)=='e321872ed64826a92dbec9ea1d6df11cfab1a863c4e2042677371e5a1bcb57de'
e=json.loads(cap.read_text())
for name,h in e['sha256'].items():assert sha(MAIN/name)==h,name
old=git('show',BASE+':tools/integration_gate.py').decode();new=git('show',TIP+':tools/integration_gate.py').decode()
expected=old.replace('import resource\n','').replace('    def limits():\n        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))\n','').replace('"address_space_limit_bytes": 2 * 1024**3,','"address_space_limit_bytes": None,').replace('pass_fds=(fd,), preexec_fn=limits)','pass_fds=(fd,))')
assert expected==new,'Additional unreviewed production change'
assert sha(PROD/'tools/integration_gate.py')==hashlib.sha256(new.encode()).hexdigest()
changed=git('diff','--name-only',BASE,TIP).decode().splitlines()
assert set(changed)=={'tools/integration_gate.py','docs/integration/kernel/README.md','docs/integration/kernel/handoff.md'}
for name in changed:
 assert hashlib.sha256(git('show',TIP+':'+name)).hexdigest()==sha(PROD/name)
failed=json.loads((PROD/'artifacts/integration-gate/gate-publication-1/evidence.json').read_text())
assert failed['outcome']=='fail' and failed['published_head']==BASE and failed['actual_primary_head_after']==BASE
assert failed['common_check']['exit_code']==2 and failed['common_check']['peak_owned_tree_rss_bytes']==180826112
assert not failed['common_check']['after']['owned_processes']
diag=json.loads((MAIN/'artifacts/team-coordination/20261106-team/javac-as-diagnostic.json').read_text())
assert [(c['rlimit_as_bytes'],c['exit_code']) for c in diag['commands']]==[(2147483648,1),(None,0)]
assert all(c['argv']==['javac','-version'] for c in diag['commands'])
result={'outcome':'pass','base':BASE,'commit':TIP,'production_exact_normalization':True,'source_sha256':sha(PROD/'tools/integration_gate.py'),'source_capsule_sha256':sha(cap),'capsule_bindings_verified':len(e['sha256']),'paths':changed,'git_commands':commands,'failed_common_capsule_sha256':sha(PROD/'artifacts/integration-gate/gate-publication-1/evidence.json'),'root_diagnostic_sha256':sha(MAIN/'artifacts/team-coordination/20261106-team/javac-as-diagnostic.json')}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
