#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-080 host tests of the NAT-078 analyser (analyze_nat080.py). Evidence kind: host-test.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-080/test_analyze80.py      (needs `cc`; opens no device)

The analyser is fed texts and records that other code produced, not texts written for it:

  * the probe's console lines come from the REAL probe source (docs/procedures/nat-077/src/hash-probe.c, compiled for the host with the same
    flags as NAT-077's tests) run over a device image that the test chooses: a corrupted byte, a stale tail, a read that fails, a device that
    does not open. The expected row is therefore a consequence of what the device held, not of how the analyser reads a string;
  * the companion's records come from the REAL deliver_nat080.main() run against the NAT-076 model (the NAT-079 rig), as in test_deliver80.py;
  * the host's digests are computed from a root file by hashlib, independently of the probe.

What stays hand-written: the loader's `key=0xHEX` records (the loader's emitter is on-device C, shaped like NAT-075's `zero_bytes=0x...` lines,
which a test below reads from the archived NAT-075 run when it is present), the hard-coded decision cases for the precedence rules, and the
return classes (a time and a USB class, as NAT-049 hands them over). Nothing here is a measurement of the phone."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC77 = ROOT / "docs/procedures/nat-077/src"
NAT68_RUN = ROOT / "artifacts/nat-068/run-001"
NAT75_RUN = ROOT / "artifacts/nat-075/run-001"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T = load("nat080_t_deliver", HERE / "test_deliver80.py")
A = load("nat080_analyze_mod", HERE / "analyze_nat080.py")
D, E, rs = T.D, T.E, T.rs
SIZE, CHUNK, WRITE = T.SIZE, T.CHUNK, T.WRITE
WORK = Path(tempfile.mkdtemp(prefix="nat080-an-", dir=os.environ.get("TMPDIR")))
CKPT = 100000
READ = 32768
# progress lines of the probe over SIZE = 524288 bytes with reads of 32768 and a spacing of 100000: the first read that reaches 100000, 200000, ...
# (4 reads = 131072, 7 = 229376, 10 = 327680, 13 = 425984, 16 = 524288), worked out by hand
ATS = [131072, 229376, 327680, 425984, 524288]
CAP_DT = 380.0                  # inside the cap-reset window (372.7 .. 387.7 host seconds before the margins)


def tearDownModule():
    T.tearDownModule()
    shutil.rmtree(WORK, True)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build_exe(name, *defs):
    out = WORK / name
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-DHOST_TEST", *defs, "-I", str(SRC77), str(SRC77 / "host-main.c"), "-o", str(out)],
                   check=True, capture_output=True)
    return out


_EXES = {}


def exe(kind):
    if kind not in _EXES:
        _EXES[kind] = build_exe("probe-" + kind, "-DCKPT_BYTES=%d" % CKPT, *(['-DROOT_DEV="/nonexistent/nat080-device"'] if kind == "noopen" else []))
    return _EXES[kind]


def run_probe(device, kind="ok", *args):
    """The real probe over `device` bytes (behind descriptor 3). -> console text."""
    path = WORK / "device.bin"
    path.write_bytes(device)
    r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@" 3<"$DEV"', str(exe(kind))] + [str(a) for a in args], env={"DEV": str(path)}, capture_output=True,
                       timeout=60)
    return r.stdout.decode()


def probe_text(device, fail_after=None):
    return run_probe(device, "ok", READ, 0, "none" if fail_after is None else fail_after)


def loader_lines(status=0, committed=SIZE, rx_bytes=None, errors=0, progress=((256, 24, 0, 14), (512, 48, 0, 28)), size=SIZE):
    out = ["NAT079 rx MiB=%d trbs=%d err=%d t=%ds" % p for p in progress]
    vals = [("status", status & (2 ** 64 - 1)), ("pa", 0x9de400000), ("bytes", size), ("committed", committed),
            ("rx_bytes", committed if rx_bytes is None else rx_bytes), ("trbs", 48), ("errors", errors)]
    out += ["ticks=0x%x nat079_%s=0x%x \n" % (0x1234abcd + i, k, v) for i, (k, v) in enumerate(vals)]
    return out


def ret(dt, klass="download"):
    return A.classify_return(dict(dt=dt, klass=klass))


def dl(**kw):
    """A companion record as read_delivery() returns it, for the cases a real run does not produce on demand."""
    d = dict(outcome="delivered", error=None, committed=SIZE, host_bytes_written=SIZE, seconds=1.0, mb_per_s=1.0, mib_per_s=1.0, reconnects=0)
    d.update(kw)
    return d


def stale_line(at):
    return "SWEET hash: at=%d sha256=%s sec=0.001\n" % (at, "0" * 64)


