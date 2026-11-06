#!/usr/bin/env python3
"""Pinned in-process first-tail admission; requires actual publication/root grant."""
from contextlib import contextmanager
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import signal
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
ADMISSION = Path(__file__).resolve().parents[3]
MAIN = ADMISSION.parents[1]
TAIL = MAIN/'worktrees/vm-022-tail-cancellation-20261106'
TARGET = TAIL/'tools/build/avf_guest_link_inputs.py'
TARGET_SHA = '99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060'
POLICY_SHA = 'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0'
PLAN = TAIL/'artifacts/avf-guest-link-inputs/tail-fix-plan-2/execution-plan.json'
PLAN_SHA = '6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569'
OUT = TAIL/'artifacts/avf-guest-link-inputs/tails-execute-1'
REVIEW = MAIN/'worktrees/rev-vm022-execution-er-20261106/docs/reviews/vm-022-execution/evidence.json'
REVIEW_SHA = 'd8f6f2ad61bf238244110894c40d7a0931f4ef60ab4caa39f18d6eef6ea7157c'
OWNER = 'codex-guest-exec-20261106-cu'
EXPERIMENT = 'AVFLINKTAILRUN-001'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def load_tail():
    if sha(TARGET) != TARGET_SHA:raise ValueError('Reviewed physical tail source changed')
    spec = importlib.util.spec_from_file_location('vm022_reviewed_tail',TARGET)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

@contextmanager
def whole_deadline(seconds=600):
    """Relay the alarm through99d8 cancellation; do not raise in AF193 finally."""
    prior = {number:signal.getsignal(number) for number in [signal.SIGALRM,signal.SIGTERM,signal.SIGINT]}
    if any(signal.getitimer(signal.ITIMER_REAL)):raise ValueError('Existing real-time alarm cannot be replaced')
    state = dict(deadline_fired=False,stop_signals=[],cleanup=False,raised=False)
    def stop(number,frame):
        state['stop_signals'].append(number)
        if not state['cleanup'] and not state['raised']:
            state['raised'] = True
            raise KeyboardInterrupt('Root whole-pipeline stop')
    def deadline(number,frame):
        state['deadline_fired'] = True
        signal.raise_signal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,seconds)
        yield state
    finally:
        state['cleanup'] = True
        signal.setitimer(signal.ITIMER_REAL,0)
        for number,handler in prior.items():signal.signal(number,handler)

def validate_publication(publication,marker,publication_path,publication_sha):
    if (publication.get('outcome') != 'pass' or publication.get('mode') != 'publish' or
        publication.get('common_check',{}).get('exit_code') != 0 or
        any(p['state'] != 'Z' for p in publication['common_check']['after']['owned_processes']) or
        'tools/build/avf_guest_link_inputs.py' not in publication['audit']['paths'] or
        'docs/reviews/vm-022-execution/evidence.json' not in publication['audit']['paths']):
        raise ValueError('Actual combined tail publication and successful common check required')
    if (marker.get('accepted_by') != 'root' or marker.get('tail_executor_accepted_sha256') != TARGET_SHA or
        'REV-039' not in marker.get('original_owner_closures_authorized',[]) or
        marker.get('common_exit') != 0 or marker.get('lease_released') is not True or marker.get('owned_after') != [] or
        marker.get('published_head') != publication.get('published_head') or
        marker.get('common_evidence_sha256') != publication_sha or
        (MAIN/marker['common_evidence']).resolve() != publication_path.resolve()):
        raise ValueError('Exact root acceptance of this actual combined publication required')

def helper_argv(approval,approval_sha):
    return [str(TARGET),'--main',str(MAIN),'--vm008',str(MAIN/'worktrees/vm-008-20261105'),
        '--out',str(OUT),'--mode','execute-tails','--task','VM-022','--owner',OWNER,
        '--experiment',EXPERIMENT,'--shard','guest-link-tails','--source-plan',str(PLAN),
        '--source-plan-sha256',PLAN_SHA,'--approval',str(approval),'--approval-sha256',approval_sha]

