#!/usr/bin/env python3
"""Native DEVELOPMENT/E1S final-link admission and future STR037 caller.

STR036 may inspect incomplete accepted indices; it cannot stage or execute.
"""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
POLICY_SHA = '136f4c7885d81320e8ea5f7a1cf4032a71f81eee786cf4415e7280cfcf866098'
PINS = {
    'common': (MAIN/'tools/build/avf_kernel_objects.py','9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'),
    'core': (MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py','9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'),
    'archive': (MAIN/'tools/build/avf_guest_components.py','e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa'),
    'native': (MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py','2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f'),
    'supervise': (MAIN/'tools/build/qemu_host.py','faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99')}
APIS = {}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def safe_path(value, project=True, exists=True):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_./+\-]+',value), 'Unsafe path spelling')
    p = Path(value)
    require(p.is_absolute() and str(p) == value and '..' not in p.parts, 'Noncanonical/escaped path')
    require(not project or p.is_relative_to(MAIN), 'Input outside project authority')
    if exists:
        require(p.resolve(strict=True) == p and not p.is_symlink(), 'Aliased/missing input')
    else:
        require(APIS['common'].canonical_output_path(p) == p, 'Aliased output ancestry')
    return p


def api(name):
    if name not in APIS:
        path,expected = PINS[name]
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected and path.resolve(strict=True) == path, 'Changed/aliased pinned helper')
        spec = importlib.util.spec_from_file_location('native_link_'+name,path)
        result = importlib.util.module_from_spec(spec)
        exec(compile(raw,str(path),'exec'),result.__dict__)
        APIS[name] = result
    return APIS[name]


def binding(value):
    require(type(value) is dict and set(value) >= {'path','sha256'}, 'Missing typed file binding')
    require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']), 'Invalid input digest')
    safe_path(value['path'])
    return {'path':value['path'],'sha256':value['sha256']}


def read(value, json_value=False):
    b = binding(value); p = safe_path(b['path'])
    with api('core').CoherentFile(p) as snapshot:
        require(snapshot.digest() == b['sha256'], 'Changed input: '+str(p))
        if json_value:
            require(snapshot.length <= 64<<20, 'Bounded JSON input exceeded')
            data = b''.join(snapshot.iter_range(0,snapshot.length))
            result = json.loads(data)
        else:
            result = b
    safe_path(str(p))
    return result


def references():
    policy = read({'path':str(HERE/'policy.json'),'sha256':POLICY_SHA},True)
    contract = read(policy['contract'],True)
    read(policy['graph'],True)
    graph = read(policy['body_graph'],True)
    context = read(policy['context'],True)
    overrides = read(policy['overrides'],True)
    require(canonical(contract['native_driver']['original_shell_argv']) == policy['original_argv_sha256'], 'Native driver authority changed')
    require(contract['component_order'] == policy['component_order'], 'Component order changed')
    return policy,contract,graph,context,overrides


