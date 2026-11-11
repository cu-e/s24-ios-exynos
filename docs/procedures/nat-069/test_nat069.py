#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-069 host tests: the image loader-diag-xnu-ne2-usb (NAT-067's image with the kernel's read-only display-pipeline dump switched on by the boot-arg e1sdisp=2),
its derived driver and its analyser including the reading of the `e1s-display:` lines. Evidence kind: host-test. Nothing here talks to a phone and nothing shows what
the display registers contain on the S24: the register readings in these tests are rendered from the pinned patch's own format strings, not measured.

    <venv with pyusb>/bin/python -W ignore -I docs/procedures/nat-069/test_nat069.py [Class ...]     (a few seconds; each layer skips itself without its artifacts)

Layers:
  Build      two builds give identical hashes; the record carries the changes; the command line is NAT-067's with the tag changed and ` e1sdisp=2` appended.
  Payload    against NAT-067's: the loader differs in five boot-id/name immediate words (six against NAT-065's), the payload only in the command-line field; ramdisk and kernel
             segments are NAT-067's.
  Kernel     the payload's kernel carries the boot-arg name and every format string of the pinned display patch; the patch's pipeline function only reads (no store, no call
             but ml_io_map / e1s_display_read / printf) and every offset it reads lies inside the window it mapped; bsd_init calls the probe.
  Package    the RECOVERY candidate carries Image.payload at offset 2048 and its pins are the ones the driver holds.
  Driver     session_nat069.py is what derive.py makes from session_nat067.py; its gates behave as the NAT-062 driver's on a temporary tree.
  Display    the analyser's reading of the display lines against text rendered from the pinned patch's format strings (every fork) and against the real NAT-068 log.
  Analyser   the NAT-065 reading under the new name: a boot of another image is not accepted, the real NAT-068 text is still probe-ran-to-exit."""
import hashlib, importlib.util, json, os, re, struct, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
IMAGE = "loader-diag-xnu-ne2-usb"
IMAGE67 = "loader-diag-xnu-ne1-usb"
IMAGE65 = "loader-diag-xnu-md0-usb"
B3 = ROOT / "artifacts/nat-020/build-003"
BUILD1 = Path(os.environ.get("NAT069_BUILD1") or ROOT / "artifacts/nat-069/build-001")
BUILD2 = Path(os.environ.get("NAT069_BUILD2") or ROOT / "artifacts/nat-069/build-002")
BUILD67 = ROOT / "artifacts/nat-067/build-001"
BUILD65 = ROOT / "artifacts/nat-065/build-001"
PACKAGE = ROOT / "artifacts/nat-069/package-001"
PATCHES = ROOT / "references/s24-port/xnu/e1s/patches"
DISPLAY_PATCH = Path(os.environ.get("NAT069_PATCH") or PATCHES / "0010-e1s-display.patch")
KERNEL = B3 / "kernel.no-storage"
NAT68_LOG = PROC / "nat-068" / "run-001-kernel-log.txt"
NAT68_RUN = ROOT / "artifacts/nat-068/run-001"
LOADER_IMAGE_BYTES = 307200
CMD_OFF, CMD_LEN = 0x48, 608
EXPECTED_CMDLINE = ("rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT069-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v "
                    "loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 e1sdisp=2")
NAT67_CMDLINE = EXPECTED_CMDLINE.replace("NAT069", "NAT067").replace(" e1sdisp=2", "")
BUILD_PY = Path(os.environ.get("NAT069_BUILD") or HERE / "build.py")
DERIVE_PY = Path(os.environ.get("NAT069_DERIVE") or HERE / "derive.py")
DRIVER_PY = Path(os.environ.get("NAT069_DRIVER") or HERE / "session_nat069.py")
ANALYZE_PY = Path(os.environ.get("NAT069_ANALYZE") or HERE / "analyze_nat069.py")


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


def payload_of(build, name):
    return (build / name / "Image.payload").read_bytes()[LOADER_IMAGE_BYTES:]


def macho_symbols(data):
    """[(address, name)] of the nlist_64 symbols of a 64-bit Mach-O, sorted by address (defined, in a section)."""
    magic, _cpu, _sub, _ft, ncmds, _sz, _fl, _res = struct.unpack_from("<8I", data, 0)
    assert magic == 0xfeedfacf
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x2:                                  # LC_SYMTAB
            symoff, nsyms, stroff, strsize = struct.unpack_from("<4I", data, off + 8)
            out = []
            for i in range(nsyms):
                strx, ntype, nsect, _desc, value = struct.unpack_from("<IBBHQ", data, symoff + 16 * i)
                if ntype & 0x0e == 0x0e and nsect and strx < strsize:
                    end = data.index(b"\0", stroff + strx)
                    out.append((value, data[stroff + strx:end].decode("ascii", "replace")))
            return sorted(out)
        off += size
    raise AssertionError("no LC_SYMTAB")


# ---- the pinned display patch: format strings, function bodies, windows --------------------------------------------------------------------------------------------
def patch_text():
    return DISPLAY_PATCH.read_text()


def patch_formats(text):
    """Every printf format string of the patch (adjacent literals joined, \\n unescaped), in source order."""
    out = []
    text = "\n".join(l[1:] if l.startswith("+") else l for l in text.splitlines())
    for m in re.finditer(r'printf\(((?:\s*"(?:[^"\\]|\\.)*"\s*)+)', text):
        lits = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
        out.append("".join(lits).replace("\\n", "\n"))
    return out


def function_body(text, name, prefix="+"):
    """The text of `name(...) { ... }` in the patch (added lines), braces balanced; prefix stripped."""
    lines = [l[1:] if l.startswith(prefix) else l for l in text.splitlines()]
    src = "\n".join(lines)
    i = src.index("\n%s(void)\n{" % name)
    j = src.index("{", i)
    depth, k = 0, j
    while True:
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1


def cfmt(fmt, *args):
    """The kernel's printf for the conversions the patch uses: %u, %s, %#x, %#llx (0 prints as 0)."""
    it = iter(args)

    def rep(m):
        v = next(it)
        spec = m.group(0)
        if spec.startswith("%#"):
            return "0" if v == 0 else hex(v)
        if spec == "%u":
            return str(v)
        if spec == "%s":
            return v
        raise AssertionError(spec)
    out = re.sub(r"%#?(?:ll)?[xus]", rep, fmt)
    try:
        next(it)
    except StopIteration:
        return out
    raise AssertionError("more arguments than conversions in %r" % fmt)


