#!/usr/bin/env python3
"""REVMAIN-002 focused independent real-FD/authority controls; no target child."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time
from types import SimpleNamespace
import review

AUTHOR = review.MAIN/'worktrees/vm-022-link-correction-20261106'
SOURCE = AUTHOR/'tools/build/avf_guest_link_inputs.py'
SOURCE_SHA = '0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464'


def descriptors():
    result = {}
    for path in Path('/proc/self/fd').iterdir():
        try:result[path.name] = str(path.readlink())
        except OSError:pass
    return result


def run(out):
    start = time.monotonic()
    out.mkdir(parents=True,exist_ok=False)
    assert review.sha(SOURCE) == SOURCE_SHA
    m = review.load(SOURCE,'independent_corrected_core')
    policy = review.MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
    assert review.sha(policy) == m.RUNNER_SHA
    common = review.load(policy,'explicit_historical_af193_review_only')
    checks = []
    def check(name,condition,detail=None):
        checks.append(dict(name=name,pass_=bool(condition),detail=detail))
    def reject(name,call,mutation=None):
        try:value=call()
        except (ValueError,OSError,struct.error,UnicodeError) as error:
            check(name,mutation is None or bool(mutation),dict(error=repr(error),mutation=mutation))
        else:check(name,False,dict(incorrectly_accepted=value,mutation=mutation))
    def file(name,data):
        path=out/name;path.write_bytes(data);return path

    pinfile=AUTHOR/'artifacts/avf-guest-link-inputs/link-correction-freeze-1/artifact-bindings.json'
    assert review.sha(pinfile)=='2d0e67b6e78e41afac5d9b7a9cc7819de750f840a9d3732ff5fc31cc3a3f10d6'
    pins=json.loads(pinfile.read_text())
    check('203 frozen producer artifacts unchanged',len(pins)==203 and all(
        review.sha(AUTHOR/'artifacts/avf-guest-link-inputs'/name)==digest for name,digest in pins.items()))
    check('aggregate source pin',review.sha(AUTHOR/'docs/procedures/avf-guest-link-inputs/link-correction-evidence.json')=='6a47ee966d0d07a5b2e808286d15b6e074c1621d84e5b25fa68f6cb385787237')
    old_tree=ast.parse(review.OLD.read_text());tree=ast.parse(SOURCE.read_text())
    nodes={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    for node in old_tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='main':
            check('inherited AST '+node.name,ast.dump(node)==ast.dump(nodes[node.name]))
    measured=AUTHOR/'artifacts/avf-guest-link-inputs/link-correction-large-1'
    measured_tree=ast.parse((measured/'avf_guest_link_inputs.py').read_text())
    def algorithm(t):
        result=[n for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ['SymbolIndex','symbol_name']]
        result += [n for n in ast.walk(t) if isinstance(n,ast.For) and ast.unparse(n.iter)=='range(nsyms)']
        return [ast.dump(n) for n in result]
    bindings=json.loads((measured/'bindings.json').read_text());large=json.loads((measured/'large-result.json').read_text())
    check('once measured compact algorithm exact AST no benchmark repeated',algorithm(tree)==algorithm(measured_tree)
          and bindings['exit_code']==0 and bindings['result_sha256']==review.sha(measured/'large-result.json')
          and bindings['fixture_sha256']==review.sha(measured/'legal-count-symbols.o') and large['outcome']=='pass'
          and large['symbols']==700000,large)

    image=file('image',review.macho());obj=file('object',review.macho(False))
    view=m.bounded_macho(image,image=True,symbol_names=['__start'])
    check('primitive image symbols and digest',json.loads(json.dumps(view))==view and view['sha256']==review.sha(image)
          and view['external_symbols']['__start']['value']==review.BASE+0x400)
    fds_before=descriptors();initial=m.proc_status()
    for name,kwargs in [('parent',dict(section_segment=b'__DATA')),('file-span',dict(section_offset=0x580)),
                        ('VM-file',dict(section_offset=0x420))]:
        reject('original invalid image '+name,lambda name=name,kwargs=kwargs:m.bounded_macho(file('bad-'+name,review.macho(**kwargs)),image=True))
    zero=bytearray(review.macho());struct.pack_into('<I',zero,168,1)
    reject('file backed entry rejects zerofill',lambda:m.bounded_macho(file('zero-entry',zero),image=True))
    tail=bytearray(zero);struct.pack_into('<Q',tail,136,review.BASE+0x900)
    struct.pack_into('<Q',tail,0x500+8,review.BASE+0x900);struct.pack_into('<Q',tail,32+176+16+32*8,review.BASE+0x900)
    reject('file backed entry rejects executable virtual tail',lambda:m.bounded_macho(file('tail-entry',tail),image=True))

    # Mutations occur after actual parsing, before actual retained-FD digest.
    real_digest=m.CoherentFile.digest
    for kind,body,parse in [('image',review.macho(),lambda p:m.bounded_macho(p,image=True)),
                            ('archive',review.archive([('a.o',b'a'),('b.o',b'bb')]),m.stream_archive),
                            ('XNUP',review.xnup(image.read_bytes()),lambda p:m.inspect_xnup(p,view))]:
        for change in ['grow','shrink','equal-swap','changed-swap','symlink-retain-inode','same-size-write']:
            victim=file(kind+'-'+change,body);replacement=file(kind+'-'+change+'-replacement',body if change=='equal-swap' else b'non-format')
            fired=[]
            def mutated(snapshot):
                if snapshot.path==victim and not fired:
                    fired.append(change)
                    if change=='grow':
                        with victim.open('ab') as stream:stream.write(b'REAL-TRAILER')
                    elif change=='shrink':
                        with victim.open('r+b') as stream:stream.truncate(len(body)-1)
                    elif change=='same-size-write':
                        with victim.open('r+b') as stream:stream.write(bytes([body[0]^1]))
                    elif change=='symlink-retain-inode':
                        retained=out/(victim.name+'-retained');victim.rename(retained);victim.symlink_to(retained.name)
                    else:os.replace(replacement,victim)
                return real_digest(snapshot)
            m.CoherentFile.digest=mutated
            try:reject('real digest closure '+kind+' '+change,lambda:parse(victim),fired)
            finally:m.CoherentFile.digest=real_digest
    symlink=out/'initial-symlink';symlink.symlink_to(obj.name)
    reject('initial nofollow',lambda:m.bounded_macho(symlink))
    check('baseline exact transform',m.verify_segment_processing(obj,file('transformed',obj.read_bytes()),[])==[])
    real_init=m.CoherentFile.__init__
    for side in ['original','result']:
        for change in ['grow','shrink','equal-swap','symlink-retain-inode']:
            original=file('transform-'+side+'-'+change+'-original',review.macho(False))
            result=file('transform-'+side+'-'+change+'-result',original.read_bytes())
            victim=original if side=='original' else result;replacement=file(victim.name+'-replacement',victim.read_bytes());fired=[]
            def mutated_init(snapshot,path):
                real_init(snapshot,path)
                # For original, mutate second open (the parsed FD has closed).
                if Path(path)==victim:
                    fired.append('open')
                    target_number=2 if side=='original' else 1
                    if len(fired)==target_number:
                        if change=='grow':
                            with victim.open('ab') as stream:stream.write(b'REAL-TRAILER')
                        elif change=='shrink':
                            with victim.open('r+b') as stream:stream.truncate(64)
                        elif change=='equal-swap':os.replace(replacement,victim)
                        else:
                            retained=out/(victim.name+'-retained');victim.rename(retained);victim.symlink_to(retained.name)
            m.CoherentFile.__init__=mutated_init
            try:reject('actual transform closure '+side+' '+change,lambda:m.verify_segment_processing(original,result,[]),fired)
            finally:m.CoherentFile.__init__=real_init

    # Two rows leave a partially consumed SQLite cursor, testing context-owned
    # cleanup even when a borrowed iterator remains referenced by the caller.
    two=bytearray(review.macho(False));struct.pack_into('<4I',two,32+152+8,0x500,2,0x520,12)
    struct.pack_into('<IBBHQ',two,0x510,9,0xf,1,0,0x408);two[0x520:0x52c]=b'\0__start\0_x\0'
    two_path=file('two-symbols',two)
    for api in ['items','values']:
        before=descriptors()
        with m.macho_snapshot(two_path) as (snapshot,borrowed):
            index=borrowed['external_symbols'];dbdir=index.temporary.name
            iterator=getattr(index,api)();first=next(iterator)
        after=descriptors()
        check('retained partial '+api+' iterator closes all context SQLite FDs',before==after,
              dict(before=before,after=after,temporary_directory_removed=not Path(dbdir).exists(),first=first))
        iterator.close()
        check('explicit caller iterator cleanup leaves no FD',descriptors()==before)
    for reason in ['exception','cancel']:
        before=descriptors();prior=signal.getsignal(signal.SIGTERM);index=None
        try:
            with m.owned_cancellation():
                with m.macho_snapshot(two_path) as (snapshot,borrowed):
                    index=borrowed['external_symbols'];dbdir=index.temporary.name
                    if reason=='cancel':os.kill(os.getpid(),signal.SIGTERM)
                    else:raise RuntimeError('review-only borrowed-scope exception')
        except (RuntimeError,m.OwnedCancellation):pass
        check('index cleanup on '+reason,index.db is None and not Path(dbdir).exists()
              and descriptors()==before and signal.getsignal(signal.SIGTERM)==prior)
    with m.macho_snapshot(two_path) as (snapshot,borrowed):
        check('raw nlist original ordinal',m.macho_symbol(snapshot,borrowed,1)['name']=='_x')
        reject('raw nlist ordinal lower bound',lambda:m.macho_symbol(snapshot,borrowed,-1))
        reject('raw nlist ordinal upper bound',lambda:m.macho_symbol(snapshot,borrowed,2))
        reject('range 1MiB convenience bound',lambda:snapshot.read_range(0,1024**2+1))
        reject('range negative offset',lambda:snapshot.read_range(-1,1))
    duplicate=bytearray(two);struct.pack_into('<I',duplicate,0x510,1)
    reject('conflicting symbol exact index',lambda:m.bounded_macho(file('conflicting-symbol',duplicate)))

    rows=common.load_project(review.MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json',common.PIN)
    row=rows[0];shard=next(iter(common.SHARDS));task=dict(id='REVIEW-ONLY',owner='fixture-owner',paths=[
        'fixtures/public/avf-object-shards/'+shard,'docs/procedures/avf-object-shards/'+shard])
    provenance=dict(manifest_sha256=common.PIN,namespace_sha256='FIXTURE',compiler=dict(path=row['next_owned_compile_argv_template'][0],sha256=common.COMPILER))
    key=common.canonical(dict(provenance=provenance,id=row['id'],source=row['bound_source_sha256'],configuration=row['configuration_sha256'],recipe=common.canonical(row['next_owned_compile_argv_template'])))
    raw=dict(kind='host-test',origin='local-host',source_only=False,compiler_started=True,resource_profile='project-budget-v1',resource_qualification='pass',executor_sha256='FIXTURE',shard=shard,provenance=provenance,
             ownership_binding=dict(task=task['id'],owner=task['owner'],mode='execute',source_only_tooling_exception=False,literal_task_paths=task['paths'],requested_shard=shard,authorized_shards=[shard]),
             execution_approval=dict(task=task['id'],owner=task['owner'],shard=shard,reviewed_executor_sha256='FIXTURE',runner_reviewed=True,root_lease='FICTIONAL-NOT-A-GRANT'))
    execution=dict(schema_version=1,shard=shard,provenance=provenance,selected=[dict(id=row['id'],input_key=key)])
    record=dict(input_key=key,command=dict(child_started=True));profile=dict(manifest=dict(sha256=common.PIN),namespace_sha256='FIXTURE')
    check('actual historical literal/key derivation baseline fixture',m.producer_identity(raw,execution,record,row,profile,dict(tasks=[task]),common) is None)
    for change in ['owner','task','reservations','authority-paths','source-only','compiler-never-started','raw-compiler','plan-compiler','forged-key','grant-owner','child-never-started','future046']:
        r,e,c,p,t=copy.deepcopy((raw,execution,record,profile,task))
        if change=='owner':r['ownership_binding']['owner']='foreign'
        elif change=='task':r['ownership_binding']['task']='VM-039'
        elif change=='reservations':r['ownership_binding']['literal_task_paths']=[]
        elif change=='authority-paths':t['paths']=r['ownership_binding']['literal_task_paths']=[]
        elif change=='source-only':r['source_only']=True
        elif change=='compiler-never-started':r['compiler_started']=False
        elif change=='raw-compiler':r['provenance']['compiler']['sha256']='0'*64
        elif change=='plan-compiler':e['provenance']=copy.deepcopy(e['provenance']);e['provenance']['compiler']['sha256']='0'*64
        elif change=='forged-key':e['selected'][0]['input_key']=c['input_key']='FORGED'
        elif change=='grant-owner':r['execution_approval']['owner']='foreign'
        elif change=='child-never-started':c['command']['child_started']=False
        else:
            p['manifest']['sha256']='FUTURE046';r['provenance']['manifest_sha256']='FUTURE046'
        reject('original receipt guard '+change,lambda:m.producer_identity(r,e,c,row,p,dict(tasks=[t]),common))

    check('production and completion pins empty',m.LINK_PROFILE_PINS=={} and m.LINK_COMPLETION_PINS=={})
    receipt=dict(schema='avf-guest-link-result-v2',phase='guest-link-stage',kind='host-test',origin='local-host',task='VM-022',owner=m.OWNER,outcome='pass',source_only=False,direct_link_command_started=True,archive_command_started=True,complete_link_product=True,resource_profile='project-budget-v1',guest_executed=False,profile=profile)
    reject('typed product no profile',lambda:m.require_link_receipt(receipt,common))
    try:
        m.LINK_PROFILE_PINS[common.PIN]=profile
        reject('typed product no completion',lambda:m.require_link_receipt(receipt,common))
    finally:m.LINK_PROFILE_PINS.clear()
    for field,value in [('schema','wrong'),('task','OTHER'),('owner','OTHER'),('source_only',True),('outcome','incomplete'),('complete_link_product',False),('direct_link_command_started',False),('archive_command_started',False)]:
        reject('typed receipt rejects '+field,lambda field=field,value=value:m.require_link_receipt({**receipt,field:value},common))
    stage=ast.get_source_segment(SOURCE.read_text(),nodes['execute_link_stage_reserved'])
    check('core never claims completed allocator/runtime product',"outcome='pass'" not in stage and "outcome='incomplete'" in stage and 'allocator_retention_qualified=False' in stage)
    check('typed receipt before package approval',ast.get_source_segment(SOURCE.read_text(),nodes['execute_xnup_reserved']).index('require_link_receipt(')<ast.get_source_segment(SOURCE.read_text(),nodes['execute_xnup_reserved']).index('common.project_approval('))
    check('profile and completion pins restored',m.LINK_PROFILE_PINS=={} and m.LINK_COMPLETION_PINS=={})
    check('inspection descriptors return to baseline',descriptors()==fds_before,dict(before=fds_before,after=descriptors()))
    check('both old and corrected source freezes unchanged',review.sha(SOURCE)==SOURCE_SHA and review.sha(review.SOURCE)==review.SOURCE_SHA)
    evidence=dict(kind='host-test',origin='local-host',task='REV-041',experiment='REVMAIN-002',source_only=True,
                  outcome='pass' if all(x['pass_'] for x in checks) else 'fail',checks=checks,failed=[x['name'] for x in checks if not x['pass_']],
                  source=dict(path=str(SOURCE),sha256=review.sha(SOURCE)),historical_review_only_policy=dict(path=str(policy),sha256=review.sha(policy)),
                  producer_manifest=dict(path=str(pinfile),sha256=review.sha(pinfile),verified_count=len(pins)),
                  initial_process=initial,final_process=m.proc_status(),elapsed_seconds=time.monotonic()-start,
                  no_target_tools=True,no_production_grant=True,no_unchanged_benchmark_repeat=True,actual_reads_bypassed=False,
                  actual_cancel_signal_target='own reviewer Python PID only',argv=sys.argv,script_sha256=review.sha(__file__))
    evidence['artifacts_sha256']={str(p.relative_to(out)):review.sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    review.write(out/'evidence.json',evidence)
    print(json.dumps({k:evidence[k] for k in ['outcome','failed','elapsed_seconds','final_process']} | {'checks':len(checks)},indent=2))
    return 0 if evidence['outcome']=='pass' else 2


if __name__=='__main__':raise SystemExit(run(Path(sys.argv[1]).resolve()))
