#!/usr/bin/env python3
"""Registered VMBOOTCOLLECT-001 controls. No QEMU, compiler or guest is run."""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('collector', ROOT / 'tools/run/avf_kernel_boot.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
OUT = MAIN = None
RECORDS = []


def area(name):
    path = OUT / name
    path.mkdir()
    return path


def reject(call, contains=None):
    try:
        call()
    except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
        if contains:
            assert contains in str(error), str(error)
        RECORDS.append({'control': 'expected-rejection', 'error': str(error)})
        return
    raise AssertionError('Expected rejection did not occur')


def bound(root, name, data):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return {'path': name, 'size': len(data), 'sha256': c.digest(path)}


def fdt_bytes(*, duplicate=False):
    strings, body = bytearray(), bytearray()
    def begin(name):
        body.extend(struct.pack('>I', 1) + name.encode() + b'\0')
        body.extend(b'\0' * (-len(body) % 4))
    def end(): body.extend(struct.pack('>I', 2))
    def prop(name, value):
        off = len(strings); strings.extend(name.encode() + b'\0')
        body.extend(struct.pack('>III', 3, len(value), off) + value)
        body.extend(b'\0' * (-len(body) % 4))
    begin(''); prop('#address-cells', struct.pack('>I', 2)); prop('#size-cells', struct.pack('>I', 2))
    if duplicate: prop('#size-cells', struct.pack('>I', 2))
    begin('memory@40000000'); prop('reg', struct.pack('>QQ', 0x40000000, 256 << 20)); end()
    begin('psci'); prop('method', b'hvc\0'); end()
    begin('pl011@9000000'); prop('reg', struct.pack('>QQ', 0x09000000, 0x1000)); prop('compatible', b'arm,pl011\0'); end()
    begin('intc@8000000'); prop('reg', struct.pack('>4Q', 0x08000000, 0x10000, 0x080a0000, 0xf60000)); prop('compatible', b'arm,gic-v3\0'); end()
    begin('timer'); prop('interrupts', struct.pack('>12I', 1, 13, 4, 1, 14, 4, 1, 11, 4, 1, 10, 4)); end()
    begin('chosen'); prop('bootargs', c.APPEND.encode() + b'\0')
    prop('linux,initrd-start', struct.pack('>Q', 0x48000000)); prop('linux,initrd-end', struct.pack('>Q', 0x48000040)); end()
    end(); body.extend(struct.pack('>I', 9))
    header = struct.pack('>10I', 0xd00dfeed, 56 + len(body) + len(strings), 56, 56 + len(body),
                         40, 17, 16, 0, len(strings), len(body))
    return header + b'\0' * 16 + body + strings


class Controls(unittest.TestCase):
    def test_absent_image_refuses_before_process(self):
        with patch.object(c.subprocess, 'Popen', side_effect=AssertionError('unexpected child')):
            reject(lambda: c.prepare(MAIN, 'current', ROOT / 'artifacts/avf-kernel-boot/not-launched'), 'No admitted genuine')

    def test_real_cli_refuses_current_image(self):
        place = area('cli-refusal')
        argv = [sys.executable, '-s', str(ROOT / 'tools/run/avf_kernel_boot.py'), 'plan', '--main', str(MAIN),
                '--run-dir', str(ROOT / 'artifacts/avf-kernel-boot/not-launched'), '--out', str(place / 'must-not-exist.json')]
        start = time.monotonic()
        process = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=5)
        (place / 'stdout.txt').write_bytes(process.stdout); (place / 'stderr.txt').write_bytes(process.stderr)
        self.assertEqual(process.returncode, 2); self.assertIn(b'No admitted genuine', process.stderr)
        self.assertFalse((place / 'must-not-exist.json').exists())
        RECORDS.append({'argv': argv, 'cwd': str(ROOT), 'exit_code': process.returncode,
                        'elapsed_seconds': time.monotonic() - start, 'stdout_sha256': c.digest(place / 'stdout.txt'),
                        'stderr_sha256': c.digest(place / 'stderr.txt'), 'guest_started': False})

    def test_bound_files_change_and_aliases(self):
        place = area('bindings'); row = bound(place, 'input.bin', b'actual bounded bytes')
        self.assertEqual(c.binding(place, row), place / 'input.bin')
        (place / 'input.bin').write_bytes(b'changed bytes')
        reject(lambda: c.binding(place, row), 'Changed bound bytes')
        (place / 'alias').symlink_to('input.bin')
        reject(lambda: c.inside(place, 'alias'), 'Symlink')
        reject(lambda: c.inside(place, '../escape'), 'relative path')
        os.mkfifo(place / 'fifo')
        reject(lambda: c.inside(place, 'fifo'), 'Regular input')

    def test_existing_and_nested_run_paths_rejected(self):
        reject(lambda: c.output_dir(OUT), 'fresh')
        reject(lambda: c.output_dir(OUT / 'nested'), 'direct child')

    def test_duplicate_and_nonfinite_json_rejected(self):
        reject(lambda: c.decode_json(b'{"guest":true,"guest":false}'), 'Duplicate')
        reject(lambda: c.decode_json(b'{"x":NaN}'), 'Nonfinite')

    def test_linux_fdt_properties_and_corruptions(self):
        data = fdt_bytes(); (area('fdt') / 'authored-input.dtb').write_bytes(data)
        props = c.fdt(data)
        result = c.fdt_contract(props, {'payload_base': 0x48000000}, {'size': 64})
        self.assertEqual(result['kind'], 'Linux-input-FDT')
        reject(lambda: c.fdt(data[:-1]), 'header')
        reject(lambda: c.fdt(fdt_bytes(duplicate=True)), 'Duplicate FDT property')
        wrong = dict(props); wrong[('/psci', 'method')] = b'smc\0'
        reject(lambda: c.fdt_contract(wrong, {'payload_base': 0x48000000}, {'size': 64}), 'HVC')
        wrong = dict(props); wrong[('/timer', 'interrupts')] = struct.pack('>12I', 1, 13, 4, 1, 14, 4, 1, 12, 4, 1, 10, 4)
        reject(lambda: c.fdt_contract(wrong, {'payload_base': 0x48000000}, {'size': 64}), 'PPI27')

    def test_embedded_payload_identity_is_bytes_not_boolean(self):
        place = area('payload')
        kernel, ramdisk = b'authored kernel-format-control bytes', b'authored ramdisk control bytes'
        (place / 'kernel').write_bytes(kernel); (place / 'ramdisk').write_bytes(ramdisk)
        body = bytearray()
        for name, value in [('kernel', kernel), ('ramdisk', ramdisk), ('cmdline', b'\0')]:
            body.extend(struct.pack('<16sII', name.encode(), len(value), 0) + value + b'\0' * (-len(value) % 16))
        body.extend(b'\0' * 24)
        payload = place / 'control.xnup'; payload.write_bytes(struct.pack('<II', 0x50554e58, len(body)) + body)
        memory = c.helper(MAIN, c.read_json(c.FIXTURE), 'memory')
        package = c.embedded_identity(memory, payload, place / 'kernel', place / 'ramdisk')
        self.assertEqual(set(package['entries']), {'kernel', 'ramdisk', 'cmdline'})
        (place / 'kernel').write_bytes(b'changed')
        reject(lambda: c.embedded_identity(memory, payload, place / 'kernel', place / 'ramdisk'), 'embedded kernel')
        (place / 'kernel').write_bytes(kernel); (place / 'ramdisk').write_bytes(b'changed')
        reject(lambda: c.embedded_identity(memory, payload, place / 'kernel', place / 'ramdisk'), 'embedded ramdisk')

    def test_combined_arguments_not_just_proposed_append(self):
        memory = c.helper(MAIN, c.read_json(c.FIXTURE), 'memory')
        combined = memory.command_line({'command_line': '-v avf_exit=1'}, c.APPEND, True, {'BOOT_LINE_LENGTH': 608})
        c.combined_arguments(combined)
        reject(lambda: c.combined_arguments(c.APPEND), 'Complete final')
        reject(lambda: c.combined_arguments(combined + ' serial=0'), 'conflicting')
        reject(lambda: c.combined_arguments(combined.replace('-enable_kprintf_spam', '')), 'Complete final')

    def test_incomplete_actual_source_to_link_map_rejected(self):
        pins = c.read_json(c.FIXTURE)
        plan = c.read_json(c.binding(MAIN, pins['vm022_plan']), bound=16 << 20)
        self.assertEqual(len(plan['ordered_object_map']), 1080)
        reject(lambda: c.object_lineage(MAIN, {'objects': []}, plan['ordered_object_map'], c.Stop()),
               'Complete ordered 1080-object')

    def test_qmp_fragmentation_and_typed_reply(self):
        left, right = socket.socketpair(); transcript = []; deadline = time.monotonic() + 2
        def guard():
            if time.monotonic() > deadline: raise c.Refused('Test protocol deadline')
        def peer():
            right.sendall(b'{"QMP":'); right.sendall(b'{}}\r\n')
            data = b''
            while b'\n' not in data: data += right.recv(4096)
            request = json.loads(data)
            right.sendall(json.dumps({'event': 'RESUME', 'data': {}}).encode() + b'\n')
            right.sendall(json.dumps({'return': {}, 'id': request['id']}).encode() + b'\n')
        thread = threading.Thread(target=peer, daemon=True); thread.start()
        try:
            qmp = c.QMP(left, guard, transcript)
            self.assertIn('QMP', qmp.receive()); self.assertEqual(qmp.command('qmp_capabilities'), {})
            reject(lambda: qmp.command('quit'), 'Unapproved')
            reject(lambda: qmp.command('pmemsave', {'val': 0, 'size': True, 'filename': '../outside'}), 'Typed owned')
        finally:
            left.close(); right.close(); thread.join(timeout=2)
        self.assertFalse(thread.is_alive()); c.write_json(OUT / 'qmp-authored-peer.json', transcript)

    def test_qmp_wrong_id_and_scalar_rejected(self):
        for label, response in [('wrong-id', b'{"id":99,"return":{}}\n'), ('boolean-id', b'{"id":true,"return":{}}\n'), ('scalar', b'[]\n')]:
            left, right = socket.socketpair()
            try:
                right.sendall(response)
                qmp = c.QMP(left, lambda: None, [])
                reject(lambda: qmp.command('query-status'))
            finally: left.close(); right.close()

    def test_qmp_bounds_and_stop_before_operation(self):
        left, right = socket.socketpair(); stop = c.Stop()
        try:
            qmp = c.QMP(left, stop.check, [])
            stop.request('explicit Stop')
            reject(lambda: qmp.command('cont'), 'explicit Stop')
            stop.reason = None
            qmp.buffer = b'x' * 65537
            right.sendall(b'x')
            reject(lambda: qmp.receive(), 'budget')
        finally: left.close(); right.close()

    def test_observation_sequence_never_qualifies_kernel(self):
        combined = 'debug=0x8 rd=md0 ' + c.APPEND
        text = ('avfboot: boot-args: ' + combined + '\nDarwin Kernel Version 22.5.0: authored control\n'
                'VM002: pid=1 ostype=Darwin owned-entry=v1\navf: kernel panic: panic(initproc exited)\n'
                'avf: powering off (PSCI SYSTEM_OFF)\n').encode()
        events = [{'event': 'SHUTDOWN', 'data': {'guest': True, 'reason': 'guest-shutdown'}}]
        record = {'resume_observed': True, 'cont_acknowledged_at': 'authored-control', 'input_fdt': {'authored': True},
                  'exit_code': 0, 'live_owned_pids': [], 'stop_reason': None, 'host_signals': [], 'timed_out': False,
                  'guest_started': True, 'elapsed_seconds': .1, 'deadline_seconds': 1, 'combined_boot_args': combined}
        result = c.assess_observations(text, events, record)
        self.assertEqual(result['classification'], 'consistent-observations-awaiting-review')
        self.assertFalse(result['genuine_kernel_qualified']); self.assertFalse(result['pid1_runtime_qualified'])
        failures = [(text + b'Darwin Kernel Version repeat\n', events, record),
                    (text, events * 2, record), (text, [{'event': 'SHUTDOWN', 'data': {'guest': False, 'reason': 'host-qmp-quit'}}], record),
                    (text, events, {**record, 'timed_out': True}), (text, events, {**record, 'exit_code': False}),
                    (text, events, {**record, 'combined_boot_args': c.APPEND}),
                    (text, events, {**record, 'resume_observed': False})]
        for raw, qmp, supervisor in failures:
            self.assertEqual(c.assess_observations(raw, qmp, supervisor)['classification'], 'inconclusive')
        c.write_json(OUT / 'authored-observation-controls.json', {'kind': 'authored-controls-not-guest', 'positive': result, 'negative_cases': len(failures)})

    def test_real_owned_process_natural_exit(self):
        place = area('process-natural')
        supervisor = c.helper(MAIN, c.read_json(c.FIXTURE), 'process')
        result = c.own_process([sys.executable, '-s', '-c', 'print("owned Python control")'], place,
                               supervisor, c.Stop(), seconds=3, memory_floor=False, rss_limit=256 << 20)
        self.assertEqual(result['exit_code'], 0); self.assertEqual(result['host_signals'], [])
        self.assertEqual(result['live_owned_pids'], []); self.assertFalse(result['guest_started'])
        c.write_json(place / 'record.json', result)

    def test_real_owned_process_timeout_and_stop(self):
        supervisor = c.helper(MAIN, c.read_json(c.FIXTURE), 'process')
        for name, cancel in [('timeout', False), ('cooperative-stop', True)]:
            place = area('process-' + name); stop = c.Stop()
            def operation(process, guard, record): stop.request('Owned test Stop')
            result = c.own_process([sys.executable, '-s', '-c', 'import time; time.sleep(5)'], place,
                                   supervisor, stop, seconds=.12 if not cancel else 3,
                                   operation=operation if cancel else None, memory_floor=False, rss_limit=256 << 20)
            self.assertEqual(result['live_owned_pids'], []); self.assertTrue(result['host_signals'])
            self.assertEqual(result['timed_out'], not cancel)
            self.assertFalse(result['guest_started'])
            c.write_json(place / 'record.json', result)

    def test_pre_requested_stop_prevents_spawn(self):
        place = area('process-not-started'); stop = c.Stop(); stop.request('Already stopped')
        with patch.object(c.subprocess, 'Popen', side_effect=AssertionError('unexpected spawn')):
            reject(lambda: c.own_process([sys.executable], place, None, stop, seconds=1), 'Already stopped')
        self.assertEqual(list(place.iterdir()), [])

    def test_root_lease_expiry_and_mutation(self):
        place = area('lease'); queue = place / 'artifacts/team-coordination/20261106-team/resource-queue.json'
        plan_path = place / 'plan.json'; plan_path.write_text('{}')
        plan = {'admission': {'descriptor': {'sha256': 'a' * 64}}, 'cwd': 'owned-control-output'}
        current = datetime.now(timezone.utc)
        grant = {'id': 'authored-control', 'owner': c.OWNER, 'task': 'VM-040', 'protocol': c.PROTOCOL,
                 'plan_sha256': c.digest(plan_path), 'collector_sha256': c.digest(c.__file__),
                 'image_descriptor_sha256': 'a' * 64, 'guest_memory_mib': 256, 'owned_rss_limit_bytes': c.RSS_LIMIT,
                 'deadline_seconds': c.DEADLINE, 'output': plan['cwd'], 'issued_at': current.isoformat(),
                 'expires_at': (current + timedelta(seconds=120)).isoformat()}
        queue.parent.mkdir(parents=True); queue.write_text(json.dumps({'qemu': grant}))
        c.lease(place, 'authored-control', plan_path, plan, current=current + timedelta(seconds=1))
        reject(lambda: c.lease(place, 'authored-control', plan_path, plan, current=current + timedelta(seconds=121)), 'stale')
        grant['guest_memory_mib'] = True; queue.write_text(json.dumps({'qemu': grant}))
        reject(lambda: c.lease(place, 'authored-control', plan_path, plan, current=current + timedelta(seconds=1)), 'binding mismatch')


def main():
    global OUT, MAIN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True); parser.add_argument('--main', type=Path, required=True)
    args = parser.parse_args(); MAIN = args.main.resolve(); OUT = c.output_dir(args.out)
    OUT.mkdir(parents=True)
    started = c.now(); begin = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    c.write_json(OUT / 'controls.json', {'kind': 'authored-host-controls', 'started_at': started,
        'elapsed_seconds': time.monotonic() - begin, 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'records': RECORDS,
        'current_image_memory': c.memory_self(), 'collector_sha256': c.digest(c.__file__),
        'controls_sha256': c.digest(__file__), 'genuine_kernel_executed': False, 'QEMU_executed': False})
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': sys.exit(main())
