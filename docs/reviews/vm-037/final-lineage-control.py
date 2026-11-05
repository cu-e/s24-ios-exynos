#!/usr/bin/env python3
"""Only the final zombie predicate changes; a live observer still admits."""
import hashlib,importlib.util,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
here=Path(__file__).resolve().parent;main=Path('/home/egor/dev/pet/s24-ios-exynos');source=main/'worktrees/vm-037-ea-fix2-20261106/tools/build/avf_kernel_objects.py'
s=importlib.util.spec_from_file_location('final_fixtures',here/'focused-controls.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
s=importlib.util.spec_from_file_location('final_policy',source);e=importlib.util.module_from_spec(s);s.loader.exec_module(e);f.e=e;f.TOOL=source
start=time.monotonic();r={'kind':'source-review','origin':'local-host','outcome':'fail','bindings':{},'compiler_guest_common_started':False}
def bound(path,wanted):
 with Path(path).open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
 r['bindings'][str(path)]=actual
 if actual!=wanted:raise ValueError('Changed frozen binding '+str(path))
try:
 bound(source,'efe908ff5b6321ea1e456306a3094f9188cc501d066bcc78b435b500d56783e6')
 old=here/'fix1-helper-22afd3d.py';bound(old,'6caa0872750874937c1343b26a168c0d016fa4c98677f54303546e7d194f915a')
 before="if entry['identity']['pid'] not in table:"
 after="if entry['identity']['pid'] not in table or table[entry['identity']['pid']]['state'] == 'Z':"
 if old.read_text().count(before)!=1 or old.read_text().replace(before,after,1)!=source.read_text():raise ValueError('More than the exact final predicate changed')
 r['single_predicate_only']=True
 p=f.Project()
 try:
  sample=p.b.sample();r['live_observer_positive']={'pass':sum(row['pid']==p.b.identity['pid'] for row in sample['project_processes'])==1 and sample['project_rss_bytes']>0,'sample':sample}
  if not r['live_observer_positive']['pass']:raise ValueError('Live observer no longer admits')
 finally:p.close()
 for wt,name,expected in [('vm-037-ea-20261106','evidence.json','f353e0222ba9d9271c4c70b7d43e5ba4e8b26f2f4303a9cf238903aac5b5fde6'),('vm-037-ea-fix1-20261106','correction-evidence.json','fc60539f7f362cf24ff8de28ec06e144b86f9f137fc4c3f99818933a633fd2a5'),('vm-037-ea-fix2-20261106','zombie-evidence.json','6d3a66122d0db7afeefc6501e5899b534232feb09792dc1d312ebb0f30fc7f70')]:
  path=main/'worktrees'/wt/'docs/procedures/avf-project-budgets'/name;bound(path,expected);capsule=json.loads(path.read_text())
  for field in ['sha256','preserved_original_hashes','independent_initial_failure_receipts','preserved_fix1_hashes']:
   for name,wanted in capsule.get(field,{}).items():bound(main/name,wanted)
 bound(here/'legacy-helper-5c.py','5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8')
 r['outcome']='pass'
except Exception as error:r['error']=repr(error)
finally:
 r.update(elapsed_seconds=time.monotonic()-start,controller_memory=e.actual_controller_memory());(here/'final-lineage-control.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ('bindings','live_observer_positive')}|{'binding_count':len(r['bindings'])}))
sys.exit(0 if r['outcome']=='pass' else 1)
