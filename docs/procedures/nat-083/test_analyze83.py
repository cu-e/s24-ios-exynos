#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-083 host tests of the APFS-root analyser (analyze_nat083.py). Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-083/test_analyze83.py      (opens no device)

What the tests stand on, so that they do not merely mirror the analyser's own regexes:

  * every line the analyser reads is rendered from the C format string of the program that prints it, taken from the pinned source in references/ (the donor's init.c,
    stage0.c and apfs_vfsops.c, XNU's memdev.c, bsd_init.c and IOKitBSDInit.cpp, libmini's strerror names): the test fails if that source no longer contains the format;
  * the kernel lines are also read from the archived NAT-070 run (a real kernel text of the payload kernel) when it is present;
  * the whole `analyze()` path (boot selection, delivery record, loader values, host digest of the root file) is run over the REAL archive of NAT-078, which holds a complete
    delivery of the same root size; its kernel booted rd=md0, so the pre-registered ladder must give row 6 there.
What stays hand-written: the order and the content of the console text of the NAT-083 run (nothing has produced it yet) and the decision cases. Nothing here measures the phone."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REF = ROOT / "references"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A = load("nat083_analyze_mod", HERE / "analyze_nat083.py")
SRC = {
    "init": REF / "hakios/userland/src/init.c", "stage0": REF / "hakios/userland/src/stage0.c",
    "apfs": REF / "hakios/xnu/files/bsd/miscfs/apfs/apfs_vfsops.c", "memdev": REF / "apple-xnu/bsd/dev/memdev.c",
    "bsdinit": REF / "apple-xnu/bsd/kern/bsd_init.c", "iokit": REF / "apple-xnu/iokit/bsddev/IOKitBSDInit.cpp", "mini": REF / "hakios/userland/libmini/mini.c",
}
HAVE_SOURCES = all(p.is_file() for p in SRC.values())
NAT70 = ROOT / "artifacts/nat-070/run-001/kernel-log.txt"
NAT78 = ROOT / "artifacts/nat-078/run-001"
SIZE = A.RESERVE


def c_render(literal, *args):
    """A C printf format literal (as written between the quotes in the source) filled with args; only %d %u %s %x %X %llu %llX %zu %08X %016llX %2u are handled."""
    s = literal.encode().decode("unicode_escape")
    s = re.sub(r"%(0?\d*)(?:ll|z)?([udsxX])", lambda m: "%" + m.group(1) + ("d" if m.group(2) == "u" else m.group(2)), s)
    return s % args


def lit(key, literal):
    """The format literal, checked to be in the pinned source."""
    assert literal in SRC[key].read_text(), "%s no longer contains the format %r" % (SRC[key].name, literal)
    return literal


class Formats(unittest.TestCase):
    """The regexes of the analyser match what the pinned programs print."""

    @unittest.skipUnless(HAVE_SOURCES, "references/ not present")
    def test_every_line_the_analyser_reads_matches_the_format_of_the_program_that_prints_it(self):
        banner = c_render(lit("init", r"\n=== init: process %d, started as %s ===\n"), 1, "/redwood/sbin/init")
        self.assertEqual(A.INIT_BANNER.search(banner).groups(), ("1", "/redwood/sbin/init"))
        check = c_render(lit("init", r"[%s] %s\n"), " ok ", "memory size")
        self.assertEqual(A.CHECK.search(check).groups(), (" ok ", "memory size"))
        self.assertEqual(A.CHECK.search(c_render(lit("init", r"[%s] %s\n"), "FAIL", "x")).group(1), "FAIL")
        self.assertEqual(A.SUMMARY.search(c_render(lit("init", r"\n=== %d checks, %d failed ===\n"), 31, 2)).groups(), ("31", "2"))
        self.assertEqual(A.RC_START.search(c_render(lit("init", r"\n=== %s ===\n"), "/redwood/etc/rc")).group(1), "/redwood/etc/rc")
        self.assertEqual(A.SECTION.search(c_render(lit("init", r"\n-- memory --\n"))).group(1), "memory")
        self.assertEqual(A.SECTION.search(c_render(lit("init", r"\n-- the Darwin root volume on /dev/%s as the root --\n"), "md1")).group(1),
                         "the Darwin root volume on /dev/md1 as the root")
        self.assertEqual(A.ECHO.search(c_render(lit("init", r"\n$")) + " /bin/ps -A\n").group(1), "/bin/ps -A")
        self.assertEqual(A.EXIT_MARK.search(c_render(lit("init", r"[exit status %d]\n"), 127)).group(2), "127")
        self.assertEqual(A.EXIT_MARK.search(c_render(lit("init", r"[killed by signal %d]\n"), 11)).group(3), "11")
        self.assertEqual(A.EXIT_MARK.search(c_render(lit("init", r"[could not run: %s]\n"), "Cannot allocate memory")).group(4), "Cannot allocate memory")
        self.assertIn(A.INIT_DONE, c_render(lit("init", r"\n=== init: done ===\n")))
        st0 = c_render(lit("stage0", r"stage0: cannot mount /dev/md1 on /hakios: %s\n"), "Invalid argument")
        self.assertEqual(A.STAGE0_ERROR.search(st0).groups(), ("mount", "/dev/md1 on /hakios: Invalid argument"))
        self.assertEqual(A.STAGE0_ERROR.search(c_render(lit("stage0", r"stage0: cannot run %s: %s\n"), "/redwood/sbin/init", "No such file or directory")).group(1), "run")
        vol = c_render(lit("apfs", r'apfs: volume %u \"%s\" of container %u (at %llu MB): %llu files, %llu directories, %llu blocks of %u used\n'.replace(r"\"", '\\"')),
                       0, "Macintosh HD", 0, 0, 62258, 4000, 5000, 4096)
        self.assertEqual(A.APFS_VOLUME.search(vol).groups(), ("0", "Macintosh HD", "0", "0", "62258", "4000", "5000", "4096"))
        self.assertTrue(A.APFS_ERRORS[0].search(c_render(lit("apfs", r"apfs: cannot read the container: %d\n"), 5)))
        self.assertTrue(A.APFS_ERRORS[1].search(c_render(lit("apfs", r"apfs: no readable volume with a root directory\n"))))
        self.assertTrue(A.APFS_ERRORS[2].search(c_render(lit("apfs", r"apfs: container %u: %llu blocks of %u do not fit the device\n"), 0, 10, 4096)))
        md = c_render(lit("memdev", r"Added memory device md%x/rmd%x (%08X/%08X) at %016llX for %016llX\n"), 1, 1, 0x1000001, 0xd000001, 0x93000000, 0x93908000)
        self.assertEqual(A.MD_LINE.search(md).group(1, 5), ("md1", "0000000093908000"))
        self.assertEqual(A.A65.BSD_ROOT.search(c_render(lit("iokit", r"BSD root: %s, major %d, minor %d\n"), "md1", 1, 1)).groups(), ("md1", "1", "1"))
        self.assertEqual(A.MOUNTROOT_ERROR.search(c_render(lit("bsdinit", r"cannot mount root, errno = %d\n"), 22)).group(1), "22")

    @unittest.skipUnless(HAVE_SOURCES, "references/ not present")
    def test_the_exec_error_line_uses_the_names_of_libminis_strerror(self):
        names = re.findall(r'"([A-Z][A-Za-z ]+)"', SRC["mini"].read_text().split("strerror(int error)")[1].split("return \"Unknown error\"")[0])
        self.assertGreaterEqual(len(names), 20)
        for n in names:
            self.assertTrue(re.fullmatch(A.STRERROR, n) or n in A.STRERROR, n)
        self.assertIn("Unknown error", A.STRERROR)

    @unittest.skipUnless(NAT70.is_file(), "artifacts/nat-070 not present")
    def test_the_real_payload_kernel_text_is_read_as_the_kernel_prints_it(self):
        k = A.read_userland(NAT70.read_text(errors="replace"))
        self.assertEqual(k["bsd_root"], dict(device="md0", major=1, minor=0))
        self.assertEqual([m["name"] for m in k["md"]], ["md0"])
        self.assertEqual(k["gaps"], [])
        self.assertTrue(k["has_kernel_marker"])
        self.assertIsNone(k["apfs_volume"])
        self.assertEqual(k["pid1_exit"], dict(how="failed to start", signal=0, status=81))
        self.assertIsNone(k["init"]["banner"])


