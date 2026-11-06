#!/usr/bin/env python3
"""Targeted retained SQLite iterator lifetime controls; actual Python/files only."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import struct
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
MAIN=ROOT.parents[1]
SOURCE=ROOT/'tools/build/avf_guest_link_inputs.py'
REVIEW=MAIN/'worktrees/rev-vm022-link-eu-20261106/docs/reviews/vm-022-link/review.py'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def descriptors():
    result={}
    for path in Path('/proc/self/fd').iterdir():
        try:result[path.name]=str(path.readlink())
        except OSError:pass
    return result

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='fail',source_only=True,checks=[],observations=[],
                executor_sha256=sha(SOURCE),target_tools_executed=False,large_parser_benchmark_repeated=False)
    try:
        assert sha(REVIEW)=='d9aa067d856bdf9f06e73e4a5b4d56a77f138eca413d8c71868df7aced5e505d'
        fixture=load(REVIEW,'fixture_constructor_only');m=load(SOURCE,'cursor_corrected')
        report['initial_process']=m.proc_status()
        def check(name,value):
            if not value:raise AssertionError(name)
            report['checks'].append(name)
        def rejected(name,call):
            try:call()
            except ValueError:report['checks'].append(name);return
            raise AssertionError(name)
        two=bytearray(fixture.macho(False));struct.pack_into('<4I',two,32+152+8,0x500,2,0x520,12)
        struct.pack_into('<IBBHQ',two,0x510,9,0xf,1,0,0x408);two[0x520:0x52c]=b'\0__start\0_x\0'
        path=out/'two-symbols.o';path.write_bytes(two)
        for api in ['items','values']:
            for state in ['unstarted','partial','exhausted','explicitly-closed']:
                before=descriptors()
                with m.macho_snapshot(path) as (snapshot,view):
                    index=view['external_symbols'];directory=Path(index.temporary.name)
                    iterator=getattr(index,api)()
                    if state in ['partial','explicitly-closed']:next(iterator)
                    if state=='exhausted':check(api+' exact two-row iteration',len(list(iterator))==2)
                    if state=='explicitly-closed':iterator.close();check(api+' explicit close clears cursor',not index.cursors)
                after=descriptors()
                check(api+' '+state+' teardown closes actual FD',before==after and index.db is None and not index.cursors and not directory.exists())
                if state in ['unstarted','partial']:rejected(api+' '+state+' escaped next refuses',lambda:next(iterator))
                else:check(api+' '+state+' cannot emit more rows',next(iterator,None) is None)
                rejected(api+' '+state+' escaped lookup refuses',lambda:index.get('__start'))
                iterator.close();index.close()
                check(api+' '+state+' idempotent cleanup leaves FD unchanged',descriptors()==before)
                report['observations'].append(dict(api=api,state=state,before=before,after=after))
        before=descriptors()
        with m.macho_snapshot(path) as (snapshot,view):
            index=view['external_symbols'];items=index.items();values=index.values();next(items);next(values)
            check('both partially consumed cursors tracked',len(index.cursors)==2)
        check('simultaneous retained iterators finalized eagerly',descriptors()==before and not index.cursors)
        for iterator in [items,values]:rejected('simultaneous escaped iterator refuses',lambda iterator=iterator:next(iterator));iterator.close()
        for mode in ['body-error','actual-SIGTERM','cleanup-error-with-body','cleanup-error-alone','identity-error']:
            before=descriptors();original=RuntimeError('original body error');cleanup=RuntimeError('cleanup control error');observed=None
            prior=signal.getsignal(signal.SIGTERM);fake_closed=[];index=None;snapshot=None
            class FailingResource:
                def close(self):fake_closed.append(True);raise cleanup
            try:
                with m.owned_cancellation():
                    with m.macho_snapshot(path) as (snapshot,view):
                        index=view['external_symbols'];iterator=index.items();next(iterator)
                        if mode.startswith('cleanup-error'):snapshot.own(FailingResource())
                        if mode in ['body-error','cleanup-error-with-body']:raise original
                        if mode=='actual-SIGTERM':os.kill(os.getpid(),signal.SIGTERM)
                        if mode=='identity-error':
                            with path.open('ab') as stream:stream.write(b'changed after parsing')
            except BaseException as error:observed=error
            check(mode+' all actual owned descriptors closed',descriptors()==before and snapshot.stream.closed and index.db is None and not index.cursors)
            check(mode+' prior signal handler restored',signal.getsignal(signal.SIGTERM)==prior)
            if mode in ['body-error','cleanup-error-with-body']:check(mode+' original exception preserved by identity',observed is original)
            if mode=='cleanup-error-with-body':check('cleanup error retained as original note',fake_closed and any('cleanup control error' in note for note in original.__notes__))
            if mode=='cleanup-error-alone':check('cleanup-only failure propagated after all teardown',observed is cleanup and fake_closed)
            if mode=='actual-SIGTERM':check('actual cancellation remains nonpass',isinstance(observed,m.OwnedCancellation))
            if mode=='identity-error':check('real post-parse mutation remains rejected',isinstance(observed,ValueError));path.write_bytes(two)
            rejected(mode+' retained iterator invalidated',lambda:next(iterator));iterator.close()
        tree=ast.parse(SOURCE.read_text())
        stage=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='execute_link_stage_reserved')
        updates=[node for node in ast.walk(stage) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='update']
        outcomes=[kw.value.value for call in updates for kw in call.keywords if kw.arg=='outcome' and isinstance(kw.value,ast.Constant)]
        check('unfinished stage uses schema-valid inconclusive', 'inconclusive' in outcomes and 'incomplete' not in outcomes and 'pass' not in outcomes)
        check('all productive profile and completion pins remain closed',m.LINK_PROFILE_PINS=={} and m.LINK_COMPLETION_PINS=={})
        report.update(outcome='pass',final_process=m.proc_status(),final_fds=descriptors())
    except BaseException as error:report['error']=repr(error)
    report['artifact_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='observations'},indent=2))
    return 0 if report['outcome']=='pass' else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    raise SystemExit(run(args.out.resolve()))
