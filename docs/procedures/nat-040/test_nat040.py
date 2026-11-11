#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-040 host tests: the verifier of the S5E9945 USB2 device-mode bring-up plan (verify_plan.py).
Evidence kind: host-test of a source-review tool. Nothing here talks to a phone.

What is tested, in two layers:
  * hermetic: the verifier's own logic on a throw-away git repository with a tiny C file (function spans, the
    one-definition rule, counting inside a function only, `#ifdef` versus `#define` for the absence claims);
  * the real plan against the pinned `references/s24-linux` checkout: the committed plan verifies; and each of a list
    of deliberate corruptions of a copy of the plan or of the profile is *rejected, naming the damaged step* (a citation
    changed, a count changed, an order claim reversed, the pinned revision changed, an address in the prose changed, a
    supplier changed, a class changed, a step dropped from the minimal subset, an unknown left without a resolving
    measurement, an absence claim changed, a function renamed or the wrong function named).
The real-tree layer is skipped (not passed) when the pinned checkout is missing.
This does not test that the plan works on hardware; it tests that the verifier would notice if the plan stopped
matching the source it cites."""
import copy, hashlib, importlib.util, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = ROOT / "references/s24-linux"
PROFILE = ROOT / "src/platform/usb/profile.json"
PLAN = HERE / "plan.json"
PIN = "417484173abc2c4fa93e738ea82ad9f2e84911b1"

VERIFIER = Path(os.environ["NAT040_VERIFIER"]) if os.environ.get("NAT040_VERIFIER") else HERE / "verify_plan.py"   # a mutated copy for the mutation checks
spec = importlib.util.spec_from_file_location("verify_plan", VERIFIER)
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)

C_FILE = """\
#include <x.h>

static int foo_init(struct x *p)
{
\tstep_one();
\tudelay(10);
\tudelay(10);
\tstep_two();
\treturn 0;
}

int foo_exit(struct x *p);

static int bar_init(struct x *p)
{
\tstep_two();
\tfoo_init(p);
}

static int dup(struct x *p)
{
\treturn 1;
}

