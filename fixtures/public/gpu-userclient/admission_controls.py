#!/usr/bin/env python3
"""Actual Python-only admission/launcher refusal, deadline and cleanup controls."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"src/platform/gpu/native/userclient"))
import admission
import launcher


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--experiment",required=True)
    args=parser.parse_args()
    out=admission.owned_output(args.out);out.mkdir(parents=True)
    admission.authority(args.experiment)
    started=time.monotonic();checks=[];artifacts=[]
    def check(name,ok):
        checks.append({"case":name,"pass":bool(ok)})
        if not ok: raise AssertionError(name)
    def refuses(name,callback,phrase):
        try: callback()
        except ValueError as error:
            check(name,phrase in str(error));checks[-1]["error"]=str(error)
        else: check(name,False)
    record={"kind":"host-test","checks":checks,"source_only":True,"compiler":False,"sanitizer":False,"allocation":False,"artifacts":artifacts}
    try:
        plans={}
        for phase in ["native","host-sanitizer"]:
            actual=ROOT/"artifacts/gpu-userclient"/("future-"+phase+"-not-created")
            plans[phase]=admission.make_plan(phase,actual,args.experiment)
            p=out/(phase+"-plan.json");p.write_text(json.dumps(plans[phase],indent=2)+"\n");artifacts.append(str(p))
            refuses(phase+"-pending-interface",lambda:admission.execute(p,admission.sha(p),out/"absent-approval.json"),"Final accepted VM044/046")
            check(phase+"-no-output",not actual.exists())
            command=[sys.executable,'-s',str(ROOT/'src/platform/gpu/native/userclient/launcher.py'),'--plan',str(p),'--plan-sha256',admission.sha(p),'--approval',str(out/'absent-approval.json')]
            cli=subprocess.run(command,capture_output=True,text=True,timeout=3)
            (out/(phase+'-cli.stderr')).write_text(cli.stderr)
            record.setdefault('admission_cli',[]).append({'argv':command,'exit_code':cli.returncode,'stderr':cli.stderr})
            check(phase+'-launcher-CLI-refuses',cli.returncode==2 and 'Final accepted VM044/046' in cli.stderr)
        check("separate-phases",len(plans['native']['commands'])==3 and len(plans['host-sanitizer']['commands'])==3 and plans['native']['commands']!=plans['host-sanitizer']['commands'])
        hostspec=copy.deepcopy(admission.policy())
        hostspec['execution_enabled']=True
        hostspec['final_binding']={'accepted':True,'resource_profile':'project-budget-v1','helper':hostspec['source_control_helper']}
        refuses('real-AF193-lacks-RSS-only-API',lambda:admission.accepted_interface(hostspec,'host-sanitizer'),'run_child_rss_only interface; no fallback')
        tampered=copy.deepcopy(plans['native']);tampered['commands'][0]['argv'].append('-DUNREVIEWED_FLAG=1')
        p=out/'changed-argv.json';p.write_text(json.dumps(tampered));artifacts.append(str(p))
        refuses('changed-argv',lambda:admission.execute(p,admission.sha(p),out/'absent-approval.json'),'Source plan/argv')
        p=out/'native-plan.json'
        refuses('changed-plan-hash',lambda:admission.execute(p,'0'*64,out/'absent-approval.json'),'same-byte JSON')
        caller=out/'changed-caller';caller.mkdir()
        shutil.copyfile(ROOT/'src/platform/gpu/native/userclient/launcher.py',caller/'launcher.py')
        (caller/'admission.py').write_text((ROOT/'src/platform/gpu/native/userclient/admission.py').read_text()+'\n# changed refusal witness\n')
        command=[sys.executable,'-s',str(caller/'launcher.py'),'--plan',str(p),'--plan-sha256',admission.sha(p),'--approval',str(out/'absent-approval.json')]
        cli=subprocess.run(command,capture_output=True,text=True,timeout=3)
        record['admission_cli'].append({'argv':command,'exit_code':cli.returncode,'stderr':cli.stderr})
        check('changed-executor-before-evaluation',cli.returncode==2 and 'changed executor source' in cli.stderr)
        refuses('nonfinite-deadline',lambda:launcher.guarded(lambda:None,float('inf')),'Finite whole-phase')
        before={s:signal.getsignal(s) for s in [signal.SIGINT,signal.SIGTERM,signal.SIGALRM]}
        check('normal-handler-restoration',launcher.guarded(lambda:17,1)['result']==17 and before=={s:signal.getsignal(s) for s in before})
        signal.setitimer(signal.ITIMER_REAL,5)
        try: refuses('inherited-timer',lambda:launcher.guarded(lambda:None,1),'Existing timer')
        finally: signal.setitimer(signal.ITIMER_REAL,0)
        parent=admission.load(admission.PARENT,admission.PARENT_SHA)
        mirror=out/'source-mirror'
        for name in parent['source_freeze']['files']:
            target=mirror/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        old=admission.ROOT
        try:
            admission.ROOT=mirror;admission.frozen_sources(parent)
            extra=mirror/'src/platform/gpu/native/userclient/unreviewed.cc';extra.write_text('/* rejection witness; never compiled */\n')
            refuses('new-provider-source-refused',lambda:admission.frozen_sources(parent),'Unreviewed native provider/type')
        finally: admission.ROOT=old
        check('backend-stays-unready',all(p['backend_ready'] is False and p['hardware_result'] is False and p['native_ABI_qualified'] is False for p in plans.values()))
        # Process controls call only accepted AF193 with Python fixtures,
        # admit=False, no ProjectBudget allocation and no ASan equivalence claim.
        for case in ['normal','child-deadline','whole-deadline','term-repeat','int']:
            caseout=out/case;caseout.mkdir()
            argv=[sys.executable,'-s',str(ROOT/'fixtures/public/gpu-userclient/process_worker.py'),str(caseout),case]
            with (caseout/'controller.stdout').open('xb') as stdout,(caseout/'controller.stderr').open('xb') as stderr:
                proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'})
                try:
                    if case in ['term-repeat','int']:
                        deadline=time.monotonic()+4
                        while not (caseout/'probe-ready.json').exists() and proc.poll() is None and time.monotonic()<deadline: time.sleep(.01)
                        if not (caseout/'probe-ready.json').exists(): raise AssertionError('source probe readiness missing')
                        os.kill(proc.pid,signal.SIGINT if case=='int' else signal.SIGTERM)
                        if case=='term-repeat':
                            time.sleep(.05);os.kill(proc.pid,signal.SIGTERM)
                    code=proc.wait(timeout=8)
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
                    # Watchdog recovery may touch only exact recorded test
                    # identities. Never rely on a reused PID or arbitrary kill.
                    ready=caseout/'probe-ready.json'
                    if ready.exists():
                        ids=json.loads(ready.read_text())
                        live=[]
                        for row in ids:
                            try:
                                fields=Path('/proc',str(row['pid']),'stat').read_text().rsplit(') ',1)[1].split()
                                if int(fields[19])==row['start_ticks'] and fields[0]!='Z': live.append(row)
                            except FileNotFoundError: pass
                        if live:
                            for row in live:
                                try: os.kill(row['pid'],signal.SIGKILL)
                                except ProcessLookupError: pass
                            record.setdefault('watchdog_recovery',[]).append({'case':case,'identities':live})
            worker=admission.load(caseout/'worker.json');artifacts.append(str(caseout/'worker.json'))
            record.setdefault('process_commands',[]).append({'argv':argv,'exit_code':code,'report':str(caseout/'worker.json')})
            check(case+'-controller-exit',code==0)
            check(case+'-zero-survivors',not any(p['state']!='Z' for p in worker['after']) and not record.get('watchdog_recovery'))
            if case=='normal': check(case+'-child-pass',worker['launcher']['result']['exit_code']==0)
            elif case=='child-deadline': check(case+'-measured-deadline',worker['launcher']['result']['stop_reason']=='deadline')
            else:
                check(case+'-launcher-cancelled',worker['launcher']['outcome']=='cancelled')
                check(case+'-two-owned-groups',len({r['pgrp'] for r in worker['identities']})==2)
                if case=='term-repeat':check(case+'-both-signals',len(worker['launcher']['signals'])==2)
        record['outcome']='pass'
    except BaseException as error:
        record['outcome']='fail';record['error']=repr(error)
        raise
    finally:
        record['elapsed_seconds']=time.monotonic()-started
        record['proc_status']=[l for l in Path('/proc/self/status').read_text().splitlines() if l.startswith(('VmHWM:','VmRSS:'))]
        (out/'controls.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'outcome':record['outcome'],'checks':len(checks),'report':str(out/'controls.json')}))


if __name__=='__main__': main()
