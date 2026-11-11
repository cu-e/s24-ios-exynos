#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-062 host tests, first half: the sources of loader-diag-xnu-run-usb (NAT-059's image + patch_run62.py + the payload command-line patch), the code that
sends the kernel's log (glue62_impl.h) built for the host and read back by the analyser's parser, and the payload facts it relies on.
Evidence kind: host-test. Nothing here runs on, or is sent to, the phone.

    <capture venv>/bin/python -W ignore -I docs/procedures/nat-062/test_nat062.py     (capstone for the payload symbols; cc for the host build)

Layers:
  Derivation   patch_run62.py's hunks apply once each to NAT-059's derived tree and only ADD lines; the built tree differs from NAT-059's in exactly
               ckpt3.c, markerlib52.c and the two new headers; the stub, the stop list and the resume code are NAT-059's (which ran on the phone in NAT-060).
  Cmdline      build.py's command-line patch changes only the NUL-padded command-line field of the NAT-020 payload, to the one string the review expects.
  Host         glue62_impl.h compiled for the host (the engine replaced by a recorder, the log by a byte array that aborts on any read outside it) and its
               output read back by analyze_nat062.py's parser: every byte of the log survives the escaping, head/tail/gap, order, refusal, pacing.
  Payload      the constants against the payload and the kernel source: the symbols loader_log / loader_log_len and the boot-arg name.
  Build        the pins in build.json (hashes, reproducibility) and the image's sources.
The expected values come from the payload, the kernel source and the engine's ring size, not from the implementation."""
import difflib, hashlib, importlib.util, json, os, random, re, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
SRC = HERE / "src"
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
KERNEL_LOG_C = ROOT / "artifacts/nat-020/build-003/source/xnu/hackios/files/osfmk/arm64/loader_return.c"
B59 = ROOT / "artifacts/nat-059/build-003"
B62 = ROOT / "artifacts/nat-062/build-001"
B62B = ROOT / "artifacts/nat-062/build-002"
PKG62 = ROOT / "artifacts/nat-062/package-001"
IMAGE = "loader-diag-xnu-run-usb"
IMAGE59 = "loader-diag-xnu-ckpt4-usb"
SCRATCH = ROOT / "artifacts/nat-062/tmp"           # gitignored; the user's /tmp quota on this host is small
source_pin = unittest.skipIf(os.environ.get("NAT062_BEHAVIOUR_ONLY") == "1", "source-text pin (skipped in the behavioural mutation pass)")
sha = lambda b: hashlib.sha256(b).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


p62 = load("nat062t_patch", Path(os.environ.get("NAT062_PATCH") or HERE / "patch_run62.py"))      # mutated copies for the mutation checks
b62 = load("nat062t_build", Path(os.environ.get("NAT062_BUILD") or HERE / "build.py"))
A62 = load("nat062t_analyze", Path(os.environ.get("NAT062_ANALYZE") or HERE / "analyze_nat062.py"))
E59 = B59 / IMAGE59 / "source/shim/e1s-xnu"
E62 = B62 / IMAGE / "source/shim/e1s-xnu"
have_trees = unittest.skipUnless(E59.exists() and E62.exists(), "the NAT-059 build-003 / NAT-062 build-001 trees are not present")


def scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


