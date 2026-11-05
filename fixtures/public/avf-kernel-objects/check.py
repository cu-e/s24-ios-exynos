#!/usr/bin/env python3
"""Source-only executor qualification; existing real objects remain read-only."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('guest_executor', ROOT/'tools/build/avf_kernel_objects.py')
engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--experiment', required=True)
    args = parser.parse_args(); args.main = args.main.resolve(); out = args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():
        raise ValueError('Fresh own worktree artifact output required')
    out.mkdir(parents=True); shutil.copyfile(__file__, out/'executed-check.py')
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail', 'recorded_at': engine.stamp(), 'summary': 'Source-only guest executor controls incomplete', 'commands': [], 'checks': [], 'compiler_started': False, 'guest_executed': False, 'full_kernel_build_or_link': False, 'sdk_qualified': False, 'private_apple_abi_qualified': False}
    def check(name, value):
        report['checks'].append({'name': name, 'pass': bool(value)})
        if not value:
            raise ValueError('Control failed: '+name)
    def rejects(name, callback):
        try:
            callback()
        except (ValueError, OSError, KeyError, IndexError) as error:
            report['checks'].append({'name': name, 'pass': True, 'actual_rejection': repr(error)})
        else:
            raise ValueError('Invalid input was accepted: '+name)
    try:
        pins = engine.load(ROOT/'fixtures/public/avf-kernel-objects/inputs.json')
        supervise = engine.supervisor(args.main)
        argv = [sys.executable, ROOT/'tools/build/avf_kernel_objects.py', '--mode', 'plan', '--main', args.main, '--owner', 'codex-guest-executor-20261106-co', '--task', 'VM-009', '--experiment', args.experiment, '--shard', 'security', '--out', out/'real-plan']
        for name, item in pins.items():
            argv += ['--'+name, item['path'], '--'+name+'-sha256', item['sha256']]
        result = engine.run_child(argv, ROOT, out, 'source-only-real-plan', supervise, timeout=180, admit=False)
        report['commands'].append(result)
        plan_report_path = out/'real-plan/evidence.json'
        check('genuine frozen source-only plan process exit', result['outcome'] == 'pass')
        planned = engine.load(plan_report_path)
        check('genuine plan validates23 security IDs without compiler', planned['outcome'] == 'pass' and len(planned['selected_ids']) == 23 and planned['compiler_started'] is False)
        report['real_plan'] = {'path': str(plan_report_path), 'sha256': engine.sha(plan_report_path)}
        rows = engine.load(pins['manifest']['path'], engine.PIN)
        selectors = engine.load(pins['selectors']['path'], pins['selectors']['sha256'])
        ordered = [row['id'] for row in rows]
        combined = []
        for shard, count in engine.SHARDS.items():
            selection = engine.select(rows, selectors, shard)
            ids = [row['id'] for row in selection]; combined.extend(ids)
            check('deterministic genuine shard '+shard, len(ids) == count and ids == [i for i in ordered if i in set(selectors['shards'][shard])])
        check('ten disjoint shards cover1080 genuine IDs', len(combined) == len(set(combined)) == 1080 and set(combined) == set(ordered))
        rejects('wrong frozen manifest digest', lambda: engine.load(pins['manifest']['path'], '0'*64))
        changed = copy.deepcopy(selectors); changed['shards']['security'][0] = changed['shards']['iokit'][0]
        rejects('overlap/omission between real shards', lambda: engine.select(rows, changed, 'security'))
        changed = copy.deepcopy(selectors); changed['shards']['security'].append(changed['shards']['security'][0])
        rejects('duplicate selection', lambda: engine.select(rows, changed, 'security'))
        rejects('unknown shard', lambda: engine.select(rows, selectors, 'not-a-shard'))
        bad = list(rows); bad[0] = copy.deepcopy(rows[0]); bad[0]['id'] = '../escape.o'
        rejects('path traversal object ID', lambda: engine.validate_graph(bad))
        bad = list(rows); bad[0] = copy.deepcopy(rows[0]); bad[0]['next_owned_compile_argv_template'][bad[0]['next_owned_compile_argv_template'].index('-o')+1] = '/tmp/shared.o'
        rejects('undeclared absolute object output', lambda: engine.validate_graph(bad))
        bad = list(rows); bad[0] = copy.deepcopy(rows[0]); bad[0]['next_owned_compile_argv_template'].append('@response-file')
        rejects('unbound response file', lambda: engine.validate_graph(bad))
        for row in rows:
            actual = engine.expand(row, out/'prospective')
            original = row['next_owned_compile_argv_template']
            check('only declared output tokens change '+row['id'], all(a == b or (a.startswith('@NEXT_OBJECT_DIR@/') or a.startswith('@NEXT_DEPENDENCY_DIR@/')) for a, b in zip(original, actual)) and len(actual) == len(original))
        qualified = engine.load(pins['qualification']['path'], pins['qualification']['sha256'])
        witnesses = []; witness_cwds = {}
        for name in qualified['accepted_object_records']:
            data = engine.load(args.main/name)
            found = data['representative_compiles'] if isinstance(data, dict) else data
            witnesses += found
            if isinstance(data, dict):
                for case in found:
                    for command in data.get('commands', []):
                        if case.get('object') in command.get('argv', []) and '-c' in command.get('argv', []):
                            witness_cwds[case['object']] = command['cwd']
        real = next(x for x in witnesses if x['id'] == 'libkern/OSData.cpo' and x['actual_arm64_object'])
        source_hash = engine.sha(real['source']); original_object = Path(real['object'])
        check('real immutable ARM object witness hash', engine.sha(original_object) == real['object_sha256'])
        info = engine.macho(original_object, True)
        check('actual OSData nonempty allocator metadata', info['allocator_metadata_sections'] and info['arm64_macho_object'])
        rejects('host ELF is not a guest MachO object', lambda: engine.macho(Path(sys.executable).resolve()))
        wrong = out/'wrong-arch.o'; shutil.copyfile(original_object, wrong)
        with wrong.open('r+b') as f:
            f.seek(4); f.write(struct.pack('<I', 0x1000007))
        rejects('actual MachO mutated CPU rejected', lambda: engine.macho(wrong))
        truncated = out/'truncated.o'
        with original_object.open('rb') as f:truncated.write_bytes(f.read(16))
        rejects('truncated real MachO header', lambda: engine.macho(truncated))
        invalid = out/'invalid-load-command.o'; shutil.copyfile(original_object, invalid)
        with invalid.open('r+b') as f:
            f.seek(36); f.write(struct.pack('<I', 0xffffffff))
        rejects('actual load command extent corruption', lambda: engine.macho(invalid))
        plain = next(x for x in witnesses if x['id'] == 'osfmk/startup.o' and x['actual_arm64_object'])
        rejects('required allocator metadata absent in real startup object', lambda: engine.macho(plain['object'], True))
        dep = original_object.with_suffix('.d')
        actual_cwd = witness_cwds[str(original_object)]
        deps = engine.dependencies(dep, actual_cwd, original_object)
        check('actual archived compiler dependency rule contains selected source', str(Path(real['source']).resolve()) in deps)
        dep_copy = out/'actual-compiler.d'; shutil.copyfile(dep, dep_copy)
        object_copy = out/'actual-object.o'; shutil.copyfile(original_object, object_copy)
        actual_inputs = {p: engine.sha(p) for p in deps}
        # Authored cache sidecar around a genuine read-only prior compiler witness.
        # This tests admission only, and is not an earlier executor compilation.
        row = {'id': 'libkern/OSData.cpo', 'input_key': 'source-only-cache-control', 'source': real['source']}
        item = {'id': row['id'], 'source': row['source'], 'outcome': 'pass', 'input_key': row['input_key'], 'object': str(object_copy), 'object_sha256': engine.sha(object_copy), 'object_validation': engine.macho(object_copy, True), 'dependency_file': str(dep_copy), 'dependency_file_sha256': engine.sha(dep_copy), 'dependency_original_target': str(original_object), 'cwd': actual_cwd, 'dependencies': actual_inputs}
        engine.reusable(item, row, {'files': actual_inputs}, engine.Digests())
        check('cache admission around genuine object/dependency bytes', True)
        failed = dict(item, outcome='fail')
        rejects('failed previous outcome never resumes', lambda: engine.reusable(failed, row, {'files': actual_inputs}, engine.Digests()))
        rejects('changed input key never resumes', lambda: engine.reusable(item, dict(row, input_key='changed'), {'files': actual_inputs}, engine.Digests()))
        with object_copy.open('ab') as f:f.write(b'owned-negative-control')
        rejects('changed actual object bytes never resume', lambda: engine.reusable(item, row, {'files': actual_inputs}, engine.Digests()))
        shutil.copyfile(original_object, object_copy)
        with dep_copy.open('a') as f:f.write('\n# owned dependency mutation\n')
        rejects('changed actual dependency file never resumes', lambda: engine.reusable(item, row, {'files': actual_inputs}, engine.Digests()))
        shutil.copyfile(dep, dep_copy)
        altered = dict(actual_inputs); altered[str(Path(real['source']).resolve())] = '0'*64
        rejects('changed dependency binding never resumes', lambda: engine.reusable(item, row, {'files': altered}, engine.Digests()))
        wrongdep = out/'wrong-target.d'; wrongdep.write_text('wrong.o: '+str(real['source'])+'\n')
        rejects('compiler dependency target mismatch', lambda: engine.dependencies(wrongdep, original_object.parent, original_object))
        check('make escape parser independently covers spaces/hash/dollar/colon', engine.make_tokens(r'a\ b c\#d e$$f g\:h') == ['a b', 'c#d', 'e$f', 'g:h'])
        sandbox = out/'sandbox'; sandbox.mkdir(); sentinel = out/'outside-sentinel'; sentinel.write_text('unchanged\n'); (sandbox/'escape').symlink_to(sentinel)
        code = "import pathlib,sys; p=pathlib.Path(sys.argv[1]);p.joinpath('inside').write_text('owned');denied=0\nfor x in [pathlib.Path(sys.argv[2]),p/'escape']:\n try:x.write_text('forbidden')\n except PermissionError:denied+=1\nassert denied==2;print('REAL_WRITE_CONFINEMENT_PASS')"
        result = engine.run_child([sys.executable, '-c', code, sandbox, sentinel], ROOT, sandbox, 'write-confinement', supervise, timeout=5, admit=False)
        report['commands'].append(result)
        check('real child writes owned output but cannot truncate outside/symlink sentinel', result['outcome'] == 'pass' and sentinel.read_text() == 'unchanged\n' and (sandbox/'inside').read_text() == 'owned' and 'REAL_WRITE_CONFINEMENT_PASS' in (sandbox/'write-confinement.stdout.txt').read_text())
        result = engine.run_child([sys.executable, '-c', 'raise SystemExit(7)'], ROOT, sandbox, 'real-error', supervise, timeout=5, admit=False); report['commands'].append(result)
        check('real nonzero child error retained', result['outcome'] == 'fail' and result['exit_code'] == 7)
        result = engine.run_child([sys.executable, '-c', 'import time;print("REAL_SPIN",flush=True);time.sleep(30)'], ROOT, sandbox, 'owned-timeout', supervise, timeout=.4, admit=False); report['commands'].append(result)
        check('real finite timeout and complete owned cleanup', result['outcome'] == 'timeout' and not result['after']['owned_processes'] and 'REAL_SPIN' in (sandbox/'owned-timeout.stdout.txt').read_text())
        check('original real object/source remain unchanged', engine.sha(original_object) == real['object_sha256'] and engine.sha(real['source']) == source_hash)
        report.update(outcome='pass', summary='Actual frozen1080 graph/ten-shard source-only plan and real archived MachO/dependency/metadata checks, changed-input/cache negatives, unprivileged write-confinement and finite process controls passed; no compiler/linker/guest started')
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['controller_memory'] = engine.actual_controller_memory()
        if report['controller_memory']['exec_image_high_water_bytes'] > 256*1024**2:
            report.update(outcome='fail', controller_resource_error='Actual exec-image VmHWM exceeded256MiB')
        report['source_hashes'] = {str(p): engine.sha(p) for p in [Path(__file__), ROOT/'tools/build/avf_kernel_objects.py', ROOT/'fixtures/public/avf-kernel-objects/inputs.json']}
        report['artifact_hashes'] = {str(p): engine.sha(p) for p in out.rglob('*') if p.is_file()};report['artifacts'] = list(report['artifact_hashes']);report['sha256'] = report['artifact_hashes'];engine.write(out/'evidence.json', report)
    print(json.dumps({'outcome': report['outcome'], 'error': report.get('error'), 'checks': len(report['checks']), 'controller_memory': report.get('controller_memory')}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
