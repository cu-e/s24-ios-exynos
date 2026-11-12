"""Tests for tools/ios/macho_audit.py (IOS-012).

Every fixture is built here from the published layouts (<mach-o/loader.h>, <mach-o/fat.h>, dyld_cache_format.h, the
ARM A64 encodings of MOVZ/MOVN/SVC, the ULEB128 export trie) with `struct.pack`, so an expected value comes from the format and
not from running the parser.  No Apple file is read.
"""
import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ios"))
import macho_audit as ma  # noqa: E402

CPU_ARM64 = 0x0100000C
SVC_80 = 0xD4001001


def movz(rd, imm, hw=0):
    return 0xD2800000 | (hw << 21) | (imm << 5) | rd


def movn(rd, imm, hw=0):
    return 0x92800000 | (hw << 21) | (imm << 5) | rd


def pad(raw, n):
    return raw + b"\0" * (-len(raw) % n)


def seg(name, vmaddr, vmsize, fileoff, filesize, sections=()):
    body = struct.pack("<16sQQQQiiII", name.encode(), vmaddr, vmsize, fileoff, filesize, 7, 5, len(sections), 0)
    for sname, addr, size, off in sections:
        body += struct.pack("<16s16sQQIIIIIIII", sname.encode(), name.encode(), addr, size, off, 2, 0, 0, 0, 0, 0, 0)
    return struct.pack("<II", 0x19, 8 + len(body)) + body


def dylib_cmd(cmd, path, cur=(1336, 0, 0)):
    name = pad(path.encode() + b"\0", 8)
    return struct.pack("<IIIIII", cmd, 24 + len(name), 24, 2, cur[0] << 16 | cur[1] << 8 | cur[2], 1 << 16) + name


def simple(cmd, payload=b""):
    return struct.pack("<II", cmd, 8 + len(payload)) + payload


def macho(cmds, ftype=2, cpu=CPU_ARM64, sub=0, tail=b""):
    blob = b"".join(cmds)
    return struct.pack("<IiiIIIII", 0xFEEDFACF, cpu, sub, ftype, len(cmds), len(blob), 0, 0) + blob + tail


def build_version(platform=2, minos=(16, 5, 0), sdk=(16, 5, 0)):
    v = lambda t: t[0] << 16 | t[1] << 8 | t[2]  # noqa: E731
    return simple(0x32, struct.pack("<IIII", platform, v(minos), v(sdk), 0))


class Uleb(unittest.TestCase):
    def test_reference_value(self):
        # the example in the DWARF specification: 624485 = E5 8E 26
        self.assertEqual(ma.uleb(bytes([0xE5, 0x8E, 0x26]), 0), (624485, 3))
        self.assertEqual(ma.uleb(bytes([0x7F]), 0), (127, 1))
        self.assertEqual(ma.uleb(bytes([0x80, 0x01]), 0), (128, 2))

    def test_truncated_and_overlong(self):
        with self.assertRaises(ma.AuditError):
            ma.uleb(bytes([0x80]), 0)
        with self.assertRaises(ma.AuditError):
            ma.uleb(bytes([0x80] * 12 + [0x01]), 0)


class ExportTrie(unittest.TestCase):
    def test_prefix_sharing_and_terminals(self):
        trie = bytes([0x00, 0x01]) + b"_f\0" + bytes([6])                       # root -> "_f" at 6
        trie += bytes([0x00, 0x02]) + b"oo\0" + bytes([16]) + b"ar\0" + bytes([21])  # "_f" -> "oo" at 16, "ar" at 21
        trie += bytes([0x03, 0x00, 0xB4, 0x24, 0x00])                           # "_foo": flags 0, address 0x1234
        trie += bytes([0x02, 0x00, 0x10, 0x00])                                 # "_far": flags 0, address 0x10
        self.assertEqual(len(trie), 25)
        self.assertEqual(ma.parse_exports(trie), {"_foo": (0, 0x1234), "_far": (0, 0x10)})

    def test_reexport_has_no_address(self):
        trie = bytes([0x00, 0x01]) + b"_r\0" + bytes([6]) + bytes([0x03, 0x08, 0x01, 0x00, 0x00])
        self.assertEqual(ma.parse_exports(trie), {"_r": (0x08, None)})

    def test_edge_outside_the_trie_is_rejected(self):
        trie = bytes([0x00, 0x01]) + b"_x\0" + bytes([100])      # a one-byte ULEB (< 0x80) that is past the end of the 6-byte trie
        with self.assertRaisesRegex(ma.AuditError, "outside the trie"):
            ma.parse_exports(trie)


class SvcScan(unittest.TestCase):
    def test_known_words(self):
        # literal A64 words: movz x16,#4 and movz x16,#0x1f; svc #0x80
        self.assertEqual(movz(16, 4), 0xD2800090)
        self.assertEqual(movz(16, 0x1F), 0xD28003F0)
        text = struct.pack("<4I", 0xD2800090, SVC_80, 0xD28003F0, SVC_80)
        pairs, total = ma.scan_svc(text, 0x1000)
        self.assertEqual((pairs, total), ([(0x1000, 4), (0x1008, 0x1F)], 2))

    def test_mach_traps_are_negative(self):
        # `mov x16,#-26` assembles to movn x16,#25; the trap number is 26
        pairs, total = ma.scan_svc(struct.pack("<2I", movn(16, 25), SVC_80), 0x2000)
        self.assertEqual((pairs, total), ([(0x2000, -26)], 1))

    def test_only_a_plain_x16_immediate_directly_before_svc_counts(self):
        words = [SVC_80,                      # svc as the first word: counted in the total only
                 movz(17, 5), SVC_80,         # wrong register
                 movz(16, 5, hw=1), SVC_80,   # shifted immediate: x16 is not 5
                 0xD503201F, SVC_80,          # nop before svc
                 movz(16, 9), 0xD503201F,     # movz not followed by svc
                 movz(16, 7), SVC_80]
        pairs, total = ma.scan_svc(struct.pack("<%dI" % len(words), *words), 0x4000)
        self.assertEqual(total, 5)
        self.assertEqual(pairs, [(0x4000 + 4 * 9, 7)])

    def test_trailing_partial_word_is_ignored(self):
        pairs, total = ma.scan_svc(struct.pack("<2I", movz(16, 3), SVC_80) + b"\x01\x02", 0)
        self.assertEqual((pairs, total), ([(0, 3)], 1))


