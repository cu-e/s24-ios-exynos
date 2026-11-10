"""NAT-013 host tests for restore_stock.py. No USB device or phone is used.

FakeSBoot models the S-Boot behaviour recorded in NAT-012, not the tool's own logic:
- restore-003 (first session after a physical entry): every reply is zero, EndSession and reboot
  answer;
- restore-002 and Heimdall stock-flash-001 (a second session after a standalone EndSession in the
  same entry): data parts and sequence ends are acknowledged with zero, but EndSession never
  answers. The Android readback after stock-flash-001 still showed the boot loop, so nothing was
  committed.
The S-Boot reason (EndSession stops the async workers; BeginSession does not restart them) is
the NAT-012 disassembly (session-lifecycle-analysis.json), a source-review claim.
Run: python3 -I docs/procedures/nat-013/test_restore.py -v
"""
import hashlib
import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load('restore_stock')
audit = load('pit_audit')
ACTUAL_PIT = ROOT / 'artifacts/recovery-rescue-20261110-01/device.pit'


def entry(binary, device, ident, start, count, name, file_name=b''):
    e = struct.pack('<9I', binary, device, ident, 0, 0, start, count, 0, 0)
    return e + name.ljust(32, b'\0') + file_name.ljust(32, b'\0') + b'\0' * 32


def synthetic_pit(rows=None):
    rows = rows if rows is not None else [
        entry(0, 8, 1, 1000, 16384, b'BOOT', b'boot.img'),
        entry(0, 8, 18, 75152, 24576, b'RECOVERY', b'recovery.img'),
        entry(0, 8, 30, 200000, 99999, b'USERDATA', b'userdata.img'),
    ]
    body = struct.pack('<II', 0x12349876, len(rows)) + b'\0' * 20 + b''.join(rows)
    return body.ljust(8192, b'\0')


class Timeout(Exception):
    """Stands in for usb.core.USBTimeoutError."""


class FakeSBoot:
    def __init__(self, pit, workers_alive=True, short_chunk=None):
        self.pit, self.workers_alive, self.short_chunk = pit, workers_alive, short_chunk
        self.replies, self.commands, self.targets = [], [], []
        self.handshaken = self.begun = self.rebooted = False
        self.data_left, self.part, self.pending, self.committed = 0, 0, hashlib.sha256(), None

    def write(self, ep, b, timeout):
        b = bytes(b)
        if self.data_left:
            assert len(b) == m.PART
            self.pending.update(b)
            self.replies.append(struct.pack('<II', 0, self.part))
            self.part += 1
            self.data_left -= len(b)
            return len(b)
        if b == b'ODIN':
            self.handshaken = True
            self.replies.append(b'LOKE')
            return 4
        cmd, sub = struct.unpack_from('<II', b)
        words = struct.unpack_from('<8I', b, 8)
        self.commands.append((cmd, sub))
        if (cmd, sub) == (0x64, 0):
            self.begun = True
            self.replies.append(struct.pack('<II', 0x64, 0x38000))
        elif not self.begun:
            pass                      # "prb is null!": S-Boot hangs, nothing answers
        elif (cmd, sub) == (0x65, 1):
            self.replies.append(struct.pack('<II', 0x65, len(self.pit)))
        elif (cmd, sub) == (0x65, 2):
            chunk = self.pit[words[0] * 500:(words[0] + 1) * 500]
            self.replies.append(chunk[:1] if words[0] == self.short_chunk else chunk)
        elif (cmd, sub) == (0x66, 2):
            self.data_left, self.part = words[0], 0
            self.replies.append(struct.pack('<II', 0x66, 0))
        elif (cmd, sub) == (0x66, 3):
            self.targets.append(words[2:5])
            self.replies.append(struct.pack('<II', 0x66, 0))
        elif (cmd, sub) == (0x67, 0):
            if self.workers_alive:
                self.committed = self.pending.hexdigest()
                self.workers_alive = False     # EndSession stops the workers for this entry
                self.replies.append(struct.pack('<II', 0x67, 0))
        elif (cmd, sub) == (0x67, 1):
            self.rebooted = True
            self.replies.append(struct.pack('<II', 0x67, 0))
        else:
            self.replies.append(struct.pack('<II', cmd, 0))
        return len(b)

    def read(self, ep, n, timeout):
        if not self.replies:
            raise Timeout('no reply')
        return self.replies.pop(0)