# ---------------------------------------------------------------------------------------------------------------- a text for each case
def rendered(key, literal, *args):
    return c_render(lit(key, literal) if HAVE_SOURCES else literal, *args)


def console(commands, *, banner=True, rc="/redwood/etc/rc", summary=(31, 0), fails=(), stage0=None, done=False):
    """The console part of the text: what the donor init prints, in its own order, for the given [(echo, output, mark)] commands."""
    out = []
    if stage0:
        out.append(stage0)
    if banner:
        out.append(rendered("init", r"\n=== init: process %d, started as %s ===\n", 1, "/redwood/sbin/init"))
        out.append(rendered("init", r"\n-- the Darwin root volume on /dev/%s as the root --\n", "md1"))
        out.append(rendered("init", r"[%s] %s\n", " ok ", "the root is mounted"))
        for f in fails:
            out.append(rendered("init", r"[%s] %s\n", "FAIL", f))
        out.append(rendered("init", r"\n-- memory --\n"))
        if summary:
            out.append(rendered("init", r"\n=== %d checks, %d failed ===\n", *summary))
        if rc:
            out.append(rendered("init", r"\n=== %s ===\n", rc))
            for echo, output, mark in commands:
                out.append("\n$ " + echo + "\n")
                out.append(output)
                if mark:
                    out.append(mark + "\n")
        if done:
            out.append(rendered("init", r"\n=== init: done ===\n"))
    return "".join(out)


def kernel(*, root="md1", md1_size=SIZE, volume=True, mountroot_errno=None, apfs_error=None, panic=None, exit_line=None):
    out = ["[   40.100000]: " + rendered("memdev", r"Added memory device md%x/rmd%x (%08X/%08X) at %016llX for %016llX\n", 0, 0, 0x1000000, 0xd000000, 0x8974000, 0x8000).strip(),
           ]
    if md1_size:
        out.append("[   40.100100]: " + rendered("memdev", r"Added memory device md%x/rmd%x (%08X/%08X) at %016llX for %016llX\n", 1, 1, 0x1000001, 0xd000001, 0x93000000,
                                                   md1_size).strip())
    if root:
        out.append("[   40.100200]: " + rendered("iokit", r"BSD root: %s, major %d, minor %d\n", root, 1, int(root[2:])).strip())
    if volume:
        out.append("[   40.300000]: " + rendered("apfs", r'apfs: volume %u \"%s\" of container %u (at %llu MB): %llu files, %llu directories, %llu blocks of %u used\n'.replace(
            r"\"", '\\"'), 0, "Macintosh HD", 0, 0, 62258, 4000, 5000, 4096).strip())
    if apfs_error:
        out.append("[   40.300000]: " + apfs_error)
    if mountroot_errno is not None:
        out.append("[   40.400000]: " + rendered("bsdinit", r"cannot mount root, errno = %d\n", mountroot_errno).strip())
    if panic:
        out.append("panic(cpu 0 caller 0xfffffff007a9db58): " + panic)
    if exit_line:
        out.append(exit_line)
    return "\n".join(out) + "\n"