def movk(rd, imm, hw=0):
    return 0xF2800000 | (hw << 21) | (imm << 5) | rd


ORR_PAGE = 0xB2704FE0          # orr xN,xzr,#0xfffff0000 (literal encoding checked against a real dyld word 0xb2704ff9 for x25)


class Commpage(unittest.TestCase):
    def test_literal_words(self):
        self.assertEqual(ORR_PAGE | 25, 0xB2704FF9)
        self.assertEqual(movk(25, 0xC10C), 0xF2982199)
        # the real libsystem_kernel sequence for the timebase offset (0x88): movk x3,#0,lsl 48 ... movk x3,#0xc088
        words = [0xF2E00003, 0xF2C001E3, 0xF2BFFFE3, 0xF2981103]
        self.assertEqual(ma.scan_commpage(struct.pack("<4I", *words), 0x1000), [(0x100C, "rw", 0x88)])

    def test_orr_shape(self):
        text = struct.pack("<3I", ORR_PAGE | 25, 0xD503201F, movk(25, 0xC10C))
        self.assertEqual(ma.scan_commpage(text, 0x2000), [(0x2008, "rw", 0x10C)])

    def test_read_only_page(self):
        text = struct.pack("<2I", ORR_PAGE | 8, movk(8, 0x4025))
        self.assertEqual(ma.scan_commpage(text, 0), [(4, "ro", 0x25)])
        self.assertEqual(ma.commpage_region(0xFFFFF4025), ("ro", 0x25))
        self.assertEqual(ma.commpage_region(0xFFFFFC000), ("rw", 0))

    def test_addresses_outside_both_pages_are_dropped(self):
        for imm in (0x0000, 0x3FFF, 0x8000, 0xBFFF):
            text = struct.pack("<2I", ORR_PAGE | 8, movk(8, imm))
            self.assertEqual(ma.scan_commpage(text, 0), [], hex(imm))
        self.assertIsNone(ma.commpage_region(0xFFFFF3FFF))
        self.assertIsNone(ma.commpage_region(0xFFFFF8000))
        self.assertIsNone(ma.commpage_region(0xFFFFC0000))

    def test_register_and_distance_must_match(self):
        far = [ORR_PAGE | 3] + [0xD503201F] * 4 + [movk(3, 0xC010)]            # fifth instruction after the orr: too far
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(far), *far), 0), [])
        near = [ORR_PAGE | 3] + [0xD503201F] * 3 + [movk(3, 0xC010)]           # fourth: accepted
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(near), *near), 0), [(16, "rw", 0x10)])
        other = [ORR_PAGE | 3, movk(4, 0xC010)]                                # different register
        self.assertEqual(ma.scan_commpage(struct.pack("<2I", *other), 0), [])
        sp = [ORR_PAGE | 31, movk(31, 0xC010)]                                 # Rd=31 of an orr immediate is sp, not a value
        self.assertEqual(ma.scan_commpage(struct.pack("<2I", *sp), 0), [])
        shifted = [ORR_PAGE | 3, movk(3, 0xC010, hw=1)]                        # a shifted movk is not the low lane
        self.assertEqual(ma.scan_commpage(struct.pack("<2I", *shifted), 0), [])

    def test_four_movk_shape_needs_both_upper_lanes_of_the_same_register(self):
        ok = [movk(5, 0xC020), movk(5, 0xFFFF, 1), movk(5, 0xF, 2), movk(5, 0, 3)]
        self.assertEqual(ma.scan_commpage(struct.pack("<4I", *ok), 0), [(0, "rw", 0x20)])
        no_lane1 = [movk(5, 0xC020), movk(6, 0xFFFF, 1), movk(5, 0xF, 2)]
        self.assertEqual(ma.scan_commpage(struct.pack("<3I", *no_lane1), 0), [])
        no_lane2 = [movk(5, 0xC020), movk(5, 0xFFFF, 1)]
        self.assertEqual(ma.scan_commpage(struct.pack("<2I", *no_lane2), 0), [])
        wrong_reg = [movk(6, 0xC020), movk(5, 0xFFFF, 1), movk(5, 0xF, 2)]
        self.assertEqual(ma.scan_commpage(struct.pack("<3I", *wrong_reg), 0), [])
        far = [movk(5, 0xC020)] + [0xD503201F] * 6 + [movk(5, 0xFFFF, 1), movk(5, 0xF, 2)]   # low lane six instructions before lane 2
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(far), *far), 0), [])

    def test_four_movk_window_boundaries(self):
        pad_ = [0xD503201F]
        # the low lane and the lane-1 movk may each be at most five instructions from the lane-2 movk, before or after it
        before = [movk(5, 0xC020)] + pad_ * 3 + [movk(5, 0xFFFF, 1), movk(5, 0xF, 2)]
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(before), *before), 0), [(0, "rw", 0x20)])
        before6 = [movk(5, 0xC020)] + pad_ * 4 + [movk(5, 0xFFFF, 1), movk(5, 0xF, 2)]
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(before6), *before6), 0), [])
        after = [movk(5, 0xFFFF, 1), movk(5, 0xF, 2)] + pad_ * 4 + [movk(5, 0xC030)]
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(after), *after), 0), [(24, "rw", 0x30)])
        after6 = [movk(5, 0xFFFF, 1), movk(5, 0xF, 2)] + pad_ * 5 + [movk(5, 0xC030)]
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(after6), *after6), 0), [])
        # the lane-1 movk may also sit up to five instructions from lane 2
        lane1_far = [movk(5, 0xFFFF, 1)] + pad_ * 4 + [movk(5, 0xF, 2), movk(5, 0xC040)]
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(lane1_far), *lane1_far), 0), [(24, "rw", 0x40)])
        lane1_toofar = [movk(5, 0xFFFF, 1)] + pad_ * 5 + [movk(5, 0xF, 2), movk(5, 0xC040)]
        self.assertEqual(ma.scan_commpage(struct.pack("<%dI" % len(lane1_toofar), *lane1_toofar), 0), [])

    def test_the_same_address_is_reported_once(self):
        words = [movk(5, 0xC050), movk(5, 0xFFFF, 1), movk(5, 0xF, 2), movk(5, 0xF, 2)]
        self.assertEqual(ma.scan_commpage(struct.pack("<4I", *words), 0), [(0, "rw", 0x50)])

    def test_movz_low_lane_is_accepted_and_duplicates_are_merged(self):
        words = [movz(7, 0xC034), movk(7, 0xFFFF, 1), movk(7, 0xF, 2)]
        self.assertEqual(ma.scan_commpage(struct.pack("<3I", *words), 0), [(0, "rw", 0x34)])

    def test_names_keep_the_two_pages_apart(self):
        header = ("#define _COMM_PAGE_A (_COMM_PAGE_START_ADDRESS+0x020)\n"
                  "#define _COMM_PAGE_B (_COMM_PAGE_RO_ADDRESS + 0x020)\n"
                  "#define _COMM_PAGE_C   _COMM_PAGE_A\n"
                  "#define _COMM_PAGE_D (_COMM_PAGE_START_ADDRESS+0x0D9)\n"
                  "  #define _COMM_PAGE_E (_COMM_PAGE_START_ADDRESS+0x300)\n")
        self.assertEqual(ma.parse_commpage_names(header), {("rw", 0x20): ["_COMM_PAGE_A"], ("ro", 0x20): ["_COMM_PAGE_B"],
                                                            ("rw", 0xD9): ["_COMM_PAGE_D"]})

    def test_nearest_field_hint(self):
        names = {("rw", 0x20): ["A"], ("rw", 0xC8): ["C8"], ("ro", 0x10): ["R"]}
        self.assertEqual(ma.nearest_field(names, "rw", 0x20), {"fields": ["A"]})
        self.assertEqual(ma.nearest_field(names, "rw", 0xD0), {"fields": [], "unnamed_in_project_header": True,
                                                               "after_field": "C8", "distance": 8})
        self.assertEqual(ma.nearest_field(names, "ro", 0x4), {"fields": [], "unnamed_in_project_header": True})
        self.assertEqual(ma.nearest_field(names, "ro", 0x100), {"fields": [], "unnamed_in_project_header": True,
                                                                "after_field": "R", "distance": 0xF0})

    def test_cli_end_to_end(self):
        header = "#define _COMM_PAGE_SIG (_COMM_PAGE_START_ADDRESS+0x000)\n#define _COMM_PAGE_APPROX (_COMM_PAGE_START_ADDRESS+0x0C8)\n"
        text = struct.pack("<2I", ORR_PAGE | 1, movk(1, 0xC0D0)) + struct.pack("<2I", ORR_PAGE | 2, movk(2, 0xC0D0))
        sec = bytes(text)
        prog = macho([seg("__TEXT", 0x1000, 0x1000, 0, 0x1000, [("__text", 0x1200, len(sec), 0x200)])])
        data = pad(prog, 0x200) + sec                         # headers fit in the first 0x200 bytes; the section starts at 0x200
        with tempfile.TemporaryDirectory() as td:
            p, h = Path(td) / "prog", Path(td) / "h.h"
            p.write_bytes(data)
            h.write_text(header)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ma.main(["commpage", "--program", str(p), "--header", str(h)])
            out = json.loads(buf.getvalue())
        (img,) = out["images"].values()
        self.assertEqual(img["references"], 2)
        self.assertEqual(img["offsets"], [{"page": "rw", "offset": "0xd0", "references": 2, "fields": [],
                                           "unnamed_in_project_header": True, "after_field": "_COMM_PAGE_APPROX", "distance": 8}])
        self.assertEqual(out["header_fields"], 2)


