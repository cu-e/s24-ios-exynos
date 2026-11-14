#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-191 host tests: the patched e1s_display.c (NAT-189's sampler with the self time read by recount_thread_time_mach(current_thread()); NAT-190 panicked on recount_current_thread_time_mach, whose interrupts-off assertion the harness now enforces) built against a simulated kernel
(host/shim191.h, host/fake191.c: backboardd threads whose run time grows by a fixed pattern of the tick number, saved pc/lr, a shared
region starting at 0x1a0000000, proc_find/proc_rele reference counting, optional restart, churn and thread-table overflow); the
printed windows, buckets and counts; the e1spc=0 switch; the patch relative to NAT-185's (no register access added); mutants; and
the analyser pc190.py on the harness output with a synthetic symbol table."""
import difflib
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_display.c'
PATCH = HERE / 'e1s_display.patch'
P185 = HERE.parent / 'nat-185/e1s_display.patch'
PC_THREAD = '1'         # thread order: e1s-top, e1s-pc


def patched(patch=PATCH):
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        t = Path(tmp) / 'e1s_display.c'
        t.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(t), str(patch)], check=True)
        return t.read_text()


def run(env=None, text=None):
    with tempfile.TemporaryDirectory(prefix='nat191-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        body = '\n'.join(l for l in (text or patched()).splitlines() if not l.startswith('#include'))
        src = tmp / 'd.c'
        src.write_text('#include "shim191.h"\nextern bool ml_cpu_idle_time(int cpu_id, uint64_t *idle);\n'
                       'extern uintptr_t ml_io_map(uintptr_t pa, uintptr_t size);\n' + body)
        exe = tmp / 'd'
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wno-unused-function', '-Wno-redundant-decls', '-Wno-attributes', '-Werror', '-I', str(HERE / 'host'),
                        str(src), str(HERE / 'host/fake191.c'), '-o', str(exe)], check=True)
        e = dict(os.environ, HOST_THREAD=PC_THREAD)
        e.update(env or {})
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120, env=e)
        assert r.returncode == 0, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
        return r.stdout


def _pc190():
    spec = importlib.util.spec_from_file_location('t191_pc190', HERE.parent / 'nat-189/pc190.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _dscsym():
    spec = importlib.util.spec_from_file_location('t191_dscsym', HERE.parent / 'nat-189/dscsym.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def synthetic_table():
    """unslid base 0x180000000; the harness's slid start is 0x1a0000000 (slide 0x20000000)"""
    b = 0x180000000
    images = [(b + 0x1000000, b + 0x1100000, '/System/Library/Frameworks/QuartzCore.framework/QuartzCore'),
              (b + 0x2000000, b + 0x2100000, '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics'),
              (b + 0x3000000, b + 0x3100000, '/usr/lib/system/libsystem_platform.dylib')]
    syms = {b + 0x1000000: '<redacted>', b + 0x1000030: '<redacted>', b + 0x2000000: '_CGBlendSomething',
            b + 0x3000000: '__platform_memmove'}
    return _dscsym().Table(dict(base=b, images=images, addrs=sorted(syms), names=[syms[a] for a in sorted(syms)]))


def heads(out):
    return {int(m[1]): dict(zip(('ticks', 'busy', 'samples', 'tlost', 'self', 'pid'), map(int, m.groups()[1:7])), start=m[8])
            for m in re.finditer(r'^e1s-pc: (\d+) window \d+-\d+ s ticks (\d+) busy (\d+) samples (\d+) tlost (\d+) self (\d+) us '
                                 r'pid (-?\d+) start (\S+)$', out, re.M)}


def buckets(out, end, kind):
    got = {}
    for m in re.finditer(r'^e1s-pc: %d %s((?: [ca][0-9a-f]+:\d+)+)$' % (end, kind), out, re.M):
        for e in m[1].split():
            k, n = e.split(':')
            got[k] = int(n)
    return got


