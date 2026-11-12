#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102: the real NAT-101 `hb` Mach-O (the file inside the small root of the heartbeat image) run under Unicorn with the multi-process fake Darwin kernel of hb_vm.py.
Evidence kind: host-test (a model of the Darwin ABI; it is not the payload kernel and shows nothing about the phone).

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-102/test_hb_vm.py      (opens no device)

What it adds to NAT-101's tests: those run the control flow of hb.c through a libc model and look at the syscall instructions of the Mach-O statically. Here the arm64 machine code that
will run on the phone is executed: the svc register convention and the carry/errno handling, the fork child flag in x1, the descriptor setup of the child (dup2 before execve), the argv and
envp arrays built on the stack, the timeval layout of select and gettimeofday, the wait status, the poll loop and the SIGKILL path, and the failure paths. The fake kernel is written after
the Darwin ABI as the project's XNU source gives it; where the phone's kernel differs, the native run is the test. Skipped when the hb file or unicorn is not present."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HB = ROOT / "artifacts/nat-101/pid1-hb/root/bin/hb"
HB_SHA256 = "1819a4a89ec06403fa21df2facd73ff9723c2debd03c2ec6df9d7f6717103163"

try:
    spec = importlib.util.spec_from_file_location("nat102_hb_vm", HERE / "hb_vm.py")
    M = importlib.util.module_from_spec(spec)
    sys.modules["nat102_hb_vm"] = M
    spec.loader.exec_module(M)
except ImportError:
    M = None


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


JOBS = [dict(label="com.apple.logd", program="/usr/libexec/logd", self_start=True),
        dict(label="com.apple.containermanagerd", program="/usr/libexec/containermanagerd", self_start=True),
        dict(label="com.apple.powerd", program="/System/Library/CoreServices/powerd.bundle/powerd", self_start=True)]
MARK = re.compile(r"^SWEET hb: n=(\d+) pid=(\d+) ppid=(\d+) up=(\d+)$", re.M)
STAT = re.compile(r"^SWEET hb: n=(\d+) ps pid=(-?\d+) status=(-?\d+) ms=(\d+)( timeout-killed)?$", re.M)


def run(**kw):
    macho = HB.read_bytes()
    k = M.Kernel(**kw)
    M.VM(macho, k).run()
    return k