# ------------------------------------------------------------------------------------------------------------------ Derivation
@have_trees
class Derivation(unittest.TestCase):
    def derive(self):
        return p62.derive(E59)

    @source_pin
    def test_every_anchor_occurs_once_and_the_change_only_adds_lines(self):
        out = self.derive()                                          # patch_text raises SystemExit unless each anchor occurs exactly once
        self.assertEqual(sorted(p.name for p in out), ["ckpt3.c", "markerlib52.c"])
        for p, new in out.items():
            old = p.read_text()
            nd = list(difflib.ndiff(old.splitlines(), new.splitlines()))
            self.assertEqual([l for l in nd if l.startswith("- ")], [], "%s: the change must not remove a line" % p.name)
        added = lambda name: [l[2:] for l in difflib.ndiff((E59 / name).read_text().splitlines(), {p.name: t for p, t in out.items()}[name].splitlines()) if l.startswith("+ ")]
        self.assertEqual(added("markerlib52.c"), ['#include "glue62_impl.h"'])
        self.assertEqual(added("ckpt3.c"), [
            '#include "glue62.h"',
            "\tif (d.final && rt && ttbr0_ok(rt)) {\t/* NAT-062: the last stop: send the kernel's log so far, then let the kernel run on */",
            "\t\tnat062_dump_log(f->x[0], f->x[1], nat036_st.s.pa_minus_va, NAT062_WHY_FINAL);",
            "\t\td.action = NAT036_RESUME_C;",
            "\t\td.next = 0;\t\t\t/* slot[2] = 0: no checkpoint id is 0, the kernel does not stop again */",
            "\t} else if ((f->x[2] & 0xff) == 0) {\t/* NAT-062: the kernel's own return: send the log it hands over, then hold as before */",
            "\t\tnat062_dump_log(f->x[0], f->x[1], nat036_st.s.pa_minus_va, NAT062_WHY_RETURN);",
            "\t}"])

    def test_a_changed_anchor_is_refused_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.exists() else None) as d:
            e = Path(d)
            for f in ("ckpt3.c", "markerlib52.c"):
                (e / f).write_text((E59 / f).read_text())
            (e / "ckpt3.c").write_text((E59 / "ckpt3.c").read_text().replace("nat052_note_stop(&r);", "nat052_note_stop( &r );"))
            before = {f: (e / f).read_text() for f in ("ckpt3.c", "markerlib52.c")}
            with self.assertRaises(SystemExit) as cm:
                p62.derive(e)
            self.assertIn("anchor 'stop-handler' occurs 0 times", str(cm.exception))
            (e / "ckpt3.c").write_text((E59 / "ckpt3.c").read_text() + "\n" + p62.CKPT3_C[1][1])                  # a second occurrence of the anchor
            with self.assertRaises(SystemExit) as cm:
                p62.derive(e)
            self.assertIn("occurs 2 times", str(cm.exception))
            self.assertEqual((e / "markerlib52.c").read_text(), before["markerlib52.c"])

    def test_the_built_tree_differs_from_the_nat059_tree_in_exactly_these_files(self):
        rel = lambda base: {str(p.relative_to(base)): sha(p.read_bytes()) for p in sorted((base).rglob("*")) if p.is_file()}
        a, b = rel(B59 / IMAGE59 / "source"), rel(B62 / IMAGE / "source")
        self.assertEqual(sorted(set(a) ^ set(b)), ["shim/e1s-xnu/glue62.h", "shim/e1s-xnu/glue62_impl.h"])
        self.assertEqual(sorted(k for k in a if k in b and a[k] != b[k]), ["shim/e1s-xnu/ckpt3.c", "shim/e1s-xnu/markerlib52.c"])
        # and the built files are what derive() gives from NAT-059's, plus the two headers as committed
        for p, text in self.derive().items():
            self.assertEqual((E62 / p.name).read_text(), text, p.name)
        for f in ("glue62.h", "glue62_impl.h"):
            self.assertEqual((E62 / f).read_bytes(), (SRC / f).read_bytes(), f)

    def test_the_stub_the_stop_list_and_the_resume_rules_are_the_ones_that_ran_on_the_phone(self):
        # NAT-060 ran the NAT-059 build: its stub assembly and its ckpt.c are byte for byte the ones here
        for f in ("ckpt3_stub.S", "ckpt.c", "ckpt.h", "ckpt3.h", "markerlib47.c", "glue52.h", "glue52_impl.h"):
            if (E59 / f).exists():
                self.assertEqual((E62 / f).read_bytes(), (E59 / f).read_bytes(), f)
        c = (E62 / "ckpt3.c").read_text()
        self.assertIn("#define NAT036_STOP_LIST 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21\n", c)
        self.assertEqual(json.loads((B62 / "build.json").read_text())["stops"], json.loads((B59 / "build.json").read_text())["stops"])

    def test_the_final_stop_resumes_only_when_the_ttbr0_to_give_back_was_checked_and_the_return_only_holds(self):
        c = (E62 / "ckpt3.c").read_text()
        body = c[c.index("struct nat036_ret nat036_ckpt_c"):]
        i_note, i_final, i_ret, i_hold = (body.index(s) for s in ("nat052_note_stop(&r);", "if (d.final && rt && ttbr0_ok(rt))", "else if ((f->x[2] & 0xff) == 0)", "if (d.action == NAT036_HOLD)"))
        self.assertTrue(i_note < i_final < i_ret < i_hold, "the note comes first; the dump decisions come before the hold test")
        self.assertLess(body.index("nat059_resume_decision("), i_final, "rt is known before the final stop is resumed")
        self.assertEqual(body.count("NAT062_WHY_FINAL"), 1)
        self.assertEqual(body.count("NAT062_WHY_RETURN"), 1)
        # a final stop whose TTBR0 is not plausible keeps the old behaviour (hold): the else branch is not entered for it, because x2 is 2, not 0
        self.assertIn("(f->x[2] & 0xff) == 0", body)


