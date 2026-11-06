#!/usr/bin/env python3
"""Source-only controls for the exact frozen in-process first-tail launcher."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.dont_write_bytecode=True
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
root=Path(__file__).resolve().parents[3]
file=root/'artifacts/avf-guest-link-inputs/launcher-freeze-2/first-tail-launch.py'
s=importlib.util.spec_from_file_location('first_tail_launcher',file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=False)
r=dict(kind='host-test',origin='local-host',outcome='fail',source_only=True,launcher_sha256=m.sha(file),checks=[],
    target_tool_executed=False,production_grant=False,controller_pid=os.getpid())
def require(name,condition):
    if not condition:raise AssertionError(name)
    r['checks'].append(name)
try:
    tail=m.load_tail()
    require('exact physical reviewed helper',tail.sha(m.TARGET)==m.TARGET_SHA)
    handlers={n:signal.getsignal(n) for n in [signal.SIGTERM,signal.SIGINT,signal.SIGALRM]}
    caught=False
    with m.whole_deadline(.02) as timer:
        try:time.sleep(.2)
        except KeyboardInterrupt:caught=True
    require('real alarm outside helper context uses BaseException fallback',caught and timer['deadline_fired'])
    caught=False
    with m.whole_deadline(.02) as timer:
        with tail.owned_cancellation() as state:
            try:time.sleep(.2)
            except tail.OwnedCancellation:caught=True
    require('real alarm relays into exact reviewed SIGTERM cancellation',caught and state.signals==[signal.SIGTERM] and timer['deadline_fired'])
    class Probe:
        def sample(self,session=None,lock_timeout=.5):return {'callback_completed':True}
    probe=Probe();caught=False;callback=False
    with m.whole_deadline(.02) as timer:
        with tail.owned_cancellation() as state:
            try:
                with state.command(probe):
                    probe.sample(os.getpid())
                    time.sleep(.1)
                    callback=probe.sample(None)['callback_completed']
            except tail.OwnedCancellation:caught=True
    require('alarm during deferred final-callback surface completes callback then propagates',caught and callback and timer['deadline_fired'])
    require('all original handlers restored and whole timer disabled',all(signal.getsignal(n)==h for n,h in handlers.items()) and not any(signal.getitimer(signal.ITIMER_REAL)))
    before=os.getpid()
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        try:m.invoke([str(m.TARGET),'--help'])
        except SystemExit as result:code=result.code
    require('actual reviewed helper help executes in same process without child',code==0 and os.getpid()==before and 'execute-tails' in stdout.getvalue())
    old=m.MAIN/'worktrees/int-guest-profile-20261106/artifacts/integration-gate/guest-profile-publication-1/evidence.json'
    marker=m.MAIN/'artifacts/team-coordination/20261106-team/guest-profile-root-acceptance.json'
    try:m.validate_publication(json.loads(old.read_text()),json.loads(marker.read_text()),old,m.sha(old))
    except ValueError:r['checks'].append('actual historical profile-only publication cannot admit first tails')
    else:raise AssertionError('Historical publication credited as new tail acceptance')
    actual=m.MAIN/'worktrees/int-platform-20261106/artifacts/platform-integration/products-tail-resource-publication1/evidence.json'
    root_marker=m.MAIN/'artifacts/team-coordination/20261106-team/products-tail-resource-root-acceptance.json'
    require('exact actual combined publication bytes',m.sha(actual)=='e3bfcf5c703e7c9af1d926583bbc4eeb781f43b48375222454716315653e3e4c')
    require('exact actual root marker bytes',m.sha(root_marker)=='7555808615d34ec49f8ff35a4b069dac61819ec53bdb87038ac094a67bfcb042')
    m.validate_publication(json.loads(actual.read_text()),json.loads(root_marker.read_text()),actual,m.sha(actual))
    require('actual root tail acceptance admits source without whole-task closure',True)
    plan=json.loads(m.PLAN.read_text())
    require('reviewed plan/caller pins and proposed output remain exact/absent',m.sha(m.PLAN)==m.PLAN_SHA and plan['executor_sha256']==m.TARGET_SHA and not m.OUT.exists())
    r['outcome']='pass'
except Exception as error:r['error']=repr(error)
finally:
    r['final_process']=tail.proc_status() if 'tail' in locals() else {}
    (args.out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2));raise SystemExit(0 if r['outcome']=='pass' else 1)
