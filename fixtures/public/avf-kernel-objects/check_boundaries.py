#!/usr/bin/env python3
"""Focused REV025 output/owner regression controls; all writes are owned fixtures."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
FROZEN = '3ffde8d3b7f3737a9456946a9212866cb421b031'
OLD_SHA = '37a0b6d57e743bbf652f69052378a092c3fdb3a1c6b3ae8b64fccb8a5896b464'
TOOL_PATHS = ['tools/build/avf_kernel_objects.py', 'fixtures/public/avf-kernel-objects', 'docs/procedures/avf-kernel-objects']


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if '..' in args.out.parts or args.out.exists():
        raise ValueError('Fresh canonical own artifact output required')
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Only own artifact fixtures may be written')
    out.mkdir(parents=True); shutil.copyfile(__file__, out/'executed-boundaries.py')
    engine = module('corrected_guest_objects', ROOT/'tools/build/avf_kernel_objects.py')
    shutil.copyfile(ROOT/'tools/build/avf_kernel_objects.py', out/'corrected-executor.py')
    report = dict(kind='host-test', origin='local-host', outcome='fail', recorded_at=engine.stamp(), summary='Focused source-only owner/output boundary checks incomplete', commands=[], checks=[], compiler_started=False, guest_executed=False, full_kernel_build_or_link=False)
    def check(name, value, **facts):
        report['checks'].append(dict(name=name, passed=bool(value), **facts))
        if not value:
            raise ValueError('Boundary control failed: '+name)
    def reject(name, callback, requested):
        try:
            callback()
        except ValueError as error:
            check(name, not requested.exists(), rejection=str(error), requested=str(requested), created=False)
        else:
            raise ValueError('Boundary accepted invalid input: '+name)
    try:
        command = ['git', '-C', str(ROOT), 'show', FROZEN+':tools/build/avf_kernel_objects.py']
        result = subprocess.run(command, env=dict(os.environ, **engine.GUARDS), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        digest = hashlib.sha256(result.stdout).hexdigest()
        report['commands'].append(dict(argv=command, exit_code=result.returncode, stdout_sha256=digest, stderr_sha256=hashlib.sha256(result.stderr).hexdigest(), environment_overrides=engine.GUARDS))
        check('original frozen source retrieved unchanged', result.returncode == 0 and digest == OLD_SHA)
        old_path = out/'original-frozen-executor.py'; old_path.write_bytes(result.stdout)
        old = module('original_guest_objects', old_path)
        fake = out/'owned-fixture-main'; (fake/'state').mkdir(parents=True)
        workspace = fake/'worktrees/fixture-owner'; (workspace/'artifacts').mkdir(parents=True)
        template = dict(id='VM-010', status='in_progress', owner='owned-boundary-fixture', worktree='worktrees/fixture-owner', paths=['fixtures/public/avf-object-shards/bsd-core', 'docs/procedures/avf-object-shards/bsd-core'])
        def configure(task=None, mode='plan', shard='bsd-core', path=None, experiment_task=None):
            task = copy.deepcopy(template if task is None else task)
            experiment = dict(id='OWNED-FIXTURE-EXPERIMENT', task=experiment_task or task['id'], owner=task['owner'], status='planned')
            (fake/'state/lab.json').write_text(json.dumps(dict(tasks=[task], experiments=[experiment])))
            return SimpleNamespace(main=fake, task=task['id'], owner=task['owner'], experiment=experiment['id'], mode=mode, shard=shard, out=path or workspace/'artifacts/new')
        traversal = workspace/'artifacts/../original-escaped-output'
        returned = old.owned_out(configure(path=traversal))
        check('original traversal bug reproduced wholly inside owned fixture', returned.exists() and not returned.resolve().is_relative_to(workspace/'artifacts'), returned=str(returned), resolved=str(returned.resolve()))
        cross = workspace/'artifacts/original-cross-shard'
        returned = old.owned_out(configure(mode='execute', shard='security', path=cross))
        check('original cross-shard execute admission reproduced without compiler', returned == cross and returned.is_dir())
        generic = dict(template, id='VM-009', paths=TOOL_PATHS)
        original_generic = workspace/'artifacts/original-tooling-execute'
        returned = old.owned_out(configure(generic, mode='execute', shard='security', path=original_generic))
        check('original generic tooling execute admission reproduced without compiler', returned == original_generic and returned.is_dir())
        paths = [workspace/'artifacts/../corrected-escape', workspace/'artifacts/x/../../corrected-escape2', workspace/'artifacts-sibling/incorrect-prefix', workspace/'corrected-outside']
        for index, path in enumerate(paths):
            arguments = configure(path=path)
            reject('corrected canonical containment negative '+str(index), lambda a=arguments: engine.owned_out(a), path)
        path = workspace/'artifacts/corrected-cross-shard'
        arguments = configure(mode='execute', shard='security', path=path)
        reject('bsd-core owner cannot execute security', lambda: engine.owned_out(arguments), path)
        for mode in ['plan', 'execute']:
            path = workspace/('artifacts/wrong-shard-'+mode)
            arguments = configure(mode=mode, shard='security', path=path)
            reject('literal shard restriction applies to '+mode, lambda a=arguments: engine.owned_out(a), path)
        for index, missing in enumerate(template['paths']):
            task = dict(template, paths=[x for x in template['paths'] if x != missing])
            path = workspace/('artifacts/missing-reservation-'+str(index))
            arguments = configure(task, mode='execute', path=path)
            reject('both literal reservations required '+str(index), lambda a=arguments: engine.owned_out(a), path)
        for shard in engine.SHARDS:
            task = dict(template, id='SHARD-FIXTURE-'+shard, paths=['fixtures/public/avf-object-shards/'+shard, 'docs/procedures/avf-object-shards/'+shard])
            path = workspace/('artifacts/valid-'+shard)
            arguments = configure(task, mode='execute', shard=shard, path=path)
            returned = engine.owned_out(arguments)
            check('all ten exact shard reservation mappings '+shard, returned == path.resolve() and returned.is_dir() and arguments.ownership_binding['authorized_shards'] == [shard] and arguments.ownership_binding['source_only_tooling_exception'] is False)
        for mode in ['plan', 'execute']:
            path = workspace/('artifacts/tooling-'+mode)
            arguments = configure(generic, mode=mode, shard='security', path=path)
            if mode == 'plan':
                returned = engine.owned_out(arguments)
                check('explicit VM009 plan-only exception', returned == path.resolve() and arguments.ownership_binding['authorized_shards'] == [] and arguments.ownership_binding['source_only_tooling_exception'] is True)
            else:
                reject('VM009 can never execute shard compilers', lambda a=arguments: engine.owned_out(a), path)
        path = workspace/'artifacts/reviewer-execute'
        arguments = configure(dict(generic, id='REV-025'), mode='execute', shard='security', path=path)
        reject('generic reviewer/tool reservations confer no shard authority', lambda: engine.owned_out(arguments), path)
        for index, value in enumerate(['/tmp/unowned-fixture', 'worktrees/fixture-owner/../other', '../worktrees/fixture-owner', 'worktrees']):
            path = workspace/('artifacts/wrong-ledger-path-'+str(index))
            arguments = configure(dict(template, worktree=value), path=path)
            reject('noncanonical or unowned ledger worktree '+str(index), lambda a=arguments: engine.owned_out(a), path)
        alias = workspace/'artifacts/alias'; target = workspace/'outside-symlink-target'; target.mkdir(); alias.symlink_to(target, target_is_directory=True)
        path = alias/'new-attempt'; arguments = configure(path=path)
        reject('symlink output ancestry refused before any target write', lambda: engine.owned_out(arguments), path)
        check('symlink outside target unchanged', list(target.iterdir()) == [])
        arguments = configure(path=workspace/'artifacts/existing'); arguments.out.mkdir()
        try:
            engine.owned_out(arguments)
        except ValueError as error:
            check('existing output refused without overwrite', arguments.out.is_dir() and list(arguments.out.iterdir()) == [], rejection=str(error))
        else:
            raise ValueError('Existing output accepted')
        unknown = workspace/'artifacts/unknown-shard'; arguments = configure(shard='unknown', path=unknown)
        reject('unknown shard refused before mkdir', lambda: engine.owned_out(arguments), unknown)
        wrong_experiment = workspace/'artifacts/wrong-experiment'; arguments = configure(path=wrong_experiment, experiment_task='OTHER-TASK')
        reject('experiment must belong to original task', lambda: engine.owned_out(arguments), wrong_experiment)
        old_ast = ast.parse(result.stdout.decode()); new_text = (ROOT/'tools/build/avf_kernel_objects.py').read_text(); new_ast = ast.parse(new_text)
        def original_parts(tree, newer=False):
            parts = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == 'owned_out' or (newer and node.name in ['task_shards', 'canonical_output_path']):
                        continue
                    if node.name == 'main' and newer:
                        text = ast.get_source_segment(new_text, node).replace("'ownership_binding': args.ownership_binding, ", '')
                        node = ast.parse(text).body[0]
                parts.append(ast.dump(node, include_attributes=False))
            return parts
        check('all graph/hash/recipe/dependency/MachO/resource/resume code AST unchanged', original_parts(old_ast) == original_parts(new_ast, True))
        report.update(outcome='pass', summary='Frozen traversal and cross-shard/tooling admission defects reproduced only in owned temporary fixtures; corrected canonical/no-parent/no-symlink output plus literal two-path shard ownership and VM009 plan-only exception pass; unchanged executor algorithms verified by AST; no compiler or guest')
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['controller_memory'] = engine.actual_controller_memory()
        if report['controller_memory']['exec_image_high_water_bytes'] > 256*1024**2:
            report.update(outcome='fail', controller_resource_error='Current image VmHWM exceeds256MiB')
        report['source_hashes'] = {str(p): engine.sha(p) for p in [ROOT/'tools/build/avf_kernel_objects.py', Path(__file__)]}
        report['artifact_hashes'] = {str(p): engine.sha(p) for p in out.rglob('*') if p.is_file()}
        report['artifacts'] = list(report['artifact_hashes']); report['sha256'] = report['artifact_hashes']; engine.write(out/'evidence.json', report)
    print(json.dumps(dict(outcome=report['outcome'], error=report.get('error'), checks=len(report['checks']), controller_memory=report['controller_memory']), indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
