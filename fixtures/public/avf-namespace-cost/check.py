#!/usr/bin/env python3
"""Profile real frozen namespace bindings; compare equivalent plans and real FS failures."""
import argparse
import ast
import copy
import cProfile
import datetime
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pstats
import shutil
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
OLD_SHA = '13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47'
OLD_LOOP = "    missing = [name for name in index if any(Path(name).is_relative_to(root) for root in reduced) and name not in files]\n"
NEW_LOOP = """    root_parts = [root.parts for root in reduced]
    missing = []
    for name in index:
        name_parts = Path(name).parts
        if any(name_parts[:len(parts)] == parts for parts in root_parts) and name not in files:
            missing.append(name)
"""


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def module(path, expected):
    if digest(path) != expected:
        raise ValueError('Measured implementation hash changed')
    spec = importlib.util.spec_from_file_location('namespace_'+expected[:12], path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def fresh(path):
    if '..' in path.parts or path.exists():
        raise ValueError('Fresh canonical own output required')
    path = path.resolve()
    if not path.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Output must remain inside the VM035 worktree artifacts')
    path.mkdir(parents=True)
    return path


def pins():
    return json.loads((ROOT/'fixtures/public/avf-namespace-cost/inputs.json').read_text())


def measured_args(engine):
    p = pins()
    reference = engine.load(p['baseline_plan']['path'], p['baseline_plan']['sha256'])
    provenance = reference['provenance']
    args = SimpleNamespace(main=MAIN, shard=reference['shard'])
    for name in ['manifest', 'qualification', 'selectors']:
        setattr(args, name, Path(provenance[name])); setattr(args, name+'_sha256', provenance[name+'_sha256'])
    return args, reference


def measure(args, out):
    engine = module(args.engine, args.engine_sha256)
    shutil.copyfile(args.engine, out/'measured-executor.py')
    profile = cProfile.Profile()
    values, reference = measured_args(engine)
    begin = time.perf_counter(); cpu = time.process_time(); profile.enable()
    plan, inputs, cache = engine.bind(values, out)
    profile.disable(); elapsed = time.perf_counter()-begin; cpu_elapsed = time.process_time()-cpu
    profile.dump_stats(str(out/'profile.pstats'))
    stats = pstats.Stats(profile)
    selected = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        if name in ['namespace', 'relative_to', 'is_relative_to', '__new__', '_parse_args', '_parse_parts', 'get', 'sha', 'stat', 'resolve', 'bind']:
            selected.append(dict(file=filename, line=line, name=name, calls=calls, primitive_calls=primitive, own_seconds=own, cumulative_seconds=cumulative))
    selected.sort(key=lambda row: row['cumulative_seconds'], reverse=True)
    report = dict(kind='host-test', origin='local-host', outcome='pass', recorded_at=engine.stamp(), summary='Actual frozen guest bind measured under cProfile with a fresh per-call Digests instance; no compiler/guest', argv=[sys.executable,*sys.argv], engine={'path':str(args.engine),'sha256':args.engine_sha256}, wall_seconds=elapsed, process_cpu_seconds=cpu_elapsed, cProfile_total_calls=stats.total_calls, methods=selected, bindings_sha256=digest(out/'input-bindings.json'), plan_sha256=digest(out/'execution-plan.json'), namespace_sha256=inputs['sha256'], files=len(inputs['files']), roots=len(inputs['roots']), absent_roots=inputs['absent_search_roots'], selected=len(plan['selected']), compiler_started=False, guest_executed=False, cross_run_validation_cache=False, controller_memory=engine.actual_controller_memory())
    if report['controller_memory']['exec_image_high_water_bytes'] > 256*1024**2:
        report.update(outcome='fail', summary='Actual measured process exceeded256MiB')
    dump(out/'measurement.json', report)
    return report


def plan_tail(engine, args, out, selected, inputs, provenance):
    """Execute the actual unchanged pure bind tail on fully validated graph data.

    This is a value-equivalence projection only, never operational selector
    authorization or a compiler runner. Fresh actual bind has already validated
    every graph source/config/recipe and complete namespace for each engine.
    """
    tree = ast.parse(Path(engine.__file__).read_text())
    bind = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'bind')
    start = next(i for i,node in enumerate(bind.body) if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='provenance' for t in node.targets))
    function = ast.FunctionDef(name='_validated_plan_projection', args=ast.arguments(posonlyargs=[],args=[ast.arg(arg=n) for n in ['args','out','selected','inputs','index_path','qualified','compiler','cache']],kwonlyargs=[],kw_defaults=[],defaults=[]), body=copy.deepcopy(bind.body[start:]), decorator_list=[])
    body = ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])); context = dict(engine.__dict__)
    exec(compile(body, '<actual-unchanged-bind-tail>', 'exec'), context)
    out.mkdir()
    projection_args = copy.copy(args); projection_args.shard = 'ALL1080_VALUE_EQUIVALENCE_ONLY_NOT_AN_OPERATIONAL_SHARD'
    result, unused_inputs, unused_cache = context[function.name](projection_args,out,selected,inputs,Path(provenance['artifact_index']),{'artifact_index_sha256':provenance['artifact_index_sha256']},provenance['compiler'],None)
    return result, ast.dump(ast.Module(body=bind.body[start:],type_ignores=[]),include_attributes=False)


