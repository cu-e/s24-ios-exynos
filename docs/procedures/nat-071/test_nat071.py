#!/usr/bin/env python3
"""NAT-071 host tests: the kernel-side S5E9945 watchdog feed (0001-e1s-wdt-pet.patch on loader_return.c).

The e1s_wdt block is cut out of the patched source exactly as it is compiled into the kernel and built with the host
compiler against a harness that models the watchdog registers, the boot-args, mach_absolute_time and ml_io_map. Run:
    python3 -B -I docs/procedures/nat-071/test_nat071.py [--src PATCHED_loader_return.c]
"""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT/'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/osfmk/arm64/loader_return.c'
PATCH = HERE/'0001-e1s-wdt-pet.patch'
SRC_OVERRIDE = None
DAT83 = 65355          # WTDAT as guard.c's s5e_wdt_arm(&w, 83) computes it at 25.6 MHz

HARNESS = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define PAGE_SIZE 16384
#define NSEC_PER_SEC 1000000000ull
#define __builtin_arm_dsb(x) ((void)0)
typedef unsigned long vm_offset_t; typedef unsigned long vm_size_t;
static uint32_t regs[4096];
static int stuck, map_fails, mapped_pa_ok;
static uint64_t now_t;            /* mach_absolute_time, 1 tick = 1 ns here */
static const char *bootargs;
static char last_line[512];
static size_t used;
#define kprintf_capture(...) (used += (size_t)snprintf(last_line + used, used < sizeof last_line ? sizeof last_line - used : 0, __VA_ARGS__), used = used < sizeof last_line ? used : sizeof last_line - 1)
static vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t sz) { mapped_pa_ok = pa == 0x10040000ULL && sz >= 0x10; return map_fails ? 0 : (vm_offset_t)regs; }
static uint64_t mach_absolute_time(void) { return now_t; }
static void clock_interval_to_deadline(uint32_t n, uint64_t scale, uint64_t *d) { *d = now_t + (uint64_t)n * scale; }
static bool PE_parse_boot_argn(const char *name, void *out, int size) {
    const char *p = bootargs; size_t n = strlen(name); (void)size;
    while (p && *p) {
        while (*p == ' ') p++;
        if (!strncmp(p, name, n) && p[n] == '=') { *(uint32_t *)out = (uint32_t)strtoul(p + n + 1, 0, 0); return true; }
        while (*p && *p != ' ') p++;
    }
    return false;
}
#define printf kprintf_capture
#include "block.c"
#undef printf
int main(int argc, char **argv) {
    /* argv: boot-args, WTCON, WTDAT, map_fails, stuck, then feed times in seconds */
    bootargs = argv[1]; regs[0] = (uint32_t)strtoul(argv[2], 0, 0); regs[1] = (uint32_t)strtoul(argv[3], 0, 0);
    map_fails = atoi(argv[4]); stuck = atoi(argv[5]); regs[2] = 7; regs[3] = 0x55;
    uint32_t want = 0;
    PE_parse_boot_argn("loader_return_after", &want, 4);
    uint32_t got = e1s_wdt_window(want);
    for (char *c = last_line; *c; c++) if (*c == '\n' || *c == '"') *c = ' ';
    printf("{\"window\":%u,\"init\":{\"cnt\":%u,\"clr\":%u,\"pets\":%u,\"mapped\":%d,\"map_ok\":%d,\"line\":\"%s\"},\"ticks\":[",
        got, regs[2], regs[3], e1s_wdt_pets, e1s_wdt != 0, mapped_pa_ok, last_line);
    for (int i = 6; i < argc; i++) {
        regs[2] = 7; regs[3] = 0x55; now_t = strtoull(argv[i], 0, 0) * NSEC_PER_SEC;
        e1s_wdt_feed();
        printf("%s{\"t\":%s,\"cnt\":%u,\"clr\":%u,\"pets\":%u,\"stopped\":%d}", i > 6 ? "," : "", argv[i], regs[2], regs[3], e1s_wdt_pets, e1s_wdt_stopped);
    }
    printf("]}\n");
    return 0;
}
'''


def patched_source():
    if SRC_OVERRIDE:
        return Path(SRC_OVERRIDE).read_text()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)/'loader_return.c'
        p.write_bytes(ORIG.read_bytes())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(p), str(PATCH)], check=True)
        return p.read_text()


def cut_block(src):
    return src[src.index('#define E1S_WDT_PA'):src.index('/* end of e1s_wdt */')]


def build(d, block):
    (d/'block.c').write_text(block)
    (d/'h.c').write_text(HARNESS)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-o', str(d/'h'), str(d/'h.c')], check=True, cwd=d)
    return d/'h'


def run(exe, bootargs, con=0x21, dat=DAT83, map_fails=0, stuck=0, ticks=()):
    out = subprocess.run([str(exe), bootargs, hex(con), hex(dat), str(map_fails), str(stuck)] + [str(t) for t in ticks],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class Feed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.src = cut_block(patched_source())
        cls.exe = build(Path(cls.dir.name), cls.src)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def run_case(self, *a, **k):
        return run(self.exe, *a, **k)

    def assert_unfed(self, r, window):
        self.assertEqual(r['window'], window)
        self.assertFalse(r['init']['mapped'])
        self.assertTrue(all(t['cnt'] == 7 and t['pets'] == 0 for t in r['ticks']))

    def test_off_without_boot_arg_cuts_window(self):
        r = self.run_case('loader_return_after=150', ticks=(10, 20))
        self.assert_unfed(r, 63)
        self.assertIn('cut to 63', r['init']['line'])

    def test_off_keeps_short_window(self):
        self.assert_unfed(self.run_case('loader_return_after=63', ticks=(10,)), 63)
        self.assert_unfed(self.run_case('e1s_wdt_pet=0 loader_return_after=40', ticks=(10,)), 40)

    def test_refuses_disabled_watchdog(self):
        for con in (0x0, 0x01, 0x20):
            with self.subTest(con=con):
                r = self.run_case('e1s_wdt_pet=1 loader_return_after=150', con=con, ticks=(10,))
                self.assert_unfed(r, 63)

    def test_refuses_implausible_reload(self):
        for dat in (0, 63, 0x10000):
            with self.subTest(dat=dat):
                self.assert_unfed(self.run_case('e1s_wdt_pet=1 loader_return_after=150', dat=dat, ticks=(10,)), 63)

    def test_accepts_reload_range(self):
        for dat in (64, DAT83, 0xffff):
            with self.subTest(dat=dat):
                self.assertEqual(self.run_case('e1s_wdt_pet=1 loader_return_after=150', dat=dat)['window'], 150)

    def test_refuses_without_mapping(self):
        self.assert_unfed(self.run_case('e1s_wdt_pet=1 loader_return_after=150', map_fails=1, ticks=(10,)), 63)

    def test_maps_the_cl0_watchdog(self):
        r = self.run_case('e1s_wdt_pet=1 loader_return_after=150')
        self.assertTrue(r['init']['map_ok'])
        self.assertEqual(r['window'], 150)

    def test_feed_is_the_loaders_pet(self):
        """WTCLRINT := 0 and WTCNT := WTDAT, as s5e_wdt_pet() in the loader (s5e9945.c)."""
        r = self.run_case('e1s_wdt_pet=1 loader_return_after=150', ticks=(10, 20))
        self.assertEqual((r['init']['cnt'], r['init']['clr'], r['init']['pets']), (DAT83, 0, 1))
        for t in r['ticks']:
            self.assertEqual((t['cnt'], t['clr']), (DAT83, 0))
        self.assertEqual(r['ticks'][-1]['pets'], 3)

    def test_stops_after_window_plus_grace(self):
        """Fed until loader_return_after + 5 s, never after; stopping is final (time going back does not restart it)."""
        r = self.run_case('e1s_wdt_pet=1 loader_return_after=150', ticks=(150, 154, 155, 156, 160, 100))
        by = {t['t']: t for t in r['ticks']}
        self.assertEqual(by[154]['cnt'], DAT83)
        self.assertEqual((by[155]['cnt'], by[155]['stopped']), (7, 1))
        self.assertEqual(by[156]['cnt'], 7)
        self.assertEqual(by[160]['cnt'], 7)
        self.assertEqual(r['ticks'][-1]['cnt'], 7)
        self.assertEqual(r['ticks'][-1]['pets'], 3)

    def test_bound_holds_for_every_window(self):
        """For any window W the last feed is before W+5 s: with an 83.9 s watchdog the phone resets by W+89 s at the latest."""
        for w in (8, 63, 120, 150, 300):
            with self.subTest(w=w):
                r = self.run_case(f'e1s_wdt_pet=1 loader_return_after={w}', ticks=(w + 4, w + 5, w + 6))
                self.assertEqual(r['window'], w)
                self.assertEqual([t['cnt'] for t in r['ticks']], [DAT83, 7, 7])

    def test_stuck_counter_is_refused(self):
        """A WTCNT that does not take the reload: nothing is fed, the window is cut back to 63 s."""
        anchor = 'w[E1S_WDT_WTCNT] = dat;'
        self.assertEqual(self.src.count(anchor), 1)
        with tempfile.TemporaryDirectory() as d:
            exe = build(Path(d), self.src.replace(anchor, 'if (!stuck) ' + anchor))
            r = run(exe, 'e1s_wdt_pet=1 loader_return_after=150', stuck=1, ticks=(10,))
        self.assert_unfed(r, 63)
        self.assertIn('after reload', r['init']['line'])


if __name__ == '__main__':
    if '--src' in sys.argv:
        i = sys.argv.index('--src'); SRC_OVERRIDE = sys.argv[i+1]; del sys.argv[i:i+2]
    unittest.main(verbosity=1)