class Sysregs(unittest.TestCase):
    def test_known_words(self):
        # words taken from a real dyld (msr/mrs of an Apple register) and from the ARM ARM (mpidr_el1, DIT)
        words = [0xD51EF1A0, 0xD53EF1AA, 0xD53800A0, 0xD53B42A0, 0xD5300240]
        self.assertEqual(ma.scan_sysregs(struct.pack("<5I", *words), 0x1000),
                         [(0x1000, "msr", "S3_6_C15_C1_5"), (0x1004, "mrs", "S3_6_C15_C1_5"), (0x1008, "mrs", "S3_0_C0_C0_5"),
                          (0x100C, "mrs", "S3_3_C4_C2_5"), (0x1010, "mrs", "S2_0_C0_C2_2")])

    def test_other_system_instructions_are_not_register_moves(self):
        # msr daifset,#3 (immediate form), isb, svc #0x80, nop, sys/sysl-style words with other top bits
        words = [0xD50343DF, 0xD5033FDF, 0xD4001001, 0xD503201F, 0xD50B7B20, 0xD5280000]
        self.assertEqual(ma.scan_sysregs(struct.pack("<6I", *words), 0), [])

    def test_implementation_defined(self):
        for name, want in (("S3_6_C15_C1_5", True), ("S3_0_C11_C0_0", True), ("S3_4_C15_C10_6", True), ("S3_3_C4_C2_5", False),
                           ("S3_0_C10_C2_0", False), ("S3_0_C12_C0_0", False), ("S2_0_C15_C1_5", False), ("S2_0_C11_C0_0", False)):
            self.assertEqual(ma.implementation_defined(name), want, name)

    def test_cli_end_to_end(self):
        sec = struct.pack("<5I", 0xD51EF1A0, 0xD53EF1AA, 0xD51EF1A1, 0xD53B42A0, 0xD503201F)
        prog = macho([seg("__TEXT", 0x1000, 0x1000, 0, 0x1000, [("__text", 0x1200, len(sec), 0x200)])])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "prog"
            p.write_bytes(pad(prog, 0x200) + sec)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ma.main(["sysregs", "--program", str(p)])
            out = json.loads(buf.getvalue())
        (img,) = out["images"].values()
        self.assertEqual(img["registers"], [
            {"register": "S3_3_C4_C2_5", "access": "mrs", "count": 1, "implementation_defined": False},
            {"register": "S3_6_C15_C1_5", "access": "mrs", "count": 1, "implementation_defined": True},
            {"register": "S3_6_C15_C1_5", "access": "msr", "count": 2, "implementation_defined": True}])