def fmt_with(formats, prefix):
    f = [x for x in formats if x.startswith(prefix)]
    assert len(f) == 1, (prefix, f)
    return f[0]


def render_display(sc, formats, stamp=49.0):
    """Kernel-log text of one scenario, rendered from the patch's own formats. sc: dict(fb=(w,h,depth,stride,phys,virt), words, decon=[(frames,global_con)], wins=[(con,start,end)],
    rdma=[(en,fmt,w,h,stride,addr)], dsim=[...], cannot_map=bool, cut_after=None)."""
    L = []
    fb = sc["fb"]
    L.append(cfmt(fmt_with(formats, "e1s-display: framebuffer %ux%u"), *fb).rstrip("\n"))
    for i in range(4):
        L.append(cfmt(fmt_with(formats, "e1s-display: fb[%u]"), i, sc["words"][i], "").rstrip("\n"))
    L.append(cfmt(fmt_with(formats, "e1s-display: framebuffer sample sum"), sc.get("sum", 0)).rstrip("\n"))
    if sc.get("mode", 2) < 2:
        return "\n".join("[%11.6f]: %s" % (stamp + 0.00001 * n, s) for n, s in enumerate(L))
    if sc.get("cannot_map"):
        L.append(fmt_with(formats, "e1s-display: cannot map the display registers").rstrip("\n"))
        return "\n".join("[%11.6f]: %s" % (stamp + 0.00001 * n, s) for n, s in enumerate(L))
    for i in range(4):
        frames, g = sc["decon"][i]
        L.append(cfmt(fmt_with(formats, "e1s-display: DECON%u version"), i, 0x40000, frames, g, " run" if g & 16 else " idle", " idle-status" if g & 32 else "", 0).rstrip("\n"))
    for i in range(4):
        con, start, end = sc["wins"][i]
        L.append(cfmt(fmt_with(formats, "e1s-display: DECON0 win%u"), i, con, " on" if con & 1 else " off", start[0], start[1], end[0], end[1], 0).rstrip("\n"))
    for i in range(4):
        en, f, w, h, stride, addr = sc["rdma"][i]
        L.append(cfmt(fmt_with(formats, "e1s-display: RDMA%u enable"), i, en, " on" if en & 1 else " off", f, w, h, stride, addr).rstrip("\n"))
    for i in range(2):
        if i == 1 and sc.get("cannot_map_dsim1"):
            L.append(fmt_with(formats, "e1s-display: cannot map DSIM1").rstrip("\n"))
            continue
        v = sc["dsim"][i]
        L.append(cfmt(fmt_with(formats, "e1s-display: DSIM%u version"), i, 0x20, v, 0, 0, 0, 0, 0, 0).rstrip("\n"))
        L.append(cfmt(fmt_with(formats, "e1s-display: DSIM%u video"), i, v >> 24 & 1, v & 0x1fff, 0, 0, 0, 0, 0, 0, 0, 0).rstrip("\n"))
    L.append(cfmt(fmt_with(formats, "e1s-display: DCPHY0"), 1, 1, 1, 1).rstrip("\n"))
    L.append(cfmt(fmt_with(formats, "e1s-display: DPU_MIPI_PHY_CON"), 0x10).rstrip("\n"))
    if sc.get("cut_after") is not None:
        L = L[:sc["cut_after"]]
    return "\n".join("[%11.6f]: %s" % (stamp + 0.00001 * n, s) for n, s in enumerate(L))


FB = (1080, 2340, 32, 4320, 0xfa200000, 0xfffffff03ee80000)
IDLE = dict(fb=FB, words=[0xffffffff, 0xffffffff, 0, 0], sum=0x6fffffff9, decon=[(0, 0)] * 4, wins=[(0, (0, 0), (0, 0))] * 4, rdma=[(0, 0, 0, 0, 0, 0)] * 4, dsim=[0, 0])
RUN_FB = dict(IDLE, decon=[(7, 0x10), (0, 0), (0, 0), (0, 0)], wins=[(1, (0, 0), (1079, 2339))] + [(0, (0, 0), (0, 0))] * 3,
              rdma=[(1, 1, 1080, 2340, 4320, 0xfa200000)] + [(0, 0, 0, 0, 0, 0)] * 3, dsim=[1 << 24 | 2340, 0])


needs_build = unittest.skipUnless((BUILD1 / "build.json").exists() and (BUILD2 / "build.json").exists() and (BUILD67 / IMAGE67 / "Image.payload").exists()
                                  and (BUILD65 / IMAGE65 / "Image.payload").exists(), "artifacts/nat-069/build-001/-002 or the NAT-065/NAT-067 builds are not present")
needs_pkg = unittest.skipUnless((PACKAGE / "package.json").exists(), "artifacts/nat-069/package-001 is not present")
needs_patch = unittest.skipUnless(DISPLAY_PATCH.exists(), "the pinned e1s display patch is not present")


