#!/usr/bin/env python3
"""Focused actual Python/file controls; never invoke target tools."""
import argparse
import ast
import copy
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT.parents[1]
SOURCE = ROOT/'tools/build/avf_guest_link_inputs.py'
REVIEW = MAIN/'worktrees/rev-vm022-link-eu-20261106/docs/reviews/vm-022-link/review.py'
REVIEW_SHA = 'd9aa067d856bdf9f06e73e4a5b4d56a77f138eca413d8c71868df7aced5e505d'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def load(path,name):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def write(path,data):Path(path).write_text(json.dumps(data,indent=2)+'\n')

def large(out):
    resource.setrlimit(resource.RLIMIT_AS,(192*1024**2,192*1024**2))
    m = load(SOURCE,'large_corrected')
    count = 700_000;path = out/'legal-count-symbols.o';symoff = 56;stroff = symoff+count*16
    with path.open('xb') as stream:
        stream.write(struct.pack('<8I',0xfeedfacf,0x100000c,0,1,1,24,0,0))
        stream.write(struct.pack('<6I',2,24,symoff,count,stroff,1+count*9))
        for low in range(0,count,4096):
            stream.write(b''.join(struct.pack('<IBBHQ',1+i*9,3,0,0,i+1) for i in range(low,min(low+4096,count))))
        stream.write(b'\0')
        for low in range(0,count,4096):
            stream.write(b''.join(('_%07d'%i).encode()+b'\0' for i in range(low,min(low+4096,count))))
    start=time.monotonic();result={'outcome':'fail'}
    try:
        with m.macho_snapshot(path) as (snapshot,view):
            assert len(view['external_symbols']) == count
            assert all(view['external_symbols']['_%07d'%i]['value']==i+1 for i in (0,1,349999,699999))
            assert view['sha256']==sha(path)
        result.update(outcome='pass',symbols=count)
    except Exception as error:result['error']=repr(error)
    result.update(file_size=path.stat().st_size,elapsed_seconds=time.monotonic()-start,
                  address_space_limit_bytes=192*1024**2,current_image_memory=m.proc_status())
    write(out/'large-result.json',result)
    return 0 if result['outcome']=='pass' else 2

