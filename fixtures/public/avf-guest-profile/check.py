#!/usr/bin/env python3
"""Two genuine source-only profile plans and targeted consumer-boundary controls."""
import argparse
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT/'tools/build/avf_kernel_objects.py'
spec = importlib.util.spec_from_file_location('guest_profiles', TOOL)
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); args.main = args.main.resolve(); out = args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():raise ValueError('Fresh own output required')
    out.mkdir(parents=True); checks = []; commands = []
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail', 'recorded_at': e.stamp(),
              'argv': [sys.executable, *sys.argv], 'checks': checks, 'commands': commands,
              'compiler_started': False, 'guest_executed': False, 'full_common_run': False}
    def check(name, passed):
        checks.append({'name': name, 'pass': bool(passed)})
        if not passed:raise ValueError('Control failed: '+name)
    def rejects(name, callback):
        try:callback()
        except (ValueError, KeyError, OSError, TypeError) as error:checks.append({'name': name, 'pass': True, 'rejection': repr(error)})
        else:raise ValueError('Invalid input accepted: '+name)
    try:
        old = e.load(args.main/'fixtures/public/avf-kernel-objects/inputs.json')
        base = args.main/'worktrees/vm-038-20261106/docs/procedures/avf-firehose-namespace/qualification-session1'
        new = {'manifest': {'path': str(base/'next-full-object-manifest.json'), 'sha256': e.FIREHOSE_MANIFEST},
               'qualification': {'path': str(base/'qualified-component.json'), 'sha256': e.FIREHOSE_QUALIFICATION},
               'selectors': {'path': str(base/'object-shards.json'), 'sha256': e.FIREHOSE_SELECTORS}}
        supervise = e.supervisor(args.main)
        plans = {}
        def cli(label, pins, prospective=False):
            target = out/label
            argv = [sys.executable, TOOL, '--mode', 'plan', '--main', args.main, '--task', 'VM-039',
                    '--owner', 'codex-guest-profile-20261106-ej', '--experiment', args.experiment, '--shard', 'security', '--out', target]
            for key, item in pins.items():argv += ['--'+key, item['path'], '--'+key+'-sha256', item['sha256']]
            if prospective:argv += ['--resource-profile', e.PROJECT_PROFILE]
            result = e.run_child(argv, ROOT, out, label, supervise, timeout=120, admit=False)
            commands.append(result)
            return target, result
        for label, pins, prospective in [('legacy-plan', old, False), ('firehose-plan', new, True)]:
            target, result = cli(label, pins, prospective)
            check('actual source-only CLI '+label+' exits0', result['outcome'] == 'pass')
            evidence = e.load(target/'evidence.json'); plan = e.load(target/'execution-plan.json')
            check(label+' validates23 genuine security recipes without compiler', evidence['outcome'] == 'pass' and len(plan['selected']) == 23 and evidence['compiler_started'] is False)
            plans[label] = plan
        bad = copy.deepcopy(new); bad['qualification']['sha256'] = '0'*64
        target, failed = cli('mismatched-descriptor-cli', bad, True)
        failure = e.load(target/'evidence.json')
        check('actual CLI mismatched descriptor rejects before any compiler', failed['outcome'] == 'fail' and failure['compiler_started'] is False and 'two exact independently accepted' in failure['error'])
        legacy = plans['legacy-plan']; current = plans['firehose-plan']
        prior = args.main/'worktrees/vm-009-20261106/artifacts/avf-kernel-objects/controls-session2/real-plan'
        expected_plan_bytes = (prior/'execution-plan.json').read_bytes().replace(str(prior).encode(), str(out/'legacy-plan').encode())
        check('legacy complete plan bytes identical except declared owned output prefix', (out/'legacy-plan/execution-plan.json').read_bytes() == expected_plan_bytes)
        check('legacy complete input-binding bytes unchanged', (out/'legacy-plan/input-bindings.json').read_bytes() == (prior/'input-bindings.json').read_bytes())
        check('legacy provenance namespace retained', legacy['provenance']['namespace_sha256'] == e.LEGACY_NAMESPACE)
        check('new manifest namespace schema and project-budget profile explicit', current['provenance']['manifest_sha256'] == e.FIREHOSE_MANIFEST and current['provenance']['namespace_sha256'] == e.FIREHOSE_NAMESPACE and current['source_profile']['schema'] == e.FIREHOSE_SCHEMA and current['resource_profile'] == e.PROJECT_PROFILE)
        keys = e.load(base/'object-input-keys.json')['keys']; key_map = {row['id']: row['input_key'] for row in keys}
        check('new actual plan uses exact frozen namespace input keys', all(row['input_key'] == key_map[row['id']] for row in current['selected']))
        check('all23 selected new keys differ from genuine legacy keys', all(a['id'] == b['id'] and a['input_key'] != b['input_key'] for a, b in zip(legacy['selected'], current['selected'])))
        old_args = SimpleNamespace(**{k+'_sha256': v['sha256'] for k, v in old.items()})
        new_args = SimpleNamespace(**{k+'_sha256': v['sha256'] for k, v in new.items()})
        for key in ['manifest_sha256', 'qualification_sha256', 'selectors_sha256']:
            changed = copy.copy(new_args); setattr(changed, key, getattr(old_args, key))
            rejects('mixed accepted profiles reject '+key, lambda: e.accepted_profile(changed))
        changed = copy.copy(old_args); changed.manifest_sha256 = 'f'*64
        rejects('arbitrary manifest override rejected', lambda: e.accepted_profile(changed))
        e.resume_profile({'provenance': legacy['provenance']}, legacy)
        check('same-profile legacy resume identity allowed', True)
        rejects('old object capsule cannot resume new profile', lambda: e.resume_profile({'provenance': legacy['provenance']}, current))
        rejects('new object capsule cannot resume legacy profile', lambda: e.resume_profile({'provenance': current['provenance']}, legacy))
        task = {'id': 'VM-039', 'paths': ['tools/build/avf_kernel_objects.py', 'fixtures/public/avf-guest-profile', 'docs/procedures/avf-guest-profile']}
        check('039 literal tooling authorizes source-only plan', e.task_shards(task, 'plan', 'security')['source_only_tooling_exception'])
        rejects('039 tooling never authorizes execution', lambda: e.task_shards(task, 'execute', 'security'))
        rejects('039 incomplete literal reservation rejected', lambda: e.task_shards(dict(task, paths=task['paths'][:-1]), 'plan', 'security'))
        raw = subprocess.run(['git', 'show', '951679e13034b4d7f339edf99058020a028b2353:tools/build/avf_kernel_objects.py'], cwd=args.main, stdout=subprocess.PIPE, check=True).stdout
        accepted = out/'accepted-efe.py'; accepted.write_bytes(raw)
        check('accepted budget source witness EFE exact', e.sha(accepted) == 'efe908ff5b6321ea1e456306a3094f9188cc501d066bcc78b435b500d56783e6')
        def node(text, name):return next(x for x in ast.parse(text).body if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name == name)
        source = TOOL.read_text()
        for name in ['ProjectBudget', 'project_approval', 'approval', 'run_child', 'stable_memory', 'load_project', 'process_table', 'owned_processes', 'landlock', 'namespace', 'expand', 'reusable', 'validate_graph']:
            check('accepted AST unchanged '+name, ast.dump(node(raw, name)) == ast.dump(node(source, name)))
        # These are bounded source comparisons and own temporary filesystem
        # cases; no old or new accepted namespace is edited for a negative.
        rules = e.profile_rules(args.main)
        old_rows = e.load(old['manifest']['path'], e.PIN); new_rows = e.load(new['manifest']['path'], e.FIREHOSE_MANIFEST)
        descriptor = e.load(new['qualification']['path'], e.FIREHOSE_QUALIFICATION)
        old_root = Path(descriptor['old_root']['path']); new_root = Path(descriptor['new_root']['path'])
        for field in ['bound_source_sha256', 'configuration_sha256', 'generated_input']:
            mutated = new_rows.copy(); mutated[0] = copy.deepcopy(new_rows[0])
            mutated[0][field] = not mutated[0][field] if field == 'generated_input' else '0'*64
            rejects('same-slot transition rejects changed '+field, lambda: rules.validate_transition(old_rows, mutated, old_root, new_root))
        mutated = new_rows.copy(); mutated[0] = copy.deepcopy(new_rows[0]); mutated[0]['next_owned_compile_argv_template'].append('-DUNAPPROVED=1')
        rejects('new compiler flag rejected', lambda: rules.validate_transition(old_rows, mutated, old_root, new_root))
        mutated = new_rows.copy(); mutated[0] = copy.deepcopy(new_rows[0]); mutated[0]['next_owned_compile_argv_template'] = old_rows[0]['next_owned_compile_argv_template']
        rejects('retired root substitution omission rejected', lambda: rules.validate_transition(old_rows, mutated, old_root, new_root))
        check('all1080 sources/config/IDs and generated55 retained', [r['id'] for r in old_rows] == [r['id'] for r in new_rows] and sum(r['generated_input'] is True for r in new_rows) == 55)
        sandbox = out/'namespace-controls'; sandbox.mkdir(); installed = sandbox/'kernel'; (installed/'os').mkdir(parents=True)
        header = installed/'os/firehose_buffer_private.h'; original_header = new_root/'os/firehose_buffer_private.h'
        header.write_bytes(original_header.read_bytes()); digest = e.sha(original_header)
        rules.verify_overlay(installed, digest); check('own exact one-header root accepted', True)
        header.unlink(); rejects('absent installed header rejected', lambda: rules.verify_overlay(installed, digest))
        header.symlink_to(original_header); rejects('installed header symlink rejected', lambda: rules.verify_overlay(installed, digest)); header.unlink()
        header.write_bytes(original_header.read_bytes()); (installed/'shadow.h').write_text('owned negative')
        rejects('extra installed shadow file rejected', lambda: rules.verify_overlay(installed, digest)); (installed/'shadow.h').unlink()
        link = sandbox/'root-alias'; link.symlink_to(installed, target_is_directory=True)
        rejects('install root symlink rejected', lambda: e.canonical_output_path(link))
        shadow = sandbox/'source'; shadow.write_text('changed owned source')
        rejects('source/context artifact mutation rejected', lambda: e.bound_profile_file({'path': str(shadow), 'sha256': digest}))
        fake_row = copy.deepcopy(new_rows[0]); fake_row['cwd'] = str(installed); fake_row['bound_source'] = str(header); fake_row['next_owned_compile_argv_template'] = ['-I', str(installed), '-c', str(header)]
        expected_files = {str(header): digest}
        e.namespace([fake_row], expected_files, e.Digests()); check('owned namespace closure positive', True)
        (installed/'unexpected.h').write_text('owned shadow')
        rejects('namespace rejects newly shadowing file', lambda: e.namespace([fake_row], expected_files, e.Digests()))
        check('historical retired root still physically absent', not os.path.lexists(old_root))
        check('new exported header remains unchanged', e.sha(original_header) == digest)
        report.update(outcome='pass', summary='Genuine old/new CLI plans, exact legacy plan/input bytes, unchanged EFE budget AST, frozen new keys and targeted profile/root/transition/resume controls passed; no compiler or guest')
    except Exception as error:report['error'] = repr(error)
    finally:
        report['controller_memory'] = e.actual_controller_memory()
        report['source_hashes'] = {str(p): e.sha(p) for p in [TOOL, Path(__file__)]}
        report['artifact_hashes'] = {str(p): e.sha(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()}
        report['artifacts'] = list(report['artifact_hashes']); report['sha256'] = report['artifact_hashes']; e.write(out/'evidence.json', report)
    print(json.dumps({'outcome': report['outcome'], 'checks': len(checks), 'error': report.get('error')}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':raise SystemExit(main())