@unittest.skipUnless(M is not None and HB.is_file(), "unicorn or the hb file is not present")
class Normal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        cls.sha = hashlib.sha256(HB.read_bytes()).hexdigest()
        cls.runs = {s: run(schedule=s) for s in ("fork", "wait", "select")}

    def test_the_file_is_the_pinned_one(self):
        self.assertEqual(self.sha, HB_SHA256)

    def test_it_finishes_with_status_0_and_the_documented_lines_under_every_scheduler_policy(self):
        for sched, k in self.runs.items():
            t = k.console_text()
            self.assertEqual(k.exit_code, 0, sched)
            self.assertTrue(t.startswith("\nSWEET hb: start pid=40 ppid=1 period=10s rounds=60 ps_timeout=8s\n"), (sched, t[:120]))
            self.assertTrue(t.endswith("SWEET hb: done rounds=60\n"), sched)
            marks = MARK.findall(t)
            self.assertEqual([int(m[0]) for m in marks], list(range(1, 61)), sched)
            self.assertTrue(all((m[1], m[2]) == ("40", "1") for m in marks), sched)
            for n, _, _, up in marks:
                n, up = int(n), int(up)
                self.assertTrue(10 * (n - 1) <= up <= 11 * (n - 1) + 1, (sched, n, up))
            stats = STAT.findall(t)
            self.assertEqual([int(s[0]) for s in stats], list(range(1, 61)), sched)
            self.assertEqual([int(s[1]) for s in stats], list(range(41, 101)), sched)          # the child pids the kernel handed out
            self.assertTrue(all(s[2] == "0" and not s[4] and 100 <= int(s[3]) <= 400 for s in stats), sched)

    def test_the_text_does_not_depend_on_when_the_child_runs(self):
        def shape(k):
            return re.sub(r"(ms|up)=\d+", r"\1=#", k.console_text())
        want = shape(self.runs["wait"])
        for sched in ("fork", "select"):
            self.assertEqual(shape(self.runs[sched]), want, sched)

    def test_the_two_ps_argv_shapes_alternate_and_the_environment_and_path_are_exact(self):
        for sched, k in self.runs.items():
            self.assertEqual(len(k.execs), 60, sched)
            for i, (path, argv, envp) in enumerate(k.execs, 1):
                self.assertEqual(path, b"/bin/ps", sched)
                self.assertEqual(argv, [b"ps", b"-A"] if i % 2 else [b"ps", b"-Ao", b"pid,ppid,stat,comm"], (sched, i))
                self.assertEqual(envp, [b"PATH=/bin:/sbin:/usr/bin:/usr/sbin"], sched)

    def test_the_child_points_descriptors_1_and_2_at_the_console_before_it_execs(self):
        k = self.runs["wait"]
        for pid in range(41, 101):
            names = [(c[1], c[2][:2]) for c in k.calls if c[0] == pid]
            self.assertEqual([n for n, _ in names], ["dup2", "dup2", "execve"], pid)
            self.assertEqual([a for n, a in names[:2]], [(0, 1), (0, 2)], pid)            # the first descriptor handed out is 0

    def test_the_same_with_the_console_on_descriptor_3(self):
        k = run(first_fd=3)
        self.assertEqual(k.exit_code, 0)
        self.assertEqual(MARK.findall(k.console_text())[0][:3], ("1", "40", "1"))
        self.assertEqual([c[2][:2] for c in k.calls if c[0] == 41 and c[1] == "dup2"], [(3, 1), (3, 2)])

    def test_hb_writes_one_line_per_write_and_only_its_own_lines(self):
        k = self.runs["wait"]
        own = [w for w in k.writes if w[0] == 40]
        self.assertEqual(len(own), 1 + 60 * 2 + 1)                                           # start, 60 x (marker, status), done
        for _, fd, data in own:
            self.assertEqual(fd, 0)
            self.assertEqual(data.count(b"\n"), 2 if data.startswith(b"\nSWEET hb: start") else 1, data)
            self.assertTrue(data.endswith(b"\n"), data)
            self.assertIn(b"SWEET hb:", data)
        self.assertEqual({w[0] for w in k.writes} - {40}, set())                             # the fake ps writes through the kernel model, not through write()

    def test_the_sleeps_are_selects_with_no_descriptors_and_the_exact_timevals(self):
        k = self.runs["wait"]
        self.assertEqual(sum(1 for s in k.selects if s[4:] == (10, 0)), 60)
        self.assertEqual(sum(1 for s in k.selects if s[4:] == (0, 100000)), 120)             # a 120 ms ps is found waitable on the third poll: two sleeps per round
        self.assertEqual(len(k.selects), 180)
        self.assertTrue(all(s[:4] == (0, 0, 0, 0) for s in k.selects))

    def test_the_number_of_polls_follows_the_time_the_child_takes(self):
        for us, polls in ((0, 0), (50000, 1), (250000, 3), (780000, 8)):
            k = run(schedule="fork", plan=lambda n, argv, us=us: dict(mode="ok", us=us))
            self.assertEqual(sum(1 for s in k.selects if s[4:] == (0, 100000)), polls * 60, us)

    def test_only_the_twelve_documented_system_calls_are_issued_and_every_child_is_reaped(self):
        for sched, k in self.runs.items():
            self.assertEqual({c[1] for c in k.calls}, {"exit", "fork", "write", "open", "wait4", "getpid", "kill", "getppid", "execve", "dup2", "select", "gettimeofday"} - {"kill"}, sched)
            self.assertEqual(k.procs[0].children, [], sched)
            self.assertEqual(k.kills, [], sched)


