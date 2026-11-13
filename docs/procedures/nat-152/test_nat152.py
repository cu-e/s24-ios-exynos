"""NAT-152 host tests: scH keeps every kernel address the loader checks (the loader's own check on the built payload, the NAT-151
failure reproduced on scG as the negative case), no kernel symbol moves outside the reset-vector page and the code after psci_smp,
the started-core start path on the unicorn model (capstone + unicorn: run with artifacts/nat-065/venv/bin/python; that class
skips otherwise), the small_cores=0 boot-arg in source, kernel and command line, and the image against scF."""
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
P150 = HERE.parent / 'nat-150'
sys.path.insert(0, str(P150))
import analyze150 as A  # noqa: E402

K143 = ROOT / 'artifacts/nat-143/kernel-001'
K152 = ROOT / 'artifacts/nat-152/kernel-001'
F = ROOT / 'artifacts/nat-148/build-001/loader-diag-xnu-scF-md1/payload.adt8.bin'
H = ROOT / 'artifacts/nat-152/build-001/loader-diag-xnu-scH-md1/payload.adt8.bin'
BUILD = ROOT / 'artifacts/nat-152/build-001/build.json'
BUILD150 = ROOT / 'artifacts/nat-150/build-001'
NAME = 'loader-diag-xnu-scH-md1'


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


def symbols(kdir):
    vi = load('nat152_vi_t', ROOT / 'fixtures/public/e1s-native-link-image/verify_image.py')
    u = glob.glob(str(kdir / 'link*/kernel/kernel.unstripped'))[0]
    return {l.split()[2]: int(l.split()[0], 16) for l in vi.tool('nm', u).splitlines() if len(l.split()) == 3}, u


