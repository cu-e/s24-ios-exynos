#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-067 host tests: the image loader-diag-xnu-ne1-usb (NAT-065's md0 image with the e1s touch and battery drivers switched off on the command line), its derived
driver and its analyser. Evidence kind: host-test. Nothing here talks to a phone, and nothing shows what the kernel does after the abort NAT-066 saw.

    <venv with pyusb>/bin/python -W ignore -I docs/procedures/nat-067/test_nat067.py        (a few seconds; needs the build/package artifacts, each layer skips itself without them)

Layers:
  Build      two builds give identical hashes; the record carries the changes; the command line is NAT-065's with the tag changed and two boot-args appended.
  Payload    against NAT-065's: the loader-only Image differs in the six boot-id/name immediate words only; in the payload only the command-line field differs
             (one tag digit and the appended text); the ramdisk and every kernel segment are NAT-065's.
  Kernel     the kernel inside the payload parses both boot-args (their names and the "disabled" messages are in its binary), the abort NAT-066 recorded lies inside
             _e1s_touch_init according to the kernel's own symbol table, and the patch sources return from both drivers before they map any register.
  Package    the RECOVERY candidate carries Image.payload at offset 2048 and its pins are the ones the driver holds.
  Driver     session_nat067.py is what derive.py makes from session_nat065.py (a drifted source is refused); its gates behave as the NAT-062 driver's on a temporary tree.
  Analyser   the NAT-065 reading under the new name: the NAT-066 abort is other-panic, a probe exit is probe-ran-to-exit, a boot of another image is not accepted."""
import hashlib, importlib.util, json, os, re, struct, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
IMAGE = "loader-diag-xnu-ne1-usb"
IMAGE65 = "loader-diag-xnu-md0-usb"
B3 = ROOT / "artifacts/nat-020/build-003"
BUILD1 = Path(os.environ.get("NAT067_BUILD1") or ROOT / "artifacts/nat-067/build-001")
BUILD2 = Path(os.environ.get("NAT067_BUILD2") or ROOT / "artifacts/nat-067/build-002")
BUILD65 = ROOT / "artifacts/nat-065/build-001"
PACKAGE = ROOT / "artifacts/nat-067/package-001"
PATCHES = ROOT / "references/s24-port/xnu/e1s/patches"
KERNEL = B3 / "kernel.no-storage"
NAT66_LOG = PROC / "nat-066" / "run-001-kernel-log.txt"
NAT66_RUN = ROOT / "artifacts/nat-066/run-001"
LOADER_IMAGE_BYTES = 307200
CMD_OFF, CMD_LEN = 0x48, 608
EXPECTED_CMDLINE = ("rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT067-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v "
                    "loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0")
NAT65_CMDLINE = EXPECTED_CMDLINE.replace("NAT067", "NAT065").replace(" e1stouch=0 e1sbattery=0", "")
BUILD_PY = Path(os.environ.get("NAT067_BUILD") or HERE / "build.py")
DERIVE_PY = Path(os.environ.get("NAT067_DERIVE") or HERE / "derive.py")
DRIVER_PY = Path(os.environ.get("NAT067_DRIVER") or HERE / "session_nat067.py")
ANALYZE_PY = Path(os.environ.get("NAT067_ANALYZE") or HERE / "analyze_nat067.py")


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


def symbol_at(symbols, address):
    best = None
    for value, name in symbols:
        if value <= address:
            best = (value, name)
        else:
            break
    return best


needs_build = unittest.skipUnless((BUILD1 / "build.json").exists() and (BUILD2 / "build.json").exists() and (BUILD65 / IMAGE65 / "Image.payload").exists(),
                                  "artifacts/nat-067/build-001/-002 or artifacts/nat-065/build-001 are not present")
needs_pkg = unittest.skipUnless((PACKAGE / "package.json").exists(), "artifacts/nat-067/package-001 is not present")


# ------------------------------------------------------------------------------------------------------------------ Build
@needs_build
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b1 = json.loads((BUILD1 / "build.json").read_text())
        cls.b2 = json.loads((BUILD2 / "build.json").read_text())
        cls.b = load(BUILD_PY, "nat067_build_under_test")

    def test_two_builds_give_identical_hashes(self):
        for rel in ("Image", "Image.payload", "probe-init"):
            self.assertEqual(sha((BUILD1 / IMAGE / rel).read_bytes()), sha((BUILD2 / IMAGE / rel).read_bytes()), rel)
        for key in ("images", "image_payloads", "nat065_sources", "nat065_probe_init", "nat065_payload", "nat067_sources", "nat067_changes"):
            self.assertEqual(self.b1[key], self.b2[key], key)

    def test_the_build_record_carries_the_changes_and_nat065s_pins(self):
        b = self.b1
        self.assertEqual(sorted(b["images"]), [IMAGE])
        self.assertTrue(b["device_used"] is False and b["flashed"] is False and b["kind"] == "host-test")
        self.assertEqual(b["nat067_changes"], {"image_name": IMAGE, "cmdline_tag": "nat_attempt=NAT067-md0", "cmdline_append": self.b.APPEND, "cmdline": EXPECTED_CMDLINE})
        self.assertEqual(b["nat067_sources"], {"build.py": sha((HERE / "build.py").read_bytes())})
        a = json.loads((BUILD65 / "build.json").read_text())
        self.assertEqual(b["nat065_pins"], a["nat065_pins"], "the inputs are the pinned NAT-020 ones, the same as NAT-065's")
        self.assertEqual(b["nat065_sources"], a["nat065_sources"], "NAT-065's build.py and probe source are the ones that built it")
        for k in ("sha256", "bytes"):
            self.assertEqual(b["nat065_probe_init"][k], a["nat065_probe_init"][k], "the ramdisk is NAT-065's, byte for byte")
        self.assertEqual(b["payload_fixes"][IMAGE]["nat022_adt_size_fix"], "not applied (adt_size is already a multiple of 8)")
        self.assertEqual(b["nat065_payload"]["cmdline"], EXPECTED_CMDLINE)

    def test_the_command_line_is_nat065s_with_a_new_tag_and_two_boot_args_appended(self):
        pl = payload_of(BUILD1, IMAGE)
        raw = pl[CMD_OFF:CMD_OFF + CMD_LEN]
        self.assertEqual(raw.rstrip(b"\0"), EXPECTED_CMDLINE.encode(), "one NUL-padded string, exactly the expected text")
        self.assertLess(len(EXPECTED_CMDLINE), 256, "BOOT_LINE_LENGTH")
        a = payload_of(BUILD65, IMAGE65)[CMD_OFF:CMD_OFF + CMD_LEN].rstrip(b"\0").decode()
        self.assertEqual(a, NAT65_CMDLINE, "NAT-065's command line is the one NAT-066 ran")
        new, old = EXPECTED_CMDLINE.split(), a.split()
        self.assertEqual(new[:len(old)], [t.replace("NAT065", "NAT067") for t in old], "NAT-065's tokens in order, only the tag changed")
        self.assertEqual(new[len(old):], ["e1stouch=0", "e1sbattery=0"])
        self.assertEqual(sum(t.startswith("e1stouch") for t in new), 1)
        self.assertEqual(sum(t.startswith("e1sbattery") for t in new), 1)
        self.assertEqual(new[0], "rd=md0")

    def test_configure_hands_the_three_values_to_nat065s_build(self):
        self.assertEqual((self.b.NAME, self.b.NEW_TAG), (IMAGE, "nat_attempt=NAT067-md0"))
        self.b.configure()
        self.assertEqual((self.b.b65.NAME, self.b.b65.NEW_TAG, self.b.b65.APPEND), (IMAGE, "nat_attempt=NAT067-md0", self.b.APPEND))
        self.assertTrue(self.b.APPEND.endswith(" e1stouch=0 e1sbattery=0"))

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
        cls.p65 = (BUILD65 / IMAGE65 / "Image.payload").read_bytes()
        cls.p67 = (BUILD1 / IMAGE / "Image.payload").read_bytes()
        cls.i65 = (BUILD65 / IMAGE65 / "Image").read_bytes()
        cls.i67 = (BUILD1 / IMAGE / "Image").read_bytes()

    def test_the_loader_image_differs_from_nat065s_in_the_boot_id_immediates_only(self):
        a, b = self.i65, self.i67
        self.assertEqual((len(a), len(b)), (LOADER_IMAGE_BYTES, LOADER_IMAGE_BYTES))
        words = sorted({i & ~3 for i in range(len(a)) if a[i] != b[i]})
        self.assertEqual(len(words), 6, [hex(w) for w in words])
        self.assertTrue(all(0xf000 <= w < 0xf800 for w in words), [hex(w) for w in words])

        def chunks(name):
            h = fnv1a64(name)
            fnv = {(h >> (16 * i)) & 0xffff for i in range(4)}
            tag = {ord(name[k]) | ord(name[k + 1]) << 8 for k in (15, 17)}      # "-m","d0" / "-n","e1": the tail of the name the compiler folded into immediates
            return fnv | tag
        got65, got67 = set(), set()
        for w in words:
            x, y = struct.unpack_from("<I", a, w)[0], struct.unpack_from("<I", b, w)[0]
            self.assertIn(x & 0x7f800000, (0x52800000, 0x72800000), "MOVZ/MOVK at %#x" % w)
            self.assertEqual(x & ~(0xffff << 5), y & ~(0xffff << 5), "same opcode, shift and register at %#x" % w)
            got65.add((x >> 5) & 0xffff)
            got67.add((y >> 5) & 0xffff)
        self.assertEqual(got65, chunks(IMAGE65))
        self.assertEqual(got67, chunks(IMAGE))
        self.assertEqual(len(IMAGE), len(IMAGE65), "the names have the same length, so nothing else in the loader moves")

    def test_image_payload_is_the_loader_followed_by_the_payload(self):
        pl = self.p67
        head = bytearray(pl[:LOADER_IMAGE_BYTES])
        self.assertEqual(struct.unpack_from("<Q", head, 16)[0], len(pl))
        head[16:24] = self.i67[16:24]
        self.assertEqual(bytes(head), self.i67)
        self.assertEqual(len(self.p65), len(pl))

    def test_the_payload_differs_from_nat065s_only_in_the_command_line_field(self):
        a, b = self.p65[LOADER_IMAGE_BYTES:], self.p67[LOADER_IMAGE_BYTES:]
        self.assertEqual(len(a), len(b))
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        self.assertTrue(diff)
        self.assertTrue(all(CMD_OFF <= i < CMD_OFF + CMD_LEN for i in diff), "bytes outside the command-line field differ: %s" % [hex(i) for i in diff if not CMD_OFF <= i < CMD_OFF + CMD_LEN][:8])
        self.assertEqual(a[:CMD_OFF], b[:CMD_OFF], "the header before the field, including the segment table sizes, is NAT-065's")
        self.assertEqual(a[CMD_OFF + CMD_LEN:], b[CMD_OFF + CMD_LEN:], "every segment, the ADT and the ramdisk are NAT-065's")
        self.assertEqual(len(diff), 1 + len(" e1stouch=0 e1sbattery=0"), "one tag digit and the appended text")

    def test_the_ramdisk_is_nat065s(self):
        self.assertEqual((BUILD1 / IMAGE / "probe-init").read_bytes(), (BUILD65 / IMAGE65 / "probe-init").read_bytes())


# ------------------------------------------------------------------------------------------------------------------ Kernel
class Kernel(unittest.TestCase):
    @unittest.skipUnless(KERNEL.exists(), "the NAT-020 kernel is not present")
    def test_the_kernel_parses_both_boot_args_and_says_so(self):
        k = KERNEL.read_bytes()
        for needle in (b"e1stouch\0", b"e1sbattery\0", b"e1s-touch: disabled", b"e1s-battery: disabled (e1sbattery=0)"):
            self.assertEqual(k.count(needle), 1, needle)

    @unittest.skipUnless(KERNEL.exists() and NAT66_LOG.exists(), "the NAT-020 kernel or the NAT-066 log is not present")
    def test_the_abort_nat066_recorded_lies_inside_e1s_touch_init_in_the_kernels_symbols(self):
        text = NAT66_LOG.read_text(errors="replace")
        m = re.search(r"Kernel data abort\. at pc (0x[0-9a-f]+), lr (0x[0-9a-f]+)", text)
        self.assertTrue(m)
        pc, lr = int(m.group(1), 16), int(m.group(2), 16)
        self.assertRegex(text, r"far:? ?0x0*110300e4")
        syms = macho_symbols(KERNEL.read_bytes())
        names = {n for _, n in syms}
        for need in ("_e1s_touch_init", "_e1s_battery_init", "_bsd_init"):
            self.assertIn(need, names)
        v, n = symbol_at(syms, pc)
        self.assertEqual(n, "_e1s_touch_init", "pc %#x is in %s+%#x" % (pc, n, pc - v))
        self.assertEqual(pc - v, 0x174)
        self.assertEqual(symbol_at(syms, lr)[1], "_e1s_touch_init", "lr is in the same function: the read is not in a callee")
        # the touch function is entered from bsd_init (through redwood_input_init or directly): the frame above it is bsd_init
        self.assertEqual(symbol_at(syms, 0xfffffff0074a1444)[1], "_e1s_touch_init")

    @unittest.skipUnless((PATCHES / "0003-e1s-touch.patch").exists(), "the pinned e1s patches are not present")
    def test_both_drivers_return_from_the_boot_arg_check_before_they_map_any_register(self):
        for patch, func, arg in (("0003-e1s-touch.patch", "e1s_touch_init", "e1stouch"), ("0008-e1s-battery.patch", "e1s_battery_init", "e1sbattery")):
            text = (PATCHES / patch).read_text()
            i = text.index("+%s(void)" % func)
            body = text[i:i + 3000]
            check = body.index('PE_parse_boot_argn("%s"' % arg)
            ret = body.index("return;", check)
            first_map = body.index("ml_io_map")
            self.assertLess(check, ret, func)
            self.assertLess(ret, first_map, "%s returns before its first ml_io_map" % func)
            self.assertIn("enabled == 0", body[check:ret])
            # nothing before the check touches hardware: only declarations
            before = body[:check]
            self.assertNotIn("ml_io_map", before)
            self.assertNotIn("gpio_rd", before)
            self.assertNotIn("gpio_wr", before)

    @unittest.skipUnless((PATCHES / "0003-e1s-touch.patch").exists(), "the pinned e1s patches are not present")
    def test_the_touch_driver_reads_registers_through_physical_address_macros(self):
        text = (PATCHES / "0003-e1s-touch.patch").read_text()
        self.assertRegex(text, r"gpio_rd\(vm_offset_t reg\)")
        self.assertIn("E1S_GPP9_DAT", text)
        self.assertRegex(text, r"pin_set\(E1S_GPP9_DAT")


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
        self.assertNotEqual(p["recovery_sha256"], "c6f4a6e45806edf211ce7de16bf0882268b3f8d22f065a21e575bdb66b06f34d", "not NAT-065's image")
        stock = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
        if stock.exists():
            st = stock.read_bytes()
            self.assertEqual(sha(st), pkg["stock_sha256"])
            self.assertEqual(len(st), len(rec))
            diff = [i for i in range(2048) if rec[i] != st[i]]
            allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(576, 596)) | set(range(1636, 1644))
            self.assertTrue(diff and set(diff) <= allowed, [i for i in diff if i not in allowed])
            self.assertEqual(struct.unpack_from("<I", rec, 8)[0], len(pl))
        old = json.loads((ROOT / "artifacts/nat-065/package-001/package.json").read_text())["images"][IMAGE65]
        a = (ROOT / "artifacts/nat-065/package-001" / IMAGE65 / "recovery.img").read_bytes() if (ROOT / "artifacts/nat-065/package-001" / IMAGE65 / "recovery.img").exists() else None
        if a is not None:
            self.assertEqual(sha(a), old["recovery_sha256"])
            same_tail = rec[2048 + len(pl):] == a[2048 + len(pl):]
            self.assertTrue(same_tail, "everything after the payload is the stock RECOVERY in both candidates")


# ------------------------------------------------------------------------------------------------------------------ Driver
class Driver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load(DERIVE_PY, "nat067_derive_under_test")
        cls.text65 = (PROC / "nat-065" / "session_nat065.py").read_text()
        cls.text67 = DRIVER_PY.read_text()
        cls.pins = ("e" * 64, "f" * 64, 21878704)

    def test_the_committed_driver_is_what_the_derivation_gives(self):
        pkg = ROOT / "artifacts/nat-067/package-001/package.json"
        if not pkg.exists():
            self.skipTest("artifacts/nat-067/package-001 is not present")
        self.assertEqual(self.d.derive_session(self.text65, *self.d.package_values()), self.text67)

    def test_the_derivation_changes_only_the_listed_lines(self):
        t = self.d.derive_session(self.text65, *self.pins)
        end = "(run separately).\"\"\""
        a, b = self.text65.splitlines(), t.splitlines()
        ia = next(i for i, x in enumerate(a) if x.endswith(end))
        ib = next(i for i, x in enumerate(b) if x.endswith(end))
        code_a, code_b = a[ia + 1:], b[ib + 1:]
        self.assertEqual(len(code_a), len(code_b), "the code after the docstring has the same number of lines")
        changed = [(x, y) for x, y in zip(code_a, code_b) if x != y]
        keys = ("'%s':dict(" % IMAGE65, "NEW_SHA=", "CANARY_SHA=", "PACKAGE=", "REQUIRED_DONE=", "glob(", "marker=")
        self.assertEqual(len(changed), len(keys), [x for x, _ in changed])
        for (x, y), k in zip(changed, keys):
            self.assertIn(k, x)
            self.assertNotEqual(x, y)
        self.assertEqual(code_b[[i for i, (x, y) in enumerate(zip(code_a, code_b)) if x != y][3]], "PACKAGE=ROOT/'artifacts/nat-067/package-001'")
        self.assertNotIn(IMAGE65, t)
        for keep in ("def gate(", "def registry_blocker(", "WRITE=", "TARGET='/dev/block/sda18'", "assert len(data)==SIZE and digest(data)==expected"):
            self.assertIn(keep, t)
            self.assertEqual(t.count(keep), self.text65.count(keep), keep)

    def test_the_derivation_uses_the_values_it_is_given(self):
        t = self.d.derive_session(self.text65, "a" * 64, "b" * 64, 12345)
        self.assertIn("NEW_SHA='%s'" % ("a" * 64), t)
        self.assertIn("CANARY_SHA='%s'" % ("b" * 64), t)
        self.assertIn("CANARY_LEN=12345", t)
        self.assertNotIn("21878704", t.split("CANARY_LEN=")[1].split("\n")[0])

    def test_a_drifted_nat065_driver_is_refused(self):
        for old, new in (("'loader-diag-xnu-md0-usb':dict(", "'x':dict("),
                         ("CANARY_LEN=21878704", "CANARY_LEN=1"),
                         ("artifacts/nat-065/package-001", "artifacts/nat-099/package-001"),
                         ("*-nat065-%s-single-run-*.md", "*-nat065-%s-run-*.md"),
                         ("'NAT-064','NAT-065')", "'NAT-064')")):
            self.assertEqual(self.text65.count(old), 1, old)
            with self.assertRaises(AssertionError, msg=old):
                self.d.derive_session(self.text65.replace(old, new), *self.pins)

    def test_the_driver_pins_and_paths(self):
        mod = load(DRIVER_PY, "nat067_session_mod")
        self.assertEqual(sorted(mod.IMAGES), [IMAGE])
        self.assertTrue(str(mod.PACKAGE).endswith("artifacts/nat-067/package-001"))
        self.assertEqual(mod.STOCK_SHA, "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67")
        self.assertEqual((mod.TARGET, mod.SIZE, mod.PAYLOAD_OFFSET), ("/dev/block/sda18", 100663296, 2048))
        for t in ("NAT-066", "NAT-067", "NAT-065", "NAT-060", "NAT-043"):
            self.assertIn(t, mod.REQUIRED_DONE)
        pkg = ROOT / "artifacts/nat-067/package-001/package.json"
        if pkg.exists():
            p = json.loads(pkg.read_text())["images"][IMAGE]
            cfg = mod.IMAGES[IMAGE]
            self.assertEqual((cfg["NEW_SHA"], cfg["CANARY_SHA"], cfg["CANARY_LEN"]), (p["recovery_sha256"], p["payload_sha256"], p["payload_bytes"]))

    def test_the_gates_on_a_temporary_tree(self):
        mod = load(DRIVER_PY, "nat067_session_gates")
        cfg = mod.IMAGES[IMAGE]
        with tempfile.TemporaryDirectory(prefix="nat067-") as w:
            root = Path(w)
            (root / "docs/decisions").mkdir(parents=True)
            (root / "state").mkdir()
            mod.ROOT = root
            with self.assertRaises(AssertionError, msg="no decision file"):
                mod.gate(IMAGE, cfg)
            d = root / ("docs/decisions/0028-nat067-%s-single-run-2026-11-12.md" % IMAGE)
            d.write_text("decision 0019 %s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            self.assertEqual(mod.gate(IMAGE, cfg), d)
            for text in ("decision 0019 %s" % cfg["NEW_SHA"], "%s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]), "decision 0019 %s" % cfg["CANARY_SHA"]):
                d.write_text(text)
                with self.assertRaises(AssertionError, msg=text):
                    mod.gate(IMAGE, cfg)
            d.write_text("decision 0019 %s %s" % (cfg["NEW_SHA"], cfg["CANARY_SHA"]))
            (root / ("docs/decisions/0029-nat067-%s-single-run-2026-11-13.md" % IMAGE)).write_text("x")
            with self.assertRaises(AssertionError, msg="two decision files"):
                mod.gate(IMAGE, cfg)
            (root / ("docs/decisions/0029-nat067-%s-single-run-2026-11-13.md" % IMAGE)).unlink()
            # registry
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
            write_state(True, "docs/decisions/" + d.name, [t for t in allt if t != "NAT-066"])
            self.assertIn("NAT-066", mod.registry_blocker(d))
            write_state(True, "docs/decisions/" + d.name, allt)
            self.assertIsNone(mod.registry_blocker(d))


# ------------------------------------------------------------------------------------------------------------------ Analyser
class Analyser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = load(ANALYZE_PY, "nat067_analyze_under_test")

    def test_the_analyser_is_nat065s_under_the_new_image_name(self):
        self.assertEqual(self.a.IMAGE, IMAGE)
        self.assertIs(self.a.classify_root, self.a.A65.classify_root)
        self.assertEqual(self.a.A65.IMAGE, IMAGE65, "NAT-065's own name is restored after a call")

    @unittest.skipUnless(NAT66_LOG.exists(), "the NAT-066 log is not present")
    def test_the_nat066_abort_is_other_panic_and_a_probe_exit_is_probe_ran_to_exit(self):
        text = NAT66_LOG.read_text(errors="replace")
        r = self.a.classify_root({"2": text})
        self.assertEqual(r["outcome"], "other-panic")
        self.assertEqual(r["bsd_root"]["device"], "md0")
        self.assertFalse(r["banner_seen"])
        i = text.index("panic(cpu 0")
        fake = text[:i] + ("panic(cpu 0 caller 0xfffffff007a7d6b8): initproc exited -- no exit reason available -- (signal 0, exit status 81)\n"
                           "Debugger message: panic\n")
        r = self.a.classify_root({"2": fake})
        self.assertEqual((r["outcome"], r["exit_status"], r["pid"]), ("probe-ran-to-exit", 81, 1))

    @unittest.skipUnless((NAT66_RUN / "archive/manifest.json").exists(), "artifacts/nat-066 is not present")
    def test_the_command_line_tool_runs_under_the_new_name_and_does_not_accept_the_nat066_boot(self):
        import subprocess
        r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(ANALYZE_PY), "--archive", str(NAT66_RUN / "archive"), "--events", str(NAT66_RUN / "usb-events.jsonl"),
                            "--report", str(NAT66_RUN / "report.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        out = json.loads(r.stdout)
        self.assertEqual(out["image"], IMAGE)
        self.assertNotEqual(out["verdict"], "PASS")

    @unittest.skipUnless((NAT66_RUN / "archive/manifest.json").exists(), "artifacts/nat-066 is not present")
    def test_a_boot_of_another_image_is_not_accepted(self):
        from contextlib import redirect_stdout
        import io
        A49 = self.a.A65.A49
        events, _ = A49.read_jsonl(str(NAT66_RUN / "usb-events.jsonl"))
        report = A49.read_json(str(NAT66_RUN / "report.json")) or {}
        r65 = self.a.A65.analyze(NAT66_RUN / "archive", events, report)
        self.assertEqual(r65["verdict"], "PASS", "NAT-065's analyser accepts the NAT-066 run")
        self.assertEqual(r65["root"]["outcome"], "other-panic")
        buf = io.StringIO()
        with redirect_stdout(buf):
            r67 = self.a.analyze(NAT66_RUN / "archive", events, report)
        self.assertNotEqual(r67["verdict"], "PASS", "the NAT-067 analyser does not accept a boot of the NAT-065 image")
        self.assertEqual(r67["image"], IMAGE)


if __name__ == "__main__":
    unittest.main()
