"""analyze144 on NAT-142's real text and on synthetic additions (host-test; added lines are made up, not phone output)."""
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze144 as A  # noqa: E402

ROOT = HERE.parents[2]


def real():
    t = ROOT / 'artifacts/nat-142/analysis/kernel-text.txt'
    p = ROOT / 'artifacts/nat-142/analysis/pixels.json'
    if not t.exists() or not p.exists():
        raise unittest.SkipTest('NAT-142 analysis artifacts missing')
    return t.read_text(errors='replace'), json.loads(p.read_text())


def launch(bundle, wall='00:04:30.1'):
    return ('com.apple.xpc.launchd|1970-01-01 %s (user/501/UIKitApplication:%s[a1b2][rb-legacy]) <Notice>: '
            'service state: spawning\n' % (wall, bundle))


def console(text, add):
    """Insert `add` at the end of the console stream (before the first kernel line), where launchd lines are."""
    lines = text.splitlines(True)
    k0 = next(i for i, l in enumerate(lines) if A.RE_KT.match(l))
    return ''.join(lines[:k0]) + add + ''.join(lines[k0:])


def before_unlock(text, add):
    lines = text.splitlines(True)
    i = next(i for i, l in enumerate(lines) if 'hakios: unlock: asked, answer 1' in l)
    return ''.join(lines[:i]) + add + ''.join(lines[i:])


class Tests(unittest.TestCase):
    def test_nat142_text(self):
        t, p = real()
        r = A.classify(t, p)
        self.assertEqual((r['start'], r['events'], r['ui'], r['wake'], r['press_count']),
                         ('S3-sense-on', 'E1-coordinates', 'U0-no-press-on-home-screen', 'W0', 0))
        self.assertEqual([m['mode'] for m in r['ui_modes']], [0xff, 0xfe, 0x1, 0])
        self.assertEqual(r['home_at']['answer'], 1)
        self.assertTrue(240 < r['home_at']['t_lo'] < 245, r['home_at'])
        self.assertEqual([a['bundle'] for a in r['apps']], [])
        self.assertEqual(r['physical_input'], 'controller-events')
        self.assertEqual(r['frame_changes'], 24)
        self.assertTrue(r['clock_check']['ok'], r['clock_check'])
        self.assertEqual(r['clock_check']['pairs'], 53)
        self.assertLess(abs(r['clock_check']['median_wall_minus_kernel_s']), 0.05)

    def test_press_then_app_is_u2(self):
        t, p = real()
        r = A.classify(console(t, launch('com.apple.Preferences')) + '[ 260.0]: e1s-touch: press 92: finger 0 x 700 y 1500\n', p)
        self.assertEqual(r['ui'], 'U2-app-launched-after-press')
        self.assertEqual(r['app_after_press'][0]['app']['bundle'], 'com.apple.Preferences')
        self.assertEqual(r['physical_input'], 'ui-action')

    def test_spotlight_alone_is_not_a_touch_action(self):
        t, p = real()
        r = A.classify(console(t, launch('com.apple.Spotlight')) + '[ 260.0]: e1s-touch: press 92: finger 0 x 700 y 1500\n', p)
        self.assertEqual(r['ui'], 'U1-press-on-home-screen')
        self.assertEqual(r['physical_input'], 'controller-events')

    def test_app_too_long_after_the_press(self):
        t, p = real()
        add = '[ 245.0]: e1s-touch: press 92: finger 0 x 700 y 1500\n'
        self.assertEqual(A.classify(console(t, launch('com.apple.Preferences')) + add, p)['ui'], 'U1-press-on-home-screen')

    def test_clock_check_failure_withholds_u2(self):
        t, p = real()
        t = re.sub(r'1970-01-01 00:(\d\d):', lambda m: '1970-01-01 00:%02d:' % (int(m[1]) + 1), t)   # wall clock 60 s ahead
        r = A.classify(console(t, launch('com.apple.Preferences', '00:05:35.0')) + '[ 325.0]: e1s-touch: press 92: finger 0 x 7 y 1\n', p)
        self.assertFalse(r['clock_check']['ok'])
        self.assertTrue(59 < r['clock_check']['median_wall_minus_kernel_s'] < 61)
        self.assertEqual(r['ui'], 'U1-app-after-press-clock-unverified')
        self.assertEqual(r['physical_input'], 'controller-events')

    def test_app_without_press_or_before_home(self):
        t, p = real()
        self.assertEqual(A.classify(console(t, launch('com.apple.Preferences')), p)['ui'], 'U0-no-press-on-home-screen')
        early = before_unlock(t, launch('com.apple.Preferences')) + '[ 230.0]: e1s-touch: press 5: finger 0 x 1 y 1\n'
        self.assertEqual(A.classify(early, p)['ui'], 'U0-no-press-on-home-screen')

    def test_wake_after_press(self):
        t, p = real()
        self.assertEqual(A.classify(t + '[ 237.0]: e1s-touch: press 80: finger 0 x 1 y 1\n', p)['wake'], 'W1-press-then-wake')
        self.assertEqual(A.classify(t + '[ 220.0]: e1s-touch: press 80: finger 0 x 1 y 1\n', p)['wake'], 'W0')


if __name__ == '__main__':
    unittest.main(verbosity=2)