class Runs(T.Case):
    """Records of the real companion, made against the model. Only the helpers of test_deliver80.Main are borrowed, not its tests."""
    make_root = T.Main.make_root
    run_main = T.Main.run_main
    argv = T.Main.argv

    def wired(self, per_write=0.5, send_error=None):
        orig = D.deliver

        def go(rs_, data, open_probe, open_send, journal, wait_s, deliver_s, chunk, write_size, progress_bytes, **kw):
            def send():
                if send_error:
                    raise send_error
                return T.ClockedTransport(self.rig.t, self.clock, per_write)
            return orig(rs_, data, open_probe, send, journal, wait_s, deliver_s, chunk, write_size, progress_bytes, mono=self.clock.mono,
                        sleep=self.clock.sleep)
        return go

    def record(self, kind):
        """-> the companion's output directory for one kind of run, written by D.main()."""
        if getattr(self, "_recorded", False):                  # a second record in one test needs a second device: the model keeps its state
            self.rig = E.Rig(self.lib, SIZE, 1)
            self.addCleanup(self.rig.close)
        self._recorded = True
        out = self.tmp / ("rec-" + kind)
        data = self.data[:SIZE // 2] if kind == "refused" else self.data
        root, digest = self.make_root(data)
        argv = self.argv(root, digest, out, len(data), "--chunk", str(CHUNK), "--write-size", str(WRITE), "--progress-bytes", str(2 * CHUNK))
        phase = kind != "never-ready"
        if kind == "cap-reached":
            argv += ["--deliver-s", "2.2"]
        if kind == "never-ready":
            argv += ["--wait-s", "3"]
        if kind == "dma-lost":
            self.rig.m.set_dma_limit(self.rig.off + SIZE // 2)
        deliver = self.wired(send_error=rs.TransportError("could not set the configuration: Resource busy") if kind == "failed-0" else None)
        if phase:
            (code, _o, err, _), _r = self.in_phase(lambda: self.run_main(argv, deliver))
        else:
            code, _o, err, _ = self.run_main(argv, deliver)
        self.exit_code = code
        return out


class Parsers(Runs):
    def test_the_real_probe_text_is_read_line_by_line(self):
        text = probe_text(self.data)
        p = A.read_probe(text)
        self.assertEqual(p["banner_pid"], int(re.search(r"PID (\d+) \*\*\*", text).group(1)))
        self.assertEqual(p["reading"], dict(device="/dev/fd/3", chunk=131072))
        self.assertEqual([x["at"] for x in p["progress"]], ATS)
        for x in p["progress"]:
            self.assertEqual(x["sha256"], sha(self.data[:x["at"]]), x)
        self.assertEqual(p["final"]["bytes"], SIZE)
        self.assertEqual(p["final"]["sha256"], sha(self.data))
        self.assertTrue(p["done_line"] and p["seen"])
        self.assertIsNone(p["cannot_open"])
        self.assertIsNone(p["read_failed"])

    def test_a_kernel_prefix_in_front_of_each_line_changes_nothing(self):
        text = probe_text(self.data)
        prefixed = "".join("[   12.%03d] %s\n" % (i, l) for i, l in enumerate(text.split("\n")) if l)
        self.assertEqual(A.read_probe(prefixed), A.read_probe(text))

    def test_a_text_without_the_probe_says_so(self):
        p = A.read_probe("vm_page_bootstrap: 1 free pages, 2 wired pages\nAdded memory device md1/rmd1\n")
        self.assertFalse(p["seen"])
        self.assertEqual((p["banner_pid"], p["progress"], p["final"], p["cannot_open"], p["read_failed"], p["done_line"]), (None, [], None, None, None, False))

    def test_the_failure_lines_of_the_real_probe(self):
        op = A.read_probe(run_probe(self.data, "noopen"))
        self.assertIsNotNone(op["cannot_open"])
        self.assertEqual(op["cannot_open"]["errno"], 2, "ENOENT")
        self.assertIsNone(op["final"])
        rd = A.read_probe(probe_text(self.data, fail_after=200000))
        self.assertIsNotNone(rd["read_failed"])
        self.assertEqual(rd["read_failed"]["errno"], 5, "EIO")
        self.assertGreaterEqual(rd["read_failed"]["after"], 200000 - READ)
        self.assertLessEqual(rd["read_failed"]["after"], 200000 + READ)
        self.assertIsNone(rd["final"])
        # the read that crosses the failure point is cut at it, so the second checkpoint line is at 200000 (the first read to reach 200000), not 229376
        self.assertEqual([x["at"] for x in rd["progress"]], [131072, 200000], "the lines before the failure are kept")

    def test_loader_values_keep_the_last_record_and_read_the_status_as_signed(self):
        v = A.read_loader_values(loader_lines(status=6, committed=1234, progress=((10, 1, 0, 2), (20, 2, 0, 4))) + ["ticks=0x9 nat079_committed=0x99 \n"])
        self.assertEqual((v["status"], v["status_name"]), (6, "timeout"))
        self.assertEqual(v["values"]["committed"], 0x99, "the last record of a key wins")
        self.assertEqual(v["progress"], [(10, 1, 0, 2), (20, 2, 0, 4)])
        neg = A.read_loader_values(["ticks=0x1 nat079_status=0xffffffffffffffff \n"])
        self.assertEqual(neg["status"], -1)
        self.assertEqual(neg["status_name"], "unknown(-1)")
        edge = A.read_loader_values(["ticks=0x1 nat079_status=0x8000000000000000 \n"])
        self.assertEqual(edge["status"], -(1 << 63), "the smallest int64 stored as a uint64_t is 2^63 and is negative")
        below = A.read_loader_values(["ticks=0x1 nat079_status=0x7fffffffffffffff \n"])
        self.assertEqual(below["status"], (1 << 63) - 1, "the largest int64 stays positive")
        none = A.read_loader_values(["ticks=0x1 zero_bytes=0x8b80000 \n", "something else"])
        self.assertEqual((none["found"], none["status"], none["status_name"], none["values"], none["progress"]), (False, None, None, {}, []))
        self.assertEqual(A.read_loader_values(None)["found"], False)

    def test_the_status_names_are_the_loaders_numbering(self):
        fixed = (ROOT / "docs/procedures/nat-079/src/nat079_fixed.h").read_text()
        header = {int(n): name for name, n in re.findall(r"#define NAT079_([A-Z_]+)\s+(\d+)\t", fixed)}
        self.assertEqual(sorted(A.STATUS), sorted(header), "every loader status has a name here and nothing else")
        for n, name in A.STATUS.items():
            self.assertEqual(name.upper().replace("-", "_"), header[n], n)

    @unittest.skipUnless((NAT75_RUN / "archive").exists(), "artifacts/nat-075/run-001 is not present")
    def test_the_archived_loader_text_has_the_key_hex_shape_and_no_nat079_keys(self):
        boot = sorted((NAT75_RUN / "archive" / "boots").iterdir())[-1].name
        lines = A.A65.A59.boot_texts(NAT75_RUN / "archive", boot)
        self.assertTrue(any(re.search(r"\bzero_bytes=0x[0-9a-f]+", l) for l in lines), "NAT-075's loader prints key=0xhex records")
        self.assertFalse(A.read_loader_values(lines)["found"])

    def test_the_delivery_record_written_by_the_companion_is_read(self):
        out = self.record("delivered")
        self.assertEqual(self.exit_code, 0)
        d = A.read_delivery(out)
        doc = json.loads((out / "delivery.json").read_text())
        self.assertEqual((d["source"], d["outcome"], d["committed"], d["size"]), ("json", "delivered", SIZE, SIZE))
        self.assertTrue(d["summary_written"])
        self.assertEqual((d["mb_per_s"], d["mib_per_s"], d["seconds"]), (doc["mb_per_s"], doc["mib_per_s"], doc["seconds"]))
        self.assertEqual(d["host_bytes_written"], SIZE)
        self.assertEqual(d["reconnects"], 0)
        self.assertIsNotNone(d["waited_s"])
        self.assertEqual([m["host_bytes"] for m in d["marks"]], [2 * CHUNK, 4 * CHUNK], "a mark every 2 chunks: SIZE is 4 chunks")
        self.assertGreaterEqual(d["events"], 4)

    def test_the_journal_alone_is_enough_for_a_killed_companion(self):
        out = self.record("delivered")
        (out / "delivery.json").unlink()
        d = A.read_delivery(out)
        self.assertEqual((d["source"], d["summary_written"], d["outcome"], d["committed"]), ("journal", False, "delivered", None),
                         "no device view without the summary: the host's own count is never turned into a committed offset")
        lines = (out / "delivery.jsonl").read_text().splitlines()
        cut = [l for l in lines if '"event": "final"' not in l]
        (out / "delivery.jsonl").write_text("\n".join(cut) + "\n" + '{"event": "progress", "host_by')               # a torn last line
        d = A.read_delivery(out)
        self.assertEqual((d["outcome"], d["committed"], d["events"]), ("killed-no-final", None, len(cut)))

    def test_no_record_is_none(self):
        self.assertIsNone(A.read_delivery(None))
        self.assertIsNone(A.read_delivery(self.tmp / "nowhere"))
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertIsNone(A.read_delivery(empty))

    def test_prefix_digests_are_the_hashlib_digests_of_the_prefix(self):
        p = self.tmp / "root.img"
        p.write_bytes(self.data)
        ats = [SIZE, 0, 131072, 131072, 7, SIZE + 1, 99999999]
        got = A.host_prefix_digests(p, ats)
        self.assertEqual(sorted(got), [0, 7, 131072, SIZE], "the counts beyond the file are not invented")
        for at, d in got.items():
            self.assertEqual(d, sha(self.data[:at]), at)

    def test_the_exit_classes_are_the_numbers_the_probe_exits_with(self):
        src = (SRC77 / "hash-probe.c").read_text()
        d = {n: int(v, 16) for n, v in re.findall(r"#define (EXIT_[A-Z_]+)\s+(0x[0-9a-fA-F]+)", src)}
        self.assertEqual(sorted(d), ["EXIT_EMPTY", "EXIT_NO_CONSOLE", "EXIT_NO_DEVICE", "EXIT_READ_FAILED"])
        self.assertEqual(A.EXIT_CLASSES, {d["EXIT_NO_CONSOLE"]: "no-console", d["EXIT_NO_DEVICE"]: "cannot-open-root-device",
                                          d["EXIT_READ_FAILED"]: "read-failed", d["EXIT_EMPTY"]: "empty-device"})
        self.assertEqual(A.EXIT_OK, 0x50 + 1, "PID 1 exits with 0x50 + its pid")

    def test_every_kind_of_probe_line_alone_is_a_sighting_and_the_open_failure_names_the_device(self):
        lines = {"banner": "*** SWEET hash probe: init running as PID 1 ***", "reading": "SWEET hash: reading /dev/rmd1 in chunks of 131072",
                 "at": stale_line(131072), "final": "SWEET hash: bytes=7 sha256=%s sec=0.002" % ("1" * 64),
                 "open": "SWEET hash: cannot open /dev/rmd1, errno 2", "read": "SWEET hash: read failed after 5 bytes, errno 5"}
        for kind, line in lines.items():
            self.assertTrue(A.read_probe(line)["seen"], kind)
        self.assertFalse(A.read_probe("")["seen"])
        self.assertFalse(A.read_probe("an unrelated line")["seen"])
        self.assertEqual(A.read_probe(lines["open"])["cannot_open"], dict(device="/dev/rmd1", errno=2))
        self.assertEqual(A.read_probe(lines["read"])["read_failed"], dict(after=5, errno=5))
        self.assertEqual(A.read_probe(lines["reading"])["reading"], dict(device="/dev/rmd1", chunk=131072))

    def test_reconnects_are_counted_and_the_last_mark_gives_the_last_host_count(self):
        d = self.tmp / "journal-only"
        d.mkdir()
        events = [dict(event="start"), dict(event="reconnect", host_bytes=5), dict(event="progress", host_bytes=100), dict(event="reconnect", host_bytes=100),
                  dict(event="progress", host_bytes=200), dict(event="reconnect", host_bytes=200)]
        (d / "delivery.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        r = A.read_delivery(d)
        self.assertEqual((r["reconnects"], r["last_host_bytes"], r["outcome"], r["source"], r["events"]), (3, 200, "killed-no-final", "journal", 6))

    def test_a_summary_that_is_not_json_leaves_the_journal(self):
        out = self.record("delivered")
        (out / "delivery.json").write_text('{"outcome": "deliv')
        r = A.read_delivery(out)
        self.assertEqual((r["source"], r["summary_written"], r["outcome"]), ("journal", False, "delivered"))

    def test_the_file_is_read_in_blocks_of_at_most_8_MiB_and_never_past_its_end(self):
        n = 20 << 20
        p = self.tmp / "big.img"
        data = b"\x5a" * n
        p.write_bytes(data)
        sizes = []

        class Spy:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def read(self, k):
                sizes.append(k)
                return self.f.read(k)

        with mock.patch.object(A, "open", lambda path, mode: Spy(open(path, mode)), create=True):
            got = A.host_prefix_digests(p, [n])
        self.assertEqual(got, {n: sha(data)})
        self.assertEqual(sizes, [8 << 20, 8 << 20, 4 << 20])

    def test_a_module_loaded_by_path_is_registered_under_its_name(self):
        m = A._load("nat080_registered_probe_name", HERE / "derive.py")
        self.addCleanup(sys.modules.pop, "nat080_registered_probe_name", None)
        self.assertIs(sys.modules["nat080_registered_probe_name"], m)

    def test_the_return_classes_follow_from_the_clocks(self):
        lo, hi = A.expected_return_window()
        self.assertAlmostEqual(lo, 87.72 + 300 * 0.95, places=6)           # 372.72
        self.assertAlmostEqual(hi, 87.72 + 300 * 1.0, places=6)            # 387.72
        self.assertGreaterEqual(lo - A.CAP_RETURN[0], 8.0, "NAT-075's lower margin")
        self.assertGreaterEqual(A.CAP_RETURN[1] - hi, 17.0, "NAT-075's upper margin")
        for dt, cls in ((A.CAP_RETURN[0], "cap-reset"), (A.CAP_RETURN[1], "cap-reset"), (CAP_DT, "cap-reset"), (A.CAP_RETURN[0] - 0.1, "download-other-early"),
                        (A.CAP_RETURN[1] + 0.1, "download-other-late"), (177.9, "download-other-early")):
            self.assertEqual(ret(dt)["cls"], cls, dt)
        self.assertEqual(ret(95.0, "upload")["cls"], "upload")
        self.assertEqual(ret(CAP_DT, "upload")["cls"], "upload", "any SEC_UPLOAD return is an upload, whatever the time")
        self.assertEqual(ret(30.0, "android")["cls"], "not-download-android")
        self.assertEqual(A.classify_return(None), dict(klass=None, dt=None, cls="no-return-seen"))
        self.assertEqual(A.classify_return({})["cls"], "no-return-seen")


class Rows(Runs):
    """The pass table, row by row. Defaults are a clean pass; each test changes what the device held, what the companion recorded or what the
    loader reported."""

    def setUp(self):
        super().setUp()
        self.root_path = self.tmp / "root.img"
        self.root_path.write_bytes(self.data)
        self.size = SIZE

    def judge(self, delivery="delivered", loader=None, device=None, text=None, exit_status=81, ending=None, chain="PASS", fail_after=None):
        if isinstance(delivery, str):
            delivery = A.read_delivery(self.record(delivery))
        loader = A.read_loader_values(loader_lines() if loader is None else loader)
        text = probe_text(self.data if device is None else device, fail_after) if text is None else text
        probe = A.read_probe(text)
        ats = [p["at"] for p in probe["progress"]] + ([probe["final"]["bytes"]] if probe["final"] else []) + [SIZE]
        digests = A.host_prefix_digests(self.root_path, ats)
        return A.decide(SIZE, delivery, loader, probe, dict(exit_status=exit_status), ending or ret(CAP_DT), digests, chain)

    def flipped(self, at):
        b = bytearray(self.data)
        b[at] ^= 0x01
        return bytes(b)

    # ------------------------------------------------------------------------------------------------------------------ row 1
    def test_row_1_the_whole_image_read_back_unchanged_and_the_cap_reset(self):
        r = self.judge()
        self.assertEqual((r["row"], r["name"], r["pass"]), (1, "pass", True), r["reasons"])
        f = r["facts"]
        self.assertEqual((f["committed"], f["committed_device"], f["committed_loader"], f["exit_status"], f["ending"]), (SIZE, SIZE, SIZE, 81, "cap-reset"))
        self.assertEqual([l["at"] for l in f["check"]["lines"]], ATS)
        self.assertTrue(all(l["match"] and l["inside"] for l in f["check"]["lines"]))
        self.assertTrue(f["check"]["final_ok"])
        self.assertEqual((f["rate"]["mb_per_s"] > 0, f["probe"]["progress_lines"]), (True, 5))

    def test_row_1_needs_each_of_its_conditions(self):
        base = lambda **kw: self.judge(**kw)                                             # noqa: E731
        cases = {
            "the chain verdict is PASS": dict(chain="FAIL"),
            "PID 1 exited with status 81": dict(exit_status=80),
            "the ending is the cap reset": dict(ending=ret(500.0)),
            "the loader reports done": dict(loader=[l for l in loader_lines() if "nat079_status" not in l]),
            "the loader's reserve is the size of the image": dict(loader=loader_lines(size=2 * SIZE)),
        }
        for want, kw in cases.items():
            r = base(**kw)
            self.assertEqual(r["row"], 8, (want, r["reasons"]))
            self.assertFalse(r["pass"], want)
            self.assertEqual(r["reasons"][0], "pass conditions not met: " + want, "exactly the one condition that was broken is named")
        # the companion's record missing: the loader's committed offset alone is not a pass (the rate is part of the pass)
        r = self.judge(delivery=None)
        self.assertEqual(r["row"], 8)
        self.assertIn("the companion delivered", r["reasons"][0])
        # a companion that failed after the loader reported done
        failed = A.read_delivery(self.record("delivered"))
        failed["outcome"] = "failed"
        self.assertEqual(self.judge(delivery=failed)["row"], 8)

    def test_a_reserve_of_another_size_is_named_in_every_verdict_not_only_in_the_pass_conditions(self):
        r = self.judge(loader=loader_lines(size=2 * SIZE, status=6, committed=CHUNK), text="", exit_status=None)
        self.assertEqual(r["row"], 3)
        self.assertIn("the loader reserved %d bytes but the host's image is %d" % (2 * SIZE, SIZE), r["reasons"])
        self.assertEqual(r["facts"]["loader_bytes"], 2 * SIZE)
        ok = self.judge()
        self.assertEqual(ok["facts"]["loader_bytes"], SIZE)
        self.assertFalse(any("reserved" in x for x in ok["reasons"]))
        self.assertIsNone(self.judge(loader=[l for l in loader_lines() if "nat079_bytes" not in l])["facts"]["loader_bytes"])

    def test_row_1_does_not_depend_on_the_order_the_lines_come_in(self):
        lines = loader_lines()
        self.assertEqual(self.judge(loader=list(reversed(lines)))["row"], 1)

    # ------------------------------------------------------------------------------------------------------------------ row 2
    def test_row_2_one_flipped_byte_is_localised_to_the_first_line_that_covers_it(self):
        r = self.judge(device=self.flipped(300000))                                  # in (229376, 327680]
        self.assertEqual((r["row"], r["name"]), (2, "digest-or-length-mismatch"), r["reasons"])
        c = r["facts"]["check"]
        self.assertEqual((c["first_bad"], c["last_good"]), (327680, 229376))
        self.assertEqual(c["bad_within"], [327680, 425984, 524288])
        self.assertEqual([l["match"] for l in c["lines"]], [True, True, False, False, False])
        self.assertFalse(c["final_ok"])
        self.assertIn("327680", r["reasons"][0])

    def test_row_2_a_flip_in_the_last_byte_shows_in_the_last_line_and_the_final(self):
        r = self.judge(device=self.flipped(SIZE - 1))
        self.assertEqual(r["row"], 2)
        c = r["facts"]["check"]
        self.assertEqual((c["first_bad"], c["last_good"], c["bad_within"]), (SIZE, 425984, [SIZE]))
        self.assertTrue(c["final_bad"])

    def test_row_2_a_final_line_that_covers_less_than_the_whole_image_is_a_mismatch(self):
        r = self.judge(device=self.data[:SIZE - 32768])                              # the device read ends early; its digests are of a correct prefix
        self.assertEqual(r["row"], 2, r["reasons"])
        c = r["facts"]["check"]
        self.assertTrue(c["final_match"] and not c["final_ok"] and c["final_bad"])
        self.assertEqual(r["facts"]["probe"]["final"]["bytes"], SIZE - 32768)

    def test_row_2_also_covers_a_mismatch_inside_a_partial_delivery(self):
        rec = A.read_delivery(self.record("cap-reached"))
        got = rec["committed"]
        self.assertEqual(got, 2 * CHUNK)
        loader = loader_lines(status=6, committed=got)
        r = self.judge(delivery=rec, loader=loader, device=self.flipped(100000)[:got] + b"\xee" * (SIZE - got))
        self.assertEqual(r["row"], 2, "a digest line inside the delivered span differs")
        self.assertEqual(r["facts"]["check"]["first_bad"], 131072)

    # ------------------------------------------------------------------------------------------------------------------ rows 3, 3a, 4
    def test_row_3_a_short_transfer_judges_only_the_span_that_was_delivered(self):
        rec = A.read_delivery(self.record("cap-reached"))
        got = rec["committed"]
        self.assertEqual((rec["outcome"], got), ("cap-reached", 2 * CHUNK))          # hand-computed in test_deliver80: 5 writes of 64 KiB = 2 chunks committed
        device = self.data[:got] + b"\xee" * (SIZE - got)                             # the reserve beyond the committed offset holds old memory
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=got), device=device, exit_status=81)
        self.assertEqual((r["row"], r["name"], r["pass"]), (3, "short-transfer", False), r["reasons"])
        self.assertEqual(r["variant"] if "variant" in r else None, None)
        c = r["facts"]["check"]
        self.assertEqual([(l["at"], l["inside"], l["match"]) for l in c["lines"]],
                         [(131072, True, True), (229376, True, True), (327680, False, False), (425984, False, False), (524288, False, False)])
        self.assertEqual((c["bad_within"], c["bad_beyond"], c["last_good"]), ([], [327680, 425984, 524288], 229376))
        self.assertFalse(c["final_bad"], "the final digest covers bytes that were never delivered: not judged")
        self.assertEqual(r["facts"]["committed"], got)
        self.assertIn("ended by the companion's delivery cap", r["reasons"][0])
        self.assertEqual(r["facts"]["rate"]["mb_per_s"], rec["mb_per_s"])

    def test_row_3_without_any_digest_lines_still_reports_the_short_transfer(self):
        rec = A.read_delivery(self.record("cap-reached"))
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=rec["committed"]), text="", exit_status=None)
        self.assertEqual(r["row"], 3)

    def test_row_3_a_companion_failure_other_than_a_checksum_names_the_companion(self):
        rec = A.read_delivery(self.record("cap-reached"))
        rec["outcome"], rec["error"] = "failed", "TransportError: write failed: Pipe error"
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=rec["committed"]), text="", exit_status=None)
        self.assertEqual(r["row"], 3)
        self.assertIn("the companion failed: TransportError: write failed: Pipe error", r["reasons"][0])

    def test_row_3a_the_whole_image_arrived_and_the_hash_was_cut_short(self):
        text = probe_text(self.data)
        cut = text[:text.index("SWEET hash: at=%d" % ATS[3])]                        # the kernel's timed return came after the third line
        r = self.judge(text=cut, exit_status=None)
        self.assertEqual((r["row"], r["name"], r.get("variant")), (3, "short-transfer", "a"), r["reasons"])
        self.assertIn("last at 327680", r["reasons"][0])
        self.assertEqual(r["facts"]["check"]["last_good"], 327680)
        self.assertEqual(r["facts"]["ending"], "cap-reset")

    def test_row_4_the_cut_hash_and_a_sec_upload_ending(self):
        text = probe_text(self.data)
        cut = text[:text.index("SWEET hash: at=%d" % ATS[3])]
        r = self.judge(text=cut, exit_status=None, ending=ret(300.0, "upload"))
        self.assertEqual((r["row"], r["name"]), (4, "upload-ending-with-cut-hash"), r["reasons"])
        self.assertIn("+300.0 s", r["reasons"][0])

    def test_row_4_does_not_apply_when_the_final_line_is_there(self):
        r = self.judge(ending=ret(300.0, "upload"))
        self.assertEqual(r["row"], 8, "all of it was read back, but the ending is not the planned one")

    def test_nothing_from_the_probe_at_all_is_row_8_not_a_hash_finding(self):
        r = self.judge(text="", exit_status=None)
        self.assertEqual(r["row"], 8)
        self.assertIn("no probe line", r["reasons"][0])
        r = self.judge(text="", exit_status=None, ending=ret(300.0, "upload"))
        self.assertEqual(r["row"], 8, "an upload without any probe line says nothing about the hash")

    # ------------------------------------------------------------------------------------------------------------------ rows 5, 6
    def test_row_5_the_root_device_does_not_open(self):
        r = self.judge(text=run_probe(self.data, "noopen"), exit_status=0x61)
        self.assertEqual((r["row"], r["name"]), (5, "cannot-open-root-device"), r["reasons"])
        self.assertEqual(r["facts"]["exit_class"], "cannot-open-root-device")
        self.assertEqual(self.judge(text="", exit_status=0x61)["row"], 5, "the exit status alone is enough when the ring lost the line")

    def test_row_6_a_read_failure_and_an_empty_device(self):
        r = self.judge(fail_after=200000, exit_status=0x62)
        self.assertEqual((r["row"], r["name"]), (6, "read-failure-or-empty-device"), r["reasons"])
        self.assertEqual(r["facts"]["probe"]["read_failed"]["errno"], 5)
        self.assertEqual(self.judge(text="", exit_status=0x63)["row"], 6)
        self.assertEqual(self.judge(text="", exit_status=0x62)["row"], 6)

    def test_row_6_the_lines_before_the_failure_are_still_checked(self):
        r = self.judge(device=self.flipped(100000), fail_after=300000, exit_status=0x62)
        self.assertEqual(r["row"], 2, "a corrupted line before the failure is the earlier finding")

    # ------------------------------------------------------------------------------------------------------------------ rows 7, 9, 10
    def test_row_7_the_device_was_never_ready(self):
        rec = A.read_delivery(self.record("never-ready"))
        self.assertEqual(rec["outcome"], "never-ready")
        r = self.judge(delivery=rec, loader=loader_lines(status=0, committed=0), text="", exit_status=None)
        self.assertEqual((r["row"], r["name"]), (7, "delivery-path-never-worked"), r["reasons"])

    def test_row_7_the_device_refused_the_stream(self):
        rec = A.read_delivery(self.record("refused"))
        self.assertEqual(rec["outcome"], "refused-by-device")
        self.assertEqual(self.judge(delivery=rec, loader=loader_lines(committed=0), text="", exit_status=None)["row"], 7)

    def test_row_7_the_sender_could_not_open_the_device_and_nothing_was_committed(self):
        rec = A.read_delivery(self.record("failed-0"))
        self.assertEqual((rec["outcome"], rec["committed"], rec["host_bytes_written"]), ("failed", None, 0), "no device view, nothing written by the host")
        r = self.judge(delivery=rec, loader=loader_lines(committed=0, status=6), text="", exit_status=None)
        self.assertEqual(r["row"], 7)
        self.assertIn("Resource busy", r["reasons"][0])
        r = self.judge(delivery=rec, loader=[], text="", exit_status=None)
        self.assertEqual(r["row"], 7, "the companion's own record is enough when the host wrote nothing")
        wrote = dict(rec, host_bytes_written=CHUNK)
        r = self.judge(delivery=wrote, loader=[], text="", exit_status=None)
        self.assertEqual(r["row"], 8, "bytes were written and no committed offset exists anywhere: not a claim about the device")
        self.assertIn("no committed offset", r["reasons"][0])

    def test_row_7_the_loader_reports_that_the_path_never_existed(self):
        rec = A.read_delivery(self.record("delivered"))
        for status in (1, 2, 7):
            r = self.judge(delivery=None, loader=loader_lines(status=status, committed=0), text="", exit_status=None)
            self.assertEqual(r["row"], 7, status)
        # an engine that went down after the last byte was committed is not "never worked" (the next rule decides: here the loader is not done)
        r = self.judge(delivery=rec, loader=loader_lines(status=7, committed=SIZE))
        self.assertEqual(r["row"], 8)

    def short(self, delivery, status=6, committed=CHUNK):
        return self.judge(delivery=delivery, loader=loader_lines(status=status, committed=committed), text="", exit_status=None)

    def test_row_3_names_what_ended_the_transfer(self):
        tail = "; every digest line inside the delivered span matches"
        head = "committed %d of %d bytes; ended by " % (CHUNK, SIZE)
        r = self.short(dl(outcome="failed", error="TransportError: boom", committed=CHUNK))
        self.assertEqual((r["row"], r["reasons"][0]), (3, head + "the companion failed: TransportError: boom" + tail))
        self.assertEqual(r["facts"]["delivery_error"], "TransportError: boom")
        r = self.short(dl(outcome="failed", error=None, committed=CHUNK))
        self.assertEqual(r["reasons"][0], head + "the companion failed: no error text" + tail)
        self.assertIsNone(r["facts"]["delivery_error"])
        r = self.short(dl(outcome="cap-reached", error="delivery deadline passed after 5 bytes written", committed=CHUNK))
        self.assertEqual(r["reasons"][0], head + "the companion's delivery cap" + tail)
        r = self.short(dl(outcome="delivered", committed=CHUNK), status=6)
        self.assertEqual(r["reasons"][0], head + "the loader's cap" + tail)
        r = self.short(None, status=6)
        self.assertEqual(r["reasons"][0], head + "the loader's cap" + tail)
        r = self.short(None, status=0)
        self.assertEqual(r["reasons"][0], head + "unknown (companion no record, loader done)" + tail)
        r = self.short(dl(outcome="delivered", committed=CHUNK), status=0)
        self.assertEqual(r["reasons"][0], head + "unknown (companion delivered, loader done)" + tail)

    def test_row_3_beyond_the_delivered_span_only_the_lines_that_differ_are_listed(self):
        rec = A.read_delivery(self.record("cap-reached"))
        got = rec["committed"]
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=got), device=self.data)       # the old memory beyond happens to hold the right bytes
        c = r["facts"]["check"]
        self.assertEqual((r["row"], c["bad_within"], c["bad_beyond"], c["last_good"]), (3, [], [], ATS[-1]))
        self.assertEqual([(l["at"], l["inside"], l["match"]) for l in c["lines"]],
                         [(131072, True, True), (229376, True, True), (327680, False, True), (425984, False, True), (524288, False, True)])

    def test_row_5_names_what_the_probe_said_or_the_exit_status(self):
        r = self.judge(text="SWEET hash: cannot open /dev/rmd1, errno 2\n", exit_status=0x61)
        self.assertEqual((r["row"], r["reasons"][0]), (5, "the probe could not open the root device: {'device': '/dev/rmd1', 'errno': 2}"))
        self.assertEqual(r["facts"]["exit_class"], "cannot-open-root-device")
        r = self.judge(text="*** SWEET hash probe: init running as PID 1 ***\n", exit_status=0x61)
        self.assertEqual((r["row"], r["reasons"][0]), (5, "the probe could not open the root device: exit status 0x61"))

    def test_each_exit_status_of_the_probe_is_named_in_the_facts(self):
        for status, name in ((0x60, "no-console"), (0x61, "cannot-open-root-device"), (0x62, "read-failed"), (0x63, "empty-device"), (81, None)):
            self.assertEqual(self.judge(exit_status=status)["facts"]["exit_class"], name, status)

    def test_row_4_without_a_time_for_the_return_says_zero(self):
        text = probe_text(self.data)
        cut = text[:text.index("SWEET hash: at=%d" % ATS[3])]
        r = self.judge(text=cut, exit_status=None, ending=A.classify_return(dict(klass="upload", dt=None)))
        self.assertEqual(r["row"], 4)
        self.assertIn("(+0.0 s)", r["reasons"][0])

    def test_row_3a_needs_both_the_companion_and_the_loader_to_say_done(self):
        text = probe_text(self.data)
        cut = text[:text.index("SWEET hash: at=%d" % ATS[3])]
        no_status = [l for l in loader_lines() if "nat079_status" not in l]
        r = self.judge(text=cut, exit_status=None, loader=no_status)
        self.assertEqual((r["row"], r.get("variant")), (8, None), r["reasons"])
        r = self.judge(delivery=dl(outcome="failed", error="late"), text=cut, exit_status=None)
        self.assertEqual((r["row"], r.get("variant")), (8, None), r["reasons"])

    def test_row_8_without_any_offset_says_what_the_companion_recorded(self):
        none = ["no loader record here"]
        r = self.judge(delivery=None, loader=none, text="", exit_status=None)
        self.assertEqual((r["row"], r["reasons"][0]), (8, "no committed offset in any record (loader values absent; companion outcome none)"))
        r = self.judge(delivery=dl(outcome="cap-reached", error="deadline", committed=None), loader=none, text="", exit_status=None)
        self.assertEqual((r["row"], r["reasons"][0]),
                         (8, "no committed offset in any record (loader values absent; companion outcome cap-reached: deadline)"))

    def test_without_a_committed_offset_nothing_is_judged_as_read_back(self):
        r = self.judge(delivery=None, loader=["no loader record here"], text=stale_line(1), exit_status=None)
        c = r["facts"]["check"]
        self.assertEqual((r["row"], c["bad_within"], c["bad_beyond"]), (8, [], [1]))

    def test_row_9_the_loader_refused_or_distrusted_the_receive_phase(self):
        for status in (3, 4, 5, 8):
            r = self.judge(loader=loader_lines(status=status, committed=0 if status != 8 else SIZE))
            self.assertEqual((r["row"], r["name"]), (9, "loader-refused-the-receive-phase"), status)
            self.assertEqual(r["facts"]["loader_status_name"], A.STATUS[status])
        # row 9 comes first: the read-back below is void
        rec = A.read_delivery(self.record("never-ready"))
        self.assertEqual(self.judge(delivery=rec, loader=loader_lines(status=5, committed=0), text="", exit_status=None)["row"], 9)
        self.assertEqual(self.judge(device=self.flipped(1), loader=loader_lines(status=5))["row"], 9)

    def test_row_10_the_device_checksum_of_a_committed_chunk_differs(self):
        rec = A.read_delivery(self.record("dma-lost"))
        self.assertEqual((rec["outcome"], rec["committed"]), ("failed", 3 * CHUNK))
        self.assertIn("DeliveryError", rec["error"])
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=3 * CHUNK), text="", exit_status=None)
        self.assertEqual((r["row"], r["name"]), (10, "chunk-checksum-failure"), r["reasons"])
        self.assertEqual(r["facts"]["committed"], 3 * CHUNK)

    # ------------------------------------------------------------------------------------------------------------------ precedence and bookkeeping
    def test_the_rows_are_tried_in_the_documented_order(self):
        dma = A.read_delivery(self.record("dma-lost"))
        flipped = self.flipped(100000)
        # 10 before 2 (the digests are void when a chunk's checksum failed), 2 before 5/6, 5/6 before 3
        self.assertEqual(self.judge(delivery=dma, loader=loader_lines(status=6, committed=3 * CHUNK), device=flipped)["row"], 10)
        self.assertEqual(self.judge(device=flipped, fail_after=300000, exit_status=0x62)["row"], 2)
        rec = A.read_delivery(self.record("cap-reached"))
        short = loader_lines(status=6, committed=rec["committed"])
        self.assertEqual(self.judge(delivery=rec, loader=short, text="", exit_status=0x61)["row"], 5)
        self.assertEqual(self.judge(delivery=rec, loader=short, text="", exit_status=0x62)["row"], 6)
        self.assertEqual(self.judge(delivery=rec, loader=short, text="", exit_status=None)["row"], 3)

    def test_disagreeing_records_are_reported_not_hidden(self):
        rec = A.read_delivery(self.record("delivered"))
        rec["committed"] = SIZE                      # the companion read the whole image from the device ...
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=SIZE - CHUNK))        # ... and the loader's final record says less
        self.assertEqual(r["row"], 3)
        self.assertTrue(any("the records disagree" in x for x in r["reasons"]), r["reasons"])
        self.assertEqual((r["facts"]["committed_device"], r["facts"]["committed_loader"], r["facts"]["committed"]), (SIZE, SIZE - CHUNK, SIZE - CHUNK))
        agree = self.judge()
        self.assertFalse(any("disagree" in x for x in agree["reasons"]))

    def test_the_committed_offset_comes_from_the_loader_when_both_exist_and_from_the_device_otherwise(self):
        rec = A.read_delivery(self.record("cap-reached"))
        r = self.judge(delivery=rec, loader=loader_lines(status=6, committed=rec["committed"] + CHUNK), text="", exit_status=None)
        self.assertEqual(r["facts"]["committed"], rec["committed"] + CHUNK)
        r = self.judge(delivery=rec, loader=[], text="", exit_status=None)
        self.assertEqual((r["facts"]["committed"], r["row"]), (rec["committed"], 3))
        r = self.judge(delivery=None, loader=[], text="", exit_status=None)
        self.assertEqual(r["row"], 8)
        self.assertIn("no committed offset", r["reasons"][0])

    def test_every_row_has_a_name_and_a_decision_that_exists(self):
        self.assertEqual(sorted(A.ROWS), list(range(1, 11)))
        template = (ROOT / "docs/procedures/nat-079/decision-template-nat078.md").read_text()
        table = re.search(r"## 6\. Pass rule.*?\n\n(\|.*?)\n\n", template, re.S).group(1)
        numbers = [l.split("|")[1].strip() for l in table.splitlines()[2:]]
        self.assertEqual(numbers, ["1", "2", "3", "3a", "4", "5", "6", "7", "8", "9", "10"])