def normalize_plan(value, out):
    # Substitution is limited to the exact two declared outputs in each argv;
    # source flags/provenance/input keys are compared byte-for-byte.
    out = Path(out).resolve()
    value = copy.deepcopy(value)
    for row in value['selected']:
        for option, directory in [('-o','objects'),('-MF','dependencies')]:
            at = row['argv'].index(option)+1
            path = Path(row['argv'][at])
            if not path.is_relative_to(out/directory):
                raise ValueError('Plan output is outside its declared root')
            row['argv'][at] = '@OWNED_OUTPUT@/'+str(path.relative_to(out))
    return value


def filesystem_controls(old, new, out):
    checks = []
    def same(name, callback_old, callback_new, rejection=False):
        answers = []
        for callback in [callback_old, callback_new]:
            try:
                answers.append(('pass',callback()))
            except (ValueError,OSError) as error:
                answers.append((type(error).__name__,str(error)))
        okay = answers[0] == answers[1] and (answers[0][0] != 'pass' if rejection else answers[0][0]=='pass')
        checks.append({'name':name,'pass':okay,'actual':answers})
        if not okay:raise ValueError('Real filesystem equivalence failed:'+name)
    base = out/'real-filesystem'; source = base/'source'; headers = base/'include'; absent = base/'optional'; source.mkdir(parents=True); headers.mkdir()
    (source/'unit.c').write_text('/* owned boundary fixture, never compiled */\n')
    (headers/'input.h').write_text('#define OWNED_FIXTURE 1\n')
    row = {'cwd':str(source),'bound_source':str(source/'unit.c'),'next_owned_compile_argv_template':['not-executed','-I',str(headers),'-I',str(absent)]}
    index = {str(p):digest(p) for p in [source/'unit.c',headers/'input.h']}
    def call(engine, selected_index=None):return engine.namespace([row],index if selected_index is None else selected_index,engine.Digests())
    same('real present and absent namespace',lambda:call(old),lambda:call(new))
    missing = dict(index); missing[str(headers/'missing-first.h')]='0'*64;missing[str(headers/'missing-second.h')]='0'*64
    same('missing indexed headers and first-error order',lambda:call(old,missing),lambda:call(new,missing),True)
    similar = dict(index);similar[str(base/'include-sibling/ghost.h')]='0'*64
    same('component-prefix sibling is not contained',lambda:call(old,similar),lambda:call(new,similar))
    exact = dict(index);exact[str(headers)]='0'*64
    same('exact root directory key retains missing-input rejection',lambda:call(old,exact),lambda:call(new,exact),True)
    parent_component = dict(index);parent_component[str(headers)+'/../outside/ghost.h']='0'*64
    same('lexical parent-component index semantics unchanged',lambda:call(old,parent_component),lambda:call(new,parent_component),True)
    shadow = headers/'shadow.h';shadow.write_text('owned unindexed shadow\n')
    same('new unindexed header rejected',lambda:call(old),lambda:call(new),True);shadow.unlink()
    expected = (headers/'input.h').read_text();(headers/'input.h').write_text('changed actual header\n')
    same('changed actual header digest rejected',lambda:call(old),lambda:call(new),True);(headers/'input.h').write_text(expected)
    before = call(old)['sha256'];absent.mkdir()
    same('appearing empty optional root changes bindings identically',lambda:call(old),lambda:call(new))
    if call(new)['sha256']==before:raise ValueError('Optional-root appearance was lost')
    checks.append({'name':'actual optional-root appearance changes namespace digest','pass':True})
    (absent/'unexpected.h').write_text('owned optional shadow\n')
    same('appearing optional-root header rejected',lambda:call(old),lambda:call(new),True);(absent/'unexpected.h').unlink();absent.rmdir()
    outside=base/'outside';outside.mkdir();(outside/'target.h').write_text('owned file-symlink target\n')
    alias=headers/'directory-link';alias.symlink_to(outside,target_is_directory=True)
    same('real directory symlink rejected',lambda:call(old),lambda:call(new),True);alias.unlink()
    link=headers/'file-link.h';link.symlink_to(outside/'target.h');linked=dict(index);linked[str(link)]=digest(link)
    same('qualified file-symlink behavior retained',lambda:call(old,linked),lambda:call(new,linked));link.unlink()
    for name,engine in [('original',old),('candidate',new)]:
        path=base/('ctime-'+name);path.write_text('A');cache=engine.Digests();first=cache.get(path);stat=path.stat();time.sleep(.01);path.write_text('B');os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns));second=cache.get(path)
        okay=first!=second and second==digest(path) and path.stat().st_mtime_ns==stat.st_mtime_ns and path.stat().st_ctime_ns!=stat.st_ctime_ns
        checks.append({'name':name+' actual ctime change with restored mtime rehashes','pass':okay})
        if not okay:raise ValueError('Actual ctime invalidation lost')
    return checks


