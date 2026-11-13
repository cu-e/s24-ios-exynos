"""NAT-148 host tests: the boot-CPU state fix, the built scF image against scE, and the kernel's own ml_parse_cpu_topology on the
NAT-035 model (that class needs capstone: run with artifacts/nat-065/venv/bin/python; it skips otherwise)."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import make_adt148 as M  # noqa: E402

ADT_IN = ROOT / 'artifacts/nat-117/e1s-product.adt'
E = ROOT / 'artifacts/nat-145/build-001/loader-diag-xnu-scE-md1/payload.adt8.bin'
F = ROOT / 'artifacts/nat-148/build-001/loader-diag-xnu-scF-md1/payload.adt8.bin'
BUILD = ROOT / 'artifacts/nat-148/build-001/build.json'


def need(*paths):
    for p in paths:
        if not p.exists():
            raise unittest.SkipTest('%s missing' % p)


def states(blob):
    adt = M.m145._adt()
    root, _ = adt.parse(blob)
    c = [n for n in root.children if n.name == 'cpus'][0]
    return [n.prop('state') for n in c.children]


class Fix(unittest.TestCase):
    def test_one_running_nine_waiting(self):
        need(ADT_IN)
        out, rec = M.add_cpus(ADT_IN.read_bytes())
        self.assertEqual(states(out), [M.RUNNING] + [M.WAITING] * 9)
        self.assertEqual(rec['nat148_waiting'], ['cpu%d' % i for i in range(1, 10)])
        self.assertEqual(len(out), len(M.m145.add_cpus(ADT_IN.read_bytes())[0]))   # same-length values

    def test_scE_adt_has_ten_running(self):
        """The NAT-146 defect, on NAT-145's own function: every node 'running'."""
        need(ADT_IN)
        out, _ = M.m145.add_cpus(ADT_IN.read_bytes())
        self.assertEqual(states(out), [M.RUNNING] * 10)

    def test_fix_is_idempotent_and_rejects_other_states(self):
        need(ADT_IN)
        out, _ = M.add_cpus(ADT_IN.read_bytes())
        again, changed = M.fix_states(out)
        self.assertEqual((again, changed), (out, []))
        bad = out.replace(M.WAITING, b'offline\0', 1)
        with self.assertRaises(ValueError):
            M.fix_states(bad)


class Image(unittest.TestCase):
    def test_payload_differs_from_scE_only_in_tag_and_nine_states(self):
        need(E, F)
        a, b = E.read_bytes(), F.read_bytes()
        self.assertEqual(len(a), len(b))
        d = [i for i in range(len(a)) if a[i] != b[i]]
        runs = []
        for i in d:
            if runs and i == runs[-1][1] + 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
        state_runs = [r for r in runs if b'running' in a[r[0] - 7:r[1] + 8]]      # inside one 'running' value
        self.assertEqual(len(state_runs), 9)
        for s, e in state_runs:
            self.assertIn(b'running', a[s - 3:e + 4])
            self.assertIn(b'waiting', b[s - 3:e + 4])
        tag = [r for r in runs if r not in state_runs]
        self.assertTrue(all(r[1] < 0x100 for r in tag), tag)                # the command line at the payload's start
        self.assertIn(b'NAT145-scE', a[:0x100])
        self.assertIn(b'NAT148-scF', b[:0x100])

    def test_build_record(self):
        need(BUILD)
        r = json.loads(BUILD.read_text())
        c = r['nat148_changes']
        self.assertEqual(c['payload_cpu_states'], ['running'] + ['waiting'] * 9)
        cmd = r['payload_fixes']['loader-diag-xnu-scF-md1']['cmdline'].split()
        self.assertFalse(any(t.startswith('cpus=') for t in cmd))
        self.assertEqual(cmd.count('nat_attempt=NAT148-scF'), 1)

    def test_session_derivation(self):
        p = subprocess.run([sys.executable, '-B', str(HERE / 'derive149.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


try:
    import capstone  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, 'capstone not available (use artifacts/nat-065/venv/bin/python)')
class Model(unittest.TestCase):
    """The NAT-022 payload kernel's own ml_parse_cpu_topology from a checkpoint-35 stop on the NAT-035 model."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('nat148_model', HERE / 'model_topology.py')
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_baseline_one_cpu(self):
        r = self.m.run('baseline')
        self.assertEqual((r['stopped_at'], r.get('checkpoint'), r['topology']['num_cpus']), ('checkpoint', 12, 1))

    def test_as_built_asserts_second_boot_cpu(self):
        r = self.m.run('running')
        self.assertEqual(r['stopped_at'], '_Assert')
        self.assertEqual(r['assert']['expression'], 'topology_info.boot_cpu == NULL')
        self.assertEqual(r['topology']['num_cpus'], 2)

    def test_fixed_ten_cpus_to_checkpoint_14(self):
        r = self.m.run('waiting')
        self.assertEqual((r['stopped_at'], r.get('checkpoint')), ('checkpoint', 12))
        self.assertEqual(r['topology']['num_cpus'], 10)
        self.assertEqual(r['topology']['boot_cpu_index'], 0)
        self.assertEqual([c['phys_id'] for c in r['topology']['cpus']], [hex(i << 8) for i in range(10)])
        self.assertEqual(r['after_12'], [40, 41, 42, 43, 44, 13, 14])
        self.assertEqual(r['master_cpu'], 0)


if __name__ == '__main__':
    unittest.main()
