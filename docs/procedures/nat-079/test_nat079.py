#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-079 host tests: the delivery loader `loader-diag-xnu-rx-md1` as built by docs/procedures/nat-079/build.py.
Evidence kind: host-test. Nothing here runs on, or is sent to, the phone. The layers that need the built loader need unicorn and capstone
(artifacts/nat-065/venv), zig, and the local NAT-020/NAT-074 artifacts; each skips itself, and says why, when something is missing:

    artifacts/nat-065/venv/bin/python -W ignore -I docs/procedures/nat-079/test_nat079.py

Layers
  Hunks     make_variant79.patch_tree() on the real NAT-074 tree: every hunk matches exactly once (a drifted or duplicated anchor is an error that
            names the hunk and writes nothing), nothing outside the two files changes, the inserted text is exactly the hunks, the header ranges.
  Rules     build.py's check_rules79() on the boundary of every rule; option splitting; the command line.
  Layout    the record layouts of the compiled structs (aarch64) against the offsets the tests read; the layout of the built payload against the
            loader's argument rules: the destination is the md1 reserve, 16 KiB aligned, inside the window, outside the clear plan.
  Binary    capstone over the built loader.elf: NAT-074's rules unchanged (one s5e_wdt_pet call, in nat074_pet; the guard never pets), the receive
            phase called once from loader_main between the checkpoint-slot installation and the final pet, calling nothing that pets or resets,
            the cache-maintenance sites those of the NAT-074 loader.
  Pure      the compiled check_args / probe_pa / word / decide / fmt run in unicorn against independent models.
  Receive   the compiled nat079_receive_root in unicorn with a model of the engine's counters (usbmon_poll replaced): it ends on every byte
            committed, on the cap, on a failed self-test, on a premature host, on a missing or fallen engine; it writes nothing outside the
            reserve's probe words, the result and the engine's two fields; it refuses RX_BEGIN (leaves the placeholder) until the self-test passed.
  Pet       the real nat044_tick inside the receive loop: a pet every 30 s up to the cap, the NAT-044 reset sequence unchanged at the deadline.