def same_bytes(left, right):
    with Path(left).open('rb') as a, Path(right).open('rb') as b:
        while True:
            x, y = a.read(1024**2), b.read(1024**2)
            if x != y:return False
            if not x:return True


def compare(args,out):
    original=json.loads(Path(args.original).read_text());candidate=json.loads(Path(args.candidate).read_text())
    old=module(Path(original['engine']['path']),OLD_SHA);new=module(Path(candidate['engine']['path']),candidate['engine']['sha256'])
    old_text=Path(old.__file__).read_text();new_text=Path(new.__file__).read_text()
    if old_text.count(OLD_LOOP)!=1 or old_text.replace(OLD_LOOP,NEW_LOOP)!=new_text:
        raise ValueError('Candidate changed code outside the single equivalent membership loop')
    checks=[{'name':'only the declared index membership loop changed','pass':True}]
    old_dir=Path(args.original).parent;new_dir=Path(args.candidate).parent
    old_bindings=old.load(old_dir/'input-bindings.json',original['bindings_sha256']);new_bindings=new.load(new_dir/'input-bindings.json',candidate['bindings_sha256'])
    if (old_dir/'input-bindings.json').read_bytes()!=(new_dir/'input-bindings.json').read_bytes():raise ValueError('Actual namespace binding bytes changed')
    checks.append({'name':'actual complete namespace/input-binding bytes identical','pass':True,'files':len(old_bindings['files']),'roots':len(old_bindings['roots']),'sha256':old_bindings['sha256']})
    ref=pins();ref_plan=old.load(ref['baseline_plan']['path'],ref['baseline_plan']['sha256']);ref_out=Path(ref['baseline_plan']['path']).parent
    old_plan=old.load(old_dir/'execution-plan.json',original['plan_sha256']);new_plan=new.load(new_dir/'execution-plan.json',candidate['plan_sha256'])
    normalized_files=[]
    for label,plan,root in [('reference',ref_plan,ref_out),('original',old_plan,old_dir),('candidate',new_plan,new_dir)]:
        path=out/(label+'-normalized-plan.json');dump(path,normalize_plan(plan,root));normalized_files.append(path)
    if not same_bytes(normalized_files[0],normalized_files[1]) or not same_bytes(normalized_files[1],normalized_files[2]):raise ValueError('Actual frozen selected plan bytes differ beyond output roots')
    if digest(old_dir/'input-bindings.json')!=ref['baseline_bindings']['sha256']:raise ValueError('Fresh actual bindings differ from frozen VM018')
    checks.append({'name':'reference VM018 and both fresh actual13-ID plans identical modulo outputs','pass':True})
    cache=old.Digests()
    for path,expected in old_bindings['files'].items():
        if cache.get(path)!=expected:raise ValueError('Frozen input changed after measurement:'+path)
    checks.append({'name':'all actual input files independently rehashed after both measurements','pass':True})
    values,unused=measured_args(old);rows=old.load(values.manifest,values.manifest_sha256);selectors=old.load(values.selectors,values.selectors_sha256)
    ids=[]
    for shard in old.SHARDS:
        a=old.select(rows,selectors,shard);b=new.select(rows,selectors,shard)
        if a!=b:raise ValueError('Frozen shard selection changed')
        ids.extend(r['id'] for r in a)
    if len(ids)!=1080 or len(set(ids))!=1080:raise ValueError('Whole graph selection coverage changed')
    projected_old,tail_old=plan_tail(old,values,out/'all1080-original',rows,old_bindings,old_plan['provenance'])
    projected_new,tail_new=plan_tail(new,values,out/'all1080-candidate',rows,new_bindings,new_plan['provenance'])
    for label,plan in [('original',projected_old),('candidate',projected_new)]:
        dump(out/('all1080-'+label+'-normalized.json'),normalize_plan(plan,out/('all1080-'+label)))
    if tail_old!=tail_new or not same_bytes(out/'all1080-original-normalized.json',out/'all1080-candidate-normalized.json') or len(projected_old['selected'])!=1080:raise ValueError('1080 actual pure-tail recipe/input-key projection changed')
    checks.append({'name':'all1080 validated graph recipe/input keys and argv byte-identical modulo outputs via unchanged actual bind tail','pass':True,'scope':'Value projection after actual shared validation; not operational extra shard or cross-run validation cache'})
    checks+=filesystem_controls(old,new,out)
    return dict(kind='host-test',origin='local-host',outcome='pass',recorded_at=old.stamp(),summary='Actual frozen namespace/selected-plan equality and1080 unchanged-tail key/argv projection plus real filesystem negatives pass; only one equivalent index iteration changed; no compiler/guest/cache shortcut',argv=[sys.executable,*sys.argv],checks=checks,original_measurement={'path':str(args.original),'sha256':digest(args.original)},candidate_measurement={'path':str(args.candidate),'sha256':digest(args.candidate)},profiled_wall_seconds={'original':original['wall_seconds'],'candidate':candidate['wall_seconds']},profiled_process_cpu_seconds={'original':original['process_cpu_seconds'],'candidate':candidate['process_cpu_seconds']},compiler_started=False,guest_executed=False,cross_run_validation_cache=False,controller_memory=old.actual_controller_memory())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--phase',choices=['measure','supervised-measure','compare'],required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--engine',type=Path);parser.add_argument('--engine-sha256');parser.add_argument('--original',type=Path);parser.add_argument('--candidate',type=Path);args=parser.parse_args();out=fresh(args.out)
    shutil.copyfile(__file__,out/'executed-check.py')
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),summary='Namespace cost measurement/verification incomplete',argv=[sys.executable,*sys.argv],commands=[],compiler_started=False,guest_executed=False)
    try:
        if args.phase=='measure':report=measure(args,out)
        elif args.phase=='compare':report=compare(args,out)
        else:
            frozen=pins()['original_executor'];guard=module(Path(frozen['path']),OLD_SHA);supervise=guard.supervisor(MAIN)
            command=[sys.executable,Path(__file__).resolve(),'--phase','measure','--engine',args.engine,'--engine-sha256',args.engine_sha256,'--out',out/'measurement']
            result=guard.run_child(command,ROOT,out,'measure',supervise,timeout=300,admit=True);report['commands'].append(result)
            if result['outcome']!='pass':raise ValueError('Actual finite measured child failed:'+result['outcome'])
            child=guard.load(out/'measurement/measurement.json')
            if child['outcome']!='pass':raise ValueError('Actual measured child did not qualify')
            report.update(outcome='pass',summary='Actual source-only bind measurement completed through unchanged reviewed finite guard; no compiler/guest',measurement={'path':str(out/'measurement/measurement.json'),'sha256':digest(out/'measurement/measurement.json')},wall_seconds=child['wall_seconds'],process_cpu_seconds=child['process_cpu_seconds'],engine=child['engine'])
    except Exception as error:report['error']=repr(error)
    finally:
        guard=module(Path(pins()['original_executor']['path']),OLD_SHA);report['controller_memory']=guard.actual_controller_memory()
        if report['controller_memory']['exec_image_high_water_bytes']>256*1024**2:report.update(outcome='fail',controller_resource_error='Actual image VmHWM exceeds256MiB')
        report['fixture_sha256']=digest(__file__);report['artifact_hashes']={str(p):digest(p) for p in out.rglob('*') if p.is_file()};report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];dump(out/'evidence.json',report)
    print(json.dumps({k:report.get(k) for k in ['outcome','error','wall_seconds','process_cpu_seconds','profiled_wall_seconds','controller_memory']},indent=2));return report['outcome']!='pass'


if __name__=='__main__':raise SystemExit(main())
