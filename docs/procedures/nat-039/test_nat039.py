#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-039 host tests: the capture is read-only by construction, the parsers read real device-tree lines, and the comparison reports a
mismatch when the measured value (or the plan it is anchored to) changes. The fixture is the sanitized extract of the real capture
(capture-extract/); nothing here talks to a phone.

    python3 -I docs/procedures/nat-039/test_nat039.py"""
import contextlib
import hashlib
import io
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
EXTRACT = HERE / "capture-extract"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


cap = load("capture")
cmp_ = load("compare")


def scratch():
    d = Path(tempfile.mkdtemp(prefix="nat039-test-", dir=str(Path(tempfile.gettempdir()))))
    return d


def mutated_extract(**edits):
    """A copy of the extract with `name` -> function(text) -> text applied."""
    d = scratch()
    shutil.copytree(EXTRACT, d / "x")
    for name, fn in edits.items():
        f = d / "x" / (name + ".txt")
        f.write_text(fn(f.read_text()))
    return d, d / "x"


def rows_by_id(res):
    return {r["id"]: r for r in res["rows"]}


class CaptureIsReadOnly(unittest.TestCase):
    def test_every_command_passes_the_deny_list(self):
        cap.assert_read_only()
        self.assertGreater(len(cap.COMMANDS), 40)

    def test_names_are_unique(self):
        names = [n for n, _ in cap.COMMANDS]
        self.assertEqual(len(names), len(set(names)))

    def test_writes_and_state_changes_are_refused(self):
        for bad in ("cat /proc/x > /sys/y", "cat a >> b", "cat a 2>&1 > b", "tee /sys/x", "setprop persist.x 1", "settings put global x 1", "svc usb setFunctions mtp",
                    "mount -t debugfs none /sys/kernel/debug", "umount /x", "insmod x.ko", "rmmod x", "dd if=/dev/zero of=/x", "rm -r /x", "mv a b", "cp a b",
                    "chmod 777 /x", "kill 1", "reboot", "am start x", "pm install x", "cmd package x", "start adbd", "stop adbd", "sed -i s/a/b/ f", "ip link set down",
                    "magisk --install", "resetprop a b", "busybox devmem 0x17900000", "devmem 0x1", "sh -c 'id'", "python3 -c 1", "setenforce 0", "nohup x &",
                    "find / -exec rm {} +", "find / -delete", "find / -fprint /x"):
            with self.subTest(bad):
                with self.assertRaises(SystemExit):
                    cap.assert_read_only([("t", bad)])

    def test_harmless_redirections_are_allowed_but_only_those(self):
        cap.assert_read_only([("t", "ls /x 2>&1 | head"), ("u", "find /x 2>/dev/null | head")])
        with self.assertRaises(SystemExit):
            cap.assert_read_only([("t", "ls /x 2>&1 >/tmp/y")])

    def test_run_issues_only_get_state_and_shell_su_reads(self):
        calls = []

        def fake(args, timeout):
            calls.append(list(args))
            return 0, ("device\n" if args[0] == "get-state" else "out\n"), ""

        d = scratch()
        try:
            with mock.patch.object(cap, "adb", fake), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cap.main(["--out", str(d / "o")]), 0)
            self.assertEqual(calls[0], ["get-state"])
            self.assertEqual(len(calls), 1 + len(cap.COMMANDS))
            for c, (name, cmd) in zip(calls[1:], cap.COMMANDS):
                self.assertEqual(c[:3], ["shell", "su", "-c"])
                self.assertEqual(len(c), 4)
                self.assertTrue(c[3].startswith("'") and c[3].endswith("'"))
                self.assertIn("'\\''" if "'" in cmd else cmd[:10], c[3])
            self.assertEqual({p.name for p in (d / "o").iterdir()}, {n + ".txt" for n, _ in cap.COMMANDS} | {"index.json"})
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_missing_device_stops_before_any_command(self):
        calls = []
        with mock.patch.object(cap, "adb", lambda a, t: (calls.append(a), (1, "", "no devices"))[1]):
            d = scratch()
            try:
                with self.assertRaises(SystemExit):
                    cap.main(["--out", str(d / "o")])
            finally:
                shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(calls, [["get-state"]])

    def test_an_existing_output_directory_is_never_reused(self):
        d = scratch()
        try:
            (d / "o").mkdir()
            with self.assertRaises(FileExistsError):
                cap.main(["--out", str(d / "o")])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_deny_listed_command_never_reaches_adb(self):
        calls = []
        d = scratch()
        try:
            with mock.patch.object(cap, "COMMANDS", [("ok", "ls /x"), ("bad", "echo 1 > /sys/x")]), mock.patch.object(cap, "adb", lambda a, t: (calls.append(a), (0, "device", ""))[1]):
                with self.assertRaises(SystemExit):
                    cap.main(["--out", str(d / "o")])
        finally:
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(calls, [])


class Parsers(unittest.TestCase):
    LINE = "reg:  00 00 00 00 17 90 00 00 00 01 00 00  | ............"

    def test_property_and_node_lines(self):
        text = "== nodeA\nname:  75 73 62 00  | usb.\nranges:  | \nreg:  00 00 00 00 17 90 00 00 00 01 00 00  | ............\n== nodeB\nstatus:  6f 6b 61 79 00  | okay."
        nodes = cmp_.parse_dt(text)
        self.assertEqual([n for n, _ in nodes], ["nodeA", "nodeB"])
        self.assertEqual(nodes[0][1]["ranges"], b"")
        self.assertEqual(cmp_.cstr(nodes[0][1]["name"]), "usb")
        self.assertEqual(cmp_.cstr(nodes[1][1]["status"]), "okay")
        self.assertEqual(cmp_.reg_pairs(nodes[0][1]["reg"]), [(0x17900000, 0x10000)])

    def test_a_pipe_in_the_text_part_does_not_leak_into_the_bytes(self):
        n = cmp_.parse_dt("p:  41 42  | A|B")
        self.assertEqual(n[0][1]["p"], b"AB")

    def test_non_property_lines_are_skipped(self):
        n = cmp_.parse_dt("garbage\ngrep: /x: No such file\nreg:  00 00 00 01  | ....")
        self.assertEqual(list(n[0][1]), ["reg"])

    def test_cells_and_reg_pairs_reject_bad_lengths(self):
        with self.assertRaises(ValueError):
            cmp_.cells(b"\0\0\0")
        with self.assertRaises(ValueError):
            cmp_.reg_pairs(b"\0" * 8)

    def test_two_address_cells_combine_into_one_64_bit_base(self):
        self.assertEqual(cmp_.reg_pairs(bytes.fromhex("0000000122b20000" + "00008000")), [(0x122b20000, 0x8000)])

    def test_the_real_extract_parses_to_the_expected_nodes(self):
        n = cmp_.parse_dt((EXTRACT / "dt-hsi2c.txt").read_text())
        self.assertEqual(len(n), 3)
        self.assertEqual([x[0].rstrip("/").rsplit("/", 1)[-1] for x in n[1:]], ["ptn3222-repeater@4F", "tusb2e11-repeater@3E"])


class ComparisonOnTheRealExtract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = cmp_.compare(EXTRACT)
        cls.rows = rows_by_id(cls.res)

    def test_no_mismatch_and_the_expected_counts(self):
        s = self.res["summary"]
        self.assertEqual(s["mismatches"], [])
        self.assertEqual(s["counts"], {"match": 20, "consistent": 4, "new": 13, "unresolved": 2, "mismatch": 0})

    def test_the_unresolved_rows_are_exactly_the_ones_that_need_a_register_or_debugfs_read(self):
        self.assertEqual(self.res["summary"]["unresolved"], ["C11d", "C13"])

    def test_values_are_the_device_tree_values(self):
        r = self.rows
        self.assertEqual(r["C01"]["observed"], "0x17900000/0x10000")
        self.assertEqual(r["C01c"]["observed"], "1790c100-1790ffff")
        self.assertEqual(r["C02"]["observed"], {"kind": "SPI", "number": 403, "flags": 4})
        self.assertEqual(r["C04"]["observed"], ["0x178a0000", "0x178b0000", "0x178c0000", "0x178d0000", "0x178e0000"])
        self.assertEqual(r["C04b"]["observed"], ["0x200", "0x200", "0x200", "0x800", "0x800"])
        self.assertEqual(r["C06"]["observed"], "0x12862000/0x20")
        self.assertEqual(r["C08"]["observed"], "0x17810204")
        self.assertEqual(r["C10"]["observed"], "0x61c")
        self.assertEqual(r["C10b"]["observed"], "0x620")
        self.assertEqual(r["C11"]["observed"], "0x22b20000")
        self.assertEqual(r["C15"]["observed"], {"tusb2e11": ["0x3e", "okay"], "ptn3222": ["0x4f", "okay"]})
        self.assertEqual(r["C12a"]["observed"], {"vdd075_usb": ["enabled", 750000], "vdd12_usb": ["enabled", 1200000], "vdd18_usb": ["enabled", 1800000], "vdd33_usb": ["enabled", 3100000]})
        self.assertEqual(r["C11c"]["observed"], {"aclk": "0x387", "sclk": "0x386", "bus": "0x388"})
        self.assertEqual(r["C19"]["observed"], {"state": "configured", "current_speed": "high-speed", "maximum_speed": "super-speed"})

    def test_repeater_tuning_pairs_are_register_then_value(self):
        t = self.rows["C17"]["observed"]
        self.assertIn(["usb2_tx_adjust_port1", "0x70", "0x5d"], t["tusb2e11"])
        self.assertIn(["usb2_rx_control", "0x06", "0x30"], t["ptn3222"])

    def test_the_two_quirk_rows_agree_on_which_quirk_the_plan_mentions(self):
        q = self.rows["C21b"]["observed"]
        self.assertTrue(q["snps,quirk-frame-length-adjustment"])
        self.assertEqual(sorted(k for k, v in q.items() if v), ["snps,quirk-frame-length-adjustment"])

    def test_every_row_has_a_known_result_a_source_and_no_empty_claim(self):
        for r in self.res["rows"]:
            self.assertIn(r["result"], ("match", "mismatch", "consistent", "new", "unresolved"))
            self.assertTrue(r["claim"] and r["source"] and r["plan_ref"])
        self.assertEqual(len({r["id"] for r in self.res["rows"]}), len(self.res["rows"]))

    def test_every_unknown_has_a_status_sentence(self):
        self.assertEqual(sorted(self.res["summary"]["unknown_status"]), ["U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8"])

    def test_command_line_exit_codes(self):
        out = scratch()
        quiet = contextlib.redirect_stdout(io.StringIO())
        try:
            with quiet:
                self.assertEqual(cmp_.main(["compare", "--capture", str(EXTRACT), "--json", str(out / "r.json")]), 0)
            self.assertEqual(json.loads((out / "r.json").read_text())["summary"]["mismatches"], [])
            d, x = mutated_extract(**{"dt-usb-top": lambda t: t.replace("00 00 00 00 17 90 00 00 00 01 00 00", "00 00 00 00 17 91 00 00 00 01 00 00")})
            try:
                with quiet:
                    self.assertEqual(cmp_.main(["compare", "--capture", str(x)]), 1)
            finally:
                shutil.rmtree(d, ignore_errors=True)
        finally:
            shutil.rmtree(out, ignore_errors=True)


class ComparisonSeesChanges(unittest.TestCase):
    """The comparison must be able to say 'mismatch'; each case edits one measured value and expects exactly the rows that depend on it."""

    def mism(self, **edits):
        d, x = mutated_extract(**edits)
        try:
            return set(cmp_.compare(x)["summary"]["mismatches"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_controller_base(self):
        self.assertIn("C01", self.mism(**{"dt-usb-top": lambda t: t.replace("17 90 00 00 00 01 00 00", "17 91 00 00 00 01 00 00")}))

    def test_interrupt_number(self):
        m = self.mism(**{"dt-dwc3": lambda t: re.sub(r"(interrupts:  00 00 00 00 00 00 01 )93", r"\g<1>94", t)})
        self.assertIn("C02", m)

    def test_gic_line_missing(self):
        self.assertIn("C02b", self.mism(**{"interrupts-usb": lambda t: t.replace("GICv3 435 Level     dwc3", "GICv3 436 Level     dwc3")}))

    def test_phy_block_base(self):
        self.assertIn("C04", self.mism(**{"dt-phy": lambda t: t.replace("17 8c 00 00 00 00 02 00", "17 8f 00 00 00 00 02 00")}))

    def test_phy_window_claims_in_iomem(self):
        self.assertIn("C04c", self.mism(**{"iomem-hsi0": lambda t: t.replace("178e0000-178e07ff : 178a0000.phy phy@178A0000\n", "")}))

    def test_sysreg_base(self):
        self.assertIn("C05", self.mism(**{"dt-sysreg-pd-cmu": lambda t: t.replace("reg:  00 00 00 00 17 82 00 00", "reg:  00 00 00 00 17 83 00 00")}))

    def test_need_smc(self):
        self.assertIn("C08", self.mism(**{"dt-sysreg-pd-cmu": lambda t: t.replace("need_smc:  17 81 02 04", "need_smc:  17 81 02 08")}))

    def test_cmu_id(self):
        self.assertIn("C07", self.mism(**{"dt-sysreg-pd-cmu": lambda t: t.replace("cmu_id:  17 80 00 00", "cmu_id:  17 80 10 00")}))

    def test_pmu_isolation_offset(self):
        self.assertIn("C10", self.mism(**{"dt-phy": lambda t: t.replace("pmu_offset:  00 00 06 1c", "pmu_offset:  00 00 06 18")}))

    def test_clock_controller_too_small_for_the_ladder_reads(self):
        self.assertIn("C11b", self.mism(**{"dt-sysreg-pd-cmu": lambda t: t.replace("22 b2 00 00 00 00 80 00", "22 b2 00 00 00 00 10 00")}))

    def test_rail_on_the_wrong_pmic(self):
        self.assertIn("C12", self.mism(**{"regulator-parents": lambda t: t.replace("s2mps28-5-regulator", "s2mps28-4-regulator")}))

    def test_rail_missing(self):
        self.assertIn("C12", self.mism(**{"regulators": lambda t: t.replace("vdd075_usb", "vdd075_other")}))

    def test_repeater_address(self):
        d, x = mutated_extract(**{"dt-hsi2c": lambda t: t.replace("reg:  00 00 00 3e", "reg:  00 00 00 3f")})
        try:
            self.assertIn("C15", cmp_.compare(x)["summary"]["mismatches"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_repeater_driver_unbound(self):
        d, x = mutated_extract(**{"i2c-repeater-drivers": lambda t: t.replace("tusb2e11-repeater\n", "")})
        try:
            r = rows_by_id(cmp_.compare(x))
            self.assertEqual(r["C16"]["result"], "mismatch")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_iommu_property_appears(self):
        d, x = mutated_extract(**{"dt-dma-props": lambda t: "iommus\n" + t})
        try:
            self.assertEqual(rows_by_id(cmp_.compare(x))["C18"]["result"], "mismatch")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_max_speed_changes(self):
        d, x = mutated_extract(**{"dt-dwc3": lambda t: t.replace("maximum-speed:  73 75 70 65 72 2d 73 70 65 65 64 00", "maximum-speed:  68 69 67 68 2d 73 70 65 65 64 00")})
        try:
            self.assertEqual(rows_by_id(cmp_.compare(x))["C03"]["result"], "mismatch")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_debugfs_becoming_readable_changes_the_clock_row(self):
        d, x = mutated_extract(**{"clk-hsi0": lambda t: "aclk 1 1 0 400000000\n"})
        try:
            self.assertEqual(rows_by_id(cmp_.compare(x))["C11d"]["result"], "new")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_genpd_becoming_readable_changes_the_domain_row(self):
        d, x = mutated_extract(**{"genpd-hsi0": lambda t: "pd_hsi0 on 0\n"})
        try:
            self.assertEqual(rows_by_id(cmp_.compare(x))["C13"]["result"], "new")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class PlanAnchors(unittest.TestCase):
    """The expectations are tied to plan.json: if a cited step stops containing the value, the comparison refuses to run."""

    def run_with_plan(self, edit):
        d = scratch()
        try:
            plan = json.loads(cmp_.PLAN.read_text())
            edit(plan)
            (d / "plan.json").write_text(json.dumps(plan))
            return cmp_.compare(EXTRACT, cmp_.Plan(d / "plan.json", cmp_.README40))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def step(self, plan, sid):
        return next(s for s in plan["steps"] if s["id"] == sid)

    def test_unmodified_copy_of_the_plan_passes(self):
        self.assertEqual(self.run_with_plan(lambda p: None)["summary"]["mismatches"], [])

    def test_changed_controller_address_in_step_3_18(self):
        def edit(p):
            s = self.step(p, "3.18")
            s["registers"] = [r.replace("0x17900000", "0x17910000") for r in s.get("registers", [])]
            s["what"] = s["what"].replace("0x17900000", "0x17910000")
        with self.assertRaises(AssertionError):
            self.run_with_plan(edit)

    def test_changed_need_smc_in_step_0_01(self):
        def edit(p):
            s = self.step(p, "0.01")
            s["what"] = s["what"].replace("0x17810204", "0x17810208")
            s["registers"] = [r.replace("0x17810204", "0x17810208") for r in s["registers"]]
        with self.assertRaises(AssertionError):
            self.run_with_plan(edit)

    def test_missing_step(self):
        with self.assertRaises(AssertionError):
            self.run_with_plan(lambda p: p["steps"].remove(self.step(p, "5.17")))

    def test_rail_names_in_u1_changed(self):
        def edit(p):
            u = next(u for u in p["unknowns"] if u["id"] == "U1")
            u["what"] = u["what"].replace("vdd12 s4_l4", "vdd12 s3_l4")
        res = self.run_with_plan(edit)
        self.assertIn("C12", res["summary"]["mismatches"])

    def test_l2_reads_outside_the_window(self):
        def edit(p):
            r = next(x for x in p["ladder"] if x["id"] == "L2")
            r["reads"] = ["0x22b30000"] + r["reads"][1:]
        self.assertIn("C11b", self.run_with_plan(edit)["summary"]["mismatches"])

    def test_readme_spi_number_drives_the_interrupt_row(self):
        d = scratch()
        try:
            (d / "README.md").write_text(cmp_.README40.read_text().replace("SPI 403", "SPI 404"))
            res = cmp_.compare(EXTRACT, cmp_.Plan(cmp_.PLAN, d / "README.md"))
            self.assertIn("C02", res["summary"]["mismatches"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_readme_without_the_cited_text_is_refused(self):
        d = scratch()
        try:
            (d / "README.md").write_text("SPI 403 only")
            with self.assertRaises(AssertionError):
                cmp_.compare(EXTRACT, cmp_.Plan(cmp_.PLAN, d / "README.md"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ExtractIsSanitized(unittest.TestCase):
    def make_cap(self, d, **overrides):
        c = d / "cap"
        c.mkdir()
        for name in cmp_.NEEDED:
            (c / (name + ".txt")).write_text(overrides.get(name, "x\n"))
        (c / "index.json").write_text(json.dumps({"at": "2026-11-11T00:00:00+0000", "commands": [{"name": "x", "exit_code": 0, "bytes": 2, "stderr": "SECRET", "command": "c", "seconds": 1}]}))
        return c

    def test_forbidden_patterns(self):
        self.assertEqual(cmp_.forbidden("ok 12:34:56:ab:cd:ef"), ["MAC-like"])
        self.assertEqual(cmp_.forbidden("imei 123456789012345 x"), ["14-16 digit number"])
        self.assertEqual(cmp_.forbidden("abc SER123 def", extra=("SER123",)), ["forbidden string"])
        self.assertEqual(cmp_.forbidden("0x17900000 1790c100-1790ffff 17900000.dwc3 25672.272721", extra=("",)), [])

    def test_extract_refuses_a_file_with_a_mac(self):
        d = scratch()
        try:
            c = self.make_cap(d, identity="mac aa:bb:cc:dd:ee:ff\n")
            with self.assertRaises(SystemExit):
                cmp_.extract(c, d / "o")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_extract_refuses_the_device_serial(self):
        d = scratch()
        try:
            c = self.make_cap(d, identity="serial ABCDE12345\n")
            with self.assertRaises(SystemExit):
                cmp_.extract(c, d / "o", extra=("ABCDE12345",))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_extract_keeps_only_the_four_usb_rails_and_records_raw_hashes(self):
        d = scratch()
        try:
            reg = "regulator.1 name=VDD_CAM state=enabled uV=1 users=1\nregulator.38 name=vdd18_usb state=enabled uV=1800000 users=1\nregulator.2 name=VDD_BTP_1P8 state=enabled uV=1 users=1\n"
            c = self.make_cap(d, regulators=reg)
            m = cmp_.extract(c, d / "o")
            kept = (d / "o" / "regulators.txt").read_text()
            self.assertEqual(kept, "regulator.38 name=vdd18_usb state=enabled uV=1800000 users=1\n")
            self.assertEqual(m["files"]["regulators.txt"]["raw_sha256"], hashlib.sha256(reg.encode()).hexdigest())
            self.assertTrue(m["files"]["regulators.txt"]["filtered"])
            self.assertFalse(m["files"]["identity.txt"]["filtered"])
            self.assertNotIn("SECRET", (d / "o" / "manifest.json").read_text(), "per-command stderr must not be copied")
            self.assertEqual(m["commands"][0].keys(), {"name", "exit_code", "bytes"})
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_committed_extract_has_no_identifier_and_matches_its_manifest(self):
        for f in EXTRACT.glob("*.txt"):
            self.assertEqual(cmp_.forbidden(f.read_text()), [], f.name)
        man = json.loads((EXTRACT / "manifest.json").read_text())
        self.assertEqual(set(man["files"]), {n + ".txt" for n in cmp_.NEEDED})
        for n, meta in man["files"].items():
            self.assertEqual((EXTRACT / n).stat().st_size, meta["kept_bytes"], n)
            if not meta["filtered"]:
                self.assertEqual(hashlib.sha256((EXTRACT / n).read_bytes()).hexdigest(), meta["raw_sha256"], n)

    def test_the_command_set_that_ran_is_the_command_set_in_the_script(self):
        man = json.loads((EXTRACT / "manifest.json").read_text())
        self.assertEqual(man["commands_sha256"], cmp_.commands_hash(cap.COMMANDS))
        self.assertEqual([c["name"] for c in man["commands"]], [n for n, _ in cap.COMMANDS])
        self.assertEqual({c["name"] for c in man["commands"] if c["exit_code"]}, {"clk-summary-header", "regulator-summary-header"})

    def test_committed_extract_rails_are_only_the_usb_rails(self):
        names = re.findall(r"name=(\S+)", (EXTRACT / "regulators.txt").read_text())
        self.assertEqual(sorted(names), sorted(cmp_.USB_RAILS))

    def test_extract_agrees_with_the_local_raw_capture_when_present(self):
        raw = HERE.parents[2] / "artifacts" / "nat-039" / "capture-004"
        if not raw.is_dir():
            self.skipTest("raw capture is kept local (artifacts/ is git-ignored)")
        man = json.loads((EXTRACT / "manifest.json").read_text())
        for n, meta in man["files"].items():
            self.assertEqual(hashlib.sha256((raw / n).read_bytes()).hexdigest(), meta["raw_sha256"], n)
        self.assertEqual(cmp_.compare(raw), cmp_.compare(EXTRACT))


if __name__ == "__main__":
    unittest.main(verbosity=1)