class MachOParse(unittest.TestCase):
    def sample(self):
        return macho([
            seg("__TEXT", 0x100000000, 0x4000, 0, 0x4000, [("__text", 0x100000800, 0x40, 0x800), ("__cstring", 0x100000900, 8, 0x900)]),
            simple(0x80000034, struct.pack("<II", 0x1000, 0x20)),                       # chained fixups
            simple(0xE, struct.pack("<I", 12) + pad(b"/usr/lib/dyld\0", 4)),           # LC_LOAD_DYLINKER
            dylib_cmd(0xC, "/usr/lib/libSystem.B.dylib"),
            dylib_cmd(0x80000018, "/usr/lib/weak.dylib", cur=(1, 2, 3)),
            simple(0x1C | 0x80000000, struct.pack("<I", 12) + pad(b"@loader_path/../lib\0", 4)),  # LC_RPATH
            build_version(),
            simple(0x80000028, struct.pack("<QQ", 0x2F40, 0)),                          # LC_MAIN
        ])

    def test_fields(self):
        data = self.sample()
        m = ma.parse_macho(data)
        self.assertEqual(m["cputype"], CPU_ARM64)
        self.assertEqual(m["filetype"], "EXECUTE")
        self.assertEqual(m["dyld_fixups"], "chained fixups")
        self.assertEqual(m["dyld_linker"], "/usr/lib/dyld")
        self.assertEqual(m["rpaths"], ["@loader_path/../lib"])
        self.assertEqual(m["build_version"], {"platform": "iOS", "minos": "16.5.0", "sdk": "16.5.0"})
        self.assertEqual(m["entry"], {"kind": "LC_MAIN", "entryoff": 0x2F40})
        self.assertEqual([(l["name"], l["kind"], l["current"]) for l in m["libraries"]],
                         [("/usr/lib/libSystem.B.dylib", "LOAD_DYLIB", "1336.0.0"), ("/usr/lib/weak.dylib", "LOAD_WEAK_DYLIB", "1.2.3")])
        self.assertEqual([s["name"] for s in m["sections"]], ["__text", "__cstring"])
        self.assertEqual(m["sections"][0], {"segment": "__TEXT", "name": "__text", "addr": 0x100000800, "size": 0x40, "offset": 0x800})

    def test_summary_flags_plain_arm64(self):
        s = ma.summarize(ma.parse_macho(self.sample()))
        self.assertEqual(s["cputype"], "arm64")
        self.assertIn("no pointer authentication", s["cpusubtype"])
        self.assertEqual(ma.summarize(ma.parse_macho(macho([build_version()], sub=2)))["cpusubtype"], "arm64e")

    def test_old_version_min_command(self):
        m = ma.parse_macho(macho([simple(0x25, struct.pack("<II", 0x0C0000, 0x0D0100))]))
        self.assertEqual(m["build_version"], {"platform": "iOS (LC_VERSION_MIN)", "minos": "12.0.0", "sdk": "13.1.0"})

    def test_malformed_inputs_are_rejected(self):
        good = self.sample()
        bad_magic = b"\xCE\xFA\xED\xFE" + good[4:]
        with self.assertRaises(ma.AuditError):
            ma.parse_macho(bad_magic)
        with self.assertRaises(ma.AuditError):
            ma.parse_macho(good[:40])                                            # commands run past the data
        # one UUID command whose cmdsize is 26 inside a 32-byte command area: only the alignment rule rejects it
        odd = struct.pack("<IiiIIIII", 0xFEEDFACF, CPU_ARM64, 0, 2, 1, 32, 0, 0) + struct.pack("<II", 0x1B, 26) + bytes(16) + bytes(8)
        with self.assertRaisesRegex(ma.AuditError, "bad load command size"):
            ma.parse_macho(odd)
        lying = bytearray(macho([build_version()]))
        lying[16:20] = struct.pack("<I", 5000)                                   # ncmds far beyond the area
        with self.assertRaisesRegex(ma.AuditError, "implausible"):
            ma.parse_macho(bytes(lying))
        short_sections = bytearray(macho([seg("__TEXT", 0, 0x1000, 0, 0x1000, [("__text", 0, 0, 0)])]))
        short_sections[32 + 8 + 16 + 32 + 8:32 + 8 + 16 + 32 + 12] = struct.pack("<I", 9)  # nsects 9, room for 1
        with self.assertRaises(ma.AuditError):
            ma.parse_macho(bytes(short_sections))

    def test_fat_slice_picks_arm64(self):
        thin = self.sample()
        hdr = struct.pack(">II", 0xCAFEBABE, 2) + struct.pack(">IIIII", 0x01000007, 3, 0x1000, 8, 12) + struct.pack(">IIIII", CPU_ARM64, 0, 0x2000, len(thin), 14)
        data = pad(hdr, 0x2000) + thin
        off, size = ma.fat_slice(data)
        self.assertEqual((off, size), (0x2000, len(thin)))
        self.assertEqual(ma.parse_macho(data, off, size)["cputype"], CPU_ARM64)
        self.assertEqual(ma.fat_slice(thin), (0, len(thin)))
        only_x86 = struct.pack(">II", 0xCAFEBABE, 1) + struct.pack(">IIIII", 0x01000007, 3, 0x1000, 8, 12)
        with self.assertRaises(ma.AuditError):
            ma.fat_slice(only_x86)