class LoaderView(unittest.TestCase):
    """The gate NAT-151 lacked."""

    def test_loader_check_on_scH_payload(self):
        need(BUILD)
        chk = load('nat152_chk_t', P150 / 'check_loader_sites.py')
        res, consts = chk.run(BUILD.parent, NAME)
        self.assertEqual(res, dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(len(consts), 13)
        self.assertEqual(chk.symbolize(K152, consts), chk.symbolize(K143, consts))

    def test_nat151_failure_reproduced_on_scG(self):
        """Negative control: the same check on NAT-150's image gives the site error the loader hit on the phone."""
        need(BUILD150 / 'loader-diag-xnu-scG-md1')
        chk = load('nat152_chk_t2', P150 / 'check_loader_sites.py')
        res, _ = chk.run(BUILD150, 'loader-diag-xnu-scG-md1')
        self.assertEqual((res['rc'], res['verdict'], res['bad']), (2, 'NAT031_SITE_BAD', 1))

    def test_where_symbols_move(self):
        """Same segment layout. Code moves only in the reset-vector page (the trampolines) and from psci_smp.o's code after
        psci_smp_init; data only from psci_smp.o's own data on (the 2 KiB marks array); in __TEXT read-only constants and strings
        shift (psci_smp's changed strings). The loader holds none of these: its data addresses (other __DATA sections) stay."""
        need(K143, K152)
        vi = load('nat152_vi_t', ROOT / 'fixtures/public/e1s-native-link-image/verify_image.py')
        a, ua = symbols(K143)
        b, ub = symbols(K152)
        lay = lambda u: [(s['name'], s['vmaddr'], s['vmsize']) for s in vi.parse(Path(u).read_bytes())['segments']]
        self.assertEqual(lay(ua), lay(ub))
        seg = lambda v: next(n for n, base, size in lay(ua) if base <= v < base + size)
        page = a['_LowResetVectorBase']
        moved = {}
        for n in a:
            if n in b and a[n] != b[n] and not page <= a[n] < page + 0x1000:
                moved.setdefault(seg(a[n]), []).append(a[n])
        self.assertEqual(sorted(moved), ['__DATA', '__TEXT', '__TEXT_EXEC'])
        self.assertGreater(min(moved['__TEXT_EXEC']), a['_psci_smp_init'])
        self.assertEqual(min(moved['__DATA']), a['_psci_smp_start_fault'])
        for n in ('_loader_return_entered', '_invalid_ttep', '_loader_log', '_loader_recording', '_loader_stub_slot'):
            self.assertEqual(a[n], b[n], n)
        for n in ('_loader_jump', '_set_mmu_ttb', '_start_first_cpu', 'common_start', '_arm_init_cpu', '_loader_return_entered',
                  '_invalid_ttep', '_arm_vm_init', '_loader_log', '_loader_recording', '_loader_stub_slot'):
            self.assertEqual(a[n], b[n], n)
        self.assertEqual(b['__start'] & ~0xfff, b['_LowResetVectorBase'])
        self.assertEqual(b['_psci_smp_early_marks'] % 128, 0)
        self.assertNotIn('_psci_smp_early_marks', a)


class Kernel(unittest.TestCase):
    def test_unchanged_objects_identical_to_nat143(self):
        need(K143 / 'compile', K152 / 'compile')
        same = 0
        for f in (p for p in glob.glob(str(K152 / 'compile/**/*.o'), recursive=True) if Path(p).is_file()):
            rel = Path(f).relative_to(K152 / 'compile')
            if rel.parts[0].startswith('osfmk_'):
                continue
            a = Path(f).read_bytes().replace(b'artifacts/nat-152/kernel-001', b'artifacts/nat-143/kernel-001')
            self.assertEqual(a, (K143 / 'compile' / rel).read_bytes(), rel)
            same += 1
        self.assertEqual(same, 5)
        self.assertEqual(sorted(p.name for p in (K152 / 'compile').glob('osfmk_*')), ['osfmk_psci_smp.o', 'osfmk_start.o'])

    def test_build_check_kernel(self):
        need(K152 / 'rebuild.json', K143 / 'rebuild.json')
        b = load('nat152_build_t', HERE / 'build.py')
        r = b.check_kernel()
        self.assertEqual(sorted(e['object'] for e in r['extra_objects'] if e['object'] in b.PATCHES), sorted(b.PATCHES))

    def test_psci_smp_patch_is_nat150s(self):
        self.assertEqual((HERE / 'psci_smp.patch').read_bytes(), (P150 / 'psci_smp.patch').read_bytes())

    def test_start_patch_shape(self):
        """No line removed. The three branches the trampolines take over stay under #else; under GENERIC_PSCI_SMP each is one
        branch of the same kind (so the same size). Added code outside the macro is marks, their value loads, their skips, the
        trampoline branches and labels."""
        p = (HERE / 'start.patch').read_text().splitlines()
        self.assertFalse([l for l in p if l.startswith('-') and not l.startswith('---')])
        body = [' '.join(l[1:].split('//')[0].split()) for l in p if l[:1] in ' +' and not l.startswith('+++')]
        swaps = [(body[i + 1], body[i + 3]) for i in range(len(body) - 4)
                 if body[i] == '#if defined(GENERIC_PSCI_SMP)' and body[i + 2] == '#else' and body[i + 4] == '#endif']
        self.assertEqual(swaps, [('b Lpsci_smp_mark4', 'b common_start'), ('cbnz x21, Lpsci_smp_mark5', 'cbnz x21, 1f'),
                                 ('cbnz x21, Lpsci_smp_mark6', 'cbnz x21, 1f')])
        added = [l[1:] for l in p if l.startswith('+') and not l.startswith('+++')]
        text = '\n'.join(added)
        macro = text.split('.macro PSCI_SMP_EARLY_MARK stage, ra, rb\n')[1].split('.endm')[0]
        self.assertEqual(set(re.findall(r'\bx\d+\b', macro)), {'x9', 'x10'})
        outside = text.split('.macro PSCI_SMP_EARLY_MARK')[0] + text.split('.endm', 1)[1]
        branches = []
        for l in outside.splitlines():
            s = l.split('//')[0].strip()
            if not s or s.startswith(('#', '/*', '*', '3:')) or re.fullmatch(r'Lpsci_smp_\w+:', s):
                continue
            op = s.split()[0]
            self.assertIn(op, ('PSCI_SMP_EARLY_MARK', 'mrs', 'mov', 'cbz', 'b', 'cbnz'), l)
            if op in ('b', 'cbnz'):
                branches.append(s.split()[-1])
        self.assertEqual(sorted(branches), sorted(['Lpsci_smp_mark4', 'Lpsci_smp_mark5', 'Lpsci_smp_mark6', 'common_start',
                                                   'Lpsci_smp_mark5_back', 'Lpsci_smp_mark6_back']))
        self.assertEqual(sorted(re.findall(r'PSCI_SMP_EARLY_MARK (\d)', outside)), ['1', '2', '3', '4', '5', '6'])

    def test_return_labels_where_the_old_branches_landed(self):
        """The old `cbnz x21, 1f` lands on LOADER_CHECKPOINT's own last label, i.e. just after the macro: E1S_BOOT_MARK 4 and the
        SCTLR reload still run for a started core. The branches back must land there too."""
        s = (ROOT / 'artifacts/nat-152/src/start.s').read_text() if (ROOT / 'artifacts/nat-152/src/start.s').exists() else None
        if s is None:
            raise unittest.SkipTest('artifacts/nat-152/src/start.s missing')
        lines = [l.split('//')[0].strip() for l in s.splitlines()]
        for ck, back in (('LOADER_CHECKPOINT 4', 'Lpsci_smp_mark5_back:'), ('LOADER_CHECKPOINT 5', 'Lpsci_smp_mark6_back:')):
            i = lines.index(ck)
            self.assertEqual(lines[i + 1], back)

    def test_small_cores_boot_arg(self):
        """small_cores is read in ml_parse_cpu_topology() (redwood.patch: 0 = all cores alike, no small-core pairing); the
        kernel carries the name; the command line has it once."""
        src = (ROOT / 'references/s24-port/xnu/hackios/redwood.patch').read_text(errors='replace')
        self.assertIn('PE_parse_boot_argn("small_cores", &small_cores_apart', src)
        self.assertIn('ml_readprop(child, "small-core", 0) != 0 && small_cores_apart', src)
        need(K152 / 'kernel.no-storage')
        self.assertIn(b'\0small_cores\0', (K152 / 'kernel.no-storage').read_bytes())


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
        need(K143, K152)
        m = load('nat152_model_t', P150 / 'model_secondary.py')
        cls.m = m
        cls.res = {}
        for name, (mpidr, handler, entry) in dict(match=(0x81000400, 'start_cpu', '_LowResetVectorBase'),
                                                  resume=(0x81000400, 'resume_idle_cpu', '_LowResetVectorBase'),
                                                  none=(0x81000a00, 'start_cpu', '_LowResetVectorBase'),
                                                  null=(0x81000400, None, '_LowResetVectorBase'),
                                                  boot=(0x81000000, None, '__start')).items():
            old, new = m.run('nat143', mpidr, handler, entry_sym=entry), m.run('nat152', mpidr, handler, entry_sym=entry)
            cls.res[name] = (old, new, m.compare(old, new))

    def test_matching_core_same_path_plus_five_marks(self):
        old, new, c = self.res['match']
        self.assertTrue(c['ok'], c)
        self.assertEqual(c['mark_blocks'], 5)
        self.assertEqual(new['stop'], 'CPACR_EL1')
        k = new['k']
        self.assertEqual(new['regs']['lr'], k.sym['_arm_init_cpu'])
        mk = new['marks']
        self.assertEqual((mk[0], mk[1], mk[2]), (0x5EC00006, 0x81000400, 0x4))
        self.assertEqual(mk[4], self.m.CPUDATA_PA + 4 * 0x1000)
        self.assertEqual(mk[5], k.pa('_start_cpu'))
        self.assertEqual((mk[6], mk[7]), (0, 0))
        self.assertEqual(mk[8], k.sym['_arm_init_cpu'])
        self.assertEqual(mk[10], 0x8a0000000)
        self.assertEqual(mk[12], 0x3454593d)

    def test_resume_handler_same_path_plus_five_marks(self):
        old, new, c = self.res['resume']
        self.assertTrue(c['ok'], c)
        self.assertEqual((c['mark_blocks'], new['marks'][0]), (5, 0x5EC00006))

    def test_core_without_cpu_data_spins_with_mark_3(self):
        old, new, c = self.res['none']
        self.assertTrue(c['ok'], c)
        self.assertEqual((old['stop'], new['stop']), ('spin', 'spin'))
        self.assertEqual((new['marks'][0], new['marks'][6]), (0x5EC00003, 0xa00))

    def test_core_with_null_handler_spins_with_mark_3(self):
        old, new, c = self.res['null']
        self.assertTrue(c['ok'], c)
        self.assertEqual((new['marks'][0], new['marks'][6]), (0x5EC00003, 0))

    def test_boot_cpu_path_unchanged(self):
        """scH's boot processor executes exactly NAT-143's instructions (NAT-150 added two cbz)."""
        old, new, c = self.res['boot']
        self.assertTrue(c['ok'], c)
        self.assertEqual((c['mark_blocks'], c['inserted_instructions'], c['inserted_runs']), (0, 0, 0))
        self.assertEqual(len(old['insns']), len(new['insns']))
        self.assertEqual(new['marks'], [0] * 16)


class Analyser(unittest.TestCase):
    def test_printf_format_matches_parser(self):
        src = (HERE / 'psci_smp.patch').read_text()
        fmt = re.search(r'"(psci: cpu %d early marks: [^"]+)"\s*\n\+\s*"([^"]+)"', src)
        c = (fmt[1] + fmt[2]).replace('\\n', '')
        line = c.replace('%llx', '%x').replace('%lld', '%d') % ((3, 0x5ec00006, 0x81000300) + (1,) * 12 + (0,))
        mk = A.marks('[ 1.0]: ' + line)
        self.assertEqual((mk[3]['where'], mk[3]['affinity']), ('E6-mmu-on', 'on'))


class Image(unittest.TestCase):
    def test_payload_against_scF(self):
        need(F, H)
        ap = load('nat152_ap', ROOT / 'docs/procedures/nat-029/analyze_payload.py')
        f, h = ap.Payload(str(F)), ap.Payload(str(H))
        self.assertEqual(len(f.segs), len(h.segs))
        for i, (a, b) in enumerate(zip(f.segs[:-2], h.segs[:-2])):
            self.assertEqual((a[0], a[1]), (b[0], b[1]), i)                     # same VM layout up to __LINKEDIT
        k = (K152 / 'kernel.no-storage').read_bytes()
        self.assertEqual(h.b[h.segs[0][2]:h.segs[0][2] + 4096], k[:4096])
        self.assertEqual(f.b[f.segs[-1][2]:], h.b[h.segs[-1][2]:])                # md0 segment, ADT and everything after
        self.assertIn(b'NAT152-scH', h.b[:0x100])

    def test_build_record(self):
        need(BUILD)
        r = json.loads(BUILD.read_text())
        self.assertEqual(r['nat148_changes']['payload_cpu_states'], ['running'] + ['waiting'] * 9)
        cmd = r['payload_fixes'][NAME]['cmdline'].split()
        old = json.loads((ROOT / 'artifacts/nat-148/build-001/build.json').read_text())['payload_fixes']['loader-diag-xnu-scF-md1']
        self.assertEqual(sorted(set(cmd) - set(old['cmdline'].split())), ['nat_attempt=NAT152-scH', 'small_cores=0'])
        self.assertEqual(sorted(set(old['cmdline'].split()) - set(cmd)), ['nat_attempt=NAT148-scF'])
        c = r['nat152_changes']
        self.assertEqual(c['kernel'], json.loads((K152 / 'rebuild.json').read_text())['no_storage_sha256'])
        self.assertEqual(c['loader_sites_check']['rc'], 0)

    def test_session_derivation(self):
        p = subprocess.run([sys.executable, '-B', str(HERE / 'derive153.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == '__main__':
    unittest.main()
