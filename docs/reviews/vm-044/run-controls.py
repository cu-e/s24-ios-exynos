#!/usr/bin/env python3
"""Run the single preregistered comparison and focused controls without retries."""
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
OLD=MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
NEW=MAIN/'worktrees/vm-044-ep-20261106/tools/build/avf_kernel_objects.py'
spec=importlib.util.spec_from_file_location('runner_subject',NEW);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
supervise=e.supervisor(MAIN)
started=time.monotonic();report={'kind':'host-test','outcome':'fail','argv':[sys.executable,*sys.argv],'commands':[],'before_samples':[],'after_samples':[],'compiler_started':False,'guest_started':False}
runtime=HERE/'runtime';runtime.mkdir(exist_ok=True)


def host():
    sample=supervise.sample();sample['monotonic']=time.monotonic()
    sample['host_vmstat']={row.split()[0]:int(row.split()[1]) for row in Path('/proc/vmstat').read_text().splitlines() if row.startswith(('pswpin ','pswpout '))}
    return sample


def pressure(sample):return sample['MemAvailable_bytes']<4*e.GIB or supervise.pressured(sample)


def invoke(label,argv,timeout):
    log=runtime/(label+'.log');begin=time.monotonic()
    with log.open('x') as output:
        command=subprocess.run(argv,cwd=HERE.parents[2],stdout=output,stderr=subprocess.STDOUT,timeout=min(timeout,180-(time.monotonic()-started)))
    report['commands'].append({'label':label,'argv':[str(value) for value in argv],'exit_code':command.returncode,'elapsed_seconds':time.monotonic()-begin,'log':str(log)})
    sample=host();report['after_samples'].append({'label':label,**sample})
    if pressure(sample):raise RuntimeError('resource-deferred: host pressure after '+label)
    return command.returncode


def six_summary(directory):
    result=json.loads((directory/'result.json').read_text());transactions=[]
    for actor in result.get('actors',[]):transactions.extend(actor['transactions'][2:2+result['rounds']])
    summary={'actual_outcome':result['outcome'],'elapsed_seconds':result['elapsed_seconds'],'owned_after':result['owned_after'],'stable_lock_inode':result.get('stable_lock_inode'),'monitor_transactions':len(transactions),'failed_monitor_transactions':[row for row in transactions if row['outcome']!='pass']}
    for key in ['wait_seconds','held_upper_seconds']:
        values=[row[key] for row in transactions if key in row]
        summary[key]={'median':statistics.median(values),'max':max(values)} if values else None
    for key in ['proc_scan_seconds','check_live_seconds','fsync_seconds']:
        values=[sum(row[key]) for row in transactions if key in row]
        summary[key]={'median':statistics.median(values),'max':max(values)} if values else None
    return summary


try:
    if e.sha(NEW)!='fe093f7c62affab911f96b3243eef28c419ddcb8180fbd74d58fc9a7420c70df' or e.sha(OLD)!='af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0':raise ValueError('Frozen source changed')
    for number in range(3):
        if number:time.sleep(1)
        report['before_samples'].append(host())
    if any(pressure(sample) for sample in report['before_samples']):raise RuntimeError('resource-deferred: host preflight')
    for label,tool in [('six-original',OLD),('six-corrected',NEW)]:
        directory=runtime/label
        code=invoke(label,[sys.executable,'-s',HERE/'six-control.py','--tool',tool,'--out',directory],70)
        if code==2:raise RuntimeError('resource-deferred: '+label)
        summary=six_summary(directory);report[label]=summary
        if summary['owned_after']:raise RuntimeError('Owned actor survived '+label)
        if label=='six-original':
            if code not in [0,1]:raise RuntimeError('Unexpected original control exit')
            if code==1 and (not summary['failed_monitor_transactions'] or any('lock acquisition timed out' not in row.get('error','') for row in summary['failed_monitor_transactions'])):raise RuntimeError('Original control failed outside the measured finite lock boundary')
        elif code!=0:raise RuntimeError('Corrected six-controller control failed')
    if invoke('rename',[sys.executable,'-s',HERE/'rename-control.py'],15)!=0:raise RuntimeError('Rename semantics control failed')
    if invoke('guards',[sys.executable,'-s',HERE/'guard-control.py'],25)!=0:raise RuntimeError('Final-boundary guard control failed')
    report['outcome']='pass'
except Exception as error:
    report['error']=repr(error)
    if 'resource-deferred' in str(error):report['outcome']='resource-deferred'
finally:
    report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
    (HERE/'controls.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['before_samples','after_samples']}))
raise SystemExit(0 if report['outcome']=='pass' else 2 if report['outcome']=='resource-deferred' else 1)