The unicorn model has no caches, no MMU and no real memory attributes, and its engine is a counter model, not the USB controller. It shows the
contract of the new code in the compiled loader; it is not a measurement of the S24. The USB side of the contract is tested in
test_e2e79.py with the NAT-076 engine model."""
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"
BASE74 = ROOT / "artifacts/nat-074/build-002/loader-diag-xnu-bigwin-md1"
BASE74_TREE = BASE74 / "source/shim/e1s-xnu"
ENGINE76 = PROC / "nat-076/engine"
NAME = "loader-diag-xnu-rx-md1"
MIB = 1 << 20
PAGE = 16384
PROBES, WORDS = 8, 16
HOLD = 512
RX_CAP_S, RETURN_AFTER_S, DEADLINE_S, PET_S, REPORT_S = 240, 45, 360, 30, 10
REAL_RESERVE = 2475720704


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


try:
    import unicorn
    from unicorn import arm64_const as A
    import capstone
    HAVE_TOOLS = True
except ImportError:
    HAVE_TOOLS = False

needs_tree = unittest.skipUnless(BASE74_TREE.exists(), "the local NAT-074 build-002 source tree is missing")
needs_all = unittest.skipUnless(HAVE_TOOLS and shutil.which("zig") and LOADER_SRC.exists() and BASE74_TREE.exists(),
                                "unicorn/capstone (artifacts/nat-065/venv), zig, or the local NAT-020/NAT-074 artifacts are missing")

mv79 = _load("nat079_test_mv", HERE / "make_variant79.py")
b79 = _load("nat079_test_build", HERE / "build.py")
if HAVE_TOOLS:
    t74 = _load("nat079_test_t74", PROC / "nat-074/test_model.py")
    t44 = t74.t44
    Sim, ElfImage = t44.Sim, t44.ElfImage
    STACK, STOPPAGE, FREQ = t44.STACK, t44.STOPPAGE, t44.FREQ

_state = {}


def built():
    """Build the variant once per run with the real build.py (about a minute), into a temporary directory."""
    if "out" not in _state:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name) / "out"
        r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--out", str(out), "--loader-source", str(LOADER_SRC)],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("build failed:\n" + r.stderr[-3000:])
        _state["tmp"], _state["out"] = tmp, out
    return _state["out"]


def tearDownModule():
    if "tmp" in _state:
        _state["tmp"].cleanup()


def sha(b):
    import hashlib
    return hashlib.sha256(b).hexdigest()


def tree_copy(dst):
    """The two files make_variant79.patch_tree() reads, copied from the NAT-074 tree."""
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for f in mv79.FILE_HUNKS:
        shutil.copy(BASE74_TREE / f, dst / f)
    return dst


# ------------------------------------------------------------------------------------------------------------------------------- Hunks
@needs_tree
class Hunks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = tree_copy(Path(self.tmp.name) / "t")

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_hunk_matches_exactly_once_in_the_real_nat074_sources(self):
        for fname, hunks in mv79.FILE_HUNKS.items():
            text = (BASE74_TREE / fname).read_text()
            for name, old, _new in hunks:
                self.assertEqual(text.count(old), 1, f"{fname}:{name}")

    def test_the_patch_changes_exactly_the_two_files_and_adds_the_three_headers(self):
        rec = mv79.patch_tree(self.tree)
        self.assertEqual(sorted(p.name for p in self.tree.iterdir()),
                         sorted(["loader.c", "markerlib47.c", "nat079.h", "nat079_fixed.h", "nat079_impl.h"]))
        self.assertEqual(sorted(rec["files"]), sorted(["loader.c", "markerlib47.c", "nat079.h", "nat079_fixed.h", "nat079_impl.h"]))
        for f, r in rec["files"].items():
            self.assertEqual(r["variant_sha256"], sha((self.tree / f).read_bytes()), f)
            if f in mv79.FILE_HUNKS:
                self.assertEqual(r["source_sha256"], sha((BASE74_TREE / f).read_bytes()), f)

    def test_the_added_text_is_exactly_the_hunks_and_nothing_else_moved(self):
        mv79.patch_tree(self.tree)
        for fname, hunks in mv79.FILE_HUNKS.items():
            text = (self.tree / fname).read_text()
            for _name, old, new in hunks:
                self.assertEqual(text.count(new), 1)
                text = text.replace(new, old)           # undo each hunk
            self.assertEqual(text, (BASE74_TREE / fname).read_text(), fname)

    def test_the_source_headers_are_copied_byte_for_byte(self):
        mv79.patch_tree(self.tree)
        for f in mv79.SRC_FILES:
            self.assertEqual((self.tree / f).read_bytes(), (HERE / "src" / f).read_bytes())

    def test_a_missing_anchor_is_an_error_naming_the_hunk_and_writes_nothing(self):
        for fname, hunks in mv79.FILE_HUNKS.items():
            for name, old, _new in hunks:
                with tempfile.TemporaryDirectory() as t:
                    tree = tree_copy(Path(t) / "t")
                    text = (tree / fname).read_text()
                    (tree / fname).write_text(text.replace(old, "", 1))
                    before = {p.name: p.read_bytes() for p in tree.iterdir()}
                    with self.assertRaises(SystemExit) as cm:
                        mv79.patch_tree(tree)
                    self.assertIn(f"hunk {name}: expected exactly one match, found 0", str(cm.exception), f"{fname}:{name}")
                    self.assertEqual({p.name: p.read_bytes() for p in tree.iterdir()}, before, "a refused patch must not write")

    def test_a_duplicated_anchor_is_an_error_too(self):
        for fname, hunks in mv79.FILE_HUNKS.items():
            for name, old, _new in hunks:
                with tempfile.TemporaryDirectory() as t:
                    tree = tree_copy(Path(t) / "t")
                    text = (tree / fname).read_text()
                    (tree / fname).write_text(text.replace(old, old + old, 1))
                    with self.assertRaises(SystemExit) as cm:
                        mv79.patch_tree(tree)
                    self.assertIn(f"hunk {name}: expected exactly one match, found 2", str(cm.exception), f"{fname}:{name}")

    def test_derive_refuses_an_existing_output_and_leaves_the_source_alone(self):
        out = Path(self.tmp.name) / "o"
        out.mkdir()
        with self.assertRaises(SystemExit):
            mv79.derive(self.tree, out)
        self.assertEqual(list(out.iterdir()), [])

    def test_the_header_carries_the_parameters_and_refuses_what_the_build_could_not_use(self):
        h = mv79.header_text(240, 1, 10)
        self.assertIn("#define NAT079_RX_CAP_S\t\t240\t", h)
        self.assertIn("#define NAT079_RX_DIRECT\t1\t", h)
        self.assertIn("#define NAT079_REPORT_S\t\t10\t", h)
        self.assertIn('#include "nat079_fixed.h"', h)
        self.assertIn("#define NAT079_RX_DIRECT\t0\t", mv79.header_text(240, 0, 10))
        for bad, text in (((0, 1, 1), "receive cap"), ((-1, 1, 1), "receive cap"), ((581, 1, 10), "receive cap"), ((240, 2, 10), "rx_direct"),
                          ((240, -1, 10), "rx_direct"), ((240, 1, 0), "report period"), ((240, 1, 241), "report period"),
                          ((240, 1, -3), "report period")):
            with self.assertRaises(SystemExit, msg=str(bad)) as cm:
                mv79.header_text(*bad)
            self.assertIn(text, str(cm.exception), bad)           # the right rule refused it, not a later one
        mv79.header_text(580, 1, 580)                    # both ends of the accepted range
        mv79.header_text(1, 0, 1)

    def test_without_parameters_the_documented_defaults_reach_the_header_and_the_record(self):
        rec = mv79.patch_tree(str(self.tree))                    # a str path on purpose
        self.assertEqual(rec["params"], {"rx_cap_s": RX_CAP_S, "rx_direct": 1, "report_s": REPORT_S})
        hdr = (self.tree / "nat079.h").read_text()
        self.assertIn(f"#define NAT079_RX_CAP_S\t\t{RX_CAP_S}\t", hdr)
        self.assertIn("#define NAT079_RX_DIRECT\t1\t", hdr)
        self.assertIn(f"#define NAT079_REPORT_S\t\t{REPORT_S}\t", hdr)
        self.assertEqual(rec["hunks"], {"loader.c": ["include", "receive_call"],
                                        "markerlib47.c": ["include", "hold_buffer", "rx_config", "impl_include"]})

    def test_a_partial_parameter_set_keeps_the_defaults_of_the_rest(self):
        rec = mv79.patch_tree(self.tree, {"rx_cap_s": 100})
        self.assertEqual(rec["params"], {"rx_cap_s": 100, "rx_direct": 1, "report_s": REPORT_S})
        self.assertIn("NAT079_RX_CAP_S\t\t100\t", (self.tree / "nat079.h").read_text())

    def test_derive_copies_the_source_and_patches_only_the_copy(self):
        out = str(Path(self.tmp.name) / "o")                      # str on purpose
        before = {p.name: p.read_bytes() for p in self.tree.iterdir()}
        rec = mv79.derive(str(self.tree), out, {"rx_cap_s": 100})
        self.assertEqual({p.name: p.read_bytes() for p in self.tree.iterdir()}, before, "the source tree must stay as it was")
        self.assertEqual(sorted(p.name for p in Path(out).iterdir()),
                         sorted(["loader.c", "markerlib47.c", "nat079.h", "nat079_fixed.h", "nat079_impl.h"]))
        self.assertEqual(rec["params"]["rx_cap_s"], 100)
        for f, r in rec["files"].items():
            self.assertEqual(r["variant_sha256"], sha((Path(out) / f).read_bytes()), f)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(HERE / "make_variant79.py"), *map(str, args)], capture_output=True, text=True)

    def test_the_command_line_prints_the_record_writes_it_on_request_and_takes_all_three_parameters(self):
        out, record = Path(self.tmp.name) / "cli-out", Path(self.tmp.name) / "record.json"
        r = self.run_cli("--source", self.tree, "--out", out, "--record", record, "--rx-cap-s", "100", "--rx-direct", "0", "--report-s", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads(r.stdout)
        self.assertEqual(rec["params"], {"rx_cap_s": 100, "rx_direct": 0, "report_s": 5})
        text = record.read_text()
        self.assertEqual(json.loads(text), rec)
        self.assertEqual(text, json.dumps(rec, indent=1) + "\n")
        hdr = (out / "nat079.h").read_text()
        self.assertIn("NAT079_RX_CAP_S\t\t100\t", hdr)
        self.assertIn("NAT079_RX_DIRECT\t0\t", hdr)
        self.assertIn("NAT079_REPORT_S\t\t5\t", hdr)

    def test_main_returns_zero_when_called_in_process(self):
        # sys.exit(None) is also status 0, so a subprocess cannot tell `return 0` from no return; a direct call can
        import contextlib
        import io
        out = Path(self.tmp.name) / "inproc-out"
        argv = ["make_variant79.py", "--source", str(self.tree), "--out", str(out)]
        old, sys.argv = sys.argv, argv
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = mv79.main()
        finally:
            sys.argv = old
        self.assertEqual(rc, 0)
        self.assertIsInstance(rc, int)
        self.assertEqual(json.loads(buf.getvalue())["params"]["rx_direct"], 1)

    def test_the_command_line_defaults_and_no_record_unless_asked(self):
        out = Path(self.tmp.name) / "cli-out"
        r = self.run_cli("--source", self.tree, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["params"], {"rx_cap_s": RX_CAP_S, "rx_direct": 1, "report_s": REPORT_S})
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir() if p.is_file()), [], "no record file without --record")

    def test_the_command_line_needs_source_and_out_and_refuses_an_existing_out(self):
        out = Path(self.tmp.name) / "cli-out"
        self.assertEqual(self.run_cli("--out", out).returncode, 2)
        self.assertFalse(out.exists())
        self.assertEqual(self.run_cli("--source", self.tree).returncode, 2)
        out.mkdir()
        r = self.run_cli("--source", self.tree, "--out", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing to overwrite", r.stderr)

    def test_the_call_hands_the_loader_s_own_reserve_to_the_phase(self):
        # source review of the hunk: the destination and the length are NAT-074's reserve expressions, the same two the clear plan uses
        call = dict((n, new) for n, _o, new in mv79.LOADER_HUNKS)["receive_call"]
        self.assertIn("nat079_receive_root(win_base, mem_end, kernel_end - NAT074_RESERVE_BYTES, NAT074_RESERVE_BYTES, &r79);", call)
        plan = BASE74_TREE.joinpath("loader.c").read_text()
        self.assertIn("kernel_end - NAT074_RESERVE_BYTES", plan)      # the clear plan skips the same range


# ------------------------------------------------------------------------------------------------------------------------------- Rules
class Rules(unittest.TestCase):
    D = dict(root_bytes=REAL_RESERVE, deadline_s=360, pet_s=30, rx_cap_s=240, return_after_s=45, rx_direct=1, report_s=10)

    def ok(self, **kw):
        a = dict(self.D, **kw)
        return b79.check_rules79(a["root_bytes"], a["deadline_s"], a["pet_s"], a["rx_cap_s"], a["return_after_s"], a["rx_direct"], a["report_s"])

    def bad(self, text, **kw):
        with self.assertRaises(SystemExit) as cm:
            self.ok(**kw)
        self.assertIn(text, str(cm.exception), kw)

    def test_the_defaults_are_accepted_and_the_reserve_is_the_root_size(self):
        self.assertEqual(self.ok(), REAL_RESERVE)
        self.assertEqual(REAL_RESERVE % PAGE, 0)

    def test_a_root_size_that_is_not_a_whole_number_of_pages_is_refused_naming_pad_root(self):
        for n in (REAL_RESERVE - 4096, REAL_RESERVE + 4096, REAL_RESERVE - 1):
            self.bad("pad_root.py" if n % 4096 == 0 else "multiple of 4 KiB", root_bytes=n)
        self.bad("positive", root_bytes=0)

    def test_the_pet_period_plus_twenty_must_fit_the_83_second_watchdog(self):
        self.ok(pet_s=63)
        self.bad("pet period", pet_s=64)
        self.bad("pet period", pet_s=0)

    def test_the_receive_cap_is_in_zero_to_580(self):
        self.ok(rx_cap_s=1, report_s=1)
        self.ok(rx_cap_s=532, return_after_s=8, deadline_s=600)          # the largest cap the 600 s deadline leaves room for
        self.bad("deadline", rx_cap_s=533, return_after_s=8, deadline_s=600)
        self.bad("deadline", rx_cap_s=580)                                # inside (0, 580] but the deadline of 360 s cannot hold it
        self.bad("receive cap", rx_cap_s=0)
        self.bad("receive cap 581 s must be in (0, 580]", rx_cap_s=581)        # this rule, not the deadline rule that also names the cap
        self.bad("receive cap 0 s must be in (0, 580]", rx_cap_s=0)
        self.bad("receive cap -5 s must be in (0, 580]", rx_cap_s=-5)

    def test_loader_return_after_is_8_to_63(self):
        self.ok(return_after_s=8)
        self.ok(return_after_s=63, deadline_s=400)
        self.bad("loader_return_after", return_after_s=7)
        self.bad("loader_return_after", return_after_s=64, deadline_s=500)
        self.bad("loader_return_after", return_after_s=0)

    def test_the_deadline_leaves_the_cap_the_free_run_and_sixty_seconds_of_loader_work(self):
        self.ok(deadline_s=240 + 45 + 60)
        self.bad("deadline", deadline_s=240 + 45 + 59)
        self.ok(rx_cap_s=100, return_after_s=10, deadline_s=170)
        self.bad("deadline", rx_cap_s=100, return_after_s=10, deadline_s=169)

    def test_the_deadline_is_at_most_600_and_above_the_pet_period(self):
        self.ok(deadline_s=600)
        self.bad("cap 601", deadline_s=601)
        self.bad("cap 30", deadline_s=30, rx_cap_s=1, return_after_s=8, report_s=1)
        self.ok(deadline_s=69, rx_cap_s=1, return_after_s=8, report_s=1)

    def test_rx_direct_is_a_flag_and_the_report_period_is_inside_the_cap(self):
        self.ok(rx_direct=0)
        self.bad("rx-direct", rx_direct=2)
        self.bad("report period", report_s=0)
        self.bad("report period", report_s=241)
        self.ok(report_s=240)

    def test_option_splitting_applies_defaults_and_passes_the_rest_on(self):
        opts, rest = b79.split_options(["build.py", "--out", "X", "--loader-source", "S", "--rx-cap-s", "100"])
        self.assertEqual(opts["--rx-cap-s"], 100)
        self.assertEqual(opts["--deadline-s"], 360)
        self.assertEqual(rest[:5], ["build.py", "--out", "X", "--loader-source", "S"])
        for k in ("--root-bytes", "--deadline-s", "--pet-s"):                       # NAT-074's build reads these three
            self.assertEqual(rest[rest.index(k) + 1], str(opts[k]))
        for k in ("--rx-cap-s", "--return-after-s", "--rx-direct", "--report-s"):     # and must not see ours
            self.assertNotIn(k, rest)
        with self.assertRaises(SystemExit):
            b79.split_options(["build.py", "--rx-cap-s", "abc"])

    def test_the_defaults_are_the_documented_ones(self):
        opts, rest = b79.split_options(["build.py"])
        self.assertEqual(opts, {"--root-bytes": REAL_RESERVE, "--deadline-s": DEADLINE_S, "--pet-s": PET_S, "--rx-cap-s": RX_CAP_S,
                                "--return-after-s": RETURN_AFTER_S, "--rx-direct": 1, "--report-s": REPORT_S})
        self.assertEqual(rest, ["build.py", "--root-bytes", str(REAL_RESERVE), "--deadline-s", "360", "--pet-s", "30"])

    def test_an_option_without_its_value_is_left_for_the_next_stage_and_options_in_the_middle_are_taken(self):
        opts, rest = b79.split_options(["build.py", "--out", "X", "--rx-cap-s"])
        self.assertIn("--rx-cap-s", rest)                                           # NAT-074's parser will reject it, with its own message
        self.assertEqual(opts["--rx-cap-s"], RX_CAP_S)
        opts, rest = b79.split_options(["build.py", "--rx-cap-s", "100", "--out", "X", "--report-s", "5", "--loader-source", "S"])
        self.assertEqual((opts["--rx-cap-s"], opts["--report-s"]), (100, 5))
        self.assertEqual(rest[:5], ["build.py", "--out", "X", "--loader-source", "S"])
        with self.assertRaises(SystemExit) as cm:
            b79.split_options(["build.py", "--report-s", "abc"])
        self.assertIn("--report-s needs an integer, got 'abc'", str(cm.exception))

    def test_the_command_line_helper_refuses_a_base_line_that_lost_or_doubled_the_name(self):
        saved = b79.b67.APPEND
        try:
            for bad in (" launchdsuffix=release", saved + " loader_return_after=8"):
                b79.b67.APPEND = bad
                with self.assertRaises(SystemExit) as cm:
                    b79.cmdline_append(45)
                self.assertIn("exactly once", str(cm.exception))
                self.assertIn(bad, str(cm.exception))
        finally:
            b79.b67.APPEND = saved

    def test_the_command_line_gets_the_planned_return_after_exactly_once(self):
        a = b79.cmdline_append(45)
        self.assertEqual(a.count("loader_return_after="), 1)
        self.assertIn(" loader_return_after=45 ", a + " ")
        self.assertNotIn("loader_return_after=8", a)
        for tail in ("launchdsuffix=release", "cs_enforcement_disable=1", "e1stouch=0", "e1sbattery=0"):
            self.assertIn(tail, a)

    def test_the_builder_refuses_an_unpadded_root_before_it_builds_anything(self):
        r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--check-only", "--loader-source", "/nonexistent",
                            "--root-bytes", "2475712512"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pad_root.py", r.stderr)


# ------------------------------------------------------------------------------------------------------------------------------- Wrapper
class Wrapper(unittest.TestCase):
    """build.py main() around a stub for NAT-074's main(): what NAT-074's build sees while it runs, what is left behind, what is added to the
    record it wrote. No tree is built; the real build is checked in BuildRecord."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        b74, b52, b47, b67 = b79.b74, b79.b52, b79.b47, b79.b67
        self.saved = dict(argv=list(sys.argv), main=b74.main, orig=b74.mv.patch_tree, e52=b52.ENGINE, e47=b47.ENGINE, name=b74.NAME,
                          tag=b74.NEW_TAG, append=b67.APPEND, mv79=b79.mv79.patch_tree, state=dict(b79.STATE))
        self.calls, self.seen = [], {}
        b74.mv.patch_tree = self.fake_orig
        b79.mv79.patch_tree = self.fake79
        b52.ENGINE, b47.ENGINE, b74.NAME, b74.NEW_TAG = "E52", "E47", "NAME", "TAG"

    def tearDown(self):
        b74, b52, b47, b67 = b79.b74, b79.b52, b79.b47, b79.b67
        s = self.saved
        sys.argv[:] = s["argv"]
        b74.main, b74.mv.patch_tree, b52.ENGINE, b47.ENGINE, b74.NAME, b74.NEW_TAG, b67.APPEND = (
            s["main"], s["orig"], s["e52"], s["e47"], s["name"], s["tag"], s["append"])
        b79.mv79.patch_tree = s["mv79"]
        b79.STATE.clear()
        b79.STATE.update(s["state"])
        self.tmp.cleanup()

    def fake_orig(self, tree, params=None):
        self.calls.append(("orig", tree, params))
        return {"orig_record": True}

    def fake79(self, tree, params=None):
        self.calls.append(("79", tree, params))
        return {"variant79_record": len(self.calls)}

    def stub(self, out=None, call_patch=True, raises=None):
        def main74():
            b74, b67 = b79.b74, b79.b67
            self.seen = dict(argv=list(sys.argv), engines=(b79.b52.ENGINE, b79.b47.ENGINE), names=(b74.NAME, b74.NEW_TAG), append=b67.APPEND)
            if call_patch:
                self.seen["rec"] = b74.mv.patch_tree("TREE", {"p": 1})
            if raises:
                raise raises
            if out is not None:
                (Path(out) / "build.json").write_text(json.dumps({"pre": 1}))
        b79.b74.main = main74

    def run_main(self, argv):
        sys.argv[:] = argv
        b79.main()

    def test_nat074_s_build_sees_the_options_the_engine_the_names_and_the_planned_command_line(self):
        self.stub()
        argv = ["build.py", "--loader-source", "S", "--rx-cap-s", "200", "--return-after-s", "30", "--deadline-s", "400", "--report-s", "5",
                "--rx-direct", "0"]
        self.run_main(argv)
        seen = self.seen
        self.assertEqual(seen["argv"][:3], ["build.py", "--loader-source", "S"])
        for k, v in (("--root-bytes", str(REAL_RESERVE)), ("--deadline-s", "400"), ("--pet-s", "30")):
            self.assertEqual(seen["argv"][seen["argv"].index(k) + 1], v)
        for k in ("--rx-cap-s", "--return-after-s", "--rx-direct", "--report-s"):
            self.assertNotIn(k, seen["argv"])
        self.assertEqual(seen["engines"], (b79.ENGINE76, b79.ENGINE76))
        self.assertEqual(seen["names"], (NAME, "nat_attempt=NAT078-rx1"))
        self.assertIn(" loader_return_after=30 ", seen["append"] + " ")
        self.assertNotIn("loader_return_after=8", seen["append"])

    def test_the_variant_hunks_run_after_nat074_s_with_the_options_and_nat074_s_record_is_what_comes_back(self):
        self.stub()
        self.run_main(["build.py", "--loader-source", "S", "--rx-cap-s", "200", "--report-s", "5", "--rx-direct", "0", "--deadline-s", "400"])
        self.assertEqual(self.calls, [("orig", "TREE", {"p": 1}), ("79", "TREE", {"rx_cap_s": 200, "rx_direct": 0, "report_s": 5})])
        self.assertEqual(self.seen["rec"], {"orig_record": True})

    def test_everything_is_put_back_afterwards_and_also_when_the_build_fails(self):
        s = self.saved
        for raises in (None, SystemExit("build failed")):
            self.stub(raises=raises)
            argv = ["build.py", "--loader-source", "S", "--out", self.tmp.name]
            sys.argv[:] = argv
            try:
                b79.main()
            except SystemExit as e:
                self.assertIs(e, raises)
            self.assertEqual(sys.argv, argv)
            self.assertEqual(b79.b74.mv.patch_tree, self.fake_orig)
            self.assertEqual((b79.b52.ENGINE, b79.b47.ENGINE, b79.b74.NAME, b79.b74.NEW_TAG), ("E52", "E47", "NAME", "TAG"))
            self.assertEqual(b79.b67.APPEND, s["append"])

    def test_the_record_nat074_wrote_is_extended_with_the_parameters_the_hashes_and_the_command_line(self):
        out = Path(self.tmp.name)
        self.stub(out=out)
        self.run_main(["build.py", "--loader-source", "S", "--out", str(out), "--rx-cap-s", "200", "--return-after-s", "30", "--deadline-s", "400",
                       "--report-s", "5", "--rx-direct", "0"])
        text = (out / "build.json").read_text()
        d = json.loads(text)
        self.assertEqual(text, json.dumps(d, indent=1))
        self.assertEqual(d["pre"], 1)
        self.assertEqual(d["nat079_sources"], {f: sha((HERE / f).read_bytes()) for f in ("build.py", "make_variant79.py", "src/nat079_impl.h",
                                                                                        "src/nat079_fixed.h")})
        self.assertEqual(sorted(d["nat079_engine"]), sorted(b79.b47.ENGINE_FILES))
        self.assertTrue(d["nat079_engine"])
        for f, h in d["nat079_engine"].items():
            self.assertEqual(h, sha((ENGINE76 / f).read_bytes()), f)
        self.assertEqual(d["nat079_params"], {"root_bytes": REAL_RESERVE, "reserve_bytes": REAL_RESERVE, "deadline_s": 400, "pet_s": 30,
                                              "rx_cap_s": 200, "return_after_s": 30, "rx_direct": 0, "report_s": 5, "wdt_s": 83,
                                              "loader_work_margin_s": 60})
        self.assertEqual(d["nat079_variant"], {"variant79_record": 2})
        self.assertEqual(d["nat079_cmdline_append"], b79.cmdline_append(30))
        self.assertIn(" loader_return_after=30 ", d["nat079_cmdline_append"] + " ")
        self.assertIn("nothing here ran on a phone", d["nat079_note"])

    def test_no_variant_record_survives_from_an_earlier_call(self):
        out = Path(self.tmp.name)
        self.stub(out=out)
        self.run_main(["build.py", "--loader-source", "S", "--out", str(out)])
        self.assertEqual(json.loads((out / "build.json").read_text())["nat079_variant"], {"variant79_record": 2})
        self.stub(out=out, call_patch=False)
        self.run_main(["build.py", "--loader-source", "S", "--out", str(out)])
        self.assertIsNone(json.loads((out / "build.json").read_text())["nat079_variant"])

    def test_a_check_only_run_never_touches_a_record_and_a_run_without_out_needs_none(self):
        out = Path(self.tmp.name)
        (out / "build.json").write_text("untouched")
        self.stub()
        self.run_main(["build.py", "--check-only", "--loader-source", "S", "--out", str(out)])
        self.assertEqual((out / "build.json").read_text(), "untouched")
        self.run_main(["build.py", "--check-only", "--loader-source", "S"])
        self.run_main(["build.py", "--loader-source", "S"])

    def test_a_build_that_wrote_no_record_is_not_an_error_here(self):
        out = Path(self.tmp.name) / "nothing-written"
        out.mkdir()
        self.stub()
        self.run_main(["build.py", "--loader-source", "S", "--out", str(out)])
        self.assertEqual(list(out.iterdir()), [])

    def test_the_output_directory_is_the_word_after_out_wherever_it_stands(self):
        out = Path(self.tmp.name) / "o"
        out.mkdir()
        self.stub(out=out)
        self.run_main(["build.py", "--rx-cap-s", "100", "--loader-source", "S", "--out", str(out), "--report-s", "5"])
        self.assertIn("nat079_params", json.loads((out / "build.json").read_text()))

    # ---- --ramdisk: the md0 init of the image
    MACHO = b"\xcf\xfa\xed\xfe" + bytes(range(60))

    def ramdisk_file(self, data=None, name="init"):
        p = Path(self.tmp.name) / name
        p.write_bytes(self.MACHO if data is None else data)
        return p

    def stub_probe(self, out=None):
        """A stub for NAT-074's main() that asks the md0 builder for its bytes, as build_payload74 does."""
        def main74():
            self.seen = dict(argv=list(sys.argv), probe=b79.b65.build_probe("WORK"))
            if out is not None:
                (Path(out) / "build.json").write_text(json.dumps({"pre": 1}))
        b79.b74.main = main74

    def test_ramdisk_replaces_the_md0_builder_during_the_build_and_is_taken_out_of_nat074_s_arguments(self):
        f = self.ramdisk_file()
        saved = b79.b65.build_probe
        self.addCleanup(setattr, b79.b65, "build_probe", saved)
        self.stub_probe()
        self.run_main(["build.py", "--loader-source", "S", "--ramdisk", str(f), "--rx-cap-s", "200"])
        self.assertEqual(self.seen["probe"], self.MACHO)
        self.assertNotIn("--ramdisk", self.seen["argv"])
        self.assertNotIn(str(f), self.seen["argv"])
        self.assertEqual(self.seen["argv"][:3], ["build.py", "--loader-source", "S"])
        self.assertIs(b79.b65.build_probe, saved)			# put back afterwards

    def test_without_ramdisk_the_md0_builder_is_left_alone(self):
        saved = b79.b65.build_probe
        seen = []
        self.addCleanup(setattr, b79.b65, "build_probe", saved)
        b79.b65.build_probe = lambda work: seen.append(work) or b"ORIGINAL"
        probe = b79.b65.build_probe
        self.stub_probe()
        self.run_main(["build.py", "--loader-source", "S"])
        self.assertEqual(self.seen["probe"], b"ORIGINAL")
        self.assertIs(b79.b65.build_probe, probe)

    def test_the_md0_builder_is_put_back_when_the_build_fails(self):
        f = self.ramdisk_file()
        saved = b79.b65.build_probe
        self.addCleanup(setattr, b79.b65, "build_probe", saved)

        def failing():
            raise SystemExit("build failed")
        b79.b74.main = failing
        with self.assertRaises(SystemExit):
            self.run_main(["build.py", "--loader-source", "S", "--ramdisk", str(f)])
        self.assertIs(b79.b65.build_probe, saved)

    def test_the_record_names_the_ramdisk_and_its_hash_or_says_there_is_none(self):
        out = Path(self.tmp.name) / "o"
        out.mkdir()
        f = self.ramdisk_file()
        saved = b79.b65.build_probe
        self.addCleanup(setattr, b79.b65, "build_probe", saved)
        self.stub_probe(out)
        self.run_main(["build.py", "--loader-source", "S", "--out", str(out), "--ramdisk", str(f)])
        d = json.loads((out / "build.json").read_text())
        self.assertEqual(d["nat079_ramdisk"], {"path": str(f), "sha256": sha(self.MACHO), "bytes": len(self.MACHO),
                                               "replaces": "nat-065 probe-init (md0)"})
        self.stub(out=out)							# a build that does not ask for the md0 bytes: the original builder is not called here
        self.run_main(["build.py", "--loader-source", "S", "--out", str(out)])
        self.assertIsNone(json.loads((out / "build.json").read_text())["nat079_ramdisk"])

    def test_a_bad_ramdisk_is_refused_before_the_build_starts(self):
        self.stub()
        macho = b"\xcf\xfa\xed\xfe"
        cases = {"missing": Path(self.tmp.name) / "nope",
                 "a directory": Path(self.tmp.name),
                 "empty": self.ramdisk_file(b"", "empty"),
                 "not a Mach-O": self.ramdisk_file(b"\x7fELF" + bytes(100), "elf"),
                 "32-bit Mach-O": self.ramdisk_file(b"\xce\xfa\xed\xfe" + bytes(100), "m32"),
                 "too big": self.ramdisk_file(macho + bytes(b79.RAMDISK_MAX - 3), "big")}
        for name, path in cases.items():
            self.seen = {}
            with self.assertRaises(SystemExit, msg=name):
                self.run_main(["build.py", "--loader-source", "S", "--ramdisk", str(path)])
            self.assertEqual(self.seen, {}, name)			# NAT-074's main never ran
        self.assertEqual(self.calls, [])
        # the bounds themselves are fine: one byte of Mach-O header-less magic is a file, the limit is inclusive
        ok = self.ramdisk_file(macho + bytes(b79.RAMDISK_MAX - 4), "limit")
        self.assertEqual(len(b79.read_ramdisk(ok)), b79.RAMDISK_MAX)
        self.assertEqual(b79.read_ramdisk(self.ramdisk_file(macho, "tiny")), macho)

    def test_the_ramdisk_size_limits_are_exact_and_each_refusal_gives_its_own_reason(self):
        """1 MiB is the documented limit (written out here, not read back from the constant); an empty file and a one-byte file are refused for
        different reasons, which is what separates `0 < len` from `0 <= len` and from `1 < len`."""
        macho = b"\xcf\xfa\xed\xfe"
        with self.assertRaisesRegex(SystemExit, "is 0 bytes"):
            b79.read_ramdisk(self.ramdisk_file(b"", "empty"))
        with self.assertRaisesRegex(SystemExit, "not a 64-bit Mach-O"):
            b79.read_ramdisk(self.ramdisk_file(b"\xcf", "one"))
        self.assertEqual(len(b79.read_ramdisk(self.ramdisk_file(macho + bytes(1048576 - 4), "limit"))), 1048576)
        with self.assertRaisesRegex(SystemExit, "is 1048577 bytes"):
            b79.read_ramdisk(self.ramdisk_file(macho + bytes(1048577 - 4), "over"))

    def test_take_ramdisk_parsing(self):
        self.assertEqual(b79.take_ramdisk(["a", "b"]), (None, ["a", "b"]))
        self.assertEqual(b79.take_ramdisk(["a", "--ramdisk", "F", "b"]), (Path("F"), ["a", "b"]))
        self.assertEqual(b79.take_ramdisk(["--ramdisk", "F"]), (Path("F"), []))
        self.assertEqual(b79.take_ramdisk(["a", "b", "--ramdisk", "F"]), (Path("F"), ["a", "b"]))
        for bad in (["a", "--ramdisk"], ["--ramdisk", "F", "--ramdisk", "G"]):
            with self.assertRaises(SystemExit):
                b79.take_ramdisk(bad)

    def test_the_modules_are_registered_under_the_names_they_were_loaded_with(self):
        self.assertIs(sys.modules["nat079_make_variant79"], b79.mv79)
        self.assertIs(sys.modules["nat079_nat074_build"], b79.b74)


