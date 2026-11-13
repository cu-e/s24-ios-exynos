"""NAT-150 host tests: the kernel's three changed objects, the secondary-core start path on the unicorn model (needs capstone and
unicorn: run with artifacts/nat-065/venv/bin/python; that class skips otherwise), the corrected SMP rule and the early-mark parser on
NAT-149's real text, and the scG image against scF."""
import glob
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import analyze150 as A  # noqa: E402

K143 = ROOT / 'artifacts/nat-143/kernel-001'
K150 = ROOT / 'artifacts/nat-150/kernel-001'
F = ROOT / 'artifacts/nat-148/build-001/loader-diag-xnu-scF-md1/payload.adt8.bin'
G = ROOT / 'artifacts/nat-150/build-001/loader-diag-xnu-scG-md1/payload.adt8.bin'
BUILD = ROOT / 'artifacts/nat-150/build-001/build.json'
T149 = ROOT / 'artifacts/nat-149/analysis/kernel-text.txt'
P149 = ROOT / 'artifacts/nat-149/analysis/pixels.json'
T144 = ROOT / 'artifacts/nat-144/analysis/kernel-text.txt'
P144 = ROOT / 'artifacts/nat-144/analysis/pixels.json'


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
    def test_unchanged_objects_identical_to_nat143(self):
        """loader_return.o and NAT-143's four objects: byte-identical after the build-directory path is normalized."""
        need(K143 / 'compile', K150 / 'compile')
        same = 0
        for f in (p for p in glob.glob(str(K150 / 'compile/**/*.o'), recursive=True) if Path(p).is_file()):
            rel = Path(f).relative_to(K150 / 'compile')
            if rel.parts[0].startswith('osfmk_'):
                continue
            a = Path(f).read_bytes().replace(b'artifacts/nat-150/kernel-001', b'artifacts/nat-143/kernel-001')
            self.assertEqual(a, (K143 / 'compile' / rel).read_bytes(), rel)
            same += 1
        self.assertEqual(same, 5)

    def test_build_check_kernel(self):
        need(K150 / 'rebuild.json', K143 / 'rebuild.json')
        b = load('nat150_build_t', HERE / 'build.py')
        r = b.check_kernel()
        self.assertEqual(sorted(e['object'] for e in r['extra_objects'] if e['object'] in b.PATCHES), sorted(b.PATCHES))

    def test_start_patch_adds_only_marks(self):
        """start.patch removes no line, and outside the macro every added instruction is a mark, its two value loads or its skip."""
        p = (HERE / 'start.patch').read_text().splitlines()
        self.assertFalse([l for l in p if l.startswith('-') and not l.startswith('---')])
        added = [l[1:] for l in p if l.startswith('+') and not l.startswith('+++')]
        text = '\n'.join(added)
        macro = text.split('.macro PSCI_SMP_EARLY_MARK stage, ra, rb\n')[1].split('.endm')[0]
        regs = set(re.findall(r'\bx\d+\b', macro))
        self.assertEqual(regs, {'x9', 'x10'})
        self.assertNotIn('sp', re.findall(r'\b\w+\b', macro))
        outside = text.split('.macro PSCI_SMP_EARLY_MARK')[0] + text.split('.endm', 1)[1]
        for l in outside.splitlines():
            s = l.split('//')[0].strip()
            if not s or s.startswith(('#', '/*', '*', '3:')):
                continue
            op = s.split()[0]
            self.assertIn(op, ('PSCI_SMP_EARLY_MARK', 'mrs', 'mov', 'cbz'), l)
        self.assertEqual(re.findall(r'PSCI_SMP_EARLY_MARK (\d)', outside), ['1', '2', '3', '4', '5', '6'])

    def test_symbols(self):
        need(K150)
        vi = load('nat150_vi_t', ROOT / 'fixtures/public/e1s-native-link-image/verify_image.py')
        u = glob.glob(str(K150 / 'link*/kernel/kernel.unstripped'))[0]
        sym = {l.split()[2]: int(l.split()[0], 16) for l in vi.tool('nm', u).splitlines() if len(l.split()) == 3}
        self.assertEqual(sym['__start'] & ~0xfff, sym['_LowResetVectorBase'])        # iBoot's rule: reset vector = __start & ~0xfff
        self.assertEqual(sym['_psci_smp_early_marks'] % 128, 0)
        seg = {s['name']: s for s in vi.parse(Path(u).read_bytes())['segments']}['__DATA']
        self.assertTrue(seg['vmaddr'] <= sym['_psci_smp_early_marks'] < seg['vmaddr'] + seg['vmsize'])