class Glue(Runs):
    """analyze() and the command line around decide()."""

    def fake_chain(self, boot_lines, text, first_return=dict(dt=CAP_DT, klass="download"), exit_status=81, verdict="PASS"):
        seen = {}

        def chain(root, events, report, allow_synthetic=False, **kw):
            seen["image"] = A.A65.IMAGE
            return dict(verdict=verdict, root=dict(exit_status=exit_status, outcome="probe-ran-to-exit"), usb=dict(first_return=first_return),
                        kernel_log=dict(texts={"1": text}), boot=dict(name="boot-1"))
        return chain, seen

    def test_analyze_runs_the_chain_under_this_images_name_and_judges_the_run(self):
        out = self.record("delivered")
        root = self.tmp / "root.img"
        root.write_bytes(self.data)
        text = "Added memory device md1/rmd1 (01000000/0D000000) at FFFFFFF008974000 for 0000000093908000\n" + probe_text(self.data)
        chain, seen = self.fake_chain(loader_lines(), text)
        before = A.A65.IMAGE
        with mock.patch.object(A, "_ANALYZE65", chain), mock.patch.object(A.A65.A59, "boot_texts", lambda r, n: loader_lines()):
            res = A.analyze(Path("."), [], {}, out, root, SIZE, sha(self.data))
        self.assertEqual(seen["image"], "loader-diag-xnu-rx-md1")
        self.assertEqual(A.A65.IMAGE, before, "NAT-065's own name is restored")
        d = res["nat078"]["decision"]
        self.assertEqual((d["row"], d["pass"]), (1, True), d["reasons"])
        self.assertEqual(res["image"], "loader-diag-xnu-rx-md1")
        self.assertEqual(res["nat078"]["loader"]["status_name"], "done")
        self.assertEqual(res["nat078"]["ending"]["cls"], "cap-reset")
        self.assertEqual([m["name"] for m in res["nat078"]["kernel"]["md"]], ["md1"])
        self.assertEqual(res["nat078"]["chain_verdict"], "PASS")
        self.assertEqual(res["nat078"]["delivery"]["committed"], SIZE)

    def test_the_chain_verdict_decides_whether_the_text_is_this_images_own(self):
        out = self.record("delivered")
        root = self.tmp / "root.img"
        root.write_bytes(self.data)
        chain, _ = self.fake_chain(loader_lines(), probe_text(self.data), verdict="FAIL")
        with mock.patch.object(A, "_ANALYZE65", chain), mock.patch.object(A.A65.A59, "boot_texts", lambda r, n: loader_lines()):
            res = A.analyze(Path("."), [], {}, out, root, SIZE, sha(self.data))
        self.assertEqual(res["nat078"]["decision"]["row"], 8)

    def test_a_root_file_that_is_not_the_image_is_refused(self):
        root = self.tmp / "root.img"
        root.write_bytes(self.data[:-1] + b"\x00" if self.data[-1] else self.data[:-1] + b"\x01")
        chain, _ = self.fake_chain(loader_lines(), "")
        with mock.patch.object(A, "_ANALYZE65", chain), mock.patch.object(A.A65.A59, "boot_texts", lambda r, n: []):
            with self.assertRaisesRegex(ValueError, "not the image the run is judged against"):
                A.analyze(Path("."), [], {}, None, root, SIZE, sha(self.data))
        with mock.patch.object(A, "_ANALYZE65", chain), mock.patch.object(A.A65.A59, "boot_texts", lambda r, n: []):
            with self.assertRaises(ValueError):
                A.analyze(Path("."), [], {}, None, self.tmp / "short.img" if (self.tmp / "short.img").write_bytes(b"x") else None, SIZE, sha(self.data))

    def test_the_chain_without_a_kernel_log_or_a_boot_is_a_row_8_not_a_crash(self):
        root = self.tmp / "root.img"
        root.write_bytes(self.data)

        def chain(*a, **kw):
            return dict(verdict="FAIL", root=None, usb=None, kernel_log=None, boot=None)
        with mock.patch.object(A, "_ANALYZE65", chain):
            res = A.analyze(Path("."), [], {}, None, root, SIZE, sha(self.data))
        d = res["nat078"]["decision"]
        self.assertEqual(d["row"], 8)
        self.assertEqual(res["nat078"]["ending"]["cls"], "no-return-seen")
        self.assertFalse(res["nat078"]["probe"]["seen"])

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = A.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_the_command_line_refuses_an_existing_output_and_a_wrong_image(self):
        root = self.tmp / "root.img"
        root.write_bytes(self.data)
        events, report = self.tmp / "e.jsonl", self.tmp / "r.json"
        events.write_text("")
        report.write_text("{}")
        base = ["--archive", str(self.tmp), "--events", str(events), "--report", str(report), "--root", str(root), "--size", str(SIZE)]
        exists = self.tmp / "analysis.json"
        exists.write_text("x")
        code, _o, err = self.cli(*base, "--sha256", sha(self.data), "--out", str(exists))
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)
        self.assertEqual(exists.read_text(), "x")
        chain, _ = self.fake_chain([], "")
        with mock.patch.object(A, "_ANALYZE65", chain), mock.patch.object(A.A65.A59, "boot_texts", lambda r, n: []):
            code, _o, err = self.cli(*base, "--sha256", sha(b"other"))
        self.assertEqual(code, 2)
        self.assertIn("refused", err)

    def cli_args(self):
        root = self.tmp / "root.img"
        root.write_bytes(self.data)
        events, report = self.tmp / "e.jsonl", self.tmp / "r.json"
        events.write_text("")
        report.write_text("{}")
        return ["--archive", str(self.tmp), "--events", str(events), "--report", str(report), "--root", str(root), "--size", str(SIZE),
                "--sha256", sha(self.data)], report

    def test_the_command_line_writes_the_outputs_it_is_asked_for_and_only_those(self):
        base, _report = self.cli_args()
        base += ["--delivery", str(self.record("delivered"))]
        chain, _ = self.fake_chain([], probe_text(self.data))
        out, log = self.tmp / "analysis.json", self.tmp / "kernel-log.txt"
        with mock.patch.object(A, "_ANALYZE65", chain), mock.patch.object(A.A65.A59, "boot_texts", lambda r, n: loader_lines()):
            code, stdout, err = self.cli(*base, "--out", str(out), "--log-out", str(log))
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out.read_text(), stdout, "the file is the text that was printed")
            self.assertTrue(stdout.startswith('{\n "'), stdout[:30])
            self.assertEqual(json.loads(stdout)["nat078"]["decision"]["row"], 1)
            self.assertIn("===== dump 1", log.read_text())
            before = sorted(p.name for p in self.tmp.iterdir())
            code, stdout, err = self.cli(*base)
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(json.loads(stdout)["nat078"]["decision"]["row"], 1)
            self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), before, "no --out and no --log-out: nothing is written")

    def test_the_report_is_passed_on_as_read_and_an_unreadable_one_is_an_empty_dict(self):
        base, report = self.cli_args()
        seen = []

        def spy(archive, events, rep, delivery, root, size, sha256, allow_synthetic=False, **kw):
            seen.append(rep)
            return {"x": 1}

        report.write_text('{"k": 1}')
        with mock.patch.object(A, "analyze", spy):
            self.assertEqual(self.cli(*base)[0], 0)
            report.write_text("not json")
            self.assertEqual(self.cli(*base)[0], 0)
            report.unlink()
            self.assertEqual(self.cli(*base)[0], 0)
        self.assertEqual(seen, [{"k": 1}, {}, {}])

    @unittest.skipUnless((NAT68_RUN / "archive").exists(), "artifacts/nat-068/run-001 is not present")
    def test_the_real_nat068_archive_is_not_this_images_boot(self):
        root = self.tmp / "root.img"
        root.write_bytes(self.data)
        out = self.tmp / "analysis.json"
        code, stdout, err = self.cli("--archive", str(NAT68_RUN / "archive"), "--events", str(NAT68_RUN / "usb-events.jsonl"), "--report", str(NAT68_RUN / "report.json"),
                                     "--root", str(root), "--size", str(SIZE), "--sha256", sha(self.data), "--out", str(out))
        self.assertEqual(code, 0, err)
        doc = json.loads(out.read_text())
        self.assertEqual(json.loads(stdout)["nat078"]["decision"]["row"], doc["nat078"]["decision"]["row"])
        self.assertEqual(doc["image"], "loader-diag-xnu-rx-md1")
        self.assertNotEqual(doc["verdict"], "PASS", "NAT-068's boot carries the NAT-067 image's boot id")
        self.assertEqual(doc["nat078"]["decision"]["row"], 8)
        self.assertFalse(doc["nat078"]["decision"]["pass"])
        self.assertEqual(A.A65.IMAGE, "loader-diag-xnu-md0-usb")


if __name__ == "__main__":
    unittest.main()