# ------------------------------------------------------------------------------------------------------------------ Cmdline
@unittest.skipUnless(PAYLOAD.exists(), "the NAT-020 build-003 payload is missing")
class Cmdline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = PAYLOAD.read_bytes()

    def test_only_the_command_line_field_changes_to_the_expected_string(self):
        new, info = b62.patch_cmdline(self.data)
        self.assertEqual(len(new), len(self.data))
        diff = [i for i in range(len(new)) if new[i] != self.data[i]]
        self.assertTrue(diff and 0x48 <= diff[0] and diff[-1] < 0x48 + 608, (diff[:3], diff[-3:]))
        want = ("rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT062-run debug=0xc serial=3 cpus=1 keepsyms=1 -v "
                "loader_return_after=8")
        self.assertEqual(new[0x48:0x48 + 608].rstrip(b"\0").decode(), want)
        self.assertEqual(new[0x48 + len(want):0x48 + 608], b"\0" * (608 - len(want)))
        self.assertEqual(info["old"], self.data[0x48:0x48 + 608].rstrip(b"\0").decode())
        self.assertEqual((info["base_sha256"], info["fixed_sha256"]), (sha(self.data), sha(new)))
        self.assertLess(len(want), 256, "the kernel's BOOT_LINE_LENGTH")
        self.assertEqual(want.count("nat_attempt="), 1)

    def test_the_boot_arg_is_the_one_the_kernel_parses_and_the_header_is_the_payloads(self):
        self.assertEqual(self.data[:8], b"SWEETXNU")
        self.assertIn(b"\0loader_return_after\0", self.data, "the kernel's PE_parse_boot_argn name")
        if KERNEL_LOG_C.exists():
            self.assertIn('PE_parse_boot_argn("loader_return_after", &seconds, sizeof(seconds))', KERNEL_LOG_C.read_text())
            self.assertIn("seconds == 0", KERNEL_LOG_C.read_text(), "0 would mean no timer")
        self.assertEqual(b62.APPEND, b" loader_return_after=8")

    def test_a_command_line_that_is_not_the_expected_one_is_refused(self):
        d = bytearray(self.data)
        for label, mutate in (
                ("no tag", lambda x: x.__setitem__(slice(0x48, 0x48 + 608), x[0x48:0x48 + 608].replace(b"NAT020-83s", b"NAT020-84s"))),
                ("already has it", lambda x: x.__setitem__(slice(0x48 + 125, 0x48 + 125 + 21), b" loader_return_after")),
                ("magic", lambda x: x.__setitem__(slice(0, 8), b"SWEETXNV")),
                ("two strings", lambda x: x.__setitem__(0x48 + 300, ord("x")))):
            x = bytearray(self.data)
            mutate(x)
            with self.assertRaises(SystemExit, msg=label):
                b62.patch_cmdline(bytes(x))
        self.assertEqual(bytes(d), self.data)

    def test_the_built_payload_carries_exactly_this_command_line(self):
        rec = B62 / "build.json"
        fixed = B62 / IMAGE / "payload.adt8.bin"
        if not (rec.exists() and fixed.exists()):
            self.skipTest("no build record")
        fix = json.loads(rec.read_text())["payload_fixes"][IMAGE]
        blob = fixed.read_bytes()
        self.assertEqual(sha(blob), fix["fixed_sha256"])
        self.assertEqual(blob[0x48:0x48 + 608].rstrip(b"\0").decode(), fix["cmdline_patch"]["new"])
        # the ADT-size fix (NAT-022) is the only other difference from the NAT-020 payload
        diff = [i for i in range(len(blob)) if blob[i] != self.data[i]]
        self.assertTrue(all(i in (40, 41) or 0x48 <= i < 0x48 + 608 for i in diff), "only the ADT size (header offset 40) and the command line differ")


