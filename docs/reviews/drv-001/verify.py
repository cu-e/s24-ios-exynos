#!/usr/bin/env python3
"""Independent exact-commit source/evidence audit and bounded host reproduction."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[3]
LAB=ROOT.parents[1]
RUN=os.environ.get('S24_REVSTM_RUN','20261105-session1')
assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN),'Canonical fresh run name required'
OUT=ROOT/'artifacts/rev-stm'/RUN
COMMIT='deb2f861160e6407f95de7f18e41b87603e651e9'
OUT.mkdir(parents=True,exist_ok=False)
(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
commands=[]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(argv,label,cwd=ROOT,env=None):
    with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:
        r=subprocess.run(list(map(str,argv)),cwd=cwd,stdout=a,stderr=b,env=env,timeout=120)
    commands.append(dict(argv=list(map(str,argv)),cwd=str(cwd),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(LAB)),stderr=str((OUT/(label+'.stderr')).relative_to(LAB))))
    (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    assert r.returncode==0,(label,r.returncode)
    return (OUT/(label+'.stdout')).read_bytes()
files=['src/platform/input/stm/'+x for x in ['protocol.c','protocol.h','fixture.c','check.py','README.md']]+['src/platform/display/contract.c','src/platform/display/contract.h','tests/test_stm_touch.py','tests/test_e1s_touch_regression.py','patches/display-input/0001-e1s-stm-coordinate-nibbles.patch','fixtures/public/stm-touch/vectors.json','fixtures/public/stm-touch/source-profile.json','docs/procedures/drv-001/README.md','docs/procedures/drv-001/handoff.md']
source={}
for i,f in enumerate(files):
    blob=run(['git','show',COMMIT+':'+f],'extract-'+str(i))
    p=OUT/'candidate'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob);source[f]=sha(p)
profile=json.loads((OUT/'candidate/fixtures/public/stm-touch/source-profile.json').read_text())
for i,s in enumerate(profile['sources']):
    repo=LAB/'references'/s['repository'];p=repo/s['path']
    blob=run(['git','-C',repo,'show',s['commit']+':'+s['path']],'donor-'+str(i))
    assert hashlib.sha256(blob).hexdigest()==s['sha256']==sha(p)
# Build actual pinned Samsung declaration as an independent native layout oracle.
header=(LAB/'references/s24-linux/drivers/input/sec_input/stm_spi/stm_dev.h').read_text()
coord=re.search(r'struct stm_ts_event_coordinate \{.*?\} __packed;',header,re.S).group()
(OUT/'samsung-layout.h').write_text('/* Exact pinned factual declaration; local artifact only. */\n#include <stdint.h>\ntypedef uint8_t u8;\n#define __packed __attribute__((packed))\n'+coord+'\n')
audit=[]
for capsule in ['commit-session1','final-session1']:
    p=LAB/'worktrees/drv-001-20261105/artifacts/stm-host'/capsule/'evidence.json';e=json.loads(p.read_text())
    for name,h in e.get('sha256',{}).items(): assert sha(LAB/name)==h,name
    for name,h in e.get('source_inputs',{}).items(): assert sha(LAB/name)==h,name
    audit.append(dict(path=str(p.relative_to(LAB)),sha256=sha(p),outcome=e['outcome'],checks=len(e['checks']),command_count=len(e['commands'])))
assert json.loads((LAB/'worktrees/drv-001-20261105/artifacts/stm-host/commit-session1/evidence.json').read_text())['commit']==COMMIT
for f,h in source.items():
    measured=LAB/'worktrees/drv-001-20261105/artifacts/stm-host/final-session1/tested-inputs'/f
    if measured.exists(): assert sha(measured)==h,f
compiler=Path('/home/egor/.local/bin/clang').resolve()
run([compiler,'--version'],'compiler')
run(['python3','--version'],'python')
(OUT/'harness.c').write_bytes((ROOT/'docs/reviews/drv-001/harness.c').read_bytes())
run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-I',OUT/'candidate/src/platform/input/stm','-I',OUT,OUT/'harness.c',OUT/'candidate/src/platform/input/stm/protocol.c',OUT/'candidate/src/platform/display/contract.c','-o',OUT/'harness'],'compile')
env=os.environ.copy();env.update(ASAN_OPTIONS='halt_on_error=1:detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1')
run(['/usr/bin/time','-v',OUT/'harness'],'independent-harness',env=env)
# Reproduce the candidate's real tests from extracted exact files, with the pinned donor available.
env=os.environ.copy();env['S24_STM_REFERENCE_ROOT']=str(LAB/'references');env['S24_STM_EVIDENCE_ROOT']=str(OUT/'candidate/artifacts/reproduced-tests')
run(['python3','-m','unittest','discover','-s','tests','-p','test_stm_touch.py','-v'],'candidate-tests',cwd=OUT/'candidate',env=env)
assert 'Ran 14 tests' in (OUT/'candidate-tests.stderr').read_text() and 'skipped' not in (OUT/'candidate-tests.stderr').read_text()
report=dict(kind='source-review',origin='local-host',outcome='pass',recorded_at=datetime.now(timezone.utc).isoformat(),summary='Independent review found no actionable host-boundary defect within stated serialized atomic acceptance contract; pinned Samsung layout oracle and independent lifecycle assertions passed',commit=COMMIT,reviewer_base=run(['git','rev-parse','HEAD'],'reviewer-base').decode().strip(),commands=commands,source_inputs=source,source_pins={s['repository']:s['commit'] for s in profile['sources']},implementation_capsules=audit,compiler=dict(path=str(compiler),sha256=sha(compiler)),device_executed=False,native_device_qualified=False,limitations=['No hardware, SPI/IRQ/power/firmware or Apple HID qualification','Independent declaration oracle runs on current host ABI; it is not a sensor measurement','Atomic synchronous acceptance and caller serialization are preconditions; native backend is absent'],checks=[dict(name=n,pass_check=True) for n in ['exact-source-commit-extracted','pinned-primary-blobs-and-local-files-match','actual-implementation-capsule-artifact-hashes-match','final-runtime-source-bytes-match-exact-commit','independent-Samsung-declaration-and-lifecycle-harness-ASan-UBSan','candidate-14-tests-reproduced-no-skips']])
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json']
report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(outcome=report['outcome'],evidence=str((OUT/'evidence.json').relative_to(LAB)),commands=len(commands))))