def validate_index(index, policy, graph, context, overrides):
    """Structural admission of real accepted references; never creates outputs."""
    require(index['schema'] == 'native-actual-body-index-v1' and index['kind'] == 'accepted-actual-product-reference-index' and index['owner'] == 'INT-002', 'Unqualified actual index kind')
    require(index['graph'] == policy['body_graph'] and index['context'] == policy['context'] and index['portable_compiler_profile'] == policy['profile'], 'Wrong graph/context/profile')
    order = [r['id'] for r in graph['objects']]
    require(len(order) == 1042 and len(set(order)) == 1042, 'Wrong native1042 graph')
    by_id = {r['id']:r for r in graph['objects']}
    ids = [r['id'] for r in index['rows']]
    require(len(ids) == len(set(ids)) and all(i in by_id for i in ids), 'Duplicate/unknown native body ID')
    require(ids == [i for i in order if i in set(ids)], 'Reordered native body selection')
    missing = [i for i in order if i not in set(ids)]
    require(index['ABSENT_ids'] == missing and index['baseline_accepted_count'] == len(ids) and index['baseline_ABSENT_count'] == len(missing), 'Missing/false baseline inventory')
    require(binding(index['two_explicit_final_overrides']) == policy['overrides'], 'Unqualified override authority')
    require(overrides['original_graph']['sha256'] == policy['body_graph']['sha256'] and overrides['unchanged_context'] == policy['context'] and overrides['unchanged_portable_compiler_profile'] == policy['profile'], 'Override lineage changed')
    require([r['id'] for r in overrides['overrides']] == ['osfmk/start.o','bsd/e1s_log.o'], 'Duplicate/reordered/unapproved override IDs')
    selected = {}
    for r in index['rows']:
        g = by_id[r['id']]
        require(r['component'] == g['component'] and r['recipe'] == g['recipe'], 'Wrong native component/recipe')
        require(r['source'] == context['selected_source_bindings'][r['id']], 'Wrong native source context')
        require(r['actual_object_input_resource_qualification'] == 'pass', 'Unqualified object/input/resource tuple')
        for key in ['object','depfile','source','recipe']:
            binding(r[key])
        a = r['actual_tuple_authority']
        require(a['format'] in ['list-of-independent-actual-products','native-worker-evidence'], 'Source plan is not output authority')
        binding(a)
        if 'independent_review' in r:
            binding(r['independent_review'])
        safe_path(r['actual_cwd'])
        require(type(r['actual_MD_dependency_count']) is int and r['actual_MD_dependency_count'] > 0 and all(re.fullmatch('[0-9a-f]{64}',r[k]) for k in ['actual_argv_sha256','actual_MD_map_sha256']), 'Missing actual argv/MD identity')
        require(Path(r['object']['path']).is_relative_to(MAIN/'worktrees') and '/artifacts/e1s-native-compile/' in r['object']['path'] and r['object']['path'].endswith('/objects/'+r['id']), 'Escaped/unowned object input')
        selected[r['id']] = r
    for r in overrides['overrides']:
        require(all(r['qualifications'][key] == 'pass' for key in ['object_validity','input_qualification','resource_qualification','storage_qualification']), 'Unqualified035 override')
        require(r['recipe'] == by_id[r['id']]['recipe'], 'Override recipe changed')
        for key in ['object','depfile','source','recipe']:
            binding(r[key])
        selected[r['id']] = {**r,'actual_tuple_authority':policy['overrides'],'override':True}
    final_missing = [i for i in order if i not in selected]
    require(index['final_available_slots_with_overrides'] == len(selected) and index['final_ABSENT_slots_with_overrides'] == len(final_missing), 'False final override inventory')
    return order,selected,final_missing


def inspect(index_binding):
    policy,contract,graph,context,overrides = references()
    index = read(index_binding,True)
    order,selected,missing = validate_index(index,policy,graph,context,overrides)
    return dict(kind='source-review',outcome='pass',baseline_accepted=len(index['rows']),baseline_ABSENT=len(index['ABSENT_ids']),selected_actual_count=len(selected),missing_ids=missing,ready=False,all_body_inputs_present=not missing,executable_argv=None,staging_or_filelists_created=False,execution_authority=False,required_additional_admission=['Complete independently accepted1042-body index/review','Exact qualified ld backend ELF runtime/interpreter/library/search/alias tuple','Separate active STR037 experiment and exact root allocation/approval/whole watchdog'],check_all_exports='NOT RUN; native DEVELOPMENT has no RELEASE export-list flag',private37_ABI='OPEN; required names retained')