# ------------------------------------------------------------------------------------------------------------------------------- layouts
LAYOUT_FLAGS = ["-DMK_TRIG=1", "-DMK_LOADER=1", "-DMK_XNU_CKPT=1", "-DNAT044_DEADLINE_S=360", "-DNAT044_REASON=S5E_REASON_DOWNLOAD",
                "-DNAT047_FAULT=0", '-DNAT047_TAG="x"', "-DLAD_WRITING_RUNGS", "-DNAT052_SERVICE_TENTHS=3"]
SIZES = {"uint8_t": 1, "uint16_t": 2, "uint32_t": 4, "int32_t": 4, "uint64_t": 8}


def record_layouts(tree):
    """{struct name: ({field: (offset, size)}, sizeof)} for struct usbmon, nat047 and nat079_result as the aarch64 compiler lays them out."""
    r = subprocess.run(["zig", "cc", "-target", "aarch64-freestanding", "-O2", "-ffreestanding", "-fno-builtin", "-mgeneral-regs-only",
                        *LAYOUT_FLAGS, f"-I{tree}", f"-I{ENGINE76}", f"-I{PROC / 'nat-045/src'}", "-fsyntax-only", "-Xclang",
                        "-fdump-record-layouts", str(Path(tree) / "markerlib52.c")], capture_output=True, text=True)
    # zig's driver exits 1 after the syntax-only pass ("FileNotFound" for an object it never writes): the dump is on stdout and is checked below
    if "[sizeof=" not in r.stdout:
        raise RuntimeError(r.stderr[-2000:])
    out, cur = {}, None
    for ln in (r.stdout + r.stderr).splitlines():
        m = re.match(r"\s*\d+(?::\d+-\d+)? \| ( *)(.+)$", ln)
        if m and not m.group(1) and m.group(2).startswith("struct "):
            cur = m.group(2)[len("struct "):]
            if cur in out:
                cur = None
            else:
                out[cur] = [{}, 0]
            continue
        if cur is None:
            continue
        s = re.search(r"\[sizeof=(\d+)", ln)
        if s:
            out[cur][1] = int(s.group(1))
            cur = None
            continue
        m = re.match(r"\s*(\d+) \|   (\S.*)$", ln)
        if m:
            decl = m.group(2)
            name = decl.split()[-1]
            typ = decl[:decl.rfind(name)].strip()
            size = 8 if typ.endswith("*") else SIZES.get(typ, 0)
            out[cur][0][name] = (int(m.group(1)), size)
    return {k: (v[0], v[1]) for k, v in out.items()}


