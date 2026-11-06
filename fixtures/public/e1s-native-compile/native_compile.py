#!/usr/bin/env python3
"""Derive or execute one exact native DEVELOPMENT component slice; no shell recipes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
COMMON = MAIN/'tools/build/avf_kernel_objects.py'
CORE = MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py'
SUPERVISOR = MAIN/'tools/build/qemu_host.py'
INTERFACE = MAIN/'worktrees/str-016-e1s-development-body-graph-20261106/fixtures/public/e1s-development-body-graph/qualified-graph.json'
PINS = [(COMMON, '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'),
        (CORE, '9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'),
        (SUPERVISOR, 'faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99')]
HEADER_AUTHORITY_SHA = '44277ad6057c26f1191212cec89c8d1387b9671ce79f85640dd3c510ca1345b6'
SOURCE_METADATA_SHA = '44a3b329931630c4447314b0e683db0c0ef571e615c1bb016321424c278b64b8'
RUNTIME_SHA = '94685ae6c56a3785b8c61c5422fb53bd8750ca92ad9caa76e9bf691bab35d12d'
INTERFACE_SHA = 'c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def module(path, expected, name):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'Changed helper: '+str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def ownership(common, manifest, executing=False):
    ledger = common.load_project(MAIN/'state/lab.json')
    tasks = [t for t in ledger['tasks'] if t['id'] == manifest['task']]
    require(len(tasks) == 1 and tasks[0]['status'] == 'in_progress' and tasks[0]['owner'] == manifest['owner'], 'Original active worker owner required')
    worktree = Path(tasks[0].get('worktree', ''))
    if not worktree.is_absolute():
        worktree = MAIN/worktree
    out = common.canonical_output_path(MAIN/manifest['out'])
    require(worktree.is_relative_to(MAIN/'worktrees') and out.is_relative_to(worktree/'artifacts/e1s-native-compile'), 'Output must belong to original worker worktree')
    if executing:
        require(tasks[0].get('scope') == 'host' and tasks[0].get('evidence_kind') == 'host-test', 'A source-review task cannot execute target workers')
        require(any(e['id'] == manifest['experiment'] and e['task'] == manifest['task'] and e['owner'] == manifest['owner'] and e['status'] == 'planned' for e in ledger['experiments']), 'Exact preregistered worker experiment required')
    return out


def derive(common, manifest_path, manifest_sha):
    manifest = common.load_project(manifest_path, manifest_sha)
    common.strict_fields(manifest, ['schema', 'task', 'owner', 'experiment', 'partition', 'object_ids', 'out', 'whole_seconds'], 'native slice manifest')
    require(manifest['schema'] == 'e1s-native-slice-v1', 'Only native slice manifests accepted')
    for key in ['task', 'owner', 'experiment', 'partition']:
        require(type(manifest[key]) is str and bool(manifest[key]), 'Missing native identity')
    relative = Path(manifest['out'])
    require(not relative.is_absolute() and '..' not in relative.parts and str(relative) == manifest['out'], 'Canonical MAIN-relative output required')
    common.strict_int(manifest['whole_seconds'], 1, 7200, 'whole native worker deadline')
    out = ownership(common, manifest)
    interface = common.load_project(INTERFACE, INTERFACE_SHA)
    require((interface['machine'], interface['kernel'], interface['architecture']) == ('E1S', 'DEVELOPMENT', 'ARM64'), 'Wrong native profile')
    inputs = {str(p): h for p, h in PINS}
    inputs.update({str(INTERFACE): INTERFACE_SHA, str(manifest_path): manifest_sha})
    def bound(binding):
        inputs[binding['path']] = binding['sha256']
        return common.load_project(binding['path'], binding['sha256'])
    graph = bound(interface['graph']); context = bound(interface['consumer_context'])
    partitions = bound(interface['partitions']); profile = bound(interface['portable_compiler_profile_selection'])
    inputs[interface['contract']['path']] = interface['contract']['sha256']
    inputs[interface['portable_compiler_profile_boundary']['path']] = interface['portable_compiler_profile_boundary']['sha256']
    require(profile['selected_external_SEED_DEFINES'] == '-DXNU_NO_TYPE_BUILTINS=0' and not profile['generated_DEVELOPMENT_default'], 'Exact explicit portable compiler profile required')
    compiler = MAIN/profile['compiler_qualification']['compiler']['path']
    inputs[str(compiler)] = profile['compiler_qualification']['compiler']['sha256']
    bound(profile['compiler_qualification']['descriptor']); bound(profile['compiler_qualification']['full_profile'])
    source_context = common.load_project(MAIN/'fixtures/public/e1s-native-source-ports/source-context.json', '3b87fdab0a2953438c7fd78f420e138604c258b5d09b97c444187737347df8dc')
    inputs[str(MAIN/'fixtures/public/e1s-native-source-ports/source-context.json')] = '3b87fdab0a2953438c7fd78f420e138604c258b5d09b97c444187737347df8dc'
    source_manifest = bound({'path':source_context['source_manifest'], 'sha256':source_context['source_manifest_sha256']})
    inputs.update({str(Path(graph['source_root'])/p): h for p,h in source_manifest.items()})
    metadata = common.load_project(HERE/'source-metadata.json', SOURCE_METADATA_SHA)
    require(metadata['root'] == str(Path(graph['source_root'])/'.git') and metadata['source_manifest_sha256'] == graph['source_manifest_sha256'], 'Wrong existing non-source metadata context')
    inputs[str(HERE/'source-metadata.json')] = SOURCE_METADATA_SHA
    inputs.update(metadata['files'])
    inputs.update({row['path']:row['sha256'] for row in context['files'].values()})
    require(len(context['files']) == 1334 and len(context['selected_source_bindings']) == 1042, 'Incomplete native context index')
    selected = [p for p in partitions['partitions'] if p['id'] == manifest['partition']]
    require(len(selected) == 1, 'Unknown native partition')
    ids = manifest['object_ids']; ordered = selected[0]['ordered_object_ids']
    require(type(ids) is list and ids and all(type(i) is str for i in ids), 'Explicit nonempty ordered slice required')
    require(ids[0] in ordered and ordered[ordered.index(ids[0]):ordered.index(ids[0])+len(ids)] == ids, 'Slice differs from original ordered partition')
    authority = bound({'path':str(HERE/'firehose-header-authority.json'), 'sha256':HEADER_AUTHORITY_SHA})
    require(authority['authority'] == 'HOST-SOURCE-EXPORT' and authority['destination'] == 'os/firehose_buffer_private.h', 'Wrong native private-header authority')
    inputs.update(authority['inputs'])
    old = graph['component_context_root']; shared = context['context_root']
    require(context['mechanical_prefix_map'] == {old:shared}, 'Wrong native context map')
    def mapped(value):
        return value.replace(old, shared)
    projections = {}; rows = []; absent = set()
    by_id = {r['id']:r for r in graph['objects']}
    for identifier in ids:
        row = by_id[identifier]; component = row['component']
        cfg = Path(shared)/'configuration'/component/'DEVELOPMENT'
        cwd = out/'cwd'/component
        prefix = f'configuration/{component}/DEVELOPMENT/'
        for name,item in context['files'].items():
            if name.startswith(prefix):
                projections[str(cwd/name[len(prefix):])] = {'source':item['path'], 'sha256':item['sha256']}
        recipe = bound(row['recipe'])
        steps = recipe['expanded_steps_by_query_BOUND_CHECKS']['0']
        require(all(not value.strip() for key,value in steps.items() if key not in ['0','1']), 'Unsupported additional native recipe stage')
        original = shlex.split(steps['1']); argv = [mapped(a) for a in original]
        require(argv[0] == str(compiler) and '-c' in argv and '-DXNU_NO_TYPE_BUILTINS=0' in argv, 'Wrong exact native compiler/profile')
        require(not any(a in [';', '&&', '|', '>', '<', '>>'] for a in argv), 'Shell recipe rejected')
        source = context['selected_source_bindings'][identifier]
        source_operand = next((n for n,a in enumerate(original) if str((Path(old)/'configuration'/component/'DEVELOPMENT'/a).resolve()) == row['source']), None)
        require(source_operand is not None and mapped(str((Path(old)/'configuration'/component/'DEVELOPMENT'/original[source_operand]).resolve())) == source['path'], 'Native source operand differs')
        argv[source_operand] = source['path']; inputs[source['path']] = source['sha256']
        obj = out/'objects'/component/row['target']; dep = out/'md'/component/(row['target']+'.d')
        require('-MF' in argv and argv.count('-MF') == 1, 'One genuine MD output required')
        argv[argv.index('-MF')+1] = str(dep)
        if '-o' in argv:
            require(argv.count('-o') == 1, 'One object output required')
            argv[argv.index('-o')+1] = str(obj)
        else:
            argv += ['-o', str(obj)]
        for n,arg in enumerate(argv):
            if arg in ['-include','-I','-isystem','-idirafter','-iquote']:
                value = argv[n+1]
            elif arg.startswith('-I'):
                value = arg[2:]
            elif arg.startswith('-fsanitize-ignorelist='):
                value = arg.split('=',1)[1]
            else:
                continue
            path = Path(value)
            if not path.is_absolute():
                require(value == '.' or (str(cwd/path) in projections and arg == '-include'), 'Unknown relative native input: '+value)
            elif not path.exists():
                absent.add(str(path))
        rows.append(dict(id=identifier, component=component, namespace_cwd=str(cfg), source=source['path'], source_sha256=source['sha256'], original_argv=original, argv=argv, cwd=str(cwd), object=str(obj), depfile=str(dep), recipe=row['recipe']))
    for cwd in {row['cwd'] for row in rows}:
        target = str(Path(cwd)/authority['destination'])
        require(target not in projections, 'Private header collides with indexed configuration')
        projections[target] = {'source':authority['header']['path'], 'sha256':authority['header']['sha256']}
    runtime = common.load_project(HERE/'runtime.json', RUNTIME_SHA)
    inputs[str(HERE/'runtime.json')] = RUNTIME_SHA
    inputs.update(runtime['files'])
    for path,h in inputs.items():
        require(Path(path).resolve(strict=True) == Path(path) and not Path(path).is_symlink() and digest(path) == h, 'Changed/aliased native input: '+path)
    result = dict(schema='e1s-native-component-plan-v1', resource_profile='project-budget-v1', task=manifest['task'], owner=manifest['owner'], experiment=manifest['experiment'], shard=manifest['partition'], manifest={'path':str(manifest_path),'sha256':manifest_sha}, executor_sha256=digest(__file__), out=str(out), whole_seconds=manifest['whole_seconds'], max_jobs=1, max_owned_rss_bytes=512*1024**2, graph=interface['graph'], context=interface['consumer_context'], profile=interface['portable_compiler_profile_selection'], commands=rows, projections=projections, inputs=inputs, absent_inputs=sorted(absent), runtime=runtime, header_authority=authority, nonsource_metadata=metadata, runtime_lookup={cwd:runtime_lookup(runtime,cwd) for cwd in sorted({r['cwd'] for r in rows})}, loader_commands={cwd:[runtime['interpreter'],'--list',str(compiler)] for cwd in sorted({r['cwd'] for r in rows})}, compiled=False)
    result['namespace'] = native_namespace(common, result)
    return result


def native_namespace(common, plan):
    rows = [dict(cwd=row['namespace_cwd'], bound_source=row['source'],
                 next_owned_compile_argv_template=row['argv']) for row in plan['commands']]
    cache = common.Digests()
    result = common.namespace(rows, plan['inputs'], cache)
    overlay = {}
    for cwd in {row['cwd'] for row in plan['commands']}:
        target = str(Path(cwd)/plan['header_authority']['destination'])
        item = plan['projections'][target]
        observed = cache.get(item['source'])
        require(observed == item['sha256'] == plan['header_authority']['header']['sha256'] and item['source'] == plan['header_authority']['header']['path'], 'Private header authority changed')
        overlay[target] = {**item, 'observed_sha256':observed, 'authority_sha256':HEADER_AUTHORITY_SHA}
    result['private_header_projection'] = overlay
    result['sha256'] = common.canonical({k:v for k,v in result.items() if k != 'sha256'})
    return result


def runtime_lookup(runtime, cwd):
    # Include literal and expanded escaped RUNPATH spellings, its empty/CWD
    # component, system paths and the recorded host's hwcaps candidates.
    compiler = Path(runtime['compiler']['path'])
    roots = {Path(cwd), *map(Path, runtime['system_directories'])}
    for value in runtime['compiler_literal_runpath'].split(':'):
        for spelling in [value, value.replace('$ORIGIN', str(compiler.parent))]:
            roots.add(Path(cwd)/spelling if not Path(spelling).is_absolute() else Path(spelling))
    roots |= {root/'glibc-hwcaps'/sub for root in list(roots) for sub in runtime['hwcaps_subdirectories']}
    result = {}
    for root in roots:
        for name in runtime['loaded']:
            path = root/name
            result[str(path)] = [str(path.resolve(strict=True)), digest(path)] if path.exists() or path.is_symlink() else None
    return result


def verify(common, plan):
    metadata = plan['nonsource_metadata']; root = Path(metadata['root'])
    nodes = [root, *root.rglob('*')]
    require(all(not p.is_symlink() for p in nodes) and {str(p):p.stat().st_mode & 0o7777 for p in nodes} == metadata['modes'], 'Existing non-source metadata names/modes changed')
    require({str(p) for p in nodes if p.is_file()} == set(metadata['files']), 'Existing non-source metadata inventory changed')
    require(native_namespace(common, plan) == plan['namespace'], 'Native include namespace/shadow changed')
    for path,h in plan['inputs'].items():
        require(Path(path).resolve(strict=True) == Path(path) and not Path(path).is_symlink() and digest(path) == h, 'Changed/aliased admitted native input: '+path)
    for cwd,lookup in plan['runtime_lookup'].items():
        require(runtime_lookup(plan['runtime'], cwd) == lookup, 'Compiler runtime search shadow changed')
    for path in plan['absent_inputs']:
        require(not Path(path).exists() and not Path(path).is_symlink(), 'Unqualified input appeared: '+path)
    for path,h in plan['runtime']['aliases'].items():
        require(str(Path(path).resolve(strict=True)) == h, 'Runtime alias changed')
    preload = Path('/etc/ld.so.preload')
    require(not preload.exists() or not preload.read_text().strip(), 'Unqualified loader preload')


def private_inputs(plan, copy=False):
    for path,item in plan['projections'].items():
        target = Path(path)
        if copy:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(Path(item['source']).read_bytes())
        require(not target.is_symlink() and digest(target) == item['sha256'], 'Private CWD input changed')
    for root in {Path(row['cwd']) for row in plan['commands']}:
        require({str(p) for p in root.rglob('*') if p.is_file() or p.is_symlink()} == {p for p in plan['projections'] if Path(p).is_relative_to(root)}, 'Private CWD has unindexed shadow')


def loader_mapping(text, runtime):
    found = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts or parts[0].startswith('linux-vdso.'):
            continue
        if '=>' in parts:
            require(len(parts) >= 3 and parts[2] != 'not', 'Unresolved compiler runtime')
            found[Path(parts[0]).name] = str(Path(parts[2]).resolve(strict=True))
        elif parts[0].startswith('/'):
            found[Path(parts[0]).name] = str(Path(parts[0]).resolve(strict=True))
        else:
            raise ValueError('Unknown loader observation')
    require(found == runtime['loaded'], 'Actual runtime differs from pinned compiler context')


def execute(common, plan, source_plan, source_sha, approval_path, approval_sha):
    require(common.load_project(source_plan, source_sha) == plan, 'Reviewed native source plan changed')
    manifest = common.load_project(plan['manifest']['path'], plan['manifest']['sha256'])
    out = ownership(common, manifest, True)
    args = SimpleNamespace(main=MAIN, out=out, **{k:plan[k] for k in ['task','owner','experiment','shard']})
    approval = common.load_project(approval_path, approval_sha)
    require(approval['source_plan_sha256'] == source_sha, 'Wrong approved native source plan')
    budget = common.project_approval(args, approval, executor_path=Path(__file__))
    require(budget.source_plan == plan and budget.rss_limit == 512*1024**2 and budget.allocation['max_compiler_jobs_total'] == 6, 'Exact six-job/512MiB native allocation required')
    supervise = module(*PINS[2], 'native_supervisor'); core = module(*PINS[1], 'native_cleanup')
    started = time.monotonic(); reserved = False
    report = dict(kind='host-test', origin='local-host', outcome='fail', recorded_at=common.stamp(), task=plan['task'], owner=plan['owner'], experiment=plan['experiment'], source_plan_sha256=source_sha, executor_sha256=digest(__file__), commands=[], objects=[], full_kernel_qualified=False, hardware_execution=False)
    with core.owned_cancellation() as cancel:
        try:
            with cancel.cleanup():
                budget.reserve(); reserved = True
            cancel.check()
            ownership(common, manifest, True); verify(common, plan)
            require(not out.exists() and not out.is_symlink(), 'Fresh native output required; no resume')
            out.mkdir(parents=True, exist_ok=False)
            write(out/'execution-plan.json', plan); private_inputs(plan, copy=True)
            loaded = set()
            for number,row in enumerate(plan['commands']):
                cancel.check(); verify(common, plan); private_inputs(plan)
                remaining = plan['whole_seconds']-(time.monotonic()-started)
                require(remaining > 0, 'Whole native worker deadline')
                for path in [row['object'],row['depfile']]:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    require(not Path(path).exists() and not Path(path).is_symlink(), 'Output already present')
                if row['cwd'] not in loaded:
                    with cancel.command(budget):
                        record = common.run_child(plan['loader_commands'][row['cwd']], Path(row['cwd']), out, 'loader-'+str(number), supervise, timeout=min(120,remaining), admit=True, budget=budget)
                        report['commands'].append(dict(role='loader', process=record))
                    require(record.get('outcome') == 'pass' and record.get('resource_qualification') == 'pass', 'Runtime admission/observation failed')
                    loader_mapping((out/('loader-'+str(number)+'.stdout.txt')).read_text(), plan['runtime']); loaded.add(row['cwd'])
                with cancel.command(budget):
                    record = common.run_child(row['argv'], Path(row['cwd']), out, 'compile-'+str(number), supervise, timeout=min(120,max(.001,plan['whole_seconds']-(time.monotonic()-started))), admit=True, budget=budget)
                    report['commands'].append(dict(role=row['id'], process=record))
                item = dict(id=row['id'], object=row['object'], depfile=row['depfile'], object_validity='not-produced', input_qualification='not-observed', resource_qualification=record.get('resource_qualification','inconclusive'))
                report['objects'].append(item)
                if record.get('child_started') and record.get('exit_code') == 0:
                    item['object_validity'] = 'fail'
                    item['object_validation'] = common.macho(row['object'], row['id'] == 'libkern/OSData.cpo')
                    item.update(object_validity='pass', object_sha256=digest(row['object']), input_qualification='fail')
                    deps = common.dependencies(row['depfile'],row['cwd'],row['object'])
                    expected = {**plan['inputs'], **{p:v['sha256'] for p,v in plan['projections'].items()}}
                    require(row['source'] in deps, 'Compiler MD omitted exact native source')
                    require(all(p in expected and digest(p) == expected[p] for p in deps), 'Unknown/changed actual native MD input')
                    item.update(input_qualification='pass', depfile_sha256=digest(row['depfile']), dependencies={p:expected[p] for p in deps})
                verify(common, plan); private_inputs(plan); cancel.check()
                require(record.get('outcome') == 'pass' and record.get('resource_qualification') == 'pass' and item['object_validity'] == 'pass' and item['input_qualification'] == 'pass', 'Stop after failed/deferred native row')
            report['outcome'] = 'pass'
        except BaseException as error:
            report['failure'] = repr(error)
        finally:
            with cancel.cleanup():
                try:
                    if reserved:
                        budget.release()
                except BaseException as error:
                    report.update(outcome='fail', release_error=repr(error))
                if cancel.signals:
                    report.update(outcome='fail', cancellation_signals=cancel.signals)
                report['terminal_sessions'] = [supervise.sample(c['process']['owned_session']) for c in report['commands'] if 'owned_session' in c['process']]
                report['owned_survivors'] = [p for sample in report['terminal_sessions'] for p in sample['owned_processes'] if p['state'] != 'Z']
                if report['owned_survivors']:
                    report['outcome'] = 'fail'
                report['elapsed_seconds'] = time.monotonic()-started
                report['controller_status'] = core.proc_status()
                if out.is_dir():
                    write(out/'evidence.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['plan','execute'])
    p.add_argument('--manifest', required=True, type=Path); p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--source-plan', type=Path); p.add_argument('--source-plan-sha256')
    p.add_argument('--approval', type=Path); p.add_argument('--approval-sha256')
    a = p.parse_args(); common = module(*PINS[0], 'native_common')
    plan = derive(common, common.canonical_output_path(a.manifest), a.manifest_sha256)
    verify(common, plan)
    if a.mode == 'plan':
        print(json.dumps(plan,indent=2)); return 0
    require(all([a.source_plan,a.source_plan_sha256,a.approval,a.approval_sha256]), 'Exact source-plan and root approval required')
    report = execute(common, plan, a.source_plan,a.source_plan_sha256,a.approval,a.approval_sha256)
    print(json.dumps(report)); return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
