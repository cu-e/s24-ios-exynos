"""Synthetic-text tests of analyze137 (host-test; the texts are made up, not phone output)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze137 as A  # noqa: E402

ROOT = HERE.parents[2]
REAL_TEXT = ROOT / 'artifacts/nat-127/analysis/kernel-text.txt'
REAL_PIX = ROOT / 'artifacts/nat-127/analysis/pixels.json'


def base():
    if not REAL_TEXT.exists():
        raise unittest.SkipTest('NAT-127 analysis artifacts missing')
    return REAL_TEXT.read_text(errors='replace'), json.loads(REAL_PIX.read_text())


def polls(dev, hw, n=3):
    return ''.join('[  10.0]: e1s-touch: poll %d device id: %s (%s)\n[  10.1]: e1s-touch: poll %d hardware id: %s\n'
                   % (i, 'no response (rails off, pins wrong, or chip held in reset)' if dev == '00 00 00 00 00' else 'ok', dev, i, hw)
                   for i in range(1, n + 1)) + '[  10.2]: e1s-touch: poll-only diagnostic complete; no IRQ or event thread\n'


class Tests(unittest.TestCase):
    def test_nat127_text_has_no_poll_lines(self):
        t, p = base()
        r = A.classify(t, p)
        self.assertEqual(r['touch'], 'T0-no-poll')
        self.assertEqual(r['window'], 'W-ok')
        self.assertEqual(r['keys'], 'K1-not-disabled')

    def test_no_response(self):
        t, p = base()
        r = A.classify(t + polls('00 00 00 00 00', '00 00 00 00 00 00 00 00') + 'e1s-keys: disabled (e1skeys=0)\n', p)
        self.assertEqual((r['touch'], r['keys'], r['complete']), ('T1-no-response', 'K0-disabled', True))
        self.assertEqual(len(r['polls']), 3)

    def test_all_ff_is_no_response(self):
        t, p = base()
        self.assertEqual(A.classify(t + polls('ff ff ff ff ff', 'ff ff ff ff ff ff ff ff'), p)['touch'], 'T1-no-response')

    def test_hardware_id_alone_is_an_answer(self):
        t, p = base()
        r = A.classify(t + polls('00 00 00 00 00', '50 34 00 00 00 00 00 00'), p)
        self.assertEqual(r['touch'], 'T2-chip-answers')
        self.assertIn('poll 1 hardware id 50 34 00 00 00 00 00 00', r['reasons'])

    def test_device_id_answer(self):
        t, p = base()
        self.assertEqual(A.classify(t + polls('20 50 34 00 00', '00 00 00 00 00 00 00 00', n=1), p)['touch'], 'T2-chip-answers')

    def test_panic_in_touch(self):
        t, p = base()
        self.assertEqual(A.classify(t + 'panic(cpu 0 caller 0x1): e1s_touch_init fault\n', p)['touch'], 'T0-fault')

    def test_rail_readbacks_pass_through(self):
        t, p = base()
        rails = ('e1s-pmic: touch I/O LDO18 enabled (0x3d 0x58 -> 0xd8 -> 0xd8)\n'
                 'e1s-pmic: touch AVDD LDO9 enabled (0x34 0x70 -> 0xf0 -> 0xf0)\ne1s-pmic: touch rails are on (settled 100 ms)\n')
        r = A.classify(t + rails, p)
        self.assertEqual(r['power'], 'P2-both-rails-verified')
        self.assertEqual(len(r['rail_readbacks']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=1)