# ------------------------------------------------------------------------------------------------------------------ Build
@needs_build
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b1 = json.loads((BUILD1 / "build.json").read_text())
        cls.b2 = json.loads((BUILD2 / "build.json").read_text())
        cls.b = load(BUILD_PY, "nat069_build_under_test")

    def test_two_builds_give_identical_hashes(self):
        for rel in ("Image", "Image.payload", "probe-init"):
            self.assertEqual(sha((BUILD1 / IMAGE / rel).read_bytes()), sha((BUILD2 / IMAGE / rel).read_bytes()), rel)
        for key in ("images", "image_payloads", "nat065_sources", "nat065_probe_init", "nat065_payload", "nat069_sources", "nat069_changes"):
            self.assertEqual(self.b1[key], self.b2[key], key)

    def test_the_build_record_carries_the_changes_and_nat065s_pins(self):
        b = self.b1
        self.assertEqual(sorted(b["images"]), [IMAGE])
        self.assertTrue(b["device_used"] is False and b["flashed"] is False and b["kind"] == "host-test")
        self.assertEqual(b["nat069_changes"], {"image_name": IMAGE, "cmdline_tag": "nat_attempt=NAT069-md0", "cmdline_append": self.b.APPEND, "cmdline": EXPECTED_CMDLINE})
        self.assertEqual(b["nat069_sources"], {"build.py": sha((HERE / "build.py").read_bytes())})
        a = json.loads((BUILD65 / "build.json").read_text())
        self.assertEqual(b["nat065_pins"], a["nat065_pins"], "the inputs are the pinned NAT-020 ones, the same as NAT-065's")
        self.assertEqual(b["nat065_sources"], a["nat065_sources"], "NAT-065's build.py and probe source are the ones that built it")
        for k in ("sha256", "bytes"):
            self.assertEqual(b["nat065_probe_init"][k], a["nat065_probe_init"][k], "the ramdisk is NAT-065's, byte for byte")
        self.assertEqual(b["nat065_payload"]["cmdline"], EXPECTED_CMDLINE)

    def test_the_command_line_is_nat067s_with_a_new_tag_and_e1sdisp_2_appended(self):
        raw = payload_of(BUILD1, IMAGE)[CMD_OFF:CMD_OFF + CMD_LEN]
        self.assertEqual(raw.rstrip(b"\0"), EXPECTED_CMDLINE.encode(), "one NUL-padded string, exactly the expected text")
        self.assertLess(len(EXPECTED_CMDLINE), 256, "BOOT_LINE_LENGTH")
        old = payload_of(BUILD67, IMAGE67)[CMD_OFF:CMD_OFF + CMD_LEN].rstrip(b"\0").decode()
        self.assertEqual(old, NAT67_CMDLINE, "NAT-067's command line is the one NAT-068 ran")
        new, was = EXPECTED_CMDLINE.split(), old.split()
        self.assertEqual(new[:len(was)], [t.replace("NAT067", "NAT069") for t in was], "NAT-067's tokens in order, only the tag changed")
        self.assertEqual(new[len(was):], ["e1sdisp=2"])
        self.assertEqual(sum(t.startswith("e1sdisp") for t in new), 1)
        for keep in ("e1stouch=0", "e1sbattery=0", "cs_enforcement_disable=1", "launchdsuffix=release", "loader_return_after=8"):
            self.assertIn(keep, new, "the NAT-068 boot-args that made PID 1 run stay")

    def test_the_appended_text_is_nat067s_plus_e1sdisp(self):
        b67 = load(PROC / "nat-067" / "build.py", "nat069_b67")
        self.assertEqual(self.b.APPEND, b67.APPEND + " e1sdisp=2")
        self.assertEqual(self.b.APPEND_NAT067, b67.APPEND)

    def test_configure_hands_the_three_values_to_nat065s_build(self):
        self.assertEqual((self.b.NAME, self.b.NEW_TAG), (IMAGE, "nat_attempt=NAT069-md0"))
        self.b.configure()
        self.assertEqual((self.b.b65.NAME, self.b.b65.NEW_TAG, self.b.b65.APPEND), (IMAGE, "nat_attempt=NAT069-md0", self.b.APPEND))
        self.assertTrue(self.b.APPEND.endswith(" e1sdisp=2"))

    def test_the_build_refuses_a_command_line_that_already_has_the_new_boot_args(self):
        self.b.configure()
        good = (B3 / "payload.bin").read_bytes()[CMD_OFF:CMD_OFF + CMD_LEN]
        self.assertEqual(self.b.b65.make_cmdline(good), EXPECTED_CMDLINE)
        bad = (good.rstrip(b"\0") + b" launchdsuffix=x").ljust(CMD_LEN, b"\0")
        with self.assertRaises(SystemExit):
            self.b.b65.make_cmdline(bad)


