#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-065 host tests, first half: the build of loader-diag-xnu-md0-usb (stage-0 ramdisk for rd=md0) and its outputs. Evidence kind: host-test.
Nothing here talks to a phone. What it shows is what the built bytes contain and what the loader's own code (adt_patch.c, compiled for the host) does
with them; it does not show what the kernel does with the ramdisk (that is the native run's question).

    <venv with capstone, pyusb, unicorn>/bin/python -W ignore -I docs/procedures/nat-065/test_nat065.py        (about 5 s with the C compiler and unicorn present)

Layers (each skips itself, and says why, when what it needs is missing):
  Inputs      the pinned NAT-020 inputs are the ones build.py pins; the probe differs from the pinned sweet-init.S in the documented way.
  Build       two builds of the same sources give identical hashes; the build record carries every input; the command line is exactly the expected one.
  Payload     the NAT-065 payload against the NAT-062 one, segment by segment and ADT node by ADT node: only the ramdisk segment, the RAMDisk property and the
              header fields that follow from them differ; adt_size is a multiple of 8 without NAT-022's fix; the loader-only Image differs from NAT-062's
              in the boot-id immediates only.
  Loader      adt_patch.c (the loader's own code) compiled for the host, run on the ADT of the built payload: the RAMDisk property is rebased by win_base - phys_base
              and nothing else changes; the loader's layout arithmetic (copied from loader.c by an anchored read, which fails when loader.c changes) puts the
              ramdisk range below the ADT and boot_args, outside every other segment, 16 KiB aligned, at the virtual address the kernel's ml_static_ptovirt
              maps back to the segment's own.
  Rebuild     the shipped sources (build.py, src/probe-init.S) rebuild the shipped ramdisk and payload byte for byte; a payload that is not the pinned one is refused.
  Ramdisk     the init (built from src/probe-init.S here, not taken from the build) is a static ad-hoc-signed arm64 Mach-O whose code-directory page hashes match its
              pages; its instructions run in unicorn against a fake syscall table (open, write, getpid, select, exit): exit status 81 for PID 1, 96 without a
              console, a 1 s select, 16-byte aligned SP at every system call, one file descriptor for every write, no mount.
  Package     the RECOVERY candidate carries Image.payload at offset 2048; its hashes are the ones the driver pins."""
import ctypes, hashlib, importlib.util, json, os, re, shutil, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
IMAGE = "loader-diag-xnu-md0-usb"
IMAGE62 = "loader-diag-xnu-run-usb"
B3 = ROOT / "artifacts/nat-020/build-003"
BUILD1, BUILD2 = ROOT / "artifacts/nat-065/build-001", ROOT / "artifacts/nat-065/build-002"
PACKAGE = ROOT / "artifacts/nat-065/package-001"
BUILD62 = ROOT / "artifacts/nat-062/build-001"
WINDOW_REPORT = B3 / "window-check/report.json"
SCRATCH = ROOT / "artifacts/nat-065/tmp"
CMD_OFF, CMD_LEN, SEG_TABLE = 0x48, 608, 0x2a8
LOADER_IMAGE_BYTES = 307200
EXPECTED_CMDLINE = ("rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT065-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v "
                    "loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1")
PAGE_16K = 0x4000
source_pin = unittest.skipIf(os.environ.get("NAT065_BEHAVIOUR_ONLY") == "1", "source-text pin (skipped in the behavioural mutation pass)")
BUILD_PY = Path(os.environ.get("NAT065_BUILD") or HERE / "build.py")
PROBE_S = Path(os.environ.get("NAT065_PROBE") or HERE / "src/probe-init.S")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fnv1a64(s):
    h = 0xcbf29ce484222325
    for c in s.encode():
        h = ((h ^ c) * 0x100000001b3) & (2**64 - 1)
    return h


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def header(b):
    magic, ver, nsegs = struct.unpack_from("<8sII", b, 0)
    virt_base, entry, adt_off, adt_size, kend, phys_base, mem_size = struct.unpack_from("<7Q", b, 0x10)
    segs = [struct.unpack_from("<4Q", b, SEG_TABLE + 32 * i) for i in range(nsegs)]
    return dict(magic=magic, version=ver, nsegs=nsegs, virt_base=virt_base, entry=entry, adt_off=adt_off, adt_size=adt_size, kernel_end=kend,
                phys_base=phys_base, mem_size=mem_size, cmdline=b[CMD_OFF:CMD_OFF + CMD_LEN].split(b"\0")[0].decode(), segs=segs)


def scratch(prefix):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))


def build_probe_bytes():
    """The ramdisk built from PROBE_S exactly as build.py builds it (clang -target arm64-apple-ios16.0 + the pinned mkinit.py); None without clang."""
    cc = shutil.which("clang")
    if not cc:
        return None
    work = scratch("probe-")
    try:
        for argv in ([cc, "-target", "arm64-apple-ios16.0", "-c", str(PROBE_S), "-o", str(work / "p.o")],
                     [sys.executable, "-I", str(B3 / "source/tools/e1s/mkinit.py"), str(work / "p.o"), str(work / "init")]):
            r = subprocess.run(argv, capture_output=True, text=True)
            if r.returncode:
                raise AssertionError("probe build failed (%d): %s" % (r.returncode, r.stderr[-600:]))
        return (work / "init").read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def payload_of(build, name=IMAGE):
    d = (build / name / "Image.payload").read_bytes()
    return d[LOADER_IMAGE_BYTES:]


def adt_props(adt):
    """{node path: [(name, value bytes)]} of an Apple device tree (node: u32 nprops, u32 nchildren, props of 32-byte name + u32 len + padded value)."""
    out = {}

    def node(off, path):
        nprops, nchild = struct.unpack_from("<II", adt, off)
        off += 8
        props = []
        for _ in range(nprops):
            name = adt[off:off + 32].split(b"\0")[0].decode()
            ln = struct.unpack_from("<I", adt, off + 32)[0] & 0x7fffffff
            props.append((name, bytes(adt[off + 36:off + 36 + ln])))
            off += 36 + ((ln + 3) & ~3)
        nm = dict(props).get("name", b"").split(b"\0")[0].decode()
        here = path + "/" + nm if path else "/"
        out[here] = props
        for _ in range(nchild):
            off = node(off, here)
        return off

    node(0, "")
    return out


needs_build = unittest.skipUnless((BUILD1 / "build.json").exists() and (BUILD2 / "build.json").exists() and (B3 / "payload.bin").exists(),
                                  "artifacts/nat-065/build-001/-002 or the NAT-020 build-003 inputs are not present")
needs_62 = unittest.skipUnless((BUILD62 / IMAGE62 / "Image.payload").exists(), "artifacts/nat-062/build-001 is not present")


# ------------------------------------------------------------------------------------------------------------------ Inputs
class Inputs(unittest.TestCase):
    @needs_build
    def test_the_nat020_inputs_are_the_pinned_ones(self):
        b = load(BUILD_PY, "nat065_build_pins")
        self.assertEqual(sorted(b.PIN), ["e1s.adt", "kernel.no-storage", "payload.bin", "source/tools/e1s/mkinit.py", "source/tools/e1s/sweet-init.S",
                                         "source/tools/e1s/xnu/mkpayload.py"])
        for rel, want in b.PIN.items():
            self.assertEqual(sha((B3 / rel).read_bytes()), want, rel)

    @needs_build
    def test_the_probe_differs_from_sweet_init_only_in_the_documented_way(self):
        s = (B3 / "source/tools/e1s/sweet-init.S").read_text()
        p = re.sub(r"/\*.*?\*/", "", PROBE_S.read_text(), flags=re.S)           # the comments name what is gone; only the code counts
        for gone in ("SYS_mount", "/dev/md1", "type_apfs", "five_sec"):
            self.assertIn(gone, s, "the pinned sweet-init.S has " + gone)
        for gone in ("SYS_mount", "/dev/md1", "type_apfs", "five_sec", "MNT_RDONLY", "SYS_sync"):
            self.assertNotIn(gone, p, gone)
        self.assertIn("#define SYS_exit\t1", p)
        self.assertIn("mov\tx0, #0x60", p)                       # no console: exit status 96
        self.assertIn("add\tx0, x20, #0x50", p)                  # 0x50 + PID
        self.assertRegex(p, r"one_sec:\n\t\.quad\t1\b[^\n]*\n\t\.quad\t0\b")                # a 1 s select
        self.assertEqual(p.count("svc\t#0x80"), 6)               # open, getpid, select, exit, the no-console exit, the shared write
        self.assertEqual(p.count("/dev/console"), 1)
        # what is kept verbatim: the banner, the console path, the stack alignment prologue
        for kept in ('"\\n*** SWEET userspace: init running as PID "', '.asciz\t"/dev/console"', "and\tx9, x9, #~15"):
            self.assertIn(kept, s)
            self.assertIn(kept, p)


# ------------------------------------------------------------------------------------------------------------------ Build
@needs_build
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b1 = json.loads((BUILD1 / "build.json").read_text())
        cls.b2 = json.loads((BUILD2 / "build.json").read_text())

    def test_two_builds_give_identical_hashes(self):
        for rel in ("Image", "Image.payload", "probe-init"):
            self.assertEqual(sha((BUILD1 / IMAGE / rel).read_bytes()), sha((BUILD2 / IMAGE / rel).read_bytes()), rel)
        for key in ("images", "image_payloads", "nat065_sources", "nat065_probe_init", "nat065_payload"):
            self.assertEqual(self.b1[key], self.b2[key], key)

    def test_the_build_record_pins_every_input(self):
        b = self.b1
        self.assertEqual(sorted(b["images"]), [IMAGE])
        self.assertTrue(b["device_used"] is False and b["flashed"] is False and b["kind"] == "host-test")
        loader = load(BUILD_PY, "nat065_build_rec")
        self.assertEqual(b["nat065_pins"], loader.PIN)
        self.assertEqual(b["nat065_sources"], {"build.py": sha((HERE / "build.py").read_bytes()), "src/probe-init.S": sha((HERE / "src/probe-init.S").read_bytes())})
        self.assertIn("clang", b["nat065_tools"]["clang"].lower())
        self.assertEqual(b["nat065_tools"]["clang_target"], "arm64-apple-ios16.0")
        probe = (BUILD1 / IMAGE / "probe-init").read_bytes()
        self.assertEqual((b["nat065_probe_init"]["sha256"], b["nat065_probe_init"]["bytes"]), (sha(probe), len(probe)))
        self.assertEqual(b["payload_fixes"][IMAGE]["ramdisk_sha256"], sha(probe))
        self.assertEqual(b["payload_fixes"][IMAGE]["nat022_adt_size_fix"], "not applied (adt_size is already a multiple of 8)")
        pl = payload_of(BUILD1)
        self.assertEqual(b["nat065_payload"]["sha256"], sha(pl))
        self.assertEqual(b["payload_fixes"][IMAGE]["fixed_sha256"], sha(pl))
        self.assertEqual(b["payload_fixes"][IMAGE]["base_payload_sha256"], sha((B3 / "payload.bin").read_bytes()))

    def test_the_command_line_is_exactly_the_expected_one(self):
        h = header(payload_of(BUILD1))
        self.assertEqual(h["cmdline"], EXPECTED_CMDLINE)
        self.assertLess(len(h["cmdline"]), 256, "BOOT_LINE_LENGTH")
        args = h["cmdline"].split()
        self.assertEqual(args[0], "rd=md0")
        for zero in ("e1sufs=0", "e1sufs_probe=0", "ufsrw=0", "ufs_write=0", "sweethw=0"):
            self.assertEqual(args.count(zero), 1, zero)
        self.assertEqual([a for a in args if a.startswith("loader_return_after")], ["loader_return_after=8"])
        self.assertEqual(sum(a in ("launchdsuffix=release", "cs_enforcement_disable=1") for a in args), 2)
        self.assertNotIn("e1sufs=1", args)
        # the field is one NUL-padded string
        raw = payload_of(BUILD1)[CMD_OFF:CMD_OFF + CMD_LEN]
        self.assertEqual(raw.rstrip(b"\0"), EXPECTED_CMDLINE.encode())

    def test_the_nat020_cmdline_builder_refuses_what_it_does_not_expect(self):
        b = load(BUILD_PY, "nat065_build_cmd")
        good = (B3 / "payload.bin").read_bytes()[CMD_OFF:CMD_OFF + CMD_LEN]
        self.assertEqual(b.make_cmdline(good), EXPECTED_CMDLINE)
        for bad in (good.replace(b"rd=md0 ", b"rd=md1 "), good.replace(b"NAT020-83s", b"NAT062-run"), good.rstrip(b"\0") + b" launchdsuffix=x",
                    good.rstrip(b"\0") + b"\0junk", good.replace(b"-v", b"-v " + b"x" * 120)):
            bad = bad.ljust(CMD_LEN, b"\0")[:CMD_LEN]
            with self.assertRaises(SystemExit, msg=bad[:60]):
                b.make_cmdline(bad)


# ------------------------------------------------------------------------------------------------------------------ Rebuild
@needs_build
@unittest.skipUnless(shutil.which("clang"), "no clang")
class Rebuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load(BUILD_PY, "nat065_build_rebuild")
        cls.data = (B3 / "payload.bin").read_bytes()

    def test_the_sources_rebuild_the_shipped_ramdisk_and_payload_byte_for_byte(self):
        payload, info = self.b.build_payload65(self.data)
        shipped = payload_of(BUILD1)
        self.assertEqual(sha(payload), sha(shipped))
        self.assertEqual(payload, shipped)
        self.assertEqual(self.b.LAST["probe"], (BUILD1 / IMAGE / "probe-init").read_bytes())
        self.assertEqual((info["cmdline"], info["adt_size"], info["adt_off"] % 8, info["ramdisk_bytes"]), (EXPECTED_CMDLINE, 14008, 0, 16635))
        self.assertEqual(info["ramdisk_sha256"], sha(self.b.LAST["probe"]))
        self.assertEqual(info["base_payload_sha256"], sha(self.data))

    def test_a_payload_or_an_input_that_is_not_the_pinned_one_is_refused(self):
        bad = bytearray(self.data)
        bad[-1] ^= 1
        with self.assertRaises(SystemExit):
            self.b.build_payload65(bytes(bad))
        saved = dict(self.b.PIN)
        try:
            for key in saved:
                self.b.PIN[key] = "0" * 64
                with self.assertRaises(SystemExit, msg=key):
                    self.b.build_payload65(self.data)
                self.b.PIN[key] = saved[key]
        finally:
            self.b.PIN.clear()
            self.b.PIN.update(saved)

    def test_the_shipped_ramdisk_is_the_build_of_the_shipped_source(self):
        self.assertEqual(build_probe_bytes(), (BUILD1 / IMAGE / "probe-init").read_bytes())


# ------------------------------------------------------------------------------------------------------------------ Payload
@needs_build
@needs_62
class Payload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p62 = payload_of(BUILD62, IMAGE62)
        cls.p65 = payload_of(BUILD1)
        cls.h62, cls.h65 = header(cls.p62), header(cls.p65)
        cls.probe = (BUILD1 / IMAGE / "probe-init").read_bytes()

    def test_the_header_differs_only_by_the_ramdisk_segment_and_what_follows_from_it(self):
        a, b = self.h62, self.h65
        for k in ("magic", "version", "virt_base", "entry", "phys_base", "mem_size"):
            self.assertEqual(a[k], b[k], k)
        self.assertEqual(b["nsegs"], a["nsegs"] + 1)
        vmsize = (len(self.probe) + PAGE_16K - 1) & ~(PAGE_16K - 1)
        self.assertEqual(vmsize, 0x8000)
        self.assertEqual(b["kernel_end"], a["kernel_end"] + vmsize)
        # the segment table grew by one 32-byte entry: every file offset moved by 32
        for s62, s65 in zip(a["segs"], b["segs"][:-1]):
            self.assertEqual(s62[:2], s65[:2])
            self.assertEqual(s62[3], s65[3])
            self.assertEqual(s65[2], s62[2] + 32)
        va, sz, off, fsz = b["segs"][-1]
        self.assertEqual((va, sz, fsz), (a["kernel_end"], vmsize, len(self.probe)))
        self.assertEqual(va % PAGE_16K, 0)
        self.assertEqual(self.p65[off:off + fsz], self.probe)
        self.assertEqual(self.p65[off + fsz:b["adt_off"]], bytes(b["adt_off"] - off - fsz), "only zero padding between the ramdisk and the ADT")
        # nothing overlaps the new segment in the file; the ADT follows it
        for s in b["segs"][:-1]:
            self.assertTrue(s[2] + s[3] <= off or s[2] >= off + fsz)
        self.assertGreaterEqual(b["adt_off"], off + fsz)

    def test_every_kernel_segment_is_byte_identical(self):
        for s62, s65 in zip(self.h62["segs"], self.h65["segs"][:-1]):
            self.assertEqual(self.p62[s62[2]:s62[2] + s62[3]], self.p65[s65[2]:s65[2] + s65[3]])

    def test_the_adt_differs_by_exactly_one_property_in_chosen_memory_map(self):
        a62 = self.p62[self.h62["adt_off"]:self.h62["adt_off"] + self.h62["adt_size"]]
        a65 = self.p65[self.h65["adt_off"]:self.h65["adt_off"] + self.h65["adt_size"]]
        n62, n65 = adt_props(a62), adt_props(a65)
        self.assertEqual(sorted(n62), sorted(n65))
        changed = [k for k in n62 if n62[k] != n65[k]]
        self.assertEqual(changed, ["//chosen/memory-map"] if "//chosen/memory-map" in n62 else changed)
        self.assertEqual(len(changed), 1)
        key = changed[0]
        self.assertTrue(key.endswith("chosen/memory-map"), key)
        p62, p65 = dict(n62[key]), dict(n65[key])
        self.assertNotIn("RAMDisk", p62)
        self.assertEqual({k: v for k, v in p65.items() if k != "RAMDisk"}, p62)
        self.assertEqual(len(n65[key]), len(n62[key]) + 1)
        phys, size = struct.unpack("<QQ", p65["RAMDisk"])
        # the build-time value: phys_base + (ramdisk va - virt_base), size = the 16 KiB-rounded segment size
        va, vmsize = self.h65["segs"][-1][:2]
        self.assertEqual((phys, size), (self.h65["phys_base"] + (va - self.h65["virt_base"]), vmsize))
        self.assertEqual(len(p65["RAMDisk"]), 16)

    def test_adt_size_is_a_multiple_of_8_without_nat022s_fix_and_52_bytes_larger_than_the_raw_adt(self):
        raw = (B3 / "e1s.adt").read_bytes()
        self.assertEqual(self.h65["adt_size"] - len(raw), 52)
        self.assertEqual(self.h65["adt_size"] % 8, 0)
        self.assertEqual(self.h65["adt_off"] % 8, 0)
        self.assertEqual(self.h62["adt_size"], len(raw) + 4, "NAT-062 carried the NAT-022 fix")
        fix = load(PROC / "nat-022/fix_payload.py", "nat065_fix22")
        with self.assertRaises(SystemExit):
            fix.fix(self.p65)           # the NAT-022 fix refuses this payload: nothing to fix

    def test_the_adt_is_the_one_the_nat063_run_used_apart_from_the_property(self):
        raw = (B3 / "e1s.adt").read_bytes()
        a65 = self.p65[self.h65["adt_off"]:self.h65["adt_off"] + self.h65["adt_size"]]
        self.assertEqual(adt_props(raw).keys(), adt_props(a65).keys())
        for k, props in adt_props(raw).items():
            got = [kv for kv in adt_props(a65)[k] if kv[0] != "RAMDisk"]
            self.assertEqual(got, props, k)

    def test_the_loader_image_differs_from_nat062s_in_the_boot_id_immediates_only(self):
        a = (BUILD62 / IMAGE62 / "Image").read_bytes()
        b = (BUILD1 / IMAGE / "Image").read_bytes()
        self.assertEqual((len(a), len(b)), (LOADER_IMAGE_BYTES, LOADER_IMAGE_BYTES))
        words = sorted({i & ~3 for i in range(len(a)) if a[i] != b[i]})
        self.assertEqual(len(words), 6, [hex(w) for w in words])
        self.assertTrue(all(0xf000 <= w < 0xf800 for w in words), "all in the one function that builds the boot id: %s" % [hex(w) for w in words])

        def chunks(name):
            h = fnv1a64(name)
            fnv = {(h >> (16 * i)) & 0xffff for i in range(4)}
            tag = {ord(name[k]) | ord(name[k + 1]) << 8 for k in (15, 17)}          # "-r","un" / "-m","d0": the tail of the name the compiler folded into immediates
            return fnv | tag
        got62, got65 = set(), set()
        for w in words:
            x, y = struct.unpack_from("<I", a, w)[0], struct.unpack_from("<I", b, w)[0]
            self.assertIn(x & 0x7f800000, (0x52800000, 0x72800000), "MOVZ/MOVK at %#x" % w)     # MOVZ and MOVK, 32- or 64-bit
            self.assertEqual(x & ~(0xffff << 5), y & ~(0xffff << 5), "same opcode, shift and register at %#x" % w)
            got62.add((x >> 5) & 0xffff)
            got65.add((y >> 5) & 0xffff)
        self.assertEqual(got62, chunks(IMAGE62))
        self.assertEqual(got65, chunks(IMAGE))
        # the Image.payload is the loader followed by exactly this payload
        pl = (BUILD1 / IMAGE / "Image.payload").read_bytes()
        head = bytearray(pl[:LOADER_IMAGE_BYTES])
        self.assertEqual(struct.unpack_from("<Q", head, 16)[0], len(pl), "the Image header's image_size covers the payload")
        head[16:24] = b[16:24]
        self.assertEqual(bytes(head), b, "the Image.payload begins with the loader Image except for its image_size field")
        self.assertEqual(pl[LOADER_IMAGE_BYTES:], self.p65)


# ------------------------------------------------------------------------------------------------------------------ Loader
HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "adt_patch.h"
int main(int argc, char **argv) {
	FILE *f = fopen(argv[1], "rb");
	fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
	uint8_t *buf = aligned_alloc(16, ((size_t)n + 15) & ~15ul);
	if (fread(buf, 1, n, f) != (size_t)n) return 99;
	fclose(f);
	long long delta = strtoll(argv[3], 0, 0);
	int rc = adt_rebase_ramdisk((uintptr_t)buf, (uint64_t)(argc > 4 ? strtoull(argv[4], 0, 0) : (uint64_t)n), delta);
	f = fopen(argv[2], "wb"); fwrite(buf, 1, n, f); fclose(f);
	printf("%d\n", rc);
	free(buf);
	return 0;
}
"""


@needs_build
class Loader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("clang") or shutil.which("cc")
        if not cc:
            raise unittest.SkipTest("no C compiler")
        cls.tmp = scratch("loader-")
        src = BUILD1 / IMAGE / "source/shim/e1s-xnu"
        cls.src = src
        (cls.tmp / "h.c").write_text(HARNESS)
        cls.exe = cls.tmp / "h"
        r = subprocess.run([cc, "-std=gnu11", "-O1", "-g", "-Wall", "-fsanitize=undefined,address", "-fno-sanitize-recover=all", "-I", str(src),
                            str(cls.tmp / "h.c"), str(src / "adt_patch.c"), "-o", str(cls.exe)], capture_output=True, text=True)
        if r.returncode:
            raise unittest.SkipTest("harness build failed: " + r.stderr[-400:])
        cls.p65 = payload_of(BUILD1)
        cls.h = header(cls.p65)
        cls.adt = cls.p65[cls.h["adt_off"]:cls.h["adt_off"] + cls.h["adt_size"]]
        cls.win = json.loads(WINDOW_REPORT.read_text())["scenarios"]["measured-initrd"]["result"]["window"] if WINDOW_REPORT.exists() else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def rebase(self, adt, delta, size=None, name="in"):
        i, o = self.tmp / (name + ".adt"), self.tmp / (name + ".out")
        i.write_bytes(adt)
        args = [str(self.exe), str(i), str(o), str(delta)] + ([str(size)] if size is not None else [])
        r = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        return int(r.stdout.split()[-1]), o.read_bytes()

    def ramdisk_prop(self, adt):
        for k, props in adt_props(adt).items():
            for n, v in props:
                if n == "RAMDisk":
                    return struct.unpack("<QQ", v)
        return None

    def test_the_loaders_rebase_moves_the_property_by_win_base_minus_phys_base_and_changes_nothing_else(self):
        win = int(self.win["base"], 16) if self.win else 0x9de400000
        delta = win - self.h["phys_base"]
        rc, out = self.rebase(self.adt, delta)
        self.assertEqual(rc, 0)
        phys0, size0 = self.ramdisk_prop(self.adt)
        phys1, size1 = self.ramdisk_prop(out)
        self.assertEqual((phys1, size1), (phys0 + delta, size0))
        va, vmsize = self.h["segs"][-1][:2]
        self.assertEqual(phys1, win + (va - self.h["virt_base"]))
        diff = [i for i in range(len(out)) if out[i] != self.adt[i]]
        self.assertTrue(diff and all(self.adt.find(b"RAMDisk\0") + 36 <= i < self.adt.find(b"RAMDisk\0") + 36 + 8 for i in diff), diff[:10])

    def test_negative_and_zero_deltas_and_the_other_windows_of_the_dtb(self):
        for win in (self.h["phys_base"], 0x80000000, 0x980000000, 0x9de400000, 0xbde400000 - 0x20000000):
            rc, out = self.rebase(self.adt, win - self.h["phys_base"], name="w%x" % win)
            self.assertEqual(rc, 0)
            va, _ = self.h["segs"][-1][:2]
            self.assertEqual(self.ramdisk_prop(out)[0], win + (va - self.h["virt_base"]), hex(win))

    def test_without_the_property_the_loader_finds_nothing_to_rebase(self):
        """NAT-020..NAT-063 payloads had no RAMDisk property: the branch this image adds never ran on the phone."""
        p62 = payload_of(BUILD62, IMAGE62) if (BUILD62 / IMAGE62 / "Image.payload").exists() else None
        if p62 is None:
            self.skipTest("NAT-062 build not present")
        h = header(p62)
        adt = p62[h["adt_off"]:h["adt_off"] + h["adt_size"]]
        rc, out = self.rebase(adt, 0x93e400000, name="p62")
        self.assertEqual(rc, 0)
        self.assertEqual(out, adt)

    def test_a_malformed_property_is_refused_and_not_written(self):
        adt = bytearray(self.adt)
        i = adt.find(b"RAMDisk\0") + 32
        for ln in (8, 0x80000010, 24):
            bad = bytearray(adt)
            struct.pack_into("<I", bad, i, ln)
            rc, out = self.rebase(bytes(bad), 0x1000, name="bad%x" % ln)
            self.assertEqual(rc, -1, hex(ln))
            self.assertEqual(out[i + 4:i + 12], bytes(bad[i + 4:i + 12]), "the value is not written when the length is wrong")
        rc, _ = self.rebase(bytes(adt[:200]), 0x1000, name="short")
        self.assertEqual(rc, -1)

    @source_pin
    def test_the_layout_arithmetic_is_the_one_in_loader_c_and_puts_the_ramdisk_where_the_kernel_will_look(self):
        text = (self.src / "loader.c").read_text()
        for anchor in ("uintptr_t kernel_end = win_base + (p->kernel_end - p->virt_base);",
                       "uintptr_t dst = win_base + (s->vmaddr - p->virt_base);",
                       "uintptr_t adt_pa = kernel_end;",
                       "uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1);",
                       "copy(adt_pa, (uintptr_t)p + p->adt_off, p->adt_size);",
                       "adt_rebase_ramdisk(adt_pa, p->adt_size,",
                       "(int64_t)(win_base - p->phys_base)",
                       "ba->physBase = win_base;",
                       "ba->topOfKernelData = ba_pa + PAGE_16K;",
                       "ba->deviceTreeP = p->virt_base + (adt_pa - win_base);"):
            self.assertEqual(text.count(anchor), 1, anchor)
        self.assertIn("(p->adt_size & 7)", text, "the multiple-of-8 rule")
        h = self.h
        for win in (0x9de400000, 0x980000000, 0x80000000):
            kernel_end = win + (h["kernel_end"] - h["virt_base"])
            adt_pa = kernel_end
            ba_pa = (adt_pa + h["adt_size"] + PAGE_16K - 1) & ~(PAGE_16K - 1)
            dsts = [(win + (va - h["virt_base"]), win + (va - h["virt_base"]) + sz) for va, sz, _, _ in h["segs"]]
            for (a, b), (c, d) in zip(dsts, dsts[1:]):
                self.assertLessEqual(b, c, "segments overlap")
            rd_lo, rd_hi = dsts[-1]
            rc, out = self.rebase(self.adt, win - h["phys_base"], name="lay%x" % win)
            phys, size = self.ramdisk_prop(out)
            self.assertEqual(rc, 0)
            self.assertEqual(phys, rd_lo, "the rebased property is where the loader copies the segment")
            self.assertEqual((phys % PAGE_16K, size % PAGE_16K, phys % 4096), (0, 0, 0))
            self.assertEqual(rd_hi, kernel_end, "the ramdisk ends where the ADT begins")
            self.assertLessEqual(phys + size, adt_pa)
            self.assertLessEqual(adt_pa + h["adt_size"], ba_pa)
            self.assertLess(phys + size, ba_pa + PAGE_16K, "below topOfKernelData")
            self.assertGreaterEqual(phys, win)
            # ml_static_ptovirt(phys) = phys - gPhysBase + gVirtBase with gPhysBase = ba->physBase = win and gVirtBase = ba->virtBase = virt_base
            self.assertEqual(phys - win + h["virt_base"], h["segs"][-1][0])
            # md0 gets page counts: mdevadd(-1, ptovirt(phys) >> 12, size >> 12): the 4 KiB-page range lies inside the 16 KiB segment
            self.assertEqual((phys % 4096, size >> 12), (0, 8))
        if self.win:
            self.assertEqual(int(self.win["base"], 16), 0x9de400000, "the window measured from the real DTB (NAT-020 window-check)")
            self.assertGreaterEqual(int(self.win["size"], 16), h["mem_size"], "the window holds the 512 MiB the payload header declares")

    def test_the_ramdisk_and_the_adt_fit_inside_the_window_with_room_to_spare(self):
        h = self.h
        used = (h["kernel_end"] - h["virt_base"]) + h["adt_size"] + 2 * PAGE_16K
        self.assertLess(used, h["mem_size"] // 2, "the loader image of this payload leaves most of the 512 MiB for the kernel's own use")


# ------------------------------------------------------------------------------------------------------------------ Ramdisk
def macho_pages(img):
    """-> (code directory slots as sha256 bytes, codeLimit, entry pc) of the init; raises AssertionError when the layout is not mkinit.py's."""
    magic, cpu, _, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<8I", img, 0)
    assert (magic, cpu, ftype) == (0xfeedfacf, 0x0100000c, 2)
    off, sig, pc, segs = 32, None, None, {}
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", img, off)
        if cmd == 0x19:
            name = img[off + 8:off + 24].split(b"\0")[0].decode()
            segs[name] = struct.unpack_from("<QQQQ", img, off + 24)
        elif cmd == 5:
            pc = struct.unpack_from("<Q", img, off + 16 + 32 * 8)[0]
        elif cmd == 0x1d:
            sig = struct.unpack_from("<II", img, off + 8)
        off += size
    assert sig and pc is not None
    blob = img[sig[0]:sig[0] + sig[1]]
    assert struct.unpack_from(">I", blob, 0)[0] == 0xfade0cc0
    cd_off = struct.unpack_from(">I", blob, 12 + 4)[0]
    cd = blob[cd_off:]
    assert struct.unpack_from(">I", cd, 0)[0] == 0xfade0c02
    hash_off, _, nspecial, nslots, code_limit = struct.unpack_from(">5I", cd, 16)
    hashes = [cd[hash_off + 32 * i:hash_off + 32 * (i + 1)] for i in range(nslots)]
    return hashes, code_limit, pc, segs, nspecial


@needs_build
class Ramdisk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = build_probe_bytes() or (BUILD1 / IMAGE / "probe-init").read_bytes()

    def test_it_is_a_static_ad_hoc_signed_arm64_executable_whose_page_hashes_match(self):
        hashes, limit, pc, segs, nspecial = macho_pages(self.img)
        self.assertEqual(len(self.img), 16635)
        self.assertEqual((limit, nspecial, len(hashes)), (0x4000, 0, 4))
        for i, h in enumerate(hashes):
            self.assertEqual(h, hashlib.sha256(self.img[i * 4096:(i + 1) * 4096]).digest(), "page %d" % i)
        self.assertEqual(sorted(segs), ["__LINKEDIT", "__PAGEZERO", "__TEXT"])
        base, size = segs["__TEXT"][0], segs["__TEXT"][1]
        self.assertTrue(base <= pc < base + size, "entry inside __TEXT")
        self.assertEqual(pc, 0x100000400, "_start is the first instruction (a global _start at the beginning of __text)")

    def test_the_probe_ends_with_the_documented_exit_statuses(self):
        try:
            from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_INTR
            from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X16, UC_ARM64_REG_SP, UC_ARM64_REG_NZCV
        except Exception:
            self.skipTest("unicorn is not installed")
        base = 0x100000000

        def run(open_ok, pid):
            uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
            uc.mem_map(base, 0x4000)
            uc.mem_write(base, self.img[:0x4000])
            uc.mem_map(0x7f0000000, 0x10000)
            calls, out, state, sp_at_call = [], bytearray(), {"exit": None}, []

            def intr(uc, intno, ud):
                nr = uc.reg_read(UC_ARM64_REG_X16)
                x = [uc.reg_read(UC_ARM64_REG_X0 + i) for i in range(5)]
                sp_at_call.append(uc.reg_read(UC_ARM64_REG_SP))
                carry = False
                if nr == 5:
                    path, a = b"", x[0]
                    while uc.mem_read(a, 1) != b"\0":
                        path += bytes(uc.mem_read(a, 1))
                        a += 1
                    calls.append(("open", path.decode(), x[1]))
                    uc.reg_write(UC_ARM64_REG_X0, 3 if open_ok else 2)
                    carry = not open_ok
                elif nr == 4:
                    calls.append(("write", x[0]))
                    out.extend(uc.mem_read(x[1], x[2]))
                    uc.reg_write(UC_ARM64_REG_X0, x[2])
                elif nr == 20:
                    calls.append(("getpid",))
                    uc.reg_write(UC_ARM64_REG_X0, pid)
                elif nr == 93:
                    calls.append(("select", x[:4], struct.unpack("<QQ", bytes(uc.mem_read(x[4], 16)))))
                    uc.reg_write(UC_ARM64_REG_X0, 0)
                elif nr == 1:
                    calls.append(("exit", x[0]))
                    state["exit"] = x[0]
                    uc.emu_stop()
                else:
                    calls.append(("unexpected", nr))
                    uc.emu_stop()
                nz = uc.reg_read(UC_ARM64_REG_NZCV)
                uc.reg_write(UC_ARM64_REG_NZCV, (nz | (1 << 29)) if carry else (nz & ~(1 << 29)))

            uc.hook_add(UC_HOOK_INTR, intr)
            uc.reg_write(UC_ARM64_REG_SP, 0x7f0008000 + 8)       # deliberately not 16-aligned: the probe aligns it itself
            uc.emu_start(base + 0x400, 0, count=5000)
            self.assertTrue(sp_at_call and all(sp % 16 == 0 for sp in sp_at_call), "SP is 16-byte aligned at every system call: %s" % [hex(s) for s in sp_at_call])
            return calls, bytes(out), state["exit"]

        calls, out, status = run(True, 1)
        self.assertEqual(status, 81)
        self.assertEqual([c[1] for c in calls if c[0] == "write"], [3, 3, 3, 3], "every write goes to the descriptor open() returned")
        self.assertEqual([c[0] for c in calls], ["open", "write", "getpid", "write", "write", "select", "write", "exit"])
        self.assertEqual(calls[0], ("open", "/dev/console", 2))
        self.assertEqual(calls[5], ("select", [0, 0, 0, 0], (1, 0)))
        self.assertEqual(out, b"\n*** SWEET userspace: init running as PID 1 ***\nSWEET probe: done, exiting\n")
        self.assertFalse([c for c in calls if c[0] == "unexpected"])
        calls, out, status = run(False, 1)
        self.assertEqual((status, [c[0] for c in calls], out), (96, ["open", "exit"], b""))
        calls, out, status = run(True, 2)
        self.assertEqual(status, 82, "the exit status carries the PID")


# ------------------------------------------------------------------------------------------------------------------ Package
@needs_build
@unittest.skipUnless((PACKAGE / "package.json").exists(), "NAT-065 package-001 is not present")
class Package(unittest.TestCase):
    def test_the_candidate_carries_image_payload_at_2048_and_the_pins_are_the_package_record(self):
        pkg = json.loads((PACKAGE / "package.json").read_text())
        p = pkg["images"][IMAGE]
        self.assertEqual(sorted(pkg["images"]), [IMAGE])
        self.assertTrue(pkg["flashed"] is False and pkg["device_used"] is False and pkg["kind"] == "host-test")
        rec = (PACKAGE / IMAGE / "recovery.img").read_bytes()
        pl = (BUILD1 / IMAGE / "Image.payload").read_bytes()
        self.assertEqual((len(rec), p["recovery_bytes"]), (100663296, 100663296))
        self.assertEqual(sha(rec), p["recovery_sha256"])
        self.assertEqual(rec[2048:2048 + len(pl)], pl)
        self.assertEqual((sha(pl), len(pl), p["payload_offset"]), (p["payload_sha256"], p["payload_bytes"], 2048))
        self.assertEqual(p["loader_image_sha256"], sha((BUILD1 / IMAGE / "Image").read_bytes()))
        stock = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
        if stock.exists():
            st = stock.read_bytes()
            self.assertEqual(sha(st), pkg["stock_sha256"])
            self.assertEqual(len(st), len(rec))
            # the boot header before the payload is the stock one except the fields the NAT-006 builder rewrites for the new sizes:
            # kernel_size [8:12], ramdisk_size [16:20], the header's id digest [576:596], recovery_dtbo_offset [1636:1644]
            diff = [i for i in range(2048) if rec[i] != st[i]]
            allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(576, 596)) | set(range(1636, 1644))
            self.assertTrue(diff and set(diff) <= allowed, [i for i in diff if i not in allowed])
            self.assertEqual(struct.unpack_from("<I", rec, 8)[0], len(pl), "kernel_size is the packaged Image.payload")


if __name__ == "__main__":
    unittest.main()