class MasterParsing(unittest.TestCase):
    MASTER = "\n".join([
        "0\tAUE_NULL\tALL\t{ int nosys(void); }   { indirect system call }",
        "1\tAUE_EXIT\tALL\t{ void exit(int rval) NO_SYSCALL_STUB; }",
        "#if SOCKETS",
        "97\tAUE_SOCKET\tALL\t{ int socket(int domain, int type, int protocol); }",
        "#else",
        "97\tAUE_NULL\tALL\t{ int nosys(void); }",
        "#endif",
        "#if SYSV_SEM",
        "#if NECP",
        "300\tAUE_NULL\tALL\t{ int nested(void); }",
        "#endif /* NECP */",
        "#else /* !SYSV_SEM */",
        "300\tAUE_NULL\tALL\t{ int nosys(void); }",
        "#endif",
        "#ifndef PGO",
        "301\tAUE_NULL\tALL\t{ int not_pgo(void); }",
        "#endif",
        "#if !SENDFILE",
        "302\tAUE_NULL\tALL\t{ int not_sendfile(void); }",
        "#endif",
        "#if CONFIG_A && CONFIG_B",
        "303\tAUE_NULL\tALL\t{ int complex_guard(void); }",
        "#endif",
        "#if CONFIG_VFORK",
        "304\tAUE_NULL\tALL\t{ int vforkish(void); }",
        "#endif",
    ])

    def test_alternatives_and_guards(self):
        a = ma.parse_master_alternatives(self.MASTER)
        self.assertEqual(a[1], [((), "exit")])
        self.assertEqual(a[97], [((("SOCKETS", True),), "socket"), ((("SOCKETS", False),), "nosys")])
        self.assertEqual(a[300], [((("SYSV_SEM", True), ("NECP", True)), "nested"), ((("SYSV_SEM", False),), "nosys")])
        self.assertEqual(a[301], [((("PGO", False),), "not_pgo")])
        self.assertEqual(a[302], [((("SENDFILE", False),), "not_sendfile")])
        self.assertEqual(a[303][0][0], (("#if CONFIG_A && CONFIG_B", True),))

    def test_unbalanced_and_elif_are_rejected(self):
        with self.assertRaises(ma.AuditError):
            ma.parse_master_alternatives("#if A\n1\tX\tALL\t{ int f(void); }\n")
        with self.assertRaises(ma.AuditError):
            ma.parse_master_alternatives("1\tX\tALL\t{ int f(void); }\n#endif\n")
        with self.assertRaises(ma.AuditError):
            ma.parse_master_alternatives("#else\n")
        with self.assertRaises(ma.AuditError):
            ma.parse_master_alternatives("#if A\n#elif B\n#endif\n")

    def test_resolution_against_a_configuration(self):
        a = ma.parse_master_alternatives(self.MASTER)
        eff = ma.effective_syscalls(a, {"SOCKETS": True, "SYSV_SEM": False, "PGO": True, "SENDFILE": True, "NECP": True})
        self.assertEqual(eff[0], ("nosys", "unconditional"))
        self.assertEqual(eff[97], ("socket", "resolved"))
        self.assertEqual(eff[300], ("nosys", "resolved"))
        self.assertEqual(eff[301], ("(no alternative enabled)", "resolved"))   # PGO is on, so `#ifndef PGO` hides it
        self.assertEqual(eff[302], ("(no alternative enabled)", "resolved"))   # SENDFILE on, `#if !SENDFILE` hides it
        self.assertEqual(eff[303][1], "unresolved:#if CONFIG_A && CONFIG_B")
        self.assertEqual(eff[304][1], "unresolved:CONFIG_VFORK")
        both = ma.effective_syscalls(a, {"SYSV_SEM": True, "NECP": False})        # inner guard fails, outer holds
        self.assertEqual(both[300], ("(no alternative enabled)", "resolved"))
        eff2 = ma.effective_syscalls(a, {"SOCKETS": False, "SYSV_SEM": True, "NECP": True, "PGO": False, "SENDFILE": False})
        self.assertEqual(eff2[97], ("nosys", "resolved"))
        self.assertEqual(eff2[300], ("nested", "resolved"))
        self.assertEqual((eff2[301], eff2[302]), (("not_pgo", "resolved"), ("not_sendfile", "resolved")))