# ------------------------------------------------------------------------------------------------------------------ Payload
@needs_build
class Payload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p67 = (BUILD67 / IMAGE67 / "Image.payload").read_bytes()
        cls.p65 = (BUILD65 / IMAGE65 / "Image.payload").read_bytes()
        cls.p69 = (BUILD1 / IMAGE / "Image.payload").read_bytes()
        cls.i67 = (BUILD67 / IMAGE67 / "Image").read_bytes()
        cls.i65 = (BUILD65 / IMAGE65 / "Image").read_bytes()
        cls.i69 = (BUILD1 / IMAGE / "Image").read_bytes()

    @staticmethod
    def chunks(name):
        h = fnv1a64(name)
        fnv = {(h >> (16 * i)) & 0xffff for i in range(4)}
        tag = {ord(name[k]) | ord(name[k + 1]) << 8 for k in (15, 17)}      # "-n","e2": the tail of the name the compiler folded into immediates
        return fnv | tag

    def immediates(self, a, b, nwords):
        words = sorted({i & ~3 for i in range(len(a)) if a[i] != b[i]})
        self.assertEqual(len(words), nwords, [hex(w) for w in words])
        self.assertTrue(all(0xf000 <= w < 0xf800 for w in words), [hex(w) for w in words])
        ga, gb = set(), set()
        for w in words:
            x, y = struct.unpack_from("<I", a, w)[0], struct.unpack_from("<I", b, w)[0]
            self.assertIn(x & 0x7f800000, (0x52800000, 0x72800000), "MOVZ/MOVK at %#x" % w)
            self.assertEqual(x & ~(0xffff << 5), y & ~(0xffff << 5), "same opcode, shift and register at %#x" % w)
            ga.add((x >> 5) & 0xffff)
            gb.add((y >> 5) & 0xffff)
        return ga, gb

    def test_the_loader_image_differs_from_nat067s_in_five_and_nat065s_in_six_immediate_words(self):
        self.assertEqual((len(self.i67), len(self.i69), len(self.i65)), (LOADER_IMAGE_BYTES,) * 3)
        ga, gb = self.immediates(self.i67, self.i69, 5)
        self.assertLessEqual(ga, self.chunks(IMAGE67))
        self.assertLessEqual(gb, self.chunks(IMAGE))
        ga, gb = self.immediates(self.i65, self.i69, 6)
        self.assertEqual(ga, self.chunks(IMAGE65))
        self.assertEqual(gb, self.chunks(IMAGE))
        self.assertEqual({len(IMAGE), len(IMAGE67), len(IMAGE65)}, {len(IMAGE)}, "the names have the same length, so nothing else in the loader moves")

    def test_image_payload_is_the_loader_followed_by_the_payload(self):
        pl = self.p69
        head = bytearray(pl[:LOADER_IMAGE_BYTES])
        self.assertEqual(struct.unpack_from("<Q", head, 16)[0], len(pl))
        head[16:24] = self.i69[16:24]
        self.assertEqual(bytes(head), self.i69)
        self.assertEqual(len(self.p67), len(pl))

    def test_the_payload_differs_from_nat067s_only_in_the_command_line_field(self):
        a, b = self.p67[LOADER_IMAGE_BYTES:], self.p69[LOADER_IMAGE_BYTES:]
        self.assertEqual(len(a), len(b))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertTrue(diff)
        self.assertTrue(all(CMD_OFF <= i < CMD_OFF + CMD_LEN for i in diff), "bytes outside the command-line field differ: %s" % [hex(i) for i in diff if not CMD_OFF <= i < CMD_OFF + CMD_LEN][:8])
        self.assertEqual(a[:CMD_OFF], b[:CMD_OFF], "the header before the field, including the segment table sizes, is NAT-067's")
        self.assertEqual(a[CMD_OFF + CMD_LEN:], b[CMD_OFF + CMD_LEN:], "every segment, the ADT and the ramdisk are NAT-067's")
        self.assertEqual(len(diff), 1 + len(" e1sdisp=2"), "one tag digit and the appended text")

    def test_the_ramdisk_is_nat067s(self):
        self.assertEqual((BUILD1 / IMAGE / "probe-init").read_bytes(), (BUILD67 / IMAGE67 / "probe-init").read_bytes())