@needs_all
class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = built()
        cls.tree = cls.out / NAME / "source/shim/e1s-xnu"
        cls.lay = record_layouts(cls.tree)

    def test_the_fields_the_tests_read_exist_with_the_expected_sizes(self):
        u = self.lay["usbmon"][0]
        for f, size in (("rx_dest", 8), ("rx_size", 8), ("rx_present", 1), ("rx_direct", 1), ("rx_enabled", 1), ("rx_state", 1),
                        ("rx_committed", 8), ("rx_bytes", 8), ("rx_last_sum", 8), ("rx_trbs", 4), ("rx_errors", 4), ("rx_dups", 4),
                        ("rx_gaps", 4), ("rx_rejects", 4), ("rx_resets", 4), ("rx_aborts", 4)):
            self.assertEqual(u[f][1], size, f)
        n = self.lay["nat047"][0]
        self.assertEqual(n["m"][0], 0, "the engine object must be first: its DMA block must be 64-byte aligned")
        for f in ("up", "polling"):
            self.assertEqual(n[f][1], 4)

    def test_the_result_struct_is_what_the_driver_unpacks(self):
        fields, size = self.lay["nat079_result"]
        names = ["pa", "bytes", "committed", "rx_bytes", "trbs", "errors", "resets", "dups", "gaps", "rejects", "aborts", "last_sum",
                 "elapsed_ticks", "freq", "selftest_bad_pa"]
        self.assertEqual([fields[k][0] for k in names], [8 * i for i in range(15)])
        self.assertEqual(fields["status"][0], 120)
        self.assertEqual(fields["pad"], (124, 4), "the tail padding is a named field: the driver unpacks 15 words and two int32")
        self.assertEqual(size, 128)


    def test_the_engine_s_dma_block_is_the_rx_buffer_and_the_image_stays_under_one_mebibyte(self):
        img = (self.out / NAME / "Image").read_bytes()
        self.assertLess(len(img), MIB)
        self.assertGreater(len(img), 307200)                         # the NAT-074 loader (the engine now holds a 64 KiB stage buffer)
        self.assertEqual(self.lay["usbmon"][1] % 64, 0)

    def test_the_built_layout_hands_the_phase_a_range_it_accepts_and_the_clear_plan_leaves_alone(self):
        rec = json.loads((self.out / "build.json").read_text())
        lay = rec["nat074_payload"]["layout"]
        self.assertEqual(lay["reserve_bytes"], REAL_RESERVE)
        self.assertEqual(lay["mem_size"], 4096 * MIB)
        win_base = 0x8FE400000
        mem_end = win_base + lay["mem_size"]
        kernel_end = win_base + lay["kernel_end_offset"]
        pa = kernel_end - REAL_RESERVE
        h = t74.header_values(self.tree)
        self.assertEqual(h["NAT074_RESERVE_BYTES"], REAL_RESERVE)
        self.assertEqual(pa, win_base + lay["reserve_offset"])
        self.assertEqual(pa % PAGE, 0)
        self.assertGreaterEqual(pa, win_base)
        self.assertLessEqual(kernel_end, mem_end)
        elf = ElfImage(self.out / NAME / "loader.elf")
        s = Sim(elf)
        s.limit_s = 1e9
        eng = elf.sym["g_nat047"]
        self.assertEqual(s.call("nat079_check_args", win_base, mem_end, pa, REAL_RESERVE, eng, eng + self.lay["usbmon"][1]) & 0xFFFFFFFF, 0)
        buf = STACK + 0x8000
        s.call("nat074_clear_plan", win_base, mem_end, kernel_end, buf)
        raw = bytes(s.mu.mem_read(buf, 48))
        spans = [struct.unpack_from("<QQ", raw, 16 * i) for i in range(3)]
        self.assertGreater(sum(n for _, n in spans), 100 * MIB)
        for base, n in spans:
            self.assertFalse(n and base < pa + REAL_RESERVE and base + n > pa, "a cleared span touches the receive range")
        self.assertLess(eng + self.lay["usbmon"][1], win_base, "the engine's own memory is outside the window")