class ConfigParsing(unittest.TestCase):
    E1S = "\n".join([
        "#  BASE =    [ inet psynch OTHER UNDEFINED_BUNDLE ]",
        "#  OTHER =   [ necp ]",
        "#  RELEASE = [ BASE secure ]",
        "#  DEVELOPMENT = [ BASE development ]",
    ])
    MASTER = "\n".join([
        "options\t\tSOCKETS\t\t# socket support\t\t# <inet>",
        "options\t\tPSYNCH\t\t# <psynch>",
        "options\t\tSYSV_SEM\t# SVID semaphores\t\t# <sysv_sem>",
        "options\t\tNECP\t\t\t\t\t\t\t\t# <necp>",
        "options\t\tALWAYS\t\t# no tag list at all",
        "options\t\tEITHER\t\t# <sysv_sem,development>",
        "options\t\tANGLE\t# keeps <angle> brackets in a remark\t# <inet>",
        "options\t\tANGLE_OFF\t# keeps <inet> in a remark\t# <sysv_sem>",
        "# options\tCOMMENTED\t# <inet>",
    ])

    def test_bundles_expand_transitively(self):
        bundles = ma.parse_config_bundles(self.E1S)
        self.assertEqual(bundles["BASE"], ["inet", "psynch", "OTHER", "UNDEFINED_BUNDLE"])
        self.assertEqual(ma.enabled_tags(bundles, "DEVELOPMENT"), {"inet", "psynch", "necp", "development"})  # not UNDEFINED_BUNDLE
        self.assertEqual(ma.enabled_tags(bundles, "RELEASE"), {"inet", "psynch", "necp", "secure"})

    def test_option_states(self):
        tags = {"inet", "psynch", "necp", "development"}
        st = ma.option_states([self.MASTER], tags)
        self.assertEqual({k: st[k] for k in ("SOCKETS", "PSYNCH", "SYSV_SEM", "NECP", "ALWAYS", "EITHER")},
                         {"SOCKETS": True, "PSYNCH": True, "SYSV_SEM": False, "NECP": True, "ALWAYS": True, "EITHER": True})
        self.assertEqual((st["ANGLE"], st["ANGLE_OFF"]), (True, False))          # the last <...> list decides
        self.assertNotIn("COMMENTED", st)
        self.assertNotIn("MISSING", st)


class Normalisation(unittest.TestCase):
    def test_names(self):
        for given, want in [("_write", "write"), ("_msgrcv$NOCANCEL", "msgrcv"), ("sys_close", "close"), ("syscall_x", "x"),
                            ("mach_msg_trap", "mach_msg"), ("_kernelrpc_mach_vm_allocate_trap", "kernelrpc_mach_vm_allocate"),
                            ("___identitysvc", "identitysvc"), ("__pthread_kill", "pthread_kill")]:
            self.assertEqual(ma.norm(given), want, given)

    def test_compare_numbers_buckets(self):
        pairs = [(0x10, 0), (0x20, 4), (0x30, 97), (0x40, 258), (0x50, 999), (0x60, 20), (0x70, -26), (0x80, -90), (0x90, 304), (0x70, -26)]
        names = {0x10: ["_syscall"], 0x20: ["_write"], 0x30: ["_sock_wrong"], 0x40: ["_msgctl"], 0x60: [], 0x70: ["_mach_reply_port"],
                 0x80: ["_mach_wait_until"], 0x90: ["_vforkish"]}
        bsd = {0: ("nosys", "unconditional"), 4: ("write", "unconditional"), 97: ("socket", "resolved"), 258: ("nosys", "resolved"),
               20: ("getpid", "unconditional"), 304: ("vforkish", "unresolved:CONFIG_VFORK")}
        mach = {26: "mach_reply_port", 90: "mach_wait_until_trap"}
        r = ma.compare_numbers(pairs, names, bsd, mach)
        self.assertEqual(r["name_match"], 4)                                    # 0 (indirect), 4, -26, -90 (_trap suffix)
        self.assertEqual([x["number"] for x in r["name_differs"]], [97])
        self.assertFalse(r["name_differs"][0]["kernel_name_exported_by_the_library"])
        self.assertEqual([x["number"] for x in r["kernel_entry_is_nosys"]], [258])
        self.assertEqual([x["number"] for x in r["number_absent_in_kernel_table"]], [999])
        self.assertEqual([x["number"] for x in r["no_export_name_at_stub"]], [20])
        self.assertEqual([x["number"] for x in r["kernel_entry_depends_on_unresolved_option"]], [304])


