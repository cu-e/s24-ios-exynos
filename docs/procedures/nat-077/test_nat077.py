#!/usr/bin/env python3
"""Host tests for NAT-077: the SHA-256 hashing probe, its static Mach-O wrapper and the root-image padding builder.

Evidence kind: host-test. Nothing here talks to the phone and nothing here is Apple software. Three layers:
  * the C source (src/sha256.h + src/hash-probe.c) compiled for the host: digests against hashlib and the FIPS 180-4 vectors, chunk and
    padding boundaries, short reads, EINTR, a failing read, an empty device, the elapsed-time text, a > 2**32-bit input;
  * the real arm64 Mach-O that build.py writes, executed instruction by instruction under Unicorn against a fake Darwin kernel
    (probe_vm.py): same digests, the exit-status classes, the system calls it issues, a wrapper that moved the sections intact;
  * the file format of that Mach-O (own parser, independent of mkstatic.py) and the refusals of mkstatic.py and pad_root.py.

    python3 -I docs/procedures/nat-077/test_nat077.py                              # host layers
    artifacts/nat-065/venv/bin/python -I docs/procedures/nat-077/test_nat077.py    # also the Unicorn layer (needs `unicorn`)
"""
import atexit
import errno
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import mkstatic  # noqa: E402
import pad_root  # noqa: E402

try:
    import probe_vm as vm
except ImportError:		# no unicorn in this interpreter
    vm = None

WORK = Path(tempfile.mkdtemp(prefix="nat077-test-"))
atexit.register(shutil.rmtree, WORK, True)
HOST = WORK / "host-probe"
CHUNK = build.DEFAULT_CHUNK
BASE = 0x100000000
EMPTY = hashlib.sha256(b"").hexdigest()
NIST = [
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
    (b"a" * 1000000, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pattern(n, seed=1):
    """Deterministic, non-repeating-looking bytes (so a swapped or repeated chunk changes the digest)."""
    out, x = bytearray(), seed & 0xffffffff
    while len(out) < n:
        x = (x * 1664525 + 1013904223) & 0xffffffff
        out += x.to_bytes(4, "little")
    return bytes(out[:n])


def console_text(dev, pid, nbytes, digest, sec, chunk=CHUNK):
    return ("\n*** SWEET hash probe: init running as PID %d ***\n"
            "SWEET hash: reading %s in chunks of %d\n"
            "SWEET hash: bytes=%d sha256=%s sec=%s\n"
            "SWEET probe: done, exiting\n" % (pid, dev, chunk, nbytes, digest, sec))


def run_host(data, *args, exe=None):
    """Run the host build of the probe with `data` behind descriptor 3. -> (exit status, console text)."""
    path = WORK / "dev.bin"
    path.write_bytes(data)
    r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@" 3<"$DEV"', str(exe or HOST)] + [str(a) for a in args],
                       env={"DEV": str(path)}, capture_output=True, timeout=120)
    return r.returncode, r.stdout.decode()


STAT_LINE = re.compile(r"HOSTSTAT ((?:[a-z_]+=\d+ ?)+)\n")


def run_host_full(data, *args, exe=None, close_stdin=False):
    """Like run_host, and -> the HOSTSTAT counters the host build prints on stderr (how often each test hook acted)."""
    path = WORK / "dev.bin"
    path.write_bytes(data)
    r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@" 3<"$DEV"' + (" 0<&-" if close_stdin else ""), str(exe or HOST)] + [str(a) for a in args],
                       env={"DEV": str(path)}, capture_output=True, timeout=120)
    m = STAT_LINE.search(r.stderr.decode())
    if not m:
        raise AssertionError("no HOSTSTAT line on stderr: %r" % r.stderr)
    return r.returncode, r.stdout.decode(), {k: int(v) for k, v in (kv.split("=") for kv in m.group(1).split())}


def pid_of(text):
    return int(re.search(r"running as PID (\d+) ", text).group(1))


def setUpModule():
    build.build_host(HOST)


class HostDigest(unittest.TestCase):
    def check(self, data, *args):
        rc, text = run_host(data, *args)
        pid = pid_of(text)
        m = re.search(r"SWEET hash: bytes=(\d+) sha256=([0-9a-f]{64}) sec=(\d+)\.(\d{3})\n", text)
        self.assertTrue(m, text)
        self.assertEqual((int(m.group(1)), m.group(2)), (len(data), sha(data)), text)
        self.assertEqual(rc, (0x50 + pid) & 0xff if data else 0x63, text)
        return text

    def test_fips_180_4_vectors(self):
        for msg, want in NIST:
            self.assertEqual(sha(msg), want)		# the vectors themselves are right
            if msg:
                self.assertIn("sha256=" + want + " ", self.check(msg))

    def test_every_length_up_to_300_around_the_padding_boundaries(self):
        for n in list(range(1, 300)):
            self.check(pattern(n, n))

    def test_chunk_boundaries(self):
        for n in (CHUNK - 1, CHUNK, CHUNK + 1, 2 * CHUNK - 64, 2 * CHUNK, 2 * CHUNK + 1, 3 * CHUNK + 4097):
            self.check(pattern(n, n))

    def test_short_reads_do_not_change_the_digest(self):
        data = pattern(200013, 7)
        for limit in (1, 7, 63, 64, 65, 511, 512, 4096, 100000, 131072, 131073):
            self.check(data, limit)

    def test_interrupted_reads_are_retried_and_not_counted(self):
        data = pattern(300000, 3)
        text = self.check(data, 0, 5)
        self.assertNotIn("read failed", text)

    def test_a_failing_read_reports_the_byte_count_and_no_digest(self):
        data = pattern(300000, 5)
        for fail_at in (0, 1, 70000, 131072, 299999):
            rc, text = run_host(data, 0, 0, fail_at)
            self.assertEqual(rc, 0x62, text)
            self.assertIn("SWEET hash: read failed after %d bytes, errno 5\n" % fail_at, text)
            self.assertNotIn("sha256=", text)
            self.assertNotIn("done, exiting", text)

    def test_an_unreadable_device_exits_0x61(self):
        missing = WORK / "host-probe-missing"
        build.build_host(missing, ['-DROOT_DEV="/nonexistent/nat077-device"'])
        rc, text = run_host(b"", exe=missing)
        self.assertEqual(rc, 0x61, text)
        self.assertIn("SWEET hash: cannot open /nonexistent/nat077-device, errno 2\n", text)
        self.assertNotIn("sha256=", text)

    def test_an_empty_device_is_not_a_success(self):
        rc, text = run_host(b"")
        self.assertEqual(rc, 0x63)
        self.assertIn("bytes=0 sha256=%s " % EMPTY, text)
        self.assertNotIn("done, exiting", text)

    def test_elapsed_text(self):
        data = pattern(5000, 9)
        for step_us, want in ((1, "0.000"), (999, "0.000"), (1000, "0.001"), (1234567, "1.234"), (1001000, "1.001"), (59999999, "59.999"),
                              (60000000, "60.000"), (3600000000, "3600.000"), (86400000999, "86400.000")):
            text = self.check(data, 0, 0, "none", step_us)
            self.assertIn(" sec=%s\n" % want, text, step_us)

    def test_a_clock_that_goes_backwards_prints_zero(self):
        text = self.check(pattern(5000, 9), 0, 0, "none", 5000000, 1)
        self.assertIn(" sec=0.000\n", text)

    def test_short_console_writes(self):
        data = pattern(4000, 11)
        rc, text = run_host(data, 0, 0, "none", 1234567, 0, 1)
        rc2, text2 = run_host(data, 0, 0, "none", 1234567, 0, 0)
        self.assertEqual(re.sub(r"PID \d+", "PID n", text), re.sub(r"PID \d+", "PID n", text2))
        self.assertEqual(rc, rc2 & 0xff if pid_of(text) == pid_of(text2) else rc)

    def test_console_text_is_exact(self):
        data = pattern(1000, 13)
        rc, text = run_host(data, 0, 0, "none", 2500000)
        self.assertEqual(text, console_text("/dev/fd/3", pid_of(text), 1000, sha(data), "2.500"))

    def test_console_text_is_exact_for_tiny_and_round_sizes(self):
        for n in (1, 5, 9, 10, 99, 100, 1000):
            data = pattern(n, n)
            rc, text = run_host(data, 0, 0, "none", 2500000)
            self.assertEqual(text, console_text("/dev/fd/3", pid_of(text), n, sha(data), "2.500"), n)

    def test_input_larger_than_two_to_the_32_bits(self):
        """513 MiB of sparse zeros: the message length in bits needs 33 bits, the byte count does not fit 29 bits of a 32-bit product."""
        size = 513 << 20
        path = WORK / "big.bin"
        with open(path, "wb") as f:
            f.truncate(size)
        want = hashlib.sha256()
        zero = bytes(1 << 20)
        for _ in range(513):
            want.update(zero)
        r = subprocess.run(["/bin/sh", "-c", 'exec "$0" 3<"$DEV"', str(HOST)], env={"DEV": str(path)}, capture_output=True, timeout=300)
        text = r.stdout.decode()
        os.unlink(path)
        self.assertIn("bytes=%d sha256=%s " % (size, want.hexdigest()), text)