@needs_all
class BuildRecord(unittest.TestCase):
    """The real build's record: NAT-074's own entries still there and filled in, ours added, the command line in the image's boot-args."""
    @classmethod
    def setUpClass(cls):
        cls.out = built()
        cls.d = json.loads((cls.out / "build.json").read_text())

    def test_nat074_s_variant_record_is_kept_and_ours_lists_what_was_patched(self):
        v74, v79 = self.d["nat074_variant"], self.d["nat079_variant"]
        self.assertIsInstance(v74, dict)
        self.assertTrue(v74["files"])
        self.assertEqual(v79["params"], {"rx_cap_s": RX_CAP_S, "rx_direct": 1, "report_s": REPORT_S})
        tree = self.out / NAME / "source/shim/e1s-xnu"
        self.assertEqual(sorted(v79["files"]), sorted(["loader.c", "markerlib47.c", "nat079.h", "nat079_fixed.h", "nat079_impl.h"]))
        for f, r in v79["files"].items():
            self.assertEqual(r["variant_sha256"], sha((tree / f).read_bytes()), f)
        # our hunks start from what NAT-074's variant left: loader.c is patched by both, markerlib47.c only by us
        self.assertEqual(v79["files"]["loader.c"]["source_sha256"], v74["files"]["loader.c"]["variant_sha256"])
        self.assertNotIn("markerlib47.c", v74["files"])

    def test_the_parameters_the_hashes_and_the_planned_command_line_are_recorded(self):
        d = self.d
        self.assertEqual(d["nat079_params"], {"root_bytes": REAL_RESERVE, "reserve_bytes": REAL_RESERVE, "deadline_s": DEADLINE_S, "pet_s": PET_S,
                                              "rx_cap_s": RX_CAP_S, "return_after_s": RETURN_AFTER_S, "rx_direct": 1, "report_s": REPORT_S,
                                              "wdt_s": 83, "loader_work_margin_s": 60})
        self.assertEqual(d["nat079_sources"], {f: sha((HERE / f).read_bytes()) for f in ("build.py", "make_variant79.py", "src/nat079_impl.h",
                                                                                        "src/nat079_fixed.h")})
        self.assertEqual({f: sha((ENGINE76 / f).read_bytes()) for f in d["nat079_engine"]}, d["nat079_engine"])
        self.assertIn("usbmon.c", d["nat079_engine"])
        self.assertEqual(d["nat079_cmdline_append"], " loader_return_after=45 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0")
        cmd = d["nat074_cmdline"]
        self.assertEqual(cmd["append"], d["nat079_cmdline_append"])
        self.assertIn(" loader_return_after=45 ", cmd["cmdline"] + " ")
        self.assertNotIn("loader_return_after=8", cmd["cmdline"])
        self.assertIn("nat_attempt=NAT078-rx1", cmd["cmdline"])
        text = (self.out / "build.json").read_text()
        self.assertEqual(text, json.dumps(json.loads(text), indent=1))

    def test_the_build_compiled_the_nat076_engine_from_its_own_directory_and_recorded_its_files(self):
        cmds = [c for c in self.d["commands"] if any(str(a).endswith("/usbmon.c") for a in c.get("argv", []))]
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0]["exit_code"], 0)
        self.assertEqual(cmds[0]["stderr"], "")
        self.assertIn(str(ENGINE76 / "usbmon.c"), cmds[0]["argv"])
        self.assertIn("-I" + str(ENGINE76), cmds[0]["argv"])
        self.assertEqual(self.d["nat041_engine"], self.d["nat079_engine"], "NAT-065's engine key must describe the engine that was compiled")


# ------------------------------------------------------------------------------------------------------------------------------- Binary
@needs_all
class Binary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = built() / NAME / "loader.elf"
        cls.img, cls.fns = t74.disasm_functions(cls.path)
        cls.names = {v: k for k, v in cls.img.sym.items()}

    def callers(self, target):
        a = self.img.sym[target]
        return sorted((n, m) for n, ins in self.fns.items() for m, t, _ in t74.bl_targets(ins) if t == a)

    def calls_of(self, fn):
        return sorted({self.names.get(t, hex(t)) for m, t, _ in t74.bl_targets(self.fns[fn]) if m == "bl"})

    def test_nat074_rules_one_pet_call_in_the_whole_image_reached_only_from_the_tick_and_the_final_pet(self):
        self.assertEqual(self.callers("s5e_wdt_pet"), [("nat074_pet", "bl")])
        self.assertEqual(self.callers("nat074_pet"), [("nat044_tick", "b"), ("nat074_final_pet", "b")])
        self.assertEqual(self.callers("nat074_final_pet"), [("loader_main", "bl")])

    def test_the_guard_arms_once_for_83_seconds_and_never_pets_or_disarms(self):
        ins = self.fns["recovery_guard"]
        arm = self.img.sym["s5e_wdt_arm"]
        calls = [i for m, t, i in t74.bl_targets(ins) if m == "bl" and t == arm]
        self.assertEqual(len(calls), 1)
        self.assertTrue(any(i.mnemonic == "mov" and i.op_str == "w1, #0x53" for i in ins if calls[0].address - 20 <= i.address < calls[0].address))
        forbidden = {self.img.sym["s5e_wdt_pet"], self.img.sym["s5e_wdt_disarm"]}
        self.assertFalse([i for m, t, i in t74.bl_targets(ins) if t in forbidden])

    def test_the_receive_phase_is_called_once_from_loader_main(self):
        self.assertEqual(self.callers("nat079_receive_root"), [("loader_main", "bl")])

    def test_the_receive_phase_comes_after_the_slot_installation_and_before_the_final_pet(self):
        order = [(i.address, self.names.get(t)) for m, t, i in t74.bl_targets(self.fns["loader_main"]) if m == "bl"]
        seq = [n for _a, n in sorted(order)]
        k = seq.index("nat079_receive_root")
        self.assertLess(seq.index("nat036_install"), k)
        self.assertLess(k, seq.index("nat074_final_pet"))
        self.assertEqual(seq.count("nat079_receive_root"), 1)
        self.assertEqual(seq.count("nat074_final_pet"), 1)

    def test_the_receive_phase_pets_resets_and_polls_only_through_the_existing_paths(self):
        self.assertEqual(self.calls_of("nat079_receive_root"),
                         ["nat044_tick", "nat079_check_args", "nat079_decide", "nat079_fmt", "nat079_selftest", "usbmon_log", "usbmon_poll"])
        self.assertEqual(self.calls_of("nat079_selftest"), ["nat079_probe_pa", "nat079_word"])
        for f in ("nat079_check_args", "nat079_probe_pa", "nat079_word", "nat079_decide", "nat079_fmt"):
            self.assertEqual(self.calls_of(f), [], f)

    def test_the_new_code_has_no_cache_maintenance_and_the_loader_side_sites_are_those_of_the_nat074_loader(self):
        def sites(fns):
            return {n: sum(1 for i in ins if i.mnemonic == "dc" and "civac" in i.op_str) for n, ins in fns.items()}
        _img, base = t74.disasm_functions(BASE74 / "loader.elf")
        now, was = sites(self.fns), sites(base)
        engine = {l.split()[2] for l in subprocess.run(["nm", str(self.path.parent / "13-usbmon.c.o")], capture_output=True, text=True).stdout.splitlines()
                  if len(l.split()) == 3 and l.split()[1] in "tT"}
        self.assertIn("usbmon_poll", engine)
        for name in set(now) | set(was):
            if name in engine:
                continue
            self.assertEqual(now.get(name, 0), was.get(name, 0), f"{name}: the loader side must keep its cache maintenance as it was")
        self.assertGreater(sum(was.values()), 0)
        # the engine gained sites by design (the bulk-OUT buffers are synced around the controller's DMA); the new phase has none
        self.assertGreater(sum(now[n] for n in engine if n in now), sum(was[n] for n in engine if n in was))
        for f in ("nat079_receive_root", "nat079_selftest", "nat079_check_args", "nat079_fmt"):
            self.assertFalse([i for i in self.fns[f] if i.mnemonic == "dc"], f)

    def test_the_new_code_uses_no_vector_or_float_registers(self):
        # the loader runs with the MMU off and strict alignment, general registers only
        for f in ("nat079_receive_root", "nat079_selftest", "nat079_check_args", "nat079_probe_pa", "nat079_word", "nat079_decide", "nat079_fmt"):
            for i in self.fns[f]:
                self.assertIsNone(re.search(r"\b[vqdsbh][0-9]{1,2}\b", i.op_str), f"{f}: {i.mnemonic} {i.op_str}")


# ------------------------------------------------------------------------------------------------------------------------------- Pure
def ref_check(win_base, mem_end, pa, nbytes, lo, hi):
    """Spec: the range is a whole number of 16 KiB pages, at least eight of them, inside the window with no 64-bit wrap, and the engine's own
    memory [lo, hi) does not intersect it."""
    if pa % PAGE or nbytes % PAGE or nbytes < PROBES * PAGE:
        return 3
    end = pa + nbytes
    if end >= 1 << 64:
        return 3
    if pa < win_base or end > mem_end:
        return 3
    if lo < end and hi > pa:
        return 3
    return 0


def ref_word(salt, i, k, p):
    v = ((salt + (i << 32) + k) * 0x9E3779B97F4A7C15) & (2**64 - 1)
    v ^= v >> 29
    return (~v & (2**64 - 1)) if p else v


