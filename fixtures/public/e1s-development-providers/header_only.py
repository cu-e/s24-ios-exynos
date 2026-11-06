#!/usr/bin/env python3
"""Root-admitted STR018 headers only; reuse the reviewed process/budget APIs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import stat
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
COMMON = MAIN / 'tools/build/avf_kernel_objects.py'
CORE = MAIN / 'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py'
PINS = {str(COMMON): '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755',
        str(CORE): '9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5',
        str(MAIN / 'tools/build/qemu_host.py'): 'faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def module(path):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PINS[str(path)], 'Changed reviewed helper')
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def native_flag_argv(path):
    # Native SETUP/replacecontents writes argv joined by spaces, newline, NUL.
    raw = path.read_bytes()
    require(raw.endswith(b'\n\x00') and raw.count(b'\x00') == 1,
            'Wrong native filter signature storage')
    text = raw[:-1].decode('utf-8')
    argv = shlex.split(text)
    require(text == ' '.join(argv) + '\n', 'Noncanonical native filter signature')
    return argv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-plan', type=Path, required=True)
    ap.add_argument('--source-plan-sha256', required=True)
    ap.add_argument('--approval', type=Path, required=True)
    ap.add_argument('--approval-sha256', required=True)
    args = ap.parse_args()
    common, core = module(COMMON), module(CORE)
    plan = common.load_project(args.source_plan, args.source_plan_sha256)
    require(plan['schema'] == 'e1s-provider-header-only-plan-v1', 'Only header plan accepted')
    require(plan['executor_sha256'] == digest(__file__), 'Wrong exact reviewed adapter')
    require(plan['helper_sha256'] == PINS, 'Wrong reviewed helper bindings')
    require(type(plan['whole_seconds']) is int and 1 <= plan['whole_seconds'] <= 600
            and plan['max_jobs'] == 1 and plan['max_owned_rss_bytes'] == 512 * 1024**2,
            'Only reviewed finite serial header bounds accepted')
    args.main = MAIN
    for key in ['task', 'owner', 'experiment', 'shard']:
        setattr(args, key, plan[key])
    require((args.task, args.owner, args.shard) == ('STR-018',
            'codex-e1s-development-providers-20261106-sr18', 'providers-headers'), 'Wrong owner/scope')
    args.out = common.canonical_output_path(plan['actual_output'])
    ledger = common.load_project(MAIN / 'state/lab.json')
    task = next(t for t in ledger['tasks'] if t['id'] == args.task)
    require(task['status'] == 'in_progress' and task['owner'] == args.owner, 'Original owner required')
    wt = Path(task['worktree'])
    if not wt.is_absolute():
        wt = MAIN / wt
    require(args.out.is_relative_to(wt / 'artifacts/e1s-development-providers') and not args.out.exists(), 'Fresh owned output required')
    require(any(e['id'] == args.experiment and e['task'] == args.task and e['owner'] == args.owner
                and e['status'] == 'planned' for e in ledger['experiments']), 'Exact planned experiment required')
    source = common.load_project(plan['provider_plan']['path'], plan['provider_plan']['sha256'])
    steps = source['commands'][:31]
    require(len(source['commands']) == 37 and len(steps) == 31
            and [c['id'] for c in steps] == ['install-headers-' + str(i).zfill(3) for i in range(30)] + ['export-firehose-header']
            and all(c['phase'] == 'headers' for c in steps), 'Only exact first31 header commands allowed')
    require(source['actual_output'] == str(args.out) and len(source['header_expected_rows']) == 315, 'Wrong output/header selection')
    require(plan['setup_exact_copies'] == [c for c in source['setup_exact_copies']
            if c['kind'] == 'actual-MIG-export-prerequisite'] and len(plan['setup_exact_copies']) == 4,
            'Only four exact actual MIG prerequisites may be staged')
    approval = common.load_project(args.approval, args.approval_sha256)
    require(approval['source_plan_sha256'] == args.source_plan_sha256, 'Root must bind exact header-only plan')
    budget = common.project_approval(args, approval, executor_path=Path(__file__))
    report = dict(kind='host-test', origin='local-host', outcome='fail', task=args.task,
                  owner=args.owner, experiment=args.experiment, shard=args.shard,
                  recorded_at=datetime.now(timezone.utc).isoformat(), source_plan_sha256=args.source_plan_sha256,
                  commands=[], headers=[], native_filter_flags={}, native_filter_argv={}, compiler_started=False,
                  archive_executed=False, layout_executed=False, resource_profile='project-budget-v1')
    started, reserved = time.monotonic(), False
    with core.owned_cancellation() as cancel:
        def remaining():
            cancel.check()
            seconds = plan['whole_seconds'] - (time.monotonic() - started)
            require(seconds > 0, 'Whole header deadline')
            return seconds

        try:
            remaining()
            args.out.mkdir(parents=True, exist_ok=False)
            for path, expected in {**source['input_sha256'], **PINS}.items():
                remaining()
                require(digest(path) == expected, 'Changed exact input: ' + path)
            remaining()
            with cancel.cleanup():
                budget.reserve()
                reserved = True
            for path in plan['setup_owned_directories']:
                remaining()
                path = common.canonical_output_path(path)
                require(path.is_relative_to(args.out) and 'unavailable-sdk' not in path.parts,
                        'Setup escaped owned header route or fabricated SDK')
                path.mkdir(parents=True, exist_ok=True)
            for copy in plan['setup_exact_copies']:
                remaining()
                require(digest(copy['source']) == copy['sha256'], 'Changed genuine generated prerequisite')
                dest = common.canonical_output_path(copy['destination'])
                require(dest.is_relative_to(args.out) and not dest.exists(), 'Owned fresh prerequisite required')
                dest.write_bytes(Path(copy['source']).read_bytes())
                remaining()
                require(digest(dest) == copy['sha256'], 'Prerequisite copy differs')
                dest.chmod(0o444)
            remaining()
            supervise = common.supervisor(MAIN)
            for index, row in enumerate(steps):
                seconds = remaining()
                record = core.run_owned_child(common, cancel, row['argv'], Path(row['cwd']), args.out,
                    'header-' + str(index).zfill(3), supervise,
                    timeout=min(row['timeout_seconds'], seconds), admit=True, budget=budget)
                record['native_accepted_exit_codes'] = row.get('accepted_exit_codes', [0])
                report['commands'].append(record)
                require(record.get('exit_code') in row.get('accepted_exit_codes', [0])
                        and not record.get('stop_reason') and record.get('resource_qualification') == 'pass',
                        'Actual header operation failed: ' + row['id'])
            for row in source['header_expected_rows']:
                remaining()
                path = common.canonical_output_path(row['output_template'])
                require(path.is_relative_to(args.out), 'Header escaped output')
                if not path.exists():
                    report['headers'].append({'path': str(path), 'status': 'absent-filtering-unproven'})
                    raise ValueError('Required scoped header absent; no empty-header invention: ' + str(path))
                info = path.lstat()
                require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_size > 0
                        and stat.S_IMODE(info.st_mode) == 0o444, 'Wrong actual native header product')
                report['headers'].append({'path': str(path), 'sha256': digest(path), 'bytes': info.st_size,
                    'mode': '0444', 'status': 'actual-installed', 'logical_header': row['logical_header'],
                    'visibility': row['visibility'], 'source': row['source'], 'native_kind': row['native_kind']})
            for guard in plan['native_flag_files']:
                remaining()
                path = common.canonical_output_path(guard['path'])
                require(path.is_relative_to(args.out), 'Native flag guard escaped owned output')
                argv = native_flag_argv(path)
                require(argv == guard['expected_argv'], 'Wrong actual native filter flags')
                report['native_filter_flags'][str(path)] = digest(path)
                report['native_filter_argv'][str(path)] = argv
            remaining()
            export = common.canonical_output_path(plan['firehose_export'])
            require(export.is_file() and not export.is_symlink() and export.stat().st_size > 0, 'Actual Firehose export missing')
            report['firehose_export'] = {'path': str(export), 'sha256': digest(export), 'bytes': export.stat().st_size}
            for path, expected in source['input_sha256'].items():
                remaining()
                require(digest(path) == expected, 'Input changed during headers: ' + path)
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
                    write(args.out / 'evidence.json', report)
    return 0 if report['outcome'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