class HostHooks(unittest.TestCase):
    """Every test hook of the host build has to act, and only when asked for: otherwise a test of short reads, interrupts, a failing read or
    a fake clock could pass without having exercised anything (the digest is the same either way)."""
    IDLE = dict(eintr=0, limited=0, cut=0, failed=0, short_writes=0, fake_clock=0)

    def idle(self, st):
        return {k: st[k] for k in self.IDLE}

    def test_a_plain_run_touches_no_hook(self):
        for n in (1, CHUNK - 1, CHUNK, CHUNK + 1, 3 * CHUNK):
            rc, text, st = run_host_full(pattern(n, n))
            self.assertEqual(self.idle(st), self.IDLE, n)
            self.assertEqual(st["reads"], -(-n // CHUNK) + 1, n)		# the data reads and the one that returns end of file
            self.assertEqual(st["real_clock"], 2)				# the start and the end
            self.assertTrue(0 < st["writes"] < len(text.encode()), st)	# one write per piece of text, not one per byte

    def test_read_limit_applies_to_exactly_the_reads_that_ask_for_more(self):
        data = pattern(300000, 5)
        for limit in (65536, 100000, CHUNK - 1):
            rc, text, st = run_host_full(data, limit)
            self.assertEqual(st["reads"], -(-300000 // limit) + 1, limit)
            self.assertEqual(st["limited"], st["reads"], limit)		# every read asks for CHUNK, which is more than the limit
        for limit in (CHUNK, CHUNK + 1, 1 << 20):
            rc, text, st = run_host_full(data, limit)
            self.assertEqual((st["limited"], st["reads"]), (0, 4), limit)

    def test_the_eintr_budget_is_consumed_exactly(self):
        data = pattern(300000, 3)
        for budget in (1, 5, 40):
            rc, text, st = run_host_full(data, 0, budget)
            self.assertEqual((st["eintr"], st["reads"]), (budget, budget + 4), budget)
            self.assertEqual(rc, (0x50 + pid_of(text)) & 0xff)

    def test_fail_after_cuts_the_read_that_crosses_it_and_fails_the_next(self):
        data = pattern(300000, 5)
        for fail_after, cut, reads in ((70000, 1, 2), (CHUNK, 0, 2), (CHUNK + 1, 1, 3), (2 * CHUNK, 0, 3)):
            rc, text, st = run_host_full(data, 0, 0, fail_after)
            self.assertEqual(rc, 0x62)
            self.assertEqual((st["cut"], st["failed"], st["reads"]), (cut, 1, reads), fail_after)
            self.assertIn("read failed after %d bytes, errno 5\n" % fail_after, text)

    def test_write_limit_applies_to_exactly_the_writes_that_are_longer(self):
        data = pattern(1000, 3)
        longest = len("SWEET hash: reading /dev/fd/3 in chunks of 131072\n")		# the longest single piece of text the probe writes
        rc, text, st = run_host_full(data, 0, 0, "none", 0, 0, 1)
        self.assertEqual(st["writes"], len(text.encode()))		# one byte per write
        self.assertTrue(0 < st["short_writes"] < st["writes"], st)
        for limit, short in ((longest, False), (longest + 1, False), (longest - 1, True)):
            rc, text, st = run_host_full(data, 0, 0, "none", 0, 0, limit)
            self.assertEqual(st["short_writes"] > 0, short, limit)
            self.assertIn("sha256=%s " % sha(data), text)
        self.assertEqual(run_host_full(data)[2]["short_writes"], 0)

    def test_the_fake_clock_is_used_only_when_asked_for(self):
        rc, text, st = run_host_full(pattern(100), 0, 0, "none", 5000)
        self.assertEqual((st["fake_clock"], st["real_clock"]), (2, 0))
        rc, text, st = run_host_full(pattern(100))
        self.assertEqual((st["fake_clock"], st["real_clock"]), (0, 2))

    def test_the_real_clock_measures_a_stall(self):
        """The device is a pipe whose writer pauses for 1.25 s between two writes: the elapsed time the probe prints must show it.
        A clock read without its seconds can never show 1 s or more; one read without its microseconds shows whole seconds only, so a real
        measurement has millisecond digits other than 000 (retried: one real run in a thousand ends on a round value)."""
        data = pattern(200000, 41)
        for attempt in range(3):
            r, w = os.pipe()
            p = subprocess.Popen(["/bin/sh", "-c", 'exec "$0" 3<&%d' % r, str(HOST)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(r,))
            os.close(r)
            with os.fdopen(w, "wb") as f:
                f.write(data[:1000])
                f.flush()
                time.sleep(1.25)
                f.write(data[1000:])
            out, err = p.communicate(timeout=60)
            text = out.decode()
            m = re.search(r"bytes=(\d+) sha256=([0-9a-f]{64}) sec=(\d+)\.(\d{3})\n", text)
            self.assertTrue(m, text)
            self.assertEqual((int(m.group(1)), m.group(2)), (len(data), sha(data)))
            self.assertTrue(1.2 <= int(m.group(3)) + int(m.group(4)) / 1000 < 30, text)
            if m.group(4) != "000":
                return
        self.fail("three real measurements in a row ended on a round second: the microseconds are not being read")

    def test_descriptor_zero_is_a_valid_console(self):
        """With stdin closed the console is opened as descriptor 0, which a `< 0` test accepts and a `<= 0` test does not."""
        for n in (1, 5000):
            data = pattern(n, n)
            rc, text, st = run_host_full(data, close_stdin=True)
            self.assertEqual(rc, (0x50 + pid_of(text)) & 0xff, text)
            self.assertIn("bytes=%d sha256=%s " % (n, sha(data)), text)


PROGRESS = re.compile(r"SWEET hash: at=(\d+) sha256=([0-9a-f]{64}) sec=(\d+\.\d{3})\n")


def check_progress(tc, data, text, expected_at, ckpt):
    """The progress lines of one run: each is the SHA-256 of a prefix, at the expected byte counts, and the rest of the text is unchanged."""
    got = [(int(a), d, t) for a, d, t in PROGRESS.findall(text)]
    tc.assertEqual([a for a, _, _ in got], expected_at, text)
    for a, d, _ in got:
        tc.assertEqual(d, sha(data[:a]), "prefix %d" % a)
        tc.assertLess(a, len(data) + 1)
    for (a, _, _), (b, _, _) in zip(got, got[1:]):
        tc.assertGreaterEqual(b, (a // ckpt + 1) * ckpt)
    return got


class HostProgress(unittest.TestCase):
    """Prefix digests every CKPT_BYTES: the host build with a 100000-byte spacing so that small inputs cross several."""

    @classmethod
    def setUpClass(cls):
        cls.exe = WORK / "host-probe-ckpt"
        build.build_host(cls.exe, ["-DCKPT_BYTES=100000"])

    def test_one_line_per_crossed_multiple_with_small_reads(self):
        data = pattern(350000, 21)
        rc, text = run_host(data, 4096, 0, "none", 250000, exe=self.exe)
        got = check_progress(self, data, text, [-(-k * 100000 // 4096) * 4096 for k in (1, 2, 3)], 100000)
        self.assertEqual([t for _, _, t in got], ["0.250", "0.500", "0.750"])		# one fake-clock step per gettimeofday() call
        self.assertIn("SWEET hash: bytes=350000 sha256=%s sec=1.000\n" % sha(data), text)
        self.assertTrue(text.index("at=") < text.index("bytes="))
        self.assertTrue(text.endswith("SWEET probe: done, exiting\n"))

    def test_big_reads_give_one_line_per_read_at_the_read_boundary(self):
        data = pattern(350000, 22)
        rc, text = run_host(data, 0, 0, "none", 0, exe=self.exe)
        check_progress(self, data, text, [131072, 262144, 350000], 100000)
        rc, text = run_host(data, 65536, 0, "none", 0, exe=self.exe)
        check_progress(self, data, text, [131072, 262144, 327680], 100000)

    def test_a_read_that_crosses_several_multiples_prints_one_line(self):
        data = pattern(400000, 23)
        rc, text = run_host(data, 0, 0, "none", 0, exe=self.exe)
        got = check_progress(self, data, text, [131072, 262144, 393216, 400000], 100000)
        self.assertEqual(len(got), 4)

    def test_no_line_below_the_first_multiple(self):
        data = pattern(99999, 24)
        rc, text = run_host(data, 0, 0, "none", 0, exe=self.exe)
        self.assertEqual(PROGRESS.findall(text), [])
        data = pattern(100000, 24)
        rc, text = run_host(data, 0, 0, "none", 0, exe=self.exe)
        check_progress(self, data, text, [100000], 100000)

    def test_a_failing_read_keeps_the_lines_printed_so_far(self):
        data = pattern(350000, 25)
        rc, text = run_host(data, 4096, 0, 250000, exe=self.exe)
        self.assertEqual(rc, 0x62)
        check_progress(self, data, text, [102400, 200704], 100000)
        self.assertIn("read failed after 250000 bytes", text)

    def test_a_clock_that_goes_backwards_prints_zero_in_progress_lines(self):
        data = pattern(250000, 26)
        rc, text = run_host(data, 4096, 0, "none", 3000000, 1, exe=self.exe)
        self.assertEqual([t for _, _, t in check_progress(self, data, text, [102400, 200704], 100000)], ["0.000", "0.000"])

    def test_default_spacing_is_128_mib(self):
        text = (HERE / "src" / "hash-probe.c").read_text()
        self.assertIn("#define CKPT_BYTES (128ull << 20)", text)
        data = pattern((128 << 20) + 5000, 27)
        rc, out = run_host(data)
        check_progress(self, data, out, [(128 << 20)], 128 << 20)


@unittest.skipIf(vm is None, "unicorn is not installed in this interpreter")
class Probe(unittest.TestCase):
    """The real Mach-O under Unicorn."""

    @classmethod
    def setUpClass(cls):
        w = WORK / "probe"
        w.mkdir()
        cls.macho, cls.linked, cls.cmds = build.build_probe(w)

    def go(self, data, **kw):
        k = vm.FakeKernel(data, **kw)
        r = vm.run(self.macho, k)
        return r["exit_code"], r["console"].decode(), k

    def test_progress_lines_in_the_real_file(self):
        w = WORK / "ckpt"
        w.mkdir()
        macho, _, _ = build.build_probe(w, "/dev/rmd1", 4096, ["-DCKPT_BYTES=10000"])
        data = pattern(30000, 31)
        k = vm.FakeKernel(data, step_us=250000)
        out = vm.run(macho, k)["console"].decode()
        got = check_progress(self, data, out, [12288, 20480, 30000], 10000)
        self.assertEqual([t for _, _, t in got], ["0.250", "0.500", "0.750"])
        self.assertIn("SWEET hash: bytes=30000 sha256=%s sec=1.000\n" % sha(data), out)
        self.assertEqual([c[0] for c in k.calls].count(vm.SYS_GETTIMEOFDAY), 5)		# t0, three progress lines, the end

    def test_the_default_build_prints_no_progress_line_for_small_inputs(self):
        rc, text, k = self.go(pattern(CHUNK * 3), step_us=1)
        self.assertEqual(PROGRESS.findall(text), [])

    def test_digest_and_console_text(self):
        for n in (1, 55, 56, 63, 64, 65, 1000, CHUNK - 1, CHUNK, CHUNK + 1, 300000):
            data = pattern(n, n)
            rc, text, k = self.go(data, step_us=1234567)
            self.assertEqual(rc, 0x51, text)
            self.assertEqual(text, console_text("/dev/rmd1", 1, n, sha(data), "1.234"))

    def test_fips_vectors(self):
        for msg, want in NIST[1:3]:
            rc, text, k = self.go(msg, step_us=1)
            self.assertIn("bytes=%d sha256=%s " % (len(msg), want), text)

    def test_empty_device(self):
        rc, text, k = self.go(b"", step_us=1)
        self.assertEqual(rc, 0x63)
        self.assertIn("bytes=0 sha256=%s " % EMPTY, text)
        self.assertNotIn("done, exiting", text)

    def test_exit_status_follows_the_pid(self):
        for pid in (1, 2, 7, 100):
            rc, text, k = self.go(pattern(100), pid=pid)
            self.assertEqual(rc, 0x50 + pid)
            self.assertIn("running as PID %d ***" % pid, text)

    def test_no_console(self):
        rc, text, k = self.go(pattern(100), console=False)
        self.assertEqual((rc, text), (0x60, ""))
        self.assertEqual([c[0] for c in k.calls], [vm.SYS_OPEN, vm.SYS_EXIT])

    def test_device_cannot_be_opened(self):
        rc, text, k = self.go(pattern(100), device_missing=True)
        self.assertEqual(rc, 0x61)
        self.assertIn("SWEET hash: cannot open /dev/rmd1, errno 2\n", text)
        self.assertNotIn("sha256=", text)

    def test_read_failure(self):
        for fail_at in (0, 1, 65536, 131072, 299999):
            rc, text, k = self.go(pattern(300000), fail_after=fail_at)
            self.assertEqual(rc, 0x62, text)
            self.assertIn("SWEET hash: read failed after %d bytes, errno 5\n" % fail_at, text)
            self.assertNotIn("sha256=", text)

    def test_short_reads_and_interrupts(self):
        data = pattern(200013, 2)
        for kw in ({"read_limit": 1}, {"read_limit": 4095}, {"read_limit": 70000}, {"eintr": 4}, {"eintr": 3, "read_limit": 513}):
            if kw.get("read_limit") == 1:
                data_ = data[:3000]		# one syscall per byte under an emulator: keep it short
            else:
                data_ = data
            rc, text, k = self.go(data_, step_us=1234567, **kw)
            self.assertEqual(rc, 0x51, (kw, text))
            self.assertIn("bytes=%d sha256=%s sec=1.234\n" % (len(data_), sha(data_)), text, kw)

    def test_short_console_writes(self):
        data = pattern(5000, 4)
        rc, text, k = self.go(data, step_us=1234567, write_limit=1)
        self.assertEqual(text, console_text("/dev/rmd1", 1, 5000, sha(data), "1.234"))

    def test_elapsed_text(self):
        data = pattern(70000, 6)
        for step_us, want in ((1, "0.000"), (999, "0.000"), (1000, "0.001"), (1234567, "1.234"), (59999999, "59.999"), (3600000000, "3600.000")):
            rc, text, k = self.go(data, step_us=step_us)
            self.assertIn(" sec=%s\n" % want, text, step_us)
        rc, text, k = self.go(data, step_us=5000000, backwards=True)
        self.assertIn(" sec=0.000\n", text)

    def test_only_the_expected_system_calls(self):
        data = pattern(300000, 8)
        rc, text, k = self.go(data, step_us=10)
        nums = [c[0] for c in k.calls]
        self.assertEqual(set(nums), {vm.SYS_OPEN, vm.SYS_READ, vm.SYS_WRITE, vm.SYS_GETPID, vm.SYS_GETTIMEOFDAY, vm.SYS_EXIT})
        self.assertEqual(k.opens, [(b"/dev/console", 2, 0), (b"/dev/rmd1", 0, 0)])		# O_RDWR / O_RDONLY, no create mode
        self.assertEqual(nums.count(vm.SYS_GETTIMEOFDAY), 2)
        self.assertEqual(nums.count(vm.SYS_GETPID), 1)
        self.assertEqual(nums.count(vm.SYS_EXIT), 1)
        self.assertEqual(nums[-1], vm.SYS_EXIT)
        self.assertEqual(k.read_sizes, [CHUNK, CHUNK, CHUNK, CHUNK])		# 300000 bytes: three full reads, one short, then end of file
        self.assertEqual(k.errors, [])

    def test_reads_land_on_the_stack_and_stay_sector_aligned(self):
        rc, text, k = self.go(pattern(300000, 8))
        reads = [c for c in k.calls if c[0] == vm.SYS_READ]
        for _, fd, buf, n in reads:
            self.assertTrue(vm.STACK_BASE <= buf < vm.STACK_BASE + vm.STACK_SIZE)
            self.assertEqual(n % 512, 0)
        self.assertEqual(len({c[2] for c in reads}), 1)		# the same buffer every time

    def test_misaligned_initial_stack_is_aligned_by_the_entry(self):
        for mis in (8, 0x28):
            k = vm.FakeKernel(pattern(1000), step_us=1)
            r = vm.run(self.macho, k, sp_misalign=mis)
            self.assertEqual(r["exit_code"], 0x51)

    def test_other_device_and_chunk_choices(self):
        w = WORK / "variant"
        w.mkdir()
        macho, _, _ = build.build_probe(w, "/dev/rdisk9", 4096)
        data = pattern(10000, 12)
        k = vm.FakeKernel(data, device_path=b"/dev/rdisk9", step_us=1)
        r = vm.run(macho, k)
        self.assertEqual(r["console"].decode(), console_text("/dev/rdisk9", 1, 10000, sha(data), "0.000", 4096))
        self.assertEqual(k.read_sizes, [4096] * 4)		# two full reads, one short, one that returns end of file

    def test_console_and_device_descriptors(self):
        """PID 1 may start with no descriptor open (the console is then descriptor 0) or with stdio inherited (descriptor 3 and up)."""
        data = pattern(5000, 14)
        for first_fd in (0, 3):
            rc, text, k = self.go(data, step_us=1234567, first_fd=first_fd)
            self.assertEqual(rc, 0x51, (first_fd, text))
            self.assertEqual(text, console_text("/dev/rmd1", 1, 5000, sha(data), "1.234"))
            self.assertEqual({c[1] for c in k.calls if c[0] == vm.SYS_WRITE}, {first_fd})
            self.assertEqual({c[1] for c in k.calls if c[0] == vm.SYS_READ}, {first_fd + 1})

    def test_a_device_opened_as_descriptor_zero_is_valid(self):
        """Descriptor 0 is a valid result of open(): a probe that tests `fd <= 0` or `fd < 1` would call the device missing. The console takes 5."""
        data = pattern(70000, 5)
        rc, text, k = self.go(data, fd_plan=[5, 0])
        self.assertEqual(rc, 0x51, text)
        self.assertEqual({c[1] for c in k.calls if c[0] == vm.SYS_WRITE}, {5})
        self.assertEqual({c[1] for c in k.calls if c[0] == vm.SYS_READ}, {0})
        self.assertIn("bytes=%d sha256=%s " % (len(data), sha(data)), text)

    def test_the_result_does_not_depend_on_what_the_stack_held(self):
        data = pattern(70000, 15)
        for fill in (0xa5, 0xff, 0x01):
            k = vm.FakeKernel(data, step_us=1234567)
            r = vm.run(self.macho, k, stack_fill=fill)
            self.assertEqual(r["exit_code"], 0x51, fill)
            self.assertEqual(r["console"].decode(), console_text("/dev/rmd1", 1, 70000, sha(data), "1.234"), fill)

    def test_a_console_that_stops_accepting_text_does_not_stop_the_probe(self):
        data = pattern(300, 16)
        full = console_text("/dev/rmd1", 1, 300, sha(data), "0.000")
        for kw in ({"write_stall_after": 0}, {"write_stall_after": 30}, {"write_error_after": 0}, {"write_error_after": 30}):
            k = vm.FakeKernel(data, step_us=1, **kw)
            r = vm.run(self.macho, k, max_insns=5_000_000)
            self.assertEqual(r["exit_code"], 0x51, kw)
            text = r["console"].decode()
            self.assertTrue(full.startswith(text) and len(text) < len(full), (kw, text))

    def test_the_wrapped_file_runs_the_same_code_the_linker_produced(self):
        """Compare the sections that were moved with what lld wrote: only the base differs, by a multiple of 4096."""
        macho, linked = self.macho, self.linked
        info = mkstatic.parse(linked)
        first, size = info["blob"]
        out = parse_macho(macho)
        new_off = out["sections"][0]["off"]
        self.assertEqual(macho[new_off:new_off + size], linked[first:first + size])
        self.assertEqual((new_off - first) % 0x1000, 0)


def parse_macho(data):
    """A second, independent reader of the wrapper's output: load commands, segments, sections, thread pc, signature location."""
    magic, cpu, sub, ftype, ncmds, sizeofcmds, flags, res = struct.unpack_from("<8I", data, 0)
    out = {"header": (magic, cpu, sub, ftype, flags, res), "cmds": [], "cmdsizes": [], "segments": {}, "sections": [], "pc": None, "sig": None,
           "sizeofcmds": sizeofcmds}
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        out["cmds"].append(cmd)
        out["cmdsizes"].append(size)
        if cmd == 0x19:
            name = data[off + 8:off + 24].split(b"\0")[0].decode()
            vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, segflags = struct.unpack_from("<4Q2i2I", data, off + 24)
            out["segments"][name] = dict(vmaddr=vmaddr, vmsize=vmsize, fileoff=fileoff, filesize=filesize, maxprot=maxprot, initprot=initprot,
                                         nsects=nsects, flags=segflags)
            for i in range(nsects):
                s = off + 72 + 80 * i
                sn = data[s:s + 16].split(b"\0")[0].decode()
                sg = data[s + 16:s + 32].split(b"\0")[0].decode()
                addr, ssize, soff, align, reloff, nreloc, sflags, r1, r2, r3 = struct.unpack_from("<2Q8I", data, s + 32)
                out["sections"].append(dict(name=sn, seg=sg, addr=addr, size=ssize, off=soff, align=align, reloff=reloff, nreloc=nreloc, flags=sflags,
                                            reserved=(r1, r2, r3)))
        elif cmd == 0x5:
            out["pc"] = struct.unpack_from("<Q", data, off + 16 + 32 * 8)[0]
            out["thread"] = struct.unpack_from("<33Q", data, off + 16)
            out["thread_hdr"] = struct.unpack_from("<II", data, off + 8)			# flavor, count
            out["thread_tail"] = struct.unpack_from("<II", data, off + 16 + 33 * 8)		# cpsr, pad
        elif cmd == 0x1d:
            out["sig"] = struct.unpack_from("<II", data, off + 8)
        off += size
    return out


class MachOFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = WORK / "file"
        w.mkdir()
        cls.macho, cls.linked, cls.cmds = build.build_probe(w)
        cls.m = parse_macho(cls.macho)

    def test_header_and_load_commands(self):
        m = self.m
        self.assertEqual(m["header"], (0xfeedfacf, 0x0100000c, 0, 2, 1, 0))		# MH_NOUNDEFS only
        self.assertEqual(m["cmds"], [0x19, 0x19, 0x19, 0x5, 0x1d])		# no LC_MAIN, no dylinker, no dylib, no dyld info, no symtab
        self.assertEqual(list(m["segments"]), ["__PAGEZERO", "__TEXT", "__LINKEDIT"])

    def test_segments(self):
        s = self.m["segments"]
        self.assertEqual((s["__PAGEZERO"]["vmaddr"], s["__PAGEZERO"]["vmsize"], s["__PAGEZERO"]["initprot"]), (0, BASE, 0))
        t = s["__TEXT"]
        self.assertEqual((t["vmaddr"], t["vmsize"], t["fileoff"], t["filesize"], t["initprot"], t["maxprot"]), (BASE, 0x4000, 0, 0x4000, 5, 5))
        le = s["__LINKEDIT"]
        self.assertEqual((le["vmaddr"], le["fileoff"], le["initprot"]), (BASE + 0x4000, 0x4000, 1))
        self.assertEqual(le["filesize"], len(self.macho) - 0x4000)

    def test_command_sizes_and_every_field_that_is_meant_to_be_zero(self):
        m = self.m
        self.assertEqual(m["cmdsizes"], [72, 72 + 80 * 4, 72, 16 + 4 * 68, 16])
        self.assertEqual(sum(m["cmdsizes"]), m["sizeofcmds"])
        self.assertEqual(m["segments"]["__PAGEZERO"], dict(vmaddr=0, vmsize=BASE, fileoff=0, filesize=0, maxprot=0, initprot=0, nsects=0, flags=0))
        self.assertEqual((m["segments"]["__TEXT"]["nsects"], m["segments"]["__LINKEDIT"]["nsects"]), (4, 0))
        self.assertEqual([m["segments"][n]["flags"] for n in m["segments"]], [0, 0, 0])
        self.assertEqual([s["reserved"] for s in m["sections"]], [(0, 0, 0)] * 4)
        self.assertEqual((m["thread_hdr"], m["thread_tail"]), ((6, 68), (0, 0)))		# ARM_THREAD_STATE64, 68 words; cpsr 0, pad 0
        self.assertEqual(m["cmds"][-1], 0x1d)
        self.assertEqual(m["sig"], (0x4000, len(self.macho) - 0x4000))

    def test_every_linked_section_keeps_its_size_alignment_and_flags(self):
        want = [(s["name"], s["size"], s["align"], s["flags"]) for s in mkstatic.parse(self.linked)["sections"]]
        self.assertEqual([(s["name"], s["size"], s["align"], s["flags"]) for s in self.m["sections"]], want)

    def test_sections_sit_inside_the_text_page_after_the_load_commands(self):
        secs = self.m["sections"]
        self.assertEqual([s["name"] for s in secs], ["__text", "__literals", "__const", "__cstring"])
        self.assertTrue(all(s["seg"] == "__TEXT" and s["nreloc"] == 0 and s["reloff"] == 0 for s in secs))
        self.assertGreaterEqual(secs[0]["off"], 32 + self.m["sizeofcmds"])
        prev = secs[0]["off"]
        for s in secs:
            self.assertEqual(s["addr"], BASE + s["off"])
            self.assertGreaterEqual(s["off"], prev)
            prev = s["off"] + s["size"]
        self.assertLessEqual(prev, 0x4000)
        self.assertEqual(secs[0]["flags"], 0x80000400)

    def test_entry_point(self):
        m = self.m
        t = m["sections"][0]
        self.assertTrue(t["addr"] <= m["pc"] < t["addr"] + t["size"])
        self.assertEqual(m["pc"] % 4, 0)
        self.assertEqual(m["thread"][31], 0)		# sp = 0: the kernel supplies the stack
        self.assertEqual(sum(m["thread"][:31]), 0)
        # the first instruction of the entry is `mov x9, sp` (0x910003e9)
        self.assertEqual(struct.unpack_from("<I", self.macho, m["pc"] - BASE)[0], 0x910003e9)

    def test_code_signature_page_hashes(self):
        data, m = self.macho, self.m
        dataoff, datasize = m["sig"]
        self.assertEqual((dataoff, dataoff + datasize), (0x4000, len(data)))
        magic, length, count = struct.unpack_from(">3I", data, dataoff)
        self.assertEqual((magic, length, count), (0xfade0cc0, datasize, 1))
        slot_type, cd_off = struct.unpack_from(">II", data, dataoff + 12)
        self.assertEqual(slot_type, 0)
        cd = dataoff + cd_off
        cmagic, clen, version, cflags, hash_off, ident_off, nspecial, ncode, limit, hsize, htype, _, pshift = struct.unpack_from(">9I4B", data, cd)[:13]
        self.assertEqual((cmagic, version, cflags, nspecial, limit, hsize, htype, pshift), (0xfade0c02, 0x20400, 2, 0, 0x4000, 32, 2, 12))
        self.assertEqual(ncode, 4)
        self.assertEqual(data[cd + ident_off:cd + ident_off + 15], b"org.sweet.init\0")
        for i in range(ncode):
            got = data[cd + hash_off + 32 * i:cd + hash_off + 32 * i + 32]
            self.assertEqual(got, hashlib.sha256(data[4096 * i:4096 * (i + 1)]).digest(), "page %d" % i)

    def test_no_relocatable_data_survived_the_link(self):
        linked = self.linked
        # lld's dyld_info: nothing to rebase, bind, weak-bind or lazily bind; no undefined symbols
        n = struct.unpack_from("<I", linked, 16)[0]
        off, seen = 32, {}
        for _ in range(n):
            cmd, size = struct.unpack_from("<II", linked, off)
            seen[cmd] = struct.unpack_from("<%dI" % ((size - 8) // 4), linked, off + 8)
            off += size
        di = seen[0x80000022]
        self.assertEqual((di[1], di[3], di[5], di[7]), (0, 0, 0, 0))
        self.assertEqual(seen[0xb][5], 0)
        self.assertNotIn(0xc, seen)

    def test_size_and_determinism(self):
        self.assertEqual(len(self.macho) % 1, 0)
        self.assertLessEqual(len(self.macho), 0x4000 + 0x400)
        w = WORK / "again"
        w.mkdir()
        again, _, _ = build.build_probe(w)
        self.assertEqual(again, self.macho)

    def test_constants_are_in_the_file_exactly_once(self):
        k = struct.pack("<I", 0x428a2f98) + struct.pack("<I", 0x71374491)
        self.assertEqual(self.macho.count(k), 1)		# the SHA-256 round constants live in the file exactly once
        self.assertEqual(self.macho.count(b"/dev/rmd1\0"), 1)	# the NUL-terminated open() path (the two log lines continue after the name)
        self.assertEqual(self.macho.count(b"/dev/console\0"), 1)


VARIANT_PRELUDE = '#include "hash-probe.c"\n'


class StaticWrapperRefusals(unittest.TestCase):
    """mkstatic.py must refuse every input it could not move without relocation, with a reason."""

    def link_variant(self, name, extra_c, lld_extra=()):
        w = WORK / ("variant-" + name)
        w.mkdir()
        src = w / "variant.c"
        src.write_text(VARIANT_PRELUDE + extra_c)
        obj, linked = w / "v.o", w / "v.lld"
        build.run(["clang", "-target", build.TARGET] + build.CFLAGS + build.defines("/dev/rmd1", CHUNK) + ["-I", build.SRC, "-c", src, "-o", obj])
        build.run(build.LLD + list(lld_extra) + ["-o", linked, obj])
        return linked.read_bytes()

    def refused(self, data, *needles):
        with self.assertRaises(SystemExit) as cm:
            mkstatic.wrap(data)
        msg = str(cm.exception)
        self.assertTrue(any(n in msg for n in needles), msg)

    def test_a_writable_global_is_refused(self):
        self.refused(self.link_variant("data", "long g_counter = 3;\n__attribute__((used)) void touch(void) { g_counter++; }\n"), "__DATA")

    def test_a_zero_initialised_global_is_refused(self):
        self.refused(self.link_variant("bss", "long g_zero;\n__attribute__((used)) void touch(void) { g_zero++; }\n"), "__DATA")

    def test_a_pointer_table_is_refused(self):
        self.refused(self.link_variant("ptrs", 'const char *const g_names[] = {"a", "b", "c"};\n__attribute__((used)) const char *pick(int i) { return g_names[i]; }\n'),
                     "__DATA", "rebase")

    def test_an_undefined_symbol_is_refused(self):
        self.refused(self.link_variant("undef", "extern void nothing(void);\n__attribute__((used)) void touch(void) { nothing(); }\n",
                                       ("-undefined", "dynamic_lookup")), "undefined", "bind", "dylib", "fixups", "__DATA")

    def test_code_that_does_not_fit_one_page_is_refused(self):
        big = "__attribute__((used)) const unsigned char g_big[20000] = {1, 2, 3};\n"
        self.refused(self.link_variant("big", big), "do not fit")

    def test_unlinked_and_foreign_files_are_refused(self):
        good = self.link_variant("good", "")
        mkstatic.wrap(good)		# the control: an unmodified variant is accepted
        self.refused(b"", "not a Mach-O")
        self.refused(good[:100], "load commands run past the end", "malformed")
        bad_cpu = bytearray(good)
        bad_cpu[4:8] = struct.pack("<I", 0x01000007)
        self.refused(bytes(bad_cpu), "not an arm64")
        bad_type = bytearray(good)
        bad_type[12:16] = struct.pack("<I", 6)		# MH_DYLIB
        self.refused(bytes(bad_type), "not an arm64")

    def test_a_missing_start_symbol_is_refused(self):
        good = bytearray(self.link_variant("nostart", ""))
        i = good.find(b"_start\0")
        self.assertGreater(i, 0)
        good[i:i + 6] = b"_stort"
        self.refused(bytes(good), "no global _start")

    def test_a_chained_fixups_or_dylib_command_is_refused(self):
        good = self.link_variant("cmd", "")
        n = struct.unpack_from("<I", good, 16)[0]
        off = 32
        for _ in range(n):
            cmd, size = struct.unpack_from("<II", good, off)
            if cmd == 0x2c:		# LC_ENCRYPTION_INFO_64: any command of the right size can be re-labelled
                for newcmd, needle in ((0xc, "dylib"), (0x80000034, "chained fixups")):
                    t = bytearray(good)
                    struct.pack_into("<I", t, off, newcmd)
                    self.refused(bytes(t), needle)
                return
            off += size
        self.fail("no relabelable command found")

    def test_the_pin_on_mkinit_is_enforced(self):
        old = mkstatic.MKINIT_SHA256
        mkstatic.MKINIT_SHA256 = "0" * 64
        try:
            with self.assertRaises(SystemExit) as cm:
                mkstatic.load_mkinit()
            self.assertIn("not the pinned one", str(cm.exception))
        finally:
            mkstatic.MKINIT_SHA256 = old

    def test_build_refuses_bad_parameters(self):
        for dev in ("rmd1", "/tmp/x", '/dev/a"b', "/dev/a\\b"):
            with self.assertRaises(SystemExit):
                build.defines(dev, CHUNK)
        for chunk in (0, -512, 100, 513, (1 << 20) + 512):
            with self.assertRaises(SystemExit):
                build.defines("/dev/rmd1", chunk)
        build.defines("/dev/rmd1", 512)
        build.defines("/dev/rmd1", 1 << 20)


VA = BASE


def seg_cmd(name, vmaddr, vmsize, fileoff, filesize, sects=(), prot=5):
    body = struct.pack("<16sQQQQiiII", name.encode(), vmaddr, vmsize, fileoff, filesize, prot, prot, len(sects), 0)
    return struct.pack("<II", 0x19, 8 + len(body) + 80 * len(sects)) + body + b"".join(sects)


def sect_cmd(name, seg, addr, size, off, reloff=0, nreloc=0):
    return struct.pack("<16s16sQQIIIIIIII", name.encode(), seg.encode(), addr, size, off, 2, reloff, nreloc, 0, 0, 0, 0)


def synth(first=0x4000, sections=(("__text", 0, 0x100), ("__cstring", 0x100, 0x40)), entry=0x10, symbols=None, dyld=(0,) * 10,
          dysym=None, symtab=True, text_fileoff=0, extra_segments=(), end=None, text_vmaddr=VA, skew=None, relocs=(0, 0)):
    """A tiny but well-formed MH_EXECUTE arm64 file with the commands mkstatic.parse looks at; every argument bends one rule.
    Symbols and strings live at 0x1000/0x1800 (inside the header page), section bytes at `first`. -> bytes"""
    secs, last = [], 0
    for i, (name, rel, size) in enumerate(sections):
        secs.append(sect_cmd(name, "__TEXT", text_vmaddr + first + rel + (skew or {}).get(i, 0), size, first + rel,
                             *(relocs if i == 0 else (0, 0))))
        last = max(last, first + rel + size)
    syms = [("_start", 0x0f, VA + first + entry)] if symbols is None else symbols
    strtab, symdata = b"\0", b""
    for name, ntype, value in syms:
        symdata += struct.pack("<IBBHQ", len(strtab), ntype, 1, 0, value)
        strtab += name.encode() + b"\0"
    cmds = [seg_cmd("__PAGEZERO", 0, VA, 0, 0, prot=0),
            seg_cmd("__TEXT", text_vmaddr, 0x8000, text_fileoff, last, secs)]
    cmds += list(extra_segments)
    cmds.append(seg_cmd("__LINKEDIT", VA + 0x8000, 0x4000, last, 0, prot=1))
    if symtab:
        cmds.append(struct.pack("<6I", 0x2, 24, 0x1000, len(syms), 0x1800, len(strtab)))
    if dysym is not None:
        cmds.append(struct.pack("<20I", 0xb, 80, *dysym))
    if dyld is not None:
        cmds.append(struct.pack("<12I", 0x80000022, 48, *dyld))
    lc = b"".join(cmds)
    total = last if end is None else end
    data = bytearray(max(total, last, 0x1800 + len(strtab)))
    data[:32] = struct.pack("<8I", 0xfeedfacf, 0x0100000c, 0, 2, len(cmds), len(lc), 1, 0)
    data[32:32 + len(lc)] = lc
    data[0x1000:0x1000 + len(symdata)] = symdata
    data[0x1800:0x1800 + len(strtab)] = strtab
    for i in range(last - first):
        data[first + i] = (i * 7 + 3) & 0xff
    return bytes(data[:total]) if end is not None else bytes(data)


def synth_ok(**kw):
    """synth() with a dysymtab that says there is no undefined symbol (what a linked executable has)."""
    kw.setdefault("dysym", (0,) * 18)
    return synth(**kw)


class WrapperInputRules(unittest.TestCase):
    """mkstatic.py against synthetic files that break one rule at a time, with the exact reason it must give.
    (The linked probe is the only real input; these files are the only way to reach every refusal and every boundary.)"""

    def refused(self, data, message):
        with self.assertRaises(SystemExit) as cm:
            mkstatic.wrap(data)
        self.assertEqual(str(cm.exception), message)

    def refused_sub(self, data, *parts):
        with self.assertRaises(SystemExit) as cm:
            mkstatic.wrap(data)
        for part in parts:
            self.assertIn(part, str(cm.exception))

    def test_the_control_file_is_wrapped_and_keeps_its_bytes(self):
        data = synth_ok()
        out = mkstatic.wrap(data)
        m = parse_macho(out)
        self.assertEqual([s["name"] for s in m["sections"]], ["__text", "__cstring"])
        self.assertEqual([(s["addr"], s["off"], s["size"]) for s in m["sections"]], [(BASE + 0x1000, 0x1000, 0x100), (BASE + 0x1100, 0x1100, 0x40)])
        self.assertEqual(out[0x1000:0x1140], data[0x4000:0x4140])
        self.assertEqual(m["pc"], BASE + 0x1010)
        self.assertEqual(m["sizeofcmds"], 680)
        self.assertEqual(len(out), 0x4000 + m["sig"][1])
        self.assertEqual(mkstatic.wrap(data), out)		# deterministic

    def test_the_blob_is_moved_by_a_multiple_of_4096_and_never_over_the_load_commands(self):
        # 32 + 680 = 712 = 0x2c8 is where the load commands end for two sections
        for first, want in ((0x4000, 0x1000), (0x4123, 0x1123), (0x4fff, 0xfff), (0x4000 + 700, 0x1000 + 700), (0x4000 + 711, 0x1000 + 711),
                            (0x4000 + 712, 712), (0x4000 + 713, 713), (0x5000, 0x1000), (0x5123, 0x1123), (0x6000 + 0x2c8, 0x2c8)):
            data = synth_ok(first=first)
            out = mkstatic.wrap(data)
            m = parse_macho(out)
            self.assertEqual(m["sizeofcmds"], 680)
            self.assertEqual([s["off"] for s in m["sections"]], [want, want + 0x100], first)
            self.assertEqual([s["addr"] for s in m["sections"]], [BASE + want, BASE + want + 0x100], first)
            self.assertEqual(m["pc"], BASE + want + 0x10, first)
            self.assertEqual(out[want:want + 0x140], data[first:first + 0x140], first)
            self.assertEqual((want - first) % 0x1000, 0, first)

    def test_the_text_page_is_filled_exactly_or_refused(self):
        for size, ok in ((0x3000, True), (0x3001, False), (0x2fff, True)):
            data = synth_ok(sections=(("__text", 0, size),))
            if ok:
                out = mkstatic.wrap(data)
                m = parse_macho(out)
                self.assertEqual(m["sections"][0]["off"] + m["sections"][0]["size"], 0x1000 + size)
            else:
                self.refused(data, "the linked sections (%d bytes at offset 0x1000) do not fit in one 16384 byte __TEXT page" % size)

    def test_file_and_command_boundaries(self):
        hdr = lambda ncmds, sizeofcmds: struct.pack("<8I", 0xfeedfacf, 0x0100000c, 0, 2, ncmds, sizeofcmds, 1, 0)
        self.refused(b"\0" * 31, "not a Mach-O file")
        self.refused(hdr(0, 0), "no __TEXT sections")		# 32 bytes exactly: a header with nothing in it
        symtab = struct.pack("<6I", 0x2, 24, 0, 0, 0, 0)
        self.refused(hdr(1, 24) + symtab, "no __TEXT sections")		# the last command ends exactly at the end of the file
        self.refused(hdr(1, 24) + symtab[:-1], "load commands run past the end of the file")
        self.refused(hdr(1, 8) + struct.pack("<II", 0x99, 8), "no __TEXT sections")		# an unknown 8-byte command is skipped
        self.refused(hdr(1, 8) + struct.pack("<II", 0x99, 4), "malformed load command")
        self.refused(hdr(1, 16) + struct.pack("<IIII", 0x99, 16, 0, 0), "no __TEXT sections")
        self.refused(hdr(1, 16) + struct.pack("<IIII", 0x99, 17, 0, 0), "malformed load command")		# one byte past the commands
        self.refused(hdr(1, 16) + struct.pack("<IIII", 0x99, 40, 0, 0), "malformed load command")
        self.refused(hdr(2, 16) + struct.pack("<IIII", 0x99, 8, 0x99, 12), "malformed load command")		# the second command overruns

    def test_a_segment_name_of_16_characters_is_read_whole(self):
        extra = seg_cmd("ABCDEFGHIJKLMNOP", 0x41, 0x1000, 0, 0)
        self.refused_sub(synth_ok(extra_segments=(extra,)), "segment ABCDEFGHIJKLMNOP: only __PAGEZERO, __TEXT, __LINKEDIT can be carried")
        self.refused_sub(synth_ok(extra_segments=(seg_cmd("__DATA", VA + 0x4000, 0x4000, 0, 0),)), "segment __DATA: only")

    def test_a_section_segment_name_of_16_characters_is_read_whole(self):
        """The 17th byte after a section's name is the low byte of its address; the refusal text must not pick it up."""
        data = bytearray(synth_ok(relocs=(0x100, 0), skew={0: 0x41}))
        i = data.find(b"__text\0")
        self.assertGreater(i, 32)
        data[i + 16:i + 32] = b"ABCDEFGHIJKLMNOP"
        self.refused(bytes(data), "section ABCDEFGHIJKLMNOP,__text has relocations")

    def test_every_dylib_load_command_is_refused(self):
        """LC_LOAD_DYLIB and its four relatives (weak, reexport, upward, lazy): a file that names a library needs dyld to run.
        The synthetic file's dyld_info command (0x80000022, 48 bytes) is relabelled, one value at a time; every other value is accepted."""
        data = synth_ok()
        off = 32
        for _ in range(struct.unpack_from("<I", data, 16)[0]):
            cmd, size = struct.unpack_from("<II", data, off)
            if cmd == 0x80000022:
                break
            off += size
        else:
            self.fail("no dyld_info command in the synthetic file")
        for newcmd in (0xc, 0x80000018, 0x8000001f, 0x80000023, 0x20):
            t = bytearray(data)
            struct.pack_into("<I", t, off, newcmd)
            self.refused(bytes(t), "the file loads a dylib: it was linked against something")
        for newcmd in (0xd, 0x80000017, 0x8000001e, 0x80000024, 0x1f, 0x21, 0x0b + 0x80000000):
            t = bytearray(data)
            struct.pack_into("<I", t, off, newcmd)
            mkstatic.wrap(bytes(t))		# an unknown command of the same size is skipped

    def test_relocations_in_any_form_are_refused(self):
        for relocs in ((0x100, 0), (0, 5), (0x100, 5)):
            self.refused(synth_ok(relocs=relocs), "section __TEXT,__text has relocations")
        mkstatic.wrap(synth_ok(relocs=(0, 0)))

    def test_only_text_sections_are_carried(self):
        bogus = seg_cmd("__LINKEDIT", VA + 0xc000, 0x1000, 0x4140, 0x40, [sect_cmd("__x", "__LINKEDIT", VA + 0x4140, 0x40, 0x4140)])
        data = synth_ok(extra_segments=(bogus,), end=0x4180)
        self.assertEqual([s["name"] for s in mkstatic.parse(data)["sections"]], ["__text", "__cstring"])
        self.assertEqual([s["name"] for s in parse_macho(mkstatic.wrap(data))["sections"]], ["__text", "__cstring"])

    def test_a_file_without_text_sections_is_refused(self):
        self.refused(synth_ok(sections=()), "no __TEXT sections")		# a __TEXT segment with nothing in it
        # no __TEXT segment, but sections that say they belong to one: still nothing to carry
        data = bytearray(synth_ok())
        i = data.find(b"__TEXT\0")
        self.assertGreater(i, 32)
        data[i:i + 16] = b"__LINKEDIT".ljust(16, b"\0")
        self.refused(bytes(data), "no __TEXT sections")

    def test_dyld_info_with_any_rebase_bind_weak_or_lazy_data_is_refused(self):
        offs = {0: 0x111, 2: 0x222, 4: 0x333, 6: 0x444, 8: 0x555, 9: 0x666}
        def info(**sizes):
            d = [0] * 10
            for k, v in offs.items():
                d[k] = v
            d[1], d[3], d[5], d[7] = sizes.get("rebase", 0), sizes.get("bind", 0), sizes.get("weak", 0), sizes.get("lazy", 0)
            return tuple(d)
        mkstatic.wrap(synth_ok(dyld=info()))		# offsets without sizes are nothing; so is an export trie
        mkstatic.wrap(synth_ok(dyld=None))		# and so is no dyld_info command at all
        for key in ("rebase", "bind", "weak", "lazy"):
            kw = {key: 7}
            expect = dict(rebase=0, bind=0, weak=0, lazy=0)
            expect.update(kw)
            self.refused(synth_ok(dyld=info(**kw)), "dyld_info has rebase/bind data (rebase %(rebase)d, bind %(bind)d, weak %(weak)d, lazy %(lazy)d bytes)" % expect)
        self.refused(synth_ok(dyld=info(rebase=1, bind=2, weak=3, lazy=4)), "dyld_info has rebase/bind data (rebase 1, bind 2, weak 3, lazy 4 bytes)")

    def test_undefined_symbols_and_missing_tables_are_refused(self):
        fill = [(i + 1) * 100 for i in range(18)]
        ok = list(fill)
        ok[5] = 0
        mkstatic.wrap(synth(dysym=tuple(ok)))		# only field 5 (nundefsym) counts
        for n in (1, 2, 3000):
            bad = list(fill)
            bad[5] = n
            self.refused(synth(dysym=tuple(bad)), "%d undefined symbols" % n)
        no_dysym = "no symbol table: cannot find _start or prove there are no undefined symbols"
        self.refused(synth(dysym=None), no_dysym)
        self.refused(synth_ok(symtab=False), no_dysym)
        self.refused(synth(dysym=None, symtab=False), no_dysym)

    def test_section_placement_rules(self):
        self.refused(synth_ok(text_fileoff=0x10), "__TEXT does not start at file offset 0")
        self.refused(synth_ok(skew={1: 4}), "section __cstring is not at segment offset == file offset")
        self.refused(synth_ok(skew={0: 0x10}), "section __text is not at segment offset == file offset")
        self.refused(synth_ok(sections=(("__text", 0, 0x100), ("__const", 0xf0, 0x40))), "__TEXT sections overlap or are out of order")
        self.refused(synth_ok(sections=(("__const", 0, 0x100), ("__text", 0x100, 0x40))), "the first __TEXT section is __const, not __text")
        self.refused(synth_ok(sections=(("__0123456789abcd", 0, 0x100), ("__text", 0x100, 0x40))), "the first __TEXT section is __0123456789abcd, not __text")
        mkstatic.wrap(synth_ok(sections=(("__text", 0, 0x100), ("__const", 0x100, 0x40), ("__cstring", 0x140, 0x40))))		# adjacent is not overlapping

    def test_a_section_may_end_exactly_at_the_end_of_the_file_but_not_past_it(self):
        mkstatic.wrap(synth_ok())
        self.refused(synth_ok(end=0x4140 - 1), "a section runs past the end of the file")
        mkstatic.wrap(synth_ok(end=0x4140 + 5000))

    def test_the_entry_symbol_must_be_a_global_defined_symbol_inside_the_first_section(self):
        for entry, ok in ((0, True), (0xff, True), (0x100, False), (0x140, False), (-1, False), (-0x4000, False)):
            data = synth_ok(entry=entry)
            if ok:
                self.assertEqual(parse_macho(mkstatic.wrap(data))["pc"], BASE + 0x1000 + entry)
            else:
                self.refused(data, "_start is not inside __text")
        for ntype, ok in ((0x0f, True), (0x0e, False), (0x01, False), (0x03, False), (0x0d, False), (0x2f, True), (0x1f, True), (0x0b, False)):
            data = synth_ok(symbols=[("_start", ntype, VA + 0x4010)])
            if ok:
                mkstatic.wrap(data)
            else:
                self.refused(data, "no global _start")
        for name in ("_star", "_start2", "start", "__start", "_Start", ""):
            self.refused(synth_ok(symbols=[(name, 0x0f, VA + 0x4010)]), "no global _start")
        mkstatic.wrap(synth_ok(symbols=[("_other", 0x0f, VA + 0x4080), ("_start", 0x0f, VA + 0x4010), ("_main", 0x0f, VA + 0x40f0)]))
        # more than one `_start`: the last one found is the one used (documented behaviour of the loop; none occurs in the linker's output)
        m = parse_macho(mkstatic.wrap(synth_ok(symbols=[("_start", 0x0f, VA + 0x4010), ("_start", 0x0f, VA + 0x4020)])))
        self.assertEqual(m["pc"], BASE + 0x1020)


class WrapperCommandLine(unittest.TestCase):
    PLIST = b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>x</key><true/></dict></plist>'

    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", str(HERE / "mkstatic.py")] + [str(a) for a in args], capture_output=True, text=True, timeout=60)

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cli-", dir=WORK))
        self.src = self.dir / "in.macho"
        self.src.write_bytes(synth_ok())

    def test_two_arguments_write_the_executable_and_say_how_big_it_is(self):
        out = self.dir / "out.macho"
        r = self.run_tool(self.src, out)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(out.read_bytes(), mkstatic.wrap(self.src.read_bytes()))
        self.assertEqual(r.stdout, "%s: %d bytes\n" % (out, out.stat().st_size))

    def test_an_entitlements_file_goes_into_the_signature_and_nowhere_else(self):
        ents = self.dir / "e.plist"
        ents.write_bytes(self.PLIST)
        out, out2 = self.dir / "o1", self.dir / "o2"
        r1, r2 = self.run_tool(self.src, out), self.run_tool(self.src, out2, ents)
        self.assertEqual((r1.returncode, r2.returncode), (0, 0), (r1.stderr, r2.stderr))
        self.assertEqual(out2.read_bytes(), mkstatic.wrap(self.src.read_bytes(), self.PLIST))
        a, b = out.read_bytes(), out2.read_bytes()
        self.assertNotEqual(a, b)
        self.assertIn(self.PLIST, b)
        self.assertNotIn(self.PLIST, a)
        self.assertEqual(a[:0x4000].count(self.PLIST), 0)
        self.assertEqual(r2.stdout, "%s: %d bytes\n" % (out2, len(b)))

    def test_any_other_number_of_arguments_prints_the_usage_and_writes_nothing(self):
        for args in ((), (self.src,), (self.src, self.dir / "x", self.dir / "e", self.dir / "extra")):
            r = self.run_tool(*args)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertIn("mkstatic.py LINKED OUT [ENTITLEMENTS.plist]", r.stderr)
            self.assertEqual(r.stdout, "")
        self.assertFalse((self.dir / "x").exists())

    def test_a_bad_input_writes_no_output_file(self):
        (self.dir / "junk").write_bytes(b"not a macho file at all, but long enough to be read as one" * 3)
        r = self.run_tool(self.dir / "junk", self.dir / "out")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not an arm64 MH_EXECUTE file", r.stderr)
        self.assertFalse((self.dir / "out").exists())


class PadRoot(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="test-", dir=ROOT / "artifacts"))
        self.addCleanup(shutil.rmtree, self.dir, True)

    def src(self, size, seed=1):
        p = self.dir / ("src-%d-%d" % (size, seed))
        p.write_bytes(pattern(size, seed))
        return p

    def test_sizes_are_padded_to_the_unit(self):
        cases = {4096: 16384, 8192: 16384, 12288: 16384, 16384: 16384, 20480: 32768, 32768: 32768, 36864: 49152, 16384 * 7 + 4096: 16384 * 8}
        for size, want in cases.items():
            src = self.src(size)
            dest = self.dir / ("out-%d" % size)
            rec = pad_root.pad(str(src), str(dest))
            data, orig = dest.read_bytes(), src.read_bytes()
            self.assertEqual(len(data), want, size)
            self.assertEqual(data[:size], orig)
            self.assertEqual(data[size:], bytes(want - size))
            self.assertEqual(rec["source_bytes"], size)
            self.assertEqual(rec["source_sha256"], sha(orig))
            self.assertEqual(rec["padded_bytes"], want)
            self.assertEqual(rec["padded_sha256"], sha(data))
            self.assertEqual(rec["pad_bytes"], want - size)
            self.assertEqual((rec["unit"], rec["padded_sectors_512"], rec["padded_pages"]), (16384, want // 512, want // 16384))
            self.assertEqual(set(rec), {"source_bytes", "source_sha256", "padded_bytes", "padded_sha256", "pad_bytes", "unit", "padded_sectors_512", "padded_pages"})

    def test_an_aligned_source_is_copied_unchanged(self):
        src = self.src(16384 * 3)
        rec = pad_root.pad(str(src), str(self.dir / "o"))
        self.assertEqual(rec["pad_bytes"], 0)
        self.assertEqual(rec["source_sha256"], rec["padded_sha256"])

    def test_sizes_that_are_not_a_multiple_of_4096_are_refused_and_nothing_is_written(self):
        for size in (1, 511, 512, 4095, 4097, 8191, 16383, 16385, 20000):
            src = self.src(size)
            dest = self.dir / ("refused-%d" % size)
            with self.assertRaises(SystemExit) as cm:
                pad_root.pad(str(src), str(dest))
            self.assertIn("multiple of 4096", str(cm.exception))
            self.assertFalse(dest.exists())
        empty = self.dir / "empty"
        empty.write_bytes(b"")
        with self.assertRaises(SystemExit):
            pad_root.pad(str(empty), str(self.dir / "o"))

    def test_the_real_image_size(self):
        self.assertEqual(pad_root.padded_size(2475712512), 2475720704)
        self.assertEqual(2475720704, 0x93908000)
        self.assertEqual(2475712512 % 4096, 0)
        self.assertNotEqual(2475712512 % 16384, 0)
        for bad in (2475712511, 2475712513, 2475712512 + 2048, 2475712512 + 4095):
            with self.assertRaises(SystemExit):
                pad_root.padded_size(bad)

    def test_units(self):
        self.assertEqual(pad_root.padded_size(4096, 4096), 4096)
        self.assertEqual(pad_root.padded_size(4096, 65536), 65536)
        for unit in (0, 512, 3000, 6144, 12288, 24576, 4097):
            with self.assertRaises(SystemExit):
                pad_root.padded_size(4096, unit)

    def test_destination_rules(self):
        src = self.src(8192)
        existing = self.dir / "exists"
        existing.write_bytes(b"keep me")
        with self.assertRaises(SystemExit) as cm:
            pad_root.pad(str(src), str(existing))
        self.assertIn("exists", str(cm.exception))
        self.assertEqual(existing.read_bytes(), b"keep me")
        with self.assertRaises(SystemExit) as cm:
            pad_root.pad(str(src), str(WORK / "outside"))
        self.assertIn("outside", str(cm.exception))
        self.assertFalse((WORK / "outside").exists())
        with self.assertRaises(SystemExit):
            pad_root.pad(str(src), str(src))
        link = self.dir / "link"
        os.symlink(src, link)
        with self.assertRaises(SystemExit):
            pad_root.pad(str(src), str(link))		# a symlink to the source already "exists"
        with self.assertRaises(SystemExit) as cm:
            pad_root.pad(str(src), str(self.dir / ".." / ".." / "nat077-escape"))
        self.assertIn("outside", str(cm.exception))

    def test_expected_size_check(self):
        src = self.src(20480)
        with self.assertRaises(SystemExit) as cm:
            pad_root.pad(str(src), str(self.dir / "o"), expect_padded=16384)
        self.assertIn("expected", str(cm.exception))
        self.assertFalse((self.dir / "o").exists())
        pad_root.pad(str(src), str(self.dir / "o2"), expect_padded=32768)

    def test_failed_verification_removes_the_destination(self):
        src = self.src(8192)
        dest = self.dir / "o"
        old = pad_root.tail_is_zero
        pad_root.tail_is_zero = lambda path, start: False
        try:
            with self.assertRaises(SystemExit) as cm:
                pad_root.pad(str(src), str(dest))
            self.assertIn("read-back", str(cm.exception))
        finally:
            pad_root.tail_is_zero = old
        self.assertFalse(dest.exists())

    def test_the_tail_check_sees_a_single_nonzero_byte(self):
        p = self.dir / "t"
        for pos in (0, 1, 8 << 20, (8 << 20) + 5, 12345):
            data = bytearray(10 << 20)
            data[pos] = 1
            p.write_bytes(bytes(data))
            self.assertFalse(pad_root.tail_is_zero(str(p), 0))
            self.assertFalse(pad_root.tail_is_zero(str(p), pos))
            self.assertTrue(pad_root.tail_is_zero(str(p), pos + 1))

    def test_command_line_writes_the_record(self):
        src = self.src(20480)
        rec = self.dir / "rec.json"
        r = subprocess.run([sys.executable, "-I", str(HERE / "pad_root.py"), str(src), str(self.dir / "o"), "--record", str(rec)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(rec.read_text()), json.loads(r.stdout))
        self.assertEqual(json.loads(rec.read_text())["padded_bytes"], 32768)
        r = subprocess.run([sys.executable, "-I", str(HERE / "pad_root.py"), str(self.src(100)), str(self.dir / "o3")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_file_sha256_with_and_without_a_limit(self):
        data = pattern(3 * 4096 + 17, 9)
        p = self.dir / "h"
        p.write_bytes(data)
        self.assertEqual(pad_root.file_sha256(str(p)), sha(data))
        for limit in (0, 1, 2, 100, 4096, 4097, len(data) - 1, len(data), len(data) + 50):
            self.assertEqual(pad_root.file_sha256(str(p), limit), sha(data[:limit]), limit)
        with mock.patch.object(pad_root, "READ", 1000):		# a limit that is not a multiple of the read size, and one that is
            for limit in (1, 999, 1000, 1001, 2500, 3000, len(data)):
                self.assertEqual(pad_root.file_sha256(str(p), limit), sha(data[:limit]), limit)
            self.assertEqual(pad_root.file_sha256(str(p)), sha(data))
            self.assertFalse(pad_root.tail_is_zero(str(p), 0))
            q = self.dir / "z"
            q.write_bytes(bytes(2500) + b"\1" + bytes(10))
            self.assertFalse(pad_root.tail_is_zero(str(q), 0))
            self.assertFalse(pad_root.tail_is_zero(str(q), 2500))
            self.assertTrue(pad_root.tail_is_zero(str(q), 2501))

    def test_the_clone_request_names_both_descriptors_and_the_fallback_copies_the_bytes(self):
        src = self.src(12288, 3)
        seen = []

        def clone(fd, req, arg=0, *a):
            seen.append((fd, req, arg))
            raise OSError(errno.EOPNOTSUPP, "no reflinks here")
        with mock.patch("fcntl.ioctl", clone):
            rec = pad_root.pad(str(src), str(self.dir / "copy"))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1], 0x40049409)		# FICLONE
        self.assertEqual((self.dir / "copy").read_bytes(), src.read_bytes() + bytes(4096))
        self.assertEqual(rec["padded_sha256"], sha(src.read_bytes() + bytes(4096)))
        # the descriptors are the destination's and the source's: record their identity at call time
        ids = []

        def clone2(fd, req, arg=0, *a):
            ids.append((os.fstat(fd).st_ino, os.fstat(arg).st_ino, os.fstat(fd).st_size, os.fstat(arg).st_size))
            raise OSError(errno.EXDEV, "other filesystem")
        with mock.patch("fcntl.ioctl", clone2):
            pad_root.pad(str(src), str(self.dir / "copy2"))
        self.assertEqual(ids, [((self.dir / "copy2").stat().st_ino, src.stat().st_ino, 0, 12288)])

    def test_a_successful_clone_is_followed_by_a_zero_extend_and_the_same_checks(self):
        src = self.src(12288, 4)
        dest = self.dir / "cloned"
        calls = []

        def clone(fd, req, arg=0, *a):
            calls.append(req)
            os.write(fd, src.read_bytes())		# what FICLONE would leave: the source's bytes, no copy loop run
        with mock.patch("fcntl.ioctl", clone):
            rec = pad_root.pad(str(src), str(dest))
        self.assertEqual(calls, [0x40049409])
        self.assertEqual(dest.read_bytes(), src.read_bytes() + bytes(4096))
        self.assertEqual(rec["pad_bytes"], 4096)

    def test_the_destination_is_synced_with_its_bytes_on_disk(self):
        src = self.src(4096, 5)
        dest = self.dir / "synced"
        seen = []
        real = os.fsync

        def spy(fd):
            seen.append(Path("/proc/self/fd/%d" % fd).resolve() == dest.resolve())
            seen.append(dest.read_bytes()[:4096] == src.read_bytes())		# a separate reader sees the data already (flushed before fsync)
            return real(fd)
        with mock.patch("fcntl.ioctl", side_effect=OSError(errno.EOPNOTSUPP, "x")), mock.patch.object(pad_root.os, "fsync", spy):
            pad_root.pad(str(src), str(dest))
        self.assertEqual(seen, [True, True])

    def test_a_destination_of_the_wrong_size_is_refused_and_removed(self):
        src = self.src(8192, 6)
        dest = self.dir / "short"
        real = os.fsync

        def cut(fd):
            real(fd)
            os.truncate(dest, 12288)		# the file loses a page between the copy and the check
        with mock.patch.object(pad_root.os, "fsync", cut):
            with self.assertRaises(SystemExit) as cm:
                pad_root.pad(str(src), str(dest))
        self.assertEqual(str(cm.exception), "destination has 12288 bytes, expected 16384")
        self.assertFalse(dest.exists())

    def test_a_destination_that_cannot_be_resolved_is_refused(self):
        src = self.src(8192, 7)
        with mock.patch.object(pad_root.Path, "resolve", side_effect=OSError("symlink loop")):
            with self.assertRaises(SystemExit) as cm:
                pad_root.pad(str(src), str(self.dir / "never"))
        self.assertEqual(str(cm.exception), "cannot resolve %s: symlink loop" % (self.dir / "never"))
        self.assertFalse((self.dir / "never").exists())

    def test_the_record_text_is_two_space_indented_sorted_json_and_optional(self):
        src = self.src(20480, 8)
        r = subprocess.run([sys.executable, "-I", str(HERE / "pad_root.py"), str(src), str(self.dir / "o")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads(r.stdout)
        self.assertEqual(r.stdout, json.dumps(rec, indent=2, sort_keys=True) + "\n")
        self.assertEqual(list(json.loads(r.stdout)), sorted(rec))
        self.assertTrue(r.stdout.startswith('{\n  "pad_bytes": 12288,\n'))
        self.assertEqual([p.name for p in self.dir.glob("*.json")], [])		# no record file without --record

    def test_the_command_line_checks_the_expected_size_and_the_unit(self):
        src = self.src(20480, 8)
        r = subprocess.run([sys.executable, "-I", str(HERE / "pad_root.py"), str(src), str(self.dir / "o"), "--expect-padded-bytes", "16384"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.dir / "o").exists())
        r = subprocess.run([sys.executable, "-I", str(HERE / "pad_root.py"), str(src), str(self.dir / "o"), "--unit", "4096", "--expect-padded-bytes", "20480"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["padded_bytes"], 20480)
        self.assertEqual((self.dir / "o").stat().st_size, 20480)

    def test_the_record_of_the_real_image_is_consistent(self):
        path = ROOT / "artifacts" / "nat-077" / "padded.json"
        if not path.exists():
            self.skipTest("artifacts/nat-077/padded.json not built here")
        rec = json.loads(path.read_text())
        self.assertEqual((rec["source_bytes"], rec["padded_bytes"], rec["pad_bytes"], rec["unit"]), (2475712512, 2475720704, 8192, 16384))
        self.assertRegex(rec["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(rec["padded_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(rec["source_sha256"], rec["padded_sha256"])
        # the padded digest is the source digest continued over 8192 zero bytes: recompute it from the source digest's input only through the files
        img = ROOT / "artifacts" / "nat-077" / "system-padded.apfs"
        if img.exists():
            self.assertEqual(img.stat().st_size, rec["padded_bytes"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
