#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-176 host tests: the display snapshot patch only loads, reads exactly NAT-162's table, and reads nothing but the PMU unless
DPUB, DPUF0 and DPUF1 all report power."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_display.c'
PATCH = HERE / 'e1s_display.patch'

WIN = [0x0, 0x4, 0x8, 0xc, 0x10, 0x14, 0x18, 0x1c] + [0x800 + 4 * i for i in range(8)]
DMA = [0x8, 0xc, 0x10, 0x14, 0x18, 0x1c, 0x40, 0x50, 0x200, 0x338, 0x740] + [0x408, 0x40c, 0x410, 0x414, 0x418, 0x41c, 0x440, 0x450]
DPP = [0x0, 0x1c, 0x30, 0x34, 0x38, 0x3c] + [0x80 + 4 * i for i in range(7)]
TABLE = {   # docs/procedures/nat-162/README.md, "The native step before any write"
    'decon': (0x19100000, [0x4, 0x30, 0x50, 0x60, 0x200, 0x204, 0x4]),
    'win2': (0x19112000, WIN), 'win3': (0x19113000, WIN),
    'wincon2': (0x19132000, [0x0]), 'wincon3': (0x19133000, [0x0]),
    'dma0': (0x19900000, DMA), 'dma1': (0x19901000, DMA),
    'dpp0': (0x19930000, DPP), 'dpp1': (0x19931000, DPP),
    'sramc0': (0x19950000, [0x10, 0x14]), 'sramc1': (0x19951000, [0x10, 0x14]),
    'sysmmu': (0x19840000, [0x0, 0x8, 0x34, 0x8000, 0x8404]),
}


def patched():
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        t = Path(tmp) / 'e1s_display.c'
        t.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(t), str(PATCH)], check=True)
        return t.read_text()


def run(env=None):
    with tempfile.TemporaryDirectory(prefix='nat176-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        text = '\n'.join(l for l in patched().splitlines() if not l.startswith('#include'))
        src = tmp / 'd.c'
        src.write_text('#include "shim176.h"\n' + text)
        exe = tmp / 'd'
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wno-unused-function', '-Werror', '-I', str(HERE / 'host'), str(src),
                        str(HERE / 'host/fakemmio176.c'), '-o', str(exe)], check=True)
        e = dict(os.environ, **(env or {}))
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, env=e)
        assert r.returncode == 0, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
        return r.stdout


def snapshots(out, when):
    got = {}
    for m in re.finditer(r'^e1s-dpp: %s (\w+) (0x[0-9a-f]+)((?: [0-9a-f]+=[0-9a-f]+)+)$' % when, out, re.M):
        pairs = [tuple(int(x, 16) for x in p.split('=')) for p in m.group(3).split()]
        got[m.group(1)] = (int(m.group(2), 16), pairs)
    return got


class Static(unittest.TestCase):
    def test_added_lines_only_load(self):
        added = [l[1:] for l in PATCH.read_text().splitlines() if l.startswith('+') and not l.startswith('+++')]
        removed = [l[1:] for l in PATCH.read_text().splitlines() if l.startswith('-') and not l.startswith('---')]
        code = '\n'.join(added)
        # every use of a register pointer is a NULL test, the ml_io_map assignment, or an e1s_display_read argument
        for m in re.finditer(r'(e1s_dpp_pmu|e1s_dpp_map\[g\])', code):
            tail = code[m.end():m.end() + 40]
            head = code[max(0, m.start() - 40):m.start()]
            ok = (head.endswith('static volatile uint32_t *') or tail.lstrip().startswith('== NULL') or tail.lstrip().startswith('= (volatile uint32_t *)ml_io_map(')
                  or head.rstrip().endswith('e1s_display_read(') or head.rstrip().endswith('e1s_display_read(\n'))
            self.assertTrue(ok, code[m.start() - 30:m.end() + 40])
        rest = '\n'.join(l for l in added if 'e1s_dpp_groups[] = {' not in l and '= (volatile uint32_t *)ml_io_map(' not in l)
        self.assertNotRegex(rest, r'\]\s*=[^=]', 'no indexed store')
        self.assertNotRegex(code, r'\*\s*\(\s*volatile', 'no raw volatile access')
        # nothing of the original is removed except the probe's own lines, which are re-added unchanged
        self.assertTrue(all(l in added for l in removed), [l for l in removed if l not in added])