@unittest.skipUnless(M is not None and HB.is_file(), "unicorn or the hb file is not present")
class Failures(unittest.TestCase):
    def test_a_ps_that_hangs_is_killed_after_eight_seconds_and_the_loop_goes_on(self):
        k = run(plan=lambda n, argv: dict(mode="hang") if n == 3 else dict(mode="ok", us=120000))
        t = k.console_text()
        stats = {int(s[0]): s for s in STAT.findall(t)}
        self.assertEqual(stats[3][1:3], ("43", "9"))                                          # the wait status of a SIGKILLed child is the signal number
        self.assertEqual(stats[3][4], " timeout-killed")
        self.assertTrue(8000 <= int(stats[3][3]) <= 8400, stats[3])
        self.assertEqual(k.kills, [(43, 9)])
        self.assertEqual(sum(1 for s in k.selects if s[4:] == (0, 100000)), 59 * 2 + 80)
        self.assertEqual([int(s[0]) for s in STAT.findall(t)], list(range(1, 61)))
        self.assertTrue(t.endswith("SWEET hb: done rounds=60\n"))
        self.assertEqual(k.exit_code, 0)
        self.assertEqual(k.procs[0].children, [])
        self.assertEqual(sum(1 for s in stats.values() if s[4]), 1)

    def test_a_ps_that_always_hangs_costs_eight_seconds_a_round_and_never_leaves_a_child(self):
        k = run(plan=lambda n, argv: dict(mode="hang"))
        self.assertEqual(len(k.kills), 60)
        self.assertEqual(k.procs[0].children, [])
        self.assertEqual(k.exit_code, 0)
        self.assertTrue(abs((k.now_us - k.start_us) / 1e6 - 60 * 18.0) < 15, (k.now_us - k.start_us) / 1e6)

    def test_a_missing_ps_exits_127_and_the_status_says_so(self):
        k = run(ps_path=b"/bin/nonexistent")
        stats = STAT.findall(k.console_text())
        self.assertEqual(len(stats), 60)
        self.assertTrue(all(s[2] == "32512" and not s[4] for s in stats), stats[:2])          # 127 << 8
        self.assertEqual(k.exit_code, 0)

    def test_a_ps_that_dies_of_a_signal_is_reported_with_the_signal_number(self):
        k = run(plan=lambda n, argv: dict(mode="crash", us=50000) if n == 2 else dict(mode="ok", us=50000))
        stats = {int(s[0]): s for s in STAT.findall(k.console_text())}
        self.assertEqual(stats[2][2], "11")
        self.assertEqual(stats[1][2], "0")

    def test_a_failing_fork_prints_the_negated_errno_does_not_wait_and_the_loop_goes_on(self):
        k = run(fork_fail_rounds=(2, 3))
        stats = {int(s[0]): s for s in STAT.findall(k.console_text())}
        self.assertEqual(stats[2][1:], ("-35", "0", "0", ""))
        self.assertEqual(stats[3][1:], ("-35", "0", "0", ""))
        self.assertEqual(stats[4][1], "42")                                                  # the first two forks failed, so the third pid is handed to round 4
        self.assertEqual(sum(1 for c in k.calls if c[1] == "wait4" and c[0] == 40) > 0, True)
        self.assertEqual(k.exit_code, 0)

    def test_a_missing_console_exits_2_without_a_word_and_without_a_fork(self):
        k = run(console_ok=False)
        self.assertEqual((k.exit_code, k.console, k.forks), (2, [], 0))
        self.assertEqual([c[1] for c in k.calls], ["open", "exit"])

    def test_a_child_that_vanished_before_wait4_does_not_hang_the_loop(self):
        k = run(reaped_elsewhere=True, plan=lambda n, argv: dict(mode="ok", us=120000))
        stats = STAT.findall(k.console_text())
        self.assertEqual(len(stats), 60)
        self.assertTrue(all(s[2] == "0" for s in stats))
        self.assertEqual(k.exit_code, 0)

    def test_the_model_refuses_what_hb_must_never_do(self):
        # the model's own guards: an unknown system call, an exec of another path and a write to a descriptor that is not open are reported, not ignored
        k = M.Kernel()
        vm = M.VM(HB.read_bytes(), k)
        self.assertEqual(k.handle(vm, 9999, [0, 0, 0, 0, 0])[1], M.ENOSYS)
        self.assertIn("unknown system call 9999", k.errors)
        self.assertEqual(M.ps_output([b"ps", b"-x"])[1], 1)
        self.assertEqual(M.ps_output([b"ps", b"-A"], self_pid=7)[0].splitlines()[-1].split()[0], b"7")

    def test_resuming_a_process_that_never_ran_is_a_failure_not_a_crash(self):
        # found by the ABI mutants (abi_mutants.py): with the fork flag inverted the ORIGINAL process execs the fake ps and is gone; handing control back to it used to raise AttributeError
        k = M.Kernel()
        vm = M.VM(HB.read_bytes(), k)
        gone = M.Proc(77, 40)
        with self.assertRaises(M.Failure) as c:
            vm.load(gone)
        self.assertIn("never suspended", str(c.exception))


