#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-089 tests. Inputs are hand-built (every number below is written out, none is taken from the module under test) plus, when the local artifact exists, the real
NAT-088 archive, whose literal facts were read by hand from its returned text before this analyser existed (20 skipped and 3 run boot tasks, kernel 193.752018 s)."""
import base64
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_nat089 as A  # noqa: E402
import kl_reader as K  # noqa: E402

REAL = HERE.parents[2] / "artifacts" / "nat-087" / "run-001" / "archive"
JOBS_DIR = HERE.parent / "nat-085"


def esc(raw):
    out = ""
    for b in raw:
        out += "\\\\" if b == 0x5c else "\\n" if b == 0x0a else "\\r" if b == 0x0d else chr(b) if 0x20 <= b < 0x7f else "\\x%02x" % b
    return out


def kl_lines(text, why=2, gap=0, drop=(), head=None):
    """The KL lines of a dump of `text` (bytes) sent as head only (len = len(text)), without the records at the offsets in `drop`."""
    n = len(text)
    lines = ["KL begin why=%d len=%d head=%d tail=0 gap=%d x0=0x0" % (why, n + gap, n, gap)]
    recs = 0
    for off in range(0, n, 96):
        if off in drop:
            continue
        lines.append("KL %06x %s" % (off, esc(text[off:off + 96])))
        recs += 1
    lines.append("KL end why=%d recs=%d bytes=%d" % (why, recs, n - sum(min(96, n - o) for o in drop)))
    return lines


def write_boot(root, name, lines, drops=()):
    d = Path(root) / "boots" / name
    d.mkdir(parents=True)
    rows = []
    for i, t in enumerate(lines):
        rows.append({"frame": {"kind": "log", "dev_seq": i, "seq": i, "text": t}})
    for at, lost in drops:
        rows.append({"frame": {"kind": "drop", "seq": 999, "reason": "ring-overrun",
                               "data_b64": base64.b64encode(json.dumps({"at_offset": at, "lost_bytes": lost, "reason": "ring-overrun"}).encode()).decode()}})
    (d / "frames.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def jobs(*specs):
    """specs: (label, program, self_start) -> job dicts; the heartbeat is com.nat085.ps."""
    return [dict(label=l, program=p, self_start=s, heartbeat=(l == "com.nat085.ps"), file=l + ".plist") for l, p, s in specs]


PS_HDR = "  PID TTY           TIME CMD\n"


def ps_list(*rows):
    return PS_HDR + "".join("%5d ??         0:00.01 %s\n" % (pid, cmd) for pid, cmd in rows)


def sysev(k, ev, what):
    return "[ %9.6f]: [System Event] [4959065237] [INFO] [Subsystem: launchd] [Event: %s] %s\n" % (k, ev, what)


def lline(ts, dom_label, msg, pid=None):
    who = "" if dom_label is None else "(%s%s) " % (dom_label, "" if pid is None else " [%d]" % pid)
    return "com.apple.xpc.launchd|1970-01-01 00:%02d:%09.6f %s<Notice>: %s\n" % (int(ts // 60), ts % 60, who, msg)


TASKS_OK = sysev(193.73, "commit-boot-mode", "Doing boot task") + sysev(193.735, "restore-datapartition", "Doing boot task") + sysev(193.737, "init-with-data-volume", "Doing boot task")
J3 = jobs(("com.apple.logd", "/usr/libexec/logd", True), ("com.apple.lsd", "/usr/libexec/lsd", False), ("com.apple.fseventsd", "/usr/libexec/fseventsd", True),
          ("com.nat085.ps", "/bin/ps", True))


class Reader(unittest.TestCase):
    def test_unescape_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            text = b"alpha\nbeta \\ gamma\r\n" + bytes(range(0x20, 0x7f)) * 3
            write_boot(t, "000001-a-dev", kl_lines(text))
            r = K.read_archive(t)
        d = r["dumps"][0]
        self.assertEqual(d["text"], text.decode())
        self.assertEqual((d["holes"], d["hole_bytes"], d["conflicts"]), ([], 0, []))

    def test_missing_records_become_exact_holes(self):
        text = bytes((i % 26) + 97 for i in range(500))
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(text, drop=(96, 192, 384)), drops=[(10, 5)])
            r = K.read_archive(t)
        d = r["dumps"][0]
        self.assertEqual(d["holes"], [(96, 288), (384, 480)])
        self.assertEqual(d["hole_bytes"], 288)
        self.assertEqual(r["drops"]["000001-a-dev"], [(10, 5, "ring-overrun")])
        want = text[:96].decode() + "\n[... 192 bytes lost in transport ...]\n" + text[288:384].decode() + "\n[... 96 bytes lost in transport ...]\n" + text[480:].decode()
        self.assertEqual(d["text"], want)

    def test_last_partial_chunk_is_a_hole_of_its_own_size(self):
        text = b"x" * 100          # chunks: (0, 96), (96, 4)
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(text, drop=(96,)))
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual((d["holes"], d["hole_bytes"]), ([(96, 100)], 4))

    def test_gap_marker_between_head_and_tail(self):
        text = b"h" * 96
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(text, gap=1234))
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual(d["text"], "h" * 96 + "\n[... 1234 bytes of the log were not sent ...]\n")

    def test_replay_boots_merge_and_fill_each_others_holes(self):
        text = bytes((i % 10) + 48 for i in range(300))
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(text, drop=(96,)))
            write_boot(t, "000002-b-dev", kl_lines(text, drop=(0,)))
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual(d["text"], text.decode())
        self.assertEqual(d["boots"], ["000001-a-dev", "000002-b-dev"])

    def test_conflicting_bytes_are_reported_and_the_first_kept(self):
        a, b = b"A" * 200, b"A" * 96 + b"B" * 96 + b"A" * 8
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(a))
            write_boot(t, "000002-b-dev", kl_lines(b))
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual(d["conflicts"], [96])
        self.assertEqual(d["text"], a.decode())

    def test_dumps_with_different_sizes_stay_separate(self):
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(b"a" * 100, why=1) + kl_lines(b"b" * 200, why=2))
            ds = K.read_archive(t)["dumps"]
        self.assertEqual([(d["why"], d["begin"]["len"]) for d in ds], [(1, 100), (2, 200)])

    def test_no_boots_directory_is_an_empty_result(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(K.read_archive(t), dict(dumps=[], boots=[], drops={}))

    def test_tail_range_is_counted_from_the_end(self):
        # why=2 with head 96 and tail 96 of len 300 (gap 108): expected chunks (204, 96) then (0, 96)
        lines = ["KL begin why=2 len=300 head=96 tail=96 gap=108 x0=0x0", "KL 0000cc " + "t" * 96, "KL 000000 " + "h" * 96, "KL end why=2 recs=2 bytes=192"]
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", lines)
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual(d["text"], "h" * 96 + "\n[... 108 bytes of the log were not sent ...]\n" + "t" * 96)
        self.assertEqual(d["holes"], [])


class Parts(unittest.TestCase):
    def test_boot_tasks_both_forms(self):
        text = sysev(1.5, "fsck", "Skipping boot-task") + sysev(2.5, "commit-boot-mode", "Doing boot task") + sysev(3.25, "boot", "Early boot complete. Continuing system boot.") \
            + "com.apple.xpc.launchd|1970-01-01 00:00:09.000000 (keybag) <Notice>: Doing boot task\n" + sysev(2.5, "commit-boot-mode", "Doing boot task")
        t = A.read_tasks(text)
        self.assertEqual((t["ran"], t["skipped"], t["early_boot_complete_kernel_s"]), (["commit-boot-mode", "keybag"], ["fsck"], 3.25))

    def test_launchd_lines(self):
        text = lline(224.5, "user/501/com.nat085.ps", "xpcproxy spawned with pid 12", 12) + lline(224.75, "system/com.apple.logd", "exited due to SIGSEGV | sent by exc handler[41]", 41) \
            + lline(225.0, "system/com.apple.logd", "service state: exited") + lline(226.0, None, "Early boot done")
        n, labels = A.read_launchd(text)
        self.assertEqual(n, 4)
        self.assertEqual(labels["com.nat085.ps"], dict(domains=["user/501"], spawns=[(224.5, 12)], exits=[], other=0))
        self.assertEqual(labels["com.apple.logd"]["exits"], [(224.75, "exited due to SIGSEGV | sent by exc handler[41]")])
        self.assertEqual(labels["com.apple.logd"]["other"], 1)

    def test_ps_lists_cut_detection(self):
        a = ps_list((1, "/sbin/launchd"), (6, "/bin/ps -A"))
        self.assertEqual(A.read_ps_lists(a + "something else\n")[0]["cut"], False)
        self.assertEqual(A.read_ps_lists(a + "\n[... 7 bytes lost in transport ...]\n")[0]["cut"], True)
        self.assertEqual(A.read_ps_lists(a.rstrip("\n"))[0]["cut"], True)
        two = A.read_ps_lists(a + "x\n" + ps_list((1, "/sbin/launchd")))
        self.assertEqual([len(l["rows"]) for l in two], [2, 1])

    def test_program_match_is_exact_on_the_first_word(self):
        pl = A.read_ps_lists(ps_list((7, "/usr/libexec/logd_helper"), (8, "/usr/libexec/logd daemon") ) + "x\n")[0]
        self.assertTrue(A.in_list("/usr/libexec/logd", pl))
        self.assertFalse(A.in_list("/usr/libexec/logd_h", pl))
        self.assertFalse(A.in_list("/usr/libexec/lo", pl))

    def test_read_jobs_flags(self):
        with tempfile.TemporaryDirectory() as t:
            for label, extra in (("a.runatload", {"RunAtLoad": True}), ("b.keepalive", {"KeepAlive": True}), ("c.keepdict", {"KeepAlive": {"PathState": {"/x": True}}}),
                                 ("d.demand", {}), ("com.nat085.ps", {"RunAtLoad": True, "KeepAlive": True})):
                (Path(t) / (label + ".plist")).write_bytes(plistlib.dumps(dict(Label=label, ProgramArguments=["/p/" + label, "x"], **extra)))
            js = A.read_jobs(t)
        self.assertEqual([(j["label"], j["program"], j["self_start"], j["heartbeat"]) for j in js],
                         [("a.runatload", "/p/a.runatload", True, False), ("b.keepalive", "/p/b.keepalive", True, False), ("c.keepdict", "/p/c.keepdict", False, False),
                          ("com.nat085.ps", "/p/com.nat085.ps", True, True), ("d.demand", "/p/d.demand", False, False)])

    def test_disabled_jobs_do_not_start_by_themselves(self):
        flag = {"#IfFeatureFlagDisabled": "X/y", "#Then": True}
        with tempfile.TemporaryDirectory() as t:
            for label, extra in (("a.disabled", {"Disabled": True, "KeepAlive": True}), ("b.enabled", {"Disabled": False, "RunAtLoad": True}), ("c.flag", {"Disabled": flag, "RunAtLoad": True}),
                                 ("d.limit", {"RunAtLoad": True, "LimitLoadToSessionType": "System"}), ("e.nothing", {})):
                (Path(t) / (label + ".plist")).write_bytes(plistlib.dumps(dict(Label=label, ProgramArguments=["/p/" + label], **extra)))
            js = A.read_jobs(t)
        self.assertEqual([(j["label"], j["self_start"], j["disabled"], j["limit_session"]) for j in js],
                         [("a.disabled", False, True, None), ("b.enabled", True, False, None), ("c.flag", False, flag, None), ("d.limit", True, None, "System"), ("e.nothing", False, None, None)])

    def test_the_table_carries_disabled_and_the_session_limit(self):
        js = jobs(("com.apple.logd", "/usr/libexec/logd", True))
        js[0].update(disabled=True, limit_session="System")
        r = run("x\n", js)
        self.assertEqual((r["table"][0]["disabled"], r["table"][0]["limit_session"]), (True, "System"))
        r2 = run("x\n", jobs(("com.apple.logd", "/usr/libexec/logd", True)))           # a job dict without the two keys (older tables) reads as None
        self.assertEqual((r2["table"][0]["disabled"], r2["table"][0]["limit_session"]), (None, None))

    STAGE_TREE = HERE.parents[1].parent / "artifacts" / "nat-089" / "pid1-stageA" / "root" / "LaunchDaemons"

    @unittest.skipUnless(STAGE_TREE.is_dir(), "the Stage A tree is a local artifact")
    def test_the_stage_a_tree_has_seven_self_starting_apple_jobs_not_eight(self):
        js = A.read_jobs(self.STAGE_TREE)
        self.assertEqual(len(js), 20)
        self.assertEqual(sorted(j["label"] for j in js if j["self_start"] and not j["heartbeat"]),
                         ["com.apple.containermanagerd", "com.apple.distnoted.xpc.daemon", "com.apple.fseventsd", "com.apple.logd", "com.apple.mobile.usermanagerd", "com.apple.powerd",
                          "com.apple.runningboardd"])
        sl = [j for j in js if j["label"] == "com.apple.syslogd"][0]
        self.assertEqual((sl["disabled"], sl["self_start"]), (True, False))                  # the stock plist says Disabled: true
        self.assertEqual(len([j for j in js if j["limit_session"] is not None]), 8)       # cfprefsd.system, containermanagerd.system, diagnosticd, distnoted (a flag conditional), fseventsd, logd, logd_helper, notifyd

    def test_real_heartbeat_plist(self):
        js = A.read_jobs(JOBS_DIR)
        self.assertEqual([(j["label"], j["program"], j["self_start"], j["heartbeat"]) for j in js], [("com.nat085.ps", "/bin/ps", True, True)])


def run(text, js=J3, hole=0, gap=0):
    return A.analyze_text(text, js, hole_bytes=hole, gap_bytes=gap)


LOGD = lline(210.0, "system/com.apple.logd", "xpcproxy spawned with pid 20", 20)
FSE = lline(210.5, "system/com.apple.fseventsd", "xpcproxy spawned with pid 21", 21)
HB = lline(211.0, "user/501/com.nat085.ps", "xpcproxy spawned with pid 22", 22)
ALL_ALIVE = ps_list((1, "/sbin/launchd.darwin"), (20, "/usr/libexec/logd"), (21, "/usr/libexec/fseventsd"), (22, "/bin/ps -A")) + "end\n"


class Rows(unittest.TestCase):
    def test_a1_all_self_starting_alive(self):
        r = run(TASKS_OK + LOGD + FSE + HB + ALL_ALIVE)
        self.assertEqual((r["row"], r["name"]), (1, "base-daemons-alive"))
        self.assertEqual(r["reason"], "all 2 self-starting jobs are in the last complete ps list; alive in total: 2")
        self.assertEqual([(t["label"], t["spawns"], t["alive_in_last_list"]) for t in r["table"]],
                         [("com.apple.logd", 1, True), ("com.apple.lsd", 0, False), ("com.apple.fseventsd", 1, True), ("com.nat085.ps", 1, True)])

    def test_a1_on_demand_job_alive_too(self):
        r = run(TASKS_OK + LOGD + FSE + HB + ps_list((20, "/usr/libexec/logd"), (21, "/usr/libexec/fseventsd"), (23, "/usr/libexec/lsd")) + "end\n")
        self.assertEqual((r["row"], r["facts"]["alive"]), (1, ["com.apple.logd", "com.apple.lsd", "com.apple.fseventsd"]))

    def test_a2_some_alive_names_the_missing(self):
        r = run(TASKS_OK + LOGD + FSE + HB + lline(215.0, "system/com.apple.fseventsd", "exited due to SIGABRT", 21) + ps_list((20, "/usr/libexec/logd")) + "end\n")
        self.assertEqual(r["row"], 2)
        self.assertEqual(r["reason"], "alive 1 of 2 self-starting jobs; not in the last list: ['com.apple.fseventsd']")
        t = {x["label"]: x for x in r["table"]}
        self.assertEqual(t["com.apple.fseventsd"]["exits"], [dict(clock=215.0, text="exited due to SIGABRT")])

    def test_a3_all_died(self):
        r = run(TASKS_OK + LOGD + FSE + ps_list((1, "/sbin/launchd.darwin"), (30, "/bin/ps -A")) + "end\n")
        self.assertEqual(r["row"], 3)
        self.assertEqual(r["reason"], "2 Apple label(s) spawned, none of the 19 programs is in the last complete ps list")

    def test_a4_nothing_spawned_only_without_holes(self):
        text = TASKS_OK + HB + ps_list((1, "/sbin/launchd.darwin"), (22, "/bin/ps -A")) + "end\n"
        self.assertEqual(run(text)["row"], 4)
        r = run(text, hole=96)
        self.assertEqual(r["row"], 8)
        self.assertEqual(r["reason"], "no `xpcproxy spawned` line for an Apple label, but 96 bytes are holes and 0 are the announced gap: spawning is not excluded")
        self.assertEqual(run(text, gap=1)["row"], 8)

    def test_a5_control_failed(self):
        extra = sysev(193.8, "keybag", "Doing boot task")
        r = run(TASKS_OK + extra + LOGD + FSE + HB + ALL_ALIVE)
        self.assertEqual(r["row"], 5)
        self.assertEqual(r["reason"], "boot tasks that ran: ['commit-boot-mode', 'restore-datapartition', 'init-with-data-volume', 'keybag'] (NAT-088: exactly "
                                      "['commit-boot-mode', 'init-with-data-volume', 'restore-datapartition'])")
        two = sysev(193.73, "commit-boot-mode", "Doing boot task") + sysev(193.74, "restore-datapartition", "Doing boot task")
        self.assertEqual(run(two + LOGD + FSE + HB + ALL_ALIVE)["row"], 5)

    def test_missing_task_lines_are_not_a_control_failure(self):
        self.assertEqual(run(LOGD + FSE + HB + ALL_ALIVE)["row"], 1)

    def test_a6_panic_beats_alive(self):
        text = TASKS_OK + LOGD + FSE + HB + ALL_ALIVE + "panic(cpu 0 caller 0xfffffff0123): zalloc: out of memory\n"
        r = run(text)
        self.assertEqual((r["row"], r["reason"]), (6, "kernel panic: zalloc: out of memory"))
        self.assertEqual(run(TASKS_OK + LOGD + ALL_ALIVE + "panic_trace: PE_arm_debug_enable_trace exit\n")["row"], 1)

    def test_a7_pid1_exit_beats_panic(self):
        text = TASKS_OK + LOGD + FSE + HB + ALL_ALIVE + "initproc exited -- no exit reason available -- (signal 9, exit status 0)\npanic(cpu 0 caller 0xfffffff0123): x\n"
        r = run(text)
        self.assertEqual((r["row"], r["facts"]["pid1_exit"]), (7, dict(how="exited", signal=9, status=0)))
        r2 = run(TASKS_OK + LOGD + ALL_ALIVE + "pid 1 exited -- no exit reason available -- (signal 0, exit 1)\n")
        self.assertEqual((r2["row"], r2["facts"]["pid1_exit"]), (7, dict(pid=1, signal=0, status=1)))

    def test_a8_cases(self):
        self.assertEqual(run("nothing from launchd here\n")["reason"], "no launchd line in the returned text")
        r = run(TASKS_OK + LOGD + FSE + HB + ps_list((1, "/sbin/launchd.darwin"), (20, "/usr/libexec/logd")))
        self.assertEqual((r["row"], r["facts"]["last_list_cut"], r["facts"]["last_list_rows"]), (8, True, 2))
        r = run(TASKS_OK + LOGD + FSE + HB)
        self.assertEqual((r["row"], r["facts"]["ps_lists"]), (8, 0))
        self.assertEqual(r["reason"], "no complete `ps -A` list in the text (0 lists, last absent): the alive set is not established")

    def test_last_list_decides_not_the_first(self):
        text = TASKS_OK + LOGD + FSE + HB + ALL_ALIVE + ps_list((1, "/sbin/launchd.darwin")) + "end\n"
        self.assertEqual(run(text)["row"], 3)


class ReaderEdges(unittest.TestCase):
    def test_frames_file_edges(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "f.jsonl"
            rows = [{"frame": {"kind": "log", "dev_seq": 5, "text": "five"}}, {"frame": {"kind": "stage", "dev_seq": 1, "text": "KL stage"}},
                    {"frame": {"kind": "log", "text": "no dev_seq"}}, {"frame": {"kind": "log", "dev_seq": 2, "text": None}},
                    {"frame": {"kind": "log", "dev_seq": 3, "text": "three"}}]
            d.write_text("\n\n".join(json.dumps(r) for r in rows) + "\n  \n")
            self.assertEqual(K.boot_lines(d), ["three", "five"])
            self.assertEqual(K.boot_drops(d), [])

    def test_blank_lines_in_a_drop_file(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "f.jsonl"
            drop = {"frame": {"kind": "drop", "reason": "ring-overrun", "data_b64": base64.b64encode(json.dumps({"at_offset": 7, "lost_bytes": 9}).encode()).decode()}}
            d.write_text("\n" + json.dumps(drop) + "\n\n")
            self.assertEqual(K.boot_drops(d), [(7, 9, "ring-overrun")])

    def test_directory_without_frames_is_skipped_and_boots_are_listed(self):
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(b"z" * 10))
            (Path(t) / "boots" / "000002-empty").mkdir()
            r = K.read_archive(t)
        self.assertEqual(r["boots"], ["000001-a-dev"])
        self.assertEqual(list(r["drops"]), ["000001-a-dev"])

    def test_refused_dump_is_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", ["KL refused why=2 x0=0x1 x1=0x2"] + kl_lines(b"q" * 10))
            ds = K.read_archive(t)["dumps"]
        self.assertEqual([d["text"] for d in ds], ["q" * 10])

    def test_conflict_listed_once_over_three_boots(self):
        a, b, c = b"A" * 200, b"A" * 96 + b"B" * 96 + b"A" * 8, b"A" * 96 + b"C" * 96 + b"A" * 8
        with tempfile.TemporaryDirectory() as t:
            for n, x in (("000001-a-dev", a), ("000002-b-dev", b), ("000003-c-dev", c)):
                write_boot(t, n, kl_lines(x))
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual(d["conflicts"], [96])

    def test_problems_are_listed_once_over_replays(self):
        text = b"p" * 300
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(text, drop=(96,)))
            one = K.read_archive(t)["dumps"][0]["problems"]
            write_boot(t, "000002-b-dev", kl_lines(text, drop=(96,)))
            two = K.read_archive(t)["dumps"][0]["problems"]
        self.assertIn("the records do not cover the announced ranges: 3 received, 4 expected", one)
        self.assertEqual(one, two)
        self.assertEqual(len(set(two)), len(two))

    def test_holes_merge_only_with_the_hole_just_before(self):
        text = b"m" * 500        # chunks at 0, 96, 192, 288, 384
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", kl_lines(text, drop=(0, 192, 288)))
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual(d["holes"], [(0, 96), (192, 384)])

    def test_record_off_the_grid_is_reported_as_extra(self):
        lines = ["KL begin why=2 len=96 head=96 tail=0 gap=0 x0=0x0", "KL 000000 " + "e" * 96, "KL 000010 stray", "KL end why=2 recs=2 bytes=101"]
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", lines)
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual((d["extra_offsets"], d["holes"]), ([16], []))

    def test_dev_seq_order_not_file_order(self):
        text = b"o" * 192
        lines = kl_lines(text)
        with tempfile.TemporaryDirectory() as t:
            write_boot(t, "000001-a-dev", lines)
            f = Path(t) / "boots" / "000001-a-dev" / "frames.jsonl"
            f.write_text("\n".join(reversed(f.read_text().splitlines())) + "\n")
            d = K.read_archive(t)["dumps"][0]
        self.assertEqual((d["text"], d["closed"]), ("o" * 192, True))


class PartsEdges(unittest.TestCase):
    def test_launchd_clock_hours_and_minutes(self):
        self.assertEqual(A.launchd_clock("1970-01-01 01:02:03.500000"), 3723.5)
        self.assertEqual(A.launchd_clock("1970-01-01 00:03:44.159344"), 224.159344)

    def test_first_early_boot_complete_wins(self):
        text = sysev(5.5, "boot", "Early boot complete. Continuing system boot.") + sysev(9.5, "boot", "Early boot complete. Continuing system boot.")
        self.assertEqual(A.read_tasks(text)["early_boot_complete_kernel_s"], 5.5)

    def test_console_task_listed_once(self):
        line = "com.apple.xpc.launchd|1970-01-01 00:00:09.000000 (keybag) <Notice>: Doing boot task\n"
        self.assertEqual(A.read_tasks(line + line)["ran"], ["keybag"])

    def test_labelless_lines_make_no_label_and_domains_are_listed_once(self):
        text = lline(1.0, None, "no label") + lline(2.0, "system/com.apple.logd", "xpcproxy spawned with pid 3", 3) + lline(3.0, "system/com.apple.logd", "xpcproxy spawned with pid 4", 4)
        n, labels = A.read_launchd(text)
        self.assertEqual((n, sorted(labels)), (3, ["com.apple.logd"]))
        self.assertEqual((labels["com.apple.logd"]["domains"], labels["com.apple.logd"]["spawns"]), (["system"], [(2.0, 3), (3.0, 4)]))

    def test_ps_row_fields(self):
        rows = A.read_ps_lists("  PID TTY           TIME CMD\n   12 ttys0     1:02.03 /usr/libexec/logd -x\nend\n")[0]["rows"]
        self.assertEqual(rows, [(12, "ttys0", "1:02.03", "/usr/libexec/logd -x")])

    def test_hole_marker_after_one_empty_line_still_cuts(self):
        a = ps_list((1, "/sbin/launchd"))
        self.assertTrue(A.read_ps_lists(a + "\n[... 7 bytes lost in transport ...]\nother\n")[0]["cut"])
        self.assertTrue(A.read_ps_lists(a + "[... 7 bytes lost in transport ...]\nother\n")[0]["cut"])
        self.assertFalse(A.read_ps_lists(a + "\nother\n")[0]["cut"])

    def test_defaults_mean_no_holes_and_no_gap(self):
        r = A.analyze_text(TASKS_OK + HB + ps_list((1, "/sbin/launchd.darwin"), (22, "/bin/ps -A")) + "end\n", J3)
        self.assertEqual((r["row"], r["facts"]["hole_bytes"], r["facts"]["gap_bytes"]), (4, 0, 0))

    def test_panic_text_is_the_message(self):
        r = run(TASKS_OK + LOGD + ALL_ALIVE + "panic(cpu 1 caller 0xfffffff00abc): kernel trap\n")
        self.assertEqual(r["facts"]["panic"], "kernel trap")

    def test_a2_counts_alive_self_starting_among_three(self):
        js = jobs(("com.apple.logd", "/usr/libexec/logd", True), ("com.apple.fseventsd", "/usr/libexec/fseventsd", True), ("com.apple.runningboardd", "/usr/libexec/runningboardd", True),
                  ("com.nat085.ps", "/bin/ps", True))
        text = LOGD + FSE + HB + ps_list((20, "/usr/libexec/logd"), (21, "/usr/libexec/fseventsd")) + "end\n"
        r = run(text, js)
        self.assertEqual((r["row"], r["reason"]), (2, "alive 2 of 3 self-starting jobs; not in the last list: ['com.apple.runningboardd']"))

    def test_label_not_seen_has_zero_spawns_and_no_domain(self):
        r = run(TASKS_OK + LOGD + FSE + HB + ALL_ALIVE)
        t = {x["label"]: x for x in r["table"]}["com.apple.lsd"]
        self.assertEqual((t["spawns"], t["first_spawn_clock"], t["domains"], t["exits"]), (0, None, [], []))


class ArchiveLevel(unittest.TestCase):
    def archive(self, t, *boots):
        for name, lines in boots:
            write_boot(t, name, lines)
        return t

    def test_no_final_dump(self):
        with tempfile.TemporaryDirectory() as t:
            r = A.analyze(self.archive(t, ("000001-a-dev", kl_lines(b"x" * 100, why=1))), JOBS_DIR)
        self.assertEqual((r["row"], r["name"], r["reason"], r["facts"], r["table"]), (8, "not-evaluated", "no why=2 kernel-log dump with text in the archive",
                                                                                      dict(boots=1, dumps=1), []))

    def test_empty_archive_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as t:
            r = A.analyze(t, JOBS_DIR)
        self.assertEqual((r["row"], r["facts"]), (8, dict(boots=0, dumps=0)))

    def test_final_dump_of_length_zero_is_not_the_one(self):
        text = (TASKS_OK + lline(224.0, "user/501/com.nat085.ps", "xpcproxy spawned with pid 9", 9) + ps_list((1, "/sbin/launchd.darwin"), (9, "/bin/ps -A")) + "end\n").encode()
        with tempfile.TemporaryDirectory() as t:
            r = A.analyze(self.archive(t, ("000001-abcdefg-dev", kl_lines(b"", why=2) + kl_lines(text, why=2))), JOBS_DIR)
        self.assertEqual(r["dump"]["boots"], ["000001"])
        self.assertEqual(r["facts"]["launchd_lines"], 1)
        self.assertEqual(r["dump"]["begin"]["len"], len(text))

    def test_only_a_length_zero_final_dump_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as t:
            r = A.analyze(self.archive(t, ("000001-a-dev", kl_lines(b"", why=2))), JOBS_DIR)
        self.assertEqual((r["row"], r["facts"]), (8, dict(boots=1, dumps=1)))

    def test_a_final_dump_of_one_byte_is_the_one(self):
        with tempfile.TemporaryDirectory() as t:
            r = A.analyze(self.archive(t, ("000001-a-dev", kl_lines(b"x", why=2))), JOBS_DIR)
        self.assertNotEqual(r["reason"], "no why=2 kernel-log dump with text in the archive")   # the one-byte dump was chosen and read; its text has no launchd lines
        self.assertEqual((r["dump"]["begin"]["len"], r["dump"]["records"]), (1, 1))

    def test_command_line_runs_isolated_and_writes_indented_json(self):
        import os
        import subprocess
        script = str(HERE / "analyze_nat089.py")
        env = {"COLUMNS": "300", "PATH": os.environ.get("PATH", "")}
        h = subprocess.run([sys.executable, "-B", "-I", script, "--help"], capture_output=True, text=True, env=env)   # -I: the script directory is not on sys.path
        self.assertEqual(h.returncode, 0, h.stderr)
        self.assertIn("NAT-089: analyser for the next native run, Stage A", h.stdout)
        text = (TASKS_OK + lline(224.0, "user/501/com.nat085.ps", "xpcproxy spawned with pid 9", 9) + ps_list((1, "/sbin/launchd.darwin"), (9, "/bin/ps -A")) + "end\n").encode()
        with tempfile.TemporaryDirectory() as t:
            self.archive(t, ("000001-a-dev", kl_lines(text)))
            out = Path(t) / "analysis.json"
            c = subprocess.run([sys.executable, "-B", "-I", script, "--archive", t, "--jobs-dir", str(JOBS_DIR), "--out", str(out)], capture_output=True, text=True, env=env)
            raw = out.read_text()
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertTrue(raw.startswith('{\n "row": 4,\n "name": "no-daemon-spawned",\n'), raw[:80])

    def test_conflict_warning_in_reason(self):
        ok = (TASKS_OK + ps_list((1, "/sbin/launchd.darwin")) + lline(224.0, "user/501/com.nat085.ps", "xpcproxy spawned with pid 9", 9) + "z" * 100).encode()
        other = ok[:96] + b"#" * 96 + ok[192:]
        with tempfile.TemporaryDirectory() as t:
            r = A.analyze(self.archive(t, ("000001-a-dev", kl_lines(ok)), ("000002-b-dev", kl_lines(other))), JOBS_DIR)
        self.assertTrue(r["reason"].endswith("; WARNING: 1 offsets have different bytes in different boots"), r["reason"])
        self.assertEqual(r["dump"]["conflicts"], [96])
        with tempfile.TemporaryDirectory() as t:
            r2 = A.analyze(self.archive(t, ("000001-a-dev", kl_lines(ok))), JOBS_DIR)
        self.assertNotIn("WARNING", r2["reason"])

    def test_main_writes_the_analysis_and_prints_the_row(self):
        import contextlib
        import io
        text = (TASKS_OK + lline(224.0, "user/501/com.nat085.ps", "xpcproxy spawned with pid 9", 9) + ps_list((1, "/sbin/launchd.darwin"), (9, "/bin/ps -A")) + "end\n").encode()
        with tempfile.TemporaryDirectory() as t:
            self.archive(t, ("000001-a-dev", kl_lines(text)))
            out = Path(t) / "analysis.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = A.main(["--archive", t, "--jobs-dir", str(JOBS_DIR), "--out", str(out)])
            raw = out.read_text()
            d = json.loads(raw)
        self.assertEqual(rc, 0)
        self.assertEqual(d["row"], 4)       # the jobs directory holds only the heartbeat: no Apple label spawned
        self.assertEqual(buf.getvalue().splitlines()[0], "row A4 no-daemon-spawned: launchd lines read, a complete last ps list, no Apple label spawned")
        self.assertEqual(buf.getvalue().splitlines()[1], "  %-48s spawns 1 alive True exits 0" % "com.nat085.ps")
        self.assertTrue(raw.endswith("}\n"))
        self.assertTrue(raw.startswith('{\n "row": 4,\n "name": "no-daemon-spawned",\n'), raw[:80])

    def test_main_requires_all_arguments(self):
        for argv in ([], ["--archive", "x"], ["--archive", "x", "--jobs-dir", "y"], ["--jobs-dir", "y", "--out", "z"], ["--archive", "x", "--out", "z"]):
            with self.assertRaises(SystemExit) as cm:
                A.main(argv)
            self.assertEqual(cm.exception.code, 2)


@unittest.skipUnless(REAL.is_dir(), "the NAT-088 archive is a local artifact")
class RealArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = A.analyze(REAL, JOBS_DIR)

    def test_dump_and_holes(self):
        d = self.r["dump"]
        self.assertEqual((d["records"], d["holes"], d["conflicts"], d["closed"]), (399, [(33441, 36225)], [], True))
        self.assertEqual((d["begin"]["len"], d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"]), (57665, 8192, 32768, 16705))

    def test_boot_tasks_and_heartbeat(self):
        f = self.r["facts"]
        self.assertEqual((sorted(f["boot_tasks"]["ran"]), len(f["boot_tasks"]["skipped"]), f["boot_tasks"]["early_boot_complete_kernel_s"]),
                         (["commit-boot-mode", "init-with-data-volume", "restore-datapartition"], 20, 193.752018))
        t = self.r["table"][0]
        self.assertEqual((t["label"], t["spawns"], t["first_spawn_clock"], t["alive_in_last_list"], len(t["exits"])), ("com.nat085.ps", 3, 224.159344, True, 2))
        self.assertEqual((f["ps_lists"], f["last_list_rows"], f["hole_bytes"], f["gap_bytes"], f["panic"], f["pid1_exit"]), (3, 2, 2784, 16705, None, None))

    def test_row_is_not_evaluated_because_no_apple_job_was_in_that_image(self):
        self.assertEqual(self.r["row"], 8)


if __name__ == "__main__":
    unittest.main(verbosity=1)