GOOD = [("/bin/df", "Filesystem 512-blocks Used Available Capacity Mounted on\n/dev/md1 4000 3000 1000 75% /\n", None),
        ("/sbin/mount", "/dev/md1 on / (apfs, local, read-only)\n", None),
        ("/bin/ps -A", "  PID TTY TIME CMD\n    1 ?? 0:00.01 /redwood/sbin/init\n", None),
        ("/usr/bin/vm_stat", "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 100000.\n", None),
        ("exec /sbin/launchd.darwin", "", None)]
EXIT_PANIC = "initproc exited -- no exit reason available -- (signal 11, exit status 0 )"


def text(cmds=GOOD, k=None, **con):
    return console(cmds, **con) + A.KMARK + "\n" + (k if k is not None else kernel())


def loader(status=0, committed=SIZE):
    return dict(found=True, values=dict(committed=committed, bytes=SIZE), status=status, status_name={0: "done", 6: "timeout"}.get(status, str(status)), progress=[])


DELIVERED = dict(outcome="delivered", committed=SIZE)


def decide(t, chain="PASS", delivery=DELIVERED, ld=None):
    return A.decide(chain, delivery, ld or loader(), SIZE, A.read_userland(t))


class Ladder(unittest.TestCase):
    def test_row_1a_the_whole_chain_ran_and_nothing_exited_after_the_exec(self):
        d = decide(text())
        self.assertEqual((d["row"], d["variant"], d["pass"]), (1, "a", True), d["reasons"])
        self.assertEqual(d["facts"]["apfs_volume"]["files"], 62258)
        self.assertEqual([c["command"] for c in d["facts"]["commands"]][-1], "exec /sbin/launchd.darwin")

    def test_failed_init_checks_are_reported_and_do_not_change_row_1(self):
        d = decide(text(fails=("kern.hostname set",), summary=(32, 1)))
        self.assertEqual((d["row"], d["variant"]), (1, "a"))
        self.assertEqual(d["facts"]["init_checks_failed"], ["kern.hostname set"])
        self.assertEqual(d["facts"]["init_summary"], dict(checks=32, failed=1))

    def test_row_1b_launchd_exited_after_the_exec_line(self):
        d = decide(text(k=kernel(panic=EXIT_PANIC, exit_line="[   99.1]: pid 1 exited -- no exit reason available -- (signal 11, exit 0)")))
        self.assertEqual((d["row"], d["variant"], d["pass"]), (1, "b", False))
        self.assertEqual(d["facts"]["pid1_exit"], dict(how="exited", signal=11, status=0))

    def test_row_1_console_text_from_launchd_after_the_exec_line_is_kept(self):
        cmds = GOOD[:-1] + [("exec /sbin/launchd.darwin", "launchd: hello\nsecond line\n", None)]
        k = A.read_userland(text(cmds))
        self.assertEqual(k["after_exec"]["lines"], ["launchd: hello", "second line"])
        self.assertEqual(decide(text(cmds))["facts"]["after_exec_bytes"], len("launchd: hello\nsecond line\n") - 1)

    def test_row_2_an_apple_program_that_exits_non_zero_is_named(self):
        cmds = [GOOD[0], ("/sbin/mount", "", "[exit status 1]")] + GOOD[2:]
        d = decide(text(cmds))
        self.assertEqual((d["row"], d["variant"]), (2, "darwin-program"))
        self.assertIn("/sbin/mount: exit status 1", d["reasons"][0])

    def test_row_2_a_program_that_cannot_be_exec_ed_shows_in_both_lines(self):
        cmds = [("/bin/df", "/bin/df: Exec format error\n", "[exit status 127]")] + GOOD[1:]
        d = decide(text(cmds))
        self.assertEqual((d["row"], d["variant"]), (2, "darwin-program"))
        self.assertIn("exec error: Exec format error", d["reasons"][0])

    def test_row_2_a_program_killed_by_a_signal(self):
        cmds = GOOD[:2] + [("/bin/ps -A", "", "[killed by signal 4]")] + GOOD[3:]
        self.assertIn("killed by signal 4", decide(text(cmds))["reasons"][0])

    def test_row_2_could_not_run(self):
        cmds = GOOD[:3] + [("/usr/bin/vm_stat", "", "[could not run: Cannot allocate memory]")] + GOOD[4:]
        self.assertIn("could not run: Cannot allocate memory", decide(text(cmds))["reasons"][0])

    def test_row_2_a_missing_command_is_not_clean(self):
        d = decide(text(GOOD[:1] + GOOD[2:]))
        self.assertEqual((d["row"], d["variant"]), (2, "darwin-program"))
        self.assertIn("/sbin/mount: no echo line", d["reasons"][0])

    def test_row_2_the_rc_file_was_never_reached(self):
        d = decide(text(rc=None))
        self.assertEqual((d["row"], d["variant"]), (2, "rc-not-reached"))
        self.assertIn("memory", d["reasons"][0])

    def test_row_2_the_rc_stops_before_the_exec(self):
        d = decide(text(GOOD[:-1]))
        self.assertEqual((d["row"], d["variant"]), (2, "exec-not-reached"))

    def test_row_2_the_exec_of_launchd_fails(self):
        cmds = GOOD[:-1] + [("exec /sbin/launchd.darwin", "/sbin/launchd.darwin: No such file or directory\n", None)]
        d = decide(text(cmds))
        self.assertEqual((d["row"], d["variant"]), (2, "launchd-exec-failed"))
        self.assertIn("No such file or directory", d["reasons"][0])

    def test_a_launchd_line_that_is_not_an_errno_text_is_not_an_exec_failure(self):
        cmds = GOOD[:-1] + [("exec /sbin/launchd.darwin", "/sbin/launchd.darwin: boot starting\n", None)]
        self.assertEqual(decide(text(cmds))["row"], 1)

    def test_row_3_stage0_could_not_mount_the_small_image(self):
        t = console([], banner=False, stage0=rendered("stage0", r"stage0: cannot mount /dev/md1 on /hakios: %s\n", "Invalid argument")) + A.KMARK + "\n" + kernel()
        d = decide(t)
        self.assertEqual(d["row"], 3, d["reasons"])
        self.assertIn("cannot mount", d["reasons"][0])

    def test_row_3_stage0_could_not_run_init(self):
        t = console([], banner=False, stage0=rendered("stage0", r"stage0: cannot run %s: %s\n", "/redwood/sbin/init", "No such file or directory")) + A.KMARK + "\n" + kernel()
        self.assertEqual(decide(t)["row"], 3)

    def test_row_4_the_root_mounted_but_pid_1_said_nothing(self):
        t = console([], banner=False) + A.KMARK + "\n" + kernel(panic="initproc failed to start -- no exit reason available -- (signal 0, exit status 127 )",
                                                            exit_line="[   41.0]: initproc failed to start -- no exit reason available -- (signal 0, exit status 127 )")
        d = decide(t)
        self.assertEqual(d["row"], 4, d["reasons"])
        self.assertEqual(d["facts"]["pid1_exit"], dict(how="failed to start", signal=0, status=127))

    def test_row_5_the_kernel_could_not_mount_the_root(self):
        t = console([], banner=False) + A.KMARK + "\n" + kernel(volume=False, mountroot_errno=22, apfs_error="apfs: cannot read the container: 5", panic="cannot mount root")
        d = decide(t)
        self.assertEqual(d["row"], 5)
        self.assertIn("errno 22", d["reasons"][0])
        self.assertEqual(d["facts"]["apfs_errors"], ["apfs: cannot read the container: 5"])

    def test_row_5_no_volume_line_and_nothing_else_is_still_row_5(self):
        t = console([], banner=False) + A.KMARK + "\n" + kernel(volume=False)
        self.assertEqual(decide(t)["row"], 5)

    def test_row_6_the_root_is_md0(self):
        d = decide(text(k=kernel(root="md0")))
        self.assertEqual(d["row"], 6)
        self.assertIn("md0", d["reasons"][0])

    def test_row_6_no_bsd_root_line(self):
        self.assertEqual(decide(text(k=kernel(root=None)))["row"], 6)

    def test_row_6_md1_of_another_size_or_missing(self):
        self.assertEqual(decide(text(k=kernel(md1_size=SIZE - 16384)))["row"], 6)
        self.assertEqual(decide(text(k=kernel(md1_size=None)))["row"], 6)

    def test_row_6_the_specified_root_memory_device_panic(self):
        k = kernel(root=None, panic="specified root memory device, md1, has not been configured")
        self.assertEqual(decide(text(k=k))["row"], 6)

    def test_row_7_the_root_was_not_fully_delivered(self):
        self.assertEqual(decide(text(), delivery=dict(outcome="failed", committed=SIZE // 2), ld=loader(6, SIZE // 2))["row"], 7)
        self.assertEqual(decide(text(), delivery=None, ld=loader(0, SIZE))["row"], 7)
        self.assertEqual(decide(text(), delivery=DELIVERED, ld=loader(6, SIZE))["row"], 7)
        self.assertEqual(decide(text(), delivery=dict(outcome="delivered", committed=SIZE), ld=loader(0, SIZE - 4096))["row"], 7)

    def test_row_9_beats_every_other_row(self):
        for chain in ("FAIL", "INCONCLUSIVE", None):
            self.assertEqual(decide(text(), chain=chain)["row"], 9)
        self.assertEqual(decide(text(k=kernel(root="md0")), chain="FAIL")["row"], 9)

    def test_row_8_an_exec_of_another_program(self):
        cmds = GOOD[:-1] + [("exec /sbin/launchd", "", None)]
        self.assertEqual(decide(text(cmds))["row"], 8)


class Gaps(unittest.TestCase):
    """A needed line that is absent while bytes of the log were not sent is never a negative finding."""
    MARK = "\n[... 29040 bytes of the log were not sent ...]\n"

    def test_a_missing_bsd_root_line_with_a_gap_is_not_established(self):
        d = decide(text(k=kernel(root=None)) + self.MARK)
        self.assertEqual(d["row"], 8)
        self.assertIn("29040", d["reasons"][0])

    def test_a_missing_md1_line_with_a_gap_is_not_established(self):
        self.assertEqual(decide(text(k=kernel(md1_size=None)) + self.MARK)["row"], 8)

    def test_a_missing_volume_line_with_a_gap_is_not_established_unless_an_error_is_in_the_text(self):
        t = console([], banner=False) + A.KMARK + "\n" + kernel(volume=False) + self.MARK
        self.assertEqual(decide(t)["row"], 8)
        t = console([], banner=False) + A.KMARK + "\n" + kernel(volume=False, mountroot_errno=22) + self.MARK
        self.assertEqual(decide(t)["row"], 5)

    def test_a_missing_banner_with_a_gap_is_not_established(self):
        t = console([], banner=False) + A.KMARK + "\n" + kernel() + self.MARK
        self.assertEqual(decide(t)["row"], 8)

    def test_a_missing_rc_or_command_with_a_gap_is_not_established(self):
        self.assertEqual(decide(text(rc=None) + self.MARK)["row"], 8)
        self.assertEqual(decide(text(GOOD[:1] + GOOD[2:]) + self.MARK)["row"], 8)
        self.assertEqual(decide(text(GOOD[:-1]) + self.MARK)["row"], 8)

    def test_a_line_that_is_present_is_judged_even_with_a_gap(self):
        cmds = [GOOD[0], ("/sbin/mount", "", "[exit status 1]")] + GOOD[2:]
        self.assertEqual(decide(text(cmds) + self.MARK)["row"], 2)
        self.assertEqual(decide(text() + self.MARK)["row"], 1)

    def test_the_gap_sizes_are_read(self):
        k = A.read_userland("a" + self.MARK + "b" + "\n[... 12 bytes of the log were not sent ...]\n")
        self.assertEqual((k["gaps"], k["gap_bytes"]), ([29040, 12], 29052))


class Blocks(unittest.TestCase):
    def test_a_block_ends_at_the_next_echo_and_not_before_the_done_line(self):
        t = console(GOOD, done=True)
        b = A.split_blocks(t)
        self.assertEqual([x["argv0"] for x in b], ["/bin/df", "/sbin/mount", "/bin/ps", "/usr/bin/vm_stat", "exec"])
        self.assertNotIn("init: done", b[-1]["text"])
        self.assertIn("Pages free", b[3]["text"])
        self.assertNotIn("Pages free", b[2]["text"])

    def test_the_runner_marks_are_attached_to_their_own_command(self):
        cmds = [GOOD[0], ("/sbin/mount", "x\n", "[exit status 3]")] + GOOD[2:]
        b = A.split_blocks(console(cmds))
        self.assertEqual([x["marks"] for x in b], [[], [dict(kind="exit-status", value=3)], [], [], []])

    def test_carriage_returns_do_not_break_the_reading(self):
        t = text().replace("\n", "\r\n")
        self.assertEqual(decide(t)["row"], 1)

    def test_output_kept_per_command_is_bounded(self):
        cmds = [("/bin/df", "x" * 10000 + "\n", None)] + GOOD[1:]
        b = A.split_blocks(console(cmds))
        self.assertEqual(len(b[0]["text"]), 3000)
        self.assertGreater(b[0]["bytes"], 10000)

    def test_the_console_text_kept_after_the_exec_line_is_bounded(self):
        cmds = GOOD[:-1] + [("exec /sbin/launchd.darwin", "".join("line %d\n" % i for i in range(100)), None)]
        k = A.read_userland(text(cmds))
        self.assertEqual(len(k["after_exec"]["lines"]), 40)
        self.assertEqual(k["after_exec"]["lines"][0], "line 0")
        self.assertEqual(k["after_exec"]["bytes"], len("".join("line %d\n" % i for i in range(100))) - 1)


class Reading(unittest.TestCase):
    """read_userland(): each field is read from its own line, in a text where no two numbers coincide."""
    VOL = '[   40.5]: apfs: volume 3 "Vol A" of container 7 (at 11 MB): 62258 files, 4001 directories, 5002 blocks of 16384 used\n'
    EXIT_A = "initproc exited -- no exit reason available -- (signal 11, exit status 3 )"
    EXIT_B = "pid 4 exited -- no exit reason available -- (signal 5, exit 9)"

    def full(self):
        stage0 = "stage0: cannot mount /dev/md0 on /redwood: Invalid argument\n"
        k = kernel(volume=False, mountroot_errno=22, apfs_error="apfs: cannot read the container: 5", panic="boom", exit_line=self.EXIT_A + "\n" + self.EXIT_B)
        return console(GOOD, done=True, stage0=stage0) + A.KMARK + "\n" + k + self.VOL

    def test_every_field_is_read_from_its_own_line(self):
        k = A.read_userland(self.full())
        self.assertEqual(k["apfs_volume"], dict(index=3, name="Vol A", container=7, at_mb=11, files=62258, directories=4001, blocks_used=5002, block_size=16384))
        self.assertEqual(k["stage0_error"], dict(what="mount", detail="/dev/md0 on /redwood: Invalid argument"))
        self.assertEqual(k["init"]["banner"], dict(pid=1, argv0="/redwood/sbin/init"))
        self.assertEqual(k["init"]["rc"], "/redwood/etc/rc")
        self.assertEqual(k["init"]["summary"], dict(checks=31, failed=0))
        self.assertEqual(k["init"]["checks_total"], 1)
        self.assertEqual(k["init"]["checks_failed"], [])
        self.assertTrue(k["init"]["done"])
        self.assertEqual(k["mountroot_errno"], 22)
        self.assertEqual(k["apfs_errors"], ["apfs: cannot read the container: 5"])
        self.assertEqual(k["panic"], "boom")
        self.assertEqual(k["pid1_exit"], dict(how="exited", signal=11, status=3))
        self.assertEqual(k["pid1_exit_printf"], dict(pid=4, signal=5, status=9))
        self.assertEqual(k["bsd_root"], dict(device="md1", major=1, minor=1))
        self.assertEqual([m["name"] for m in k["md"]], ["md0", "md1"])
        self.assertTrue(k["has_kernel_marker"])

    def test_lines_that_are_not_in_the_text_read_as_none(self):
        k = A.read_userland(console(GOOD))
        self.assertFalse(k["init"]["done"])
        for key in ("apfs_volume", "stage0_error", "panic", "pid1_exit", "pid1_exit_printf", "bsd_root", "mountroot_errno"):
            self.assertIsNone(k[key], key)
        self.assertEqual((k["apfs_errors"], k["md"], k["gaps"]), ([], [], []))
        self.assertFalse(k["has_kernel_marker"])
        self.assertFalse(k["root_panic_no_device"])
        e = A.read_userland("")
        self.assertEqual((e["text_bytes"], e["commands"], e["init"]["banner"]), (0, [], None))

    def test_a_stage0_line_after_the_kernel_marker_is_not_console_text(self):
        t = console(GOOD) + A.KMARK + "\n" + kernel() + "stage0: cannot run /x: y\n"
        self.assertIsNone(A.read_userland(t)["stage0_error"])

    def test_a_kernel_marker_at_the_very_start_leaves_no_console_text(self):
        k = A.read_userland(A.KMARK + "\n$ /bin/df\nfoo\n")
        self.assertTrue(k["has_kernel_marker"])
        self.assertEqual((k["commands"], k["exec_seen"]), ([], False))
        self.assertEqual(A.read_userland("$ /bin/df\nfoo\n")["has_kernel_marker"], False)

    def test_the_text_after_the_last_exec_line_is_kept(self):
        cmds = GOOD[:-1] + [("exec /first", "one\n", None), ("exec /sbin/launchd.darwin", "two\n", None)]
        k = A.read_userland(console(cmds))
        self.assertEqual(k["after_exec"]["lines"], ["two"])
        self.assertTrue(k["exec_seen"])

    def test_no_exec_line_means_no_text_after_it(self):
        k = A.read_userland(console(GOOD[:-1]))
        self.assertEqual((k["after_exec"], k["exec_seen"]), (dict(bytes=0, lines=[]), False))


class Details(unittest.TestCase):
    MARK = Gaps.MARK

    def test_the_block_of_a_command_ends_at_the_next_echo_and_the_target_is_the_program(self):
        b = A.split_blocks(console(GOOD, done=True))
        self.assertEqual([x["target"] for x in b], ["/bin/df", "/sbin/mount", "/bin/ps", "/usr/bin/vm_stat", "/sbin/launchd.darwin"])
        self.assertNotIn("exec", b[3]["text"])                    # the vm_stat block stops at the exec echo
        self.assertNotIn("/usr/bin/vm_stat", b[2]["text"])
        self.assertEqual(b[3]["bytes"], len("\n" + GOOD[3][1] + "\n"))          # the newline after the echo, the output, the blank line the runner prints before the next echo
        self.assertEqual(b[0]["command"], "/bin/df")
        self.assertEqual(b[2]["command"], "/bin/ps -A")

    def test_a_bare_exec_is_about_the_exec_word_itself(self):
        b = A.split_blocks("\n$ exec\n\n$ /bin/df\n")
        self.assertEqual([(x["argv0"], x["target"]) for x in b], [("exec", "exec"), ("/bin/df", "/bin/df")])

    def test_a_done_line_right_after_the_echo_leaves_an_empty_block(self):
        b = A.split_blocks("$ /bin/df\n=== init: done ===\n")
        self.assertEqual((b[0]["bytes"], b[0]["text"]), (0, ""))

    def test_a_block_without_a_done_line_keeps_all_its_bytes(self):
        b = A.split_blocks("$ /bin/df\nabc\n")
        self.assertEqual((b[0]["bytes"], b[0]["text"]), (5, "abc"))

    def test_could_not_run_keeps_the_reason_only(self):
        b = A.split_blocks("$ /bin/df\n[could not run: Cannot allocate memory]\n")
        self.assertEqual(b[0]["marks"], [dict(kind="could-not-run", value="Cannot allocate memory")])

    def test_a_clean_block_has_no_problem_and_a_missing_one_has(self):
        self.assertIsNone(A.command_problem(dict(exec_error=None, marks=[])))
        self.assertEqual(A.command_problem(None), "no echo line")

    def test_the_pick_of_the_return_dump_is_the_highest_non_empty_one(self):
        self.assertEqual(A.pick_text({"1": "early", "2": "late", "3": ""}), ("2", "late"))
        self.assertEqual(A.pick_text({"1": "only"}), ("1", "only"))
        self.assertEqual(A.pick_text({"1": "", "2": None}), (None, ""))
        self.assertEqual(A.pick_text(None), (None, ""))
        self.assertEqual(A.pick_text({"1": "a", "2": "b", "3": "c"}), ("3", "c"))

    def test_the_delivered_size_may_come_from_the_companion_when_the_loader_lacks_it(self):
        ld = loader()
        ld["values"] = {}
        d = decide(text(), ld=ld)
        self.assertEqual((d["row"], d["variant"]), (1, "a"))
        self.assertEqual(d["facts"]["committed"], SIZE)
        d = decide(text(), delivery=dict(outcome="delivered", committed=SIZE - 1), ld=ld)
        self.assertEqual(d["row"], 7)

    def test_row_1a_says_how_much_console_text_followed_the_exec_line(self):
        d = decide(text())
        self.assertTrue(d["reasons"][0].endswith("(0 bytes of console text after the exec line)"), d["reasons"])
        cmds = GOOD[:-1] + [("exec /sbin/launchd.darwin", "launchd: hello\nsecond line\n", None)]
        self.assertTrue(decide(text(cmds))["reasons"][0].endswith("(%d bytes of console text after the exec line)" % (len("launchd: hello\nsecond line\n") - 1)))

    def test_row_1b_either_a_pid_1_exit_or_a_panic_is_enough_and_both_are_named(self):
        d = decide(text(k=kernel(panic="boom")))
        self.assertEqual((d["row"], d["variant"], d["pass"]), (1, "b", False))
        self.assertTrue(d["reasons"][0].endswith("after it: PID 1 exit none, panic boom"), d["reasons"])
        d = decide(text(k=kernel(exit_line=Reading.EXIT_A)))
        self.assertEqual((d["row"], d["variant"]), (1, "b"))
        self.assertIn("'signal': 11", d["reasons"][0])
        self.assertTrue(d["reasons"][0].endswith("panic none"), d["reasons"])

    def test_row_2_rc_not_reached_names_the_summary_or_its_absence(self):
        d = decide(text(rc=None, summary=None))
        self.assertIn("summary absent", d["reasons"][0])
        d = decide(text(rc=None, summary=(31, 2)))
        self.assertIn("summary {'checks': 31, 'failed': 2}", d["reasons"][0])

    def test_row_4_names_the_panic_and_the_exit_or_their_absence(self):
        t = console([], banner=False) + A.KMARK + "\n" + kernel()
        d = decide(t)
        self.assertEqual(d["row"], 4)
        self.assertIn("panic none, PID 1 exit none", d["reasons"][0])
        t = console([], banner=False) + A.KMARK + "\n" + kernel(panic="init died", exit_line="initproc failed to start -- no exit reason available -- (signal 0, exit status 127 )")
        d = decide(t)
        self.assertIn("panic init died", d["reasons"][0])
        self.assertIn("'status': 127", d["reasons"][0])

    def test_row_5_names_what_the_kernel_said(self):
        base = console([], banner=False) + A.KMARK + "\n"
        d = decide(base + kernel(volume=False, mountroot_errno=22))
        self.assertEqual(d["row"], 5)
        self.assertIn("errno 22; apfs lines none; panic none", d["reasons"][0])
        d = decide(base + kernel(volume=False, apfs_error="apfs: cannot read the container: 5") + self.MARK)
        self.assertEqual(d["row"], 5)
        self.assertIn("errno None; apfs lines ['apfs: cannot read the container: 5']; panic none", d["reasons"][0])
        d = decide(base + kernel(volume=False, panic="boom") + self.MARK)
        self.assertEqual(d["row"], 5)
        self.assertIn("errno None; apfs lines none; panic boom", d["reasons"][0])

    def test_row_6_the_root_device_panic_is_a_finding_even_when_the_log_has_a_gap(self):
        k = kernel(root=None, panic="specified root memory device, md1, has not been configured")
        d = decide(text(k=k) + self.MARK)
        self.assertEqual(d["row"], 6)
        self.assertIn("panicked on the specified root memory device", d["reasons"][0])
        d = decide(text(k=k))
        self.assertIn("panicked on the specified root memory device", d["reasons"][0])


class Plumbing(unittest.TestCase):
    """analyze() with the shipped chain replaced by a stub: the image name the chain runs under, and what is put back afterwards."""

    def test_the_chain_runs_under_this_images_name_and_the_previous_name_comes_back(self):
        seen = {}

        def stub(root, events, report, allow_synthetic, **kw):
            seen["image"] = A.A65.IMAGE
            return {"kernel_log": {"texts": {"1": "", "2": text()}}, "verdict": "PASS"}

        before = A.A65.IMAGE
        A.A65.IMAGE = "sentinel-name"
        try:
            with mock.patch.object(A.A80, "_ANALYZE65", stub), mock.patch.object(A.A80, "host_prefix_digests", lambda p, sizes: {SIZE: "x"}):
                out = A.analyze(Path("nowhere"), [], {}, None, Path("image"), SIZE, "x")
            self.assertEqual(seen["image"], A.IMAGE)
            self.assertEqual(A.A65.IMAGE, "sentinel-name")
        finally:
            A.A65.IMAGE = before
        self.assertEqual(out["image"], A.IMAGE)
        self.assertEqual(out["nat083"]["kernel"]["dump_used"], "2")
        self.assertEqual(out["nat083"]["chain_verdict"], "PASS")

    def test_a_restore_happens_even_when_the_chain_raises(self):
        def boom(*a, **kw):
            raise RuntimeError("chain failed")

        before = A.A65.IMAGE
        A.A65.IMAGE = "sentinel-name"
        try:
            with mock.patch.object(A.A80, "_ANALYZE65", boom):
                with self.assertRaises(RuntimeError):
                    A.analyze(Path("nowhere"), [], {}, None, Path("image"), SIZE, "x")
            self.assertEqual(A.A65.IMAGE, "sentinel-name")
        finally:
            A.A65.IMAGE = before


SHA78 = "552800ff3ac3de129b550c838681d0cb1d08cc4df0d38b2dc1088a9b258a8258"


@unittest.skipUnless(NAT78.is_dir() and (ROOT / "artifacts/nat-077/system-padded.apfs").is_file(), "artifacts/nat-078 and nat-077 not present")
class Main(unittest.TestCase):
    """The command line over the real NAT-078 archive. The host digest of the 2.3 GiB root file is replaced by its known value here (RealArchive runs the real digest once)."""

    def run_main(self, extra=(), sha=SHA78):
        argv = ["--archive", str(NAT78 / "archive"), "--events", str(NAT78 / "usb-events.jsonl"), "--report", str(NAT78 / "report.json"), "--delivery", str(NAT78 / "delivery"),
                "--root", str(ROOT / "artifacts/nat-077/system-padded.apfs"), "--size", str(SIZE), "--sha256", sha] + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(A, "IMAGE", "loader-diag-xnu-rx-md1"), mock.patch.object(A.A80, "host_prefix_digests", lambda p, sizes: {SIZE: SHA78}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = A.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_without_out_it_prints_the_record_and_writes_no_file(self):
        rc, out, err = self.run_main()
        self.assertEqual((rc, err), (0, ""))
        self.assertTrue(out.startswith('{\n "'), out[:20])                      # indent 1
        self.assertTrue(out.endswith("}\n"))
        res = json.loads(out)
        self.assertEqual(res["nat083"]["chain_verdict"], "PASS")                   # the report was read (an empty one gives "undetermined")
        self.assertEqual(res["nat083"]["decision"]["row"], 6)

    def test_out_and_log_out_are_written(self):
        with tempfile.TemporaryDirectory() as d:
            o, lg = Path(d) / "analysis.json", Path(d) / "kernel.log"
            rc, out, err = self.run_main(["--out", str(o), "--log-out", str(lg)])
            self.assertEqual((rc, err), (0, ""))
            self.assertEqual(o.read_text(), out)
            self.assertEqual(json.loads(o.read_text())["nat083"]["decision"]["row"], 6)
            self.assertGreater(lg.stat().st_size, 1000)

    def test_an_existing_out_file_is_refused_and_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "analysis.json"
            o.write_text("keep")
            rc, out, err = self.run_main(["--out", str(o)])
            self.assertEqual((rc, out), (2, ""))
            self.assertEqual(err, "refused: %s already exists\n" % o)
            self.assertEqual(o.read_text(), "keep")

    def test_a_root_file_that_is_not_the_judged_image_is_refused_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            o = Path(d) / "analysis.json"
            rc, out, err = self.run_main(["--out", str(o)], sha="0" * 64)
            self.assertEqual((rc, out), (2, ""))
            self.assertTrue(err.startswith("refused: the root file is not the image the run is judged against"), err)
            self.assertFalse(o.exists())

    def test_the_synthetic_flag_is_accepted(self):
        rc, out, err = self.run_main(["--allow-synthetic"])
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("nat083", json.loads(out))


@unittest.skipUnless(NAT78.is_dir() and (ROOT / "artifacts/nat-077/system-padded.apfs").is_file(), "artifacts/nat-078 and nat-077 not present")
class RealArchive(unittest.TestCase):
    """analyze() over the archive of NAT-078: the plumbing (boot selection, delivery record, loader values, root hash) with a real kernel text that booted rd=md0."""

    @classmethod
    def setUpClass(cls):
        events, _ = A.A65.A49.read_jsonl(str(NAT78 / "usb-events.jsonl"))
        report = A.A65.A49.read_json(str(NAT78 / "report.json")) or {}
        old = A.IMAGE
        A.IMAGE = "loader-diag-xnu-rx-md1"
        cls.a65_image_before = A.A65.IMAGE
        A.S.LAST["stale"] = "left by an earlier analysis"
        try:
            cls.res = A.analyze(NAT78 / "archive", events, report, NAT78 / "delivery", ROOT / "artifacts/nat-077/system-padded.apfs", SIZE,
                                "552800ff3ac3de129b550c838681d0cb1d08cc4df0d38b2dc1088a9b258a8258")
        finally:
            A.IMAGE = old
        cls.a65_image_after = A.A65.IMAGE

    def test_the_run_leaves_no_state_of_an_earlier_analysis_and_restores_the_image_name(self):
        self.assertNotIn("stale", A.S.LAST)
        self.assertEqual(self.a65_image_after, self.a65_image_before)

    def test_the_record_names_the_image_the_dump_and_the_ending(self):
        self.assertEqual(self.res["image"], "loader-diag-xnu-rx-md1")        # analyze() ran with the patched name; the field says which name the chain used
        self.assertEqual(self.res["nat083"]["kernel"]["dump_used"], "2")
        self.assertEqual(self.res["nat083"]["ending"]["cls"], "cap-reset")
        self.assertEqual(self.res["nat083"]["ending"]["klass"], "download")

    def test_the_ladder_gives_row_6_for_a_kernel_that_booted_md0(self):
        d = self.res["nat083"]["decision"]
        self.assertEqual((d["row"], d["pass"]), (6, False), d["reasons"])
        self.assertEqual(self.res["nat083"]["chain_verdict"], "PASS")

    def test_the_replay_boot_was_judged_and_the_delivery_record_was_read(self):
        n = self.res["nat083"]
        self.assertTrue(n["nat081"]["applied"])
        self.assertEqual(n["delivery"]["outcome"], "delivered")
        self.assertEqual(n["delivery"]["committed"], SIZE)
        self.assertEqual(n["loader"]["status_name"], "done")
        self.assertEqual([m["name"] for m in n["kernel"]["md"]], ["md0", "md1"])
        self.assertEqual(n["kernel"]["md"][1]["size"], SIZE)
        self.assertEqual(n["kernel"]["gaps"], [])

    def test_the_wrong_root_file_is_refused(self):
        events, _ = A.A65.A49.read_jsonl(str(NAT78 / "usb-events.jsonl"))
        with self.assertRaises(ValueError):
            A.analyze(NAT78 / "archive", events, A.A65.A49.read_json(str(NAT78 / "report.json")) or {}, NAT78 / "delivery",
                      ROOT / "artifacts/nat-077/system-padded.apfs", SIZE, "0" * 64)

    def test_the_boot_selection_hook_is_removed_afterwards(self):
        self.assertFalse(getattr(A.A65.A49.load_archive, "__name__", "") == "load_archive" and A.A65.A49.load_archive.__module__ == A.S.__name__)


if __name__ == "__main__":
    unittest.main(verbosity=1)
