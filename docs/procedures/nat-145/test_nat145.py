"""NAT-145 host tests: the SMP ADT against the donor's mkadt smp table, the built scE image, and analyze146 on NAT-144's real text plus
synthetic additions (added lines are made up, not phone output)."""
import hashlib
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import analyze146 as A  # noqa: E402
import make_adt145 as M  # noqa: E402

SRC = ROOT / 'artifacts/nat-020/build-003/source/tools/e1s/xnu'
ADT_IN = ROOT / 'artifacts/nat-117/e1s-product.adt'
BUILD = ROOT / 'artifacts/nat-145/build-001'
NAME = 'loader-diag-xnu-scE-md1'


def need(*paths):
    for p in paths:
        if not p.exists():
            raise unittest.SkipTest('%s missing' % p)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def cpus_of(adt, blob):
    root, _ = adt.parse(blob)
    c = [n for n in root.children if n.name == 'cpus'][0]
    return [{k: v for k, _, v in n.props if k != 'AAPL,phandle'} for n in c.children]


class Adt(unittest.TestCase):
    def test_matches_donor_mkadt_smp(self):
        need(ADT_IN, SRC / 'mkadt.py')
        adt = M._adt()
        out, rec = M.add_cpus(ADT_IN.read_bytes(), adt)
        self.assertEqual(rec['cpus'], 10)
        sys.path.insert(0, str(SRC))
        try:
            mk = load('nat145_mkadt', SRC / 'mkadt.py')
            donor = mk.build(smp=True)
        finally:
            sys.path.remove(str(SRC))
        donor = donor if isinstance(donor, (bytes, bytearray)) else adt.serialize(donor)
        self.assertEqual(cpus_of(adt, out), cpus_of(adt, bytes(donor)))

    def test_mpidr_map_and_phandles(self):
        need(ADT_IN)
        adt = M._adt()
        out, rec = M.add_cpus(ADT_IN.read_bytes(), adt)
        regs = [struct.unpack('<I', c['reg'])[0] for c in cpus_of(adt, out)]
        self.assertEqual(regs, [i << 8 for i in range(10)])
        small = ['small-core' in c for c in cpus_of(adt, out)]
        self.assertEqual(small, [True] * 4 + [False] * 6)
        root, _ = adt.parse(out)
        seen = []

        def walk(n):
            v = n.prop('AAPL,phandle')
            if v is not None and len(v) == 4:
                seen.append(struct.unpack('<I', v)[0])
            for c in n.children:
                walk(c)
        walk(root)
        self.assertEqual(len(seen), len(set(seen)), 'duplicate phandle')

    def test_refuses_second_pass(self):
        need(ADT_IN)
        out, _ = M.add_cpus(ADT_IN.read_bytes())
        with self.assertRaises(ValueError):
            M.add_cpus(out)


