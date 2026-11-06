#!/usr/bin/env python3
"""Only STR018's separately root-admitted four compiles and two archives."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE / 'header_only.py'
BASE_SHA = '97d201ce8f6cfee9ca2c222fc11a8fe584eaa08155dbcf8e1c9633ae6e41bad2'
IDS = ['compile-firehose', 'pthread-kern_init', 'pthread-kern_support',
       'pthread-kern_synch', 'archive-firehose_kernel', 'archive-pthread_kext']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_base():
    raw = BASE.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == BASE_SHA, 'Changed reviewed local API')
    spec = importlib.util.spec_from_file_location('str018_header_source_api', BASE)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(BASE), 'exec'), module.__dict__)
    return module


def remap(value, mapping):
    if isinstance(value, str):
        for old, new in mapping.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [remap(row, mapping) for row in value]
    if isinstance(value, dict):
        return {key: remap(row, mapping) for key, row in value.items()}
    return value


def regular(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_size > 0,
            'Missing/nonregular/empty actual product: ' + str(path))
    return info.st_size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-plan', type=Path, required=True)
    ap.add_argument('--source-plan-sha256', required=True)
    ap.add_argument('--approval', type=Path, required=True)
    ap.add_argument('--approval-sha256', required=True)
    args = ap.parse_args()
    base = load_base()
    common, core = base.module(base.COMMON), base.module(base.CORE)
    plan = common.load_project(args.source_plan, args.source_plan_sha256)
    require(plan['schema'] == 'str018-provider-objects-plan-v1'
            and plan['executor_sha256'] == sha(__file__)
            and plan['helper_sha256'] == base.PINS, 'Wrong reviewed object caller/plan')
    require(plan['whole_seconds'] == 600 and plan['max_jobs'] == 1
            and plan['max_owned_rss_bytes'] == 512 * 1024**2, 'Wrong serial resource bounds')
    args.main = base.MAIN
    for key in ['task', 'owner', 'experiment', 'shard']:
        setattr(args, key, plan[key])
    require((args.task, args.owner, args.shard) == ('STR-018',
            'codex-e1s-development-providers-20261106-sr18', 'providers-objects'), 'Wrong owner/scope')
    args.out = common.canonical_output_path(plan['actual_output'])
    state = common.load_project(base.MAIN / 'state/lab.json')
    task = next(row for row in state['tasks'] if row['id'] == args.task)
    wt = Path(task['worktree'])
    if not wt.is_absolute():
        wt = base.MAIN / wt
    require(task['status'] == 'in_progress' and task['owner'] == args.owner
            and args.out.is_relative_to(wt / 'artifacts/e1s-development-providers')
            and not args.out.exists(), 'Fresh original-owned output required')
    require(any(row['id'] == args.experiment and row['task'] == args.task
                and row['owner'] == args.owner and row['status'] == 'planned'
                for row in state['experiments']), 'Exact planned experiment required')
    full = common.load_project(plan['provider_full_plan']['path'], plan['provider_full_plan']['sha256'])
    header = common.load_project(plan['actual_header_descriptor']['path'], plan['actual_header_descriptor']['sha256'])
    manifest = common.load_project(plan['actual_header_manifest']['path'], plan['actual_header_manifest']['sha256'])
    require(header['outcome'] == manifest['outcome'] == 'pass'
            and header['header_count'] == len(manifest['headers']) == 315
            and len(manifest['native_filter_signatures']) == 32
            and manifest['provider_plan'] == plan['provider_full_plan']
            and manifest['own_reservation_released'] and manifest['root_released']
            and manifest['root_owned_survivors'] == [],
            'Actual accepted header phase required')
    header_pins = {row['path']: row['sha256'] for row in [*manifest['headers'],
                   *manifest['native_filter_signatures'], *manifest['actual_MIG_copies'],
                   manifest['firehose_export']]}
    require(plan['header_product_sha256'] == header_pins, 'Wrong actual header bindings')
    old = full['actual_output']
    mapping = {old + '/native-bsd': str(args.out / 'native-bsd'),
               old + '/objects': str(args.out / 'objects'),
               old + '/public-availability': str(args.out / 'public-availability'),
               old + '/libfirehose_kernel.a': str(args.out / 'libfirehose_kernel.a'),
               old + '/libpthread_kext.a': str(args.out / 'libpthread_kext.a')}
    commands = remap(full['commands'][-6:], mapping)
    for row in commands:
        if row['cwd'] == old:
            row['cwd'] = str(args.out)
    copies = remap([row for row in full['setup_exact_copies']
                    if row['kind'] != 'actual-MIG-export-prerequisite'], mapping)
    require(len(full['commands']) == 37 and [row['id'] for row in commands] == IDS
            and commands == plan['commands'] and mapping == plan['mechanical_path_map']
            and len(copies) == 75 and copies == plan['setup_exact_copies'],
            'Only exact last six operations and native context copies allowed')
    for row, product in zip(commands[:4], plan['objects']):
        argv = row['argv']
        require(product['id'] == row['id'] and product['cwd'] == row['cwd']
                and product['path'] == argv[argv.index('-o') + 1]
                and product['MD'] == argv[argv.index('-MF') + 1]
                and product['source'] in argv, 'Object/MD inspection must bind actual argv')
    require(len(plan['objects']) == 4 and plan['archives'] == [
            {'id': row['id'], 'path': row['argv'][3], 'objects': row['argv'][4:]}
            for row in commands[4:]], 'Archive inspection must bind actual argv')
    catalog = common.load_project(plan['dependency_source_catalog']['path'], plan['dependency_source_catalog']['sha256'])
    approval = common.load_project(args.approval, args.approval_sha256)
    require(approval['source_plan_sha256'] == args.source_plan_sha256, 'Root must bind exact object plan')
    budget = common.project_approval(args, approval, executor_path=Path(__file__))
    require(budget.rss_limit == plan['max_owned_rss_bytes'], 'Wrong actual allocation RSS cap')
    pins = {**plan['source_bindings_sha256'], **header_pins, **base.PINS}
    report = dict(kind='host-test', origin='local-host', outcome='fail', task=args.task,
                  owner=args.owner, experiment=args.experiment, recorded_at=datetime.now(timezone.utc).isoformat(),
                  source_plan_sha256=args.source_plan_sha256, commands=[], objects=[], archives=[],
                  header_regenerated=False, MIG_reemitted=False, layout_executed=False,
                  provider_tuple_layout_qualified=False, ABI_link_runtime_qualified=False)
    started, reserved, dependencies = time.monotonic(), False, {}
    with core.owned_cancellation() as cancel:
        def remaining():
            cancel.check()
            seconds = plan['whole_seconds'] - (time.monotonic() - started)
            require(seconds > 0, 'Object phase dispatch/work deadline')
            return seconds

        try:
            args.out.mkdir(parents=True, exist_ok=False)
            for path, expected in pins.items():
                remaining()
                require(sha(path) == expected, 'Changed exact input: ' + path)
            with cancel.cleanup():
                budget.reserve()
                reserved = True
            for path in plan['setup_owned_directories']:
                remaining()
                path = common.canonical_output_path(path)
                require(path.is_relative_to(args.out) and 'unavailable-sdk' not in path.parts,
                        'Setup escaped own context or fabricated SDK')
                path.mkdir(parents=True, exist_ok=True)
            for row in copies:
                remaining()
                require(sha(row['source']) == row['sha256'], 'Changed native context source')
                dest = common.canonical_output_path(row['destination'])
                require(dest.is_relative_to(args.out) and not dest.exists(), 'Fresh owned context copy required')
                dest.write_bytes(Path(row['source']).read_bytes())
                require(sha(dest) == row['sha256'], 'Native context copy differs')
                dest.chmod(0o444)
            supervise = common.supervisor(base.MAIN)
            for index, row in enumerate(commands):
                record = core.run_owned_child(common, cancel, row['argv'], Path(row['cwd']), args.out,
                    'operation-' + str(index).zfill(3), supervise,
                    timeout=min(row['timeout_seconds'], remaining()), admit=True, budget=budget)
                report['commands'].append(record)
                require(record.get('exit_code') == 0 and not record.get('stop_reason')
                        and record.get('resource_qualification') == 'pass', 'Actual operation failed: ' + row['id'])
                if index < 4:
                    product = plan['objects'][index]
                    regular(product['path']); regular(product['MD'])
                    object_info = common.macho(product['path'])
                    require(object_info['cpu_subtype'] == 0, 'Exact ARM64 object subtype required')
                    deps = common.dependencies(product['MD'], product['cwd'], product['path'])
                    require(str(Path(product['source']).resolve()) in deps, 'Actual MD omits provider source')
                    rows = []
                    for name in deps:
                        remaining()
                        value = sha(name)
                        if name in catalog['sha256_by_path']:
                            require(value == catalog['sha256_by_path'][name], 'Changed qualified MD source: ' + name)
                            identity = 'accepted-sha256'
                        else:
                            git = catalog['public_firehose_git_blobs'].get(name)
                            require(git is not None, 'Unbound actual MD dependency: ' + name)
                            digest = hashlib.sha1(('blob ' + str(Path(name).stat().st_size) + '\0').encode())
                            with Path(name).open('rb') as stream:
                                for chunk in iter(lambda: stream.read(1024**2), b''):
                                    digest.update(chunk)
                            require(digest.hexdigest() == git['blob_sha1'], 'Changed public donor MD source: ' + name)
                            identity = 'genuine-firehose-git-blob'
                        dependencies[name] = value
                        rows.append({'path': name, 'sha256': value, 'source_identity': identity})
                    report['objects'].append({**product, **object_info,
                        'MD_sha256': sha(product['MD']), 'actual_dependencies': rows})
                else:
                    product = plan['archives'][index - 4]
                    regular(product['path'])
                    members = core.stream_archive(product['path'])
                    fresh = {item['path']: item for item in report['objects']}
                    expected = [{'name': Path(name).name, 'sha256': fresh[name]['sha256'],
                                 'file_size': fresh[name]['file_size']} for name in product['objects']]
                    require(list(members) == expected, 'Actual archive members differ from fresh provider objects')
                    report['archives'].append({**product, 'members': list(members),
                                               'sha256': members.sha256, 'file_size': members.file_size})
            products = {item['path']: item['sha256'] for item in [*report['objects'], *report['archives']]}
            products.update({item['MD']: item['MD_sha256'] for item in report['objects']})
            for path, expected in {**pins, **dependencies, **products}.items():
                remaining()
                require(sha(path) == expected, 'Input/dependency changed during object phase: ' + path)
            remaining()
            report['outcome'] = 'pass'
        except Exception as error:
            if isinstance(error, core.OwnedCancellation) and getattr(error, 'command', None) is not None:
                report['commands'].append(error.command)
            report['error'] = repr(error)
        finally:
            with cancel.cleanup():
                try:
                    budget.release() if reserved or budget.registered else None
                    report['own_reservation_released'] = not budget.registered
                    if reserved and not budget.registered:
                        report['owned_cleanup'] = 'broker-release-verified-no-retained-owned-child'
                except Exception as error:
                    report.update(outcome='fail', budget_release_error=repr(error))
                if cancel.signals:
                    report.update(outcome='fail', cancelled_signals=cancel.signals)
                report['elapsed_seconds'] = time.monotonic() - started
                if args.out.is_dir():
                    base.write(args.out / 'evidence.json', report)
    return 0 if report['outcome'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