@needs_all
class Pure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.elf = ElfImage(built() / NAME / "loader.elf")
        cls.sim = Sim(cls.elf)
        cls.sim.limit_s = 1e9

    def call(self, name, *a):
        return self.sim.call(name, *a)

    def test_check_args_matches_the_spec_on_a_grid_around_every_boundary(self):
        # NOTE: the compiler specialises this static function to its one call site, so the engine range [lo, hi) is the loader's own
        # g_nat047 whatever x4/x5 say; the boundaries of that comparison are exercised on the generic host build in test_e2e79.CheckArgs.
        win, end = 0x8FE400000, 0x8FE400000 + 4096 * MIB
        lo, hi = 0x41dc0, 0x41dc0 + 76224
        cases = []
        for pa in (win, win + PAGE, win - PAGE, win + 77 * MIB, end - 8 * PAGE, end - 8 * PAGE + PAGE, win + 1, win + 512, 0, lo & ~(PAGE - 1)):
            for n in (7 * PAGE, 8 * PAGE, 8 * PAGE + 512, 8 * PAGE + 1, REAL_RESERVE, end - win, end - win + PAGE, 0, PAGE, 2**64 - 8 * PAGE):
                cases.append((win, end, pa, n, lo, hi))
        cases += [(0, 2**64 - 1, 2**64 - 8 * PAGE, 8 * PAGE, lo, hi),             # pa + bytes wraps to exactly 0
                  (0, 2**64 - 1, 2**64 - 16 * PAGE, 8 * PAGE, lo, hi),            # the same range one block lower: valid
                  (0, 2**40, 0x40000, 0x40000, lo, hi),                           # the engine inside the range
                  (0, 2**40, 0x100000, 0x40000, lo, hi),                          # clear of the engine
                  (0, 2**40, lo & ~(PAGE - 1), 8 * PAGE, lo, hi),                 # starts at the engine's page
                  (0, 2**40, (hi + PAGE - 1) & ~(PAGE - 1), 8 * PAGE, lo, hi),    # first page after the engine
                  (0, 2**40, ((lo & ~(PAGE - 1)) - 8 * PAGE), 8 * PAGE, lo, hi),  # ends exactly at the engine's page
                  ]
        seen = set()
        for c in cases:
            want = ref_check(*c)
            seen.add(want)
            self.assertEqual(self.call("nat079_check_args", *c) & 0xFFFFFFFF, want, c)
        self.assertEqual(seen, {0, 3})

    def test_probe_pages_are_the_first_the_last_and_six_distinct_interior_pages_of_the_range(self):
        for pa, n in ((0x8FE400000 + 77 * MIB, REAL_RESERVE), (0x900000000, 8 * PAGE), (0x900000000, 9 * PAGE), (0x900000000, 100 * PAGE),
                      (0x900000000, 4 * MIB)):
            pages = n // PAGE
            got = [self.call("nat079_probe_pa", pa, n, i) for i in range(PROBES)]
            self.assertEqual(got[0], pa)
            self.assertEqual(got[1], pa + (pages - 1) * PAGE)
            for g in got:
                self.assertEqual(g % PAGE, 0)
                self.assertTrue(pa <= g and g + WORDS * 8 <= pa + n, (pa, n, hex(g)))
            self.assertEqual(len(set(got)), PROBES, "probe pages must be distinct")
            interior = got[2:]
            self.assertEqual(interior, sorted(interior))
            self.assertTrue(all(pa < g < got[1] for g in interior))
            for i in range(2, PROBES):
                self.assertEqual(got[i], pa + (pages * (i - 1) // (PROBES - 1)) * PAGE)       # spread evenly

    def test_the_pattern_words_match_the_model_and_the_two_passes_are_complements(self):
        for salt in (0, 1, 0xDEADBEEFCAFEF00D, 2**64 - 1):
            for i in (0, 1, 7):
                for k in (0, 1, 15):
                    for p in (0, 1):
                        self.assertEqual(self.call("nat079_word", salt, i, k, p), ref_word(salt, i, k, p), (salt, i, k, p))
                    self.assertEqual(self.call("nat079_word", salt, i, k, 1), ~self.call("nat079_word", salt, i, k, 0) & (2**64 - 1))
        words = {self.call("nat079_word", 12345, i, k, 0) for i in range(PROBES) for k in range(WORDS)}
        self.assertEqual(len(words), PROBES * WORDS, "no two words of a self-test may be equal")
        self.assertNotEqual(self.call("nat079_word", 1, 0, 0, 0), self.call("nat079_word", 2, 0, 0, 0))

    def test_decide_is_done_first_then_engine_down_then_timeout_then_running(self):
        for up in (0, 1):
            for committed, total in ((0, 100), (99, 100), (100, 100), (101, 100)):
                for elapsed, cap in ((0, 50), (49, 50), (50, 50), (51, 50)):
                    if committed >= total:
                        want = 0
                    elif not up:
                        want = 7
                    elif elapsed >= cap:
                        want = 6
                    else:
                        want = -1
                    got = self.call("nat079_decide", up, committed, total, elapsed, cap) & 0xFFFFFFFF
                    self.assertEqual(got - (1 << 32) if got >= 1 << 31 else got, want, (up, committed, total, elapsed, cap))

    def test_decide_compares_unsigned_64_bit_values(self):
        big = 1 << 63
        self.assertEqual(self.call("nat079_decide", 1, big, 10, 0, 5) & 0xFFFFFFFF, 0)          # committed above 2^63 is "all of it"
        self.assertEqual(self.call("nat079_decide", 1, 0, 10, big, 1) & 0xFFFFFFFF, 6)          # elapsed above 2^63 is "late"
        self.assertEqual(self.call("nat079_decide", 1, 5, big + 1, big, big + 1) & 0xFFFFFFFF, 0xFFFFFFFF)
        self.assertEqual(self.call("nat079_decide", 1, big - 1, big, big - 1, big) & 0xFFFFFFFF, 0xFFFFFFFF)

    def test_the_progress_line_is_decimal_only_and_has_the_documented_shape(self):
        buf = STACK + 0x4000
        for args in ((0, 0, 0, 0), (1, 2, 3, 4), (9, 10, 99, 100), (2360, 12345, 0, 240), (2**32, 2**32 - 1, 2**32 + 1, 7),
                     (2**64 - 1, 2**64 - 1, 2**64 - 1, 2**64 - 1), (1234567890123456789, 10, 100, 1000)):
            n = self.call("nat079_fmt", buf, *args) & 0xFFFFFFFF
            got = bytes(self.sim.mu.mem_read(buf, n)).decode()
            want = "NAT079 rx MiB=%d trbs=%d err=%d t=%ds" % args
            self.assertEqual(got, want)
            self.assertEqual(n, len(want))
            self.assertLessEqual(n, 109)
        longest = self.call("nat079_fmt", buf, *(2 ** 64 - 1,) * 4) & 0xFFFFFFFF
        self.assertEqual(longest, 109)
        self.assertLessEqual(longest, int(re.search(r"NAT079_LINE_MAX\s+(\d+)u", (HERE / "src/nat079_fixed.h").read_text()).group(1)))


# ------------------------------------------------------------------------------------------------------------------------------- Receive
WIN = 0x900000000
SENTINEL = 0xA5


class StepSim(Sim):
    """Sim with a coarse counter: every read of CNTVCT advances `step` ticks, so a 240 s cap takes a few thousand loop rounds."""
    def __init__(self, elf, step, init=None):
        self.step = step
        super().__init__(elf, init)

    def _mrs(self, uc, reg, cp, ud):
        if (cp.crn, cp.crm, cp.op0, cp.op1, cp.op2) == (14, 0, 3, 3, 2):
            self.clk += self.step
            if (self.clk - self.clk0) / FREQ > self.limit_s:
                uc.emu_stop()
            uc.reg_write(reg, self.clk)
            return True
        return super()._mrs(uc, reg, cp, ud)


RET = struct.pack("<I", 0xD65F03C0)


class Run:
    """One call of the compiled nat079_receive_root with a fake window, a counter model of the engine and the loader's tick/poll/log replaced
    by observers. Engine fields are read and written at the offsets the compiler reports."""

    def __init__(self, elf, lay, win_size=16 * MIB, pa_off=2 * MIB, nbytes=4 * MIB, step_ms=100, fake_tick=True, init=None, fill=True):
        self.elf, self.lay = elf, lay
        self.s = StepSim(elf, FREQ * step_ms // 1000, init)
        self.s.limit_s = 1e9
        self.win_base, self.mem_end = WIN, WIN + win_size
        self.pa, self.nbytes = WIN + pa_off, nbytes
        self.events, self.logs, self.writes, self.trace = [], [], [], []
        mu = self.s.mu
        mu.mem_map(WIN, win_size)
        if fill:
            mu.mem_write(self.pa, bytes([SENTINEL]) * nbytes)
        self.base = elf.sym["g_nat047"]
        self.hold = elf.sym["g_nat079_hold"]
        self.res = STACK + 0x1000
        mu.mem_write(self.res, b"\xEE" * 128)
        for f, v in (("up", 1), ("polling", 0)):
            self.put("nat047", f, v)
        for f, v in (("rx_present", 1), ("rx_direct", 1), ("rx_enabled", 1), ("rx_state", 0), ("rx_dest", self.hold), ("rx_size", HOLD)):
            self.put("usbmon", f, v)
        self.polls = 0
        self.poll_cb = None
        if fake_tick:
            self.stub("nat044_tick", lambda uc: self.events.append("tick"))
        self.stub("usbmon_poll", self._poll)
        self.stub("usbmon_log", self._log)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._store, None, 1, 0)

    # -- engine fields
    def off(self, st, f):
        return self.base + self.lay[st][0][f][0]

    def put(self, st, f, v):
        size = self.lay[st][0][f][1]
        self.s.mu.mem_write(self.off(st, f), (v & (2 ** (8 * size) - 1)).to_bytes(size, "little"))

    def get(self, st, f):
        size = self.lay[st][0][f][1]
        return int.from_bytes(bytes(self.s.mu.mem_read(self.off(st, f), size)), "little")

    def rx(self, f):
        return self.get("usbmon", f)

    # -- observers
    def stub(self, name, cb):
        a = self.elf.sym[name]
        self.s.mu.mem_write(a, RET)
        self.s.hook_symbol(name, cb)

    def _store(self, uc, access, addr, size, value, ud):
        self.writes.append((addr, size))
        self.trace.append(("w", addr, size))

    def watch_barriers(self, addresses):
        """Record every execution of the instructions at ADDRESSES (the dsb of the self-test) in the same ordered trace as the stores."""
        for a in addresses:
            self.s.mu.hook_add(unicorn.UC_HOOK_CODE, lambda uc, addr, size, ud: self.trace.append(("b", addr, 0)), None, a, a)

    def _poll(self, uc):
        self.polls += 1
        self.events.append("poll")
        if self.poll_cb:
            self.poll_cb(self, self.polls)

    def _log(self, uc):
        x = [uc.reg_read(A.UC_ARM64_REG_X0 + i) for i in range(4)]
        self.events.append("log")
        self.logs.append((x[0], x[1], bytes(uc.mem_read(x[2], x[3] & 0xFFFF)).decode(), self.s.t()))

    # -- the call
    def go(self, win_base=None, mem_end=None, pa=None, nbytes=None):
        s = self.s
        r = s.call("nat079_receive_root", self.win_base if win_base is None else win_base, self.mem_end if mem_end is None else mem_end,
                   self.pa if pa is None else pa, self.nbytes if nbytes is None else nbytes, self.res, max_insn=2_000_000_000)
        status = r & 0xFFFFFFFF
        status = status - (1 << 32) if status >= 1 << 31 else status
        raw = bytes(s.mu.mem_read(self.res, 128))
        names = ["pa", "bytes", "committed", "rx_bytes", "trbs", "errors", "resets", "dups", "gaps", "rejects", "aborts", "last_sum",
                 "elapsed_ticks", "freq", "selftest_bad_pa"]
        v = struct.unpack("<15Q2i", raw)
        self.r = dict(zip(names, v[:15]))
        self.r["status"] = v[15]
        if s.trigger_clk is None:                       # a run stopped by the NAT-044 reset has no return value
            assert self.r["status"] == status, (self.r["status"], status)
        return status

    def probe_pages(self):
        """The eight pages the self-test may touch: the first, the last and six spread evenly in between."""
        pages = self.nbytes // PAGE
        idx = [0, pages - 1] + [pages * (i - 1) // (PROBES - 1) for i in range(2, PROBES)]
        return [self.pa + n * PAGE for n in idx]

    def reserve_bytes(self):
        return bytes(self.s.mu.mem_read(self.pa, self.nbytes))

    def untouched_except(self, ranges):
        """True when every byte of the reserve outside `ranges` still has the sentinel."""
        data = bytearray(self.reserve_bytes())
        for a, n in ranges:
            data[a - self.pa:a - self.pa + n] = bytes([SENTINEL]) * n
        return set(data) == {SENTINEL}

    def writes_outside(self, allowed):
        bad = []
        for a, n in self.writes:
            if not any(lo <= a and a + n <= hi for lo, hi in allowed):
                bad.append((hex(a), n))
        return bad


def stream(chunk, start_after=0):
    """poll_cb that commits `chunk` bytes per poll once the destination is the reserve (the rx_dest the phase installed)."""
    def cb(run, n):
        if run.rx("rx_dest") != run.pa or n <= start_after:
            return
        done = min(run.rx("rx_committed") + chunk, run.rx("rx_size"))
        run.put("usbmon", "rx_committed", done)
        run.put("usbmon", "rx_bytes", done)
        run.put("usbmon", "rx_trbs", run.rx("rx_trbs") + 1)
        run.put("usbmon", "rx_last_sum", 0x1111 * n)
    return cb


@needs_all
class Receive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = built()
        cls.elf = ElfImage(out / NAME / "loader.elf")
        cls.lay = record_layouts(out / NAME / "source/shim/e1s-xnu")
        _img, fns = t74.disasm_functions(out / NAME / "loader.elf")
        cls.dsb = [i.address for i in fns["nat079_selftest"] if i.mnemonic == "dsb"]

    def run_(self, **kw):
        return Run(self.elf, self.lay, **kw)

    def allowed(self, run, extra=()):
        # the stack and the result, the probe words of the reserve, rx_dest/rx_size of the engine, and the `polling` guard that the inlined
        # nat047_poll() raises and lowers around every engine poll
        eng_fields = [(run.off("usbmon", "rx_dest"), run.off("usbmon", "rx_dest") + 16), (run.off("nat047", "polling"), run.off("nat047", "polling") + 4)]
        probes = [(p, p + WORDS * 8) for p in run.probe_pages()]
        return [(STACK, STACK + 0x10000), *eng_fields, *probes, *extra]

    # -- success
    def test_a_stream_that_completes_ends_with_done_and_the_engine_counters_in_the_result(self):
        r = self.run_()
        r.poll_cb = stream(512 * 1024)
        self.assertEqual(r.go(), 0)
        self.assertEqual(r.polls, 8)
        d = r.r
        self.assertEqual((d["pa"], d["bytes"]), (r.pa, r.nbytes))
        self.assertEqual((d["committed"], d["rx_bytes"], d["trbs"]), (r.nbytes, r.nbytes, 8))
        self.assertEqual(d["last_sum"], 0x1111 * 8)
        self.assertEqual(d["freq"], FREQ)
        self.assertEqual(d["selftest_bad_pa"], 0)
        self.assertGreater(d["elapsed_ticks"], 0)
        self.assertLess(d["elapsed_ticks"] / FREQ, 2.0)
        self.assertEqual((r.rx("rx_dest"), r.rx("rx_size")), (r.pa, r.nbytes))

    def test_the_destination_is_installed_only_after_the_self_test_and_before_the_first_poll(self):
        r = self.run_()
        seen = []
        r.poll_cb = lambda run, n: (seen.append((run.rx("rx_dest"), run.rx("rx_size"))), stream(1 << 20)(run, n))
        self.assertEqual(r.go(), 0)
        self.assertEqual(seen[0], (r.pa, r.nbytes))
        self.assertTrue(r.untouched_except([(p, WORDS * 8) for p in r.probe_pages()]))

    def test_every_loop_round_ticks_the_watchdog_before_it_polls_the_engine(self):
        r = self.run_()
        r.poll_cb = stream(256 * 1024)
        self.assertEqual(r.go(), 0)
        ev = [e for e in r.events if e in ("tick", "poll")]
        self.assertEqual(ev, ["tick", "poll"] * r.polls)

    def test_the_self_test_leaves_the_probe_pages_zero_and_the_rest_of_the_reserve_alone(self):
        r = self.run_()
        r.poll_cb = None                                 # no stream: stop at the cap (TIMEOUT), the reserve is as the phase left it
        r.s.limit_s = 1e9
        status = r.go()
        self.assertEqual(status, 6)
        data = r.reserve_bytes()
        for p in r.probe_pages():
            self.assertEqual(data[p - r.pa:p - r.pa + WORDS * 8], bytes(WORDS * 8), hex(p))
        self.assertTrue(r.untouched_except([(p, WORDS * 8) for p in r.probe_pages()]))

    def test_nothing_is_written_outside_the_probe_words_the_result_the_stack_and_the_two_engine_fields(self):
        r = self.run_()
        r.poll_cb = stream(1 << 20)
        self.assertEqual(r.go(), 0)
        self.assertEqual(r.writes_outside(self.allowed(r)), [])
        self.assertTrue(any(r.res <= a < r.res + 128 for a, _ in r.writes), "the result was written")
        # the fields written are exactly rx_dest and rx_size
        written = {a for a, _ in r.writes if r.off("usbmon", "rx_dest") <= a < r.off("usbmon", "rx_dest") + 16}
        self.assertEqual(written, {r.off("usbmon", "rx_dest"), r.off("usbmon", "rx_size")})

    def test_the_self_test_writes_each_probe_word_three_times_a_pattern_its_complement_and_a_zero(self):
        r = self.run_()
        r.poll_cb = None
        self.assertEqual(r.go(), 6)
        probes = r.probe_pages()
        stored = sum(size for a, size in r.writes if any(p <= a < p + WORDS * 8 for p in probes))
        self.assertEqual(stored, PROBES * WORDS * 8 * 3)

    def test_the_self_test_puts_a_barrier_after_every_write_pass_and_after_the_last_clear_before_the_destination_is_handed_over(self):
        r = self.run_()
        self.assertTrue(self.dsb, "the self-test has no dsb at all")
        r.watch_barriers(self.dsb)
        r.poll_cb = None
        self.assertEqual(r.go(), 6)
        probes = r.probe_pages()
        dest = r.off("usbmon", "rx_dest")
        k_dest = next(k for k, e in enumerate(r.trace) if e[0] == "w" and e[1] == dest)
        before = r.trace[:k_dest]
        self.assertEqual(sum(1 for e in before if e[0] == "b"), PROBES * 2 + 1)       # one per write pass of every page, one at the end
        last_probe = max(k for k, e in enumerate(before) if e[0] == "w" and any(p <= e[1] < p + WORDS * 8 for p in probes))
        self.assertTrue(any(e[0] == "b" for e in r.trace[last_probe + 1:k_dest]), "no barrier between the last clear and the hand-over")

    def test_every_engine_counter_lands_in_its_own_result_field(self):
        r = self.run_()
        vals = dict(rx_trbs=3, rx_errors=5, rx_resets=7, rx_dups=11, rx_gaps=13, rx_rejects=17, rx_aborts=19)

        def cb(run, n):
            if run.rx("rx_dest") != run.pa:
                return
            run.put("usbmon", "rx_committed", run.nbytes)
            run.put("usbmon", "rx_bytes", run.nbytes)
            for f, v in vals.items():
                run.put("usbmon", f, v)
            run.put("usbmon", "rx_last_sum", 0xABCDEF)
        r.poll_cb = cb
        self.assertEqual(r.go(), 0)
        d = r.r
        self.assertEqual((d["trbs"], d["errors"], d["resets"], d["dups"], d["gaps"], d["rejects"], d["aborts"], d["last_sum"]),
                         (3, 5, 7, 11, 13, 17, 19, 0xABCDEF))

    def full_result(self, r, status, **over):
        want = dict(pa=r.pa, bytes=r.nbytes, committed=0, rx_bytes=0, trbs=0, errors=0, resets=0, dups=0, gaps=0, rejects=0, aborts=0, last_sum=0,
                    elapsed_ticks=0, freq=FREQ, selftest_bad_pa=0, status=status)
        want.update(over)
        return want

    def test_a_start_that_was_refused_leaves_every_field_of_the_result_defined(self):
        # the result memory starts as 0xEE bytes: a field the phase forgot to set shows up as 0xEEEE...
        r = self.run_()
        r.put("nat047", "up", 0)
        self.assertEqual(r.go(), 1)
        self.assertEqual(r.r, self.full_result(r, 1))
        r = self.run_()
        r.put("usbmon", "rx_present", 0)
        self.assertEqual(r.go(), 2)
        self.assertEqual(r.r, self.full_result(r, 2))
        r = self.run_()
        self.assertEqual(r.go(pa=r.pa + 512), 3)
        self.assertEqual(r.r, self.full_result(r, 3, pa=r.pa + 512))
        r = self.run_()
        r.put("usbmon", "rx_committed", 512)
        r.put("usbmon", "rx_bytes", 512)
        self.assertEqual(r.go(), 4)
        self.assertEqual(r.r, self.full_result(r, 4, committed=512, rx_bytes=512))
        r = self.run_()
        addr = r.probe_pages()[3] + 8

        def stuck(uc, access, a, size, value, ud):
            uc.mem_write(addr, struct.pack("<Q", struct.unpack("<Q", bytes(uc.mem_read(addr, 8)))[0] | 1))
        r.s.mu.hook_add(unicorn.UC_HOOK_MEM_READ, stuck, None, addr, addr + 7)
        self.assertEqual(r.go(), 5)
        self.assertEqual(r.r, self.full_result(r, 5, selftest_bad_pa=addr))

    # -- the cap
    def test_without_traffic_the_phase_ends_at_the_cap_with_timeout_and_reports_every_ten_seconds(self):
        r = self.run_()
        self.assertEqual(r.go(), 6)
        d = r.r
        secs = d["elapsed_ticks"] / FREQ
        self.assertGreaterEqual(secs, RX_CAP_S)
        self.assertLess(secs, RX_CAP_S + 0.5)
        self.assertEqual(r.polls, len([e for e in r.events if e == "tick"]))
        self.assertEqual((d["committed"], d["rx_bytes"], d["trbs"]), (0, 0, 0))
        times = []
        for m, kind, text, t in r.logs:
            self.assertEqual(m, r.base)
            self.assertEqual(kind, 1)
            g = re.fullmatch(r"NAT079 rx MiB=0 trbs=0 err=0 t=(\d+)s", text)
            self.assertIsNotNone(g, text)
            times.append(int(g.group(1)))
        # the model counter advances by exactly 100 ms per round, so the lines come at exactly 10 s, 20 s, ... 230 s of the receive loop
        # (the round at 240 s is the cap: decide() ends the phase before a line is due)
        self.assertEqual(times, list(range(REPORT_S, RX_CAP_S, REPORT_S)))

    def test_progress_lines_carry_the_committed_mebibytes_and_the_counters(self):
        r = self.run_(nbytes=64 * MIB, pa_off=2 * MIB, win_size=80 * MIB)

        def cb(run, n):
            if run.rx("rx_dest") == run.pa:
                run.put("usbmon", "rx_committed", min(run.nbytes, n * 128 * 1024))
                run.put("usbmon", "rx_bytes", min(run.nbytes, n * 128 * 1024))
                run.put("usbmon", "rx_trbs", n)
                run.put("usbmon", "rx_errors", n // 100)
        r.poll_cb = cb
        self.assertEqual(r.go(), 0)
        self.assertGreater(len(r.logs), 0)
        mibs = []
        for _m, _k, text, t in r.logs:
            g = re.fullmatch(r"NAT079 rx MiB=(\d+) trbs=(\d+) err=(\d+) t=(\d+)s", text)
            self.assertIsNotNone(g, text)
            mib, trbs, err, secs = map(int, g.groups())
            self.assertEqual(err, trbs // 100)
            self.assertEqual(mib, min(64, trbs * 128 // 1024))
            self.assertLessEqual(abs(secs - t), 2)
            mibs.append(mib)
        self.assertEqual(mibs, sorted(mibs))

    # -- the engine states
    def test_a_faulty_word_of_any_probe_page_fails_the_self_test_whichever_pass_exposes_it(self):
        """A toggling bit fails in the first pass, a stuck-at-zero or stuck-at-one bit in the pass whose pattern has that bit the other way:
        the self-test writes a salted pattern and its complement, so every stuck bit is caught. The phase then ends at once, names the word,
        and leaves the engine's destination at the placeholder (RX_BEGIN stays refused: GET_RX still reports 512 bytes)."""
        pages = self.run_().probe_pages()
        for i in range(PROBES):
            for k in (0, 7, 15):
                for kind in ("toggle", "stuck0", "stuck1"):
                    r = self.run_()
                    r.poll_cb = stream(1 << 20)
                    addr = pages[i] + 8 * k

                    def rd(uc, access, a, size, value, ud, kind=kind, addr=addr):
                        cur = struct.unpack("<Q", bytes(uc.mem_read(addr, 8)))[0]
                        new = {"toggle": cur ^ 1, "stuck0": cur & ~1, "stuck1": cur | 1}[kind]
                        if new != cur:
                            uc.mem_write(addr, struct.pack("<Q", new))
                    r.s.mu.hook_add(unicorn.UC_HOOK_MEM_READ, rd, None, addr, addr + 7)
                    self.assertEqual(r.go(), 5, (i, k, kind))
                    self.assertEqual(r.r["selftest_bad_pa"], addr, (i, k, kind))
                    self.assertEqual(r.polls, 0)
                    self.assertEqual(r.events, [], "no tick, poll or log: the phase did not start")
                    self.assertEqual((r.rx("rx_dest"), r.rx("rx_size")), (r.hold, HOLD))
                    self.assertEqual(r.writes_outside(self.allowed(r)), [])
                    self.assertEqual(r.r["committed"], 0)

    def test_a_host_that_sent_before_the_destination_was_real_is_refused_without_touching_the_reserve(self):
        for f, v in (("rx_state", 1), ("rx_trbs", 1), ("rx_committed", 512), ("rx_bytes", 512)):
            r = self.run_()
            r.put("usbmon", f, v)
            r.poll_cb = stream(1 << 20)
            self.assertEqual(r.go(), 4, f)
            self.assertEqual(r.polls, 0)
            self.assertEqual((r.rx("rx_dest"), r.rx("rx_size")), (r.hold, HOLD))
            self.assertTrue(r.untouched_except([]), "the self-test must not run after a premature host")
            self.assertEqual(r.writes_outside([(STACK, STACK + 0x10000)]), [])
            if f in ("rx_committed", "rx_bytes"):
                self.assertEqual(r.r[{"rx_committed": "committed", "rx_bytes": "rx_bytes"}[f]], 512)

    def test_an_engine_that_never_came_up_is_reported_and_nothing_is_written(self):
        r = self.run_()
        r.put("nat047", "up", 0)
        self.assertEqual(r.go(), 1)
        self.assertEqual((r.r["pa"], r.r["bytes"]), (r.pa, r.nbytes))
        self.assertEqual((r.polls, len(r.events)), (0, 0))
        self.assertTrue(r.untouched_except([]))
        self.assertEqual(r.writes_outside([(STACK, STACK + 0x10000)]), [])

    def test_an_engine_without_the_bulk_out_endpoint_is_reported(self):
        r = self.run_()
        r.put("usbmon", "rx_present", 0)
        self.assertEqual(r.go(), 2)
        self.assertTrue(r.untouched_except([]))
        self.assertEqual(r.polls, 0)

    def test_bad_arguments_are_refused_before_anything_is_written(self):
        r0 = self.run_()
        eng = r0.base
        cases = {
            "unaligned start": dict(pa=r0.pa + 512),
            "unaligned length": dict(nbytes=r0.nbytes - 512),
            "seven pages": dict(nbytes=7 * PAGE),
            "below the window": dict(pa=r0.win_base - PAGE),
            "past the window": dict(pa=r0.mem_end - 4 * PAGE),
            "zero length": dict(nbytes=0),
        }
        for what, kw in cases.items():
            r = self.run_()
            r.poll_cb = stream(1 << 20)
            self.assertEqual(r.go(**kw), 3, what)
            self.assertEqual(r.polls, 0, what)
            self.assertEqual((r.rx("rx_dest"), r.rx("rx_size")), (r.hold, HOLD), what)
            self.assertTrue(r.untouched_except([]), what)
            self.assertEqual(r.writes_outside([(STACK, STACK + 0x10000)]), [], what)
        # the engine's own memory inside the range
        r = self.run_()
        before = bytes(r.s.mu.mem_read(eng, 4096))
        lo = eng & ~(PAGE - 1)
        self.assertEqual(r.go(win_base=0, mem_end=2 ** 40, pa=lo, nbytes=8 * PAGE), 3)
        self.assertEqual(bytes(r.s.mu.mem_read(eng, 4096)), before)
        self.assertEqual(r.writes_outside([(STACK, STACK + 0x10000)]), [])

    def test_an_engine_that_falls_over_mid_stream_ends_the_phase_with_engine_down(self):
        r = self.run_()

        def cb(run, n):
            stream(256 * 1024)(run, n)
            if n == 3:
                run.put("nat047", "up", 0)                 # nat047_fault() does this
        r.poll_cb = cb
        self.assertEqual(r.go(), 7)
        self.assertEqual(r.polls, 3)
        self.assertEqual(r.r["committed"], 3 * 256 * 1024)
        self.assertLess(r.r["elapsed_ticks"] / FREQ, 3)          # at once, not at the cap

    def test_done_wins_over_a_fault_in_the_same_round(self):
        r = self.run_()

        def cb(run, n):
            stream(run.nbytes)(run, n)
            run.put("nat047", "up", 0)
        r.poll_cb = cb
        self.assertEqual(r.go(), 0)

    def test_counters_that_disagree_at_the_end_are_reported_not_trusted(self):
        for broken in ("rx_bytes", "rx_committed_over"):
            r = self.run_()

            def cb(run, n, broken=broken):
                if run.rx("rx_dest") != run.pa:
                    return
                if broken == "rx_bytes":
                    run.put("usbmon", "rx_committed", run.nbytes)
                    run.put("usbmon", "rx_bytes", run.nbytes - 512)
                else:
                    run.put("usbmon", "rx_committed", run.nbytes + 512)
                    run.put("usbmon", "rx_bytes", run.nbytes + 512)
            r.poll_cb = cb
            self.assertEqual(r.go(), 8, broken)

    def test_a_poll_that_is_already_running_does_not_count_as_progress(self):
        # nat047_poll() is inlined: with `polling` set it returns without calling the engine, and the phase waits for the cap
        r = self.run_()
        r.put("nat047", "polling", 1)
        r.poll_cb = stream(1 << 20)
        self.assertEqual(r.go(), 6)
        self.assertEqual(r.polls, 0)

    def test_a_stream_that_stalls_part_way_times_out_with_the_partial_counters(self):
        r = self.run_()
        r.poll_cb = lambda run, n: stream(512 * 1024)(run, n) if n <= 5 else None
        self.assertEqual(r.go(), 6)
        self.assertEqual(r.r["committed"], 5 * 512 * 1024)
        self.assertEqual(r.r["trbs"], 5)

    def test_the_real_size_reserve_in_a_4_gib_window_is_accepted_and_only_the_probe_words_are_written(self):
        win, off = 4096 * MIB, 77 * MIB
        self.assertLessEqual(off + REAL_RESERVE, win)
        try:
            r = self.run_(win_size=win, pa_off=off, nbytes=REAL_RESERVE, fill=False)
        except unicorn.UcError as e:
            self.skipTest("cannot map a 4 GiB window on this host: %s" % e)
        self.assertEqual(r.go(), 6)                                  # no traffic: the cap
        self.assertEqual(r.r["selftest_bad_pa"], 0)
        self.assertEqual((r.rx("rx_dest"), r.rx("rx_size")), (r.pa, REAL_RESERVE))
        self.assertEqual(r.writes_outside(self.allowed(r)), [])
        pages = r.probe_pages()
        self.assertEqual(pages[1], r.pa + REAL_RESERVE - PAGE)
        self.assertEqual(len(set(pages)), PROBES)


# ------------------------------------------------------------------------------------------------------------------------------- Pet
@needs_all
class Pet(unittest.TestCase):
    """The real nat044_tick (not stubbed) inside the receive loop, armed by the real recovery_guard."""
    @classmethod
    def setUpClass(cls):
        out = built()
        cls.elf = ElfImage(out / NAME / "loader.elf")
        cls.lay = record_layouts(out / NAME / "source/shim/e1s-xnu")

    def armed(self, skew_s=0):
        r = Run(self.elf, self.lay, fake_tick=False, init={t44.INFORM3: t44.NORMAL, t44.INFORM2: 0x0AA50011, t44.CMD: 0xD})
        r.s.mu.mem_write(self.elf.sym["diagnostic_value"], RET)
        self.assertEqual(r.s.call("recovery_guard") & 0xFFFFFFFF, 0)
        r.t0 = r.s.g("t0")
        r.refresh0 = len(r.s.wdt_events)
        r.s.clk += FREQ * skew_s              # time that passed between the guard and the receive phase (window clear, ELF copy, ...)
        return r

    def pets(self, r):
        wtdat = next(v for k, o, v, _ in r.s.wdt_events if k == "W" and o == 4)
        out, ev = [], r.s.wdt_events[r.refresh0:]
        for n, (k, o, v, c) in enumerate(ev):
            if k == "W" and o == 0xC and v == 0 and [e[:3] for e in ev[n + 1:n + 3]] == [("R", 4, wtdat), ("W", 8, wtdat)]:
                out.append((c - r.t0) / FREQ)
        return out

    def test_the_watchdog_is_petted_every_thirty_seconds_through_the_whole_receive_phase(self):
        r = self.armed(skew_s=14)
        self.assertEqual(r.go(), 6)
        pets = self.pets(r)
        end = (r.s.clk - r.t0) / FREQ
        self.assertGreaterEqual(end, RX_CAP_S + 14)
        self.assertLess(end, DEADLINE_S, "the receive phase plus the loader work before it must end inside the NAT-044 deadline")
        marks = [0.0] + pets + [end]
        self.assertGreaterEqual(len(pets), 7)
        self.assertLess(max(b - a for a, b in zip(marks, marks[1:])), 83 - 20, "the longest gap between pets must stay inside the watchdog")
        for a, b in zip(pets, pets[1:]):
            self.assertGreaterEqual(b - a, PET_S - 1e-6)
            self.assertLess(b - a, PET_S + 0.5)
        self.assertIsNone(r.s.trigger_clk, "the deadline must not fire during the receive phase")
        self.assertEqual(r.s.g("fired"), 0)

    def test_a_phase_that_overruns_the_deadline_is_stopped_by_the_nat044_reset_sequence_with_the_pets_unchanged(self):
        r = self.armed(skew_s=200)                      # 200 s lost before the phase: the cap would end it at about 440 s, the deadline is 360 s
        r.go()
        self.assertIsNotNone(r.s.trigger_clk)
        dt = (r.s.trigger_clk - r.t0) / FREQ
        self.assertGreaterEqual(dt, DEADLINE_S)
        self.assertLess(dt, DEADLINE_S + 0.5)
        pets = self.pets(r)
        self.assertTrue(pets)
        self.assertLess(max(pets), dt)
        writes = [(o, v) for k, o, v, _ in r.s.pmu_events if k == "W"]
        self.assertEqual(writes[-4:], [(t44.INFORM2, 0x0A4E0011), (t44.INFORM3, t44.DOWNLOAD), (t44.CMD, 0x8), (t44.REBOOT, 2)])


if __name__ == "__main__":
    unittest.main()