class Sampler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run()

    def test_windows(self):
        h = heads(self.out)
        self.assertEqual(sorted(h), [220, 265, 310, 375])
        self.assertIn('e1s-pc: done', self.out)
        self.assertIn('e1s-pc: backboardd[40] shared cache start 0x1a0000000', self.out)
        for end, span in ((220, 20), (265, 45), (310, 45), (375, 65)):
            self.assertAlmostEqual(h[end]['ticks'], span * 1000, delta=2, msg=end)
            # A 6/10 + B 3/10 + D 1/50 of the ticks; the very first tick has no baseline
            self.assertAlmostEqual(h[end]['samples'], span * 1000 * 0.92, delta=3, msg=end)
            self.assertEqual(h[end]['samples'], h[end]['busy'])
            self.assertEqual((h[end]['tlost'], h[end]['pid'], h[end]['start']), (0, 40, '0x1a0000000'))
            self.assertAlmostEqual(h[end]['self'], span * 1000 * 5, delta=20)
        self.assertRegex(self.out, r'RESULT end at \d+ s refs 0 ')
        self.assertNotIn('BAD', self.out)

    def test_buckets(self):
        f, g, l = (buckets(self.out, 265, k) for k in 'fgl')
        self.assertEqual(set(f), {'c1000040', 'c3000080', 'a100004000'})
        self.assertAlmostEqual(f['c1000040'], 27000, delta=2)
        self.assertAlmostEqual(f['c3000080'], 13500, delta=2)
        self.assertAlmostEqual(f['a100004000'], 900, delta=2)
        self.assertEqual(set(g), {'c1000000', 'c3000000', 'a100000000'})
        self.assertEqual(l, {'c2000000': f['c1000040'] + f['c3000080'], 'a100004100': f['a100004000']})
        self.assertIn('e1s-pc: 265 f shown %d lost 0' % sum(f.values()), self.out)
        self.assertEqual(list(f), ['c1000040', 'c3000080', 'a100004000'])      # busiest first

    def test_restart(self):
        out = run({'HOST_RESTART_S': '280'})
        h = heads(out)
        self.assertEqual((h[265]['pid'], h[310]['pid'], h[375]['pid']), (40, 41, 41))
        self.assertIn('e1s-pc: backboardd[41] shared cache start 0x1a0000000', out)
        self.assertLess(h[310]['ticks'], 45000 - 400)                               # no ticks while it is gone
        self.assertRegex(out, r'refs 0 ')

    def test_churn_and_overflow(self):
        h = heads(run({'HOST_CHURN': '1'}))
        self.assertEqual(h[265]['tlost'], 0)                 # new threads reuse the slots of the gone ones
        self.assertAlmostEqual(h[265]['samples'], 45000 * 0.92, delta=3)
        h = heads(run({'HOST_BBD_THREADS': '120'}))
        self.assertGreater(h[265]['tlost'], 0)
        self.assertEqual(sorted(h), [220, 265, 310, 375])

    def test_no_shared_region(self):
        out = run({'HOST_NO_SR': '1'})
        self.assertEqual(heads(out)[265]['start'], '0')
        self.assertIn('a1a1000040', buckets(out, 265, 'f'))

    def test_no_memory(self):
        out = run({'HOST_NO_ALLOC': '1'})
        self.assertIn('e1s-pc: cannot allocate', out)
        self.assertEqual(heads(out), {})
        self.assertIn('e1s-pc: done', out)
        self.assertNotIn('BAD', out)

    def test_off_and_others_unchanged(self):
        out = run({'BOOTARG_e1spc': '0', 'HOST_THREAD': '9'})
        self.assertNotIn('e1s-pc', out)
        self.assertIn('threads 1', out)
        self.assertIn('threads 2', run({'HOST_THREAD': '9'}))
        out = run({'HOST_THREAD': '0'})
        self.assertIn('e1s-top: 205 s span', out)
        self.assertNotIn('e1s-pc: 220', out)
        self.assertNotIn('e1s-dpp', out)                   # NAT-176's snapshot is left out (no room, see the patch)
        self.assertNotIn('map 0x1', out)                   # and with it every register map but the framebuffer probe's

    def test_mutants(self):
        text = patched()
        for o, n in (('if (fresh || now <= before) {', 'if (fresh || before == ~0ULL) {'),
                     ('e1s_pc_add(&e1s_pc->fine, pc >> 6);', 'e1s_pc_add(&e1s_pc->fine, lr >> 6);'),
                     ('addr - e1s_pc_start < E1S_PC_CACHE_SIZE', 'addr - e1s_pc_start > E1S_PC_CACHE_SIZE'),
                     ('(e->gen == 0 || e->gen + 1U < e1s_pc_gen)', '(e->gen == 0)'),
                     ('t->count[i] > t->count[best]', 't->count[i] < t->count[best]'),
                     ('\tproc_rele(p);\n\treturn true;', '\treturn true;'),
                     ('strncmp(proc_best_name(p), "backboardd", 11)', 'strncmp(proc_best_name(p), "SpringBoard", 12)')):
            self.assertEqual(text.count(o), 1, o)
            env = {'HOST_CHURN': '1'} if 'gen + 1U' in o else {}
            out = run(env, text=text.replace(o, n))
            ok = True
            try:
                h, f = heads(out), buckets(out, 265, 'f')
                ok = abs(h[265]['samples'] - 45000 * 0.92) < 4 and h[265]['tlost'] == 0 and list(f) == ['c1000040', 'c3000080', 'a100004000'] \
                    and 'refs 0 ' in out
            except KeyError:
                ok = False
            self.assertFalse(ok, n)