@unittest.skipUnless(M is not None and HB.is_file(), "unicorn or the hb file is not present")
class WithTheAnalyser(unittest.TestCase):
    """What the model's console text means to the analyser that will read the phone's text (analyze_nat102.py)."""

    @classmethod
    def setUpClass(cls):
        cls.AN = _load("nat102_analyze_for_vm", HERE / "analyze_nat102.py")

    def test_the_whole_transcript_is_row_h5_with_sixty_lists_and_the_last_one_names_the_daemons(self):
        t = "[  215.1]: noise\n" + run().console_text() + "kernel: trailing noise\n"
        r = self.AN.analyze_text(t, JOBS)
        self.assertEqual((r["row"], r["name"]), (5, "hb-ps-lists"))
        f = r["facts"]
        self.assertEqual((f["lists_after_hb_marker"], f["lists_not_from_hb"]), (60, 0))
        self.assertEqual(f["last_list"]["round"], 60)
        self.assertEqual(f["last_list"]["kind"], "O")
        self.assertEqual(f["zombies_in_last_list"], [19])
        self.assertEqual(f["self_starting_jobs_in_last_list"], ["com.apple.logd", "com.apple.containermanagerd"])      # the job table's order, powerd is a zombie
        self.assertEqual(f["done"]["rounds"], 60)

    def test_a_returned_tail_that_starts_in_the_middle_of_a_line_is_still_h5(self):
        t = run().console_text()
        tail = t[-2500:]
        self.assertFalse(tail.startswith("\nSWEET hb: start"))
        r = self.AN.analyze_text("kernel: x\n" + tail, JOBS)
        self.assertEqual(r["row"], 5, r["reason"])
        self.assertTrue(r["facts"]["lists_after_hb_marker"] >= 3)

    def test_a_head_only_window_with_one_marker_and_no_list_is_h3(self):
        t = run().console_text()
        head = t[:t.index("  PID")]
        r = self.AN.analyze_text(head, JOBS)
        self.assertEqual(r["row"], 3)

    def test_a_hung_ps_shows_in_the_facts(self):
        k = run(plan=lambda n, argv: dict(mode="hang") if n == 2 else dict(mode="ok", us=120000))
        r = self.AN.analyze_text(k.console_text(), JOBS)
        self.assertEqual(r["row"], 5)
        killed = [s for s in r["facts"]["ps_status"] if s["timeout_killed"]]
        self.assertEqual([(s["n"], s["status"]) for s in killed], [(2, 9)])


if __name__ == "__main__":
    unittest.main()
