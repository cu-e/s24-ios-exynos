#!/usr/bin/env python3
"""Independent source/binding/control review of the prospective guard only."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
WT=MAIN/'worktrees/vm-008-admission-20261106'
OUT=Path(__file__).resolve().parent/'admission-verification.json'
started=time.monotonic()
r={'kind':'source-review','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':[sys.executable,*sys.argv],'bindings':{},'controls':[],'compiler_generator_guest_started':False}
def bound(path,wanted):
    path=Path(path)
    with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    r['bindings'][str(path)]=actual
    if actual!=wanted:raise ValueError('Binding mismatch: '+str(path))
def check(value,message):
    if not value:raise ValueError(message)
try:
    ep=WT/'docs/procedures/avf-kernel-headers/admission-evidence.json'
    dp=WT/'fixtures/public/avf-kernel-headers/admission-qualified.json'
    bound(ep,'50bfe91c3dc06f9151ba7a6d35d571c42a8c4c9db0e1f6fc115c77a017ac5355')
    bound(dp,'a9d40d614ca28bf6719cbde9b9dadcf6f0c92726330ef694768eae05677ae6a0')
    e=json.loads(ep.read_text());d=json.loads(dp.read_text())
    for path,wanted in e['sha256'].items():bound(MAIN/path,wanted)
    for path,wanted in e['historical_fingerprints_unchanged'].items():bound(MAIN/path,wanted)
    report=json.loads((MAIN/d['probe']['report']).read_text())
    check(report['outcome']=='pass' and len(report['controls'])==4 and all(x['pass'] for x in report['controls']),'Four producer controls pass')
    live=report['actual_readonly_probe']
    samples=live['admission']['samples']
    check(live['pass'] and live['children_before']==live['children_after']=='','Actual readonly probe has no children')
    check(len(samples)==3 and all(s['MemAvailable_bytes']>=4*1024**3 for s in samples),'Actual three floor observations')
    spacing=[b['monotonic_seconds']-a['monotonic_seconds'] for a,b in zip(samples,samples[1:])]
    check(all(delta>=1 for delta in spacing),'Actual one-second sample spacing')
    check(report['controller_usage']['current_image_peak_rss_bytes']<=256*1024**2,'Producer current-image controller budget')
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(WT/'tools/build'))
    spec=importlib.util.spec_from_file_location('review_admission',WT/'tools/build/avf_kernel_headers.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    floor=4*1024**3
    for name,values,expected,expected_reads in [('last-sample-low',[floor,floor,floor-1],False,3),('all-floor',[floor]*3,True,3),('too-close',[floor]*3,False,2)]:
        sequence=iter(values);clock=[0.0];sleeps=[]
        def pause(seconds):sleeps.append(seconds);clock[0]+=seconds/4 if name=='too-close' else seconds
        proof=module.stable_admission(read_available=lambda:next(sequence),pause=pause,monotonic=lambda:clock[0],timestamp=lambda:str(clock[0]))
        check(proof['admitted'] is expected and len(proof['samples'])==expected_reads,'Independent helper control: '+name)
        check(sleeps==[1.0]*(expected_reads-1),'Independent interval requests: '+name)
        r['controls'].append({'name':name,'pass':True,'admission':proof})
    holder=module.Headers.__new__(module.Headers)
    holder.args=SimpleNamespace(qualification=MAIN/'worktrees/vm-008-20261105/fixtures/public/avf-kernel-headers/qualified-component.json')
    holder.main=MAIN
    rejected=False
    with patch.object(module.subprocess,'Popen',side_effect=AssertionError('No child permitted')):
        try:holder.verify()
        except ValueError as error:rejected='Scoped implementation differs' in str(error)
    check(rejected,'Prospective tool strictly rejects old descriptor before broad verification')
    r['controls'].append({'name':'new-tool-old-descriptor-rejected','pass':True,'full_sweep_or_child_started':False})
    check(d['historical_verification']['historical_runs_relabelled'] is False and d['historical_verification']['use_frozen_entrypoint'] is True,'Explicit historical compatibility')
    r.update(outcome='pass',producer_controls=4,independent_controls=4,actual_producer_sample_spacing_seconds=spacing,historical_tool_preserved=True,prospective_guard_only=True)
except Exception as error:r['error']=repr(error)
finally:
    usage={line.split(':',1)[0]:int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:','VmRSS:'))}
    r.update(elapsed_seconds=round(time.monotonic()-started,3),current_image_peak_rss_bytes=usage['VmHWM'],current_rss_bytes=usage['VmRSS'],raw_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    OUT.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('bindings','controls')}))
sys.exit(0 if r['outcome']=='pass' else 1)
