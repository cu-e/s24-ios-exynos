#!/usr/bin/env python3
"""NAT-141 host checks of the STM start sequence and the polled event thread against host/peer141.c (pin-level, synthetic).

The driver's own e1s_touch.c (original + docs/procedures/nat-141/e1s_touch_combined.patch) runs on the host with its real
bit-banged SPI. kernel_thread_start runs the thread synchronously; the peer's host_delay ends the program after PEER_DELAYS delays.

Host-test only: the peer's READY/echo/coordinate bytes are synthetic. Only a native run with a finger on the screen shows events.
"""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_touch.c'
PATCH = HERE / 'e1s_touch_combined.patch'
HOST = HERE.parent / 'nat-121/host'
USI = dict(PEER_CLK=0, PEER_MOSI=1, PEER_MISO=2, PEER_CS=3)
OLD = dict(PEER_CLK=2, PEER_MOSI=1, PEER_MISO=0, PEER_CS=3)
ID_FRAMES = ['c0 22', 'd1 00 00 00 00 00 00 00 00', 'fb 20 00 00 00 00 00 00 00 00 00 00 00 00'] * 3
READ = '87' + ' 00' * 17
ALLOWED_WRITES = {'fa 20 00 00 24 81', 'c0 62', 'a0 00 01', 'c0 10'}


def run_case(wiring=USI, delays=400, no_ready=0):
    with tempfile.TemporaryDirectory(prefix='nat141-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        source = tmp / 't.c'
        source.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(source), str(PATCH)], check=True)
        text = '\n'.join(l for l in source.read_text().splitlines() if not l.startswith('#include'))
        for o, n in (('return *(volatile uint32_t *)reg;', 'return host_rd(reg);'),
                     ('*(volatile uint32_t *)reg = value;', 'host_wr(reg, value);')):
            assert text.count(o) == 1, o
            text = text.replace(o, n)
        pre = '#include "shim.h"\nuint32_t host_rd(uintptr_t); void host_wr(uintptr_t,uint32_t); void host_delay(int,int);\n'
        pre += '#define delay_for_interval host_delay\n#define kernel_thread_start host_thread_start\nstatic int threads;\n'
        pre += ('static kern_return_t host_thread_start(void (*f)(void *,wait_result_t),void *a,thread_t *t)'
                ' { *t=0; threads++; printf("THREAD\\n"); f(a, 0); return 0; }\n')
        text += ('\nint main(void) { host_steps=3; e1s_touch_init(); printf("RESULT returned threads=%d irq=%d bad=%d\\n",'
                 'threads,host_irq_attached,host_bad); return 0; }\n')
        source.write_text(pre + text)
        exe = tmp / 't'
        defs = ['-D%s=%d' % kv for kv in dict(wiring, PEER_DELAYS=delays, PEER_NO_READY=no_ready).items()]
        subprocess.run(['cc', '-std=gnu11', '-w', '-I', str(HOST), *defs, str(source), str(HERE / 'host/peer141.c'), '-o', str(exe)],
                       check=True)
        return subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=30).stdout


def frames(out):
    return [l[len('FRAME'):].strip() for l in out.splitlines() if l.startswith('FRAME')]


def posts(out):
    return [tuple(int(x) for x in l.split()[1:]) for l in out.splitlines() if l.startswith('post ')]


class StartAndEventTests(unittest.TestCase):
    def test_answering_peer_gets_the_samsung_start_order_and_its_touch_is_posted(self):
        out = run_case()
        f = frames(out)
        self.assertEqual(f[:10], [''] + ID_FRAMES)
        rest = [x for x in f[10:] if x != READ]
        self.assertEqual(rest[:4], ['fa 20 00 00 24 81', 'c0 62', 'a0 00 01', 'c0 10'])
        self.assertIn('e1s-touch: start: ready after 1 read(s)', out)
        self.assertIn('e1s-touch: start: echo of a0 after 1 read(s)', out)
        self.assertIn('e1s-touch: start: sense on (ready yes, scan echo yes); polling events every 10000 us, no IRQ', out)
        x, y = 0x123 * 65535 // 4095, 0x456 * 65535 // 4095
        self.assertEqual(posts(out), [(1, 1, x, y), (2, 1, x, y), (3, 1, x, y)])  # REDWOOD_TOUCH_DOWN/MOVE/UP
        self.assertIn('e1s-touch: coord 1: finger 1 action 1 x 291 y 1110', out)
        self.assertIn('e1s-touch: coord 3: finger 1 action 3 x 291 y 1110', out)
        self.assertIn('THREAD', out)
        self.assertIn('queue_left=0', out)

    def test_only_the_four_start_writes_and_reads_are_sent(self):
        f = frames(run_case())[10:]
        writes = {x for x in f if x and not x.startswith('87')}
        self.assertEqual(writes, ALLOWED_WRITES)
        self.assertTrue(all(x == READ for x in f if x.startswith('87')))

    def test_no_ready_is_bounded_and_the_thread_still_polls(self):
        out = run_case(delays=400, no_ready=1)
        self.assertIn('e1s-touch: start: no ready event in 150 reads', out)
        self.assertIn('sense on (ready no, scan echo yes)', out)
        self.assertEqual(len(posts(out)), 3)

    def test_periodic_summary_counts(self):
        out = run_case(delays=1400)
        self.assertIn('e1s-touch: events after 1000 polls: coord 3 (press 1 release 1) other 0; irq line low in 1000 polls', out)

    def test_unanswered_id_starts_nothing(self):
        out = run_case(wiring=OLD)
        self.assertIn('e1s-touch: no event thread: the last ID poll was "no response', out)
        self.assertNotIn('THREAD', out)
        self.assertEqual([x for x in frames(out) if x.startswith('fa') or x.startswith('a0') or x == 'c0 10'], [])
        self.assertIn('RESULT returned threads=0 irq=0 bad=0', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
