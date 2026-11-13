#!/usr/bin/env python3
"""NAT-129 host checks of the scA image.

1. e1s_input_init() from the kernel's own e1s_input.c is compiled on the host with counting stubs and executed: with e1skeys=0
   it must return without starting a thread, mapping the ALIVE GPIO block or asking the PMIC anything; the same code without
   the token (and with e1skeys=1) is the control that does start the thread.
2. The linked scA kernel (NAT-128's kernel.no-storage) carries that code path's string, and the built image's command line
   has e1spmic=2 and e1skeys=0 once each, no e1spmic=0, within 255 bytes.

Host-test only: this says nothing about the phone's PMIC, rails or touch controller.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_input.c'
KERNEL = ROOT / 'artifacts/nat-128/kernel-001/kernel.no-storage'
BUILD = ROOT / 'artifacts/nat-129/build-001/build.json'
NAME = 'loader-diag-xnu-scA-md1'

STUBS = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <stdlib.h>
#define E1S 1
#define __unused __attribute__((unused))
typedef int kern_return_t; typedef void *thread_t; typedef int wait_result_t; typedef uintptr_t vm_offset_t; typedef size_t vm_size_t;
#define KERN_SUCCESS 0
#define NSEC_PER_MSEC 1000000ULL
#define REDWOOD_BUTTON_DOWN 1
#define REDWOOD_BUTTON_UP 2
#define REDWOOD_BUTTON_VOLUME_UP 3
#define REDWOOD_BUTTON_LOCK 4
static int n_threads, n_pmic, n_io, n_post;
static const char *arg_name; static uint32_t arg_val; static int arg_set;
int PE_parse_boot_argn(const char *n, void *v, int s) { if (arg_set && !strcmp(n, arg_name)) { memcpy(v, &arg_val, s < 4 ? s : 4); return 1; } return 0; }
static kern_return_t kernel_thread_start(void (*f)(void *, wait_result_t), void *a, thread_t *t) { (void)f; (void)a; *t = 0; n_threads++; return 0; }
static void thread_deallocate(thread_t t) { (void)t; }
static thread_t current_thread(void) { return 0; }
kern_return_t thread_terminate(thread_t t) { (void)t; exit(3); }
vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t size) { (void)pa; (void)size; n_io++; return 0; }
bool e1s_pmic_ready(void) { n_pmic++; return false; }
bool e1s_pmic_power_key(void) { n_pmic++; return false; }
void redwood_touch_post(int a, int b, int c, int d) { (void)a; (void)b; (void)c; (void)d; n_post++; }
static void delay_for_interval(uint64_t a, uint64_t b) { (void)a; (void)b; }
'''

MAIN = r'''
int main(int argc, char **argv) {
    if (argc > 2) { arg_set = 1; arg_name = argv[1]; arg_val = (uint32_t)strtoul(argv[2], 0, 0); }
    e1s_input_init();
    printf("RESULT threads=%d pmic=%d io=%d post=%d\n", n_threads, n_pmic, n_io, n_post);
    return 0;
}
'''


def build_exe(tmp):
    text = '\n'.join(l for l in SRC.read_text().splitlines() if not l.startswith('#include') and not l.startswith('extern '))
    c = tmp / 'input.c'
    c.write_text(STUBS + text + MAIN)
    exe = tmp / 'input'
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wno-unused-function', '-Wno-unused-variable', str(c), '-o', str(exe)], check=True)
    return exe


class KeysDisabledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='nat129-', dir=os.environ.get('TMPDIR'))
        cls.exe = build_exe(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_init(self, *args):
        return subprocess.run([str(self.exe), *args], check=True, capture_output=True, text=True, timeout=10).stdout

    def test_e1skeys_0_starts_nothing_and_asks_the_pmic_nothing(self):
        out = self.run_init('e1skeys', '0')
        self.assertIn('e1s-keys: disabled (e1skeys=0)', out)
        self.assertIn('RESULT threads=0 pmic=0 io=0 post=0', out)

    def test_control_without_the_token_starts_the_thread(self):
        for args in ((), ('e1skeys', '1')):
            with self.subTest(args=args):
                out = self.run_init(*args)
                self.assertIn('RESULT threads=1', out)
                self.assertNotIn('disabled', out)

    def test_another_token_does_not_disable(self):
        self.assertIn('RESULT threads=1', self.run_init('e1skeyz', '0'))


class ImageTests(unittest.TestCase):
    def test_kernel_carries_the_disabled_path(self):
        if not KERNEL.exists():
            self.skipTest('kernel artifact missing')
        self.assertIn(b'e1s-keys: disabled (e1skeys=0)', KERNEL.read_bytes())

    def test_cmdline(self):
        if not BUILD.exists():
            self.skipTest('build artifact missing')
        b = json.loads(BUILD.read_text())
        cmd = b['payload_fixes'][NAME]['cmdline']
        t = cmd.split()
        self.assertEqual((t.count('e1spmic=2'), t.count('e1skeys=0'), t.count('e1sufs=0')), (1, 1, 1))
        self.assertNotIn('e1spmic=0', t)
        self.assertNotIn('e1sufs_probe=0', t)
        self.assertLessEqual(len(cmd.encode()), 255)
        self.assertEqual(b['nat129_changes']['kernel'], 'd6d56001d32aadda5059ab0a2255b313d7ca2055da88d645d1610214bf284517')


if __name__ == '__main__':
    unittest.main(verbosity=2)