def run(out, large_evidence=None):
    out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='fail',source_only=True,
        checks=[],executor_sha256=sha(SOURCE),target_tools_executed=False,production_pins_rebound=False)
    try:
        assert sha(REVIEW)==REVIEW_SHA
        fixture=load(REVIEW,'review_fixture_constructors_only')
        m=load(SOURCE,'corrected_link')
        policy=MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
        assert sha(policy)==m.RUNNER_SHA
        common=load(policy,'historical_review_only_af193_no_production_override')
        initial=m.proc_status();fds_before=len(os.listdir('/proc/self/fd'))
        def check(name,condition):
            if not condition:raise AssertionError(name)
            report['checks'].append(name)
        def reject(name,call):
            try:call()
            except (ValueError,OSError,struct.error,UnicodeError):report['checks'].append(name);return
            raise AssertionError('Not rejected: '+name)
        def file(name,data):
            path=out/name;path.write_bytes(data);return path
        image=file('image',fixture.macho());obj=file('object',fixture.macho(False))
        view=m.bounded_macho(image,image=True)
        check('valid image digest and entry from same real FD',view['sha256']==sha(image) and view['entry']==fixture.BASE+0x400)
        check('ordinary parser returns only JSON primitives',bool(json.dumps(view)))
        with m.macho_snapshot(image,image=True) as (snapshot,borrowed):
            index=borrowed['external_symbols']
            check('borrowed exact raw nlist ordinal and range API',m.macho_symbol(snapshot,borrowed,0)['name']=='__start' and snapshot.read_range(0,4)==bytes.fromhex('cffaedfe'))
        check('borrowed symbol store closes at snapshot exit',index.db is None)
        check('closed046 profile and completion pins',m.LINK_PROFILE_PINS=={} and m.LINK_COMPLETION_PINS=={})
        before={n.name:ast.dump(n) for n in ast.parse((MAIN/'worktrees/vm-022-tail-cancellation-20261106/tools/build/avf_guest_link_inputs.py').read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name!='main'}
        after={n.name:ast.dump(n) for n in ast.parse(SOURCE.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        check('all inherited tail and cancellation AST unchanged',all(after[k]==v for k,v in before.items()))
        for name,kwargs in [('parent',dict(section_segment=b'__DATA')),('span',dict(section_offset=0x580)),('mapping',dict(section_offset=0x420))]:
            reject('image section '+name,lambda kwargs=kwargs,name=name:m.bounded_macho(file('bad-'+name,fixture.macho(**kwargs)),image=True))
        zero=bytearray(fixture.macho());struct.pack_into('<I',zero,32+72+64,1)
        reject('entry section cannot be zero-fill',lambda:m.bounded_macho(file('zero-entry',zero),image=True))
        real_digest=m.CoherentFile.digest
        for format_name,body,parse in [('macho',fixture.macho(),lambda p:m.bounded_macho(p,image=True)),
                                     ('xnup',fixture.xnup(b'x'),lambda p:m.inspect_xnup(p,dict(file_size=1,sha256=hashlib.sha256(b'x').hexdigest()))),
                                     ('archive',fixture.archive([('one.o',b'x')]),m.stream_archive)]:
            for mutation in ['grow','shrink','same-inode-swap','changed-inode-swap','symlink-swap']:
                victim=file(format_name+'-'+mutation,body)
                replacement=file(format_name+'-'+mutation+'-replacement',body if mutation=='same-inode-swap' else b'wrong-format-real-bytes')
                fired=[]
                def mutated(snapshot):
                    if snapshot.path==victim and not fired:
                        fired.append(True)
                        if mutation=='grow':
                            with victim.open('ab') as stream:stream.write(b'19-byte-real-trailer')
                        elif mutation=='shrink':
                            with victim.open('r+b') as stream:stream.truncate(len(body)-1)
                        elif mutation=='symlink-swap':
                            victim.unlink();victim.symlink_to(replacement)
                        else:os.replace(replacement,victim)
                    return real_digest(snapshot)
                m.CoherentFile.digest=mutated
                try:reject(format_name+' coherent FD '+mutation,lambda:parse(victim))
                finally:m.CoherentFile.digest=real_digest
                check(format_name+' mutation actually occurred '+mutation,bool(fired))
        symlink=out/'initial-symlink';symlink.symlink_to(obj)
        reject('initial symlink cannot be inspection source',lambda:m.bounded_macho(symlink))
        transformed=file('transform-baseline',obj.read_bytes())
        check('real unchanged transform positive',m.verify_segment_processing(obj,transformed,[])==[])
        real_init=m.CoherentFile.__init__
        for mutation in ['grow','shrink','swap']:
            target=file('transform-'+mutation,obj.read_bytes());replacement=file('transform-'+mutation+'-replacement',obj.read_bytes())
            fired=[]
            def mutated_init(snapshot,path):
                real_init(snapshot,path)
                if Path(path)==target and not fired:
                    fired.append(True)
                    if mutation=='grow':
                        with target.open('ab') as stream:stream.write(b'UNVALIDATED-TRAILER!')
                    elif mutation=='shrink':
                        with target.open('r+b') as stream:stream.truncate(100)
                    else:os.replace(replacement,target)
            m.CoherentFile.__init__=mutated_init
            try:reject('transform real post-open '+mutation,lambda:m.verify_segment_processing(obj,target,[]))
            finally:m.CoherentFile.__init__=real_init
            check('transform mutation actually occurred '+mutation,bool(fired))
        fake=dict(schema='fictional',task='OTHER',outcome='pass',source_only=True,image=dict(path=str(image),sha256=sha(image)))
        for name,patch in [('wrong-schema',{}),('wrong-task',{'schema':'avf-guest-link-result-v2'}),('source-only',{'schema':'avf-guest-link-result-v2','task':'VM-022'})]:
            reject('typed package receipt '+name,lambda patch=patch:m.require_link_receipt({**fake,**patch},None))
        full=dict(schema='avf-guest-link-result-v2',phase='guest-link-stage',kind='host-test',origin='local-host',task='VM-022',owner=m.OWNER,
                  outcome='pass',source_only=False,direct_link_command_started=True,archive_command_started=True,complete_link_product=True,
                  resource_profile='project-budget-v1',guest_executed=False,profile={'manifest':{'sha256':'unaccepted'}})
        reject('plausible receipt cannot bypass empty source-profile gate',lambda:m.require_link_receipt(full,None))
        for field in ['direct_link_command_started','archive_command_started','complete_link_product']:
            reject('receipt requires actual '+field,lambda field=field:m.require_link_receipt({**full,field:False},None))
        # New literal/provenance helper uses the actual unchanged common API.
        policy=MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
        check('historical review-only physicalAF193 API source bound',sha(policy)==m.RUNNER_SHA)
        report['historical_review_only_api_source']=dict(path=str(policy),sha256=sha(policy),production_fallback=False)
        rows=common.load_project(MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json',common.PIN)
        row=rows[0];task=dict(id='FIXTURE-ORIGINAL',owner='fixture-owner',paths=['fixtures/public/avf-object-shards/osfmk','docs/procedures/avf-object-shards/osfmk'])
        shard=next(iter(common.SHARDS))
        task['paths']=['fixtures/public/avf-object-shards/'+shard,'docs/procedures/avf-object-shards/'+shard]
        provenance=dict(manifest_sha256=common.PIN,namespace_sha256='fixture-namespace',compiler=dict(path=row['next_owned_compile_argv_template'][0],sha256=common.COMPILER))
        key=common.canonical(dict(provenance=provenance,id=row['id'],source=row['bound_source_sha256'],configuration=row['configuration_sha256'],recipe=common.canonical(row['next_owned_compile_argv_template'])))
        raw=dict(kind='host-test',origin='local-host',source_only=False,compiler_started=True,resource_profile='project-budget-v1',resource_qualification='pass',
                 executor_sha256='fixture-executor',shard=shard,provenance=provenance,
                 ownership_binding=dict(task=task['id'],owner=task['owner'],mode='execute',source_only_tooling_exception=False,
                     literal_task_paths=task['paths'],requested_shard=shard,authorized_shards=[shard]),
                 execution_approval=dict(task=task['id'],owner=task['owner'],shard=shard,reviewed_executor_sha256='fixture-executor',runner_reviewed=True,root_lease='fixture-only-never-granted'))
        execution=dict(schema_version=1,shard=shard,provenance=provenance,selected=[dict(id=row['id'],input_key=key)])
        record=dict(input_key=key,command=dict(child_started=True));profile=dict(manifest=dict(sha256=common.PIN),namespace_sha256='fixture-namespace')
        check('real common key and literal-reservation derivation fixture only',m.producer_identity(raw,execution,record,row,profile,dict(tasks=[task]),common) is None)
        for case in ['owner','task','reservations','source-only','compiler-started','raw-compiler','plan-compiler','forged-key']:
            r,e,c=copy.deepcopy((raw,execution,record))
            if case=='owner':r['ownership_binding']['owner']='foreign'
            elif case=='task':r['ownership_binding']['task']='VM-039'
            elif case=='reservations':r['ownership_binding']['literal_task_paths']=[]
            elif case=='source-only':r['source_only']=True
            elif case=='compiler-started':r['compiler_started']=False
            elif case=='raw-compiler':r['provenance']['compiler']['sha256']='0'*64
            elif case=='plan-compiler':e['provenance']['compiler']['sha256']='0'*64
            else:e['selected'][0]['input_key']=c['input_key']='mutually-forged'
            reject('literal original producer rejects '+case,lambda r=r,e=e,c=c:m.producer_identity(r,e,c,row,profile,dict(tasks=[task]),common))
        tree=ast.parse(SOURCE.read_text())
        stage=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute_link_stage_reserved')
        check('no complete product pass emitted before allocator/runtime qualification',"outcome='pass'" not in ast.get_source_segment(SOURCE.read_text(),stage))
        if large_evidence:
            bindings=json.loads((large_evidence/'bindings.json').read_text())
            result=json.loads((large_evidence/'large-result.json').read_text())
            def symbol_algorithm(path):
                tree=ast.parse(path.read_text())
                nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ['SymbolIndex','symbol_name']]
                loops=[n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.iter,ast.Call) and ast.unparse(n.iter)=='range(nsyms)']
                return [ast.dump(n) for n in [*nodes,*loops]]
            check('reuse exact prior measured unchanged compact symbol algorithm without repeat',
                  symbol_algorithm(SOURCE)==symbol_algorithm(large_evidence/'avf_guest_link_inputs.py') and bindings['exit_code']==0 and
                  bindings['result_sha256']==sha(large_evidence/'large-result.json') and
                  bindings['fixture_sha256']==sha(large_evidence/'legal-count-symbols.o') and
                  result['outcome']=='pass' and result['symbols']==700000)
            report['prior_large_bindings']=dict(path=str(large_evidence/'bindings.json'),sha256=sha(large_evidence/'bindings.json'))
        else:
            process=subprocess.run([sys.executable,'-s',str(Path(__file__).resolve()),'--out',str(out),'--large'],capture_output=True,text=True,timeout=90,start_new_session=True,
                                   env={**os.environ,'LC_ALL':'C','PYTHONUTF8':'1','PYTHONNOUSERSITE':'1'})
            write(out/'large-process.json',dict(argv=process.args,exit_code=process.returncode,stdout=process.stdout,stderr=process.stderr))
            result=json.loads((out/'large-result.json').read_text())
            check('valid700k symbols under192MiB AS no MemoryError',process.returncode==0 and result['outcome']=='pass' and result['symbols']==700000)
        report['large_result']=result
        gc.collect()
        report['fds_before']=fds_before
        report['fds_after_count']=len(os.listdir('/proc/self/fd'))
        report['fds_after']={}
        for descriptor in Path('/proc/self/fd').iterdir():
            try:report['fds_after'][descriptor.name]=str(descriptor.readlink())
            except OSError:pass
        check('no inspection FD leaks',len(os.listdir('/proc/self/fd'))==fds_before)
        report.update(outcome='pass',initial_process=initial,final_process=m.proc_status(),review_constructor_source=dict(path=str(REVIEW),sha256=REVIEW_SHA))
    except Exception as error:report['error']=repr(error)
    report['artifacts_sha256']={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'evidence.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='artifacts_sha256'},indent=2))
    return 0 if report['outcome']=='pass' else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--large',action='store_true');parser.add_argument('--large-evidence',type=Path)
    args=parser.parse_args()
    raise SystemExit(large(args.out) if args.large else run(args.out.resolve(),args.large_evidence.resolve() if args.large_evidence else None))
