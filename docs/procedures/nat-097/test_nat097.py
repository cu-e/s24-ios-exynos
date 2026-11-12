#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-097 tests. Inputs are hand-built: the dump layouts below are written out as numbers (the offsets of the first and last record of each segment are literals worked out by hand,
not taken from the module under test), plus, when the local artifact exists, the real NAT-093 archive, whose facts were read by hand in docs/procedures/nat-093/posthoc.json before this
reader existed (length 170,097, 345 of 428 records, two missing ranges of 4,800 and 3,168 bytes)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "nat-089"))
sys.path.insert(0, str(HERE.parent / "nat-093"))
import analyze_nat097 as A  # noqa: E402
import kl_reader2 as R  # noqa: E402
import test_nat089 as T89  # noqa: E402  (its fixtures: esc, write_boot, jobs, text builders)
import kl_reader as K1  # noqa: E402
import analyze_nat089 as A89  # noqa: E402

REAL = HERE.parents[2] / "artifacts" / "nat-092" / "run-001" / "archive"
POSTHOC = HERE.parent / "nat-093" / "posthoc.json"
RAW = 96


def data(n):
    """n bytes of text that exercise the escape (a backslash and a newline every so often) and no two records alike."""
    return bytes([0x5c if i % 251 == 7 else 0x0a if i % 97 == 50 else 0x20 + (i * 7 + i // 96) % 90 for i in range(n)])


def segment(buf, lo, hi):
    return [(o, buf[o:min(o + RAW, hi)]) for o in range(lo, hi, RAW)]


def lines(length, why=2, head_max=8192, tail_max=32768, drop=(), begin=True, end=True, bytes_override=None, recs_override=None, extra=(), reorder=False, buf=None):
    """The KL lines a complete dump of `length` bytes sends (tail ascending, then head ascending), minus the records at `drop`, with or without the begin line.
    The layout is spelled out here independently of the module under test."""
    buf = buf if buf is not None else data(length)
    head = min(length, head_max)
    tail = min(length - head, tail_max)
    gap = length - head - tail
    recs = segment(buf, length - tail, length) + segment(buf, 0, head)
    out = []
    if begin:
        out.append("KL begin why=%d len=%d head=%d tail=%d gap=%d x0=0x0" % (why, length, head, tail, gap))
    sent = [(o, r) for o, r in recs if o not in drop]
    if reorder:
        sent[0], sent[1] = sent[1], sent[0]
    for o, r in list(sent) + list(extra):
        out.append("KL %06x %s" % (o, T89.esc(r)))
    if end:
        out.append("KL end why=%d recs=%d bytes=%d" % (why, len(recs) if recs_override is None else recs_override, head + tail if bytes_override is None else bytes_override))
    return out


def archive(boots):
    """boots: [lines, ...] -> a temporary archive directory (the caller keeps the TemporaryDirectory alive)."""
    td = tempfile.TemporaryDirectory()
    for i, ls in enumerate(boots, 1):
        T89.write_boot(td.name, "%06d-x" % i, ls)
    return td


def text_of_bytes(m):
    return b"".join(m["bytes"][o] for o in sorted(m["bytes"]))


class Geometry(unittest.TestCase):
    """The dump of 50,000 bytes: head 0..8192 (86 records, the last 32 bytes), tail 17,232..50,000 (342 records, the last at offset 49,968 with 32 bytes), gap 9,040; 428 records, 40,960 bytes."""

    def test_capped_dump_without_begin_is_inferred_from_the_last_tail_record(self):
        td = archive([lines(50000, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual(a["unreadable"], [])
        self.assertEqual(len(a["dumps"]), 1)
        d = a["dumps"][0]
        self.assertEqual(d["begin"], dict(why=2, len=50000, head=8192, tail=32768, gap=9040, x0=None))
        self.assertTrue(d["begin_inferred"])
        self.assertEqual((len(d["bytes"]), d["hole_bytes"], d["holes"], d["closed"]), (428, 0, [], True))
        self.assertEqual(min(o for o in d["bytes"] if o >= 8192), 17232)
        self.assertEqual(len(d["bytes"][49968]), 32)

    def test_lost_records_become_exact_holes_and_the_text_carries_markers(self):
        drop = {0, 17232, 17328, 39888}     # the first head record, the first two tail records, one in the middle of the tail (17,232 + 236 * 96 = 39,888)
        td = archive([lines(50000, begin=False, drop=drop)])
        d = R.read_archive2(td.name)["dumps"][0]
        self.assertEqual(d["holes"], [(0, 96), (17232, 17424), (39888, 39984)])
        self.assertEqual(d["hole_bytes"], 96 + 192 + 96)
        self.assertEqual(len(d["bytes"]), 424)
        self.assertEqual(d["text"].count("bytes lost in transport"), 3)
        self.assertIn("9040 bytes of the log were not sent", d["text"])

    def test_with_the_real_begin_the_result_equals_the_nat089_reader(self):
        td = archive([lines(50000, drop={96, 17328})])
        v1 = K1.read_archive(td.name)["dumps"]
        v2 = R.read_archive2(td.name)["dumps"]
        self.assertEqual(len(v1), 1)
        self.assertEqual(len(v2), 1)
        self.assertFalse(v2[0]["begin_inferred"])
        self.assertEqual({k: v for k, v in v2[0].items() if k != "begin_inferred"}, v1[0])

    def test_the_inferred_dump_equals_the_dump_with_begin_except_for_the_marker_and_x0(self):
        drop = {96, 17328}
        td1, td2 = archive([lines(50000, drop=drop)]), archive([lines(50000, drop=drop, begin=False)])
        a, b = R.read_archive2(td1.name)["dumps"][0], R.read_archive2(td2.name)["dumps"][0]
        self.assertEqual(a["text"], b["text"])
        self.assertEqual(a["bytes"], b["bytes"])
        self.assertEqual(a["holes"], b["holes"])
        self.assertEqual({k: v for k, v in a["begin"].items() if k != "x0"}, {k: v for k, v in b["begin"].items() if k != "x0"})
        self.assertEqual((a["begin_inferred"], b["begin_inferred"]), (False, True))

    def test_dump_below_the_cap_takes_its_length_from_the_end_line_even_if_the_last_record_is_lost(self):
        # length 20,000: head 8,192, tail 11,808 from 8,192 (123 records exactly, the last at 19,904 with 96 bytes), 86 + 123 = 209 records, 20,000 bytes
        td = archive([lines(20000, begin=False, drop={19904})])
        a = R.read_archive2(td.name)
        self.assertEqual(a["unreadable"], [])
        d = a["dumps"][0]
        self.assertEqual(d["begin"], dict(why=2, len=20000, head=8192, tail=11808, gap=0, x0=None))
        self.assertEqual((len(d["bytes"]), d["holes"]), (208, [(19904, 20000)]))

    def test_head_only_dump(self):
        # length 5,000: head 5,000 (53 records, the last 8 bytes), no tail
        td = archive([lines(5000, begin=False, drop={96})])
        d = R.read_archive2(td.name)["dumps"][0]
        self.assertEqual(d["begin"], dict(why=2, len=5000, head=5000, tail=0, gap=0, x0=None))
        self.assertEqual((len(d["bytes"]), d["holes"]), (52, [(96, 192)]))
        self.assertEqual(len(d["bytes"][4992]), 8)

    def test_why_1_geometry(self):
        # why 1: head 8,192, tail 8,192; length 30,000: tail from 21,808, 86 + 86 = 172 records, the last at 29,968 with 32 bytes
        td = archive([lines(30000, why=1, tail_max=8192, begin=False, drop={21904})])
        a = R.read_archive2(td.name)
        self.assertEqual(a["unreadable"], [])
        d = a["dumps"][0]
        self.assertEqual((d["why"], d["begin"]["len"], d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"]), (1, 30000, 8192, 8192, 13616))
        self.assertEqual(min(o for o in d["bytes"] if o >= 8192), 21808)

    def test_the_whole_text_is_reproduced_when_nothing_is_lost(self):
        buf = data(50000)
        td = archive([lines(50000, begin=False, buf=buf)])
        d = R.read_archive2(td.name)["dumps"][0]
        want = buf[:8192].decode("utf-8", "replace") + "\n[... 9040 bytes of the log were not sent ...]\n" + buf[17232:].decode("utf-8", "replace")
        self.assertEqual(d["text"], want)


class Refusals(unittest.TestCase):
    def refused(self, ls, fragment, boots=1):
        td = archive([ls] * boots if boots == 1 else ls)
        a = R.read_archive2(td.name)
        self.assertEqual(a["dumps"], [], a["dumps"])
        self.assertEqual(len(a["unreadable"]), 1)
        self.assertIn(fragment, a["unreadable"][0]["reason"])
        return a

    def test_capped_dump_whose_final_tail_record_was_lost_is_not_guessed(self):
        self.refused(lines(50000, begin=False, drop={49968}), "the end of the tail was lost")

    def test_capped_dump_without_any_tail_record(self):
        keep = [l for l in lines(50000, begin=False) if not l.startswith("KL ") or l.startswith("KL end") or int(l.split()[1], 16) < 8192]
        self.refused(keep, "no tail record arrived")

    def test_end_line_with_other_counts_than_the_geometry(self):
        a = self.refused(lines(50000, begin=False, recs_override=427), "the end line says 427 records")
        self.assertEqual(a["unreadable"][0]["reason"], "the end line says 427 records / 40960 bytes; the inferred geometry (len 50000, head 8192, tail 32768) needs 428 / 40960")
        self.refused(lines(20000, begin=False, recs_override=208), "the end line says 208 records")
        self.refused(lines(20000, begin=False, bytes_override=19999), "is not on the inferred grid")     # length 19,999 puts the last record at 19,904 with 95 bytes

    def test_a_capped_dump_of_exactly_head_plus_tail_is_inferred(self):
        # length 40,960: tail from exactly 8,192 (the head's size), the last tail record at 40,928 with 32 bytes
        td = archive([lines(40960, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual(a["unreadable"], [])
        d = a["dumps"][0]
        self.assertEqual(d["begin"], dict(why=2, len=40960, head=8192, tail=32768, gap=0, x0=None))
        self.assertEqual((len(d["bytes"]), d["holes"]), (428, []))

    def test_a_tail_record_at_exactly_the_head_size_counts_as_a_tail_record(self):
        # length 40,960, every tail record but the first (offset 8,192, 96 bytes) lost: it is the last received tail record and it is not the final one
        ls = lines(40960, begin=False, drop={o for o in range(8192 + 96, 40960, 96)})
        a = self.refused(ls, "the last received tail record (offset 0x2000) has 96 bytes")
        self.assertIn("the end of the tail was lost", a["unreadable"][0]["reason"])

    def test_a_length_below_head_plus_tail_found_from_a_capped_end_line_is_refused(self):
        # a forged group: one 32-byte record at offset 8,192 and the end line of a capped dump
        a = self.refused(["KL 002000 " + T89.esc(b"x" * 32), "KL end why=2 recs=428 bytes=40960"], "")
        self.assertEqual(a["unreadable"][0]["reason"], "the length found from the last tail record (8224) is below head + tail (40960)")

    def test_no_end_line(self):
        a = self.refused(lines(50000, begin=False, end=False), "without a `KL end` line")
        self.assertEqual(a["unreadable"][0]["records"], 428)

    def test_no_record_at_all(self):
        self.refused(["KL end why=2 recs=428 bytes=40960"], "no record of the dump arrived")

    def test_end_line_of_an_unknown_why(self):
        self.refused(["KL 000000 abc", "KL end why=7 recs=1 bytes=3"], "why=7")

    def test_end_line_above_the_cap(self):
        self.refused(["KL 000000 abc", "KL end why=2 recs=1 bytes=40961"], "more than head + tail")

    def test_record_off_the_grid(self):
        self.refused(lines(50000, begin=False, extra=[(17233, b"x" * 96)]), "not on the inferred grid")

    def test_record_of_a_wrong_size(self):
        ls = lines(50000, begin=False)
        i = next(k for k, l in enumerate(ls) if l.startswith("KL 000060 "))      # offset 96: a head record of 96 bytes, sent here as 95
        ls[i] = ls[i][:-1]
        self.refused(ls, "not on the inferred grid")

    def test_two_tail_alignments_in_one_dump(self):
        # records of the grid starting at 17,232 and one at 17,232 + 48: the second is off the grid
        self.refused(lines(50000, begin=False, extra=[(17280, b"y" * 96)]), "not on the inferred grid")

    def test_records_out_of_order(self):
        a = self.refused(lines(50000, begin=False, reorder=True), "out of the order")
        self.assertEqual(a["unreadable"][0]["reason"], "the record at offset 0x4350 is out of the order the image sends or repeated")

    def test_a_repeated_offset(self):
        ls = lines(50000, begin=False)
        k = next(i for i, l in enumerate(ls) if l.startswith("KL 004350 "))
        ls.insert(k + 1, ls[k])
        self.refused(ls, "out of the order the image sends or repeated")

    def test_invalid_escape_is_a_lost_record_with_a_problem(self):
        ls = lines(50000, begin=False)
        k = next(i for i, l in enumerate(ls) if l.startswith("KL 004350 "))
        ls[k] = "KL 004350 \\q"
        td = archive([ls])
        a = R.read_archive2(td.name)
        d = a["dumps"][0]
        self.assertEqual(d["holes"], [(17232, 17328)])
        self.assertEqual(len(d["problems"]), 1)
        self.assertIn("not valid escaped text", d["problems"][0])

    def test_unparsed_kl_line_with_nothing_else(self):
        self.refused(["KL garbage"], "unparseable KL lines")


class Archives(unittest.TestCase):
    def test_replay_boots_without_begin_fill_each_others_holes(self):
        td = archive([lines(50000, begin=False, drop={96, 192}), lines(50000, begin=False, drop={192, 17328})])
        a = R.read_archive2(td.name)
        self.assertEqual(len(a["dumps"]), 1)
        d = a["dumps"][0]
        self.assertEqual(d["holes"], [(192, 288)])
        self.assertEqual(len(d["boots"]), 2)
        self.assertTrue(d["begin_inferred"])

    def test_a_real_begin_in_another_boot_clears_the_marker(self):
        td = archive([lines(50000, begin=False, drop={96}), lines(50000)])
        d = R.read_archive2(td.name)["dumps"][0]
        self.assertFalse(d["begin_inferred"])
        self.assertEqual(d["hole_bytes"], 0)

    def test_a_dump_with_a_different_length_stays_separate(self):
        td = archive([lines(50000, begin=False), lines(50096, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual(sorted(d["begin"]["len"] for d in a["dumps"]), [50000, 50096])

    def test_two_dumps_in_a_boot_one_with_begin_one_without(self):
        td = archive([lines(5000, why=1) + lines(50000, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual([(d["why"], d["begin"]["len"], d["begin_inferred"]) for d in a["dumps"]], [(1, 5000, False), (2, 50000, True)])

    def test_a_dump_without_begin_before_one_with_begin(self):
        td = archive([lines(50000, begin=False) + lines(5000, why=1)])
        a = R.read_archive2(td.name)
        self.assertEqual([(d["why"], d["begin"]["len"], d["begin_inferred"]) for d in a["dumps"]], [(2, 50000, True), (1, 5000, False)])
        self.assertEqual(a["unreadable"], [])

    def test_two_groups_without_begin_in_one_boot(self):
        td = archive([lines(5000, begin=False) + lines(20000, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual(sorted(d["begin"]["len"] for d in a["dumps"]), [5000, 20000])

    def test_a_group_that_fails_does_not_stop_the_next_one(self):
        td = archive([lines(50000, begin=False, recs_override=1) + lines(5000, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual([d["begin"]["len"] for d in a["dumps"]], [5000])
        self.assertEqual(len(a["unreadable"]), 1)
        self.assertEqual(a["unreadable"][0]["boot"], "000001-x")

    def test_conflicting_bytes_between_boots_are_reported(self):
        a_, b_ = lines(50000, begin=False), lines(50000, begin=False, buf=data(50000)[::-1])
        td = archive([a_, b_])
        d = R.read_archive2(td.name)["dumps"][0]
        self.assertTrue(d["conflicts"])

    def test_a_boot_directory_without_frames_is_skipped_and_the_others_are_listed_with_their_drops(self):
        with tempfile.TemporaryDirectory() as t:
            T89.write_boot(t, "000001-x", lines(5000, begin=False), drops=[(100, 2000), (5000, 7)])
            (Path(t) / "boots" / "000002-empty").mkdir()
            T89.write_boot(t, "000003-x", lines(5000))
            a = R.read_archive2(t)
        self.assertEqual(a["boots"], ["000001-x", "000003-x"])
        self.assertEqual(a["drops"], {"000001-x": [(100, 2000, "ring-overrun"), (5000, 7, "ring-overrun")], "000003-x": []})
        self.assertEqual(len(a["dumps"]), 1)

    def test_no_boots_directory(self):
        with tempfile.TemporaryDirectory() as t:
            a = R.read_archive2(t)
        self.assertEqual((a["dumps"], a["boots"], a["unreadable"]), ([], [], []))

    def test_the_end_line_without_data_between_two_dumps_does_not_swallow_the_next_records(self):
        td = archive([["KL end why=2 recs=428 bytes=40960"] + lines(5000, begin=False)])
        a = R.read_archive2(td.name)
        self.assertEqual([d["begin"]["len"] for d in a["dumps"]], [5000])
        self.assertEqual(len(a["unreadable"]), 1)
        self.assertIn("no record", a["unreadable"][0]["reason"])


class Analyzer(unittest.TestCase):
    JOBS = T89.J3

    def head_only(self, text, begin=True, drop=()):
        n = len(text)
        ls = lines(n, begin=begin, drop=drop, buf=text)
        return ls

    def write_jobs(self, td):
        d = Path(td) / "jobs"
        d.mkdir()
        import plistlib
        for label, prog, ss in ((l, p, s) for l, p, s in (("com.apple.logd", "/usr/libexec/logd", True), ("com.apple.lsd", "/usr/libexec/lsd", False),
                                                      ("com.apple.fseventsd", "/usr/libexec/fseventsd", True), ("com.nat085.ps", "/bin/ps", True))):
            pl = dict(Label=label, ProgramArguments=[prog])
            if ss:
                pl["RunAtLoad"] = True
            (d / (label + ".plist")).write_bytes(plistlib.dumps(pl))
        return d

    def text_a1(self):
        return (T89.TASKS_OK + T89.LOGD + T89.FSE + T89.HB + T89.ALL_ALIVE).encode()

    def test_a1_text_read_with_and_without_begin_gives_the_same_row(self):
        text = self.text_a1()
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            with_begin = Path(t) / "a"
            T89.write_boot(with_begin, "000001-x", self.head_only(text))
            without = Path(t) / "b"
            T89.write_boot(without, "000001-x", self.head_only(text, begin=False))
            r1, r2 = A89.analyze(with_begin, jd), A.analyze(without, jd)
            r3 = A.analyze(with_begin, jd)
        self.assertEqual(r1["row"], 1)
        self.assertEqual(r2["row"], 1)
        self.assertEqual({k: v for k, v in r3.items() if k not in ("dump", "facts")}, {k: v for k, v in r1.items() if k not in ("dump", "facts")})
        self.assertEqual({k: v for k, v in r3["facts"].items() if k != "unreadable"}, r1["facts"])
        self.assertEqual({k: v for k, v in r3["dump"].items() if k != "begin_inferred"}, r1["dump"])
        self.assertFalse(r3["dump"]["begin_inferred"])
        self.assertTrue(r2["dump"]["begin_inferred"])
        self.assertIn("geometry was inferred", r2["reason"])
        self.assertNotIn("inferred", r3["reason"])
        self.assertEqual(r2["table"], r1["table"])

    def test_without_begin_nat089_says_a8_and_v2_reads_the_row(self):
        text = self.text_a1()
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", self.head_only(text, begin=False))
            old, new = A89.analyze(t + "/arch", jd), A.analyze(t + "/arch", jd)
        self.assertEqual(old["row"], 8)
        self.assertIn("no why=2", old["reason"])
        self.assertEqual(new["row"], 1)

    def test_a_refused_group_is_named_in_the_a8_reason(self):
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", lines(50000, begin=False, drop={49968}))
            r = A.analyze(t + "/arch", jd)
        self.assertEqual(r["row"], 8)
        self.assertIn("1 group(s) of records without a begin could not be inferred", r["reason"])
        self.assertIn("the end of the tail was lost", r["reason"])
        self.assertEqual(len(r["facts"]["unreadable"]), 1)

    def test_no_dump_at_all_is_a8_without_the_unreadable_clause(self):
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", ["not a KL line"])
            r = A.analyze(t + "/arch", jd)
        self.assertEqual(r["row"], 8)
        self.assertNotIn("could not be inferred", r["reason"])

    def test_a_why_2_dump_of_length_zero_has_no_text_and_one_of_length_one_has(self):
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/empty", "000001-x", ["KL begin why=2 len=0 head=0 tail=0 gap=0 x0=0x0", "KL end why=2 recs=0 bytes=0"])
            T89.write_boot(t + "/one", "000001-x", ["KL begin why=2 len=1 head=1 tail=0 gap=0 x0=0x0", "KL 000000 x", "KL end why=2 recs=1 bytes=1"])
            r0, r1 = A.analyze(t + "/empty", jd), A.analyze(t + "/one", jd)
        self.assertEqual(r0["row"], 8)
        self.assertIn("no why=2 kernel-log dump with text", r0["reason"])
        self.assertEqual(r1["row"], 8)
        self.assertIn("no launchd line in the returned text", r1["reason"])

    def test_the_unreadable_groups_are_listed_next_to_a_dump_that_was_read(self):
        text = self.text_a1()
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", lines(50000, begin=False, drop={49968}) + self.head_only(text, begin=False))
            r = A.analyze(t + "/arch", jd)
            T89.write_boot(t + "/clean", "000001-x", self.head_only(text, begin=False))
            c = A.analyze(t + "/clean", jd)
        self.assertEqual(r["row"], 1)
        self.assertEqual([u["boot"] for u in r["facts"]["unreadable"]], ["000001-x"])
        self.assertIn("the end of the tail was lost", r["facts"]["unreadable"][0]["reason"])
        self.assertEqual(c["facts"]["unreadable"], [])

    def test_a_why_1_dump_alone_is_not_the_final_dump(self):
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", lines(5000, why=1, begin=False))
            r = A.analyze(t + "/arch", jd)
        self.assertEqual(r["row"], 8)
        self.assertIn("no why=2", r["reason"])

    def test_the_longest_final_dump_is_read(self):
        text = self.text_a1()
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", lines(300, begin=False, buf=b"x" * 300) + self.head_only(text, begin=False))
            r = A.analyze(t + "/arch", jd)
        self.assertEqual(r["row"], 1)
        self.assertEqual(r["dump"]["begin"]["len"], len(text))

    def test_conflicts_are_warned_about(self):
        text = self.text_a1()
        other = text.replace(b"logd", b"LOGD", 1)
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", self.head_only(text, begin=False))
            T89.write_boot(t + "/arch", "000002-x", self.head_only(other, begin=False))
            r = A.analyze(t + "/arch", jd)
        self.assertRegex(r["reason"], r"; WARNING: \d+ offsets have different bytes in different boots$")

    def test_main_writes_the_json_and_prints_the_row(self):
        import contextlib
        import io
        text = self.text_a1()
        with tempfile.TemporaryDirectory() as t:
            jd = self.write_jobs(t)
            T89.write_boot(t + "/arch", "000001-x", self.head_only(text, begin=False))
            out = Path(t) / "r.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = A.main(["--archive", t + "/arch", "--jobs-dir", str(jd), "--out", str(out)])
            j = json.loads(out.read_text())
        self.assertEqual(rc, 0)
        self.assertEqual(j["row"], 1)
        self.assertTrue(buf.getvalue().startswith("row A1 "))
        self.assertIn("com.apple.logd", buf.getvalue())


@unittest.skipUnless(REAL.is_dir() and POSTHOC.is_file(), "the NAT-093 archive is a local artifact")
class RealNat093(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = R.read_archive2(REAL)
        cls.ph = json.loads(POSTHOC.read_text())["geometry"]

    def test_one_inferred_dump_with_the_hand_read_geometry(self):
        self.assertEqual(self.a["unreadable"], [])
        finals = [d for d in self.a["dumps"] if d["why"] == 2]
        self.assertEqual(len(finals), 1)
        d = finals[0]
        self.assertTrue(d["begin_inferred"])
        self.assertEqual((d["begin"]["len"], d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"]), (170097, 8192, 32768, 129137))
        self.assertEqual(len(d["bytes"]), 345)
        self.assertEqual(d["hole_bytes"], 7968)
        self.assertEqual([[lo, hi] for lo, hi in d["holes"]], self.ph["missing"])
        self.assertEqual([[lo, hi] for lo, hi in d["holes"]], [[137329, 142129], [145489, 148657]])
        self.assertEqual((d["conflicts"], d["extra_offsets"], d["problems"]), ([], [], []))

    def test_the_numbers_equal_posthoc_json(self):
        d = [d for d in self.a["dumps"] if d["why"] == 2][0]
        self.assertEqual((len(d["bytes"]), d["begin"]["len"], self.ph["records"], self.ph["length"], self.ph["expected_records"]), (345, 170097, 345, 170097, 428))

    def test_the_bytes_equal_the_ones_the_hand_reader_read(self):
        import posthoc_boot2 as P
        a62 = P.load_a62()
        boots = sorted((REAL / "boots").glob("000002-*"))
        recs, end = P.read_boot(a62, boots[0])
        d = [d for d in self.a["dumps"] if d["why"] == 2][0]
        self.assertEqual(d["bytes"], recs)
        self.assertEqual(end, dict(why=2, recs=428, bytes=40960))

    def test_the_old_reader_says_no_dump_and_the_new_one_does_not_change_the_row(self):
        jd = HERE.parents[2] / "artifacts" / "nat-096" / "pid1-sq" / "root" / "LaunchDaemons"
        if not jd.is_dir():
            self.skipTest("the NAT-096 small root is a local artifact")
        old, new = A89.analyze(REAL, jd), A.analyze(REAL, jd)
        self.assertEqual(old["row"], 8)
        self.assertIn("no why=2", old["reason"])
        self.assertEqual(new["row"], 8)
        self.assertIn("no launchd line", new["reason"])
        self.assertTrue(new["dump"]["begin_inferred"])


if __name__ == "__main__":
    unittest.main()