def own(request, executing=False):
    common = api('common'); ledger = common.load_project(MAIN/'state/lab.json')
    require(request['task'] == 'STR-037', 'STR036 source task cannot stage or execute')
    tasks = {t['id']:t for t in ledger['tasks']}; t = tasks[request['task']]
    require(t['status'] == 'in_progress' and t['owner'] == request['owner'] and t['scope'] == 'host' and t['evidence_kind'] == 'host-test', 'Original active host-test owner required')
    require('STR-036' in t['depends_on'] and all(tasks[d]['status'] == 'done' for d in t['depends_on']), 'Actual task dependencies not accepted')
    require(any(e['id'] == request['experiment'] and e['task'] == request['task'] and e['owner'] == request['owner'] and e['status'] == 'planned' for e in ledger['experiments']), 'Actual original experiment not planned')
    relative = Path(request['out'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'Output escape')
    out = safe_path(str(MAIN/relative),exists=False)
    wt = Path(t['worktree'])
    require(wt.is_relative_to(MAIN/'worktrees') and out.is_relative_to(wt/'artifacts/e1s-native-link') and not out.exists(), 'Fresh original-owner link output required')
    return out


def actual_tuples(index, selected):
    """Verify original actual tuple records, one producer index at a time."""
    groups = defaultdict(list)
    for row in index['rows']:
        groups[(row['actual_tuple_authority']['path'],row['actual_tuple_authority']['sha256'])].append(row)
    inputs = {}
    for (path,sha),rows in groups.items():
        value = read({'path':path,'sha256':sha},True); inputs[path] = sha
        form = rows[0]['actual_tuple_authority']['format']
        if form == 'list-of-independent-actual-products':
            by_id = {r['id']:r for r in value}
            require(len(by_id) == len(value), 'Duplicate producer tuple ID')
            for row in rows:
                r = by_id[row['id']]
                require(r['actual_resource_qualification'] == 'pass' and r['object'] == row['object']['path'] and r['object_sha256'] == row['object']['sha256'] and r['depfile'] == row['depfile']['path'] and r['depfile_sha256'] == row['depfile']['sha256'] and r['source'] == row['source'] and r['recipe'] == row['recipe'], 'Actual producer tuple differs')
                require(canonical(r['actual_argv']) == row['actual_argv_sha256'] and canonical(r['actual_MD_dependencies']) == row['actual_MD_map_sha256'] and len(r['actual_MD_dependencies']) == row['actual_MD_dependency_count'] and r['actual_cwd'] == row['actual_cwd'], 'Actual argv/CWD/MD map differs')
        else:
            require(value['outcome'] == 'pass' and not value['owned_survivors'], 'Unqualified native producer cleanup')
            objects = {r['id']:r for r in value['objects']}
            for row in rows:
                r = objects[row['id']]; a = row['actual_tuple_authority']
                plan = read({'path':str(MAIN/a['source_plan']['path']),'sha256':a['source_plan']['sha256']},True)
                inputs[str(MAIN/a['source_plan']['path'])] = a['source_plan']['sha256']
                command = next(c['process'] for c in value['commands'] if c['role'] == row['id'])
                source = next(c for c in plan['commands'] if c['id'] == row['id'])
                require(all(r[k] == 'pass' for k in ['object_validity','input_qualification','resource_qualification']) and command['resource_qualification'] == 'pass' and command['exit_code'] == 0, 'Native raw tuple qualification')
                require(r['object'] == row['object']['path'] and r['object_sha256'] == row['object']['sha256'] and r['depfile_sha256'] == row['depfile']['sha256'] and source['source'] == row['source']['path'] and source['source_sha256'] == row['source']['sha256'] and source['recipe'] == row['recipe'], 'Native raw/source tuple differs')
                require(canonical(command['argv']) == row['actual_argv_sha256'] and command['cwd'] == row['actual_cwd'] and canonical(r['dependencies']) == row['actual_MD_map_sha256'] and len(r['dependencies']) == row['actual_MD_dependency_count'], 'Native raw argv/MD mismatch')
        for row in rows:
            if 'independent_review' in row:
                read(row['independent_review'],True); inputs[row['independent_review']['path']] = row['independent_review']['sha256']
    for row in selected.values():
        for key in ['object','depfile','source','recipe']:
            b = read(row[key]); inputs[b['path']] = b['sha256']
    return inputs


def runtime_inputs(runtime,policy,cwd):
    require(runtime['schema'] == 'e1s-native-link-runtime-v1' and set(runtime['programs']) == {'clang','ld','setsegname'}, 'Exact native tool runtime tuple required')
    expected = {'clang':policy['tools']['clang'],'ld':policy['tools']['ld'],'setsegname':policy['tools']['XNU_setsegname']}
    inputs,lookups = {},{}
    for name,r in runtime['programs'].items():
        require(r['compiler'] == expected[name], 'Wrong exact frontend/backend/transform executable')
        require(type(r['loaded']) is dict and r['loaded'] and r['files'] and r['aliases'], 'Missing ELF runtime observation binding')
        for p,h in r['files'].items():
            require(safe_path(p,project=False) == Path(p), 'Aliased runtime file')
            with api('core').CoherentFile(p) as f:require(f.digest() == h, 'Changed runtime file')
            inputs[p] = h
        for path,target in r['aliases'].items():
            require(str(Path(path).resolve(strict=True)) == target and target in r['files'], 'Runtime alias drift')
        require(all(path in r['files'] for path in r['loaded'].values()) and str(Path(r['interpreter']).resolve(strict=True)) in r['files'], 'Runtime map not fully indexed')
        require(r['interpreter'] == '/lib64/ld-linux-x86-64.so.2' and r['files'].get('/usr/lib64/ld-linux-x86-64.so.2') == '9c492275e50fb1bb7ee54855e701516d1fe75c95123abf61c008ff731caf1e27', 'Unqualified host ELF interpreter')
        read(r['compiler'])
        inputs[r['compiler']['path']] = r['compiler']['sha256']
        lookups[name] = api('native').runtime_lookup(r,str(cwd))
    return inputs,lookups


def make_plan(request_binding):
    request = read(request_binding,True)
    api('common').strict_fields(request,['schema','task','owner','experiment','out','whole_seconds','index','input_review','runtime'],'native link request')
    require(request['schema'] == 'e1s-native-link-request-v1', 'Wrong request schema')
    policy,contract,graph,context,overrides = references()
    index = read(request['index'],True)
    order,selected,missing = validate_index(index,policy,graph,context,overrides)
    require(not missing, 'Incomplete actual native selection: '+str(len(missing))+' missing IDs')
    review = read(request['input_review'],True)
    require(review['schema'] == 'e1s-native-link-input-review-v1' and review['outcome'] == 'pass' and review['index_sha256'] == request['index']['sha256'] and review['accepted_body_count'] == 1042 and review['graph_sha256'] == policy['body_graph']['sha256'] and review['overrides_sha256'] == policy['overrides']['sha256'], 'Complete independent native input seal required')
    out = own(request); cwd = out/'kernel'
    api('common').strict_int(request['whole_seconds'],1,1800,'whole link deadline')
    inputs = actual_tuples(index,selected)
    for b in [request_binding,request['index'],request['input_review'],request['runtime'],policy['contract'],policy['graph'],policy['body_graph'],policy['context'],policy['profile'],policy['overrides'],{'path':str(HERE/'policy.json'),'sha256':POLICY_SHA}]:
        read(b); inputs[b['path']] = b['sha256']
    for p,h in PINS.values():inputs[str(p)] = h
    inputs[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    runtime = read(request['runtime'],True)
    runtime_files,lookups = runtime_inputs(runtime,policy,cwd); inputs.update(runtime_files)
    copies,transforms = [],[]
    for identifier in order:
        b = binding(selected[identifier]['object']); copies.append(dict(id=identifier,source=b,destination=str(out/'objects'/identifier)))
    for tail in contract['tail_order']:
        b = read(tail['object']); inputs[b['path']] = b['sha256']; copies.append(dict(id='tail/'+tail['name'],source=b,destination=str(cwd/tail['name'])))
        b = read(tail['depfile']); inputs[b['path']] = b['sha256']
    metadata = read(policy['metadata'],True)
    require(len(metadata['metadata']) == 22 and metadata['outcome'] == 'pass', 'Genuine22 metadata products required')
    inputs[policy['metadata']['path']] = policy['metadata']['sha256']
    for relative,b in metadata['metadata'].items():
        target = safe_path(str(out/relative),exists=False); b = read(b); inputs[b['path']] = b['sha256']; copies.append(dict(id='metadata/'+relative,source=b,destination=str(target)))
    libraries = contract['libraries']; archives = []
    for b in [libraries['fresh_native_provider_libraries']['descriptor'],libraries['fresh_native_provider_libraries']['partial_qualification'],libraries['cc_kext']['prior_actual_frontend_authority']]:
        read(b); inputs[b['path']] = b['sha256']
    for a in libraries['fresh_native_provider_libraries']['archives']:
        b = read(a); inputs[b['path']] = b['sha256']; destination = out/'libraries/kernel'/Path(a['path']).name
        copies.append(dict(id=a['id'],source=b,destination=str(destination))); archives.append(dict(source=b,expected_members=a['members']))
    cc = libraries['cc_kext']; b = read(cc['archive']); inputs[b['path']] = b['sha256']; read(cc['descriptor']); inputs[cc['descriptor']['path']] = cc['descriptor']['sha256']; archives.append(dict(source=b,expected_member_count=287))
    tool = policy['tools']['XNU_setsegname']; read(tool); inputs[tool['path']] = tool['sha256']
    for group in contract['owned_copy_transforms']:
        for identifier in group['ordered_object_ids']:
            p = out/'objects'/identifier
            passes = [(None,'__HIB',None)] if group['component']=='osfmk' else [('__TEXT','__KLD',None),(None,'__KLDDATA','__KLD')]
            for number,(old,new,ignore) in enumerate(passes):
                target = Path(str(p)+'.pass'+str(number))
                argv = [tool['path'], *(['-s',old] if old else []), *(['-i',ignore] if ignore else []), '-n',new,'-o',str(target),str(p)]
                transforms.append(dict(id=identifier,argv=argv,original=str(p),result=str(target),passes=[[old,new,ignore]]))
    filelists = [{'component':c,'path':str(out/'filelists'/(c+'.filelist')),'ids':[r['id'] for r in graph['objects'] if r['component']==c]} for c in policy['component_order']]
    require(sum(len(f['ids']) for f in filelists)==1042, 'No second LIBOBJS selection')
    driver = contract['native_driver']['original_shell_argv'][:]
    oldlibs = [a[2:] for a in driver if a.startswith('-L')]
    pathmap = {old:str(out/'libraries/kernel'/('platform' if old.endswith('/platform') else '')) for old in set(oldlibs)}
    pathmap.update({b['path']:str(cwd/name) for name,b in contract['metadata']['link_inputs'].items()})
    for number,a in enumerate(driver):
        if a.startswith('-L'):driver[number] = '-L'+pathmap[a[2:]]
        elif a in ['version.o','lastkerneldataconst.o','lastkernelconstructor.o','nonlto.o']:driver[number] = str(cwd/a)
        elif a == 'link.filelist':driver[number] = str(cwd/a)
        elif number and driver[number-1] == '-o':driver[number] = str(cwd/'kernel.unstripped')
        elif a.startswith('-Wl,'):
            for name in contract['metadata']['link_inputs']:
                if a.endswith('/'+name):driver[number] = a.rsplit(',',1)[0]+','+str(cwd/name)
    # These exact source-built routing additions were separately qualified; no
    # old RELEASE flags, journal wrapper or backend argument restoration.
    driver.insert(1,'--ld-path='+policy['tools']['ld']['path'])
    driver += ['-resource-dir',cc['link_only_resource_dir']]
    return dict(schema='e1s-native-link-plan-v1',resource_profile='project-budget-v1',**{k:request[k] for k in ['task','owner','experiment','whole_seconds']},shard='native-final-link',out=str(out),cwd=str(cwd),request=request_binding,executor_sha256=inputs[str(Path(__file__).resolve())],max_jobs=1,max_owned_rss_bytes=512<<20,inputs=inputs,order=order,copies=copies,transforms=transforms,filelists=filelists,link_filelist=str(cwd/'link.filelist'),driver=driver,output=str(cwd/'kernel.unstripped'),archives=archives,runtime=runtime,runtime_lookup=lookups,original_driver_argv=contract['native_driver']['original_shell_argv'],routing_only_additions=['--ld-path='+policy['tools']['ld']['path'],'-resource-dir',cc['link_only_resource_dir']],check_all_exports='NOT RUN; genuine source obligation remains',private37_ABI='OPEN',hardware_execution=False)


def execute(plan,source_plan,source_sha,approval_binding):
    """Future STR037 only: all copies/targets occur after exact root approval."""
    common,core,supervise = api('common'),api('core'),api('supervise')
    require(read({'path':str(source_plan),'sha256':source_sha},True) == plan, 'Reviewed execution plan changed')
    require(make_plan(plan['request']) == plan, 'Reconstructed native plan differs')
    request = read(plan['request'],True); out = own(request,True)
    args = SimpleNamespace(main=MAIN,out=out,**{k:plan[k] for k in ['task','owner','experiment','shard']})
    approval = read(approval_binding,True)
    require(approval['source_plan_sha256'] == source_sha, 'Wrong root source-plan approval')
    budget = common.project_approval(args,approval,executor_path=Path(__file__))
    require(budget.source_plan == plan and budget.rss_limit == (512<<20) and budget.allocation['max_compiler_jobs_total'] == 6, 'Exact root6-job/512MiB allocation required')
    started,reserved = time.monotonic(),False
    report = dict(kind='host-test',outcome='inconclusive',task=plan['task'],owner=plan['owner'],experiment=plan['experiment'],source_plan_sha256=source_sha,commands=[],transforms=[],archives=[],link_executed=False,check_all_exports=plan['check_all_exports'],private37_ABI='OPEN',hardware_execution=False)
    staged = {}
    with core.owned_cancellation() as cancel:
        def checkpoint():
            cancel.check()
            require(not Path('/etc/ld.so.preload').exists() or not Path('/etc/ld.so.preload').read_text().strip(), 'Unqualified loader preload')
            remaining = plan['whole_seconds']-(time.monotonic()-started)
            require(remaining > 0, 'Whole native link deadline exceeded')
            snapshot = budget.sample(lock_timeout=min(.5,remaining))
            require(not snapshot['violations'] and snapshot['project_rss_bytes'] <= 6<<30 and snapshot['MemAvailable_bytes'] >= 4<<30, 'Project resource boundary failed')
            require(not supervise.pressured(supervise.sample()), 'Host memory pressure; no retry')
            return remaining

        def hashes(items):
            for path,expected in items.items():
                checkpoint(); safe_path(path,project=Path(path).is_relative_to(MAIN))
                with core.CoherentFile(path) as f:require(f.digest() == expected, 'Changed admitted input: '+path)

        def copy(source,destination):
            checkpoint(); destination = safe_path(str(destination),exists=False)
            require(destination.is_relative_to(out), 'Copy outside owned output')
            destination.parent.mkdir(parents=True,exist_ok=True)
            with core.CoherentFile(source['path']) as f, destination.open('xb') as stream:
                require(f.digest() == source['sha256'], 'Copy source changed')
                for block in f.iter_range(0,f.length):
                    checkpoint(); stream.write(block)
                f.check()
            with core.CoherentFile(destination) as f:require(f.digest() == source['sha256'], 'Copy postimage differs')
            staged[str(destination)] = source['sha256']

        def inventory():
            hashes(staged)
            for root in [out/'objects',out/'kernel',out/'libraries',out/'filelists',out/'raw']:
                if not root.exists():continue
                actual = set()
                for p in root.rglob('*'):
                    require(not p.is_symlink(), 'Symlink in owned link namespace')
                    if p.is_file():actual.add(str(p))
                    else:require(p.is_dir(), 'Nonregular staging entry')
                require(actual == {p for p in staged if Path(p).is_relative_to(root)}, 'Unindexed owned link input/shadow')

        def command(role,argv):
            remaining = checkpoint()
            try:
                record = core.run_owned_child(common,cancel,argv,Path(plan['cwd']),out,role,supervise,timeout=min(120,remaining),budget=budget)
            except core.OwnedCancellation as error:
                if error.command is not None:report['commands'].append(dict(role=role,process=error.command))
                raise
            report['commands'].append(dict(role=role,process=record))
            require(record['outcome'] == 'pass' and record.get('resource_qualification') == 'pass' and record['exit_code'] == 0, 'Actual command failed/deferred: '+role)
            return record

        try:
            with cancel.cleanup():
                budget.reserve(); reserved = True
            checkpoint()
            out.mkdir(parents=True,exist_ok=False)
            (out/'execution-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
            Path(plan['cwd']).mkdir(); (out/'libraries/kernel/platform').mkdir(parents=True)
            hashes(plan['inputs'])
            # Fresh generic ELF observations are actual commands, never source checks.
            for name,runtime in plan['runtime']['programs'].items():
                require(api('native').runtime_lookup(runtime,plan['cwd']) == plan['runtime_lookup'][name], 'ELF lookup namespace drift')
                record = command('runtime-'+name,[runtime['interpreter'],'--list',runtime['compiler']['path']])
                api('native').loader_mapping((out/('runtime-'+name+'.stdout.txt')).read_text(),runtime)
            strict_archive = api('archive')
            for archive in plan['archives']:
                checkpoint(); p = archive['source']['path']
                with core.CoherentFile(p) as snapshot:
                    strict = strict_archive.archive_members(p,with_metadata=True)
                    members = core.stream_archive(p)
                    require(strict['toc_name'] in strict_archive.TOC_NAMES and strict['sha256'] == members.sha256 == snapshot.digest() == archive['source']['sha256'] and strict['members'] == [{k:m[k] for k in ['name','sha256']} for m in members], 'Strict archive snapshot disagreement')
                    if 'expected_members' in archive:
                        require(list(members) == archive['expected_members'], 'Provider member order/body changed')
                    else:require(len(members) == archive['expected_member_count'], 'cc_kext member inventory changed')
                    report['archives'].append(dict(source=archive['source'],members=list(members),toc=strict['toc_name']))
            for item in plan['copies']:copy(item['source'],Path(item['destination']))
            for number,item in enumerate(plan['transforms']):
                original,result = Path(item['original']),Path(item['result'])
                raw = out/'raw'/original.relative_to(out/'objects')
                if not raw.exists():copy({'path':str(original),'sha256':staged[str(original)]},raw)
                hashes({str(original):staged[str(original)]})
                command('transform-'+str(number),item['argv'])
                substitutions = core.verify_segment_processing(original,result,[tuple(p) for p in item['passes']])
                with core.CoherentFile(result) as f:sha = f.digest()
                staged[str(result)] = sha
                replacement = Path(str(original)+'.install')
                copy({'path':str(result),'sha256':sha},replacement)
                os.replace(replacement,original); staged.pop(str(replacement)); staged[str(original)] = sha
                report['transforms'].append(dict(**item,sha256=sha,changed_section_offsets=substitutions))
            for item in plan['filelists']:
                p = Path(item['path']); p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(''.join(str(out/'objects'/i)+'\n' for i in item['ids']))
                with core.CoherentFile(p) as f:staged[str(p)] = f.digest()
            joined = Path(plan['link_filelist'])
            joined.write_bytes(b''.join(Path(f['path']).read_bytes() for f in plan['filelists']))
            with core.CoherentFile(joined) as f:staged[str(joined)] = f.digest()
            require(sum(len(f['ids']) for f in plan['filelists']) == 1042, 'Wrong final filelist count')
            hashes(plan['inputs']); inventory()
            for name,runtime in plan['runtime']['programs'].items():
                require(api('native').runtime_lookup(runtime,plan['cwd']) == plan['runtime_lookup'][name], 'Pre-link ELF lookup shadow changed')
            report['staged_input_sha256'] = dict(staged)
            report['link_executed'] = True
            command('native-driver-link',plan['driver'])
            report['image'] = core.bounded_macho(plan['output'],image=True,symbol_names=['__start'])
            # Output is intentionally outside the pre-link input inventory.
            with core.CoherentFile(plan['output']) as f:staged[plan['output']] = f.digest()
            hashes(plan['inputs']); inventory(); checkpoint()
            report.update(outcome='pass',object_validity='pass',input_qualification='pass',resource_qualification='pass',physical_mapping='UNQUALIFIED',archive_extraction_closure='Actual driver diagnostics retained; no blanket private ABI claim')
        except BaseException as error:
            report.update(outcome='inconclusive' if isinstance(error,core.OwnedCancellation) else 'fail',error=repr(error))
        finally:
            with cancel.cleanup():
                if reserved:
                    try:budget.release()
                    except BaseException as error:report.update(outcome='fail',release_error=repr(error))
                sessions = [c['process']['owned_session'] for c in report['commands'] if c['process'].get('child_started')]
                report['owned_survivors'] = [p for sid in sessions for p in supervise.sample(sid)['owned_processes'] if p['state'] != 'Z']
                if report['owned_survivors']:report['outcome'] = 'fail'
                report['elapsed_seconds'] = time.monotonic()-started
                if out.exists():(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['inspect','plan','execute'])
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--input-sha256',required=True)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--approval-sha256')
    args = parser.parse_args()
    supplied = {'path':str(args.input),'sha256':args.input_sha256}
    if args.mode == 'inspect':result = inspect(supplied)
    elif args.mode == 'plan':result = make_plan(supplied)
    else:
        require(args.approval and args.approval_sha256, 'Exact future root approval required')
        result = execute(read(supplied,True),args.input,args.input_sha256,{'path':str(args.approval),'sha256':args.approval_sha256})
    print(json.dumps(result,indent=2))
    return 0 if result.get('outcome','pass') == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
