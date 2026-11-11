#!/usr/bin/env python3
"""NAT-042 tests (host only):  python3 -I docs/procedures/nat-042/test_nat042.py
Needs: cc, zig, git, references/s24-linux at the pin. The runtime-DTB checks run only if devices/e1s-fdt/2026-11-10/runtime.dtb exists."""
import copy, json, os, re, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import verify_plan as V  # noqa: E402

PLAN = json.load(open(os.path.join(HERE, "plan.json")))
MOD = os.path.join(HERE, "module")


def run_check(plan):
    return V.check(plan, root=ROOT)


def failed_names(res):
    return {r["check"] for r in res if r["passed"] is False}


class PlanVsVendorSource(unittest.TestCase):
    def test_real_plan_passes_and_the_runtime_dtb_is_really_checked_when_present(self):
        ok, res = run_check(PLAN)
        self.assertTrue(ok, [r for r in res if r["passed"] is False])
        self.assertGreater(len(res), 90)
        dtb_present = os.path.exists(os.path.join(ROOT, PLAN["runtime_dtb"]["path"]))
        dtb_checks = [r for r in res if r["check"].startswith("dtb ")]
        if dtb_present:
            self.assertGreaterEqual(len(dtb_checks), 9)
            self.assertTrue(all(r["passed"] for r in dtb_checks))
        else:
            self.assertTrue(any(r["passed"] is None for r in res))

    def mutated(self, fn):
        p = copy.deepcopy(PLAN)
        fn(p)
        return run_check(p)

    def test_a_citation_on_the_wrong_line_fails(self):
        def f(p):
            for c in p["citations"]:
                if c["id"] == "R02": c["line"] += 1
        ok, res = self.mutated(f)
        self.assertFalse(ok); self.assertIn("citation R02", failed_names(res))

    def test_a_citation_with_other_text_fails(self):
        def f(p):
            for c in p["citations"]:
                if c["id"] == "S09": c["text"] = c["text"].replace("DOWNLOAD", "RECOVERY")
        ok, res = self.mutated(f)
        self.assertFalse(ok); self.assertIn("citation S09", failed_names(res))

    def test_a_plan_value_that_disagrees_with_the_source_fails(self):
        for key, bad in (("reboot", "0x400"), ("reboot_trigger", "0x1"), ("reason_download", "0x12345611"), ("inform2_normal", "0x4f"),
                         ("mode_fastboot", "0x5"), ("reboot_cmd", "0x810"), ("inform3", "0xb4"), ("mode_mask", "0x3"), ("inform2_byte_mask", "0xf")):
            def f(p, key=key, bad=bad): p["values"][key] = bad
            ok, res = self.mutated(f)
            self.assertFalse(ok, key); self.assertIn("value " + key, failed_names(res))

    def test_derived_values_follow_the_source_not_the_plan(self):
        # tamper with the citation text *and* the plan value consistently: the line check still catches it
        def f(p):
            p["values"]["reboot"] = "0x400"
            for c in p["citations"]:
                if c["id"] == "R02": c["text"] = "reboot-offset = <0x0400>;"
        ok, res = self.mutated(f)
        self.assertFalse(ok); self.assertIn("citation R02", failed_names(res))

    def test_unknown_pin_fails(self):
        def f(p): p["pin"]["sha"] = "0" * 40
        ok, res = self.mutated(f)
        self.assertFalse(ok); self.assertIn("pin-exists", failed_names(res))

    def test_absence_claims_are_checked(self):
        for i in range(len(PLAN["absence_claims"])):
            def f(p, i=i): p["absence_claims"][i]["expect_files"] = p["absence_claims"][i]["expect_files"] + ["drivers/not/there.c"]
            ok, res = self.mutated(f)
            self.assertFalse(ok); self.assertIn("absence " + PLAN["absence_claims"][i]["id"], failed_names(res))

    def test_a_sequence_step_may_not_cite_a_missing_citation(self):
        def f(p): p["vendor_sequence_download"][0]["cites"].append("ZZ99")
        ok, res = self.mutated(f)
        self.assertFalse(ok); self.assertIn("sequence-cites-exist ZZ99", failed_names(res))

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, PLAN["runtime_dtb"]["path"])), "runtime DTB not present")
    def test_runtime_dtb_values_are_compared(self):
        for node, key in (("/exynos-reboot", "reboot-offset"), ("/sec-reboot", "panic-inform"), ("/exynos-reboot", "reboot-cmd-offset")):
            def f(p, node=node, key=key): p["runtime_dtb"]["u32"][node][key] = "0x1234"
            ok, res = self.mutated(f)
            self.assertFalse(ok); self.assertIn("dtb %s %s" % (node, key), failed_names(res))

        def g(p): p["runtime_dtb"]["sha256"] = "0" * 64
        ok, res = self.mutated(g)
        self.assertFalse(ok); self.assertIn("runtime-dtb-hash", failed_names(res))


