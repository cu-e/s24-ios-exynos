"""analyze142 on the real NAT-140 text and on synthetic additions (host-test; added lines are made up, not phone output)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze142 as A  # noqa: E402

ROOT = HERE.parents[2]


def real():
    t = ROOT / 'artifacts/nat-140/analysis/kernel-text.txt'
    p = ROOT / 'artifacts/nat-140/analysis/pixels.json'
    if not t.exists() or not p.exists():
        raise unittest.SkipTest('NAT-140 analysis artifacts missing')
    return t.read_text(errors='replace'), json.loads(p.read_text())


START = '[ 1.0]: e1s-touch: event thread started (gpa1 pud=0x11111011)\n'


def sense(ready='yes', echo='yes'):
    return '[ 1.1]: e1s-touch: start: sense on (ready %s, scan echo %s); polling events every 10000 us, no IRQ\n' % (ready, echo)


class Tests(unittest.TestCase):
    def test_nat140_text(self):
        t, p = real()
        r = A.classify(t, p)
        self.assertEqual((r['touch'], r['power'], r['start'], r['events'], r['physical_input']),
                         ('T2-chip-answers', 'P2-both-rails-verified', 'S0-no-thread', 'E0-no-coordinates', 'not-established'))
        self.assertTrue(r['reader'].startswith('R1-open'))

    def test_start_states(self):
        t, p = real()
        self.assertEqual(A.classify(t + START + sense('no', 'yes'), p)['start'], 'S1-not-ready')
        self.assertEqual(A.classify(t + START + sense('yes', 'no'), p)['start'], 'S2-no-scan-echo')
        self.assertEqual(A.classify(t + START + sense(), p)['start'], 'S3-sense-on')
        self.assertEqual(A.classify(t + START, p)['start'], 'S0-no-thread')

    def test_coordinates(self):
        t, p = real()
        add = START + sense() + ('[ 2.0]: e1s-touch: coord 1: finger 0 action 1 x 2048 y 1000\n'
                                 '[12.0]: e1s-touch: events after 1000 polls: coord 7 (press 2 release 2) other 1; irq line low in 9 polls\n')
        r = A.classify(t + add, p)
        self.assertEqual((r['events'], r['coord_total'], r['physical_input']), ('E1-coordinates', 7, 'controller-events'))
        self.assertEqual(r['coord_lines'][0], dict(n=1, finger=0, action=1, x=2048, y=1000))

    def test_zero_summary_is_no_coordinates(self):
        t, p = real()
        add = START + sense() + '[12.0]: e1s-touch: events after 1000 polls: coord 0 (press 0 release 0) other 0; irq line low in 0 polls\n'
        self.assertEqual(A.classify(t + add, p)['events'], 'E0-no-coordinates')


if __name__ == '__main__':
    unittest.main(verbosity=2)
