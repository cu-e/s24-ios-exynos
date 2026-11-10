#!/usr/bin/env python3
"""Single source-only request through the unchanged qualified supervisor."""
import hashlib,importlib.util,json,resource,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[5]
REQUEST=Path(__file__).with_name('request.json')
r=json.loads(REQUEST.read_text())
p=Path(r['runner']['path']);h=hashlib.sha256()
with p.open('rb') as stream:
 for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
if h.hexdigest()!=r['runner']['sha256']:raise ValueError('Frozen executor mismatch')
if r['source_plan_argv'][r['source_plan_argv'].index('--mode')+1]!='plan':raise ValueError('Source-only phase')
out=Path(r['source_plan_output'])
if out.exists() or Path(r['proposed_actual_output']).exists():raise ValueError('Fresh outputs required')
out.mkdir(parents=True)
spec=importlib.util.spec_from_file_location('accepted_resource_executor',p);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
start=time.monotonic()
report={'kind':'source-review','origin':'local-host','task':r['task'],'owner':r['owner'],'outcome':'fail','recorded_at':e.stamp(),'runner_sha256':h.hexdigest(),'compiler_started':False,'experiment_remains_planned':True}
try:
 result=e.run_child(r['source_plan_argv'],WT,out,'source-plan',e.supervisor(Path(r['source_plan_argv'][r['source_plan_argv'].index('--main')+1])),timeout=120,admit=True)
 report.update(command=result,outcome=result['outcome'],exit_code=result.get('exit_code'))
finally:
 report['elapsed_seconds']=time.monotonic()-start
 report['current_image_memory']={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:','VmRSS:'))}
 report['historical_ru_maxrss_kib_not_current_memory']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
 report['actual_output_exists']=Path(r['proposed_actual_output']).exists()
 e.write(out/'completion.json',report)
print(json.dumps({'outcome':report['outcome'],'exit_code':report.get('exit_code'),'completion':str(out/'completion.json')}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