class ModuleVsPlan(unittest.TestCase):
    def header(self):
        d = {}
        for m in re.finditer(r"#define\s+(S5E_\w+)\s+(0x[0-9a-fA-F]+|[0-9]+)u?\b", open(os.path.join(MOD, "s5e9945_reset.h")).read()):
            d[m.group(1)] = int(m.group(2), 0)
        return d

    def test_header_constants_equal_the_values_derived_from_the_vendor_source(self):
        h = self.header(); v = {k: (int(x, 16) if isinstance(x, str) else x) for k, x in PLAN["values"].items()}
        pairs = {"S5E_PMU_BASE": "pmu_base", "S5E_PMU_INFORM2": "inform2", "S5E_PMU_INFORM3": "inform3", "S5E_PMU_REBOOT_CMD": "reboot_cmd",
                 "S5E_PMU_REBOOT": "reboot", "S5E_PMU_REBOOT_TRIGGER": "reboot_trigger", "S5E_REASON_NORMAL": "reason_normal",
                 "S5E_REASON_DOWNLOAD": "reason_download", "S5E_REASON_BOOTLOADER": "reason_bootloader", "S5E_INFORM2_BYTE_SHIFT": "inform2_byte_shift",
                 "S5E_INFORM2_BYTE_MASK": "inform2_byte_mask", "S5E_INFORM2_NORMAL": "inform2_normal", "S5E_MODE_MASK": "mode_mask",
                 "S5E_MODE_NORMAL": "mode_normal", "S5E_MODE_FASTBOOT": "mode_fastboot"}
        for hk, pk in pairs.items():
            self.assertIn(hk, h); self.assertEqual(h[hk], v[pk], hk)
        # and the plan's values are themselves re-derived from the pinned source by the verifier
        ok, res = run_check(PLAN)
        self.assertTrue(ok)
        derived = {r["check"][len("value "):] for r in res if r["check"].startswith("value ")}
        # every plan value is re-derived from a cited vendor line, except pmu_base, which the runtime-DTB reg check covers
        self.assertEqual(derived | {"pmu_base"}, set(PLAN["values"]))
        self.assertNotIn("pmu_base", derived)

    def test_the_recovery_reason_is_deliberately_not_a_header_constant(self):
        self.assertNotIn("0x12345604", open(os.path.join(MOD, "s5e9945_reset.h")).read().lower())


class HostAndTarget(unittest.TestCase):
    def test_host_model_test_passes(self):
        with tempfile.TemporaryDirectory() as t:
            exe = os.path.join(t, "t")
            cc = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", MOD, os.path.join(HERE, "test", "host_test.c"), "-o", exe], capture_output=True, text=True)
            self.assertEqual(cc.returncode, 0, cc.stderr)
            r = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("all checks passed", r.stdout)

    @unittest.skipUnless(shutil.which("zig"), "zig not installed")
    def test_aarch64_freestanding_build_is_clean_and_uses_only_dsb_and_wfi(self):
        base = ["zig", "cc", "-target", "aarch64-freestanding", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-O2", "-Wall", "-Wextra", "-Werror", "-I", MOD]
        src = os.path.join(MOD, "s5e9945_reset.c")
        with tempfile.TemporaryDirectory() as t:
            o = os.path.join(t, "r.o")
            r = subprocess.run(base + ["-c", src, "-o", o], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertGreater(os.path.getsize(o), 200)
            sfile = os.path.join(t, "r.s")
            # zig adds -c internally, so -Werror would flag it as an unused argument; the -c build above already ran with -Werror
            s = subprocess.run([a for a in base if a != "-Werror"] + ["-Wno-unused-command-line-argument", "-S", src, "-o", sfile], capture_output=True, text=True)
            self.assertEqual(s.returncode, 0, s.stderr)
            asm = open(sfile).read()
            self.assertRegex(asm, r"\bdsb\s+sy\b")
            self.assertRegex(asm, r"\bwfi\b")
            calls = set(re.findall(r"\b(?:bl|b)\s+([A-Za-z_][\w.]*)", asm))
            self.assertTrue(all(c.startswith("s5e_") or c.startswith(".L") or c.startswith("$") for c in calls), calls)
            self.assertNotRegex(asm, r"\b(mem(cpy|set|move)|__stack_chk)")


class Mutants(unittest.TestCase):
    def test_every_mutant_of_the_module_is_killed(self):
        with tempfile.TemporaryDirectory() as t:
            out = os.path.join(t, "m")
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "mutate_reset.py"), "--out", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout[-1500:])
            s = json.load(open(os.path.join(out, "summary.json")))
            self.assertEqual(s["total"], s["killed"])
            self.assertGreaterEqual(s["total"], 27)


if __name__ == "__main__":
    unittest.main(verbosity=2)
