#!/usr/bin/env python3
"""Host tests for the NAT-074 big-window loader variant (window rule). Needs the local NAT-065 build tree (gitignored) and clang;
a missing input is a failure, not a skip."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
SRC = ROOT / "artifacts/nat-065/build-001/loader-diag-xnu-md0-usb/source/shim/e1s-xnu"
RUNTIME_DTB = ROOT / "devices/e1s-fdt/2026-11-10/runtime.dtb"
MIB = 1 << 20


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


make_variant = load("make_variant")
check = load("check_big_window")
fdtgen = load("fdtgen")


def expected(nodes, reserved, min_w=256 * MIB, max_w=4096 * MIB):
    """Independent model of the intended rule: merge touching nodes, subtract reservations, take the largest gap (first on a tie),
    cap it, 2 MiB-align, place at the top of the gap."""
    merged = []
    for b, z in sorted(nodes):
        if merged and b <= merged[-1][0] + merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b + z - merged[-1][0])
        else:
            merged.append([b, z])
    best = (0, 0)
    for b, z in merged:
        cur, end = b, b + z
        gaps = []
        for rb, rz in sorted(reserved):
            if rb >= end or rb + rz <= cur:
                continue
            if rb > cur:
                gaps.append((cur, rb))
            cur = max(cur, rb + rz)
        if cur < end:
            gaps.append((cur, end))
        for s, e in gaps:
            base = (s + 0x1FFFFF) & ~0x1FFFFF
            if e <= base:
                continue
            size = min(e - base, max_w) & ~0x1FFFFF
            if size >= min_w and size > best[1]:
                best = (e - size, size)
    return best


class Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert SRC.is_dir(), f"missing local input {SRC}"
        cls.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        t = Path(cls.tmp.name)
        import shutil
        shutil.copytree(SRC, t / "variant")
        (t / "variant/loader.c").write_text(make_variant.apply((SRC / "loader.c").read_text()))
        cls.orig = check.build(SRC, t / "orig-build")
        cls.var = check.build(t / "variant", t / "var-build")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # The loader refuses a tree with no reservation at all ("an empty list cannot establish E1S firmware carve-out ownership"),
    # so every synthetic tree carries one far-away 1 MiB block, which is also part of what `expected` subtracts.
    FAR = ("far", 0x8FF00000, 1 << 20)

    def window(self, exe, nodes, reserved=()):
        p = Path(self.tmp.name) / "case.dtb"
        p.write_bytes(fdtgen.fdt(nodes, [self.FAR, *reserved]))
        w = check.run(exe, p)["window"]
        return (int(w["base"], 16), int(w["size"], 16)) if w["found"] else (0, 0)

    def test_real_dtb_original_reproduces_nat068_window(self):
        w = check.run(self.orig, RUNTIME_DTB)["window"]
        self.assertEqual((int(w["base"], 16), int(w["size"], 16)), (0x9DE400000, 512 * MIB))

    def test_real_dtb_variant_takes_4096_mib_at_the_top_of_the_gap(self):
        r = check.run(self.var, RUNTIME_DTB)
        w = (int(r["window"]["base"], 16), int(r["window"]["size"], 16))
        self.assertEqual(w, (0x9FE400000 - 4096 * MIB, 4096 * MIB))
        mem = [(int(a, 16), int(s, 16)) for a, s in r["memory"]]
        rsv = [(int(a, 16), int(s, 16)) for a, s in r["reserved"]]
        self.assertEqual(w, expected(mem, rsv))
        # no reservation overlaps the window, and it lies inside the union of the touching nodes
        self.assertFalse([x for x in rsv if x[1] and x[0] < w[0] + w[1] and w[0] < x[0] + x[1]])
        self.assertTrue(any(b <= w[0] and w[0] + w[1] <= b + z for b, z in [(0x880000000, 6144 * MIB)]))

    def test_touching_nodes_merge(self):
        nodes = [(0x880000000, 2048 * MIB), (0x900000000, 2048 * MIB)]
        self.assertEqual(self.window(self.var, nodes), (0x880000000, 4096 * MIB))
        self.assertEqual(self.window(self.orig, nodes), (0x880000000 + 1536 * MIB, 512 * MIB))

    def test_node_order_does_not_matter(self):
        nodes = [(0x900000000, 2048 * MIB), (0x880000000, 2048 * MIB)]
        self.assertEqual(self.window(self.var, nodes), (0x880000000, 4096 * MIB))

    def test_overlapping_nodes_merge_without_growing_past_the_union(self):
        nodes = [(0x880000000, 3000 * MIB), (0x880000000 + 2000 * MIB, 3000 * MIB)]
        self.assertEqual(self.window(self.var, nodes), expected(nodes, [self.FAR[1:]]))

    def test_a_hole_between_nodes_is_not_merged(self):
        nodes = [(0x880000000, 2048 * MIB), (0x980000000, 2048 * MIB)]
        self.assertEqual(self.window(self.var, nodes), (0x880000000, 2048 * MIB))

    def test_gap_under_256_mib_is_rejected_and_exactly_256_is_accepted(self):
        self.assertEqual(self.window(self.var, [(0x880000000, 255 * MIB)]), (0, 0))
        self.assertEqual(self.window(self.var, [(0x880000000, 256 * MIB)]), (0x880000000, 256 * MIB))

    def test_reservation_splits_a_merged_range(self):
        nodes = [(0x880000000, 2048 * MIB), (0x900000000, 2048 * MIB)]
        rsv = [("hole", 0x880000000 + 1024 * MIB, 64 * MIB)]
        want = expected(nodes, [(b, z) for _, b, z in [self.FAR, *rsv]])
        self.assertEqual(want[1], 3008 * MIB)
        self.assertEqual(self.window(self.var, nodes, rsv), want)

    def test_a_tree_without_any_reservation_is_refused_by_both(self):
        p = Path(self.tmp.name) / "norsv.dtb"
        p.write_bytes(fdtgen.fdt([(0x880000000, 2048 * MIB)]))
        for exe in (self.orig, self.var):
            self.assertEqual(check.run(exe, p)["window"]["found"], 0)

    def test_the_cap_is_4096_mib_and_not_more(self):
        self.assertEqual(self.window(self.var, [(0x880000000, 6144 * MIB)])[1], 4096 * MIB)

    def test_variant_equals_original_when_nothing_touches_and_gaps_are_small(self):
        nodes = [(0x80000000, 400 * MIB), (0xC0000000, 300 * MIB)]
        self.assertEqual(self.window(self.var, nodes), self.window(self.orig, nodes))

    def test_derivation_refuses_a_drifted_source(self):
        with self.assertRaises(SystemExit):
            make_variant.apply("int nothing;\n")
        text = (SRC / "loader.c").read_text()
        with self.assertRaises(SystemExit):
            make_variant.apply(text + "\n#define MAX_WINDOW\t(512UL << 20)\n")


class FdtHelper(unittest.TestCase):
    def test_header_and_sizes(self):
        b = fdtgen.fdt([(0x880000000, 1 << 30)], [("r", 0x880000000, 1 << 20)], [(0x1000, 0x1000)])
        import struct
        magic, total = struct.unpack(">II", b[:8])
        self.assertEqual((magic, total), (0xD00DFEED, len(b)))


if __name__ == "__main__":
    unittest.main()