try:
    import capstone  # noqa: F401
    import unicorn  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, 'capstone/unicorn not available (use artifacts/nat-065/venv/bin/python)')
class Model(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        need(K143, K150)
        m = load('nat150_model_t', HERE / 'model_secondary.py')
        cls.m = m
        cls.res = {}
        for name, (mpidr, handler, entry) in dict(match=(0x81000400, 'start_cpu', '_LowResetVectorBase'),
                                                  none=(0x81000a00, 'start_cpu', '_LowResetVectorBase'),
                                                  null=(0x81000400, None, '_LowResetVectorBase'),
                                                  boot=(0x81000000, None, '__start')).items():
            old, new = m.run('nat143', mpidr, handler, entry_sym=entry), m.run('nat150', mpidr, handler, entry_sym=entry)
            cls.res[name] = (old, new, m.compare(old, new))

    def test_matching_core_same_path_plus_five_marks(self):
        old, new, c = self.res['match']
        self.assertTrue(c['ok'], c)
        self.assertEqual(c['mark_blocks'], 5)
        self.assertEqual(new['stop'], 'CPACR_EL1')
        k = new['k']
        self.assertEqual(new['regs']['lr'], k.sym['_arm_init_cpu'])
        mk = new['marks']
        self.assertEqual(mk[0], 0x5EC00006)
        self.assertEqual(mk[1], 0x81000400)
        self.assertEqual(mk[2], 0x4)                                              # 1: CurrentEL = EL1
        self.assertEqual(mk[4], self.m.CPUDATA_PA + 4 * 0x1000)                  # 2: its cpu data
        self.assertEqual(mk[5], k.pa('_start_cpu'))                              # ... and handler
        self.assertEqual((mk[6], mk[7]), (0, 0))                                 # 3: not written
        self.assertEqual(mk[8], k.sym['_arm_init_cpu'])                          # 4: lr (KVA)
        self.assertEqual(mk[10], 0x8a0000000)                                    # 5: TTBR1 = cpu_ttep
        self.assertEqual(mk[12], 0x3454593d)                                     # 6: SCTLR as switched on

    def test_core_without_cpu_data_spins_with_mark_3(self):
        old, new, c = self.res['none']
        self.assertTrue(c['ok'], c)
        self.assertEqual((old['stop'], new['stop']), ('spin', 'spin'))
        self.assertEqual(new['marks'][0], 0x5EC00003)
        self.assertEqual(new['marks'][6], 0xa00)

    def test_core_with_null_handler_spins_with_mark_3(self):
        old, new, c = self.res['null']
        self.assertTrue(c['ok'], c)
        self.assertEqual(new['marks'][0], 0x5EC00003)
        self.assertEqual(new['marks'][6], 0)

    def test_boot_cpu_path_two_cbz_no_marks(self):
        old, new, c = self.res['boot']
        self.assertTrue(c['ok'], c)
        self.assertEqual((c['mark_blocks'], c['inserted_instructions']), (0, 2))
        self.assertEqual(new['marks'], [0] * 16)


class Analyser(unittest.TestCase):
    def test_nat149_real_text(self):
        need(T149, P149)
        r = A.classify(T149.read_text(errors='replace'), json.loads(P149.read_text()))
        self.assertEqual((r['smp'], r['smp_rule146']), ('C0-one', 'C1-some'))
        self.assertEqual(r['cpus']['running'], 1)
        self.assertEqual(r['cpus']['joined'], [])
        self.assertEqual(r['cpus']['not_joined'], list(range(1, 10)))
        self.assertEqual(r['early_marks'], {})

    def test_nat144_baseline(self):
        need(T144, P144)
        r = A.classify(T144.read_text(errors='replace'), json.loads(P144.read_text()))
        self.assertEqual(r['smp'], 'C0-one')
        self.assertEqual(r['fps_steady_windows'], 8)

    def test_marks_and_c1(self):
        need(T149, P149)
        base = T149.read_text(errors='replace')
        line = ('[  100.0]: psci: cpu %d early marks: last %s mpidr 0x81000%d00 1:0x4,0x30d00804 2:0x0,0x0 3:0x0,0x0 4:0x0,0x0 '
                '5:0x0,0x0 6:0x0,0x0 affinity_info %d\n')
        text = base + line % (4, '0x5ec00001', 4, 0) + line % (5, '0x0', 5, 1) + line % (6, '0x5ec00005', 6, 0)
        text = text + '[ 200.0]: GenericARMPE: 3 of 10 processors are running\n'
        r = A.classify(text, json.loads(P149.read_text()))
        self.assertEqual(r['early_where'], {'E1-entry': [4], 'E0-no-entry': [5], 'E5-before-mmu': [6]})
        self.assertEqual(r['early_marks'][5]['affinity'], 'off')
        self.assertEqual(r['early_marks'][4]['stages'], {1: ['0x4', '0x30d00804']})
        self.assertEqual(r['smp'], 'C1-some')

    def test_printf_format_matches_parser(self):
        src = (HERE / 'psci_smp.patch').read_text()
        fmt = re.search(r'"(psci: cpu %d early marks: [^"]+)"\s*\n\+\s*"([^"]+)"', src)
        c = (fmt[1] + fmt[2]).replace('\\n', '')
        line = c.replace('%llx', '%x').replace('%lld', '%d') % ((7, 0x5ec00002, 0x81000700) + (1,) * 12 + (2,))
        mk = A.marks('[ 1.0]: ' + line)
        self.assertIn(7, mk)
        self.assertEqual((mk[7]['where'], mk[7]['affinity']), ('E2-cpu-data-found', 'on pending'))


class Image(unittest.TestCase):
    def test_payload_differs_from_scF_only_in_kernel_and_tag(self):
        need(F, G)
        ap = load('nat150_ap', ROOT / 'docs/procedures/nat-029/analyze_payload.py')
        f, g = ap.Payload(str(F)), ap.Payload(str(G))
        self.assertEqual(len(f.segs), len(g.segs))
        for i, (a, b) in enumerate(zip(f.segs, g.segs)):
            self.assertEqual((a[0], a[1]), (b[0], b[1]), i)                     # same VM layout
        k150 = (K150 / 'kernel.no-storage').read_bytes()
        self.assertEqual(g.b[g.segs[0][2]:g.segs[0][2] + 4096], k150[:4096])
        tail = f.segs[-1][2]
        self.assertEqual(f.b[tail:], g.b[g.segs[-1][2]:])                         # md0 segment, ADT and everything after: same bytes
        head = [i for i in range(f.segs[0][2]) if f.b[i] != g.b[i]]
        self.assertTrue(head)
        self.assertIn(b'NAT150-scG', g.b[:0x100])
        self.assertIn(b'NAT148-scF', f.b[:0x100])

    def test_build_record(self):
        need(BUILD)
        r = json.loads(BUILD.read_text())
        self.assertEqual(r['nat148_changes']['payload_cpu_states'], ['running'] + ['waiting'] * 9)
        cmd = r['payload_fixes']['loader-diag-xnu-scG-md1']['cmdline'].split()
        self.assertEqual(cmd.count('nat_attempt=NAT150-scG'), 1)
        self.assertFalse(any(t.startswith('cpus=') for t in cmd))
        self.assertEqual(r['nat150_changes']['kernel'], json.loads((K150 / 'rebuild.json').read_text())['no_storage_sha256'])

    def test_session_derivation(self):
        p = subprocess.run([sys.executable, '-B', str(HERE / 'derive151.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == '__main__':
    unittest.main()
