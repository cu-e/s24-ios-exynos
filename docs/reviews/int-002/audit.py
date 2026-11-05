"""Stream exact frozen producer capsule and committed-file bindings."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
PRODUCER=MAIN/'worktrees/int-kernel-20261106'
COMMIT='8042e6529e34d470620940e9263ede76e9331b18'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0')
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
p=PRODUCER/'artifacts/integration-gate/light-4/evidence.json'
assert sha(p)=='2807bf0826091372c20b5ff1c8a35d7ee02fb4575f9114c6f3a32fff5f10273c'
evidence=json.loads(p.read_text())
checks=[]; commands=[]
for name,expected in evidence['sha256'].items():
    actual=sha(MAIN/name); assert actual==expected,name
    checks.append({'path':name,'sha256':actual})
for name,expected in evidence['committed_inputs_sha256'].items():
    argv=['git','show',COMMIT+':'+name]
    result=subprocess.run(argv,cwd=MAIN,env=ENV,capture_output=True,check=True)
    actual=hashlib.sha256(result.stdout).hexdigest();assert actual==expected,name
    commands.append({'argv':argv,'exit_code':result.returncode,'stdout_sha256':actual,'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
cases=[]
for case in sorted((PRODUCER/'artifacts/integration-gate/light-4/cases').glob('*.json')):
    data=json.loads(case.read_text())
    assert data['evidence']['tool_sha256']==evidence['committed_inputs_sha256']['tools/integration_gate.py']
    cases.append({'name':case.name,'exit':data['exit_code'],'outcome':data['evidence']['outcome']})
assert len(cases)==13
out={'outcome':'pass','producer_commit':COMMIT,'producer_capsule_sha256':sha(p),'bindings_verified':len(checks),'bindings':checks,'committed_file_commands':commands,'final_case_reports':cases}
Path(sys.argv[1]).write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'outcome':'pass','bindings':len(checks),'committed_files':len(commands),'final_reports':len(cases)}))
