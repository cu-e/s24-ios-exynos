#!/usr/bin/env python3
"""Focused registered REV-037 corrections; tiny Python/source controls only."""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import resource
import struct
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[3]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def lease_case(main, out, case):
    c = load(ROOT / 'tools/run/avf_kernel_boot.py', 'lease_' + case)
    pins = c.read_json(c.FIXTURE); supervisor = c.helper(main, pins, 'process')
    place = out / case; place.mkdir()
    # These explicit seams bypass only the unavailable genuine-image branch.
    # Real lease validation, admission, Popen and owned cleanup remain unchanged.
    c.ROOT = place
    base = place / 'artifacts/avf-kernel-boot'; base.mkdir(parents=True)
    run = base / 'control-run'; plan_path = base / 'control-plan.json'
    plan = {'main': str(place), 'image_id': 'HOST-CONTROL-NO-IMAGE', 'cwd': str(run),
            'admission': {'descriptor': {'sha256': 'a' * 64}}, 'descriptor': {},
            'collector_sha256': c.digest(c.__file__), 'fixture_sha256': c.digest(c.FIXTURE),
            'argv': [sys.executable, '-s', '-c', 'print("Owned lease regression Python")'],
            'layout': {}, 'package': {}, 'checked_layout': {}, 'combined_boot_args': ''}
    c.write_json(plan_path, plan)
    epoch = datetime.now(timezone.utc); clock = {'seconds': 0.0}
    grant = {'id': 'HOST-CONTROL-NOT-A-GUEST-LEASE', 'owner': c.OWNER, 'task': 'VM-040',
             'protocol': c.PROTOCOL, 'plan_sha256': c.digest(plan_path),
             'collector_sha256': c.digest(c.__file__), 'image_descriptor_sha256': 'a' * 64,
             'guest_memory_mib': 256, 'owned_rss_limit_bytes': c.RSS_LIMIT,
             'deadline_seconds': c.DEADLINE, 'output': str(run), 'issued_at': epoch.isoformat(),
             'expires_at': (epoch + timedelta(seconds=2.5 if case == 'late-expiry' else 120)).isoformat()}
    queue = place / 'artifacts/team-coordination/20261106-team/resource-queue.json'
    c.write_json(queue, {'qemu': grant})
    report = {'case': case, 'kind': 'explicit-host-only-seams', 'lease_checks': [], 'sleeps': [],
              'spawn_calls': [], 'QEMU_executed': False, 'guest_executed': False}
    real_lease, real_own, real_popen = c.lease, c.own_process, subprocess.Popen
    real_sample = supervisor.sample
    state = {'in_own': False}
    def sample(session=None):
        value = real_sample(session)
        if case == 'late-memory-drop' and state['in_own'] and session is None:
            value['MemAvailable_bytes'] = 0
            report['injected_resource_snapshot'] = value
        return value
    supervisor.sample = sample
    def checked_lease(root, lease_id, path, current_plan):
        row = {'virtual_seconds': clock['seconds']}; report['lease_checks'].append(row)
        try:
            value = real_lease(root, lease_id, path, current_plan,
                               current=epoch + timedelta(seconds=clock['seconds']))
            row['accepted'] = True; return value
        except Exception as error:
            row.update(accepted=False, error=str(error)); raise
    def sleep(seconds):
        report['sleeps'].append(seconds); clock['seconds'] += seconds
        # The real child still gets a scheduling opportunity; lease time is virtual.
        if seconds < 1: time.sleep(min(seconds, .01))
    def observed_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        report['spawn_calls'].append({'argv': args[0], 'pid': process.pid,
                                      'virtual_seconds': clock['seconds']})
        return process
    class Captured(Exception): pass
    def observed_own(*args, **kwargs):
        report['before_own_virtual_seconds'] = clock['seconds']
        state['in_own'] = True
        if case == 'late-expiry': clock['seconds'] = 3
        if case == 'late-revocation': queue.write_text(json.dumps({'qemu': None}))
        if case == 'late-Stop': args[3].request('Focused Stop before Popen')
        subprocess.Popen = observed_popen
        try:
            kwargs['seconds'] = 3
            record = real_own(*args, **kwargs)
            report['owned_record'] = record
            c.write_json(place / 'owned-record.json', record)
        except c.Refused as error:
            report['pre_spawn_error'] = str(error)
        finally:
            subprocess.Popen = real_popen
        raise Captured()
    c.prepare = lambda *args, **kwargs: copy.deepcopy(plan)
    c.helper = lambda root, current_pins, name: supervisor if name == 'process' else None
    c.protocol_operation = lambda *args: None
    c.lease, c.own_process = checked_lease, observed_own
    c.time = SimpleNamespace(monotonic=time.monotonic, sleep=sleep)
    try:
        c.collect(plan_path, grant['id'], c.Stop())
    except Captured:
        pass
    finally:
        subprocess.Popen = real_popen
    assert report['before_own_virtual_seconds'] == 2
    assert [s for s in report['sleeps'] if s == 1] == [1, 1]
    if case == 'valid-Python':
        record = report['owned_record']
        assert len(report['spawn_calls']) == 1 and record['exit_code'] == 0
        assert record['host_signals'] == [] and record['live_owned_pids'] == []
        assert record['guest_started'] is False
    else:
        assert report['spawn_calls'] == [], report
        if 'owned_record' in report:
            assert report['owned_record']['live_owned_pids'] == []
            assert report['owned_record']['host_signals'] == []
            assert 'owned_session' not in report['owned_record']
    report['outcome'] = 'pass'; c.write_json(place / 'report.json', report)
    return report