class Image(unittest.TestCase):
    def test_build_record(self):
        need(BUILD / 'build.json')
        r = json.loads((BUILD / 'build.json').read_text())
        cmd = r['payload_fixes'][NAME]['cmdline'].split()
        self.assertFalse(any(t.startswith('cpus=') or t.startswith('cpumask=') for t in cmd))
        for t in ('nat_attempt=NAT145-scE', 'loader_return_after=270', 'rec_secs=270', 'rd=md1', 'xrd=md0', 'e1s_wdt_pet=1'):
            self.assertEqual(cmd.count(t), 1, t)
        adt = (BUILD / NAME / 'payload.adt8.bin').read_bytes()
        self.assertEqual(hashlib.sha256(adt).hexdigest(), r['nat145_changes']['payload_adt_sha256'])
        self.assertEqual(r['nat145_changes']['adt']['cpus'], 10)

    def test_session_derivation(self):
        import subprocess
        p = subprocess.run([sys.executable, '-B', str(HERE / 'derive146.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


def real():
    t = ROOT / 'artifacts/nat-144/analysis/kernel-text.txt'
    p = ROOT / 'artifacts/nat-144/analysis/pixels.json'
    need(t, p)
    return t.read_text(errors='replace'), json.loads(p.read_text())


def kernel_tail(text, add):
    return text + ('' if text.endswith('\n') else '\n') + add


FT = ('[%8.6f]: MiniIOMobileFramebuffer: from one frame to the next: %d times under 10 ms, %d under 18, %d under 26, %d under 35, '
      '%d longer (the longest %d ms); half under %d ms, 95 in 100 under %d ms; %d pauses\n')


class Analyse(unittest.TestCase):
    def test_nat144_baseline(self):
        t, p = real()
        r = A.classify(t, p)
        self.assertEqual((r['ui'], r['smp']), ('U2-app-launched-after-press', 'C0-one'))
        self.assertEqual((r['cpus']['registered'], r['cpus']['started'], r['cpus']['ncpu'], r['cpus']['failed'], r['cpus']['running']),
                         ([0], [0], 1, [], 1))   # NAT-144 line 3502: "the slower cores started too: 1 processors running"
        self.assertEqual(len(r['frame_windows']), 17)
        self.assertEqual(r['fps_steady_windows'], 8)
        self.assertEqual(r['fps_median_interval_ms'], 57)
        self.assertTrue(16 < r['fps_best_window'] < 23, r['fps_best_window'])

    def test_ten_cpus_is_c2(self):
        t, p = real()
        add = ''.join('[ 1.%d]: GenericARMCPU: cpu %d (phys id 0x%x) registered\n[ 1.%d]: cpu_start() cpu: %d\n' % (i, i, i << 8, i, i)
                      for i in range(1, 10))
        add += '[ 2.0]: GenericARMPE: 7 of 10 processors are running\n[ 30.0]: GenericARMPE: the slower cores started too: 10 processors running\n'
        t = t.replace('page size 16384, 1 cpu', 'page size 16384, 10 cpus')
        r = A.classify(kernel_tail(t, add), p)
        self.assertEqual(r['smp'], 'C2-all-ten')
        self.assertEqual(r['cpus']['started'], list(range(10)))
        self.assertEqual(r['cpus']['running'], 10)
        r = A.classify(kernel_tail(t, add.replace('the slower cores started too: 10', 'the slower cores started too: 9')), p)
        self.assertEqual((r['smp'], r['cpus']['running']), ('C1-some', 9))

    def test_failure_makes_c1(self):
        t, p = real()
        add = ''.join('[ 1.%d]: cpu_start() cpu: %d\n' % (i, i) for i in range(1, 9))
        add += '[ 1.9]: psci: cpu 9 (MPIDR 0x900) was not started: the firmware answers -2 (INVALID_PARAMETERS)\n'
        r = A.classify(kernel_tail(t.replace('page size 16384, 1 cpu', 'page size 16384, 9 cpus'), add), p)
        self.assertEqual(r['smp'], 'C1-some')
        self.assertEqual(r['cpus']['failed'], [dict(cpu=9, what='was not started')])
        self.assertEqual(r['cpus']['ncpu'], 9)

    def test_fps_steady_rule(self):
        t, p = real()
        add = FT % (400.0, 0, 0, 0, 0, 0, 0, 0, 0, 0)          # anchor
        add += FT % (405.0, 10, 290, 0, 0, 0, 17, 16, 17, 0)   # 300 frames in 5 s = 60/s, no pause
        add += FT % (410.0, 100, 500, 0, 0, 0, 17, 9, 17, 3)   # faster but with pauses: not steady
        add += FT % (410.5, 30, 0, 0, 0, 0, 9, 9, 9, 0)        # 30 frames in 0.5 s: 60/s, at the 20-frame floor or above
        r = A.classify(kernel_tail(t, add), p)
        rates = {w['t']: w['rate'] for w in r['frame_windows']}
        self.assertEqual(rates[405.0], 60.0)
        self.assertEqual(rates[410.0], 120.0)
        self.assertEqual(r['fps_best_window'], 60.0)

    def test_stop_notes(self):
        t, p = real()
        r = A.classify(kernel_tail(t, '\npsci: cpu 3 did not stop: it is left running\n'), p)
        self.assertEqual(r['cpus']['stop_notes'], [dict(cpu=3, what='did not stop')])


if __name__ == '__main__':
    unittest.main()
