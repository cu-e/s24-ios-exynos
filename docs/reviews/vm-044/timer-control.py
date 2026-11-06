#!/usr/bin/env python3
"""Independent actual blocking-flock outer-timer/context controls, no benchmark."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
TOOL=MAIN/'worktrees/vm-044-ep-fix5-20261106/tools/build/avf_kernel_objects.py'
EXPECTED='bfa8a7ddc2d0d9fa42158c24d9d3906a26348666e82b2fcae181e72763911dc3'
CASES=['timeout','earlier-raises','earlier-returns','earlier-reentrant','earlier-reentrant-held','later-acquire','later-timeout','periodic-refusal','default-refusal','blocked-refusal','pending-refusal','threaded-refusal','worker-refusal','invalid-finite']


def load():
    spec=importlib.util.spec_from_file_location('timer_subject',TOOL);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e);return e


def one(name,root):
    e=load();root.mkdir();holder=None;thread=None;event=threading.Event()
    initial_handler=signal.getsignal(signal.SIGALRM);initial_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    report={'case':name,'outcome':'fail','source_sha256':e.sha(TOOL),'events':[],'flock_flags':[]}
    real_signal=signal.signal;real_mask=signal.pthread_sigmask;real_flock=e.fcntl.flock
    class OuterDeadline(Exception):pass
    def outer(signum,frame):
        report['events'].append({'kind':'outer','at':time.monotonic()})
        if name=='earlier-raises':raise OuterDeadline('actual earlier deadline')
        if name.startswith('earlier-reentrant'):
            with (root/('lock' if name.endswith('held') else 'nested-free')).open('a+') as nested:
                try:e.bounded_flock(nested,.03);report['events'].append({'kind':'nested-acquired'})
                except ValueError as error:report['events'].append({'kind':'nested-refused','error':str(error)})
    def tracked_flock(*args):report['flock_flags'].append(args[1]);return real_flock(*args)
    try:
        if e.sha(TOOL)!=EXPECTED:raise ValueError('Frozen final source changed')
        real_signal(signal.SIGALRM,outer)
        lock=root/'lock';ready=root/'ready';duration=.08 if name=='later-acquire' else 2
        holder_code="import fcntl,pathlib,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);pathlib.Path(sys.argv[2]).touch();time.sleep(float(sys.argv[3]))"
        if name!='invalid-finite':
            holder=subprocess.Popen([sys.executable,'-c',holder_code,str(lock),str(ready),str(duration)],cwd='/tmp')
            end=time.monotonic()+2
            while not ready.exists() and time.monotonic()<end:time.sleep(.005)
            if not ready.exists():raise RuntimeError('Real holder not ready')
        if name.startswith('earlier-'):signal.setitimer(signal.ITIMER_REAL,.08)
        elif name.startswith('later-'):signal.setitimer(signal.ITIMER_REAL,.4)
        elif name=='periodic-refusal':signal.setitimer(signal.ITIMER_REAL,.4,.2)
        elif name=='default-refusal':real_signal(signal.SIGALRM,signal.SIG_DFL);signal.setitimer(signal.ITIMER_REAL,.4)
        elif name=='blocked-refusal':real_mask(signal.SIG_BLOCK,{signal.SIGALRM})
        if name=='threaded-refusal':
            thread=threading.Thread(target=lambda:event.wait(2));thread.start()
        entry_mask=real_mask(signal.SIG_BLOCK,set());entry_handler=signal.getsignal(signal.SIGALRM)
        started=time.monotonic();error=None;acquired=False
        def pending_at_block(how,mask):
            result=real_mask(how,mask)
            if how==signal.SIG_BLOCK and set(mask)=={signal.SIGALRM} and not report.get('pending_injected'):
                report['pending_injected']=True;os.kill(os.getpid(),signal.SIGALRM)
            return result
        with lock.open('a+') as stream,patch.object(e.fcntl,'flock',tracked_flock):
            try:
                if name=='pending-refusal':
                    with patch.object(e.signal,'pthread_sigmask',pending_at_block):e.bounded_flock(stream,.5)
                elif name=='worker-refusal':
                    errors=[]
                    def worker():
                        try:e.bounded_flock(stream,.5)
                        except Exception as caught:errors.append(repr(caught))
                    thread=threading.Thread(target=worker);thread.start();thread.join(timeout=1)
                    if thread.is_alive() or len(errors)!=1:raise AssertionError('Worker must refuse finitely')
                    error=errors[0]
                elif name=='invalid-finite':
                    errors=[]
                    for value in [0,-1,.5001,True,float('nan'),float('inf')]:
                        try:e.bounded_flock(stream,value)
                        except ValueError as caught:errors.append(str(caught))
                    if len(errors)!=6:raise AssertionError('Invalid finite boundary accepted')
                    error=str(errors)
                else:
                    e.bounded_flock(stream,.12 if name=='later-timeout' else .5);acquired=True
            except BaseException as caught:error=repr(caught)
        elapsed=time.monotonic()-started;remaining=signal.getitimer(signal.ITIMER_REAL)
        current_mask=real_mask(signal.SIG_BLOCK,set());handler_ok=signal.getsignal(signal.SIGALRM)==entry_handler
        report.update(elapsed_seconds=elapsed,error=error,acquired=acquired,remaining_timer=remaining,mask=[int(x) for x in current_mask],expected_mask=[int(x) for x in entry_mask],handler_restored=handler_ok)
        good=current_mask==entry_mask and handler_ok
        if name=='timeout':good &= not acquired and error is not None and 'timed out' in error and .4<elapsed<1
        elif name=='earlier-raises':good &= 'OuterDeadline' in (error or '') and len(report['events'])==1 and elapsed<.4 and remaining[0]==0
        elif name.startswith('earlier-'):
            good &= 'Earlier outer alarm returned' in (error or '') and elapsed<.4 and remaining[0]==0
            if name=='earlier-reentrant':good &= any(x['kind']=='nested-acquired' for x in report['events'])
            if name=='earlier-reentrant-held':good &= any(x['kind']=='nested-refused' for x in report['events'])
        elif name.startswith('later-'):
            good &= .05<remaining[0]<.4 and (acquired if name=='later-acquire' else 'timed out' in (error or ''))
            time.sleep(max(0,.43-(time.monotonic()-started)))
            good &= len(report['events'])==1 and .3<report['events'][0]['at']-started<.7
        elif name=='periodic-refusal':good &= 'one-shot' in (error or '') and remaining[1]==.2 and .25<remaining[0]<=.4 and not report['flock_flags']
        elif name=='default-refusal':good &= 'one-shot' in (error or '') and .25<remaining[0]<=.4 and not report['flock_flags']
        elif name=='blocked-refusal':good &= 'blocked/pending' in (error or '') and not report['flock_flags']
        elif name=='pending-refusal':good &= 'blocked/pending' in (error or '') and len(report['events'])==1 and not report['flock_flags']
        elif name in ['threaded-refusal','worker-refusal']:good &= 'single main-thread' in (error or '') and not report['flock_flags']
        elif name=='invalid-finite':good &= not report['flock_flags']
        good &= all(flags==e.fcntl.LOCK_EX for flags in report['flock_flags'])
        report['outcome']='pass' if good else 'fail'
    except BaseException as error:report['exception']=repr(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);real_signal(signal.SIGALRM,initial_handler);real_mask(signal.SIG_SETMASK,initial_mask)
        event.set()
        if thread is not None:thread.join(timeout=2)
        if holder is not None:
            if holder.poll() is None:holder.terminate()
            holder.wait(timeout=2)
        report['children_after']=[] if holder is None or holder.poll() is not None else [holder.pid]
        report['threads_after']=threading.active_count();report['controller_memory']=e.actual_controller_memory()
        (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['outcome']=='pass' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=CASES);parser.add_argument('--out',type=Path);args=parser.parse_args()
    if args.case:return one(args.case,args.out)
    e=load();supervise=e.supervisor(MAIN);report={'kind':'host-test','outcome':'fail','argv':[sys.executable,*sys.argv],'admission':[],'cases':[],'no_contention_benchmark':True}
    root=HERE/'runtime'/'timer-cases';root.mkdir()
    for n in range(3):
        if n:time.sleep(1)
        report['admission'].append(supervise.sample())
    try:
        if any(row['MemAvailable_bytes']<4*e.GIB or supervise.pressured(row) for row in report['admission']):raise RuntimeError('resource-deferred: preflight')
        for name in CASES:
            proc=subprocess.Popen([sys.executable,'-s',str(Path(__file__).resolve()),'--case',name,'--out',str(root/name)],start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:stdout,stderr=proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);stdout,stderr=proc.communicate(timeout=2)
            record={'case':name,'exit_code':proc.returncode,'stdout':stdout,'stderr':stderr}
            if (root/name/'result.json').exists():record['result']=json.loads((root/name/'result.json').read_text())
            report['cases'].append(record)
            if proc.returncode:raise AssertionError('Actual timer case failed: '+name)
        report['after_host_sample']=supervise.sample()
        if report['after_host_sample']['MemAvailable_bytes']<4*e.GIB or supervise.pressured(report['after_host_sample']):raise RuntimeError('resource-deferred: postflight')
        report['outcome']='pass'
    except Exception as error:
        report['error']=repr(error)
        if 'resource-deferred' in str(error):report['outcome']='resource-deferred'
    report['controller_memory']=e.actual_controller_memory();(HERE/'timer-control.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['cases','admission']}|{'case_count':len(report['cases'])}));return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