class Run(unittest.TestCase):
    def test_table_both_snapshots(self):
        out = run()
        for when in ('probe', 'late'):
            got = snapshots(out, when)
            self.assertEqual(set(got), set(TABLE), when)
            for name, (pa, offs) in TABLE.items():
                self.assertEqual(got[name][0], pa, name)
                self.assertEqual([o for o, _ in got[name][1]], offs, name)
                for o, v in got[name][1]:
                    self.assertEqual(v, 0xA0000000 | ((pa + o) & 0x0fffffff), (name, hex(o)))
            self.assertIn('e1s-dpp: %s pmu dpub 0x1 dpuf0 0x1 dpuf1 0x1' % when, out)
        lines = out.splitlines()
        late = lines.index(next(l for l in lines if l.startswith('e1s-dpp: late pmu')))
        self.assertEqual(lines[late - 1], 'clock 300 s')         # taken once 300 s of uptime have passed, not before
        self.assertIn('e1s-dpp: late snapshot thread started (at 300 s)', out)
        maps = re.findall(r'^map (0x[0-9a-f]+) ', out, re.M)
        self.assertEqual(len(maps), len(set(maps)), 'each block mapped once')

    def test_gate(self):
        for var in ('E1S_DPUB', 'E1S_DPUF0', 'E1S_DPUF1'):
            out = run({var: '0x0'})
            self.assertEqual(snapshots(out, 'probe'), {}, var)
            self.assertEqual(snapshots(out, 'late'), {}, var)
            self.assertEqual(out.count('skipped: a display power domain is off'), 2, var)
            self.assertEqual(re.findall(r'^map (0x[0-9a-f]+) ', out, re.M), ['0x12860000'], var)
        out = run({'E1S_DPUF1': '0x2'})                          # bit 0 is what counts
        self.assertEqual(snapshots(out, 'probe'), {})

    def test_off(self):
        out = run({'BOOTARG_e1sdpp': '0'})
        self.assertNotIn('e1s-dpp', out)
        self.assertNotIn('map ', out)


def _dpp177():
    import importlib.util
    spec = importlib.util.spec_from_file_location('nat176_dpp177', HERE / 'dpp177.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Analyser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _dpp177()
        cls.out = run()

    def test_ok_and_decode(self):
        r = self.m.analyse(self.out)
        self.assertEqual(r['verdict'], 'R-ok')
        self.assertEqual(r['changed_probe_to_late'], {})
        self.assertEqual(r['probe']['dma1']['base'], hex(0xA0000000 | 0x9901040))
        self.assertEqual(len(r['probe']['decon']['frame_count']), 2)

    def test_visible_scaler_and_sysmmu(self):
        text = self.out.replace('wincon3 0x19133000 0=a9133000', 'wincon3 0x19133000 0=11')
        text = text.replace('sysmmu 0x19840000 0=a9840000', 'sysmmu 0x19840000 0=0')
        r = self.m.analyse(text)
        self.assertEqual(r['probe']['visible'], [dict(window='win3', dpp=1, has_scaler=True)])
        self.assertFalse(r['probe']['sysmmu']['translating'])
        late = text.replace('e1s-dpp: late dpp1 0x19931000 0=a9931000', 'e1s-dpp: late dpp1 0x19931000 0=a9931001')
        self.assertEqual(self.m.analyse(late)['changed_probe_to_late'], {'dpp1': {'0x0': ['0xa9931000', '0xa9931001']}})

    def test_other_verdicts(self):
        self.assertEqual(self.m.analyse('nothing\n')['verdict'], 'R-none')
        self.assertEqual(self.m.analyse(run({'E1S_DPUF0': '0'}))['verdict'], 'R-gated')
        partial = '\n'.join(l for l in self.out.splitlines() if not l.startswith('e1s-dpp: late sramc1'))
        self.assertEqual(self.m.analyse(partial)['verdict'], 'R-partial')


if __name__ == '__main__':
    unittest.main()
