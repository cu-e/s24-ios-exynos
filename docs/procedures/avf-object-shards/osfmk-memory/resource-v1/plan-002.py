import hashlib,importlib.util,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
m=Path('/home/egor/dev/pet/s24-ios-exynos');wt=Path(__file__).resolve().parents[5]
p=m/'worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1048576):h.update(b)
 return h.hexdigest()
assert sha(p)=='9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'
s=importlib.util.spec_from_file_location('pinned_ev',p);e=importlib.util.module_from_spec(s);s.loader.exec_module(e)
r=json.loads((wt/'fixtures/public/avf-object-shards/osfmk-memory/resource-v1/request-002.json').read_text())
out=Path(r['supervised_output']);out.mkdir(parents=True,exist_ok=False)
supervisor=e.supervisor(m)
for _ in range(3):assert supervisor.sample()['MemAvailable_bytes']>=4*1024**3
record=e.run_child(r['plan_argv'],wt,out,'source-plan',supervisor,timeout=120,admit=False)
(out/'supervision.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'outcome':record['outcome'],'exit_code':record['exit_code'],'peak_total_owned_rss_bytes':record['peak_total_owned_rss_bytes'],'survivors':record['after']['owned_processes']}))
raise SystemExit(0 if record['outcome']=='pass' else 2)
