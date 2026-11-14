"""NAT-165 host tests: the kernel differs from NAT-152's only in redwood_input.o (NAT-121's patch plus one call), the call reaches only
load_start() with no cpufreq/ddr boot-arg (source at the pinned SHA equals the derive-001 source built), the image is scJ's with
cpuload=1000 and this kernel, the loader gates pass, load166 decodes synthetic lines in the driver's format, and the session is a
counted derivation."""
import difflib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
J = ROOT / 'artifacts/nat-158/build-001'
M = ROOT / 'artifacts/nat-165/build-001'
JN, MN = 'loader-diag-xnu-scJ-md1', 'loader-diag-xnu-scM-md1'
DERIVE = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev'


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


class Kernel(unittest.TestCase):
    def test_one_object_changed(self):
        need(ROOT / 'artifacts/nat-165/kernel-001/rebuild.json')
        b = load('nat165_b_t', HERE / 'build.py')
        r = b.check_kernel()
        self.assertEqual(r['expect_strings']['tl: u at %llu'], 1)
        self.assertEqual([l.strip() for l in b.nat121_hunks_kept() if not l.strip().startswith(('/*', '*'))], ['redwood_cpufreq_init();'])

    def test_call_reaches_only_load_start(self):
        need(DERIVE / 'redwood_cpufreq.c')
        up = subprocess.run(['git', '-C', str(ROOT / 'references/s24-port'), 'show',
                             'c8860decc62c6d6180e609036d027a2997972420:xnu/hackios/files/bsd/dev/redwood_cpufreq.c'], capture_output=True, text=True)
        if up.returncode:
            raise unittest.SkipTest('pinned upstream missing')
        src = (DERIVE / 'redwood_cpufreq.c').read_text()
        self.assertEqual(src, up.stdout)
        body = src[src.index('redwood_cpufreq_init(void)\n{'):]
        body = body[:body.index('\n}\n')]
        steps = [l.strip() for l in body.splitlines()]
        i = steps.index('load_start();')
        self.assertEqual(steps[i + 1:i + 3], ['enabled = 2;', 'PE_parse_boot_argn("ddr", &enabled, sizeof(enabled));'])
        self.assertIn('} else if (enabled == 2 && cpufreq_wanted()) {', steps)
        self.assertIn('if (!PE_parse_boot_argn("cpufreq", &enabled, sizeof(enabled)) || !enabled) {', steps)
        self.assertIn('return PE_parse_boot_argn("cpufreq", &on, sizeof(on)) && on != 0;', src)

    def test_cmdline_has_no_cpufreq_or_ddr(self):
        need(M / 'build.json', J / 'build.json')
        cmd = json.loads((M / 'build.json').read_text())['payload_fixes'][MN]['cmdline']
        j = json.loads((J / 'build.json').read_text())['payload_fixes'][JN]['cmdline']
        self.assertEqual(cmd, j.replace('fb_filter=0 ', 'fb_filter=0 cpuload=1000 ').replace('NAT158-scJ', 'NAT165-scM'))
        self.assertFalse([t for t in cmd.split() if t.split('=')[0] in ('cpufreq', 'ddr', 'ddr_vote', 'ddr_rest', 'membench')])
        self.assertEqual(len(cmd.encode()), 255)


class Gates(unittest.TestCase):
    def test_loader_sites_and_relocations(self):
        need(M / 'build.json')
        r = load('nat165_reloc_t', ROOT / 'docs/procedures/nat-157/relocscan.py').scan(M / MN)
        self.assertEqual([(x['object'], x['allowed']) for x in r], [('00-start.S.o', True)])
        chk = load('nat165_chk_t', ROOT / 'docs/procedures/nat-150/check_loader_sites.py')
        res, consts = chk.run(M, MN)
        self.assertEqual(res, dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(chk.symbolize(ROOT / 'artifacts/nat-165/kernel-001', consts),
                         chk.symbolize(ROOT / 'artifacts/nat-143/kernel-001', consts))


class Decoder(unittest.TestCase):
    def test_synthetic(self):
        L = load('nat165_load_t', HERE / 'load166.py')
        lines = []
        for k in range(30):                                    # 30 s of load lines, core 0 at 95%, cores 1.. read 100 (never ran)
            lines.append('tl: u at %d 0:95 1:100 2:100' % ((340 + k) * 1000000))
        for k in range(6):                                     # six 5 s framebuffer windows ending 345..370 s
            lines.append('[  %d.000000]: MiniIOMobileFramebuffer: 50 frames in 5000 ms (10 a second), 26000 us each in the driver, '
                         'after 0 us waiting for the GPU and, 0 of them, 0 us for the next refresh; 0 swaps waited for the frame '
                         'before, 0 gave up; 0 swaps came a refresh late themselves' % (345 + 5 * k))
        r = L.analyse('\n'.join(lines) + '\n')
        self.assertEqual(r['load_lines'], 30)
        self.assertEqual(r['verdict'], 'L2-saturated')
        self.assertEqual(r['steady_busy'][0]['median'], 95)
        self.assertEqual(r['graded_core'], 0)
        r2 = L.analyse('\n'.join(l.replace(' 0:95', ' 0:40') for l in lines) + '\n')
        self.assertEqual(r2['verdict'], 'L0-headroom')


class Session(unittest.TestCase):
    def test_counted_derivation(self):
        need(ROOT / 'artifacts/nat-165/package-001/package.json')
        text = load('nat165_derive_t', HERE / 'derive166.py').build()
        self.assertEqual((HERE / 'session_nat166.py').read_text(), text)
        img = json.loads((ROOT / 'artifacts/nat-165/package-001/package.json').read_text())['images'][MN]
        for s in (img['recovery_sha256'], img['payload_sha256'], "'NAT-165')", '*-nat166-%s-single-run-*.md'):
            self.assertIn(s, text)
        old = (ROOT / 'docs/procedures/nat-158/session_nat159.py').read_text().splitlines()
        self.assertEqual(sum(1 for l in difflib.unified_diff(old, text.splitlines(), lineterm='', n=0) if l[:1] == '+' and l[:3] != '+++'), 8)


if __name__ == '__main__':
    unittest.main()