class SyntheticCache(unittest.TestCase):
    """A two-file split cache with two images, built from dyld_cache_format.h offsets."""
    BASE = 0x180000000
    SUB = 0x184000000

    @classmethod
    def build(cls, d):
        d = Path(d)
        image_paths = ["/usr/lib/system/libsystem_kernel.dylib", "/usr/lib/libB.dylib"]
        # image 0: libsystem_kernel at BASE+0x1000 with stubs for write (4) and mach_reply_port (trap 26), exports via trie
        stub_write, stub_trap, stub_ghost = 0x800, 0x810, 0x820
        text = struct.pack("<4I", movz(16, 4), SVC_80, 0xD65F03C0, 0xD503201F)
        text += struct.pack("<4I", movn(16, 25), SVC_80, 0xD65F03C0, 0xD503201F)
        text += struct.pack("<4I", movz(16, 200), SVC_80, 0xD65F03C0, 0xD503201F)
        trie_off = 0x100                                            # relative to __LINKEDIT vmaddr via dataoff
        # trie: root -> "_write" (@..) and "_mach_reply_port" with terminal infos holding stub offsets (< 128: one byte)
        def uleb(v):
            out = bytearray()
            while True:
                b = v & 0x7F
                v >>= 7
                out.append(b | (0x80 if v else 0))
                if not v:
                    return bytes(out)
        e1, e2 = b"_write\0", b"_mach_reply_port\0"
        root_len = 2 + len(e1) + 1 + len(e2) + 1

        def terminal(addr):                      # node: terminal size, flags, address, no children
            info = uleb(0) + uleb(addr)
            return bytes([len(info)]) + info + bytes([0])
        n1, n2 = terminal(stub_write), terminal(stub_trap)
        trie = bytes([0, 2]) + e1 + bytes([root_len]) + e2 + bytes([root_len + len(n1)]) + n1 + n2
        img0 = macho([
            seg("__TEXT", cls.BASE + 0x1000, 0x1000, 0, 0x1000, [("__text", cls.BASE + 0x1000 + stub_write, len(text), 0x800)]),
            seg("__LINKEDIT", cls.BASE + 0x3000, 0x1000, 0x2000, 0x1000),
            simple(0x80000033, struct.pack("<II", 0x2000 + trie_off, len(trie))),
            dylib_cmd(0xD, image_paths[0]),
        ], ftype=6)
        # image 1: libB, a leaf
        img1 = macho([seg("__TEXT", cls.BASE + 0x2000, 0x1000, 0, 0x1000), dylib_cmd(0xD, image_paths[1]),
                      dylib_cmd(0xC, image_paths[0]), dylib_cmd(0xC, "/usr/lib/libDeepGone.dylib")], ftype=6)
        main = bytearray(0x4000)
        main[0:16] = b"dyld_v1   arm64\0"
        struct.pack_into("<II", main, 0x10, 0x200, 1)                 # one mapping: the main file itself
        struct.pack_into("<I", main, 0xD8, 2)                         # platform iOS
        struct.pack_into("<I", main, 0x16C, 16 << 16 | 5 << 8)        # os version 16.5.0
        struct.pack_into("<QQ", main, 0xE0, cls.BASE, 0x5000000)      # shared region
        struct.pack_into("<QQQII", main, 0x200, cls.BASE, 0x4000, 0, 7, 5)
        struct.pack_into("<II", main, 0x1C0, 0x300, 2)                # images
        paths_at = 0x3F00
        struct.pack_into("<QQQII", main, 0x300, cls.BASE + 0x1000, 0, 0, paths_at, 0)
        struct.pack_into("<QQQII", main, 0x320, cls.BASE + 0x2000, 0, 0, paths_at + 64, 0)
        main[paths_at:paths_at + len(image_paths[0]) + 1] = image_paths[0].encode() + b"\0"
        main[paths_at + 64:paths_at + 64 + len(image_paths[1]) + 1] = image_paths[1].encode() + b"\0"
        main[0x1000:0x1000 + len(img0)] = img0
        main[0x1000 + 0x800:0x1000 + 0x800 + len(text)] = text
        main[0x3100:0x3100 + len(trie)] = trie
        main[0x2000:0x2000 + len(img1)] = img1
        # the subcache: header page, then one data page at file offset 0x1000 that is mapped at SUB
        sub = bytearray(0x2000)
        sub[0:16] = b"dyld_v1   arm64\0"
        struct.pack_into("<II", sub, 0x10, 0x200, 1)
        struct.pack_into("<QQQII", sub, 0x200, cls.SUB, 0x1000, 0x1000, 3, 3)
        sub[0x1000:0x1008] = b"SUBCACHE"
        (d / "dyld_shared_cache_arm64").write_bytes(bytes(main))
        (d / "dyld_shared_cache_arm64.01").write_bytes(bytes(sub))
        (d / "dyld_shared_cache_arm64.01.dylddata").write_bytes(bytes(sub))
        (d / "dyld_shared_cache_arm64.map").write_text("not a cache file")
        (d / "dyld_shared_cache_arm64.symbols").write_bytes(b"not part of the cache set")
        return stub_write, stub_trap, stub_ghost

    def test_files_mappings_and_reads(self):
        with tempfile.TemporaryDirectory() as td:
            self.build(td)
            dsc = ma.Dsc(Path(td) / "dyld_shared_cache_arm64")
            try:
                self.assertEqual([n for n, _f, _m in dsc.files],
                                 ["dyld_shared_cache_arm64", "dyld_shared_cache_arm64.01", "dyld_shared_cache_arm64.01.dylddata"])
                self.assertEqual((dsc.magic, dsc.platform, ma.version(dsc.os_version)), ("dyld_v1   arm64", 2, "16.5.0"))
                self.assertEqual((dsc.shared_region_start, dsc.shared_region_size), (self.BASE, 0x5000000))
                self.assertEqual([p for _a, p in dsc.images], ["/usr/lib/system/libsystem_kernel.dylib", "/usr/lib/libB.dylib"])
                self.assertEqual(bytes(dsc.read(self.SUB, 8)), b"SUBCACHE")                 # served by the second file
                self.assertEqual(bytes(dsc.read(self.BASE, 6)), b"dyld_v")
                with self.assertRaises(ma.AuditError):
                    dsc.read(self.BASE + 0x4000, 4)                                         # past the last byte of the mapping
                with self.assertRaises(ma.AuditError):
                    dsc.read(self.SUB + 0xFFE, 8)                                           # runs over the end of a mapping
                m, addr = dsc.macho("/usr/lib/libB.dylib")
                self.assertEqual((addr, m["filetype"], m["install_name"]), (self.BASE + 0x2000, "DYLIB", "/usr/lib/libB.dylib"))
            finally:
                dsc.close()

    def test_a_non_cache_file_in_the_set_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            self.build(td)
            (Path(td) / "dyld_shared_cache_arm64.02").write_bytes(b"MZ" + bytes(100))
            with self.assertRaises(ma.AuditError):
                ma.Dsc(Path(td) / "dyld_shared_cache_arm64")

    def test_an_empty_file_in_the_set_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as td:
            self.build(td)
            (Path(td) / "dyld_shared_cache_arm64.02").write_bytes(b"")
            with self.assertRaises(ValueError):                         # mmap refuses a zero-length file
                ma.Dsc(Path(td) / "dyld_shared_cache_arm64")

    def test_mapping_past_the_end_of_its_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            self.build(td)
            sub = bytearray((Path(td) / "dyld_shared_cache_arm64.01").read_bytes())
            struct.pack_into("<QQQII", sub, 0x200, self.SUB, 0x2000, 0x1000, 3, 3)   # 0x1000 + 0x2000 > the 0x2000-byte file
            (Path(td) / "dyld_shared_cache_arm64.01").write_bytes(bytes(sub))
            with self.assertRaisesRegex(ma.AuditError, "runs past its file"):
                ma.Dsc(Path(td) / "dyld_shared_cache_arm64")

    def test_no_main_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "dyld_shared_cache_arm64.01").write_bytes(b"dyld_v1   arm64\0" + bytes(100))
            with self.assertRaises(ma.AuditError):
                ma.Dsc(Path(td) / "dyld_shared_cache_arm64")

    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ma.main(argv), 0)
        return json.loads(buf.getvalue())

    def test_syscalls_subcommand_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            self.build(td)
            t = Path(td)
            (t / "syscalls.master").write_text("\n".join([
                "0\tAUE_NULL\tALL\t{ int nosys(void); }",
                "4\tAUE_NULL\tALL\t{ user_ssize_t write(int fd, user_addr_t cbuf, user_size_t nbyte); }",
                "#if SOCKETS", "200\tAUE_NULL\tALL\t{ int sock(void); }", "#else", "200\tAUE_NULL\tALL\t{ int nosys(void); }", "#endif"]))
            (t / "syscall_sw.c").write_text("/* 26 */ MACH_TRAP(mach_reply_port, 0, 0, NULL),\n/* 27 */ MACH_TRAP(kern_invalid, 0, 0, NULL),\n")
            cfg = t / "config"
            cfg.mkdir()
            (cfg / "MASTER").write_text("options SOCKETS # sockets # <inet>\n")
            (cfg / "MASTER.arm64").write_text("")
            (cfg / "MASTER.arm64.e1s").write_text("#  DEVELOPMENT = [ BASE ]\n#  BASE = [ other ]\n")
            out = self.run_main(["syscalls", "--cache", str(t / "dyld_shared_cache_arm64"), "--master", str(t / "syscalls.master"),
                                 "--traps", str(t / "syscall_sw.c"), "--config-dir", str(cfg)])
            self.assertEqual((out["svc_80_total"], out["svc_with_x16_immediate"], out["distinct_bsd_numbers"], out["distinct_mach_traps"]),
                             (3, 3, 2, 1))
            c = out["comparison"]
            self.assertEqual(c["name_match"], 2)                                            # write=4 and mach_reply_port=-26
            self.assertEqual(c["number_absent_in_kernel_table"], [])
            # the stub at 200 has no export, and SOCKETS is off in this configuration, so the kernel entry is nosys
            self.assertEqual([x["number"] for x in c["kernel_entry_is_nosys"]], [200])
            self.assertEqual(out["kernel_tables"]["guards_in_master"], {"SOCKETS": False})
            self.assertEqual(out["kernel_tables"]["config"], "DEVELOPMENT of MASTER.arm64.e1s")

    def test_closure_subcommand_reports_missing_libraries(self):
        with tempfile.TemporaryDirectory() as td:
            self.build(td)
            t = Path(td)
            prog = t / "prog"
            prog.write_bytes(macho([build_version(), dylib_cmd(0xC, "/usr/lib/libB.dylib"), dylib_cmd(0xC, "/usr/lib/libGone.dylib"),
                                    dylib_cmd(0x80000018, "/usr/lib/libWeakGone.dylib")]))
            out = self.run_main(["closure", str(prog), "--cache", str(t / "dyld_shared_cache_arm64")])
            cl = out["programs"][str(prog)]["closure"]
            # libB (in the cache) pulls in libsystem_kernel (in the cache) and libDeepGone (missing): two levels deep
            self.assertEqual(cl["images"], 2)
            self.assertEqual(cl["missing_required"], ["/usr/lib/libDeepGone.dylib", "/usr/lib/libGone.dylib"])
            self.assertEqual(sorted(cl["missing"]), ["/usr/lib/libDeepGone.dylib", "/usr/lib/libGone.dylib", "/usr/lib/libWeakGone.dylib"])
            self.assertEqual(cl["missing"]["/usr/lib/libDeepGone.dylib"]["first_referrer"], "/usr/lib/libB.dylib")
            self.assertEqual(cl["missing"]["/usr/lib/libGone.dylib"]["first_referrer"], "prog")
            self.assertFalse(cl["missing"]["/usr/lib/libWeakGone.dylib"]["required"])
            self.assertEqual(out["programs"][str(prog)]["libraries_in_cache"], ["/usr/lib/libB.dylib"])
            self.assertEqual(out["cache"]["images"], 2)


class Cstrings(unittest.TestCase):
    def test_matches_only_the_cstring_section(self):
        blob = b"alpha\0kern.bootargs\0\0hw.target\0DYLD_PRINT_APIS\0"
        prog = macho([seg("__TEXT", 0x1000, 0x1000, 0, 0x1000, [("__cstring", 0x1100, len(blob), 0x100)])])
        data = pad(prog, 0x100) + blob                       # headers fit in the first 0x100 bytes; the section starts at 0x100
        self.assertEqual(len(data), 0x100 + len(blob))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "prog"
            p.write_bytes(data)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ma.main(["cstrings", str(p), "--match", r"^kern\.", "--match", "DYLD_"])
            out = json.loads(buf.getvalue())
        self.assertEqual(out["cstring_count"], 4)
        self.assertEqual(out["matches"], {r"^kern\.": ["kern.bootargs"], "DYLD_": ["DYLD_PRINT_APIS"]})


if __name__ == "__main__":
    unittest.main()