class Nat190Regression(unittest.TestCase):
    def test_189_patch_panics_in_this_harness(self):
        # NAT-190 on the phone: the first window tick of NAT-189's sampler hit recount.c:567; this harness must reproduce it
        with self.assertRaises(AssertionError) as c:
            run(text=patched(HERE.parent / 'nat-189/e1s_display.patch'))
        self.assertIn('PANIC recount_current_thread_time_mach', str(c.exception))

    def test_only_self_time_changed_against_189(self):
        a, b = patched(HERE.parent / 'nat-189/e1s_display.patch').splitlines(), patched().splitlines()
        diff = [l for l in difflib.ndiff(a, b) if l[:2] in ('- ', '+ ')]
        code = [l for l in diff if not l[2:].lstrip().startswith(('*', '/*'))]
        self.assertEqual(sorted(set(l[:2] for l in code)), ['+ ', '- '])
        self.assertTrue(all('recount_current_thread_time_mach()' in l for l in code if l.startswith('- ')), code)
        self.assertTrue(all('recount_thread_time_mach(current_thread())' in l for l in code if l.startswith('+ ')), code)
        self.assertNotIn('recount_current', '\n'.join(l for l in b if not l.lstrip().startswith('*')))


class PatchScope(unittest.TestCase):
    def test_extends_185_without_register_access(self):
        old = patched(P185)
        a, b = old.splitlines(), patched().splitlines()
        diff = list(difflib.ndiff(a, b))
        # only NAT-176's display-layer snapshot (its block and its three probe lines) goes; NAT-185's e1s-top stays
        block = old[old.index('/*\n * NAT-176: a read-only snapshot'):old.index('/*\n * NAT-185: where the only running core')]
        removed = [l[2:] for l in diff if l.startswith('- ')]
        self.assertTrue(removed)
        self.assertFalse([l for l in removed if l not in block.splitlines() and 'dpp' not in l.lower()
                          and l not in ('\t\treturn;', '\t}', '\t\tthread_deallocate(thread);')], removed)
        self.assertFalse([l for l in removed if 'e1s_top' in l or 'E1S_TOP' in l])
        self.assertEqual(sorted(set(l[2:] for l in diff if l.startswith('+ ') and 'minsize' in l and not l[2:].lstrip().startswith('*'))), ['__attribute__((minsize))'])
        added = [l[2:] for l in diff if l.startswith('+ ') and not l[2:].lstrip().startswith(('/*', '*'))]
        self.assertFalse([l for l in added if 'ml_io_map' in l or 'volatile' in l or 'e1s_display_read' in l or 'copyin' in l
                          or 'copyout' in l])
        self.assertFalse([l for l in added if re.search(r'\b(set_saved_state|thread_set_state|task_suspend|thread_suspend)', l)])


class Analyser(unittest.TestCase):
    def test_on_harness(self):
        a = _pc190()
        r = a.analyse(run(), synthetic_table())
        self.assertEqual(r['verdict'], 'P-ok')
        self.assertEqual(r['swipe_leader'], 'ca')
        self.assertAlmostEqual(r['swipe_groups']['ca'], 0.6 / 0.92, delta=0.001)
        self.assertAlmostEqual(r['swipe_groups']['copy'], 0.3 / 0.92, delta=0.001)
        self.assertAlmostEqual(r['swipe_groups']['outside'], 0.02 / 0.92, delta=0.001)
        self.assertEqual(r['swipe_coarse_coverage'], 1.0)
        w = [w for w in r['windows'] if w['end'] == 265][0]
        self.assertEqual(w['slide'], 0x20000000)
        self.assertEqual(w['f']['functions'][0]['name'], 'QuartzCore:sub_181000030')
        self.assertEqual(w['f']['functions'][1]['name'], '__platform_memmove')
        self.assertEqual(w['l']['functions'][0]['name'], '_CGBlendSomething')
        self.assertAlmostEqual(w['sampler_share'], 0.005, delta=0.0001)
        self.assertEqual(r['last_leader'], 'ca')

    def test_unsymbolised_and_verdicts(self):
        a = _pc190()
        r = a.analyse(run())
        self.assertEqual(r['verdict'], 'P-ok')
        self.assertFalse(r['symbolised'])
        self.assertEqual(a.analyse('')['verdict'], 'P-none')
        head = 'e1s-pc: %d window %d-%d s ticks 45000 busy %d samples %d tlost 0 self 1 us pid 16 start 0x1a0000000\n'
        thin = head % (265, 220, 265, 999, 999) + head % (310, 265, 310, 1000, 1000)
        self.assertEqual(a.analyse(thin)['verdict'], 'P-thin')
        self.assertEqual(a.analyse(head % (265, 220, 265, 1000, 1000) + head % (310, 265, 310, 1000, 1000))['verdict'], 'P-ok')
        self.assertEqual(a.analyse(head % (220, 200, 220, 9000, 9000))['verdict'], 'P-thin')     # outside the swipe windows


if __name__ == '__main__':
    unittest.main()
