#!/usr/bin/env python3
"""STR019 exact local source preparation only: no compiler or target execution."""
import datetime, hashlib, json, os, shutil, subprocess
from pathlib import Path
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'artifacts/e1s-boot-log/source-002'
OUT.mkdir(parents=True, exist_ok=False)
commands=[]
def digest(data): return hashlib.sha256(data).hexdigest()
def run(argv,cwd):
    p=subprocess.run(argv,cwd=cwd,env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'},capture_output=True,timeout=15)
    commands.append({'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':p.returncode,'stdout_sha256':digest(p.stdout),'stderr':p.stderr.decode(errors='replace')})
    (OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    if p.returncode: raise RuntimeError('source command failed; retained commands.json')
    return p.stdout
pin=json.loads((ROOT/'fixtures/public/e1s-framebuffer/upstream.json').read_text())
extra=['shim/e1s-xnu/start.S','shim/e1s-xnu/loader.ld','tools/e1s/read_log.py','xnu/e1s/patches/0011-e1s-log.patch','xnu/e1s/patches/0012-e1s-boot-marker.patch']
files=list(pin['sources'])+extra
rows={}
for rel in files:
    body=run(['git','-C',str(MAIN/'references/s24-port'),'show',pin['revision']+':'+rel],MAIN)
    blob=run(['git','-C',str(MAIN/'references/s24-port'),'rev-parse',pin['revision']+':'+rel],MAIN).decode().strip()
    compatible=run(['git','--git-dir='+str(MAIN/'worktrees/int-platform-20261106/artifacts/platform-integration/strategy-reassessment1/upstream.git'),'show',pin['compatible_revision']+':'+rel],MAIN)
    if body!=compatible: raise RuntimeError('source revision compatibility changed: '+rel)
    if rel in pin['sources'] and digest(body)!=pin['sources'][rel]['donor_sha256']: raise RuntimeError('donor mismatch: '+rel)
    dst=OUT/'donor'/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(body)
    rows[rel]={'donor_sha256':digest(body),'git_blob_sha1':blob,'compatible_exact_bytes':True}
shutil.copytree(OUT/'donor',OUT/'baseline')
for key in ['memory','display']:
    path=ROOT/pin[key+'_patch'];body=path.read_bytes()
    if digest(body)!=pin[key+'_patch_sha256']: raise RuntimeError(key+' patch identity changed')
    for check in [True,False]: run(['git','apply']+(['--check'] if check else [])+[str(path)],OUT/'baseline')
for rel,row in pin['sources'].items():
    body=(OUT/'baseline'/rel).read_bytes()
    if digest(body)!=row['display_sha256']: raise RuntimeError('composed identity changed: '+rel)
for rel in rows: rows[rel]['baseline_sha256']=digest((OUT/'baseline'/rel).read_bytes())
(OUT/'source-bindings.json').write_text(json.dumps({'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'upstream':pin,'files':rows,'commands':str(OUT/'commands.json'),'source_only':True},indent=2)+'\n')
print(json.dumps({'outcome':'pass','source_only':True,'files':len(rows),'commands':len(commands),'out':str(OUT)},indent=2))
