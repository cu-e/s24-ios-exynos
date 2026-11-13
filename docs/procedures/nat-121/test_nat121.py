#!/usr/bin/env python3
"""NAT-121 host tests.

  * e1s_touch.c as patched (source of the KRN-044 rebuild: artifacts/nat-121/kernel-001/src/bsd_e1s_touch.o/e1s_touch.c) is compiled on
    the host with host/shim.h + host/harness.c: ml_io_map hands out two fake 4 KiB pages, gpio_rd/gpio_wr are routed through a
    checker. Per e1stouch_steps: step 1 writes nothing; step 2 writes only the PERIC1 page (gpp9 CON/DAT/PUD at +0xe0..+0xe8) and
    never the ALIVE page and attaches no IRQ; step 3 attaches the IRQ. No access ever falls outside the mapped pages.
  * The same harness on the UNPATCHED source faults (NAT-066's defect reproduced as an out-of-page access).
  * redwood_input.c patch: a second devfs node 'hakios-touch' on the same cdevsw; libhakios.dylib in md0 names /dev/hakios-touch.
Run: python3 -B -I docs/procedures/nat-121/test_nat121.py
"""
import re, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K = ROOT / "artifacts/nat-121/kernel-001"
PATCHED = K / "src/bsd_e1s_touch.o/e1s_touch.c"
ORIG = ROOT / "worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_touch.c"
RI_PATCHED = K / "src/bsd_redwood_input.o/redwood_input.c"
LIB = ROOT / "artifacts/nat-110/pid1-sc2-hb/root/lib/libhakios.dylib"

MAIN = r'''
#include <stdlib.h>
int main(int argc, char **argv) {
	host_steps = atoi(argv[1]);
	e1s_touch_init();
	int changed_peric = 0;
	for (int i = 0; i < 4096; i++) changed_peric |= fake_page[0][i] != 0;
	printf("RESULT bad=%d writes_peric=%d writes_alive=%d irq=%d\n", host_bad, host_writes[0], host_writes[1], host_irq_attached);
	return 0;
}
'''


def host_source(text):
    # drop the kernel includes (the shim stands in) and route register access through the checker
    text = "\n".join(l for l in text.splitlines() if not l.startswith("#include"))
    text = text.replace("return *(volatile uint32_t *)reg;", "return host_rd(reg);")
    text = text.replace("*(volatile uint32_t *)reg = value;", "host_wr(reg, value);")
    text = text.replace("extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);", "vm_offset_t ml_io_map(vm_offset_t, vm_size_t);")
    pre = '#include "shim.h"\nuint32_t host_rd(uintptr_t a); void host_wr(uintptr_t a, uint32_t v);\n#define printf(...) printf(__VA_ARGS__)\n'
    return pre + text + MAIN


def run(src_path, steps):
    with tempfile.TemporaryDirectory() as w:
        w = Path(w)
        (w / "t.c").write_text(host_source(src_path.read_text()))
        exe = w / "t"
        r = subprocess.run(["cc", "-std=gnu11", "-w", "-I", str(HERE / "host"), str(w / "t.c"), str(HERE / "host/harness.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(r.stderr[-2000:])
        r = subprocess.run([str(exe), str(steps)], capture_output=True, text=True, timeout=60)
        m = re.search(r"RESULT bad=(\d+) writes_peric=(\d+) writes_alive=(\d+) irq=(\d+)", r.stdout)
        return dict(bad=int(m.group(1)), peric=int(m.group(2)), alive=int(m.group(3)), irq=int(m.group(4)), out=r.stdout)


@unittest.skipUnless(PATCHED.exists(), "kernel-001 absent")
class TouchTests(unittest.TestCase):
    def test_step1_writes_nothing(self):
        r = run(PATCHED, 1)
        self.assertEqual((r["bad"], r["peric"], r["alive"], r["irq"]), (0, 0, 0, 0))
        self.assertIn("e1s-touch: step 1: gpp9", r["out"])
        self.assertIn("stopped after step 1", r["out"])

    def test_step2_only_gpp9(self):
        r = run(PATCHED, 2)
        self.assertEqual((r["bad"], r["alive"], r["irq"]), (0, 0, 0))
        self.assertGreater(r["peric"], 0)
        self.assertIn("device id:", r["out"])
        self.assertIn("stopped after step 2", r["out"])

    def test_step3_irq(self):
        r = run(PATCHED, 3)
        self.assertEqual(r["bad"], 0)
        self.assertEqual(r["irq"], 1)
        self.assertGreater(r["alive"], 0)

    def test_unpatched_source_reaches_outside_the_map(self):
        if not ORIG.exists():
            self.skipTest("original source absent")
        r = run(ORIG, 3)
        self.assertGreater(r["bad"], 0)

    def test_only_gpp9_registers_written_in_step2(self):
        src = PATCHED.read_text()
        for name, off in (("CON", 0xe0), ("DAT", 0xe4), ("PUD", 0xe8), ("DRV", 0xec)):
            self.assertIn("#define E1S_GPP9_%s            (gpp9 + 0x%x)" % (name, off), src)


@unittest.skipUnless(RI_PATCHED.exists(), "kernel-001 absent")
class DeviceNodeTests(unittest.TestCase):
    def test_two_nodes_one_cdevsw(self):
        s = RI_PATCHED.read_text()
        self.assertEqual(len(re.findall(r'devfs_make_node\(makedev\(major, 0\)[^;]*"(redwood|hakios)-touch"\)', s)), 2)

    @unittest.skipUnless(LIB.exists(), "md0 root absent")
    def test_lib_reads_hakios_touch(self):
        b = LIB.read_bytes()
        self.assertIn(b"/dev/hakios-touch", b)
        self.assertNotIn(b"/dev/redwood-touch", b)




class AnalyserTests(unittest.TestCase):
    T120 = ROOT / "artifacts/nat-120/analysis/kernel-text.txt"
    P120 = ROOT / "artifacts/nat-120/analysis/pixels.json"

    def setUp(self):
        if not self.T120.exists() or not PATCHED.exists():
            self.skipTest("inputs absent")
        sys.path.insert(0, str(HERE))
        import analyze122
        self.A = analyze122
        self.t = self.T120.read_text(errors="replace")
        import json
        self.px = json.loads(self.P120.read_text())

    def ins(self, extra):
        i = self.t.index("--- loader_return_after expired ---")
        return self.t[:i] + extra + self.t[i:]

    def test_nat120_has_no_step1(self):
        self.assertEqual(self.A.classify(self.t, self.px)["touch"], "T0-no-step1")

    def test_harness_zero_id_is_no_response(self):
        self.assertEqual(self.A.classify(self.ins(run(PATCHED, 2)["out"]), self.px)["touch"], "T1-no-response")

    def test_ok_id(self):
        out = run(PATCHED, 2)["out"].replace("no response (rails off, pins wrong, or chip held in reset) (00 00 00 00 00)", "ok (20 01 a5 3c 07)")
        r = self.A.classify(self.ins(out), self.px)
        self.assertEqual(r["touch"], "T2-chip-answers")
        self.assertIn("20 01 a5 3c 07", r["reasons"][0])

    def test_touch_panic(self):
        r = self.A.classify(self.t + "\npanic(cpu 0 caller 0x0): Kernel data abort. at pc _e1s_touch_init+0x1\n", self.px)
        self.assertEqual(r["touch"], "T0-fault")

    def test_reader_open(self):
        r = self.A.classify(self.ins("[ 230.0]: redwood-touch: opened by pid 42 (minor 0)\n"), self.px)
        self.assertTrue(r["reader_opened"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
