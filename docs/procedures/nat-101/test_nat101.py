#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-101 host tests. Evidence kind: host-test. Nothing here runs on the phone, and nothing here executes the Darwin binary.

Three layers:
  * HostModel: src/hb.c compiled for Linux with -DHOST_TEST (the same control flow over libc shims) and run against fake ps scripts: the output format,
    the round loop, the odd/even ps arguments, a hanging ps killed after the timeout, a missing ps, a missing console, a failing fork. The raw Darwin
    system-call layer (numbers in x16, the x1 child flag, the carry convention) is NOT run by any of this.
  * DarwinBinary: the real freestanding build (clang + lld + mkstatic) is audited structurally, and its machine code is disassembled with capstone: the
    set of `svc #0x80` call sites and the system-call number loaded before each one must be exactly the intended set (no unlink, rename, mount, ...).
  * Builders: build_hb.audit refusals on synthetic Mach-O headers; build_hb_root.new_rc and build() refusals; with the real artifacts (skipped when absent)
    the image tree against NAT-096's file by file.
"""
import hashlib
import importlib.util
import json
import os
import re
import resource
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = HERE / "src" / "hb.c"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


BH = _load("nat101_build_hb", HERE / "build_hb.py")
BR = _load("nat101_build_hb_root", HERE / "build_hb_root.py")
BASE = ROOT / "artifacts/nat-096/pid1-sq"
OUT = ROOT / "artifacts/nat-101/pid1-hb"
HBJ = ROOT / "artifacts/nat-101/hb-build-001/hb.json"
HAVE = BASE.is_dir() and OUT.is_dir() and HBJ.is_file()

FAKE_PS = """#!/bin/sh
echo "PID TTY TIME CMD"
echo "$$ fake-ps"
echo "ARGS: $*"
echo "stderr line" >&2
"""
HANG_PS = "#!/bin/sh\nexec sleep 30\n"


def compile_host(tmp, name, console, ps, rounds=3, period=1, timeout=1):
    exe = Path(tmp) / name
    cmd = ["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-DHOST_TEST", '-DCONSOLE_DEV="%s"' % console, '-DPS_PATH="%s"' % ps,
           "-DHB_ROUNDS=%d" % rounds, "-DHB_PERIOD_S=%d" % period, "-DHB_PS_TIMEOUT_S=%d" % timeout, "-o", str(exe), str(SRC)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return exe


def script(tmp, name, body):
    p = Path(tmp) / name
    p.write_text(body)
    p.chmod(0o755)
    return str(p)


class HostModel(unittest.TestCase):
    def run_hb(self, tmp, console, ps, preexec=None, **kw):
        exe = compile_host(tmp, "hb-host", console, ps, **kw)
        p = subprocess.Popen([str(exe)], preexec_fn=preexec)
        try:
            rc = p.wait(timeout=30)
        finally:
            if p.poll() is None:        # a mutant that never ends must not outlive the test
                p.kill()
                p.wait()
        out = Path(console).read_text() if Path(console).exists() else None
        return rc, out, p.pid

    def test_normal_rounds_output_format_and_ps_arguments(self):
        with tempfile.TemporaryDirectory() as t:
            con = Path(t) / "console"
            con.write_text("")
            rc, out, pid = self.run_hb(t, con, script(t, "ps", FAKE_PS))
            self.assertEqual(rc, 0)
            lines = out.split("\n")
            self.assertEqual(lines[0], "")
            me = os.getpid()
            self.assertEqual(lines[1], "SWEET hb: start pid=%d ppid=%d period=1s rounds=3 ps_timeout=1s" % (pid, me))
            rest = lines[2:]
            for n in (1, 2, 3):
                m = re.fullmatch(r"SWEET hb: n=%d pid=%d ppid=%d up=(\d+)" % (n, pid, me), rest.pop(0))
                self.assertIsNotNone(m, n)
                got = {rest.pop(0) for _ in range(4)}   # the fake ps writes four lines (one on stderr); their order between the two streams is the kernel's
                self.assertEqual({g for g in got if g.startswith("ARGS")}, {"ARGS: -A" if n % 2 else "ARGS: -Ao pid,ppid,stat,comm"})
                self.assertIn("PID TTY TIME CMD", got)
                self.assertIn("stderr line", got)
                fake_pid = [g for g in got if g.endswith("fake-ps")][0].split()[0]
                st = re.fullmatch(r"SWEET hb: n=%d ps pid=%s status=0 ms=(\d+)" % (n, fake_pid), rest.pop(0))
                self.assertIsNotNone(st, n)
                self.assertLess(int(st.group(1)), 900)
            self.assertEqual(rest, ["SWEET hb: done rounds=3", ""])
            self.assertEqual(sum(1 for line in lines if "timeout-killed" in line), 0)

    def test_up_counter_advances_with_the_period(self):
        with tempfile.TemporaryDirectory() as t:
            con = Path(t) / "console"
            con.write_text("")
            rc, out, _ = self.run_hb(t, con, script(t, "ps", FAKE_PS), rounds=3, period=1)
            ups = [int(m) for m in re.findall(r"up=(\d+)", out)]
            self.assertEqual(ups, [0, 1, 2])

    def test_hanging_ps_is_killed_after_the_timeout_and_the_loop_goes_on(self):
        with tempfile.TemporaryDirectory() as t:
            con = Path(t) / "console"
            con.write_text("")
            rc, out, _ = self.run_hb(t, con, script(t, "ps", HANG_PS), rounds=2, period=1, timeout=1)
            self.assertEqual(rc, 0)
            status = re.findall(r"SWEET hb: n=(\d) ps pid=(\d+) status=(\d+) ms=(\d+) timeout-killed", out)
            self.assertEqual([s[0] for s in status], ["1", "2"])
            for _n, _pid, st, ms in status:
                self.assertEqual(int(st), 9)             # raw wait status of a SIGKILLed child: the signal number
                self.assertGreaterEqual(int(ms), 1000)
                self.assertLess(int(ms), 2500)
            self.assertIn("SWEET hb: done rounds=2", out)

    def test_missing_ps_reports_exit_127_and_the_loop_goes_on(self):
        with tempfile.TemporaryDirectory() as t:
            con = Path(t) / "console"
            con.write_text("")
            rc, out, _ = self.run_hb(t, con, str(Path(t) / "no-such-ps"), rounds=2)
            self.assertEqual(rc, 0)
            self.assertEqual(re.findall(r" ps pid=\d+ status=(\d+) ms=\d+\n", out), [str(127 << 8)] * 2)
            self.assertNotIn("timeout-killed", out)
            self.assertIn("SWEET hb: done rounds=2", out)

    def test_missing_console_exits_2_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            con = Path(t) / "no-such-dir" / "console"
            rc, out, _ = self.run_hb(t, con, script(t, "ps", FAKE_PS), rounds=1)
            self.assertEqual(rc, 2)
            self.assertIsNone(out)

    def test_failing_fork_is_reported_with_the_negated_errno(self):
        def no_more_processes():
            resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))

        with tempfile.TemporaryDirectory() as t:
            con = Path(t) / "console"
            con.write_text("")
            rc, out, _ = self.run_hb(t, con, script(t, "ps", FAKE_PS), preexec=no_more_processes, rounds=2)
            if os.geteuid() == 0:
                self.skipTest("root is exempt from RLIMIT_NPROC")
            self.assertEqual(rc, 0)
            self.assertEqual(re.findall(r" ps pid=(-?\d+) status=0 ms=\d+\n", out), ["-11", "-11"])      # EAGAIN
            self.assertNotIn("fake-ps", out)
            self.assertIn("SWEET hb: done rounds=2", out)


def macho(cmds, cputype=0x0100000c, filetype=2):
    """A header plus load commands: cmds = [(cmd id, payload bytes after the 8-byte command header)]."""
    body = b"".join(struct.pack("<II", c, 8 + len(p)) + p for c, p in cmds)
    return struct.pack("<IiiIIIII", 0xfeedfacf, cputype, 0, filetype, len(cmds), len(body), 0, 0) + body


def seg(name):
    return (0x19, name.encode().ljust(16, b"\0") + b"\0" * 56)


GOOD = [seg("__PAGEZERO"), seg("__TEXT"), seg("__LINKEDIT"), (0x5, b"\0" * 8)]


class AuditRefusals(unittest.TestCase):
    def test_the_good_synthetic_header_passes(self):
        self.assertEqual(BH.audit(macho(GOOD))["segments"], ["__PAGEZERO", "__TEXT", "__LINKEDIT"])

    def test_refusals_with_their_messages(self):
        cases = [
            (macho(GOOD, cputype=7), "not an arm64 MH_EXECUTE"),
            (macho(GOOD, filetype=6), "not an arm64 MH_EXECUTE"),
            (macho(GOOD[:3]), "no LC_UNIXTHREAD"),
            (macho(GOOD + [(0x80000028, b"\0" * 16)]), "LC_MAIN present"),
            (macho(GOOD + [(0xc, b"\0" * 16)]), "LC_LOAD_DYLIB present"),
            (macho(GOOD + [(0xe, b"\0" * 16)]), "LC_LOAD_DYLINKER present"),
            (macho([seg("__PAGEZERO"), seg("__TEXT"), seg("__DATA"), seg("__LINKEDIT"), (0x5, b"\0" * 8)]), "segments .* not __PAGEZERO/__TEXT/__LINKEDIT"),
        ]
        for data, msg in cases:
            with self.assertRaisesRegex(BH.BuildError, msg):
                BH.audit(data)


class BuildParams(unittest.TestCase):
    def test_existing_output_directory_and_parameter_ranges(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(BH.BuildError, "exists: pick a new directory"):
                BH.build(t)
            for kw in ({"period": 0}, {"period": 61}, {"rounds": 0}, {"rounds": 601}, {"ps_timeout": 0}, {"ps_timeout": 31}):
                with self.assertRaisesRegex(BH.BuildError, "period 1..60"):
                    BH.build(Path(t) / "new", **kw)
                self.assertFalse((Path(t) / "new").exists())


class SourceDefaults(unittest.TestCase):
    def test_the_macro_defaults_of_hb_c_equal_the_builders_defaults(self):
        import inspect
        r = subprocess.run(["cc", "-E", "-dM", "-DHOST_TEST", str(SRC)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        macros = dict(re.findall(r"^#define (HB_\w+|CONSOLE_DEV|PS_PATH) (.*)$", r.stdout, re.M))
        d = {k: v.default for k, v in inspect.signature(BH.build).parameters.items()}
        self.assertEqual((int(macros["HB_PERIOD_S"]), int(macros["HB_ROUNDS"]), int(macros["HB_PS_TIMEOUT_S"])), (d["period"], d["rounds"], d["ps_timeout"]))
        self.assertEqual(macros["CONSOLE_DEV"], '"/dev/console"')
        self.assertEqual(macros["PS_PATH"], '"/bin/ps"')


def disassemble_svc_sites(data):
    """-> [(offset in __text, syscall number loaded by the nearest earlier write to x16/w16, or None)] for every `svc #0x80`."""
    import capstone
    off = 32
    magic, _cpu, _sub, _ft, ncmds, _sz, _fl, _r = struct.unpack_from("<IiiIIIII", data, 0)
    text = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x19 and data[off + 8:off + 24].split(b"\0")[0] == b"__TEXT":
            nsects = struct.unpack_from("<I", data, off + 64)[0]
            for i in range(nsects):
                s = off + 72 + 80 * i
                if data[s:s + 16].split(b"\0")[0] == b"__text":
                    addr, ssize, soff = struct.unpack_from("<QQI", data, s + 32)
                    text = (addr, ssize, soff)
        off += size
    assert text, "no __text"
    addr, ssize, soff = text
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    insns = list(md.disasm(data[soff:soff + ssize], addr))
    assert sum(i.size for i in insns) == ssize, "the section does not disassemble end to end (data in code?)"
    sites = []
    for idx, i in enumerate(insns):
        if i.mnemonic == "svc":
            assert i.op_str == "#0x80", i.op_str
            num = None
            for j in range(idx - 1, max(idx - 40, -1), -1):
                k = insns[j]
                first = k.op_str.split(",")[0].strip()
                if first in ("w16", "x16"):
                    m = re.fullmatch(r"(?:w|x)16, #(0x[0-9a-f]+|\d+)", k.op_str) if k.mnemonic == "mov" else None
                    num = int(m.group(1), 0) if m else None
                    break
            sites.append((i.address - addr, num))
    return sites, insns


class DarwinBinary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rec = BH.build(Path(cls.tmp.name) / "b")
        cls.data = (Path(cls.tmp.name) / "b" / "hb").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_binary_is_a_static_arm64_executable_of_the_expected_shape(self):
        self.assertEqual(self.rec["audit"]["segments"], ["__PAGEZERO", "__TEXT", "__LINKEDIT"])
        self.assertEqual(len(self.data), self.rec["hb"]["bytes"])
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), self.rec["hb"]["sha256"])
        self.assertLess(len(self.data), 32768)

    def test_every_svc_site_loads_one_of_the_intended_system_call_numbers(self):
        try:
            import capstone  # noqa: F401
        except ImportError:
            self.skipTest("capstone is not installed")
        sites, insns = disassemble_svc_sites(self.data)
        self.assertGreaterEqual(len(sites), 12)
        self.assertNotIn(None, [n for _o, n in sites], "a svc whose number is not a constant move")
        numbers = {n for _o, n in sites}
        # exit 1, fork 2, write 4, open 5, wait4 7, getpid 20, kill 37, getppid 39, execve 59, dup2 90, select 93, gettimeofday 116
        self.assertEqual(numbers, {1, 2, 4, 5, 7, 20, 37, 39, 59, 90, 93, 116})
        self.assertEqual(sum(1 for _o, n in sites if n == 2), 1, "exactly one fork site")
        self.assertEqual(sum(1 for _o, n in sites if n == 59), 1, "exactly one execve site")
        self.assertEqual(sum(1 for _o, n in sites if n == 37), 1, "exactly one kill site")

    def test_the_only_program_it_can_start_and_the_console_are_named_in_the_binary(self):
        self.assertEqual(self.data.count(b"/bin/ps\0"), 1)
        self.assertEqual(self.data.count(b"/dev/console\0"), 1)
        for forbidden in (b"/dev/rmd", b"/dev/disk", b"/dev/block", b"launchd", b"/redwood"):
            self.assertNotIn(forbidden, self.data)

    @staticmethod
    def without_host_model(text):
        """hb.c with every `#ifdef HOST_TEST` half dropped and every `#else` / `#ifndef HOST_TEST` half kept, by hand and not by the preprocessor (flat blocks only; a nested conditional inside one is refused)."""
        out, mode = [], None            # mode: None outside, "drop" in a host half, "keep" in a target half
        for line in text.split("\n"):
            s = line.strip()
            if mode is None and s in ("#ifdef HOST_TEST", "#ifndef HOST_TEST"):
                mode = "drop" if s == "#ifdef HOST_TEST" else "keep"
                continue
            if mode is not None:
                if s.startswith(("#if", "#ifdef", "#ifndef")):
                    raise AssertionError("a conditional nested inside a HOST_TEST block: " + line)
                if s == "#else":
                    mode = "keep" if mode == "drop" else "drop"
                    continue
                if s.startswith("#endif"):
                    mode = None
                    continue
                if mode == "drop":
                    continue
            out.append(line)
        assert mode is None
        return "\n".join(out)

    def test_the_host_model_code_is_not_part_of_the_darwin_binary(self):
        text = (HERE / "src/hb.c").read_text()
        stripped = self.without_host_model(text)
        self.assertNotIn("HOST_TEST", stripped)
        self.assertNotIn("#include <errno.h>", stripped)
        self.assertLess(len(stripped), len(text))
        with tempfile.TemporaryDirectory() as t:
            alt = Path(t) / "src"
            alt.mkdir()
            (alt / "hb.c").write_text(stripped)
            real = BH.SRC
            BH.SRC = alt
            try:
                rec = BH.build(Path(t) / "b")
            finally:
                BH.SRC = real
            self.assertEqual(rec["hb"]["sha256"], self.rec["hb"]["sha256"])
            self.assertEqual((Path(t) / "b" / "hb").read_bytes(), self.data)

    @unittest.skipUnless(HAVE, "local artifacts absent")
    def test_the_built_artifact_equals_a_fresh_build(self):
        self.assertEqual(json.loads(HBJ.read_text())["hb"]["sha256"], self.rec["hb"]["sha256"])


class RootBuilder(unittest.TestCase):
    def test_new_rc_inserts_the_block_before_the_exec_line(self):
        base = (BASE / "root/etc/rc").read_bytes() if HAVE else None
        if base is None:
            self.skipTest("local artifacts absent")
        new = BR.new_rc(base).decode()
        self.assertTrue(new.startswith(base.decode()[:-len(BR.EXEC_LINE)]))
        self.assertTrue(new.endswith(BR.RC_ADDITION + BR.EXEC_LINE))
        self.assertEqual(new.count("/redwood/bin/hb &\n"), 1)
        self.assertEqual(new.count(BR.EXEC_LINE), 1)

    def test_new_rc_refuses_an_unpinned_rc_and_a_misplaced_exec_line(self):
        with self.assertRaisesRegex(BR.BuildError, "the base etc/rc is sha256 .* not the pinned"):
            BR.new_rc(b"# some other rc\nexec /sbin/launchd.darwin\n")
        import unittest.mock as mock
        other = b"/bin/df\nexec /sbin/launchd.darwin\n/bin/ps -A\n"
        with mock.patch.object(BR, "BASE_RC_SHA256", hashlib.sha256(other).hexdigest()), \
                self.assertRaisesRegex(BR.BuildError, "does not end with the single line"):
            BR.new_rc(other)
        twice = b"exec /sbin/launchd.darwin\n/bin/df\nexec /sbin/launchd.darwin\n"
        with mock.patch.object(BR, "BASE_RC_SHA256", hashlib.sha256(twice).hexdigest()), \
                self.assertRaisesRegex(BR.BuildError, "does not end with the single line"):
            BR.new_rc(twice)

    def test_build_refusals(self):
        with tempfile.TemporaryDirectory() as t:
            hb = Path(t) / "hb"
            hb.write_bytes(b"not a mach-o")
            with self.assertRaisesRegex(BR.BuildError, "must be new"):
                BR.build(t, BASE, ROOT, hb)
            with self.assertRaisesRegex(BR.BuildError, "has no root.apfs and root/"):
                BR.build(Path(t) / "o1", t, ROOT, hb)
            (Path(t) / "root").mkdir()
            (Path(t) / "root.apfs").write_bytes(b"another image")
            with self.assertRaisesRegex(BR.BuildError, "the base root.apfs is sha256 .* not the pinned"):
                BR.build(Path(t) / "o2", t, ROOT, hb)

    @unittest.skipUnless(HAVE, "local artifacts absent")
    def test_a_non_static_hb_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            hb = Path(t) / "hb"
            hb.write_bytes(macho(GOOD + [(0xc, b"\0" * 16)]))
            with self.assertRaisesRegex(BR.BuildError, "not a static arm64 Mach-O: LC_LOAD_DYLIB present"):
                BR.build(Path(t) / "out", BASE, ROOT / "artifacts/ios-root/recipe", hb)
            self.assertFalse((Path(t) / "out").exists())


class BuildParamBoundaries(unittest.TestCase):
    """The ranges are closed intervals: the edge values pass the check (the build then reaches its first compiler call, replaced here by a sentinel), the values just outside do not."""

    class Stop(Exception):
        pass

    def reaches_the_compiler(self, **kw):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as t, mock.patch.object(BH.b77, "run", side_effect=self.Stop):
            try:
                BH.build(Path(t) / "new", **kw)
            except self.Stop:
                return True
            except BH.BuildError as e:
                self.assertIn("period 1..60", str(e))
                return False
        self.fail("the build finished without a compiler call")

    def test_edges_pass_and_the_values_outside_do_not(self):
        for kw in ({"period": 1}, {"period": 60}, {"rounds": 1}, {"rounds": 600}, {"ps_timeout": 1}, {"ps_timeout": 30}):
            self.assertTrue(self.reaches_the_compiler(**kw), kw)
        for kw in ({"period": 0}, {"period": 61}, {"rounds": 0}, {"rounds": 601}, {"ps_timeout": 0}, {"ps_timeout": 31}):
            self.assertFalse(self.reaches_the_compiler(**kw), kw)


class AuditSegmentName(unittest.TestCase):
    def test_a_segment_name_of_sixteen_bytes_is_read_whole_and_not_one_byte_further(self):
        name = "__SIXTEEN_BYTES_"        # fills the 16-byte field; the next byte (the low byte of vmaddr) must not become part of it
        self.assertEqual(len(name), 16)
        payload = name.encode() + b"\x41" + b"\0" * 55
        with self.assertRaises(BH.BuildError) as c:
            BH.audit(macho([(0x19, payload), (0x5, b"\0" * 8)]))
        self.assertIn("'%s'" % name, str(c.exception))


@unittest.skipUnless(HAVE, "local artifacts absent")
class BuilderEntryPoints(unittest.TestCase):
    """The command lines of both builders, run for real into a scratch directory with the default arguments (the values the recorded artifacts were built with)."""
    HB = ROOT / "artifacts/nat-101/hb-build-001/hb"

    def call(self, main, argv):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(argv)
        return buf.getvalue()

    def test_build_hb_main_builds_the_recorded_program_with_the_defaults(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "new"
            text = self.call(BH.main, ["--out", str(out)])
            rec = json.loads((out / "hb.json").read_text())
            self.assertEqual(rec["params"], {"period_s": 10, "rounds": 60, "ps_timeout_s": 8})
            data = (out / "hb").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), json.loads(HBJ.read_text())["hb"]["sha256"])
            self.assertEqual(text, "%s: %d bytes sha256 %s\n" % (out / "hb", len(data), hashlib.sha256(data).hexdigest()))
            self.assertTrue((out / "hb.json").read_text().endswith("}\n"))

    def test_hb_json_has_the_layout_of_the_recorded_one(self):
        """Line by line, the way the recorded hb.json is laid out (two-space indent, sorted keys, a final newline); only the two `commands` lines name a scratch directory and are compared by their indent."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "new"
            self.call(BH.main, ["--out", str(out)])
            got = (out / "hb.json").read_text().splitlines()
            want = HBJ.read_text().splitlines()
            self.assertEqual(len(got), len(want))
            scratch_lines = 0
            for g, w in zip(got, want):
                if "nat101-" in w:
                    scratch_lines += 1
                    self.assertEqual(len(g) - len(g.lstrip()), len(w) - len(w.lstrip()))
                    self.assertTrue(g.rstrip(",").endswith('"'), g)
                else:
                    self.assertEqual(g, w)
            self.assertEqual(scratch_lines, 2)

    def run_script(self, name, argv):
        """The script as the command line starts it (python <file> ...), in a scratch working directory: the `if __name__ == "__main__"` guard is what is under test."""
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-B", "-I", str(HERE / name)] + argv, capture_output=True, text=True, cwd=cwd, timeout=300)

    def test_build_hb_runs_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "new"
            r = self.run_script("build_hb.py", ["--out", str(out)])
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            data = (out / "hb").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), json.loads(HBJ.read_text())["hb"]["sha256"])
            self.assertEqual(r.stdout, "%s: %d bytes sha256 %s\n" % (out / "hb", len(data), hashlib.sha256(data).hexdigest()))
            r = self.run_script("build_hb.py", ["--out", str(out)])
            self.assertEqual(r.returncode, 1)
            self.assertIn("build_hb: ", r.stderr)

    def test_build_hb_root_runs_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "new"
            r = self.run_script("build_hb_root.py", ["--out", str(out), "--hb", str(self.HB)])
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            self.assertEqual((out / "root.apfs").read_bytes(), (OUT / "root.apfs").read_bytes())
            self.assertEqual(json.loads(r.stdout)["files"], 26)

    def test_build_hb_main_turns_a_refusal_into_a_prefixed_exit(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit) as c:
                BH.main(["--out", t])
            self.assertTrue(str(c.exception.code).startswith("build_hb: ") and "exists" in str(c.exception.code), c.exception.code)
            with self.assertRaises(SystemExit) as c:
                BH.main(["--out", str(Path(t) / "x"), "--period", "61"])
            self.assertTrue(str(c.exception.code).startswith("build_hb: period 1..60"), c.exception.code)
            self.assertFalse((Path(t) / "x").exists())

    def test_build_hb_root_main_builds_the_recorded_image_with_the_default_base_and_recipe(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "new"
            text = self.call(BR.main, ["--out", str(out), "--hb", str(self.HB)])
            printed = json.loads(text)
            rec = json.loads((out / "build.json").read_text())
            recorded = json.loads((OUT / "build.json").read_text())
            self.assertEqual(printed, {"root_apfs": rec["root_apfs"], "files": 26, "kernel_readback_ok": True})
            self.assertEqual(rec["root_apfs"]["sha256"], recorded["root_apfs"]["sha256"])
            self.assertEqual(hashlib.sha256((out / "root.apfs").read_bytes()).hexdigest(), recorded["root_apfs"]["sha256"])
            # the whole record equals the recorded one (script hash included) once the scratch directory is written the way the recorded run wrote its own
            self.assertEqual(json.loads(json.dumps(rec).replace(str(out), "artifacts/nat-101/pid1-hb")), recorded)

    def test_build_hb_root_main_turns_a_refusal_into_a_prefixed_exit(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit) as c:
                BR.main(["--out", t, "--hb", str(self.HB)])
            self.assertTrue(str(c.exception.code).startswith("build_hb_root: ") and "must be new" in str(c.exception.code), c.exception.code)

    def test_a_fresh_root_build_record_says_what_was_built_and_read_back(self):
        with tempfile.TemporaryDirectory() as t:
            rec = BR.build(Path(t) / "new", BASE, ROOT / "artifacts/ios-root/recipe", self.HB)
            hb = self.HB.read_bytes()
            self.assertEqual(rec["files"], 26)
            k = rec["kernel_apfs_lib_readback"]
            self.assertEqual((k["mismatches"], k["files_compared"], k["local_files"]), ([], 26, 26))
            self.assertGreater(k["entries"], 26)          # directories and links are listed too
            self.assertEqual(rec["verify_content"]["exit"], 0)
            self.assertEqual(rec["added"], {"bin/hb": {"sha256": hashlib.sha256(hb).hexdigest(), "mode": "755", "bytes": len(hb)}})
            self.assertEqual(rec["changed"]["etc/rc"]["base_sha256"], BR.BASE_RC_SHA256)
            self.assertEqual(rec["changed"]["etc/rc"]["addition"], BR.RC_ADDITION)
            self.assertEqual(rec["script_sha256"], hashlib.sha256((HERE / "build_hb_root.py").read_bytes()).hexdigest())
            self.assertIn("1024 blocks of 4096 bytes", rec["root_apfs"]["mkapfs_last_line"])
            text = (Path(t) / "new/build.json").read_text()
            self.assertNotIn(str(ROOT), text)
            self.assertTrue(text.endswith("}\n"))

    def tampered(self, how):
        """write_image with the local tree changed between the image build and the kernel's readback: the readback must name the file."""
        import unittest.mock as mock
        real = BR.B99.run
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "root"
            import shutil
            shutil.copytree(BASE / "root", root, symlinks=True)

            def wrapper(cmd, *a, **kw):
                if "census" in [str(c) for c in cmd]:
                    how(root)
                return real(cmd, *a, **kw)
            with mock.patch.object(BR.B99, "run", side_effect=wrapper):
                return BR.write_image(root, Path(t) / "img.apfs", ROOT / "artifacts/ios-root/recipe")["kernel"]

    def test_the_readback_names_a_file_whose_content_differs(self):
        k = self.tampered(lambda root: (root / "etc/rc").write_bytes(b"changed after the image was built\n"))
        self.assertEqual(k["mismatches"], ["/etc/rc"])

    def test_the_readback_names_a_file_whose_mode_differs(self):
        k = self.tampered(lambda root: (root / "etc/rc").chmod(0o600))
        self.assertEqual(k["mismatches"], ["/etc/rc (mode)"])

    def test_an_untouched_tree_reads_back_clean(self):
        k = self.tampered(lambda root: None)
        self.assertEqual((k["mismatches"], k["files_compared"]), ([], 25))


@unittest.skipUnless(HAVE, "local artifacts absent")
class RealImage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads((OUT / "build.json").read_text())
        cls.before = BR.tree(BASE / "root")
        cls.after = BR.tree(OUT / "root")

    def test_the_tree_differs_from_nat096s_in_bin_hb_and_etc_rc_only(self):
        added, removed, changed = BR.tree_diff(self.before, self.after)
        self.assertEqual((added, removed, changed), (["bin/hb"], [], ["etc/rc"]))
        self.assertEqual(sum(1 for v in self.before.values() if v[0] == "file"), 25)
        self.assertEqual(sum(1 for v in self.after.values() if v[0] == "file"), 26)

    def test_modes(self):
        self.assertEqual(self.after["bin/hb"][1], 0o755)
        self.assertEqual(self.after["etc/rc"][1], self.before["etc/rc"][1])

    def test_rc_in_the_image_is_the_base_rc_plus_the_block_before_exec(self):
        base = (BASE / "root/etc/rc").read_text()
        new = (OUT / "root/etc/rc").read_text()
        self.assertEqual(new, base[:-len(BR.EXEC_LINE)] + BR.RC_ADDITION + BR.EXEC_LINE)
        self.assertEqual(new.splitlines()[-2], "/redwood/bin/hb &")
        self.assertEqual(new.splitlines()[-1], "exec /sbin/launchd.darwin")

    def test_hb_in_the_image_is_the_built_program(self):
        h = hashlib.sha256((OUT / "root/bin/hb").read_bytes()).hexdigest()
        self.assertEqual(h, json.loads(HBJ.read_text())["hb"]["sha256"])
        self.assertEqual(h, self.rec["added"]["bin/hb"]["sha256"])
        self.assertEqual(BH.audit((OUT / "root/bin/hb").read_bytes())["segments"], ["__PAGEZERO", "__TEXT", "__LINKEDIT"])

    def test_every_other_file_is_byte_identical_to_nat096s(self):
        for p, v in self.before.items():
            if p != "etc/rc":
                self.assertEqual(self.after[p], v, p)

    def test_image_record_matches_the_file_and_the_readback_was_clean(self):
        img = OUT / "root.apfs"
        self.assertEqual(self.rec["root_apfs"]["sha256"], hashlib.sha256(img.read_bytes()).hexdigest())
        self.assertEqual(img.stat().st_size, 4194304)           # the md0 region of the image
        rb = self.rec["kernel_apfs_lib_readback"]
        self.assertEqual((rb["mismatches"], rb["files_compared"], rb["local_files"]), ([], 26, 26))
        self.assertEqual(self.rec["verify_content"]["exit"], 0)
        self.assertEqual(self.rec["base"]["root_apfs_sha256"], BR.BASE_ROOT_APFS_SHA256)

    def test_the_launchd_job_set_is_untouched(self):
        self.assertEqual(sorted(p for p in self.after if p.startswith("LaunchDaemons/")), sorted(p for p in self.before if p.startswith("LaunchDaemons/")))
        self.assertNotIn("LaunchDaemons/com.apple.backboardd.plist", self.after)
        self.assertNotIn("etc/inject.conf", self.after)


if __name__ == "__main__":
    unittest.main()