# ------------------------------------------------------------------------------------------------------------------ Host
HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define NAT062_HOST 1
#define UNUSED __attribute__((unused))
static const uint8_t *g_mem;
static uint64_t g_base, g_len, g_reads, g_lo = ~0ull, g_hi;
static int g_up = 1;
static UNUSED uint8_t rd(uint64_t pa)
{
	if (pa < g_base || pa >= g_base + g_len) {
		fprintf(stderr, "OOB read at %llx\n", (unsigned long long)pa);
		exit(3);
	}
	g_reads++;
	if (pa < g_lo) g_lo = pa;
	if (pa > g_hi) g_hi = pa;
	return g_mem[pa - g_base];
}
static UNUSED void emit(const char *b, const char *e)
{
	fputs("R ", stdout);
	fwrite(b, 1, (size_t)(e - b), stdout);
	fputc('\n', stdout);
}
static UNUSED void wait_(void) { fputs("W\n", stdout); }
#define N62_UP() g_up
#define N62_EMIT(b, e) emit((b), (e))
#define N62_WAIT() wait_()
#define N62_BYTE(pa) rd((uint64_t)(pa))
@N47@
#include "glue62_impl.h"
int main(int argc, char **argv)
{
	if (argc != 8) return 2;
	uint64_t x0 = strtoull(argv[1], 0, 16), x1 = strtoull(argv[2], 0, 16), delta = strtoull(argv[3], 0, 16);
	uint32_t why = (uint32_t)strtoul(argv[4], 0, 10);
	g_up = atoi(argv[5]);
	FILE *f = fopen(argv[6], "rb");
	static uint8_t buf[0x200000];
	g_len = f ? fread(buf, 1, sizeof buf, f) : 0;
	g_mem = buf;
	g_base = x0;
	nat062_dump_log(x0, x1, delta, why);
	fprintf(stderr, "reads=%llu lo=%llx hi=%llx\n", (unsigned long long)g_reads, (unsigned long long)g_lo, (unsigned long long)g_hi);
	return 0;
}
'''
LOG_VA = 0xfffffff007b90a00
PA = 0x9a2b0a00                           # an arbitrary physical address of loader_log
DELTA = (PA - LOG_VA) % (1 << 64)         # PA - VA, as the loader computes it (wraps modulo 2**64)
HEAD = {1: 8192, 2: 8192}
TAIL = {1: 8192, 2: 32768}
LOG_MAX = 0x180000
BURST, RING = 8192, 32768


def n47_text():
    src = (PROC / "nat-047/src/markerlib47.c").read_text()
    out = []
    for name in ("n47_s", "n47_x", "n47_d"):
        m = re.search(r"static char \*%s\(.*?\n}\n" % name, src, re.S)
        out.append(m.group(0).replace("static char", "static UNUSED char", 1))
    return "\n".join(out)


def pattern(n, seed=1):
    """Log bytes that exercise every escape: all 256 values in a shuffled order, repeated, with text and newlines mixed in."""
    r = random.Random(seed)
    vals = list(range(256))
    out = bytearray()
    while len(out) < n:
        r.shuffle(vals)
        out += bytes(vals)
        out += b"xnu: [ 1.234] CPU0: hello \\ world\r\n"
    return bytes(out[:n])


needs_cc = unittest.skipUnless(subprocess.run(["cc", "--version"], capture_output=True).returncode == 0, "no host C compiler")


@needs_cc
class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = scratch("host-")
        h = cls.tmp / "harness.c"
        h.write_text(HARNESS.replace("@N47@", n47_text()))
        impl = cls.impl = Path(os.environ.get("NAT062_SRC") or SRC)
        cls.exe = cls.tmp / "harness"
        r = subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-I", str(impl), str(h), "-o", str(cls.exe)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def dump(self, log, why=1, *, x0=None, x1=None, up=1, delta=DELTA):
        """-> (records, waits, reads, lo, hi, parsed). `records` is the text of every KL record; `waits[i]` the number of records emitted before wait i."""
        x0 = (LOG_VA + delta) % (1 << 64) if x0 is None else x0
        x1 = len(log) if x1 is None else x1
        f = self.tmp / "mem.bin"
        f.write_bytes(log)
        r = subprocess.run([str(self.exe), "%x" % (x0 % (1 << 64)), "%x" % x1, "%x" % delta, str(why), str(up), str(f), "-"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        recs, waits, sizes = [], [], []
        for line in r.stdout.splitlines():
            if line == "W":
                waits.append(len(recs))
            else:
                self.assertTrue(line.startswith("R "), line)
                recs.append(line[2:])
        m = re.match(r"reads=(\d+) lo=([0-9a-f]+) hi=([0-9a-f]+)", r.stderr.strip().splitlines()[-1])
        return recs, waits, int(m[1]), int(m[2], 16), int(m[3], 16)

    def expect_split(self, n, why):
        head = min(n, HEAD[why])
        tail = min(n - head, TAIL[why])
        return head, tail, n - head - tail

    def parse(self, recs):
        dumps, stray = A62.parse_kl(recs)
        self.assertEqual(stray, [])
        return dumps

    def test_every_byte_value_survives_the_escaping_and_the_dump_is_complete(self):
        for why in (1, 2):
            for n in (1, 95, 96, 97, 4000, 8192):
                with self.subTest(why=why, n=n):
                    log = pattern(n, seed=n)
                    recs, waits, reads, lo, hi = self.dump(log, why)
                    (d,) = self.parse(recs)
                    self.assertEqual((d["status"], d["problems"]), ("complete", []))
                    self.assertEqual(b"".join(r for _, r in sorted(d["records"])), log)
                    self.assertEqual((d["begin"]["why"], d["begin"]["len"], d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"]), (why, n, n, 0, 0))
                    self.assertEqual(reads, n, "every byte is read exactly once")

    def test_the_text_of_a_dump_with_a_gap_is_head_marker_tail_and_the_gap_bytes_are_never_read(self):
        for why in (1, 2):
            for n in (HEAD[why] + TAIL[why] + 1, HEAD[why] + TAIL[why] + 5000, 100000, 1500000):
                with self.subTest(why=why, n=n):
                    log = pattern(n, seed=n)
                    recs, waits, reads, lo, hi = self.dump(log, why)
                    (d,) = self.parse(recs)
                    head, tail, gap = self.expect_split(n, why)
                    self.assertGreater(gap, 0)
                    self.assertEqual((d["status"], d["begin"]["head"], d["begin"]["tail"], d["begin"]["gap"]), ("complete", head, tail, gap))
                    got = A62.dump_text(d)
                    marker = "\n[... %d bytes of the log were not sent ...]\n" % gap
                    self.assertEqual(got, (log[:head].decode("utf-8", "replace") + marker + log[n - tail:].decode("utf-8", "replace")))
                    self.assertEqual(reads, head + tail)
                    self.assertEqual(sum(len(r) for _, r in d["records"]), head + tail)
                    # the newest text first, then the oldest
                    offs = [o for o, _ in d["records"]]
                    self.assertEqual(offs[0], n - tail)
                    self.assertEqual(offs[-((head + 95) // 96)], 0, "the oldest text follows the newest")
                    self.assertEqual(sorted(offs), sorted(set(offs)))

    def test_a_log_of_exactly_head_plus_tail_has_no_gap_and_one_byte_more_has_a_gap_of_one(self):
        for why in (1, 2):
            n = HEAD[why] + TAIL[why]
            recs, _, reads, _, _ = self.dump(pattern(n), why)
            (d,) = self.parse(recs)
            self.assertEqual((d["status"], d["begin"]["gap"]), ("complete", 0))
            self.assertEqual(reads, n)
            recs, _, reads, _, _ = self.dump(pattern(n + 1), why)
            (d,) = self.parse(recs)
            self.assertEqual((d["status"], d["begin"]["gap"], reads), ("complete", 1, n))

    def test_an_empty_log_is_a_complete_dump_of_nothing(self):
        recs, waits, reads, lo, hi = self.dump(b"", 1)
        (d,) = self.parse(recs)
        self.assertEqual((d["status"], d["begin"]["len"], len(d["records"]), reads), ("complete", 0, 0, 0))
        self.assertEqual(len(waits), 1, "the final wait only")

    def test_the_largest_log_the_array_can_hold_is_accepted_and_one_more_byte_is_refused_without_reading(self):
        recs, _, reads, _, _ = self.dump(pattern(LOG_MAX), 2)
        (d,) = self.parse(recs)
        self.assertEqual((d["status"], d["begin"]["len"], d["begin"]["gap"]), ("complete", LOG_MAX, LOG_MAX - 8192 - 32768))
        self.assertEqual(reads, 8192 + 32768)
        recs, waits, reads, lo, hi = self.dump(b"", 2, x1=LOG_MAX + 1)
        self.assertEqual(recs, ["KL refused why=2 x0=0x%x x1=0x%x" % (PA, LOG_MAX + 1)])
        self.assertEqual((reads, len(waits)), (0, 1))

    def test_only_the_payloads_loader_log_address_is_dumped(self):
        for label, x0 in (("the virtual address itself", LOG_VA), ("one byte off", PA + 1), ("zero", 0), ("page below", PA - 4096)):
            with self.subTest(label):
                recs, waits, reads, lo, hi = self.dump(b"", 1, x0=x0, x1=100)
                self.assertEqual(recs, ["KL refused why=1 x0=0x%x x1=0x64" % x0])
                self.assertEqual(reads, 0)
        recs, _, reads, _, _ = self.dump(pattern(10), 1, delta=0)                     # a delta of 0 (MMU-off identity) is a delta like any other
        self.assertEqual(self.parse(recs)[0]["status"], "complete")

    def test_nothing_is_sent_and_nothing_is_read_while_the_engine_is_not_up(self):
        recs, waits, reads, lo, hi = self.dump(pattern(500), 1, up=0)
        self.assertEqual((recs, waits, reads), ([], [], 0))

    def test_every_record_is_printable_ascii_on_one_line_within_the_buffer_and_the_engines_record_size(self):
        recs, _, _, _, _ = self.dump(pattern(60000), 2)
        for r in recs:
            self.assertTrue(all(0x20 <= ord(c) < 0x7f for c in r), r)
            self.assertLessEqual(len(r), 448, "NAT062_REC_MAX")
            self.assertLessEqual(len(r), 1024, "USBMON_REC_MAX")
            self.assertTrue(r.startswith("KL "))

    def test_the_host_never_gets_more_than_a_third_of_the_ring_between_two_polls(self):
        """The engine has no acknowledgement and `usbmon_log` overwrites the oldest record when the ring (32 KiB) is full: pacing is the only protection."""
        for why, n in ((1, 20000), (2, 1500000), (2, 30000)):
            recs, waits, _, _, _ = self.dump(pattern(n, seed=7), why)
            sizes, start = [], 0
            for w in waits + [len(recs)]:
                sizes.append(sum(len(r) + 16 for r in recs[start:w]))
                start = w
            self.assertEqual(waits[-1], len(recs), "the last thing is a wait: what is still in the ring is polled out before the kernel runs or the hold starts")
            self.assertLessEqual(max(sizes), BURST + 448 + 16 + 120, (why, n, max(sizes)))
            self.assertLess(3 * max(sizes), RING)
            if len(recs) > 100:
                self.assertGreaterEqual(len(waits), sum(len(r) + 16 for r in recs) // (BURST + 600), "a wait about every 8 KiB")

    def test_the_wait_after_a_burst_is_the_loaders_poll_and_long_enough_for_the_host_to_read_the_burst(self):
        """The harness replaces N62_WAIT by a marker, so its length is read from the source. A burst is at most about 8.7 KiB in the ring; the host reads up to
        4 KiB per control transfer at about 17 ms (NAT-043/058 timelines), i.e. 3 transfers = ~0.05 s: the poll must last at least 0.2 s (4x margin) and at most 1 s
        (the NAT-044 deadline budget: a return dump has about 6 waits)."""
        t = (self.impl / "glue62_impl.h").read_text()
        self.assertIn("#define N62_WAIT()\tmk_wait_tenths(NAT062_WAIT_TENTHS)\n", t)
        n = int(re.search(r"#define NAT062_WAIT_TENTHS\s+(\d+)u", t)[1])
        self.assertTrue(2 <= n <= 10, "NAT062_WAIT_TENTHS=%d" % n)

    def test_the_begin_and_end_records_say_what_was_sent_and_the_parser_checks_them(self):
        recs, _, _, _, _ = self.dump(pattern(30000), 1)
        self.assertRegex(recs[0], r"^KL begin why=1 len=30000 head=8192 tail=8192 gap=13616 x0=0x[0-9a-f]+$")
        self.assertRegex(recs[-1], r"^KL end why=1 recs=%d bytes=16384$" % (len(recs) - 2))
        # damage in transit is named
        bad = list(recs)
        del bad[5]
        (d,) = self.parse(bad)
        self.assertEqual(d["status"], "damaged")
        self.assertTrue(any("do not cover the announced ranges" in p for p in d["problems"]), d["problems"])
        bad = recs[:-1]
        (d,) = self.parse(bad)
        self.assertEqual(d["status"], "truncated")
        bad = list(recs)
        bad[7] = bad[7][:12] + "\\q" + bad[7][14:]
        (d,) = self.parse(bad)
        self.assertEqual(d["status"], "damaged")
        self.assertTrue(any("not valid escaped text" in p for p in d["problems"]), d["problems"])


# ------------------------------------------------------------------------------------------------------------------ Parser
class Parser(unittest.TestCase):
    """analyze_nat062.py's reader of the `KL` records, on text written by hand (the C writer is checked against it in the Host layer)."""

    def test_unescape_inverts_the_dumps_escapes_and_refuses_anything_else(self):
        self.assertEqual(A62.unescape("abc \\\\ x\\n\\r\\x00\\xff~"), b"abc \\ x\n\r\x00\xff~")
        self.assertEqual(A62.unescape(""), b"")
        for bad in ("\\q", "\\", "\\x4", "\\xzz", "\\X41", "a\x01b", "a\x7fb", "\u00e9", "tab\there"):
            self.assertIsNone(A62.unescape(bad), repr(bad))

    def test_the_four_record_kinds_and_their_neighbours(self):
        lines = ["CK n=1 arr=1 last=1 x2=0x2 x3=0x1 mask=0x2 sctlr=0x0 sp=0x0 kttbr0=0x0 vbar=0x0 setups=0",
                 "KL begin why=1 len=3 head=3 tail=0 gap=0 x0=0x9a2b0a00", "KL 000000 abc", "KL end why=1 recs=1 bytes=3",
                 "KL refused why=2 x0=0x1 x1=0x2", "HOLD stage=0x51 code=0x203e"]
        dumps, stray = A62.parse_kl(lines)
        self.assertEqual(stray, [])
        self.assertEqual([(d["why"], d["status"]) for d in dumps], [(1, "complete"), (2, "refused")])
        self.assertEqual(dumps[0]["records"], [(0, b"abc")])
        self.assertEqual(dumps[1]["refused"], {"x0": 1, "x1": 2})

    def test_a_dump_that_is_not_closed_before_the_next_begins_is_truncated_and_stray_lines_are_reported(self):
        lines = ["KL begin why=1 len=3 head=3 tail=0 gap=0 x0=0x1", "KL 000000 abc", "KL begin why=2 len=1 head=1 tail=0 gap=0 x0=0x1", "KL 000000 z", "KL end why=2 recs=1 bytes=1",
                 "KL 000000 stray", "KL end why=1 recs=0 bytes=0"]
        dumps, stray = A62.parse_kl(lines)
        self.assertEqual([(d["why"], d["status"]) for d in dumps], [(1, "truncated"), (2, "complete")])
        self.assertEqual([i for i, _ in stray], [5, 6], "the record outside any dump and the end record that closes nothing")
        self.assertTrue(any("unparsed KL line" in p or "KL begin" in p for p in dumps[0]["problems"]))

    def test_the_end_record_must_agree_with_the_begin_record(self):
        for end, word in (("KL end why=2 recs=1 bytes=3", "does not match begin"), ("KL end why=1 recs=2 bytes=3", "the end record says 2 records")):
            (d,), _ = A62.parse_kl(["KL begin why=1 len=3 head=3 tail=0 gap=0 x0=0x1", "KL 000000 abc", end])
            self.assertEqual(d["status"], "damaged")
            self.assertTrue(any(word in p for p in d["problems"]), d["problems"])
        (d,), _ = A62.parse_kl(["KL begin why=1 len=10 head=3 tail=3 gap=3 x0=0x1", "KL 000007 xyz", "KL 000000 abc", "KL end why=1 recs=2 bytes=6"])
        self.assertEqual(d["status"], "damaged", "head + tail + gap = len holds here, but the image would have sent head 8192 or the whole 10 bytes")
        self.assertTrue(any("does not send the head and tail this image sends" in p for p in d["problems"]), d["problems"])
        (d,), _ = A62.parse_kl(["KL begin why=1 len=10 head=10 tail=0 gap=1 x0=0x1", "KL end why=1 recs=0 bytes=0"])
        self.assertTrue(any("head+tail+gap" in p for p in d["problems"]), d["problems"])
        (d,), _ = A62.parse_kl(["KL begin why=3 len=2 head=2 tail=0 gap=0 x0=0x1", "KL 000000 ab", "KL end why=3 recs=1 bytes=2"])
        self.assertTrue(any("outside what the image can send" in p for p in d["problems"]), d["problems"])
        (d,), _ = A62.parse_kl(["KL begin why=1 len=%d head=8192 tail=8192 gap=%d x0=0x1" % (LOG_MAX + 1, LOG_MAX + 1 - 16384), "KL end why=1 recs=0 bytes=0"])
        self.assertTrue(any("outside what the image can send" in p for p in d["problems"]), d["problems"])

    def test_a_record_at_the_wrong_offset_or_of_the_wrong_size_is_not_complete(self):
        (d,), _ = A62.parse_kl(["KL begin why=1 len=200 head=200 tail=0 gap=0 x0=0x1", "KL 000000 " + "a" * 96, "KL 000060 " + "b" * 96, "KL 0000c0 " + "c" * 8, "KL end why=1 recs=3 bytes=200"])
        self.assertEqual(d["status"], "complete")
        (d,), _ = A62.parse_kl(["KL begin why=1 len=200 head=200 tail=0 gap=0 x0=0x1", "KL 000000 " + "a" * 96, "KL 000061 " + "b" * 96, "KL 0000c1 " + "c" * 8, "KL end why=1 recs=3 bytes=200"])
        self.assertEqual(d["status"], "damaged")


# ------------------------------------------------------------------------------------------------------------------ Payload
@unittest.skipUnless(PAYLOAD.exists(), "the NAT-020 build-003 payload is missing")
class Payload(unittest.TestCase):
    def test_the_log_address_and_size_are_the_payloads_symbols(self):
        try:
            import capstone  # noqa: F401  (the NAT-035 model's inputs import it)
            n35 = PROC / "nat-035"
            sys.path.insert(0, str(n35))
            cr = load("nat062t_cresume", n35 / "cresume.py")
            v = cr.a5.Image().vals
        except Exception as e:
            self.skipTest("the NAT-035 model inputs are missing: %r" % (e,))
        self.assertEqual(v["_loader_log"], LOG_VA)
        h = (SRC / "glue62.h").read_text()
        self.assertEqual(int(re.search(r"NAT062_LOG_VA\s+(0x[0-9a-fA-F]+)ULL", h)[1], 16), v["_loader_log"])
        self.assertEqual(int(re.search(r"NAT062_LOG_MAX\s+(0x[0-9a-fA-F]+)ULL", h)[1], 16), v["_loader_log_len"] - v["_loader_log"], "loader_log is a char array that ends where loader_log_len begins")

    def test_the_array_size_is_the_kernel_sources(self):
        if not KERNEL_LOG_C.exists():
            self.skipTest("no kernel source")
        src = KERNEL_LOG_C.read_text()
        self.assertIn("#define LOADER_LOG_SIZE (1536 * 1024)", src)
        self.assertIn("char     loader_log[LOADER_LOG_SIZE];", src)
        self.assertEqual(1536 * 1024, LOG_MAX)

    def test_the_stub_hands_over_the_physical_address_and_length_of_the_log_in_x0_and_x1(self):
        if not KERNEL_LOG_C.exists():
            self.skipTest("no kernel source")
        src = KERNEL_LOG_C.read_text()
        self.assertRegex(src, r"loader_jump\(")
        i = src.index("loader_jump(")
        self.assertIn("loader_log_len", src[i:i + 6000], "loader_jump passes the log length")


# ------------------------------------------------------------------------------------------------------------------ Build
@unittest.skipUnless((B62 / "build.json").exists(), "NAT-062 build-001 is not present")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads((B62 / "build.json").read_text())

    @source_pin
    def test_the_build_record_pins_the_sources_of_this_directory(self):
        want = {f: sha((HERE / f).read_bytes()) for f in ("patch_run62.py", "build.py")}
        want.update({f: sha((SRC / f).read_bytes()) for f in ("glue62.h", "glue62_impl.h")})
        self.assertEqual(self.rec["nat062_sources"], want, "the image was built from the committed files")

    def test_two_builds_gave_the_same_image(self):
        if not (B62B / "build.json").exists():
            self.skipTest("no second build")
        b = json.loads((B62B / "build.json").read_text())
        self.assertEqual(self.rec["images"], b["images"])
        self.assertEqual(self.rec["image_payloads"], b["image_payloads"])
        self.assertEqual(self.rec["nat062_sources"], b["nat062_sources"])

    def test_the_package_pins_the_recovery_image_and_the_payload(self):
        pkg = json.loads((PKG62 / "package.json").read_text())
        p = pkg["images"][IMAGE]
        self.assertEqual(sorted(pkg["images"]), [IMAGE])
        self.assertTrue(pkg["flashed"] is False and pkg["kind"] == "host-test" and pkg["device_used"] is False)
        self.assertEqual(p["payload_sha256"], self.rec["image_payloads"][IMAGE]["sha256"])
        self.assertEqual(p["payload_bytes"], self.rec["image_payloads"][IMAGE]["bytes"])
        self.assertEqual(p["loader_image_sha256"], self.rec["images"][IMAGE]["sha256"])
        rec = PKG62 / IMAGE / "recovery.img"
        if rec.exists():
            self.assertEqual(sha(rec.read_bytes()), p["recovery_sha256"])
            self.assertEqual(rec.stat().st_size, 100663296)
        pay = B62 / IMAGE / "Image.payload"
        if pay.exists():
            self.assertEqual(sha(pay.read_bytes()), p["payload_sha256"])

    def test_the_payload_inside_the_image_is_the_command_line_patched_one(self):
        pay = B62 / IMAGE / "Image.payload"
        fixed = B62 / IMAGE / "payload.adt8.bin"
        if not (pay.exists() and fixed.exists()):
            self.skipTest("no payload files")
        blob, xnu = pay.read_bytes(), fixed.read_bytes()
        self.assertEqual(blob.count(xnu), 1, "the patched XNU payload is embedded once")
        self.assertIn(b"loader_return_after=8", blob)
        self.assertEqual(blob.count(b"nat_attempt=NAT020-83s"), 0, "the old command-line tag is gone (the loader's own log text \"NAT020-83s: ...\" is not the command line)")
        self.assertEqual(blob.count(b"nat_attempt=NAT062-run"), 1)


if __name__ == "__main__":
    unittest.main()
