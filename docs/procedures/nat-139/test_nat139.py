#!/usr/bin/env python3
"""NAT-139 host checks of the SPI9 pin map against a pin-level synthetic peer (host/peer139.c).

The touch driver's own e1s_touch.c (original source + a combined patch) is compiled on the host. Its real bit-banged
e1s_spi_transfer runs, and the peer sees only GPP9 CON/DAT register traffic. The peer is wired either by the USI pad order that
the pinned DT implies (CLK 0, MOSI 1, MISO 2, CS 3) or by the order NAT-122/124/137 used (CLK 2, MOSI 1, MISO 0, CS 3).

  NAT-139 driver + USI peer   -> the peer's synthetic IDs are read, frames are exactly the bounded read-only sequence
  NAT-128 driver + USI peer   -> all-00 IDs and the peer never sees a clock edge (the phone's T1 class)
  NAT-128 driver + old peer   -> IDs read (control: the model is not failing by itself)
  NAT-139 driver + old peer   -> all-00 IDs (symmetry)

Host-test only: this does not show which wiring the phone has. Only a native run can answer that.
"""
import hashlib
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
PATCHES = {'nat139': HERE / 'e1s_touch_combined.patch', 'nat128': HERE.parent / 'nat-128/e1s_touch_combined.patch'}
HOST = HERE.parent / 'nat-121/host'
USI = dict(PEER_CLK=0, PEER_MOSI=1, PEER_MISO=2, PEER_CS=3)
OLD = dict(PEER_CLK=2, PEER_MOSI=1, PEER_MISO=0, PEER_CS=3)
EXPECTED_FRAMES = ['c0 22', 'd1 00 00 00 00 00 00 00 00', 'fb 20 00 00 00 00 00 00 00 00 00 00 00 00'] * 3
PEER_DEVID = '5a 13 9c 01 7e'
PEER_HWID = '31 32 33 34 35 36 37 38'


def run_case(driver, wiring):
    with tempfile.TemporaryDirectory(prefix='nat139-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        source = tmp / 't.c'
        source.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(source), str(PATCHES[driver])], check=True)
        text = '\n'.join(l for l in source.read_text().splitlines() if not l.startswith('#include'))
        for o, n in (('return *(volatile uint32_t *)reg;', 'return host_rd(reg);'),
                     ('*(volatile uint32_t *)reg = value;', 'host_wr(reg, value);')):
            assert text.count(o) == 1, o
            text = text.replace(o, n)
        pre = '#include "shim.h"\nuint32_t host_rd(uintptr_t); void host_wr(uintptr_t,uint32_t);\n'
        pre += 'extern int host_frames, host_clk_edges_outside_frames;\n'
        pre += '#define kernel_thread_start host_thread_start\nstatic int threads;\n'
        pre += 'static kern_return_t host_thread_start(void (*f)(void *,wait_result_t),void *a,thread_t *t) { (void)f;(void)a;*t=0;threads++;return 0;}\n'
        text += ('\nint main(void) { host_steps=3; e1s_touch_init(); printf("RESULT irq=%d threads=%d bad=%d outside=%d\\n",'
                 'host_irq_attached,threads,host_bad,host_clk_edges_outside_frames); return 0; }\n')
        source.write_text(pre + text)
        exe = tmp / 't'
        defs = ['-D%s=%d' % kv for kv in wiring.items()]
        subprocess.run(['cc', '-std=gnu11', '-w', '-I', str(HOST), *defs, str(source), str(HERE / 'host/peer139.c'), '-o', str(exe)],
                       check=True)
        return subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=10).stdout


def frames(out):
    return [l[len('FRAME'):].strip() for l in out.splitlines() if l.startswith('FRAME')]


def ids(out):
    dev = re.findall(r'poll \d device id: (.*?) \(((?:[0-9a-f]{2} ?){5})\)', out)
    hw = re.findall(r'poll \d hardware id: ((?:[0-9a-f]{2} ?){8})', out)
    return dev, hw


