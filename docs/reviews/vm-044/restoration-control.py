#!/usr/bin/env python3
"""Actual repeated SIGINT at alarm restoration in an isolated owned process."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode=True
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')


def module(path):
    spec=importlib.util.spec_from_file_location('restoration_subject',path);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e);return e


def child(args):
    e=module(args.tool);root=args.out;root.mkdir();lock=root/'lock';ready=root/'holder-ready'
    report={'kind':'host-test','outcome':'fail','source_sha256':e.sha(args.tool),'pid':os.getpid(),'injection':'actual second SIGINT immediately before restoring captured SIGALRM handler, after actual first SIGINT interrupts contended flock','events':[]}
    original_signal=signal.signal;original_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set());original_handler=signal.getsignal(signal.SIGALRM)
    holder=sender=None;injected=False
    def outer(signum,frame):report['events'].append('original-outer-handler-fired')
    try:
        if e.sha(args.tool)!=args.expected:raise ValueError('Wrong frozen subject')
        holder_code="import fcntl,pathlib,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);pathlib.Path(sys.argv[2]).touch();time.sleep(3)"
        holder=subprocess.Popen([sys.executable,'-c',holder_code,str(lock),str(ready)],cwd='/tmp')
        end=time.monotonic()+2
        while not ready.exists() and time.monotonic()<end:time.sleep(.005)
        if not ready.exists():raise RuntimeError('Owned holder did not acquire')
        original_signal(signal.SIGALRM,outer);signal.setitimer(signal.ITIMER_REAL,.9)
        def at_restore(signum,handler):
            nonlocal injected
            if signum==signal.SIGALRM and handler is outer and not injected:
                injected=True;report['events'].append('second-real-SIGINT-at-restoration');os.kill(os.getpid(),signal.SIGINT)
            return original_signal(signum,handler)
        sender_code="import os,signal,sys,time;time.sleep(.05);os.kill(int(sys.argv[1]),signal.SIGINT)"
        sender=subprocess.Popen([sys.executable,'-c',sender_code,str(os.getpid())],cwd='/tmp')
        started=time.monotonic()
        with lock.open('a+') as stream:
            try:
                with patch.object(e.signal,'signal',at_restore):e.bounded_flock(stream,.5)
            except BaseException as error:report['caught']=repr(error)
        report['elapsed_seconds']=time.monotonic()-started
        report['observed_mask']=[int(value) for value in signal.pthread_sigmask(signal.SIG_BLOCK,set())]
        report['expected_mask']=[int(value) for value in original_mask]
        report['original_handler_restored']=signal.getsignal(signal.SIGALRM) is outer
        report['observed_handler_name']=getattr(signal.getsignal(signal.SIGALRM),'__name__',str(signal.getsignal(signal.SIGALRM)))
        report['remaining_timer']=signal.getitimer(signal.ITIMER_REAL)
        report['injected_second_signal']=injected
        restored=set(report['observed_mask'])==set(report['expected_mask']) and report['original_handler_restored'] and .5<report['remaining_timer'][0]<.9
        report['outcome']='pass' if injected and restored else 'fail'
    except BaseException as error:report['error']=repr(error)
    finally:
        # Repair only this fixture process after recording the actual state.
        signal.setitimer(signal.ITIMER_REAL,0);original_signal(signal.SIGALRM,original_handler);signal.pthread_sigmask(signal.SIG_SETMASK,original_mask)
        for process in [holder,sender]:
            if process is not None:
                if process.poll() is None:process.terminate()
                process.wait(timeout=2)
        report['children_after']=[process.pid for process in [holder,sender] if process is not None and process.poll() is None]
        report['controller_memory']=e.actual_controller_memory()
        (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['outcome']=='pass' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tool',type=Path,required=True);parser.add_argument('--expected',required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--child',action='store_true');args=parser.parse_args()
    if args.child:return child(args)
    e=module(args.tool);supervise=e.supervisor(MAIN);report={'kind':'host-test','outcome':'fail','argv':[sys.executable,*sys.argv],'admission':[]}
    for number in range(3):
        if number:time.sleep(1)
        sample=supervise.sample();sample['monotonic']=time.monotonic();report['admission'].append(sample)
    if any(row['MemAvailable_bytes']<4*e.GIB or supervise.pressured(row) for row in report['admission']):
        report['outcome']='resource-deferred';args.out.with_suffix('.admission.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 2
    argv=[sys.executable,'-s',str(Path(__file__).resolve()),'--tool',str(args.tool),'--expected',args.expected,'--out',str(args.out),'--child']
    process=subprocess.Popen(argv,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        stdout,stderr=process.communicate(timeout=5);report.update(exit_code=process.returncode,stdout=stdout,stderr=stderr)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);stdout,stderr=process.communicate(timeout=2);report.update(exit_code=process.returncode,error='Owned isolated case timed out',stdout=stdout,stderr=stderr)
    if (args.out/'result.json').exists():report['case']=json.loads((args.out/'result.json').read_text())
    report['after_host_sample']=supervise.sample();report['outcome']='pass' if process.returncode==0 else 'fail'
    if report['after_host_sample']['MemAvailable_bytes']<4*e.GIB or supervise.pressured(report['after_host_sample']):report['outcome']='resource-deferred'
    args.out.with_suffix('.driver.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['outcome']=='pass' else 2 if report['outcome']=='resource-deferred' else 1


if __name__=='__main__':raise SystemExit(main())
