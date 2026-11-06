#!/usr/bin/env python3
"""One fixed native four-tail stage; borrow accepted admission and guards."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[3]
BASE = WT/'artifacts/e1s-native-tails/plan-1/execution-plan.json'
BASE_SHA = 'e96eb5986af804a2e7018eb534d149d0c10691e8f82bccaf3cfa3a899b3908ca'
OUT = WT/'artifacts/e1s-native-tails/execute-2'
VIEW = WT/'artifacts/e1s-native-tails/plan-2/namespace-cwd'
NATIVE = MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py'
NATIVE_SHA = '2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f'
COMMON = MAIN/'tools/build/avf_kernel_objects.py'
COMMON_SHA = '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'
IDS = ['kernel/nonlto.o','kernel/version.o','kernel/lastkerneldataconst.o','kernel/lastkernelconstructor.o']


def helpers():
    # Native module import defines functions only. Never call its component
    # derive/execute, replace its globals or adopt its AVF/profile identities.
    import hashlib
    import importlib.util
    with NATIVE.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=NATIVE_SHA:
            raise ValueError('Changed accepted native helper')
    spec = importlib.util.spec_from_file_location('tail_native_guards',NATIVE)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    return native, native.module(COMMON,COMMON_SHA,'tail_common')


def ownership(common, plan, executing=False):
    ledger = common.load_project(MAIN/'state/lab.json')
    task = next(t for t in ledger['tasks'] if t['id']=='STR-021')
    if task['status']!='in_progress' or task['owner']!=plan['owner']:
        raise ValueError('Original active SR21 owner required')
    worktree = Path(task['worktree'])
    if not worktree.is_absolute(): worktree = MAIN/worktree
    if worktree!=WT or common.canonical_output_path(OUT)!=OUT:
        raise ValueError('Wrong owned physical tail worktree/output')
    if executing and (task['scope']!='host' or task['evidence_kind']!='host-test' or not any(
        e['id']==plan['experiment'] and e['task']=='STR-021' and e['owner']==plan['owner'] and e['status']=='planned'
        for e in ledger['experiments'])):
        raise ValueError('Exact original-owner planned host experiment required')


def derive(native, common):
    base = common.load_project(BASE,BASE_SHA)
    native.require([r['id'] for r in base['compile_commands']]==IDS,'Exactly four native tails required')
    inputs = dict(base['input_bindings'])
    inputs.update({str(BASE):BASE_SHA,str(NATIVE):NATIVE_SHA,str(Path(__file__)):native.digest(__file__)})
    sc = common.load_project(base['derived_source_context']['path'],base['derived_source_context']['sha256'])
    manifest = common.load_project(sc['source_manifest'],sc['source_manifest_sha256'])
    inputs.update({str(Path(sc['source_root'])/p):h for p,h in manifest.items()})
    metadata_path = NATIVE.parent/'source-metadata.json'
    metadata = common.load_project(metadata_path,native.SOURCE_METADATA_SHA)
    native.require(metadata['root']==str(Path(sc['source_root'])/'.git'),'Wrong fixed native metadata')
    inputs[str(metadata_path)] = native.SOURCE_METADATA_SHA
    inputs.update(metadata['files'])
    runtime_path = NATIVE.parent/'runtime.json'
    runtime = common.load_project(runtime_path,native.RUNTIME_SHA)
    inputs[str(runtime_path)] = native.RUNTIME_SHA
    inputs.update(runtime['files'])
    native.require(VIEW.is_dir() and not VIEW.is_symlink() and not list(VIEW.iterdir()),'Exact empty namespace view required')
    rows = []
    cwd = OUT/'cwd/kernel'
    for source in base['compile_commands']:
        argv = list(source['argv'])
        obj = OUT/'objects/kernel'/source['target']
        dep = OUT/'md/kernel'/(source['target'][:-2]+'.d')
        native.require('-o' not in argv and argv.count('-MF')==1,'Original tail output semantics changed')
        argv[argv.index('-MF')+1] = str(dep)
        argv += ['-o',str(obj)]
        rows.append(dict(id=source['id'],target=source['target'],namespace_cwd=str(VIEW),cwd=str(cwd),
            source=source['source']['path'],source_sha256=source['source']['sha256'],argv=argv,
            object=str(obj),depfile=str(dep),original_argv=source['original_compiler_argv'],
            static_plan_argv=source['argv']))
    elf_path = WT/'artifacts/e1s-native-tails/plan-2/setsegname-ELF.json'
    elf = common.load_project(elf_path,'a9648e98c4d41323246af03d97466381dca6395355546ecaa785031317dd717f')
    inputs[str(elf_path)] = native.digest(elf_path)
    for kind in ['stdout','stderr']:
        inputs[elf[kind]['path']] = elf[kind]['sha256']
    native.require(elf['observed_DT_NEEDED']==['libc.so.6'] and elf['observed_RUNPATH'] is None,'Wrong genuine setsegname runtime')
    tool = base['postprocess']['argv'][0]
    tool_runtime = dict(runtime,compiler={'path':tool,'sha256':inputs[tool]},
        loaded={name:path for name,path in runtime['loaded'].items() if name in ['libc.so.6','ld-linux-x86-64.so.2']},compiler_literal_runpath='')
    transform = dict(base['postprocess'])
    transform['cwd'] = str(cwd)
    transform['argv'] = [tool,'-s','__DATA','-n','__LASTDATA_CONST','-o',str(OUT/'objects/kernel/lastkernelconstructor.o__'),rows[-1]['object']]
    transform['raw_snapshot_before'] = str(OUT/'raw/lastkernelconstructor.o')
    transform['rename_only_after_exit0'] = {'source':transform['argv'][-2],'destination':rows[-1]['object']}
    absent = [r['path'] for c in base['compile_commands'] for r in c['path_operands'] if r['status']=='explicit-absent-search-directory']
    plan = dict(schema='e1s-native-four-tails-caller-plan-v1',resource_profile='project-budget-v1',task='STR-021',
        owner=base['owner'],experiment=base['experiment'],shard=base['shard'],out=str(OUT),
        executor_sha256=native.digest(__file__),whole_seconds=600,max_jobs=1,max_owned_rss_bytes=512*1024**2,
        static_tail_plan={'path':str(BASE),'sha256':BASE_SHA},commands=rows,postprocess=transform,
        accepted_native_helper={'path':str(NATIVE),'sha256':NATIVE_SHA},inputs=inputs,projections={},
        absent_inputs=sorted(set(absent)),runtime=runtime,nonsource_metadata=metadata,
        runtime_lookup={str(cwd):native.runtime_lookup(runtime,str(cwd))},
        loader_commands={str(cwd):[runtime['interpreter'],'--list',runtime['compiler']['path']]},
        transform_runtime=tool_runtime,transform_runtime_lookup=native.runtime_lookup(tool_runtime,str(cwd)),
        transform_loader_command=[runtime['interpreter'],'--list',tool],
        namespace_view={'path':str(VIEW),'meaning':'Empty accepted top-level kernel configuration projection; no source/context mutation'},
        actual_outputs_measured=False,execution_authority=False,external_root_watchdog_required=True)
    ownership(common,plan)
    plan['namespace'] = native.native_namespace(common,plan)
    verify(native,common,plan)
    return plan


def verify(native, common, plan):
    native.verify(common,plan)
    native.require(not list(VIEW.iterdir()),'Empty namespace view gained shadow files')
    native.require(native.runtime_lookup(plan['transform_runtime'],plan['commands'][0]['cwd'])==plan['transform_runtime_lookup'],
        'Native section-tool runtime search changed')


def object_facts(core, path):
    with core.macho_snapshot(path) as (snapshot,view):
        symbols=view['external_symbols']
        if len(symbols)>4096:
            raise ValueError('Unexpected symbol cardinality for four fixed tiny native sources')
        return {**view,'external_symbol_count':len(symbols),'external_symbols':dict(symbols.items()),'sha256':snapshot.digest()}


def execute(native, common, plan, source_path, source_sha, approval_path, approval_sha):
    native.require(common.load_project(source_path,source_sha)==plan,'Reviewed exact tail plan changed')
    ownership(common,plan,True)
    args = SimpleNamespace(main=MAIN,out=OUT,**{k:plan[k] for k in ['task','owner','experiment','shard']})
    approval = common.load_project(approval_path,approval_sha)
    native.require(approval['source_plan_sha256']==source_sha,'Wrong tail source-plan approval')
    budget = common.project_approval(args,approval,executor_path=Path(__file__))
    native.require(budget.source_plan==plan and budget.rss_limit==512*1024**2 and budget.allocation['max_compiler_jobs_total']==6,
        'Exact native one-job512MiB/six-total allocation required')
    core = native.module(*native.PINS[1],'tail_cleanup')
    supervise = native.module(*native.PINS[2],'tail_supervise')
    started = time.monotonic(); reserved = False
    report = dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=common.stamp(),task='STR-021',
        owner=plan['owner'],experiment=plan['experiment'],source_plan_sha256=source_sha,executor_sha256=native.digest(__file__),
        commands=[],objects=[],full_kernel_qualified=False,hardware_execution=False)
    with core.owned_cancellation() as cancel:
        try:
            with cancel.cleanup():
                budget.reserve(); reserved=True
            cancel.check(); ownership(common,plan,True); verify(native,common,plan)
            native.require(not OUT.exists() and not OUT.is_symlink(),'Fresh tail output required; no resume')
            OUT.mkdir(parents=True,exist_ok=False); native.write(OUT/'execution-plan.json',plan)
            Path(plan['commands'][0]['cwd']).mkdir(parents=True)
            native.private_inputs(plan)
            def run(argv,label,seconds=120,role=None):
                cancel.check(); verify(native,common,plan); native.private_inputs(plan)
                remaining = 600-(time.monotonic()-started)
                native.require(remaining>0,'Whole native tail deadline')
                with cancel.command(budget):
                    result = common.run_child(argv,Path(plan['commands'][0]['cwd']),OUT,label,supervise,
                        timeout=min(seconds,remaining),admit=True,budget=budget)
                    report['commands'].append(dict(role=role or label,process=result))
                cancel.check()
                native.require(result.get('outcome')=='pass' and result.get('resource_qualification')=='pass','Stop after failed/deferred tail child:'+label)
                return result
            cwd = plan['commands'][0]['cwd']
            run(plan['loader_commands'][cwd],'compiler-loader')
            native.loader_mapping((OUT/'compiler-loader.stdout.txt').read_text(),plan['runtime'])
            for number,row in enumerate(plan['commands']):
                for p in [row['object'],row['depfile']]:
                    Path(p).parent.mkdir(parents=True,exist_ok=True)
                    native.require(not Path(p).exists() and not Path(p).is_symlink(),'Output already present')
                result = run(row['argv'],'compile-'+str(number),role=row['id'])
                item = dict(id=row['id'],object=row['object'],depfile=row['depfile'],object_validation=common.macho(row['object']),
                    object_sha256=native.digest(row['object']),depfile_sha256=native.digest(row['depfile']),
                    inspection=object_facts(core,row['object']))
                report['objects'].append(item)
                deps = common.dependencies(row['depfile'],row['cwd'],row['object'])
                native.require(row['source'] in deps,'Actual tail MD omitted source')
                native.require(all(p in plan['inputs'] and native.digest(p)==plan['inputs'][p] for p in deps),'Unknown/changed actual tail MD input')
                item['dependencies'] = {p:plan['inputs'][p] for p in deps}
                item['input_qualification']='pass'
                item['resource_qualification']=result['resource_qualification']
                verify(native,common,plan); native.private_inputs(plan)
            transform = plan['postprocess']
            raw = Path(transform['raw_snapshot_before']); raw.parent.mkdir()
            original = Path(plan['commands'][-1]['object'])
            native.require(original.stat().st_size<=16*1024**2,'Unexpected constructor size')
            shutil.copyfile(original,raw)
            native.require(native.digest(raw)==native.digest(original),'Raw constructor copy changed')
            report['constructor_raw_sha256']=native.digest(raw)
            run(plan['transform_loader_command'],'section-tool-loader',30)
            native.loader_mapping((OUT/'section-tool-loader.stdout.txt').read_text(),plan['transform_runtime'])
            run(transform['argv'],'constructor-transform',30)
            temporary = Path(transform['rename_only_after_exit0']['source'])
            changed = core.verify_constructor_transform(raw,temporary)
            temporary.replace(original)
            native.require(core.verify_constructor_transform(raw,original)==changed,'Final transform replacement changed')
            report['constructor_transform']=dict(changed_sections=changed,raw=str(raw),raw_sha256=native.digest(raw),
                final=str(original),final_sha256=native.digest(original),final_object_validation=common.macho(original))
            final_facts=object_facts(core,original)
            item=report['objects'][-1]
            native.require(item['inspection']['external_symbols']==final_facts['external_symbols'],'Constructor symbols/imports changed')
            item.update(raw_object=str(raw),raw_object_sha256=native.digest(raw),raw_inspection=item['inspection'],
                object_sha256=native.digest(original),object_validation=common.macho(original),inspection=final_facts)
            verify(native,common,plan); native.private_inputs(plan); cancel.check()
            report['outcome']='pass'
        except BaseException as error:
            report['failure']=repr(error)
        finally:
            with cancel.cleanup():
                try:
                    if reserved: budget.release()
                except BaseException as error:
                    report.update(outcome='fail',release_error=repr(error))
                if cancel.signals: report.update(outcome='fail',cancellation_signals=cancel.signals)
                report['terminal_sessions']=[supervise.sample(c['process']['owned_session']) for c in report['commands'] if 'owned_session' in c['process']]
                report['owned_survivors']=[p for s in report['terminal_sessions'] for p in s['owned_processes'] if p['state']!='Z']
                if report['owned_survivors']: report['outcome']='fail'
                report['elapsed_seconds']=time.monotonic()-started
                report['controller_status']=core.proc_status()
                if OUT.is_dir(): native.write(OUT/'evidence.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['plan','execute'])
    p.add_argument('--source-plan',type=Path);p.add_argument('--source-plan-sha256')
    p.add_argument('--approval',type=Path);p.add_argument('--approval-sha256')
    a=p.parse_args();native,common=helpers();plan=derive(native,common)
    if a.mode=='plan': print(json.dumps(plan,indent=2));return 0
    native.require(all([a.source_plan,a.source_plan_sha256,a.approval,a.approval_sha256]),'Exact reviewed plan and root approval required')
    report=execute(native,common,plan,a.source_plan,a.source_plan_sha256,a.approval,a.approval_sha256)
    print(json.dumps(report));return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
