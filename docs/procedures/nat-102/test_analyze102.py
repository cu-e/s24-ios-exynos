#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102: tests of analyze_nat102.py (the heartbeat ladder H0-H5). Evidence kind: host-test.

The text the analyser reads is produced by two independent things so that the tests do not merely mirror the parser: (1) the real hb.c control flow (compiled for the host with -DHOST_TEST, run against a
fake ps that prints the two real column formats) wrapped in kernel-log-looking noise, and (2) hand-written texts for the cases hb cannot produce on the host (cut lists, holes, a flood). With the real
NAT-098 kernel text (local artifact, skipped when absent) the ladder must say H1: that run had no hb."""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


AN = _load("nat102_analyze", HERE / "analyze_nat102.py")
JOBS_DIR = ROOT / "artifacts/nat-096/pid1-sq/root/LaunchDaemons"
SRC = ROOT / "docs/procedures/nat-101/src/hb.c"
NAT098_TEXT = ROOT / "artifacts/nat-098/run-001/kernel-log.txt"

JOBS = [
    dict(label="com.apple.logd", program="/usr/libexec/logd", self_start=True),
    dict(label="com.apple.containermanagerd", program="/usr/libexec/containermanagerd", self_start=True),
    dict(label="com.apple.powerd", program="/usr/libexec/powerd", self_start=True),
    dict(label="com.apple.notifyd", program="/usr/sbin/notifyd", self_start=False),
    dict(label="com.nat085.ps", program="/bin/ps", self_start=True),
]
NOISE = ["[  215.101]: AppleARMPE: something", "[  215.220]: launchd: boot task", "kernel: noise line without a clock"]

LIST_A = "  PID TTY           TIME CMD\n    1 ??         0:00.10 /sbin/launchd\n   16 ??         0:00.02 /usr/libexec/logd\n   12 ??         0:00.01 /usr/libexec/containermanagerd\n   30 ??         0:00.00 ps -A"
LIST_O = "  PID  PPID STAT COMM\n    1     0 Ss   /sbin/launchd\n   16     1 Ss   /usr/libexec/logd\n   19     1 Z    (powerd)\n   31     5 R+   ps"


def hb_console(rounds=3, ps_a=LIST_A, ps_o=LIST_O):
    """What hb prints, in the real format, for `rounds` rounds."""
    out = ["", "SWEET hb: start pid=40 ppid=1 period=10s rounds=60 ps_timeout=8s"]
    for n in range(1, rounds + 1):
        out.append("SWEET hb: n=%d pid=40 ppid=1 up=%d" % (n, (n - 1) * 10))
        out.append(ps_a if n % 2 else ps_o)
        out.append("SWEET hb: n=%d ps pid=%d status=0 ms=%d" % (n, 40 + n, 120 + n))
    return "\n".join(out)


class Parse(unittest.TestCase):
    def test_start_marks_status_lists_and_rounds(self):
        p = AN.parse("\n".join(NOISE) + "\n" + hb_console(3) + "\nSWEET hb: done rounds=3\n")
        self.assertEqual((p["start"]["pid"], p["start"]["ppid"], p["start"]["period"], p["start"]["rounds"], p["start"]["ps_timeout"]), (40, 1, 10, 60, 8))
        self.assertEqual([m["n"] for m in p["marks"]], [1, 2, 3])
        self.assertEqual([(m["pid"], m["ppid"]) for m in p["marks"]], [(40, 1), (40, 1), (40, 1)])
        self.assertEqual([m["up"] for m in p["marks"]], [0, 10, 20])
        self.assertEqual([(s["n"], s["ps_pid"], s["status"], s["ms"], s["timeout_killed"]) for s in p["ps_status"]], [(1, 41, 0, 121, False), (2, 42, 0, 122, False), (3, 43, 0, 123, False)])
        self.assertEqual(p["done"]["rounds"], 3)
        self.assertEqual([(x["kind"], x["round"], len(x["rows"])) for x in p["lists"]], [("A", 1, 4), ("O", 2, 4), ("A", 3, 4)])
        self.assertEqual(p["lists"][1]["rows"][2], dict(pid=19, ppid=1, stat="Z", cmd="(powerd)"))
        self.assertEqual(p["lists"][0]["rows"][1], dict(pid=16, tty="??", time="0:00.02", cmd="/usr/libexec/logd"))
        self.assertEqual(p["unknown_hb"], [])

    def test_a_timeout_killed_status_and_negative_values(self):
        p = AN.parse("SWEET hb: n=2 ps pid=-11 status=0 ms=3\nSWEET hb: n=3 ps pid=77 status=9 ms=8001 timeout-killed\n")
        self.assertEqual([(s["ps_pid"], s["status"], s["timeout_killed"]) for s in p["ps_status"]], [(-11, 0, False), (77, 9, True)])

    def test_an_unparsable_hb_line_is_kept_not_dropped(self):
        p = AN.parse("SWEET hb: something new\n")
        self.assertEqual(p["unknown_hb"], ["SWEET hb: something new"])

    def test_a_list_not_directly_after_a_marker_has_no_round(self):
        text = "SWEET hb: n=1 pid=40 ppid=1 up=0\n" + "noise\n" * 5 + LIST_A + "\n"
        p = AN.parse(text)
        self.assertIsNone(p["lists"][0]["round"])

    def test_a_list_after_its_status_line_is_not_claimed_by_the_old_marker(self):
        # the job heartbeat's list (no hb marker before it) comes after hb's status line: it must not inherit the round
        text = "SWEET hb: n=1 pid=40 ppid=1 up=0\n" + LIST_A + "\nSWEET hb: n=1 ps pid=41 status=0 ms=5\n" + LIST_A + "\n"
        p = AN.parse(text)
        self.assertEqual([x["round"] for x in p["lists"]], [1, None])

    def test_cut_lists_are_flagged(self):
        text = hb_console(1) + "\n"
        whole = AN.parse(text)["lists"][0]
        self.assertFalse(whole["cut"])
        cut = AN.parse("SWEET hb: n=1 pid=40 ppid=1 up=0\n" + LIST_A + "\n")["lists"][0]
        self.assertTrue(cut["cut"])
        holed = AN.parse("SWEET hb: n=1 pid=40 ppid=1 up=0\n" + LIST_A + "\n\n[... 1234 bytes lost in transport ...]\n")["lists"][0]
        self.assertTrue(holed["cut"])

    def test_the_two_list_formats_are_told_apart(self):
        p = AN.parse(LIST_A + "\n" + LIST_O + "\n")
        self.assertEqual([x["kind"] for x in p["lists"]], ["A", "O"])
        self.assertEqual([len(x["rows"]) for x in p["lists"]], [4, 4])


class Rows(unittest.TestCase):
    def test_h5_with_the_real_hb_output(self):
        r = AN.analyze_text("\n".join(NOISE) + "\n" + hb_console(3) + "\n", JOBS)
        self.assertEqual((r["row"], r["name"]), (5, "hb-ps-lists"))
        f = r["facts"]
        self.assertEqual(f["lists_after_hb_marker"], 3)
        self.assertEqual(f["lists_not_from_hb"], 0)
        self.assertEqual(f["last_list"]["round"], 3)
        self.assertEqual(f["last_list"]["kind"], "A")
        self.assertEqual(f["last_list"]["processes"], ["/sbin/launchd", "/usr/libexec/logd", "/usr/libexec/containermanagerd", "ps -A"])
        self.assertTrue(f["pid1_in_last_list"])
        self.assertEqual(f["self_starting_jobs_in_last_list"], ["com.apple.logd", "com.apple.containermanagerd"])      # powerd is not in it, the heartbeat job is excluded
        self.assertEqual((f["max_pid_first_list"], f["max_pid_last_list"]), (30, 30))
        self.assertIn("names: /sbin/launchd, /usr/libexec/logd", r["reason"])

    def test_console_after_logd_needs_logd_in_a_list(self):
        # hb's first rounds run before launchd exists (hb is started from rc): lists of those rounds name init, not launchd and logd, and prove nothing about the console after logd started
        early = "  PID TTY           TIME CMD\n    1 ??         0:00.11 /redwood/sbin/init\n   40 ??         0:00.01 /redwood/bin/hb\n   41 ??         0:00.00 ps -A"
        r = AN.analyze_text(hb_console(1, ps_a=early) + "\n", JOBS)
        self.assertEqual(r["row"], 5)
        self.assertFalse(r["facts"]["console_after_logd"])
        self.assertEqual((r["facts"]["rounds_with_logd"], r["facts"]["pid1_commands"]), ([], ["/redwood/sbin/init"]))
        self.assertIn("none, so every list may predate launchd", r["reason"])
        # round 1 early, rounds 2 and 3 after logd started: the proof is in rounds 2 and 3
        later = hb_console(3)
        text = hb_console(1, ps_a=early) + "\n" + later[later.index("SWEET hb: n=2 pid"):] + "\n"
        r = AN.analyze_text(text, JOBS)
        self.assertTrue(r["facts"]["console_after_logd"])
        self.assertEqual(r["facts"]["rounds_with_logd"], [2, 3])
        self.assertEqual(r["facts"]["pid1_commands"], ["/redwood/sbin/init", "/sbin/launchd"])
        self.assertIn("rounds [2, 3]", r["reason"])

    def test_console_after_logd_is_unknown_without_lists(self):
        self.assertIsNone(AN.analyze_text("SWEET hb: n=1 pid=40 ppid=1 up=0\n", JOBS)["facts"]["console_after_logd"])
        self.assertIsNone(AN.analyze_text("nothing\n", JOBS)["facts"]["console_after_logd"])

    def test_logd_helper_is_not_logd(self):
        helper = "  PID TTY           TIME CMD\n    1 ??         0:00.10 /sbin/launchd\n   17 ??         0:00.02 /usr/libexec/logd_helper"
        self.assertFalse(AN.analyze_text(hb_console(1, ps_a=helper) + "\n", JOBS)["facts"]["console_after_logd"])

    def test_h5_states_and_zombies_come_from_the_o_format_list(self):
        r = AN.analyze_text(hb_console(2) + "\n", JOBS)
        self.assertEqual(r["row"], 5)
        f = r["facts"]
        self.assertEqual(f["last_list"]["kind"], "O")
        self.assertEqual(f["states_in_last_list"], {"S": 2, "Z": 1, "R": 1})
        self.assertEqual(f["zombies_in_last_list"], [19])
        self.assertTrue(f["table"][0]["in_last_list"])
        self.assertFalse(f["table"][2]["in_last_list"])           # powerd is a zombie "(powerd)", not its program path

    def test_h5_counts_lists_that_do_not_come_from_hb(self):
        text = hb_console(1) + "\n" + LIST_A + "\n"
        r = AN.analyze_text(text, JOBS)
        self.assertEqual((r["row"], r["facts"]["lists_after_hb_marker"], r["facts"]["lists_not_from_hb"]), (5, 1, 1))

    def test_h3_rounds_without_a_list(self):
        text = "SWEET hb: start pid=40 ppid=1 period=10s rounds=60 ps_timeout=8s\nSWEET hb: n=1 pid=40 ppid=1 up=0\nSWEET hb: n=1 ps pid=41 status=32512 ms=3\n"
        r = AN.analyze_text(text, JOBS)
        self.assertEqual((r["row"], r["name"]), (3, "hb-rounds-no-list"))
        self.assertIn("no recognisable ps list", r["reason"])
        self.assertEqual(r["facts"]["ps_status"][0]["status"], 32512)

    def test_h3_when_the_only_lists_are_not_hbs(self):
        text = "SWEET hb: n=1 pid=40 ppid=1 up=0\n" + "x\n" * 6 + LIST_A + "\n"
        self.assertEqual(AN.analyze_text(text, JOBS)["row"], 3)

    def test_h2_start_only(self):
        r = AN.analyze_text("noise\nSWEET hb: start pid=40 ppid=1 period=10s rounds=60 ps_timeout=8s\n" + LIST_A + "\n", JOBS)
        self.assertEqual((r["row"], r["name"]), (2, "hb-start-only"))

    def test_h1_no_hb_line_even_with_ps_lists_and_launchd_noise(self):
        r = AN.analyze_text("\n".join(NOISE) + "\n" + LIST_A + "\n", JOBS)
        self.assertEqual((r["row"], r["name"]), (1, "no-hb-line"))
        self.assertEqual(r["facts"]["lists_not_from_hb"], 1)

    def test_h1_mentions_unrecognised_hb_lines(self):
        r = AN.analyze_text("SWEET hb: weird\n", JOBS)
        self.assertEqual(r["row"], 1)
        self.assertIn("1 unrecognised hb line", r["reason"])

    def test_the_highest_row_wins(self):
        self.assertEqual(AN.analyze_text(hb_console(1), JOBS)["row"], 5)
        self.assertEqual(AN.analyze_text("SWEET hb: n=1 pid=1 ppid=1 up=0\n", JOBS)["row"], 3)

    def test_launchd_console_lines_are_counted_as_a_fact(self):
        line = "com.apple.xpc.launchd|2026-11-12 18:10:00.123456 (system/com.apple.logd) <Notice>: xpcproxy spawned with pid 16"
        r = AN.analyze_text(line + "\n" + hb_console(1), JOBS)
        self.assertEqual(r["facts"]["launchd_console_lines"], 1)
        self.assertEqual(r["facts"]["launchd_labels"], ["com.apple.logd"])

    def test_hole_and_gap_numbers_are_carried(self):
        r = AN.analyze_text(hb_console(1), JOBS, hole_bytes=4896, gap_bytes=3072)
        self.assertEqual((r["facts"]["hole_bytes"], r["facts"]["gap_bytes"]), (4896, 3072))


class HostModelOutput(unittest.TestCase):
    """The producer is the real hb.c (host model), not a string written in this file."""

    def test_the_analyser_reads_what_hb_prints(self):
        with tempfile.TemporaryDirectory() as t:
            ps = Path(t) / "ps"
            ps.write_text('#!/bin/sh\nif [ "$1" = "-A" ]; then\n printf "  PID TTY           TIME CMD\\n    1 ??         0:00.10 /sbin/launchd\\n   16 ??         0:00.02 /usr/libexec/logd\\n"\n'
                          'else\n printf "  PID  PPID STAT COMM\\n    1     0 Ss   /sbin/launchd\\n   16     1 Ss   /usr/libexec/logd\\n"\nfi\n')
            ps.chmod(0o755)
            con = Path(t) / "console"
            con.write_text("")
            exe = Path(t) / "hb"
            r = subprocess.run(["cc", "-O2", "-DHOST_TEST", '-DCONSOLE_DEV="%s"' % con, '-DPS_PATH="%s"' % ps, "-DHB_ROUNDS=2", "-DHB_PERIOD_S=1", "-DHB_PS_TIMEOUT_S=2", "-o", str(exe), str(SRC)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(subprocess.run([str(exe)], timeout=30).returncode, 0)
            text = "\n".join(NOISE) + "\n" + con.read_text()
        res = AN.analyze_text(text, JOBS)
        self.assertEqual(res["row"], 5)
        f = res["facts"]
        self.assertEqual([m["n"] for m in f["marks"]], [1, 2])
        self.assertEqual([x["kind"] for x in f["lists"]], ["A", "O"])
        self.assertEqual(f["last_list"]["processes"], ["/sbin/launchd", "/usr/libexec/logd"])
        self.assertEqual(f["done"]["rounds"], 2)
        self.assertEqual(f["start"]["period"], 1)


@unittest.skipUnless(NAT098_TEXT.is_file() and JOBS_DIR.is_dir(), "NAT-098's kernel text is not present")
class RealNat098Text(unittest.TestCase):
    def test_nat098_had_no_hb_so_it_reads_h1_and_nat098s_job_lists_are_not_hbs(self):
        text = NAT098_TEXT.read_text(errors="replace")
        r = AN.analyze_text(text, AN.A89.read_jobs(JOBS_DIR))
        self.assertEqual((r["row"], r["name"]), (1, "no-hb-line"))
        self.assertEqual(r["facts"]["lists_after_hb_marker"], 0)
        self.assertEqual(r["facts"]["launchd_console_lines"], 0)            # NAT-098's reading: no launchd console-form line


class Main(unittest.TestCase):
    def test_out_must_not_exist(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "o.json"
            out.write_text("x")
            with self.assertRaisesRegex(SystemExit, "--out exists"):
                AN.main(["--archive", t, "--jobs-dir", t, "--out", str(out)])
            self.assertEqual(out.read_text(), "x")

    def test_rows_table_is_the_documented_one(self):
        self.assertEqual(AN.ROWS, {0: "no-kernel-text", 1: "no-hb-line", 2: "hb-start-only", 3: "hb-rounds-no-list", 5: "hb-ps-lists"})
        doc = AN.__doc__
        for k, v in AN.ROWS.items():
            self.assertRegex(doc, r"H%d %s" % (k, re.escape(v)))

    @unittest.skipUnless((ROOT / "artifacts/nat-098/run-001/archive").exists() and JOBS_DIR.is_dir(), "NAT-098's archive is not present")
    def test_the_whole_pipeline_on_the_real_nat098_archive_gives_h1_with_the_dump_facts(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "o.json"
            self.assertEqual(AN.main(["--archive", str(ROOT / "artifacts/nat-098/run-001/archive"), "--jobs-dir", str(JOBS_DIR), "--out", str(out)]), 0)
            r = json.loads(out.read_text())
        self.assertEqual((r["row"], r["name"]), (1, "no-hb-line"))
        self.assertTrue(r["dump"]["begin_inferred"])


class MutationGapCoverage(unittest.TestCase):
    @staticmethod
    def _write_boot(arch, boot_name, log_lines):
        fr = arch / "boots" / boot_name / "frames.jsonl"
        fr.parent.mkdir(parents=True, exist_ok=True)
        rows = [json.dumps({"frame": {"kind": "log", "dev_seq": idx, "text": ln}}) for idx, ln in enumerate(log_lines)]
        fr.write_text("\n".join(rows) + "\n")

    def test_parse_boundaries_status_reset_consecutive_lines_and_eof(self):
        # status line clears last_mark even if a list appears within 3 lines of the marker
        text = "SWEET hb: n=1 pid=40 ppid=1 up=0\nSWEET hb: n=1 ps pid=41 status=0 ms=5\nnoise\n" + LIST_A + "\n"
        self.assertIsNone(AN.parse(text)["lists"][0]["round"])

        # consecutive done / unknown / mark lines without blank separators, plus list ending at EOF (no trailing newline)
        consec = (
            "SWEET hb: start pid=40 ppid=1 period=10s rounds=60 ps_timeout=8s\n"
            "SWEET hb: done rounds=1\n"
            "SWEET hb: weird\n"
            "SWEET hb: n=2 pid=40 ppid=1 up=5\n"
            + LIST_A
        )
        p = AN.parse(consec)
        self.assertEqual(p["done"]["rounds"], 1)
        self.assertEqual(p["unknown_hb"], ["SWEET hb: weird"])
        self.assertEqual([m["n"] for m in p["marks"]], [2])
        self.assertEqual([(x["round"], x["cut"]) for x in p["lists"]], [(2, True)])

        # one blank line between list and hole marker vs noise after hole
        holed = LIST_A + "\n\n[... 10 bytes lost in transport ...]\nnoise\n"
        self.assertTrue(AN.parse(holed)["lists"][0]["cut"])

        # round association boundary: gap <= 3 (2 lines between marker and header) vs > 3 (3 lines)
        at_3 = "SWEET hb: n=1 pid=40 ppid=1 up=0\na\nb\n" + LIST_A + "\n"
        at_4 = "SWEET hb: n=1 pid=40 ppid=1 up=0\na\nb\nc\n" + LIST_A + "\n"
        self.assertEqual(AN.parse(at_3)["lists"][0]["round"], 1)
        self.assertIsNone(AN.parse(at_4)["lists"][0]["round"])

    def test_program_in_list_and_text_edge_facts(self):
        self.assertIs(AN.program_in_list("/a/b/c", [{"cmd": "c"}]), True)
        self.assertIs(AN.program_in_list("/a/b/c", [{"cmd": "/x/y/c -v"}]), True)
        self.assertIs(AN.program_in_list("/a/b/c", [{"cmd": "a/b"}]), False)
        self.assertIs(AN.program_in_list("/a/b/c", [{"cmd": "c_other"}]), False)

        r_def = AN.analyze_text(hb_console(1), JOBS)
        self.assertEqual((r_def["facts"]["hole_bytes"], r_def["facts"]["gap_bytes"]), (0, 0))

        orphan = "SWEET hb: n=1 ps pid=41 status=0 ms=5\nSWEET hb: done rounds=1\nSWEET hb: weird\n"
        r_h1 = AN.analyze_text(orphan, JOBS)
        self.assertEqual(r_h1["row"], 1)
        self.assertIn("3 unrecognised hb line(s)", r_h1["reason"])

        no_pid1 = "  PID TTY           TIME CMD\n   40 ??         0:00.01 /redwood/bin/hb"
        r_nopid1 = AN.analyze_text(hb_console(1, ps_a=no_pid1) + "\n", JOBS)
        self.assertIs(r_nopid1["facts"]["pid1_in_last_list"], False)
        self.assertEqual(r_nopid1["facts"]["pid1_commands"], [])
        self.assertIn("self-starting Apple jobs of the table in it: none", r_nopid1["reason"])

        mixed = hb_console(1) + "\nSWEET hb: n=2 pid=40 ppid=1 up=10\n" + no_pid1 + "\n"
        r_mixed = AN.analyze_text(mixed, JOBS)
        self.assertEqual(r_mixed["facts"]["pid1_commands"], ["/sbin/launchd"])

    def test_synthetic_archives_cover_h0_unreadable_conflicts_and_cli_output(self):
        import contextlib
        import io
        # H0: why=1 dump and empty why=2 dump do not qualify, plus unreadable orphan end record
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            arch = root / "arch0"
            jobs = root / "jobs"
            jobs.mkdir()
            self._write_boot(arch, "boot01-extra", [
                "KL begin why=1 len=5 head=5 tail=0 gap=0 x0=0x1",
                "KL 000000 hello",
                "KL end why=1 recs=1 bytes=5",
                "KL begin why=2 len=0 head=0 tail=0 gap=0 x0=0x1",
                "KL end why=2 recs=0 bytes=0",
            ])
            r0_clean = AN.analyze(arch, jobs)
            self.assertEqual((r0_clean["row"], r0_clean["name"]), (0, "no-kernel-text"))
            self.assertEqual(r0_clean["reason"], "no why=2 kernel-log dump with text in the archive")
            self.assertEqual(r0_clean["facts"]["unreadable"], [])

            self._write_boot(arch, "boot02-extra", [
                "KL 000000 x",
                "KL end why=9 recs=1 bytes=1",
            ])
            r0 = AN.analyze(arch, jobs)
            self.assertEqual((r0["row"], r0["name"]), (0, "no-kernel-text"))
            self.assertIn("no why=2 kernel-log dump with text in the archive", r0["reason"])
            self.assertIn("could not be inferred", r0["reason"])
            self.assertEqual(len(r0["facts"]["unreadable"]), 1)

            # Inferred-begin synthetic archive (no KL begin, no conflicts)
            arch_inf = root / "arch_inf"
            self._write_boot(arch_inf, "boot01-extra", [
                "KL 000000 a",
                "KL end why=2 recs=1 bytes=1",
            ])
            r_inf = AN.analyze(arch_inf, jobs)
            self.assertEqual(r_inf["row"], 1)
            self.assertTrue(r_inf["dump"]["begin_inferred"])
            self.assertIn("NAT-097 rules", r_inf["reason"])
            self.assertNotIn("WARNING", r_inf["reason"])

            # Single-byte valid why=2 dump tests len > 0 vs len > 1, plus conflict & non-inferred begin & unreadable
            arch1 = root / "arch1"
            self._write_boot(arch1, "boot01-extra", [
                "KL begin why=2 len=1 head=1 tail=0 gap=0 x0=0x1",
                "KL 000000 a",
                "KL end why=2 recs=1 bytes=1",
                "KL 000000 z",
                "KL end why=9 recs=1 bytes=1",
            ])
            self._write_boot(arch1, "boot02-extra", [
                "KL begin why=2 len=1 head=1 tail=0 gap=0 x0=0x1",
                "KL 000000 b",
                "KL end why=2 recs=1 bytes=1",
            ])
            out = root / "out.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = AN.main(["--archive", str(arch1), "--jobs-dir", str(jobs), "--out", str(out)])
            self.assertEqual(rc, 0)
            raw_json = out.read_text()
            self.assertTrue(raw_json.startswith('{\n "'))
            r1 = json.loads(raw_json)
            self.assertEqual((r1["row"], r1["name"]), (1, "no-hb-line"))
            self.assertEqual(r1["dump"]["boots"], ["boot01", "boot02"])
            self.assertFalse(r1["dump"]["begin_inferred"])
            self.assertNotIn("NAT-097 rules", r1["reason"])
            self.assertIn("WARNING: 1 offsets have different bytes in different boots", r1["reason"])
            self.assertEqual(len(r1["facts"]["unreadable"]), 1)
            self.assertIn("row H1 no-hb-line:", buf.getvalue())

    def test_cli_help_uses_first_docstring_line(self):
        r = subprocess.run([sys.executable, str(HERE / "analyze_nat102.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("NAT-102: the heartbeat ladder", r.stdout)
        self.assertNotIn("Why:", r.stdout)


if __name__ == "__main__":
    unittest.main()
