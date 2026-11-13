#!/usr/bin/env python3
"""NAT-143 host checks: NAT-141's start-sequence and event-thread cases rerun on the NAT-143 patch (regression), plus the press/release
log lines the UI correlation needs. The driver's own e1s_touch.c runs against NAT-141's pin-level synthetic STM peer
(docs/procedures/nat-141/host/peer141.c: READY, echo, then press/move/release of finger 1 at x 0x123 y 0x456).

Host-test only: the peer's bytes are synthetic.
"""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nat143_test141', HERE.parent / 'nat-141/test_nat141.py')
t141 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t141)
t141.PATCH = HERE / 'e1s_touch_combined.patch'     # run_case() reads the module global at call time
t141.HERE = HERE.parent / 'nat-141'                 # peer141.c stays NAT-141's


class Nat141CasesOnNat143Patch(t141.StartAndEventTests):
    pass


class PressReleaseLog(unittest.TestCase):
    def test_press_and_release_are_logged_with_raw_coordinates(self):
        out = t141.run_case()
        lines = [l for l in out.splitlines() if l.startswith('e1s-touch: press ') or l.startswith('e1s-touch: release ')]
        self.assertEqual(lines, ['e1s-touch: press 1: finger 1 x 291 y 1110', 'e1s-touch: release 1: finger 1 x 291 y 1110'])

    def test_moves_are_not_logged_as_touches(self):
        out = t141.run_case()
        self.assertNotIn('e1s-touch: move', out)
        self.assertEqual(out.count('e1s-touch: press '), 1)

    def test_patch_differs_from_nat141_only_by_the_touch_log(self):
        old = (HERE.parent / 'nat-141/e1s_touch_combined.patch').read_text().splitlines()
        new = (HERE / 'e1s_touch_combined.patch').read_text().splitlines()
        added = [l for l in new if l not in old]
        removed = [l for l in old if l not in new]
        self.assertTrue(all(l.startswith('@@') or 'logged_' in l or 'E1S_EV_LOG_TOUCH' in l or 'press' in l or 'release' in l
                            or l.strip() in ('+\t\t\t\t}',) for l in added), added)
        self.assertTrue(all(l.startswith('@@') or 'logged_o = 0, reports = 0' in l for l in removed), removed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