class PinMapTests(unittest.TestCase):
    def test_nat139_driver_reads_a_usi_wired_peer(self):
        out = run_case('nat139', USI)
        self.assertIn('RESULT irq=0 threads=0 bad=0 outside=0', out)
        self.assertIn('e1s-touch: spi9 map clk=gpp9-0 mosi=gpp9-1 miso=gpp9-2 cs=gpp9-3; miso cs-high=0 cs-low=0', out)
        self.assertIn('gpp9 con=0x1011 dat=0x8', out)
        # the level check selects the chip once without a clock edge, then the nine bounded read-only frames follow
        self.assertEqual(frames(out), [''] + EXPECTED_FRAMES)
        dev, hw = ids(out)
        self.assertEqual(dev, [('ok', PEER_DEVID)] * 3)
        self.assertEqual(hw, [PEER_HWID] * 3)
        self.assertIn('poll-only diagnostic complete', out)

    def test_nat128_driver_on_a_usi_wired_peer_is_the_phone_t1_class(self):
        out = run_case('nat128', USI)
        self.assertIn('RESULT irq=0 threads=0 bad=0', out)
        self.assertTrue(frames(out) and all(f == '' for f in frames(out)), frames(out))  # CS toggles, the peer's CLK pad never moves
        dev, hw = ids(out)
        self.assertEqual(len(dev), 3)
        self.assertTrue(all(s.startswith('no response') and b == '00 00 00 00 00' for s, b in dev), dev)
        self.assertEqual(hw, ['00 00 00 00 00 00 00 00'] * 3)

    def test_control_nat128_driver_reads_a_peer_wired_its_way(self):
        out = run_case('nat128', OLD)
        self.assertEqual(frames(out), EXPECTED_FRAMES)
        dev, hw = ids(out)
        self.assertEqual(dev, [('ok', PEER_DEVID)] * 3)
        self.assertEqual(hw, [PEER_HWID] * 3)

    def test_nat139_driver_on_an_old_wired_peer_reads_nothing(self):
        dev, hw = ids(run_case('nat139', OLD))
        self.assertTrue(all(b == '00 00 00 00 00' for _, b in dev), dev)
        self.assertEqual(hw, ['00 00 00 00 00 00 00 00'] * 3)

    def test_patch_changes_only_the_map_and_adds_the_level_check(self):
        nat128 = PATCHES['nat128'].read_text()
        nat139 = PATCHES['nat139'].read_text()
        added = [l for l in nat139.splitlines() if l.startswith('+') and not l.startswith('+++')]
        base = [l for l in nat128.splitlines() if l.startswith('+') and not l.startswith('+++')]
        extra = [l for l in added if l not in base]
        self.assertTrue(any('#define E1S_SPI_CLK_PIN         0' in l for l in extra))
        self.assertTrue(any('#define E1S_SPI_MISO_PIN        2' in l for l in extra))
        code = [l for l in extra if not re.match(r'^\+\s*(/?\*|$)', l)]
        writes = [l for l in code if 'pin_set' in l or 'gpio_wr' in l or 'pin_function' in l or 'pin_pull' in l]
        self.assertEqual(writes, ['+\t\tpin_set(E1S_GPP9_DAT, E1S_SPI_CS_PIN, false);', '+\t\tpin_set(E1S_GPP9_DAT, E1S_SPI_CS_PIN, true);'])
        self.assertFalse([l for l in code if 'e1s_spi_transfer' in l or 'stm_write' in l])


XNU = ORIG.parents[2]
KERNEL = ROOT / 'artifacts/nat-139/kernel-001/kernel.no-storage'
BUILD = ROOT / 'artifacts/nat-139/build-001/build.json'
NAME = 'loader-diag-xnu-scB-md1'


class ImageTests(unittest.TestCase):
    def test_kernel_carries_the_nat139_code(self):
        if not KERNEL.exists():
            self.skipTest('kernel artifact missing')
        data = KERNEL.read_bytes()
        for s in (b'spi9 map clk=gpp9-%u', b'poll-only diagnostic complete', b'e1s-keys: disabled (e1skeys=0)', b'msgbuf'):
            self.assertIn(s, data)

    def test_cmdline(self):
        if not BUILD.exists():
            self.skipTest('build artifact missing')
        b = json.loads(BUILD.read_text())
        cmd = b['payload_fixes'][NAME]['cmdline']
        t = cmd.split()
        for tok in ('msgbuf=1048576', 'e1spmic=2', 'e1skeys=0', 'e1sufs=0', 'e1sbattery=0', 'rd=md1', 'xrd=md0'):
            self.assertEqual(t.count(tok), 1, tok)
        self.assertFalse([x for x in t if x.startswith('ufs_write') or x.startswith('e1spmic=') and x != 'e1spmic=2'])
        self.assertLessEqual(len(cmd.encode()), 255)
        self.assertEqual(b['nat139_changes']['kernel'], hashlib.sha256(KERNEL.read_bytes()).hexdigest() if KERNEL.exists() else None)

    def test_ufs_write_has_one_reader_that_enables_on_one_only(self):
        hits = []
        for p in sorted((XNU / 'bsd').rglob('*.c')) + sorted((XNU / 'osfmk').rglob('*.c')) + sorted((XNU / 'iokit').rglob('*.cpp')):
            text = p.read_text(errors='replace')
            for line in text.splitlines():
                if 'PE_parse_boot_argn("ufs_write"' in line:
                    hits.append((p.name, line.strip()))
        self.assertEqual(hits, [('redwood_ufs.c', 'if (PE_parse_boot_argn("ufs_write", &check, sizeof(check)) && check == 1) {')])

    def test_msgbuf_boot_arg_is_xnus_own_and_bounded(self):
        log = (XNU / 'bsd/kern/subr_log.c').read_text()
        self.assertIn('PE_parse_boot_argn("msgbuf", &msgbuf_size, sizeof(msgbuf_size))', log)
        self.assertIn('if (size == 0 || size > MAX_MSG_BSIZE) {', log)
        self.assertIn('#define MAX_MSG_BSIZE   (1*1024*1024)', (XNU / 'bsd/sys/msgbuf.h').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