def fdt_cases(main, out, c):
    controls = load(ROOT / 'fixtures/public/avf-kernel-boot/controls.py', 'focused_controls')
    controls.OUT, controls.MAIN = out, main
    raw = controls.fdt_bytes(); (out / 'source-valid-authored-input.dtb').write_bytes(raw)
    props = c.fdt(raw); layout = {'payload_base': 0x48000000}; package = {'size': 64}
    cases = []
    def probe(name, current, expected):
        row = {'case': name, 'expected_acceptance': expected,
               'properties': {node + ':' + key: value.hex() for (node, key), value in current.items()}}
        try:
            row['result'] = c.fdt_contract(current, layout, package); row['accepted'] = True
        except (ValueError, KeyError, struct.error) as error:
            row.update(accepted=False, error=str(error))
        cases.append(row); assert row['accepted'] is expected, row
    probe('new-source-valid-authored-fixture', props, True)
    old = main / 'worktrees/vm-040-eh-20261106/artifacts/avf-kernel-boot/controls-9efba94-1/fdt/authored-input.dtb'
    probe('unchanged-old-published-fixture', c.fdt(old.read_bytes()), False)
    mutations = [
        ('missing-memory-device-type', ('/memory@40000000', 'device_type'), None),
        ('wrong-memory-device-type', ('/memory@40000000', 'device_type'), b'xmemory\0'),
        ('prefixed-PL011', ('/pl011@9000000', 'compatible'), b'xarm,pl011\0'),
        ('prefixed-GIC', ('/intc@8000000', 'compatible'), b'xarm,gic-v3\0'),
        ('unterminated-PL011', ('/pl011@9000000', 'compatible'), b'arm,pl011'),
        ('unterminated-GIC', ('/intc@8000000', 'compatible'), b'arm,gic-v3'),
        ('zero-GIC-spans', ('/intc@8000000', 'reg'), struct.pack('>4Q', 0x08000000, 0, 0x080a0000, 0)),
        ('short-GIC-distributor', ('/intc@8000000', 'reg'), struct.pack('>4Q', 0x08000000, 4, 0x080a0000, 0xf60000)),
        ('short-GIC-redistributor', ('/intc@8000000', 'reg'), struct.pack('>4Q', 0x08000000, 0x10000, 0x080a0000, 4)),
        ('overflow-GIC-span', ('/intc@8000000', 'reg'), struct.pack('>4Q', 0x08000000, 0x10000, 0x080a0000, (1 << 64) - 1))]
    for name, key, value in mutations:
        current = dict(props)
        if value is None: current.pop(key)
        else: current[key] = value
        probe(name, current, False)
    current = dict(props)
    current[('/pl011@9000000', 'compatible')] = b'vendor,uart\0arm,pl011\0arm,primecell\0'
    current[('/intc@8000000', 'compatible')] = b'vendor,intc\0arm,gic-v3\0'
    probe('exact-tokens-within-valid-lists', current, True)
    source = main / 'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2/source/scion/avf/shim'
    expected = {'avfboot.c': '2957f3c8b17009b1d96191f6ccb782e90b135e7dc22208df2e3045b69d5f2c75',
                'fdtx.c': '115aabba3c26f259b8f0fb16a3ad581a1b9af8060c4c4cac50e01aee69a5e68c'}
    for name, sha in expected.items(): assert c.digest(source / name) == sha
    # One focused existing host-peer control, not the full19-case suite.
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        controls.Controls('test_real_python_peer_paused_input_fdt_protocol')]))
    assert result.wasSuccessful()
    report = {'cases': cases, 'old_fixture': {'path': str(old), 'sha256': c.digest(old)},
              'new_authored_fixture_sha256': c.digest(out / 'source-valid-authored-input.dtb'),
              'source_bindings': {str(source / name): sha for name, sha in expected.items()},
              'peer_control_count': 1, 'actual_QEMU_FDT_qualified': False}
    c.write_json(out / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--phase', choices=('lease', 'fdt'), required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args(); main_root = args.main.resolve()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    c = load(ROOT / 'tools/run/avf_kernel_boot.py', 'correction_recorder')
    out = c.output_dir(args.out); out.mkdir(parents=True)
    started, stamp = time.monotonic(), c.now(); outcome = 'fail'
    try:
        if args.phase == 'lease':
            reports = [lease_case(main_root, out, case) for case in
                       ('late-expiry', 'late-revocation', 'late-memory-drop', 'late-Stop', 'valid-Python')]
            c.write_json(out / 'report.json', {'cases': reports, 'outcome': 'pass'})
        else:
            fdt_cases(main_root, out, c)
        outcome = 'pass'
    except BaseException:
        (out / 'failure.txt').write_text(traceback.format_exc())
    files = [p for p in sorted(out.rglob('*')) if p.is_file() and not p.is_symlink()]
    relative = lambda path: str(path.relative_to(main_root))
    commands = [{'argv': [sys.executable, *sys.argv], 'cwd': str(Path.cwd()),
                 'exit_code': 0 if outcome == 'pass' else 1, 'elapsed_seconds': time.monotonic() - started}]
    for path in files:
        if path.name in ('owned-record.json', 'record.json'):
            record = c.read_json(path)
            commands.append({key: record[key] for key in ('argv', 'cwd', 'exit_code', 'elapsed_seconds')})
    evidence = {'kind': 'host-test', 'origin': 'local-host', 'outcome': outcome, 'recorded_at': stamp,
        'summary': 'Focused REV-037 ' + args.phase + ' correction host controls; no compiler/QEMU/guest.',
        'task': 'VM-040', 'owner': c.OWNER, 'commit': args.commit,
        'experiment': 'VMBOOTCOLLECT-002' if args.phase == 'lease' else 'VMBOOTCOLLECT-003',
        'commands': commands, 'artifacts': [relative(p) for p in files],
        'artifact_sha256': {relative(p): c.digest(p) for p in files},
        'source_sha256': {relative(path): c.digest(path) for path in
                          (ROOT / 'tools/run/avf_kernel_boot.py', Path(__file__),
                           ROOT / 'fixtures/public/avf-kernel-boot/controls.py')},
        'current_image_memory': c.memory_self(), 'elapsed_seconds': time.monotonic() - started,
        'limitations': ['Explicit unavailable-image/ROOT/protocol/virtual-clock host seams do not admit a kernel or root guest lease.',
            'Old physical source, original reviewer/producer capsules and original invalid host fixture remain unchanged.',
            'A new valid authored fixture is not actual QEMU FDT qualification.',
            'No compiler, QEMU, phone, production packaging, common checks or MAIN publication. Independent recheck/acceptance pending.']}
    c.write_json(out / 'evidence.json', evidence)
    print(json.dumps({'outcome': outcome, 'phase': args.phase, 'evidence': str(out / 'evidence.json'),
                      'current_image_memory': c.memory_self()}))
    return 0 if outcome == 'pass' else 1


if __name__ == '__main__': sys.exit(main())
