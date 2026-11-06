#!/usr/bin/env python3
"""Focused real-signal restoration proof; no child, compiler or sanitizer."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/platform/gpu/native/userclient'))
import admission
import launcher

CANCEL={signal.SIGALRM,signal.SIGTERM,signal.SIGINT}


def mask():
    return set(signal.pthread_sigmask(signal.SIG_BLOCK,set()))


def names(values):
    return sorted(signal.Signals(s).name for s in values)


def run_case(case,stage=None,injected=(),blocked_int=False,preexisting=False,callback_cancel=False,default_int=False):
    raw_signal=signal.signal;raw_timer=signal.setitimer
    initial={s:signal.getsignal(s) for s in CANCEL};initial_mask=mask()
    working=initial_mask|{signal.SIGUSR1}|({signal.SIGINT} if blocked_int else set())
    record={'case':case,'delivered':[],'hook':None,'injected':names(injected),'initial_caller_mask':names(working)}
    before={}
    def prior(number,frame):
        record['delivered'].append({'signal':signal.Signals(number).name,
            'all_handlers_restored':all(signal.getsignal(s)==before[s] for s in CANCEL),'mask':names(mask())})
    for s in CANCEL:
        before[s]=signal.default_int_handler if default_int and s==signal.SIGINT else prior
        raw_signal(s,before[s])
    signal.pthread_sigmask(signal.SIG_SETMASK,working)
    if preexisting: os.kill(os.getpid(),signal.SIGINT)
    def inject():
        record['hook']={'mask':names(mask()),'all_cancel_signals_blocked':CANCEL.issubset(mask())}
        for s in injected: os.kill(os.getpid(),s)
    def intercept(number,handler):
        if stage=='handlers' and number==signal.SIGALRM and handler==before[signal.SIGALRM] and record['hook'] is None: inject()
        return raw_signal(number,handler)
    def timer(which,seconds,interval=0):
        if stage=='timer' and which==signal.ITIMER_REAL and seconds==0 and record['hook'] is None: inject()
        return raw_timer(which,seconds,interval)
    def callback():
        if callback_cancel:
            try: os.kill(os.getpid(),signal.SIGINT)
            finally:
                os.kill(os.getpid(),signal.SIGTERM)
                os.kill(os.getpid(),signal.SIGALRM)
        return 23
    signal.signal=intercept;signal.setitimer=timer
    try:
        try: record['result']=launcher.guarded(callback,1)
        except BaseException as error: record['escaped']={'type':type(error).__name__,'message':str(error)}
        record['handlers_restored_at_return']=all(signal.getsignal(s)==before[s] for s in CANCEL)
        record['mask_at_return']=names(mask())
        record['pending_at_return']=names(signal.sigpending()&CANCEL)
        record['timer_at_return']=list(signal.getitimer(signal.ITIMER_REAL))
        record['delivery_before_caller_unblock']=len(record['delivered'])
        if blocked_int:
            signal.pthread_sigmask(signal.SIG_SETMASK,working-{signal.SIGINT})
            record['pending_after_caller_unblock']=names(signal.sigpending()&CANCEL)
    finally:
        signal.signal=raw_signal;signal.setitimer=raw_timer
        # Repair only this fixture process even if a candidate fails. Drain
        # only the fixture's three generated signals through safe prior handlers.
        signal.pthread_sigmask(signal.SIG_BLOCK,CANCEL)
        raw_timer(signal.ITIMER_REAL,0)
        for s in CANCEL: raw_signal(s,prior)
        signal.pthread_sigmask(signal.SIG_UNBLOCK,CANCEL)
        signal.pthread_sigmask(signal.SIG_BLOCK,CANCEL)
        for s,handler in initial.items(): raw_signal(s,handler)
        signal.pthread_sigmask(signal.SIG_SETMASK,initial_mask)
    record['fixture_handlers_repaired']=all(signal.getsignal(s)==initial[s] for s in CANCEL)
    record['fixture_mask_repaired']=mask()==initial_mask
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--experiment',required=True)
    args=parser.parse_args();admission.authority(args.experiment)
    out=admission.owned_output(args.out);out.mkdir(parents=True)
    started=time.monotonic();checks=[];cases=[]
    result={'kind':'host-test','checks':checks,'cases':cases,'source_only':True,'child_or_target_tool':False,'root_allocation':False,'argv':[sys.executable,'-s',*sys.argv]}
    def check(name,ok):
        checks.append({'case':name,'pass':bool(ok)})
        if not ok: raise AssertionError(name)
    try:
        definitions=[
            ('normal-nonempty-mask',{}),
            ('first-INT-handler-restoration',{'stage':'handlers','injected':(signal.SIGINT,)}),
            ('repeated-all-handler-restoration',{'stage':'handlers','injected':tuple([signal.SIGINT,signal.SIGTERM,signal.SIGALRM]*2)}),
            ('first-TERM-timer-restoration',{'stage':'timer','injected':(signal.SIGTERM,)}),
            ('callback-first-and-repeated-cancel',{'callback_cancel':True}),
            ('caller-blocked-INT-pending',{'stage':'handlers','injected':(signal.SIGINT,signal.SIGINT),'blocked_int':True}),
            ('caller-existing-INT-pending',{'blocked_int':True,'preexisting':True}),
            ('caller-default-INT-semantics',{'stage':'handlers','injected':(signal.SIGINT,),'default_int':True})]
        for name,options in definitions:
            r=run_case(name,**options);cases.append(r)
            check(name+'-handlers-restored',r['handlers_restored_at_return'])
            check(name+'-exact-old-mask',r['mask_at_return']==r['initial_caller_mask'])
            check(name+'-timer-off',r['timer_at_return']==[0.0,0.0])
            check(name+'-fixture-state-repaired',r['fixture_handlers_repaired'] and r['fixture_mask_repaired'])
            if options.get('stage'):check(name+'-blocked-through-hook',r['hook']['all_cancel_signals_blocked'])
            if options.get('default_int'):
                check(name+'-original-KeyboardInterrupt',r.get('escaped',{}).get('type')=='KeyboardInterrupt')
            else:
                check(name+'-no-Cancelled-escape','escaped' not in r)
                check(name+'-result',r['result']['outcome']==('cancelled' if options.get('callback_cancel') else 'pass'))
            if options.get('blocked_int'):
                check(name+'-caller-owned-pending',r['pending_at_return']==['SIGINT'] and r['delivery_before_caller_unblock']==0 and r['pending_after_caller_unblock']==[])
                check(name+'-caller-unblock-delivers',len(r['delivered'])==1 and r['delivered'][0]['signal']=='SIGINT')
            elif options.get('injected') and not options.get('default_int'):
                check(name+'-pending-delivered-to-caller',{d['signal'] for d in r['delivered']}==set(r['injected']))
            if r['delivered']:check(name+'-all-handlers-restored-before-delivery',all(d['all_handlers_restored'] for d in r['delivered']))
            if options.get('callback_cancel'):check(name+'-first-and-repeated-recorded',r['result']['signals']==[signal.SIGINT,signal.SIGTERM,signal.SIGALRM])
        # Re-pin phase metadata without rerunning the old35/process matrix.
        phase_plans=[]
        for phase in ['native','host-sanitizer']:
            actual=ROOT/'artifacts/gpu-userclient'/('future-signalfix-'+phase+'-absent')
            p=admission.make_plan(phase,actual,args.experiment)
            f=out/(phase+'-plan.json');f.write_text(json.dumps(p,indent=2)+'\n')
            before={s:signal.getsignal(s) for s in CANCEL};old_mask=mask()
            try:launcher.guarded(lambda:admission.execute(f,admission.sha(f),out/'no-approval.json'))
            except admission.PendingInterface as error:check(phase+'-disabled-before-allocation','Final accepted VM044/046' in str(error))
            else:check(phase+'-disabled-before-allocation',False)
            check(phase+'-exception-restores-handlers-mask',before=={s:signal.getsignal(s) for s in CANCEL} and mask()==old_mask)
            check(phase+'-actual-output-absent',not actual.exists())
            phase_plans.append({'phase':phase,'path':str(f),'sha256':admission.sha(f),'launcher':p['launcher'],'executor':p['executor']})
        result['phase_plans']=phase_plans
        result['outcome']='pass'
    except BaseException as error:
        result['outcome']='fail';result['error']=repr(error);raise
    finally:
        result['elapsed_seconds']=time.monotonic()-started
        result['proc_status']=[l for l in Path('/proc/self/status').read_text().splitlines() if l.startswith(('VmRSS:','VmHWM:'))]
        (out/'focused.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'outcome':result['outcome'],'checks':len(checks),'report':str(out/'focused.json')}))


if __name__=='__main__':main()
