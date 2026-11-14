#!/usr/bin/env python3
"""NAT-169 host checks: the real e1s_touch.c (original + a combined patch) against host/peer169.c (pin-level, synthetic).

Compared drivers: NAT-167's patch (read-modify-write per pin change, unconditional 0x87 read every poll) and NAT-169's (DAT shadowed
per transfer, poll gated on gpa1-2 with a full read every 25th poll). Host-test only: the peer's bytes and its IRQ level model
(low exactly while events are queued, stock IRQF_TRIGGER_LOW) are synthetic.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_touch.c'
P167 = ROOT / 'docs/procedures/nat-167/e1s_touch_combined.patch'
P169 = HERE / 'e1s_touch_combined.patch'
HOST = ROOT / 'docs/procedures/nat-121/host'
USI = dict(PEER_CLK=0, PEER_MOSI=1, PEER_MISO=2, PEER_CS=3)
READ = '87' + ' 00' * 17


def run_case(patch, delays=2100, irq=0, late=0):
    with tempfile.TemporaryDirectory(prefix='nat169-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        source = tmp / 't.c'
        source.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(source), str(patch)], check=True)
        text = '\n'.join(l for l in source.read_text().splitlines() if not l.startswith('#include'))
        for o, n in (('return *(volatile uint32_t *)reg;', 'return host_rd(reg);'),
                     ('*(volatile uint32_t *)reg = value;', 'host_wr(reg, value);')):
            assert text.count(o) == 1, o
            text = text.replace(o, n)
        pre = '#include "shim.h"\nuint32_t host_rd(uintptr_t); void host_wr(uintptr_t,uint32_t); void host_delay(int,int);\n'
        pre += '#define delay_for_interval host_delay\n#define kernel_thread_start host_thread_start\nstatic int threads;\n'
        pre += ('static kern_return_t host_thread_start(void (*f)(void *,wait_result_t),void *a,thread_t *t)'
                ' { *t=0; threads++; printf("THREAD\\n"); f(a, 0); return 0; }\n')
        text += '\nint main(void) { host_steps=3; e1s_touch_init(); printf("RESULT returned\\n"); return 0; }\n'
        source.write_text(pre + text)
        exe = tmp / 't'
        defs = ['-D%s=%d' % kv for kv in dict(USI, PEER_DELAYS=delays, PEER_NO_READY=0, PEER_IRQ_MODEL=irq, PEER_LATE_AT=late).items()]
        subprocess.run(['cc', '-std=gnu11', '-w', '-I', str(HOST), *defs, str(source), str(HERE / 'host/peer169.c'), '-o', str(exe)],
                       check=True)
        return subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=60).stdout


def frames(out):
    return [l[len('FRAME'):].strip() for l in out.splitlines() if l.startswith('FRAME')]


def posts(out):
    return [tuple(int(x) for x in l.split()[1:]) for l in out.splitlines() if l.startswith('post ')]


def counts(out):
    m = re.search(r'COUNTS dat_reads=(\d+) dat_writes=(\d+) wave=([0-9a-f]+)', out)
    return int(m.group(1)), int(m.group(2)), m.group(3)


class Nat169(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = run_case(P167)
        cls.new = run_case(P169)                       # no IRQ model: the line reads low, so every poll reads (waveform check)
        cls.old_irq = run_case(P167, irq=1, late=1500)
        cls.new_irq = run_case(P169, irq=1, late=1500)

    def test_same_frames_and_dat_writes_with_fewer_reads(self):
        self.assertEqual(frames(self.old), frames(self.new))
        r0, w0, h0 = counts(self.old)
        r1, w1, h1 = counts(self.new)
        self.assertEqual((w0, h0), (w1, h1))          # the same DAT values in the same order
        nf = len(frames(self.new))
        bits = sum(len(f.split()) for f in frames(self.new)) * 8
        init0, init1 = r0 - 4 * bits - 2 * nf, r1 - bits - nf
        # NAT-167: 3 read-modify-writes + the MISO read per bit, a CS read-modify-write at each end of a transfer;
        # NAT-169: the MISO read per bit and one read per transfer. The few left are the same pin setup outside transfers.
        self.assertTrue(0 <= init0 <= 16 and 0 <= init1 <= 16, (init0, init1))     # measured 7 and 8
        self.assertLess(r1 * 3, r0)

    def test_gated_poll_loses_no_event_and_skips_idle_reads(self):
        want = [p for p in posts(self.old_irq)]
        self.assertEqual(posts(self.new_irq), want)
        self.assertEqual(len(want), 6)                 # finger 1 after sense on, finger 2 queued during the idle polls
        reads_old = sum(f == READ for f in frames(self.old_irq))
        reads_new = sum(f == READ for f in frames(self.new_irq))
        self.assertLess(reads_new * 10, reads_old)

    def test_summary_line_keeps_the_old_prefix_and_counts(self):
        lines = [l for l in self.new_irq.splitlines() if 'events after' in l]
        self.assertEqual(len(lines), 2)
        m = re.search(r'events after 2000 polls: coord 6 \(press 2 release 2\) other \d+; irq line low in (\d+) polls; '
                      r'skipped (\d+), high-line reads (\d+) with 0 events', lines[1])
        self.assertIsNotNone(m, lines[1])
        low, skipped, high = map(int, m.groups())
        self.assertEqual(low + skipped + high, 2000)
        self.assertAlmostEqual(high, 2000 // 25, delta=low)        # every 25th poll, unless the line was low on that poll

    def test_start_line_names_the_gate(self):
        self.assertIn('no IRQ, read on a low gpa1-2 or every 25 polls', self.new_irq)


class Touch170(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('touch170', HERE / 'touch170.py')
        self.t = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.t)
        self.text = (ROOT / 'artifacts/nat-168/analysis/kernel-text.txt').read_text(errors='replace')

    def test_nat168_text_reads_as_before(self):
        r = self.t.analyse(self.text)
        self.assertEqual((r['verdict'], r['seconds_per_1000'], r['device_id_read_ms']), ('P0', 19.47, 5.241))
        self.assertNotIn('gate', r)

    def gated(self, events, period_s):
        lines = ['[  %d.000001]: e1s-touch: events after %d polls: coord 0 (press 0 release 0) other 3; irq line low in 2 polls; '
                 'skipped %d, high-line reads %d with %d events' % (100 + k * period_s, k * 1000, k * 1000 - 2 - 40 * k, 40 * k, events)
                 for k in range(1, 11)]
        head = self.text[:self.text.index('e1s-touch: events after 1000 polls')]
        return head + '\n'.join(lines) + '\n'

    def test_gate_counters_and_verdicts(self):
        r = self.t.analyse(self.gated(0, 10))
        self.assertEqual((r['verdict'], r['seconds_per_1000']), ('P1', 10.0))
        self.assertEqual(r['gate'], dict(polls=10000, irq_low=2, skipped=9598, high_reads=400, high_events=0))
        self.assertEqual(self.t.analyse(self.gated(1, 10))['verdict'], 'G-fail')

    def test_unpadded_stamp_fraction(self):
        text = '[  122.944911]: e1s-touch: spi9 map x\n[  122.1002373]: e1s-touch: poll 1 device id: ok (1)\n'
        m1, m2 = self.t.MAP.search(text), self.t.ID1.search(text)
        self.assertEqual(self.t.us(m2) - self.t.us(m1), 57462)


class Build(unittest.TestCase):
    def test_image_record(self):
        b = __import__('json').loads((ROOT / 'artifacts/nat-169/build-001/build.json').read_text())
        old = __import__('json').loads((ROOT / 'artifacts/nat-167/build-001/build.json').read_text())
        c = b['payload_fixes']['loader-diag-xnu-scO-md1']['cmdline']
        self.assertEqual(c, old['payload_fixes']['loader-diag-xnu-scN-md1']['cmdline'].replace('NAT167-scN', 'NAT169-scO'))
        self.assertEqual(b['nat152_changes']['loader_sites_check'], dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(b['nat169_changes']['kernel'], 'e32e36c1ad958c28e26ce58ad979fe408bafe1035d94987ce183ee79dce39ba0')

    def test_object_has_the_gate_strings(self):
        o = (ROOT / 'artifacts/nat-169/kernel-001/compile/bsd_e1s_touch.o/e1s_touch.o').read_bytes()
        for s in (b'e1stouch_full', b'skipped %u, high-line reads %u with %u events', b'read on a low gpa1-2 or every %u polls'):
            self.assertIn(s, o)


if __name__ == '__main__':
    unittest.main()
