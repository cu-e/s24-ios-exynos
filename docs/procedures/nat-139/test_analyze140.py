"""analyze140 on the real NAT-137 and NAT-124 texts and on synthetic additions (host-test; added lines are made up, not phone output)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze140 as A  # noqa: E402

ROOT = HERE.parents[2]


def real(run):
    t = ROOT / ('artifacts/%s/analysis/kernel-text.txt' % run)
    p = ROOT / ('artifacts/%s/analysis/pixels.json' % run)
    if not t.exists() or not p.exists():
        raise unittest.SkipTest('%s analysis artifacts missing' % run)
    return t.read_text(errors='replace'), json.loads(p.read_text())


MAP = '[  10.0]: e1s-touch: spi9 map clk=gpp9-0 mosi=gpp9-1 miso=gpp9-2 cs=gpp9-3; miso cs-high=0 cs-low=1\n'
ANSWER = ('[  10.1]: e1s-touch: poll 1 device id: ok (5a 13 9c 01 7e)\n'
          '[  10.1]: e1s-touch: poll 1 hardware id: 31 32 33 34 35 36 37 38\n')


class Tests(unittest.TestCase):
    def test_nat137_text_reproduces_its_verdicts_and_the_log_gap(self):
        t, p = real('nat-137')
        r = A.classify(t, p)
        self.assertEqual((r['window'], r['display'], r['touch'], r['power'], r['keys']),
                         ('W-ok', 'D2-refreshing', 'T1-no-response', 'P0-no-verified-rails', 'K0-disabled'))
        self.assertEqual((r['spi_map'], r['miso'], r['log']), ('MAP-missing', None, 'L-pmic-lost'))
        self.assertEqual(r['msgbuf_section_bytes'], 131102)

    def test_nat124_text_keeps_the_pmic_lines(self):
        t, p = real('nat-124')
        r = A.classify(t, p)
        self.assertEqual(r['log'], 'L-pmic-kept')
        self.assertNotEqual(r['power'], 'P0-no-verified-rails')

    def test_map_line_and_answer(self):
        t, p = real('nat-137')
        r = A.classify(t + MAP + ANSWER, p)
        self.assertEqual((r['spi_map'], r['miso']), ('MAP-ok', dict(cs_high=0, cs_low=1)))
        self.assertEqual(r['touch'], 'T2-chip-answers')
        self.assertEqual(r['physical_input'], 'not-established')

    def test_unexpected_map_is_reported(self):
        t, p = real('nat-137')
        r = A.classify(t + MAP.replace('clk=gpp9-0', 'clk=gpp9-2').replace('miso=gpp9-2', 'miso=gpp9-0'), p)
        self.assertEqual(r['spi_map'], 'MAP-unexpected (2, 1, 0, 3)')


if __name__ == '__main__':
    unittest.main(verbosity=2)