# ------------------------------------------------------------------------------------------------------------------ Kernel
@needs_patch
class Kernel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = patch_text()
        cls.formats = patch_formats(cls.text)

    def test_the_patch_prints_the_formats_the_analyser_reads_and_the_payload_kernel_carries_them(self):
        ours = [f for f in self.formats if f.startswith("e1s-display: ")]
        self.assertEqual(len(ours), 13, "the patch has changed: re-read the analyser's regexes against it")
        pl = payload_of(BUILD1, IMAGE) if (BUILD1 / IMAGE / "Image.payload").exists() else None
        if pl is None:
            self.skipTest("artifacts/nat-069/build-001 is not present")
        for f in ours:
            self.assertIn(f.encode(), pl, "the payload kernel lacks %r (built without the display patch?)" % f)
        self.assertEqual(pl.count(b"e1sdisp\0"), 1)

    @unittest.skipUnless(KERNEL.exists(), "the NAT-020 kernel is not present")
    def test_the_kernel_symbols_include_the_probe_and_the_bsd_init_caller(self):
        names = {n for _, n in macho_symbols(KERNEL.read_bytes())}
        for need in ("_e1s_display_probe", "_bsd_init", "_ml_io_map", "_PE_parse_boot_argn"):
            self.assertIn(need, names)

    def test_bsd_init_calls_the_probe_once_and_the_mode_defaults_to_1(self):
        body = function_body(self.text, "e1s_display_probe")
        self.assertIn("uint32_t mode = 1;", body)
        self.assertIn('PE_parse_boot_argn("e1sdisp"', body)
        self.assertEqual(re.findall(r"if \(mode (==|>=) (\d)\)", body), [("==", "0"), (">=", "2")], "0 = off, >=2 = pipeline read")
        self.assertEqual(len(re.findall(r"^\+\s+e1s_display_probe\(\);", self.text, re.M)), 1, "one call in bsd_init")
        self.assertRegex(self.text, r"extern void e1s_display_probe\(void\);")

    def test_the_pipeline_function_only_reads(self):
        body = function_body(self.text, "e1s_display_pipeline")
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', body)
        code = re.sub(r"volatile uint32_t \*\w+( = \w+)?;", "", code)          # declarations only
        calls = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", code))
        self.assertEqual(calls - {"for", "if"}, {"ml_io_map", "e1s_display_read", "printf"}, "any other call could write")
        for ptr in ("decon", "win", "wincon", "dma", "dsim", "dphy", "ss", "d"):
            self.assertIsNone(re.search(r"\b%s\s*\[" % ptr, code), "%s is indexed directly in the pipeline function" % ptr)
            self.assertIsNone(re.search(r"\*\s*%s\b" % ptr, code), "%s is dereferenced directly" % ptr)
        flat = "\n".join(l[1:] if l.startswith("+") else l for l in self.text.splitlines())
        read = re.search(r"e1s_display_read\(volatile uint32_t \*base, uint32_t offset\)\n\{(.*?)\n\}", flat, re.S)
        self.assertEqual(read.group(1).strip(), "return base[offset / 4];", "the only access to a mapped window is one 32-bit load")

    def test_every_offset_the_pipeline_reads_lies_inside_the_window_it_mapped(self):
        t = "\n".join(l[1:] if l.startswith("+") else l for l in self.text.splitlines())
        macro = dict((m.group(1), int(m.group(2), 16)) for m in re.finditer(r"#define (E1S_\w+)\s+(0x[0-9a-fA-F]+)U?L?", t))
        windows = {"decon": ("E1S_DECON0_MAIN_SIZE", 4, ["E1S_DECON_VERSION", "E1S_DECON_FRAME_COUNT", "E1S_DECON_GLOBAL_CON", "E1S_DECON_OPMODE"], 0x1000),
                   "win": ("E1S_DECON0_WIN_SIZE", 16, ["E1S_WIN_START_POSITION", "E1S_WIN_END_POSITION", "E1S_WIN_SECURE_CON"], 0x1000),
                   "wincon": ("E1S_DECON0_WINCON_SIZE", 16, ["E1S_WINCON_ENABLE"], 0x1000),
                   "dma": ("E1S_DMA0_SIZE", 4, ["E1S_RDMA_ENABLE", "E1S_RDMA_IN_CTRL_0", "E1S_RDMA_SRC_WIDTH", "E1S_RDMA_SRC_HEIGHT", "E1S_RDMA_SRC_STRIDE_0", "E1S_RDMA_BASEADDR_P0"], 0x1000),
                   "dsim": ("E1S_DSIM0_SIZE", 1, ["E1S_DSIM_VERSION", "E1S_DSIM_LINK_STATUS0", "E1S_DSIM_LINK_STATUS1", "E1S_DSIM_LINK_STATUS2", "E1S_DSIM_LINK_STATUS3",
                                                  "E1S_DSIM_MIPI_STATUS", "E1S_DSIM_DPHY_STATUS", "E1S_DSIM_CLK_CTRL"], 0),
                   "dphy": ("E1S_DCPHY0_SIZE", 1, ["E1S_DSIM_PHY_PLL_STAT0", "E1S_DSIM_PHY_MC_GNR0"], 0),
                   "ss": ("E1S_DISP_SS_SIZE", 1, [], 0)}
        body = function_body(self.text, "e1s_display_pipeline")
        # the loop bounds the analysis assumes are the ones in the source
        self.assertEqual(len(re.findall(r"for \(i = 0; i < 4; i\+\+\)", body)), 2, "DECON and RDMA")
        self.assertEqual(len(re.findall(r"for \(i = 0; i < 16; i\+\+\)", body)), 1)
        self.assertEqual(len(re.findall(r"for \(i = 0; i < 2; i\+\+\)", body)), 1)
        for name, (size_macro, count, offsets, step) in windows.items():
            size = macro[size_macro]
            worst = (count - 1) * step + max([macro[o] for o in offsets] + [0]) + 4
            self.assertLessEqual(worst, size, "%s: last read ends at %#x, window is %#x" % (name, worst, size))
        self.assertLessEqual(0x08 + 4, macro["E1S_DISP_SS_SIZE"], "DPU_MIPI_PHY_CON read")
        self.assertEqual(macro["E1S_DSIM_PHY_MC_GNR0"], 0x300)

    def test_the_pipeline_function_runs_after_the_framebuffer_report_and_only_for_mode_2(self):
        body = function_body(self.text, "e1s_display_probe")
        self.assertLess(body.index("e1s_display_framebuffer();"), body.index("e1s_display_pipeline();"))
        self.assertLess(body.index("mode >= 2"), body.index("e1s_display_pipeline();"))


# ------------------------------------------------------------------------------------------------------------------ Package
@needs_build
@needs_pkg
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
        self.assertNotEqual(p["recovery_sha256"], "ae946b4be577b8179ad55f8c43bc4c9ca8afc50c25c131f6823f99d98ea2552d", "not NAT-067's image")
        stock = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
        if stock.exists():
            st = stock.read_bytes()
            self.assertEqual(sha(st), pkg["stock_sha256"])
            self.assertEqual(len(st), len(rec))
            diff = [i for i in range(2048) if rec[i] != st[i]]
            allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(576, 596)) | set(range(1636, 1644))
            self.assertTrue(diff and set(diff) <= allowed, [i for i in diff if i not in allowed])
            self.assertEqual(struct.unpack_from("<I", rec, 8)[0], len(pl))
        prev = ROOT / "artifacts/nat-067/package-001" / IMAGE67 / "recovery.img"
        if prev.exists():
            a = prev.read_bytes()
            self.assertEqual(rec[2048 + len(pl):], a[2048 + len(pl):], "everything after the payload is what NAT-067's candidate has there")


