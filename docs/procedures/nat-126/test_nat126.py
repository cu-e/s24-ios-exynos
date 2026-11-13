#!/usr/bin/env python3
"""NAT-126 host checks; no native action."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoPmicTests(unittest.TestCase):
    def test_disabled_init_never_probes_or_sends(self):
        tests = load('nat126_pmic_test', HERE.parent / 'nat-123/test_nat123.py')
        tests.TransportTests.setUpClass()
        try:
            out = tests.TransportTests().run_case(mode=0)
        finally:
            tests.TransportTests.tearDownClass()
        self.assertIn('disabled (e1spmic=0)', out)
        self.assertIn('RESULT cmds=0 writes=0 bad=0', out)
        self.assertNotIn('e1s-acpm:', out)

    def test_touch_guard_controls(self):
        tests = load('nat126_touch_test', HERE.parent / 'nat-125/test_nat125.py')
        self.assertIn('irq=1 threads=1', tests.run_case(fixed=False))
        self.assertIn('irq=0 threads=0', tests.run_case())
        self.assertIn('irq=1 threads=1', tests.run_case(responsive='valid'))

    def test_actual_cmdline_is_readonly_pmic(self):
        import json
        path = ROOT / 'artifacts/nat-126/build-001/build.json'
        self.assertTrue(path.exists(), 'NAT-126 image not built')
        report = json.loads(path.read_text())
        cmd = report['payload_fixes']['loader-diag-xnu-sc9-md1']['cmdline']
        tokens = cmd.split()
        self.assertLess(len(cmd.encode()), 256)
        for need in ('e1spmic=0', 'e1s_wdt_pet=1', 'e1s_decon_hw=1', 'serial=3', 'rd=md1', 'xrd=md0'):
            self.assertEqual(tokens.count(need), 1, need)
        for forbidden in ('e1spmic=2', 'e1spmic=3', 'e1stouch=0'):
            self.assertNotIn(forbidden, tokens)
        self.assertEqual(report['nat126_changes']['kernel'], 'a31e746c961beae19a58deef24a9e0df72e3764fd66478eb0e369b936eba485a')


if __name__ == '__main__':
    unittest.main(verbosity=2)