def invoke(argv):
    if Path(argv[0]) != TARGET or sha(TARGET) != TARGET_SHA:raise ValueError('Only the exact reviewed caller can run')
    prior = sys.argv
    try:
        sys.argv = argv
        runpy.run_path(str(TARGET),run_name='__main__')
    finally:sys.argv = prior

def preflight(args):
    tail = load_tail();common = tail.accepted_runner(MAIN)
    if sha(MAIN/'tools/build/avf_guest_link_inputs.py') != TARGET_SHA:
        raise ValueError('MAIN has not published exact reviewed tail source')
    review = common.load_project(REVIEW,REVIEW_SHA)
    if (review['outcome'] != 'pass' or review['reviewed_source']['sha256'] != TARGET_SHA or
        review['reviewed_plan']['sha256'] != PLAN_SHA):raise ValueError('Exact final independent tail review required')
    publication = common.load_project(args.publication,args.publication_sha256)
    marker_path = common.canonical_output_path(args.root_acceptance)
    if not marker_path.is_relative_to(MAIN/'artifacts/team-coordination/20261106-team'):
        raise ValueError('Only canonical root acceptance markers are allowed')
    marker = common.load_project(marker_path,args.root_acceptance_sha256)
    validate_publication(publication,marker,args.publication,args.publication_sha256)
    owned = SimpleNamespace(main=MAIN,out=OUT,task='VM-022',owner=OWNER,experiment=EXPERIMENT,shard='guest-link-tails',
        vm008=MAIN/'worktrees/vm-008-20261105',execute_out=OUT)
    tail.tail_ownership(owned,common)
    plan = common.load_project(PLAN,PLAN_SHA)
    if plan != tail.tail_plan(owned,common):raise ValueError('Source plan no longer reconstructs exactly')
    approval = common.load_project(args.approval,args.approval_sha256)
    if approval['source_plan_sha256'] != PLAN_SHA:raise ValueError('Wrong root-approved plan')
    # Read-only constructor validation; no reserve/state mutation until caller.
    budget = common.project_approval(owned,approval,executor_path=TARGET)
    if budget.rss_limit != 268435456 or budget.allocation['max_compiler_jobs_total'] != 6:
        raise ValueError('This first-run admission requires256MiB and the current six-job global profile')
    args.launcher_out = common.canonical_output_path(args.launcher_out)
    if args.launcher_out.exists() or not args.launcher_out.is_relative_to(ADMISSION/'artifacts/avf-guest-link-inputs'):
        raise ValueError('Fresh separate owned launcher-log output required')
    return tail

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['publication','root-acceptance','approval']:
        parser.add_argument('--'+name,type=Path,required=True);parser.add_argument('--'+name+'-sha256',required=True)
    parser.add_argument('--launcher-out',type=Path,required=True)
    args = parser.parse_args()
    started = time.monotonic();tail = None;timer = None
    report = dict(kind='host-test',outcome='fail',task='VM-022',owner=OWNER,experiment=EXPERIMENT,
        launcher_pid=os.getpid(),launcher_sha256=sha(__file__),helper_sha256=TARGET_SHA,policy_sha256=POLICY_SHA,
        source_plan_sha256=PLAN_SHA,in_process=True,whole_deadline_seconds=600,target_invoked=False)
    try:
        with whole_deadline() as timer:
            tail = preflight(args)
            args.launcher_out.mkdir(parents=True,exist_ok=False)
            report['helper_argv'] = helper_argv(args.approval,args.approval_sha256)
            report['target_invoked'] = True
            try:invoke(report['helper_argv'])
            except SystemExit as stopped:
                report['helper_exit_code'] = int(stopped.code or 0)
                report['outcome'] = 'pass' if report['helper_exit_code'] == 0 else 'fail'
    except BaseException as error:
        report.update(outcome='fail',error=repr(error))
    finally:
        if timer:report.update(deadline_fired=timer['deadline_fired'],outer_stop_signals=timer['stop_signals'])
        report['elapsed_seconds'] = time.monotonic()-started
        if tail:report['final_process'] = tail.proc_status()
        if args.launcher_out.is_dir():
            (args.launcher_out/'launcher-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    return 0 if report['outcome']=='pass' else 2

if __name__ == '__main__':raise SystemExit(main())
