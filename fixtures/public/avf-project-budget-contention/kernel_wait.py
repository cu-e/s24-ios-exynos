#!/usr/bin/env python3
"""Real-process prototype controls; no compiler, allocation or production queue."""
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

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]; TOOL=ROOT/'tools/build/avf_kernel_objects.py'
spec=importlib.util.spec_from_file_location('kernel_wait_engine',TOOL);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


def worker(mode, out, lock_path):
    checks=[]; child=None; start=time.monotonic()
    old_handler=signal.getsignal(signal.SIGALRM); old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    report={'mode':mode,'checks':checks,'outcome':'fail','pid':os.getpid()}
    def check(name,value):
        checks.append({'name':name,'pass':bool(value)})
        if not value:raise ValueError(name)
    class OuterDeadline(BaseException):pass
    class Cancelled(BaseException):pass
    events=[]
    def outer(signum,frame):events.append(time.monotonic());raise OuterDeadline()
    try:
        with lock_path.open('a+') as lock:
            if mode=='timeout':
                before=time.monotonic()
                try:e.bounded_flock(lock,.5)
                except ValueError as error:check('raising timeout interrupts real Python3.14 blocking flock',str(error)=='Project budget lock acquisition timed out')
                else:raise ValueError('held lock acquired')
                check('same half-second bound observed',.45<=time.monotonic()-before<.8)
                check('handler and disabled timer restored',signal.getsignal(signal.SIGALRM)==old_handler and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
            elif mode=='earlier':
                signal.signal(signal.SIGALRM,outer);signal.setitimer(signal.ITIMER_REAL,.12)
                before=time.monotonic()
                try:e.bounded_flock(lock,.5)
                except OuterDeadline:pass
                else:raise ValueError('earlier deadline lost')
                check('earlier raising outer deadline propagated once',len(events)==1 and .09<time.monotonic()-before<.35)
                check('consumed outer one-shot is not rearmed',signal.getsignal(signal.SIGALRM)==outer and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
            elif mode=='later':
                signal.signal(signal.SIGALRM,outer);before=time.monotonic();signal.setitimer(signal.ITIMER_REAL,.65)
                try:e.bounded_flock(lock,.12)
                except ValueError:pass
                else:raise ValueError('held lock acquired')
                remaining,interval=signal.getitimer(signal.ITIMER_REAL)
                check('remaining earlier-installed timer decremented rather than restarted',.35<remaining<.56 and interval==0 and signal.getsignal(signal.SIGALRM)==outer)
                try:time.sleep(.8)
                except OuterDeadline:pass
                check('restored outer deadline fires at original wall time',len(events)==1 and .60<events[0]-before<.78)
            elif mode=='success':
                signal.signal(signal.SIGALRM,outer);before=time.monotonic();signal.setitimer(signal.ITIMER_REAL,.3)
                with (out/'unheld.lock').open('a+') as free:e.bounded_flock(free,.5)
                remaining,_=signal.getitimer(signal.ITIMER_REAL)
                check('successful acquisition restores original handler and remaining timer',signal.getsignal(signal.SIGALRM)==outer and .2<remaining<=.3)
                try:time.sleep(.45)
                except OuterDeadline:pass
                check('successful acquisition preserves earlier outer deadline',len(events)==1 and .25<events[0]-before<.43)
            elif mode.startswith('cancel-'):
                restoration='restore' in mode
                expected_alarm=old_handler; cancel_count=[]; injected=[]; original_signal=signal.signal
                if restoration:
                    def expected_alarm(signum,frame):raise OuterDeadline()
                    signal.signal(signal.SIGALRM,expected_alarm);signal.setitimer(signal.ITIMER_REAL,.9)
                sig=getattr(signal,mode.split('-')[1]);previous=signal.getsignal(sig)
                def cancel(signum,frame):cancel_count.append(signum);raise Cancelled()
                signal.signal(sig,cancel)
                child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(8)'],cwd='/tmp',start_new_session=True)
                (out/(mode+'.ready')).write_text(json.dumps({'child_pid':child.pid,'controller_pid':os.getpid()}))
                if restoration:
                    def at_restore(signum,handler):
                        if signum==signal.SIGALRM and handler is expected_alarm and not injected:
                            injected.append(time.monotonic());os.kill(os.getpid(),sig)
                        return original_signal(signum,handler)
                    e.signal.signal=at_restore
                try:
                    try:e.bounded_flock(lock,.5)
                    except Cancelled:pass
                    else:raise ValueError('cancellation lost')
                finally:e.signal.signal=original_signal
                timer=signal.getitimer(signal.ITIMER_REAL)
                check('TERM/INT handler preserved and alarm restored',signal.getsignal(sig)==cancel and signal.getsignal(signal.SIGALRM)==expected_alarm and (restoration or timer==(0.0,0.0)))
                if restoration:
                    check('second actual cancellation delivered only after restoration',len(injected)==1 and cancel_count==[sig,sig])
                    check('original exact signal mask restored despite second cancellation',signal.pthread_sigmask(signal.SIG_BLOCK,set())==old_mask)
                    check('original outer timer remaining deadline retained',.5<timer[0]<.9 and timer[1]==0)
                signal.signal(sig,previous)
            elif mode=='unsupported':
                for interval,handler in [(.2,outer),(0,signal.SIG_IGN),(0,signal.SIG_DFL)]:
                    signal.signal(signal.SIGALRM,handler);signal.setitimer(signal.ITIMER_REAL,.8,interval)
                    try:e.bounded_flock(lock,.5)
                    except ValueError:pass
                    else:raise ValueError('unsupported timer accepted')
                    remaining,actual_interval=signal.getitimer(signal.ITIMER_REAL)
                    check('unsupported timer refused and preserved '+str(interval)+str(handler),remaining>.65 and actual_interval==interval and signal.getsignal(signal.SIGALRM)==handler)
                    signal.setitimer(signal.ITIMER_REAL,0)
                errors=[]
                def threaded():
                    try:e.bounded_flock(lock,.5)
                    except ValueError as error:errors.append(str(error))
                thread=threading.Thread(target=threaded);thread.start();thread.join(timeout=1)
                check('non-main-thread refuses without blocking',len(errors)==1 and not thread.is_alive())
                gate=threading.Event();thread=threading.Thread(target=lambda:gate.wait(1));thread.start()
                try:
                    try:e.bounded_flock(lock,.5)
                    except ValueError as error:check('main interpreter with another thread refuses', 'single main-thread' in str(error))
                    else:raise ValueError('multi-thread process accepted')
                finally:gate.set();thread.join(timeout=1)
                pending=[];signal.signal(signal.SIGALRM,lambda s,f:pending.append(s));signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM});os.kill(os.getpid(),signal.SIGALRM)
                try:e.bounded_flock(lock,.5)
                except ValueError:pass
                else:raise ValueError('blocked pending alarm accepted')
                check('unsupported pending blocked signal retained',signal.SIGALRM in signal.sigpending() and signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK,set()))
                signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
                check('original pending handler delivers after original mask restoration',pending==[signal.SIGALRM])
        report['outcome']='pass'
    except BaseException as error:report['error']=repr(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler);signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
        if child is not None:
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            child.wait(timeout=3)
            check('owned child cleanup complete',not any(p['session']==child.pid and p['state']!='Z' for p in e.process_table().values()))
        report['elapsed_seconds']=time.monotonic()-start
        (out/(mode+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    return report['outcome']!='pass'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--main',type=Path);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--worker');parser.add_argument('--lock',type=Path);parser.add_argument('--restoration-only',action='store_true');args=parser.parse_args()
    if args.worker:return worker(args.worker,args.out,args.lock)
    out=args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():raise ValueError('fresh own artifact output required')
    out.mkdir(parents=True);supervise=e.supervisor(args.main.resolve());holder=None;actors=[]
    report={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':e.stamp(),'argv':[sys.executable,*sys.argv],'engine_sha256':e.sha(TOOL),'compiler_started':False,'commands':[]}
    try:
        admission=[]
        for _ in range(3):
            sample=supervise.sample();admission.append(sample)
            if sample['MemAvailable_bytes']<4*e.GIB or supervise.pressured(sample):report.update(outcome='resource-deferred',admission=admission);return 2
            time.sleep(1)
        report['admission']=admission;lock=out/'stable.lock';ready=out/'holder.ready'
        holder=subprocess.Popen([sys.executable,'-c',"import fcntl,pathlib,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);pathlib.Path(sys.argv[2]).write_text('ready');time.sleep(25)",lock,ready],cwd='/tmp')
        deadline=time.monotonic()+2
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.005)
        if not ready.exists():raise ValueError('holder not ready')
        identity=(lock.stat().st_dev,lock.stat().st_ino)
        modes=['timeout','earlier','later','success','unsupported']+['cancel-'+sig+'-'+str(n) for n in range(3) for sig in ['SIGTERM','SIGINT']]
        if args.restoration_only:modes=['cancel-'+sig+'-restore-'+str(n) for n in range(3) for sig in ['SIGTERM','SIGINT']]
        # Cancellation names carry round suffix; each worker uses unique paths.
        for mode in modes:
            proc=subprocess.Popen([sys.executable,__file__,'--worker',mode,'--out',str(out),'--lock',str(lock)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);actors.append(proc)
            if mode.startswith('cancel-'):
                marker=out/(mode+'.ready');deadline=time.monotonic()+2
                while not marker.exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.005)
                if not marker.exists():raise ValueError('cancel worker not ready')
                time.sleep(.03);os.kill(proc.pid,getattr(signal,mode.split('-')[1]))
            stdout,stderr=proc.communicate(timeout=4);record=json.loads((out/(mode+'.json')).read_text())
            report['commands'].append({'argv':proc.args,'exit_code':proc.returncode,'record':record,'stdout':stdout,'stderr':stderr})
            if proc.returncode or record['outcome']!='pass':raise ValueError('worker failed '+mode)
        report['stable_inode_unchanged']=identity==(lock.stat().st_dev,lock.stat().st_ino)
        report['after_resources']=supervise.sample();report['outcome']='resource-deferred' if report['after_resources']['MemAvailable_bytes']<4*e.GIB or supervise.pressured(report['after_resources']) else 'pass'
    except BaseException as error:report['error']=repr(error)
    finally:
        for proc in actors:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=3)
        if holder is not None:
            holder.terminate();holder.wait(timeout=3)
        report['controller_memory']=e.actual_controller_memory();report['source_hashes']={str(p):e.sha(p) for p in [TOOL,Path(__file__)]}
        report['artifacts']=[str(p) for p in out.iterdir() if p.is_file()];report['sha256']={p:e.sha(p) for p in report['artifacts']}
        (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','stable_inode_unchanged']}|{'cases':len(report['commands'])},indent=2))
    return report['outcome']!='pass'

if __name__=='__main__':raise SystemExit(main())