static int dup(struct x *q)
{
\treturn 2;
}
"""

MACROS = """\
#ifdef SOME_MACRO
int a;
#endif
"""


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"})


class Hermetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "r"
        cls.repo.mkdir()
        (cls.repo / "a.c").write_text(C_FILE)
        (cls.repo / "m1.c").write_text(MACROS)
        (cls.repo / "m2.c").write_text("#define SOME_MACRO 1\n")
        git(cls.repo, "init", "-q")
        git(cls.repo, "add", ".")
        git(cls.repo, "commit", "-q", "-m", "x")
        cls.rev = subprocess.run(["git", "-C", str(cls.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        cls.lines = C_FILE.split("\n")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_function_span_bounds(self):
        lo, hi = vp.function_span(self.lines, "foo_init")
        self.assertEqual(self.lines[lo], "static int foo_init(struct x *p)")
        self.assertEqual(self.lines[hi - 1], "}")
        self.assertEqual((lo + 1, hi), (3, 10))   # lines 3..10 inclusive, 1-based

    def test_prototype_and_call_are_not_definitions(self):
        # `int foo_exit(struct x *p);` is a prototype; `\tfoo_init(p);` in bar_init is an indented call
        with self.assertRaisesRegex(vp.VerifyError, "not found"):
            vp.function_span(self.lines, "foo_exit")
        lo, hi = vp.function_span(self.lines, "foo_init")
        self.assertEqual(lo + 1, 3)               # not the call in bar_init at line 17

    def test_two_definitions_are_ambiguous(self):
        with self.assertRaisesRegex(vp.VerifyError, "defined 2 times"):
            vp.function_span(self.lines, "dup")

    def test_missing_function(self):
        with self.assertRaisesRegex(vp.VerifyError, "not found"):
            vp.function_span(self.lines, "nothing_here")

    def step(self, text, func=None, count=None):
        src = {"file": "a.c", "text": text}
        if func:
            src["func"] = func
        if count is not None:
            src["count"] = count
        return {"id": "t.01", "source": src}

    def test_counts_only_inside_the_named_function(self):
        # step_two() appears in foo_init once and in bar_init once: inside foo_init it must count 1
        r = vp.check_step(self.step("step_two();", "foo_init"), self.repo, self.rev, {})
        self.assertTrue(r["ok"])
        self.assertEqual(r["lines"], [8])
        # whole file: twice
        r = vp.check_step(self.step("step_two();", None), self.repo, self.rev, {})
        self.assertFalse(r["ok"])
        self.assertEqual(r["found"], 2)
        r = vp.check_step(self.step("step_two();", None, count=2), self.repo, self.rev, {})
        self.assertTrue(r["ok"])

    def test_repeated_text_needs_the_right_count(self):
        self.assertTrue(vp.check_step(self.step("udelay(10);", "foo_init", count=2), self.repo, self.rev, {})["ok"])
        self.assertFalse(vp.check_step(self.step("udelay(10);", "foo_init", count=1), self.repo, self.rev, {})["ok"])
        self.assertFalse(vp.check_step(self.step("udelay(10);", "foo_init", count=3), self.repo, self.rev, {})["ok"])

    def test_text_in_the_other_function_is_not_found(self):
        r = vp.check_step(self.step("step_one();", "bar_init"), self.repo, self.rev, {})
        self.assertFalse(r["ok"])
        self.assertEqual(r["found"], 0)

    def test_order_check(self):
        res = {
            "x": {"file": "a.c", "lines": [6], "ok": True},
            "y": {"file": "a.c", "lines": [8], "ok": True},
            "z": {"file": "b.c", "lines": [9], "ok": True},
            "u": {"file": "b.c", "lines": [], "ok": False},
        }
        ok = [{"id": "y", "after": "x"}]
        bad = [{"id": "x", "after": "y"}]
        other_file = [{"id": "z", "after": "x"}]
        same_line = [{"id": "x", "after": "x"}]
        self.assertEqual(vp.check_order(ok, res), [])
        self.assertEqual(len(vp.check_order(bad, res)), 1)
        self.assertEqual(len(vp.check_order(other_file, res)), 1)
        self.assertEqual(len(vp.check_order(same_line, res)), 1)       # equal lines are not "after"
        self.assertEqual(len(vp.check_order([{"id": "x", "after": "nope"}], res)), 1)
        # an unresolved citation is reported as itself, not again as an order error (cross-file ones included)
        self.assertEqual(vp.check_order([{"id": "u", "after": "x"}, {"id": "x", "after": "u"}], res), [])

    def absence(self, hits, prefix="#ifdef "):
        return {"absences": [{"id": "A", "word": "SOME_MACRO", "claim": "c", "expected_hits": hits, "hit_prefix": prefix}]}

    def test_absence_exact_hit_set(self):
        # SOME_MACRO is both #ifdef'd (m1.c) and #define'd (m2.c): a claim that it is only ever #ifdef'd must fail
        r = vp.check_absences(self.absence([{"file": "m1.c", "count": 1}]), self.repo, self.rev)[0]
        self.assertFalse(r["ok"])
        self.assertIn("m2.c", r["hits"])
        # claim both files with the #ifdef prefix: the #define line breaks the prefix rule
        r = vp.check_absences(self.absence([{"file": "m1.c", "count": 1}, {"file": "m2.c", "count": 1}]), self.repo, self.rev)[0]
        self.assertFalse(r["ok"])
        self.assertEqual(r["lines_without_prefix"], ["#define SOME_MACRO 1"])
        # claim both with the right prefix for define: both files, but m1 starts with #ifdef -> still fails
        r = vp.check_absences(self.absence([{"file": "m1.c", "count": 1}, {"file": "m2.c", "count": 1}], "#"), self.repo, self.rev)[0]
        self.assertTrue(r["ok"])
        # wrong count in a file
        r = vp.check_absences(self.absence([{"file": "m1.c", "count": 2}, {"file": "m2.c", "count": 1}], "#"), self.repo, self.rev)[0]
        self.assertFalse(r["ok"])
        # a word that does not appear at all, with an empty expectation, holds
        a = {"absences": [{"id": "A", "word": "NOT_ANYWHERE", "claim": "c", "expected_hits": [], "hit_prefix": "#ifdef "}]}
        self.assertTrue(vp.check_absences(a, self.repo, self.rev)[0]["ok"])


@unittest.skipUnless((REPO / ".git").exists() or (REPO / "HEAD").exists(), "pinned checkout references/s24-linux is missing")
class RealPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head != PIN:
            raise unittest.SkipTest(f"checkout HEAD {head} is not the pin {PIN}")
        cls.plan = json.loads(PLAN.read_text())
        cls.profile = json.loads(PROFILE.read_text())
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_verifier(self, plan=None, profile=None, name="run"):
        d = Path(self.tmp.name) / name
        d.mkdir(exist_ok=True)
        pp, qq, out = d / "plan.json", d / "profile.json", d / "resolved.json"
        if plan is None:
            pp = PLAN                       # the committed file itself, so the recorded hash can be compared
        else:
            pp.write_text(json.dumps(plan))
        qq.write_text(json.dumps(profile if profile is not None else self.profile))
        proc = subprocess.run([sys.executable, str(VERIFIER), "--plan", str(pp), "--profile", str(qq),
                               "--repo", str(REPO), "--out", str(out)], capture_output=True, text=True)
        res = json.loads(out.read_text()) if out.exists() else None
        return proc.returncode, proc.stdout, res

    def step(self, plan, sid):
        return next(s for s in plan["steps"] if s["id"] == sid)

    def assert_rejected(self, plan, needle, profile=None, name="mut", errors=1):
        """The mutant must be rejected for the intended reason and for that reason only: `errors` is the number of
        errors the single corruption is expected to produce (more than one only where the corruption breaks several
        stated rules at once; each such test says which)."""
        rc, out, res = self.run_verifier(plan, profile, name)
        self.assertEqual(rc, 1, out)
        self.assertFalse(res["ok"])
        self.assertTrue(any(needle in e for e in res["errors"]), f"{needle!r} not in {res['errors']}")
        self.assertEqual(len(res["errors"]), errors, res["errors"])

    # ---------------------------------------------------------------- the committed plan
    def test_committed_plan_verifies(self):
        rc, out, res = self.run_verifier(name="base")
        self.assertEqual(rc, 0, out)
        self.assertTrue(res["ok"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["steps"], len(self.plan["steps"]))
        self.assertEqual(res["steps_resolved"], res["steps"])
        self.assertTrue(all(r["found"] == r["want"] for r in res["results"]))
        self.assertTrue(all(c["ok"] for c in res["profile_checks"]))
        self.assertEqual([a["id"] for a in res["absences"]], ["A1", "A2"])
        self.assertEqual(res["plan_sha256"], hashlib.sha256(PLAN.read_bytes()).hexdigest())
        self.assertEqual(res["revision"], PIN)

    def test_plan_has_the_pieces_the_task_needs(self):
        # not a mirror of the plan: the facts below are what NAT-040's acceptance asks to be present
        phases = {s["phase"] for s in self.plan["steps"]}
        for p in ("0 platform", "1 PHY order", "2 USBCON", "3 eUSB2 PHY", "4 HS-only", "5 DWC3 core", "6 device start", "7 repeater"):
            self.assertIn(p, phases)
        self.assertGreaterEqual(len(self.plan["unknowns"]), 6)
        for u in self.plan["unknowns"]:
            self.assertTrue(u["resolve"], u["id"])
        self.assertFalse(self.plan["live_firmware_equivalence_qualified"])
        # the plan must not declare itself hardware evidence
        self.assertEqual(self.plan["kind"], "source-review")
        # the resolving tasks exist in the registry
        reg = json.loads((ROOT / "state/lab.json").read_text())
        ids = {t["id"] for t in reg["tasks"]}
        for u in self.plan["unknowns"]:
            for r in u["resolve"]:
                self.assertIn(r["task"], ids, f"{u['id']} -> {r['task']}")

    # ---------------------------------------------------------------- corruptions of the plan
    def test_changed_citation_text(self):
        p = copy.deepcopy(self.plan)
        self.step(p, "3.12")["source"]["text"] = "((EUSBPHY_REG_CMN_CTRL_p) (&reg))->b.phy_enable = 2;"
        self.assert_rejected(p, "3.12: expected 1 occurrence(s) of the cited text, found 0")

    def test_changed_count(self):
        p = copy.deepcopy(self.plan)
        self.assertEqual(self.step(p, "3.10")["source"]["count"], 2)
        self.step(p, "3.10")["source"]["count"] = 1
        self.assert_rejected(p, "3.10: expected 1 occurrence(s) of the cited text, found 2")
        p = copy.deepcopy(self.plan)
        self.step(p, "3.11")["source"]["count"] = 2      # a text that occurs once, claimed twice
        self.assert_rejected(p, "3.11: expected 2 occurrence(s) of the cited text, found 1", name="mut2")

    def test_reversed_order_claim(self):
        # 3.11 (release phy_reset) is claimed to come after 3.15 (the 2500 us wait); in the source it comes before
        p = copy.deepcopy(self.plan)
        self.step(p, "3.11")["after"] = "3.15"
        self.assert_rejected(p, "3.11 (line")
        # and the genuine claim 3.15 after 3.11 holds in the committed plan (base run) but not once reversed
        p = copy.deepcopy(self.plan)
        self.step(p, "3.09")["after"] = "3.12"
        self.assert_rejected(p, "3.09 (line", name="mut2")

    def test_after_in_another_file_is_rejected(self):
        p = copy.deepcopy(self.plan)
        self.step(p, "5.04")["after"] = "3.12"
        self.assert_rejected(p, "5.04: 'after' 3.12 is in another file")

    def test_wrong_pinned_revision(self):
        p = copy.deepcopy(self.plan)
        p["source"]["revision"] = "0" * 40
        rc, out, res = self.run_verifier(p, name="rev")
        self.assertEqual(rc, 1)
        self.assertTrue(any("does not equal the pinned revision" in e for e in res["errors"]))
        self.assertGreaterEqual(len([e for e in res["errors"] if "git show" in e]), len(self.plan["steps"]))   # every citation unreadable
        self.assertTrue(any("profile cross-check failed: pinned comparison revision" in e for e in res["errors"]))

    def test_short_revision_is_rejected(self):
        p = copy.deepcopy(self.plan)
        p["source"]["revision"] = PIN[:12]
        rc, out, res = self.run_verifier(p, name="shortrev")
        self.assertEqual(rc, 1)
        self.assertTrue(any("full 40-hex" in e for e in res["errors"]))

    def test_address_in_prose_differs_from_profile(self):
        p = copy.deepcopy(self.plan)
        s = self.step(p, "3.18")
        self.assertIn("eUSB ctrl 0x178b0000", s["what"])
        s["what"] = s["what"].replace("eUSB ctrl 0x178b0000", "eUSB ctrl 0x178b1000")
        self.assert_rejected(p, "register region bases")

    def test_supplier_in_prose_differs_from_profile(self):
        p = copy.deepcopy(self.plan)
        s = self.step(p, "0.04")
        self.assertIn("vdd12 = s4_l4", s["what"])
        s["what"] = s["what"].replace("vdd12 = s4_l4", "vdd12 = s4_l5")
        self.assert_rejected(p, "supplies")

    def test_repeater_address_in_prose_differs_from_profile(self):
        p = copy.deepcopy(self.plan)
        s = self.step(p, "1.01")
        self.assertIn("0x4f", s["what"])
        s["what"] = s["what"].replace("0x4f", "0x4e")
        # two stated rules break together: the address list, and the address -> part map (0x4e names no part)
        self.assert_rejected(p, "repeater I2C 7-bit addresses", errors=2)

    def test_profile_changed_instead_of_plan(self):
        q = copy.deepcopy(self.profile)
        q["PHY"]["pmu_offsets"][0] = "0x618"
        self.assert_rejected(self.plan, "PMU isolation offsets", profile=q)
        q = copy.deepcopy(self.profile)
        q["comparison"]["live_firmware_equivalence_qualified"] = True
        self.assert_rejected(self.plan, "live-firmware equivalence", profile=q, name="mut2")
        q = copy.deepcopy(self.profile)
        q["USB2_repeaters"]["actual_fitted_component_qualified"] = True
        self.assert_rejected(self.plan, "repeater fitted part", profile=q, name="mut3")

    def test_class_changed(self):
        # 3.05 is a vendor step in the minimal subset; calling it informational drops it from V but it stays in minimal
        p = copy.deepcopy(self.plan)
        self.step(p, "3.05")["class"] = "I"
        self.assert_rejected(p, "3.05 is in minimal_subset but is not class V")
        p = copy.deepcopy(self.plan)
        self.step(p, "3.05")["class"] = "nonsense"
        # two rules broken at once: the class is not in the legend, and (not being V) the step is in the minimal subset
        self.assert_rejected(p, "unknown class", name="mut2", errors=2)

    def test_v_step_dropped_from_minimal_subset(self):
        p = copy.deepcopy(self.plan)
        for m in p["minimal_subset"]:
            if "3.07" in m["ids"]:
                m["ids"].remove("3.07")
        self.assert_rejected(p, "3.07 is class V but not in minimal_subset")

    def test_omitted_step_must_be_listed(self):
        p = copy.deepcopy(self.plan)
        for o in p["omitted"]:
            if "4.02" in o["ids"]:
                o["ids"].remove("4.02")
        self.assert_rejected(p, "4.02 is M-omit but not listed in omitted")

    def test_unknown_without_resolving_measurement(self):
        p = copy.deepcopy(self.plan)
        p["unknowns"][0]["resolve"] = []
        self.assert_rejected(p, "has no resolving measurement")

    def test_unknown_with_a_malformed_task(self):
        p = copy.deepcopy(self.plan)
        p["unknowns"][0]["resolve"][0]["task"] = "later"
        self.assert_rejected(p, "bad task id")

    def test_u_step_not_covered(self):
        p = copy.deepcopy(self.plan)
        for u in p["unknowns"]:
            if "0.04" in u["steps"]:
                u["steps"].remove("0.04")
        self.assert_rejected(p, "0.04 is class U but neither an unknown nor an omission covers it")

    def test_absence_claim_changed(self):
        p = copy.deepcopy(self.plan)
        p["absences"][0]["expected_hits"][0]["count"] = 3
        self.assert_rejected(p, "absence A1")
        p = copy.deepcopy(self.plan)
        p["absences"][1]["expected_hits"] = []
        self.assert_rejected(p, "absence A2", name="mut2")
        p = copy.deepcopy(self.plan)
        p["absences"][1]["hit_prefix"] = "#define "
        self.assert_rejected(p, "absence A2", name="mut3")

    def test_renamed_function(self):
        p = copy.deepcopy(self.plan)
        self.step(p, "3.12")["source"]["func"] = "phy_exynos_eusb_initiatx"
        self.assert_rejected(p, "3.12: function 'phy_exynos_eusb_initiatx' not found")

    def test_wrong_function_named(self):
        # text that is in phy_exynos_eusb_initiate, cited from phy_exynos_eusb_tune in the same file
        p = copy.deepcopy(self.plan)
        self.step(p, "3.03")["source"]["func"] = "phy_exynos_eusb_tune"
        self.assert_rejected(p, "3.03: expected 1 occurrence(s) of the cited text, found 0")

    def test_unknown_file(self):
        p = copy.deepcopy(self.plan)
        self.step(p, "3.03")["source"]["file"] = "drivers/phy/samsung/does-not-exist.c"
        self.assert_rejected(p, "3.03: git show")

    # ---------------------------------------------------------------- the ladder and the power-on chain
    def rung(self, plan, rid):
        return next(r for r in plan["ladder"] if r["id"] == rid)

    def test_vendor_step_not_in_any_rung(self):
        p = copy.deepcopy(self.plan)
        self.rung(p, "L4")["steps"].remove("5.00")
        self.assert_rejected(p, "5.00 is class V but no ladder rung performs it")

    def test_nat043_unknown_without_a_rung(self):
        p = copy.deepcopy(self.plan)
        for r in p["ladder"]:
            if "U2" in r["resolves"]:
                r["resolves"].remove("U2")
        self.assert_rejected(p, "unknown U2 is to be measured by NAT-043 but no ladder rung resolves it")

    def test_ladder_names_unknown_step_or_unknown(self):
        p = copy.deepcopy(self.plan)
        self.rung(p, "L4")["steps"].append("9.99")
        self.assert_rejected(p, "ladder L4 names unknown step 9.99")
        p = copy.deepcopy(self.plan)
        self.rung(p, "L1")["resolves"].append("U99")
        self.assert_rejected(p, "ladder L1 resolves unknown U99", name="mut2")

    def test_first_rungs_only_read(self):
        # the plan promises that L0-L2 write nothing; tie the promise to the steps they perform
        for rid in ("L0", "L1", "L2"):
            r = self.rung(self.plan, rid)
            self.assertEqual(r["writes"], [], rid)
            for sid in r["steps"]:
                for reg in self.step(self.plan, sid).get("registers", []):
                    self.assertNotIn(" = ", reg, f"{rid} step {sid} writes: {reg}")
        # and a write-step moved into L1 is what this check would catch
        p = copy.deepcopy(self.plan)
        self.rung(p, "L1")["steps"].append("0.20")
        with self.assertRaises(AssertionError):
            for sid in self.rung(p, "L1")["steps"]:
                for reg in self.step(p, sid).get("registers", []):
                    self.assertNotIn(" = ", reg)

    def test_power_on_chain_order(self):
        # vendor order in pmucal_local_enable: on sequence, then the DTZPC SMC, then cmu_init
        self.assertEqual(self.step(self.plan, "0.02")["after"], "0.22")
        self.assertEqual(self.step(self.plan, "0.23")["after"], "0.02")
        p = copy.deepcopy(self.plan)
        self.step(p, "0.22")["after"] = "0.23"
        self.assert_rejected(p, "0.22 (line")
        p = copy.deepcopy(self.plan)
        self.step(p, "0.02")["after"] = "0.23"
        self.assert_rejected(p, "0.02 (line", name="mut2")             # the SMC is claimed after cmu_init, but comes before it

    def test_pmu_register_changed_in_citation(self):
        p = copy.deepcopy(self.plan)
        st = self.step(p, "0.21")
        self.assertIn("0x2004", st["source"]["text"])
        st["source"]["text"] = st["source"]["text"].replace("0x2004", "0x2008")
        self.assert_rejected(p, "0.21: expected 1 occurrence(s) of the cited text, found 0")

    def test_missing_step_does_not_crash_the_profile_check(self):
        p = copy.deepcopy(self.plan)
        p["steps"] = [s for s in p["steps"] if s["id"] != "3.18"]
        self.assert_rejected(p, "profile cross-check could not run")

    def test_duplicate_step_id(self):
        # 4.10 (informational, no order claim, referenced by nothing) takes the id of 4.09: exactly the duplicate is reported
        p = copy.deepcopy(self.plan)
        i = next(k for k, s in enumerate(p["steps"]) if s["id"] == "4.10")
        p["steps"][i]["id"] = "4.09"
        self.assert_rejected(p, "duplicate step ids")


if __name__ == "__main__":
    unittest.main(verbosity=2)