# ------------------------------------------------------------------------------------------------------------------ Driver
class Driver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load(DERIVE_PY, "nat069_derive_under_test")
        cls.text67 = (PROC / "nat-067" / "session_nat067.py").read_text()
        cls.text69 = DRIVER_PY.read_text()
        cls.pins = ("e" * 64, "f" * 64, 21878704)

    def test_the_committed_driver_is_what_the_derivation_gives(self):
        if not (ROOT / "artifacts/nat-069/package-001/package.json").exists():
            self.skipTest("artifacts/nat-069/package-001 is not present")
        self.assertEqual(self.d.derive_session(self.text67, *self.d.package_values()), self.text69)

    def test_the_derivation_changes_only_the_listed_lines(self):
        t = self.d.derive_session(self.text67, *self.pins)
        end = "(run separately).\"\"\""
        a, b = self.text67.splitlines(), t.splitlines()
        ia = next(i for i, x in enumerate(a) if x.endswith(end))
        ib = next(i for i, x in enumerate(b) if x.endswith(end))
        code_a, code_b = a[ia + 1:], b[ib + 1:]
        self.assertEqual(len(code_a), len(code_b), "the code after the docstring has the same number of lines")
        changed = [(x, y) for x, y in zip(code_a, code_b) if x != y]
        keys = ("'%s':dict(" % IMAGE67, "NEW_SHA=", "CANARY_SHA=", "PACKAGE=", "REQUIRED_DONE=", "glob(", "marker=")
        self.assertEqual(len(changed), len(keys), [x for x, _ in changed])
        for (x, y), k in zip(changed, keys):
            self.assertIn(k, x)
            self.assertNotEqual(x, y)
        self.assertEqual(code_b[[i for i, (x, y) in enumerate(zip(code_a, code_b)) if x != y][3]], "PACKAGE=ROOT/'artifacts/nat-069/package-001'")
        self.assertNotIn(IMAGE67, t)
        for keep in ("def gate(", "def registry_blocker(", "WRITE=", "TARGET='/dev/block/sda18'", "assert len(data)==SIZE and digest(data)==expected"):
            self.assertIn(keep, t)
            self.assertEqual(t.count(keep), self.text67.count(keep), keep)

    def test_the_derivation_uses_the_values_it_is_given(self):
        t = self.d.derive_session(self.text67, "a" * 64, "b" * 64, 12345)
        self.assertIn("NEW_SHA='%s'" % ("a" * 64), t)
        self.assertIn("CANARY_SHA='%s'" % ("b" * 64), t)
        self.assertIn("CANARY_LEN=12345", t)
        self.assertNotIn("21878704", t.split("CANARY_LEN=")[1].split("\n")[0])

    def test_a_drifted_nat067_driver_is_refused(self):
        for old, new in (("'loader-diag-xnu-ne1-usb':dict(", "'x':dict("),
                         ("CANARY_LEN=21878704", "CANARY_LEN=1"),
                         ("artifacts/nat-067/package-001", "artifacts/nat-099/package-001"),
                         ("*-nat067-%s-single-run-*.md", "*-nat067-%s-run-*.md"),
                         ("'NAT-066','NAT-067')", "'NAT-066')")):
            self.assertEqual(self.text67.count(old), 1, old)
            with self.assertRaises(AssertionError, msg=old):
                self.d.derive_session(self.text67.replace(old, new), *self.pins)

    def test_the_driver_pins_and_paths(self):
        mod = load(DRIVER_PY, "nat069_session_mod")
        self.assertEqual(sorted(mod.IMAGES), [IMAGE])
        self.assertTrue(str(mod.PACKAGE).endswith("artifacts/nat-069/package-001"))
        self.assertEqual(mod.STOCK_SHA, "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")
        self.assertEqual((mod.TARGET, mod.SIZE, mod.PAYLOAD_OFFSET), ("/dev/block/sda18", 100663296, 2048))
        for t in ("NAT-066", "NAT-067", "NAT-068", "NAT-069", "NAT-065", "NAT-060", "NAT-043"):
            self.assertIn(t, mod.REQUIRED_DONE)
        pkg = ROOT / "artifacts/nat-069/package-001/package.json"
        if pkg.exists():
            p = json.loads(pkg.read_text())["images"][IMAGE]
            cfg = mod.IMAGES[IMAGE]
            self.assertEqual((cfg["NEW_SHA"], cfg["CANARY_SHA"], cfg["CANARY_LEN"]), (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))

    def test_the_gates_on_a_temporary_tree(self):
        mod = load(DRIVER_PY, "nat069_session_gates")
        cfg = mod.IMAGES[IMAGE]
        with tempfile.TemporaryDirectory(prefix="nat069-") as w:
            root = Path(w)
            (root / "docs/decisions").mkdir(parents=True)
            (root / "state").mkdir()
            mod.ROOT = root
            with self.assertRaises(AssertionError, msg="no decision file"):
                mod.gate(IMAGE, cfg)
            d = root / ("docs/decisions/0029-nat069-%s-single-run-2026-11-12.md" % IMAGE)
            d.write_text("decision 0019 %s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            self.assertEqual(mod.gate(IMAGE, cfg), d)
            for text in ("decision 0019 %s" % cfg["NEW_SHA"], "%s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]), "decision 0019 %s" % cfg["CANARY_SHA"]):
                d.write_text(text)
                with self.assertRaises(AssertionError, msg=text):
                    mod.gate(IMAGE, cfg)
            d.write_text("decision 0019 %s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            (root / ("docs/decisions/0030-nat069-%s-single-run-2026-11-13.md" % IMAGE)).write_text("x")
            with self.assertRaises(AssertionError, msg="two decision files"):
                mod.gate(IMAGE, cfg)
            (root / ("docs/decisions/0030-nat069-%s-single-run-2026-11-13.md" % IMAGE)).unlink()

            def write_state(native, decision, done):
                st = dict(project=dict(permissions=dict(native=native),
                                       permission_decisions=[dict(scope="native", value=native, decision=decision)] if decision else []),
                          tasks=[dict(id=t, status="done") for t in done])
                (root / "state/lab.json").write_text(json.dumps(st))
            allt = list(mod.REQUIRED_DONE)
            write_state(False, "docs/decisions/" + d.name, allt)
            self.assertIn("native permission is not set", mod.registry_blocker(d))
            write_state(True, "docs/decisions/other.md", allt)
            self.assertIn("does not cite", mod.registry_blocker(d))
            write_state(True, "docs/decisions/" + d.name, allt[:-1])
            self.assertIn(allt[-1], mod.registry_blocker(d))
            write_state(True, "docs/decisions/" + d.name, [t for t in allt if t != "NAT-068"])
            self.assertIn("NAT-068", mod.registry_blocker(d))
            write_state(True, "docs/decisions/" + d.name, allt)
            self.assertIsNone(mod.registry_blocker(d))


# ------------------------------------------------------------------------------------------------------------------ Display
@needs_patch
class Display(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = load(ANALYZE_PY, "nat069_analyze_display")
        cls.formats = patch_formats(patch_text())

    def read(self, sc, **kw):
        return self.a.parse_display(render_display(dict(sc, **kw), self.formats))

    def test_text_rendered_from_the_patchs_formats_is_read_back_field_for_field(self):
        d = self.read(RUN_FB)
        self.assertEqual(d["framebuffer"], dict(width=1080, height=2340, depth=32, stride=4320, phys=0xfa200000, virt=0xfffffff03ee80000))
        self.assertEqual(d["fb_words"], [0xffffffff, 0xffffffff, 0, 0])
        self.assertEqual(d["fb_sum"], 0x6fffffff9)
        self.assertEqual([(x["index"], x["frames"], x["run"], x["idle_status"]) for x in d["decon"]], [(0, 7, True, False), (1, 0, False, False), (2, 0, False, False), (3, 0, False, False)])
        self.assertEqual([(w["index"], w["on"], w["start"], w["end"]) for w in d["windows"]][:2], [(0, True, (0, 0), (1079, 2339)), (1, False, (0, 0), (0, 0))])
        r0 = d["rdma"][0]
        self.assertEqual((r0["on"], r0["fmt"], r0["width"], r0["height"], r0["stride"], r0["addr"]), (True, 1, 1080, 2340, 4320, 0xfa200000))
        self.assertEqual(len(d["rdma"]), 4)
        self.assertEqual([(s["index"], s["video"], s["line"]) for s in d["dsim"]], [(0, 1, 2340), (1, 0, 0)])
        self.assertEqual(d["dcphy"], dict(pll=1, lock=1, ready=1, enable=1))
        self.assertEqual(d["dpu_mipi_phy_con"], 0x10)
        self.assertIsNotNone(d["read_at_s"])

    def test_each_fork(self):
        cases = [
            ("scans-loader-framebuffer", self.read(RUN_FB)),
            ("pipeline-idle", self.read(IDLE)),
            ("scans-other-buffer", self.read(RUN_FB, rdma=[(1, 1, 1080, 2340, 4320, 0x80000000)] + [(0, 0, 0, 0, 0, 0)] * 3)),
            ("scans-other-buffer", self.read(RUN_FB, rdma=[(1, 1, 1080, 2340, 4320, 0xfa200000 + 4320 * 2340)] + [(0, 0, 0, 0, 0, 0)] * 3)),     # one row past the end
            ("scans-loader-framebuffer", self.read(RUN_FB, rdma=[(1, 1, 1080, 2340, 4320, 0xfa200000 + 4320 * 2340 - 4)] + [(0, 0, 0, 0, 0, 0)] * 3)),   # last word inside
            ("rdma-reads-framebuffer-decon-idle", self.read(RUN_FB, decon=[(0, 0)] * 4, wins=[(0, (0, 0), (0, 0))] * 4)),
            ("decon-running-no-enabled-rdma", self.read(RUN_FB, rdma=[(0, 0, 0, 0, 0, 0)] * 4)),
            ("cannot-map", self.read(IDLE, cannot_map=True)),
            ("framebuffer-only", self.read(IDLE, mode=1)),
            ("pipeline-partial", self.read(RUN_FB, cut_after=5 + 4 + 4 + 2)),
            ("pipeline-partial", self.read(RUN_FB, cut_after=-1)),
        ]
        for want, d in cases:
            self.assertEqual(d["fork"], want, (want, d["fork"]))
            self.assertEqual(d["answer"], self.a.FORKS[want])
        self.assertEqual(set(self.a.FORKS) - {c[0] for c in cases} - {"no-display-text", "no-usable-framebuffer"}, set())

    def test_a_pipeline_with_a_missing_line_in_the_middle_is_partial(self):
        lines = render_display(RUN_FB, self.formats).splitlines()
        whole = self.a.parse_display("\n".join(lines))
        self.assertEqual(whole["fork"], "scans-loader-framebuffer")
        for what in ("DECON2 ", "DECON0 win3 ", "RDMA2 ", "DSIM1 video", "DSIM0 version", "DCPHY0"):
            kept = [l for l in lines if "e1s-display: " + what not in l]
            self.assertEqual(len(kept), len(lines) - 1, what)
            self.assertEqual(self.a.parse_display("\n".join(kept))["fork"], "pipeline-partial", what)

    def test_a_scan_out_that_depends_on_a_running_pipeline_needs_a_running_pipeline(self):
        on_window_only = self.read(RUN_FB, decon=[(0, 0)] * 4)
        self.assertEqual(on_window_only["fork"], "scans-loader-framebuffer", "a window that is on counts as running")
        none = self.read(RUN_FB, decon=[(0, 0)] * 4, wins=[(0, (0, 0), (0, 0))] * 4)
        self.assertEqual(none["fork"], "rdma-reads-framebuffer-decon-idle")

    def test_dsim1_cannot_map_is_a_complete_reading(self):
        d = self.read(RUN_FB, cannot_map_dsim1=True)
        self.assertTrue(d["cannot_map_dsim1"])
        self.assertEqual(len(d["dsim"]), 1)
        self.assertEqual(d["fork"], "scans-loader-framebuffer")

    def test_a_log_without_display_text_or_with_a_console_without_framebuffer(self):
        d = self.a.parse_display("[   1.000000]: bsd_init: done\n")
        self.assertEqual((d["fork"], d["lines"]), ("no-display-text", 0))
        d = self.a.parse_display("[   1.000000]: e1s-display: framebuffer 0x0 depth 0 stride 0\n[   1.000001]: e1s-display: the console has no usable framebuffer\n")
        self.assertEqual(d["fork"], "no-usable-framebuffer")

    def test_the_caveat_is_attached_to_every_reading_that_names_a_scan_out_state(self):
        for sc in (RUN_FB, IDLE):
            self.assertIn("not established", self.read(sc)["caveat"])
        self.assertIsNone(self.read(IDLE, mode=1)["caveat"])

    def test_duplicate_dumps_collapse(self):
        one = render_display(RUN_FB, self.formats)
        d = self.a.parse_display(one + "\n" + one)
        self.assertEqual((len(d["decon"]), len(d["rdma"]), len(d["dsim"]), len(d["windows"])), (4, 4, 2, 4))
        self.assertEqual(d["fork"], "scans-loader-framebuffer")

    def test_a_pipeline_without_a_framebuffer_report_cannot_be_called_the_loaders_buffer(self):
        text = "\n".join(l for l in render_display(RUN_FB, self.formats).splitlines() if "e1s-display: framebuffer" not in l)
        d = self.a.parse_display(text)
        self.assertIsNone(d["framebuffer"])
        self.assertEqual(d["fork"], "scans-other-buffer")

    def test_analyze_attaches_the_reading_of_the_joined_dump_texts(self):
        a = self.a
        text = render_display(RUN_FB, self.formats)
        lines = text.splitlines()
        old = a._ANALYZE65
        a._ANALYZE65 = lambda *x, **k: {"kernel_log": {"texts": {"1": "\n".join(lines[:9]), "2": "\n".join(lines[9:])}}, "image": "x"}
        try:
            out = a.analyze(None, [], {})
        finally:
            a._ANALYZE65 = old
        self.assertEqual(out["display"]["fork"], "scans-loader-framebuffer", "the dumps are joined before the lines are read")
        self.assertEqual(a.A65.IMAGE, IMAGE65, "NAT-065's name is restored")

    @unittest.skipUnless(NAT68_LOG.exists(), "the NAT-068 log is not present")
    def test_the_real_nat068_text_gives_the_framebuffer_report_and_no_pipeline(self):
        text = NAT68_LOG.read_text(errors="replace")
        d = self.a.parse_display(text)
        self.assertEqual(d["framebuffer"]["width"], 1080)
        self.assertEqual((d["framebuffer"]["height"], d["framebuffer"]["stride"], d["framebuffer"]["depth"]), (2340, 4320, 32))
        self.assertEqual(d["framebuffer"]["phys"], 0xfa200000)
        self.assertEqual(d["fb_words"], [0xffffffff, 0xffffffff, 0, 0])
        self.assertEqual(d["fb_sum"], 0x6fffffff9)
        self.assertEqual((d["decon"], d["rdma"], d["dsim"]), ([], [], []))
        self.assertEqual(d["fork"], "framebuffer-only")

    @unittest.skipUnless(NAT68_LOG.exists(), "the NAT-068 log is not present")
    def test_rendered_pipeline_lines_inserted_in_the_real_log_are_found_and_the_root_verdict_is_unchanged(self):
        text = NAT68_LOG.read_text(errors="replace")
        marker = "framebuffer sample sum"
        lines = text.splitlines()
        i = next(k for k, l in enumerate(lines) if marker in l)
        pipe = render_display(RUN_FB, self.formats).splitlines()
        extra = [l for l in pipe if "e1s-display: framebuffer" not in l and "fb[" not in l]
        merged = "\n".join(lines[:i + 1] + extra + lines[i + 1:])
        d = self.a.parse_display(merged)
        self.assertEqual(d["fork"], "scans-loader-framebuffer")
        self.assertEqual(self.a.classify_root({"2": merged})["outcome"], "probe-ran-to-exit")


# ------------------------------------------------------------------------------------------------------------------ Analyser
class Analyser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = load(ANALYZE_PY, "nat069_analyze_under_test")

    def test_the_analyser_is_nat065s_under_the_new_image_name(self):
        self.assertEqual(self.a.IMAGE, IMAGE)
        self.assertIs(self.a.classify_root, self.a.A65.classify_root)
        self.assertEqual(self.a.A65.IMAGE, IMAGE65, "NAT-065's own name is restored after a call")

    @unittest.skipUnless(NAT68_LOG.exists(), "the NAT-068 log is not present")
    def test_the_real_nat068_text_is_probe_ran_to_exit(self):
        r = self.a.classify_root({"2": NAT68_LOG.read_text(errors="replace")})
        self.assertEqual((r["outcome"], r["exit_status"], r["pid"]), ("probe-ran-to-exit", 81, 1))

    @unittest.skipUnless((NAT68_RUN / "archive/manifest.json").exists(), "artifacts/nat-068 is not present")
    def test_a_boot_of_the_previous_image_is_not_accepted_and_the_display_key_is_present(self):
        from contextlib import redirect_stdout
        import io
        A49 = self.a.A65.A49
        events, _ = A49.read_jsonl(str(NAT68_RUN / "usb-events.jsonl"))
        report = A49.read_json(str(NAT68_RUN / "report.json")) or {}
        a67 = load(PROC / "nat-067" / "analyze_nat067.py", "nat069_a67_control")
        buf = io.StringIO()
        with redirect_stdout(buf):
            r67 = a67.analyze(NAT68_RUN / "archive", events, report)
            r69 = self.a.analyze(NAT68_RUN / "archive", events, report)
        self.assertEqual((r67["verdict"], r67["root"]["outcome"]), ("PASS", "probe-ran-to-exit"), "control: NAT-067's analyser accepts the NAT-068 run of its own image")
        self.assertNotEqual(r69["verdict"], "PASS", "the NAT-069 analyser does not accept a boot of the NAT-067 image")
        self.assertEqual(r69["image"], IMAGE)
        self.assertIn("display", r69)

    @unittest.skipUnless((NAT68_RUN / "archive/manifest.json").exists(), "artifacts/nat-068 is not present")
    def test_the_command_line_tool_runs_under_the_new_name(self):
        import subprocess
        r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(ANALYZE_PY), "--archive", str(NAT68_RUN / "archive"), "--events", str(NAT68_RUN / "usb-events.jsonl"),
                            "--report", str(NAT68_RUN / "report.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        out = json.loads(r.stdout)
        self.assertEqual(out["image"], IMAGE)
        self.assertNotEqual(out["verdict"], "PASS")
        self.assertIn("display", out)


if __name__ == "__main__":
    unittest.main()