IMAGE = bytes(range(256)) * (m.SIZE // 256)
IMAGE_SHA = hashlib.sha256(IMAGE).hexdigest()


class Patched(unittest.TestCase):
    def setUp(self):
        self._stock = m.STOCK
        m.STOCK = IMAGE_SHA           # the synthetic image stands in for the local stock backup

    def tearDown(self):
        m.STOCK = self._stock


class SessionLifecycle(Patched):
    def test_fresh_entry_commits_and_never_reports_pass(self):
        dev, report = FakeSBoot(synthetic_pit()), {}
        m.run_session(dev, IMAGE, report, expected_pit=None)
        self.assertEqual(dev.committed, IMAGE_SHA)
        self.assertTrue(dev.rebooted)
        self.assertEqual(set(dev.targets), {m.TARGET})
        self.assertTrue(all(report['stages'].values()))
        self.assertEqual(report['outcome'], 'awaiting-readback')

    def test_second_session_in_one_entry_is_reported_as_not_flushed(self):
        dev = FakeSBoot(synthetic_pit())
        m.run_session(dev, IMAGE, {}, expected_pit=None)      # the entry's one session
        dev.rebooted, dev.committed = False, None
        dev.pending = hashlib.sha256()
        report = {}
        with self.assertRaises(Timeout):
            m.run_session(dev, IMAGE, report, expected_pit=None)
        s = report['stages']
        self.assertTrue(s['pit_validated'] and s['upload_acknowledged'])
        self.assertFalse(s['session_end_confirmed'] or s['reboot_confirmed'])
        self.assertEqual(report['outcome'], 'acknowledged-not-flushed')
        self.assertIsNone(dev.committed)
        self.assertFalse(dev.rebooted)
        self.assertEqual(dev.commands[-1], (0x67, 0))          # no reboot after the timeout

    @unittest.skipUnless((ROOT / 'artifacts/recovery-rescue-20261110-01/restore-003/trace.json').exists(),
                         'NAT-012 device trace is a local artifact')
    def test_command_sequence_equals_the_successful_device_session(self):
        dev, report = FakeSBoot(synthetic_pit()), {}
        m.run_session(dev, IMAGE, report, expected_pit=None)
        saved = json.loads((ROOT / 'artifacts/recovery-rescue-20261110-01/restore-003/trace.json').read_text())
        key = lambda r: (r['cmd'], r['subcmd'], list(r['words']))
        self.assertEqual([key(r) for r in report['trace']], [key(r) for r in saved])

    def test_short_pit_chunk_stops_before_any_write(self):
        dev, report = FakeSBoot(synthetic_pit(), short_chunk=3), {}
        with self.assertRaises(m.ProtocolError):
            m.run_session(dev, IMAGE, report, expected_pit=None)
        self.assertEqual(report['outcome'], 'aborted-before-write')
        self.assertNotIn((0x64, 2), dev.commands)
        self.assertNotIn((0x66, 0), dev.commands)

    def test_wrong_image_is_refused_before_usb_io(self):
        dev = FakeSBoot(synthetic_pit())
        with self.assertRaises(ValueError):
            m.run_session(dev, IMAGE[:-1] + b'\1', {}, expected_pit=None)
        self.assertEqual(dev.commands, [])
        self.assertFalse(dev.handshaken)


class StateMachine(unittest.TestCase):
    def session(self):
        dev = FakeSBoot(synthetic_pit())
        return dev, m.Session(dev, {})

    def test_order_is_enforced_without_touching_the_device(self):
        dev, s = self.session()
        with self.assertRaises(m.ProtocolError):
            s.command(0x64, 0, (4,), expected=0x38000)          # before the handshake
        self.assertEqual(dev.commands, [])
        s.handshake()
        with self.assertRaises(m.ProtocolError):
            s.handshake()                                       # second handshake on one link
        s.command(0x64, 0, (4,), expected=0x38000, next_state='session')
        before = list(dev.commands)
        for cmd in [(0x64, 0, (4,)), (0x66, 2, (m.PART,)), (0x67, 0, ()), (0x67, 1, ())]:
            with self.assertRaises(m.ProtocolError):
                s.command(*cmd)
        with self.assertRaises(m.ProtocolError):
            s.data_part(b'\0' * m.PART, 0)
        self.assertEqual(dev.commands, before)

    def test_after_end_session_only_reboot_is_allowed(self):
        dev, s = self.session()
        s.state = 'ended'
        for cmd in [(0x64, 0, (4,)), (0x65, 1, ()), (0x66, 0, ()), (0x66, 2, (m.PART,)), (0x67, 0, ())]:
            with self.assertRaises(m.ProtocolError):
                s.command(*cmd)
        self.assertEqual(dev.commands, [])


class WireGuards(unittest.TestCase):
    def test_forbidden_commands_targets_and_flags(self):
        b = m.packet(0x66, 3, (0, 6291456, 0, 8, 18, 1, 0, 0))
        self.assertEqual(struct.unpack_from('<10I', b), (0x66, 3, 0, 6291456, 0, 8, 18, 1, 0, 0))
        for cmd in [(0x65, 0), (0x66, 7), (0x67, 2), (0x68, 0), (0x64, 1)]:
            with self.assertRaises(ValueError):
                m.packet(*cmd)
        for words in [(0, 6291456, 0, 8, 20, 1, 0, 0),   # another identifier
                      (0, 6291456, 0, 2, 18, 1, 0, 0),   # another device type
                      (0, 6291456, 0, 8, 18, 1, 1, 0),   # EFS clear
                      (0, 6291456, 0, 8, 18, 1, 0, 1),   # boot update
                      (0, m.SEQUENCE + 1, 0, 8, 18, 1, 0, 0)]:
            with self.assertRaises(ValueError):
                m.packet(0x66, 3, words)


class PitRules(unittest.TestCase):
    def test_synthetic_valid(self):
        self.assertEqual(m.validate_pit(synthetic_pit(), None)[:3], m.TARGET)

    def test_rejections(self):
        base = [entry(0, 8, 1, 1000, 16384, b'BOOT', b'boot.img'),
                entry(0, 8, 18, 75152, 24576, b'RECOVERY', b'recovery.img')]
        cases = {
            'duplicate identifier': base + [entry(0, 8, 18, 9, 9, b'OTHER')],
            'zero identifier': base + [entry(0, 8, 0, 9, 9, b'OTHER')],
            'zeroed RECOVERY entry': [base[0], b'\0' * 132],
            'second RECOVERY': base + [entry(0, 8, 40, 9, 9, b'RECOVERY')],
            'wrong bounds': [base[0], entry(0, 8, 18, 75152, 24575, b'RECOVERY')],
            'wrong device type': [base[0], entry(0, 2, 18, 75152, 24576, b'RECOVERY')],
            'invalid name': base + [entry(0, 8, 41, 9, 9, b'BAD/NAME')],
        }
        for label, rows in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                m.validate_pit(synthetic_pit(rows), None)
        with self.assertRaises(ValueError):
            m.validate_pit(synthetic_pit()[:200], None)
        with self.assertRaises(ValueError):
            m.validate_pit(synthetic_pit())                    # hash differs from the measured PIT

    @unittest.skipUnless(ACTUAL_PIT.exists(), 'measured PIT is a local artifact')
    def test_measured_pit_passes_strict_and_original_odin4_rules(self):
        pit = ACTUAL_PIT.read_bytes()
        self.assertEqual(m.validate_pit(pit)[:3], m.TARGET)
        rows = audit.entries(pit)
        for modified in (False, True):
            kept, fatal, notes = audit.parse(rows, modified)
            self.assertIsNone(fatal)
            self.assertEqual(notes, [])
            hits = audit.match(kept, 'recovery.img')
            self.assertEqual([(h['index'], h['partition'], h['identifier']) for h in hits], [(24, 'RECOVERY', 18)])


class HostGuards(unittest.TestCase):
    def test_ledger_allows_one_session_per_enumeration(self):
        with tempfile.TemporaryDirectory() as t:
            ledger = Path(t) / 'sessions.jsonl'
            boot = Path(t) / 'boot_id'
            boot.write_text('boot-a\n')
            key = m.enumeration_key(5, 24, boot)
            m.claim_enumeration(ledger, key, 'out-1')
            with self.assertRaises(m.ProtocolError):
                m.claim_enumeration(ledger, key, 'out-2')
            m.claim_enumeration(ledger, m.enumeration_key(5, 25, boot), 'out-3')  # re-entered
            boot.write_text('boot-b\n')
            m.claim_enumeration(ledger, m.enumeration_key(5, 24, boot), 'out-4')  # host rebooted
            self.assertEqual(len(ledger.read_text().splitlines()), 3)

    def test_other_processes_holding_the_node_are_found(self):
        with tempfile.TemporaryDirectory() as t:
            for pid, target in [('4242', '/dev/bus/usb/005/024'), ('4343', '/dev/null'), ('self', '/x')]:
                os.makedirs(f'{t}/{pid}/fd')
                os.symlink(target, f'{t}/{pid}/fd/3')
            self.assertEqual(m.device_node_users(5, 24, t), [4242])
            self.assertEqual(m.device_node_users(5, 23, t), [])


class Assessment(unittest.TestCase):
    done = dict(outcome='awaiting-readback', stages={k: True for k in m.STAGES})

    def readback(self, booted='1', match=True):
        return dict(properties={'sys.boot_completed': booted}, recovery_hash_match=match)

    def test_only_a_matching_readback_passes(self):
        self.assertEqual(m.assess(self.done, self.readback())['outcome'], 'pass')
        self.assertEqual(m.assess(self.done, None)['outcome'], 'inconclusive')
        self.assertEqual(m.assess(self.done, self.readback(match=False))['outcome'], 'fail')
        self.assertEqual(m.assess(self.done, self.readback(booted=''))['outcome'], 'inconclusive')

    def test_unflushed_session_fails_even_if_readback_matches(self):
        stopped = dict(outcome='acknowledged-not-flushed', stages={})
        self.assertEqual(m.assess(stopped, self.readback())['outcome'], 'fail')

    @unittest.skipUnless((ROOT / 'artifacts/recovery-rescue-20261110-01/android-check-003.json').exists(),
                         'NAT-012 readback is a local artifact')
    def test_nat012_saved_readbacks(self):
        d = ROOT / 'artifacts/recovery-rescue-20261110-01'
        early = json.loads((d / 'android-check-002.json').read_text())     # boot animation running
        final = json.loads((d / 'android-check-003.json').read_text())
        self.assertEqual(m.assess(self.done, early)['outcome'], 'inconclusive')
        self.assertEqual(m.assess(self.done, final)['outcome'], 'pass')


if __name__ == '__main__':
    unittest.main()
