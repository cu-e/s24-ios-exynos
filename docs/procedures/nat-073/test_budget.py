#!/usr/bin/env python3
"""Host tests for the arithmetic in budget.py (gap finding, node merging, the loader's window rule)."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("budget", Path(__file__).with_name("budget.py"))
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)

MIB = budget.MIB


class Gaps(unittest.TestCase):
    def test_reserved_range_splits_a_node(self):
        got = budget.free_gaps([(0, 1000 * MIB)], [(300 * MIB, 100 * MIB)])
        self.assertEqual(got, [(0, 300 * MIB), (400 * MIB, 600 * MIB)])

    def test_min_size_filters(self):
        got = budget.free_gaps([(0, 1000 * MIB)], [(300 * MIB, 100 * MIB)], 500 * MIB)
        self.assertEqual(got, [(400 * MIB, 600 * MIB)])

    def test_reserved_outside_and_overlapping_the_edge(self):
        got = budget.free_gaps([(100 * MIB, 100 * MIB)], [(0, 120 * MIB), (190 * MIB, 50 * MIB)])
        self.assertEqual(got, [(120 * MIB, 70 * MIB)])

    def test_fully_reserved_node_has_no_gap(self):
        self.assertEqual(budget.free_gaps([(0, 10 * MIB)], [(0, 10 * MIB)]), [])


class Merge(unittest.TestCase):
    def test_touching_nodes_merge_and_gaps_survive(self):
        got = budget.merge_ranges([(2 * budget.GIB, budget.GIB), (0, budget.GIB), (budget.GIB, budget.GIB), (4 * budget.GIB, budget.GIB)])
        self.assertEqual(got, [(0, 3 * budget.GIB), (4 * budget.GIB, budget.GIB)])

    def test_contained_range_does_not_shrink(self):
        self.assertEqual(budget.merge_ranges([(0, 100), (10, 20)]), [(0, 100)])


class LoaderRule(unittest.TestCase):
    def test_gap_is_capped_and_taken_from_the_top(self):
        base, size = budget.loader_choice([(0x880000000, 2048 * MIB)], [])
        self.assertEqual(size, 512 * MIB)
        self.assertEqual(base + size, 0x880000000 + 2048 * MIB)

    def test_first_node_wins_a_tie(self):
        nodes = [(0x980000000, 2048 * MIB), (0x900000000, 2048 * MIB)]
        base, _ = budget.loader_choice(nodes, [])
        self.assertEqual(base, 0x980000000 + 2048 * MIB - 512 * MIB)

    def test_gap_below_the_minimum_is_ignored(self):
        self.assertEqual(budget.loader_choice([(0x80000000, 255 * MIB)], []), (0, 0))

    def test_reservation_moves_the_window_down(self):
        base, size = budget.loader_choice([(0, 1024 * MIB)], [(900 * MIB, 124 * MIB)])
        self.assertEqual((base, size), (388 * MIB, 512 * MIB))

    def test_touching_nodes_alone_do_not_give_more_than_the_cap_but_merging_gives_more_gap(self):
        nodes = [(0, 2048 * MIB), (2048 * MIB, 2048 * MIB)]
        self.assertEqual(budget.loader_choice(nodes, [])[1], 512 * MIB)
        gaps = budget.free_gaps(budget.merge_ranges(nodes), [])
        self.assertEqual(gaps, [(0, 4096 * MIB)])


class LogParsing(unittest.TestCase):
    def test_kv_reads_hex(self):
        self.assertEqual(budget.kv("ticks=0x20c6cda7 zero_begin=0x9de400000 ", "zero_begin"), 0x9de400000)
        self.assertIsNone(budget.kv("nothing here", "ticks"))

    def test_loader_measurements_and_timing(self):
        rows = [
            {"text": "window from DTB=0x9de400000 win=0x9de400000 win size=0x20000000 "},
            {"text": "ticks=0x1000000 zero_begin=0x9de400000 "},
            {"text": "ticks=0x1000000 zero_bytes=0x10000000 "},
            {"text": "ticks=0x2000000 zero_bytes=0x20000000 "},
            {"text": "seg 0x0 -> 0x9e1404000 0x198000"},
            {"text": "ticks=0x2800000 clean_full_window_begin=0x9de400000 "},
            {"text": "ticks=0x2900000 clean_full_window_end=0x9fe400000 "},
            {"text": "ticks=0x3000000 return_entry_to_assembly=0x9e183b4a8 "},
        ]
        m = budget.loader_measurements(rows)
        self.assertEqual((m["window_base"], m["window_size"]), (0x9de400000, 0x20000000))
        self.assertEqual(m["segments"], 1)
        self.assertEqual(m["segment_bytes"], 0x198000)
        t = budget.derive_timing(m)
        self.assertAlmostEqual(t["zero_seconds"], 0x1000000 / budget.TICK_HZ)
        self.assertAlmostEqual(t["clean_seconds"], 0x100000 / budget.TICK_HZ)


if __name__ == "__main__":
    unittest.main()
