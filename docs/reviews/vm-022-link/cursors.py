#!/usr/bin/env python3
"""REVMAIN-003 independent cursor/schema controls; no subprocess or target tool."""
import ast
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time
import review
from correction import descriptors

AUTHOR=review.MAIN/'worktrees/vm-022-link-cursor-20261106'
SOURCE=AUTHOR/'tools/build/avf_guest_link_inputs.py'
SOURCE_SHA='9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'
PREVIOUS=review.MAIN/'worktrees/vm-022-link-correction-20261106/tools/build/avf_guest_link_inputs.py'


def run(out):
    start=time.monotonic();out.mkdir(parents=True,exist_ok=False)
    assert review.sha(SOURCE)==SOURCE_SHA
    assert review.sha(PREVIOUS)=='0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464'
    m=review.load(SOURCE,'review_final_cursor_core');checks=[];observations=[]
    initial=m.proc_status()
    def check(name,value,detail=None):checks.append(dict(name=name,pass_=bool(value),detail=detail))
    def reject(name,call):
        try:value=call()
        except ValueError as error:check(name,True,repr(error))
        else:check(name,False,repr(value))
    pinpath=AUTHOR/'artifacts/avf-guest-link-inputs/link-cursor-controls-1/artifact-bindings.json'
    assert review.sha(pinpath)=='32267dfd083966ecd3c1996eba2dd4d2bbe5f13420fb637d932e7cf42a95d403'
    pins=json.loads(pinpath.read_text())
    check('all frozen final producer artifact bindings',all(review.sha(pinpath.parent/name)==digest for name,digest in pins.items()),len(pins))
    check('final aggregate binding',review.sha(AUTHOR/'docs/procedures/avf-guest-link-inputs/link-cursor-evidence.json')=='79b212efb27f81af2224be0ecd0ade210d98e47c62d9ca279dbe902e8019c2a2')
    old={n.name:n for n in ast.parse(PREVIOUS.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    current={n.name:n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    changed=[]
    for name,node in old.items():
        if ast.dump(node)!=ast.dump(current[name]):changed.append(name)
    check('only registered three nodes changed',set(changed)=={'CoherentFile','SymbolIndex','execute_link_stage_reserved'},changed)
    oldmethods={n.name:n for n in old['CoherentFile'].body if isinstance(n,ast.FunctionDef)}
    newmethods={n.name:n for n in current['CoherentFile'].body if isinstance(n,ast.FunctionDef)}
    check('retained FD read/hash/identity API unchanged',all(ast.dump(n)==ast.dump(newmethods[name]) for name,n in oldmethods.items() if name!='__exit__'))
    class Normalize(ast.NodeTransformer):
        def visit_Constant(self,node):
            if node.value=='incomplete':return ast.copy_location(ast.Constant(value='inconclusive'),node)
            return node
    normalized=Normalize().visit(old['execute_link_stage_reserved'])
    check('stage change is only schema valid inconclusive',ast.dump(normalized)==ast.dump(current['execute_link_stage_reserved']))
    check('symbol name and parser loop unchanged no benchmark repeat',ast.dump(old['symbol_name'])==ast.dump(current['symbol_name']) and ast.dump(old['parse_macho_snapshot'])==ast.dump(current['parse_macho_snapshot']))
    two=bytearray(review.macho(False));struct.pack_into('<4I',two,32+152+8,0x500,2,0x520,12)
    struct.pack_into('<IBBHQ',two,0x510,9,0xf,1,0,0x408);two[0x520:0x52c]=b'\0__start\0_x\0'
    path=out/'two-symbols.o';path.write_bytes(two)
    primitive=m.bounded_macho(path,symbol_names=['__start','_x'])
    check('primitive result two real symbols',primitive['external_symbol_count']==2 and len(primitive['external_symbols'])==2 and json.loads(json.dumps(primitive))==primitive)
    baseline=descriptors()
    for api in ['items','values']:
        for state in ['partial','unstarted','exhausted','explicitly-closed']:
            before=descriptors()
            with m.macho_snapshot(path) as (snapshot,view):
                index=view['external_symbols'];directory=Path(index.temporary.name);iterator=getattr(index,api)()
                if state in ['partial','explicitly-closed']:next(iterator)
                if state=='exhausted':assert len(list(iterator))==2
                if state=='explicitly-closed':iterator.close()
            after=descriptors()
            check('actual FD closure '+api+' '+state,before==after and index.db is None and not index.cursors and not directory.exists(),dict(before=before,after=after))
            if state in ['partial','unstarted']:reject('escaped next '+api+' '+state,lambda:next(iterator))
            else:check('ended iterator no extra row '+api+' '+state,next(iterator,None) is None)
            reject('escaped get '+api+' '+state,lambda:index.get('__start'))
            reject('escaped len '+api+' '+state,lambda:len(index))
            iterator.close();index.close();index.close()
            check('idempotent cleanup '+api+' '+state,descriptors()==before)
    before=descriptors()
    with m.macho_snapshot(path) as (snapshot,view):
        index=view['external_symbols'];items=index.items();values=index.values();next(items);next(values)
        check('simultaneous real cursors tracked',len(index.cursors)==2)
    check('simultaneous actual FDs closed',descriptors()==before and not index.cursors)
    for name,iterator in [('items',items),('values',values)]:reject('simultaneous escaped '+name,lambda:next(iterator));iterator.close()
    for mode in ['body','own-SIGTERM','cleanup-only','body-and-cleanup','identity-and-cleanup']:
        before=descriptors();prior=signal.getsignal(signal.SIGTERM);body=RuntimeError('original review body');cleanup=RuntimeError('review cleanup error');seen=None;closed=[]
        class Failing:
            def close(self):closed.append('failing');raise cleanup
        class Remaining:
            def close(self):closed.append('remaining')
        try:
            with m.owned_cancellation():
                with m.macho_snapshot(path) as (snapshot,view):
                    index=view['external_symbols'];directory=Path(index.temporary.name);iterator=index.items();next(iterator)
                    if 'cleanup' in mode:
                        snapshot.own(Remaining());snapshot.own(Failing())
                    if mode in ['body','body-and-cleanup']:raise body
                    if mode=='own-SIGTERM':os.kill(os.getpid(),signal.SIGTERM)
                    if mode=='identity-and-cleanup':
                        with path.open('ab') as stream:stream.write(b'ACTUAL-GROWTH')
        except BaseException as error:seen=error
        check('all actual resources closed '+mode,descriptors()==before and snapshot.stream.closed and index.db is None and not index.cursors and not directory.exists())
        check('signal handlers restored '+mode,signal.getsignal(signal.SIGTERM)==prior)
        if mode in ['body','body-and-cleanup']:check('original exception identity '+mode,seen is body)
        if mode=='cleanup-only':check('cleanup only propagated',seen is cleanup and closed==['failing','remaining'])
        if mode=='body-and-cleanup':check('cleanup noted while body preserved',closed==['failing','remaining'] and any('review cleanup error' in n for n in body.__notes__))
        if mode=='identity-and-cleanup':
            check('identity primary cleanup secondary',isinstance(seen,ValueError) and closed==['failing','remaining'] and any('review cleanup error' in n for n in seen.__notes__))
            path.write_bytes(two)
        if mode=='own-SIGTERM':check('own actual cancellation nonpass',isinstance(seen,m.OwnedCancellation))
        reject('failed scope escaped iterator '+mode,lambda:next(iterator));iterator.close()
        observations.append(dict(mode=mode,observed_type=type(seen).__name__,notes=getattr(seen,'__notes__',[]),before=before,after=descriptors()))
    stage=ast.get_source_segment(SOURCE.read_text(),current['execute_link_stage_reserved'])
    check('unfinished result schema valid complete false',"outcome='inconclusive'" in stage and 'complete_link_product=False' in stage and "outcome='pass'" not in stage)
    check('productive and completion pins empty',m.LINK_PROFILE_PINS=={} and m.LINK_COMPLETION_PINS=={})
    check('final actual descriptor baseline',descriptors()==baseline,dict(before=baseline,after=descriptors()))
    check('old and final physical freezes unchanged',review.sha(SOURCE)==SOURCE_SHA and review.sha(PREVIOUS)=='0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464')
    result=dict(kind='host-test',origin='local-host',outcome='pass' if all(c['pass_'] for c in checks) else 'fail',task='REV-041',experiment='REVMAIN-003',source_only=True,
                checks=checks,failed=[c['name'] for c in checks if not c['pass_']],observations=observations,source=dict(path=str(SOURCE),sha256=review.sha(SOURCE)),
                producer_manifest=dict(path=str(pinpath),sha256=review.sha(pinpath),verified_count=len(pins)),initial_process=initial,final_process=m.proc_status(),
                descriptors_before=baseline,descriptors_after=descriptors(),elapsed_seconds=time.monotonic()-start,argv=sys.argv,script_sha256=review.sha(__file__),
                no_children_or_target_tools=True,no_production_grant=True,no_corpus_or_benchmark_repeat=True,previous_whole_matrix_not_repeated=True)
    result['artifact_hashes']={str(p.relative_to(out)):review.sha(p) for p in out.rglob('*') if p.is_file()}
    review.write(out/'evidence.json',result)
    print(json.dumps({k:result[k] for k in ['outcome','failed','elapsed_seconds','final_process']} | {'checks':len(checks)},indent=2))
    return 0 if result['outcome']=='pass' else 2


if __name__=='__main__':raise SystemExit(run(Path(sys.argv[1]).resolve()))
