"""Host tests for tools/ios/ipsw_inspect.py (IOS-002).

Evidence class: host-test. Every archive here is synthesised in a temporary directory. The only Apple-shaped data is
the minimal set of BuildManifest.plist keys the inspector reads (ProductBuildVersion, ProductVersion,
SupportedProductTypes, BuildIdentities[].Info.{DeviceClass,RestoreBehavior}, Manifest[component].Info.Path); member
contents are placeholder bytes and the "kernelcache" is a hand-built IM4P around a made-up banner. Nothing here says
anything about a real IPSW; the inspector's run on the real archive is recorded separately (IOS-001).
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import plistlib
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ipsw_inspect", ROOT / "tools/ios/ipsw_inspect.py")
ins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ins)

BUILD, PRODUCT, CLASS = "20F66", "iPhone10,3", "d22ap"
COMPONENT_PATHS = {
    "OS": "root.dmg",
    "Cryptex1,SystemOS": "system.dmg",
    "Cryptex1,AppOS": "app.dmg",
    "KernelCache": "kernelcache.bin",
    "DeviceTree": "Firmware/dt.im4p",
}


def der(tag, content):
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + content


def im4p(payload, kind=b"krnl", description=b"synthetic-kernelcache", extra=b""):
    return der(0x30, der(0x16, b"IM4P") + der(0x16, kind) + der(0x16, description) + der(0x04, payload) + extra)


def thin_macho_header(filetype=2):
    return struct.pack("<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, filetype, 0, 0, 0, 0)


BANNER = b"Darwin Kernel Version 99.1.0: synthetic test banner; root:xnu-0000.1~1/RELEASE_ARM64_TESTCHIP"


def kernel_payload():
    return thin_macho_header() + b"\0" * 64 + BANNER + b"\0" + b"tail" * 20


def lzfse_raw(payload):
    return b"bvx-" + struct.pack("<I", len(payload)) + payload + b"bvx$"


def manifest(build=BUILD, products=(PRODUCT,), classes=(CLASS,), paths=None, drop=(), behaviors=("Erase", "Update")):
    paths = dict(COMPONENT_PATHS if paths is None else paths)
    identities = []
    for cls in classes:
        for behavior in behaviors:
            entries = {name: {"Info": {"Path": path}} for name, path in paths.items() if name not in drop}
            identities.append({"Info": {"DeviceClass": cls, "RestoreBehavior": behavior}, "Manifest": entries})
    return {"ProductBuildVersion": build, "ProductVersion": "16.5", "SupportedProductTypes": list(products),
            "BuildIdentities": identities}


def write_ipsw(path, plist=None, members=None, omit=(), raw_manifest=None, stored=True):
    members = dict({p: b"placeholder:" + p.encode() for p in COMPONENT_PATHS.values()}, **(members or {}))
    with zipfile.ZipFile(path, "w") as z:
        if raw_manifest is not None:
            z.writestr("BuildManifest.plist", raw_manifest)
        elif plist is not False:
            z.writestr("BuildManifest.plist", plistlib.dumps(manifest() if plist is None else plist))
        for name, data in members.items():
            if name not in omit:
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                z.writestr(info, data)
    return path


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def check(self, **kwargs):
        path = write_ipsw(self.dir / "t.ipsw", **kwargs)
        return ins.inspect(path)


class Verdicts(TempCase):
    def test_accepted_reports_components_and_makes_no_compatibility_claim(self):
        report = self.check()
        self.assertEqual(report["verdict"], "accepted", report["detail"])
        self.assertEqual(report["compatibility"], "not-assessed")
        self.assertEqual(report["product_build_version"], BUILD)
        self.assertEqual(set(report["components"]), set(COMPONENT_PATHS))
        self.assertEqual(report["components"]["OS"][0]["path"], "root.dmg")
        self.assertEqual(report["components"]["OS"][0]["identities"], ["Erase", "Update"])

    def test_verdict_vocabulary_is_exactly_the_five(self):
        self.assertEqual(ins.VERDICTS, ("accepted", "wrong-build", "wrong-device", "missing-member", "not-an-ipsw"))

    def test_wrong_build_names_the_found_build(self):
        report = self.check(plist=manifest(build="21A1"))
        self.assertEqual(report["verdict"], "wrong-build")
        self.assertIn("21A1", report["detail"])
        self.assertIn(BUILD, report["detail"])

    def test_wrong_product_type_names_the_supported_list(self):
        report = self.check(plist=manifest(products=("iPhone11,2",)))
        self.assertEqual(report["verdict"], "wrong-device")
        self.assertIn("iPhone11,2", report["detail"])

    def test_wrong_device_class_names_what_was_found(self):
        report = self.check(plist=manifest(classes=("n841ap",)))
        self.assertEqual(report["verdict"], "wrong-device")
        self.assertIn("n841ap", report["detail"])

    def test_device_class_matches_case_insensitively(self):
        self.assertEqual(self.check(plist=manifest(classes=("D22AP",)))["verdict"], "accepted")

    def test_expected_device_class_is_case_insensitive_too(self):
        path = write_ipsw(self.dir / "t.ipsw")
        self.assertEqual(ins.inspect(path, expect_device_class="D22AP")["verdict"], "accepted")

    def test_build_is_checked_before_device(self):
        report = self.check(plist=manifest(build="21A1", products=("iPhone11,2",)))
        self.assertEqual(report["verdict"], "wrong-build")

    def test_other_identity_classes_do_not_hide_the_expected_one(self):
        plist = manifest()
        plist["BuildIdentities"] += manifest(classes=("d221ap",))["BuildIdentities"]
        self.assertEqual(self.check(plist=plist)["verdict"], "accepted")

    def test_listed_but_absent_member_is_missing_member(self):
        report = self.check(omit=("system.dmg",))
        self.assertEqual(report["verdict"], "missing-member")
        self.assertIn("system.dmg", report["detail"])

    def test_identity_without_a_required_component_is_missing_member(self):
        report = self.check(plist=manifest(drop=("KernelCache",)))
        self.assertEqual(report["verdict"], "missing-member")
        self.assertIn("KernelCache", report["detail"])

    def test_extra_unlisted_members_are_ignored(self):
        report = self.check(members={"unrelated.bin": b"x"})
        self.assertEqual(report["verdict"], "accepted")

    def test_identities_may_name_different_files_for_one_component(self):
        plist = manifest()
        plist["BuildIdentities"][1]["Manifest"]["RestoreRamDisk"] = {"Info": {"Path": "ramdisk-b.dmg"}}
        plist["BuildIdentities"][0]["Manifest"]["RestoreRamDisk"] = {"Info": {"Path": "ramdisk-a.dmg"}}
        report = self.check(plist=plist, members={"ramdisk-a.dmg": b"a", "ramdisk-b.dmg": b"b"})
        self.assertEqual(report["verdict"], "accepted", report["detail"])
        self.assertEqual(sorted(s["path"] for s in report["components"]["RestoreRamDisk"]),
                         ["ramdisk-a.dmg", "ramdisk-b.dmg"])
        missing = self.check(plist=plist, members={"ramdisk-a.dmg": b"a"})
        self.assertEqual(missing["verdict"], "missing-member")
        self.assertIn("ramdisk-b.dmg", missing["detail"])


class NotAnIpsw(TempCase):
    def test_absent_file(self):
        report = ins.inspect(self.dir / "nope.ipsw")
        self.assertEqual(report["verdict"], "not-an-ipsw")
        self.assertIn("no such file", report["detail"])

    def test_directory_is_not_a_file(self):
        self.assertEqual(ins.inspect(self.dir)["verdict"], "not-an-ipsw")

    def test_plain_file_is_not_a_zip(self):
        path = self.dir / "t.ipsw"
        path.write_bytes(b"this is not a zip" * 10)
        self.assertEqual(ins.inspect(path)["verdict"], "not-an-ipsw")

    def test_empty_file(self):
        path = self.dir / "t.ipsw"
        path.write_bytes(b"")
        self.assertEqual(ins.inspect(path)["verdict"], "not-an-ipsw")

    def test_zip_without_manifest_names_it(self):
        report = self.check(plist=False)
        self.assertEqual(report["verdict"], "not-an-ipsw")
        self.assertIn("BuildManifest.plist", report["detail"])

    def test_unparseable_manifest(self):
        self.assertEqual(self.check(raw_manifest=b"<<not a plist>>")["verdict"], "not-an-ipsw")

    def test_manifest_without_required_keys(self):
        for key in ("ProductBuildVersion", "SupportedProductTypes", "BuildIdentities"):
            with self.subTest(missing=key):
                plist = manifest()
                del plist[key]
                report = self.check(plist=plist)
                self.assertEqual(report["verdict"], "not-an-ipsw")
                self.assertIn(key, report["detail"])

    def test_manifest_of_the_wrong_shape(self):
        for plist in ([1, 2], {"ProductBuildVersion": BUILD, "SupportedProductTypes": 5, "BuildIdentities": []}):
            with self.subTest(plist=plist):
                self.assertEqual(self.check(plist=plist)["verdict"], "not-an-ipsw")

    def test_oversized_manifest_is_refused_without_parsing(self):
        report = self.check(raw_manifest=b"x" * (ins.MAX_MANIFEST_BYTES + 1))
        self.assertEqual(report["verdict"], "not-an-ipsw")
        self.assertIn("larger", report["detail"])

    def test_zip_slip_member_names_are_refused(self):
        for name in ("../evil", "dir/../../evil", "/abs/evil", "C:evil", "back\\slash"):
            with self.subTest(name=name):
                path = self.dir / "slip.ipsw"
                with zipfile.ZipFile(path, "w") as z:
                    z.writestr("BuildManifest.plist", plistlib.dumps(manifest()))
                    info = zipfile.ZipInfo("placeholder")
                    info.filename = name
                    z.writestr(info, b"x")
                report = ins.inspect(path)
                self.assertEqual(report["verdict"], "not-an-ipsw")
                self.assertIn("unsafe member name", report["detail"])

    def test_name_check_covers_what_zipfile_itself_would_normalise_away(self):
        # zipfile truncates a member name at a NUL when reading, so this class of name cannot be built as an archive
        for name in ("a\x00b", "", "..", "x/../y", "/", "D:\\x"):
            with self.subTest(name=name):
                self.assertIsNotNone(ins.unsafe_member(name))
        for name in ("BuildManifest.plist", "Firmware/all_flash/DeviceTree.d22ap.im4p", "096-04088-077.dmg", "a..b/c"):
            with self.subTest(name=name):
                self.assertIsNone(ins.unsafe_member(name))

    def test_unsafe_manifest_path_is_refused(self):
        for bad in ("../outside.dmg", "/etc/passwd"):
            with self.subTest(path=bad):
                paths = dict(COMPONENT_PATHS, OS=bad)
                report = self.check(plist=manifest(paths=paths))
                self.assertEqual(report["verdict"], "not-an-ipsw")
                self.assertIn("unsafe", report["detail"])

    def test_unsafe_member_name_wins_over_a_wrong_build(self):
        path = self.dir / "slip.ipsw"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("BuildManifest.plist", plistlib.dumps(manifest(build="other")))
            z.writestr(zipfile.ZipInfo("../x"), b"x")
        self.assertEqual(ins.inspect(path)["verdict"], "not-an-ipsw")


class Hashing(TempCase):
    def test_member_hashes_match_hashlib(self):
        path = write_ipsw(self.dir / "t.ipsw")
        report = ins.inspect(path, with_sha256=True)
        self.assertEqual(report["verdict"], "accepted")
        for name, digest in report["member_sha256"].items():
            if name == "BuildManifest.plist":
                data = plistlib.dumps(manifest())
            else:
                data = b"placeholder:" + name.encode()
            self.assertEqual(digest, hashlib.sha256(data).hexdigest(), name)
        self.assertEqual(set(report["member_sha256"]), set(COMPONENT_PATHS.values()) | {"BuildManifest.plist"})

    def test_hashing_is_off_by_default(self):
        self.assertNotIn("member_sha256", self.check())

    def test_corrupted_member_data_is_detected_when_hashing(self):
        path = write_ipsw(self.dir / "t.ipsw", members={"root.dmg": b"A" * 4096})
        blob = bytearray(path.read_bytes())
        at = blob.index(b"A" * 4096)
        blob[at + 100] ^= 0xFF
        path.write_bytes(bytes(blob))
        report = ins.inspect(path, with_sha256=True)
        self.assertEqual(report["verdict"], "not-an-ipsw")
        self.assertIn("root.dmg", report["detail"])

    def test_deflated_members_hash_to_the_content_hash(self):
        data = b"B" * 100000
        path = write_ipsw(self.dir / "t.ipsw", members={"root.dmg": data}, stored=False)
        with zipfile.ZipFile(path) as z:
            self.assertEqual(z.getinfo("root.dmg").compress_type, zipfile.ZIP_DEFLATED)
            self.assertLess(z.getinfo("root.dmg").compress_size, len(data))
        report = ins.inspect(path, with_sha256=True)
        self.assertFalse(report["components"]["OS"][0]["stored"])
        self.assertEqual(report["member_sha256"]["root.dmg"], hashlib.sha256(data).hexdigest())


class Der(unittest.TestCase):
    def test_roundtrip_short_and_long_lengths(self):
        for size in (0, 1, 127, 128, 255, 256, 70000):
            with self.subTest(size=size):
                blob = der(0x04, b"z" * size)
                tag, start, end = ins.der_element(blob, 0)
                self.assertEqual((tag, end - start, end), (0x04, size, len(blob)))

    def test_truncated_and_overlong_elements_are_refused(self):
        blob = der(0x04, b"z" * 300)
        for cut in (0, 1, 2, 3, 100, len(blob) - 1):
            with self.subTest(cut=cut):
                with self.assertRaises(ins.InspectError):
                    ins.der_element(blob[:cut], 0)

    def test_indefinite_and_oversized_length_forms_are_refused(self):
        with self.assertRaises(ins.InspectError):
            ins.der_element(b"\x30\x80\x00\x00", 0)
        with self.assertRaises(ins.InspectError):
            ins.der_element(b"\x30\x85\x01\x00\x00\x00\x00", 0)
        with self.assertRaises(ins.InspectError):
            ins.der_element(b"\x1f\x01\x00", 0)

    def test_child_may_not_run_past_its_parent(self):
        blob = der(0x30, der(0x04, b"abcd"))
        with self.assertRaises(ins.InspectError):
            ins.der_element(blob, 2, end=5)

    def test_im4p_fields(self):
        blob = im4p(b"payload", extra=der(0x30, der(0x02, b"\x01") + der(0x02, b"\x00\xff")))
        parsed = ins.parse_im4p(blob)
        self.assertEqual((parsed["kind"], parsed["description"]), ("krnl", "synthetic-kernelcache"))
        self.assertEqual(blob[slice(*parsed["payload"])], b"payload")
        self.assertEqual(parsed["compression"], {"algorithm_id": 1, "uncompressed_size": 255})
        self.assertFalse(parsed["key_bag"])

    def test_non_im4p_input_is_refused(self):
        valid_body = der(0x16, b"IM4P") + der(0x16, b"krnl") + der(0x16, b"d") + der(0x04, b"p")
        self.assertEqual(ins.parse_im4p(der(0x30, valid_body))["kind"], "krnl")
        for blob in (der(0x31, valid_body), b"", b"\x30\x00", der(0x30, der(0x16, b"IM4R") + der(0x16, b"a") + der(0x16, b"b") + der(0x04, b"")),
                     der(0x04, b"IM4P"), der(0x30, der(0x16, b"IM4P") + der(0x16, b"a") + der(0x16, b"b") + der(0x05, b""))):
            with self.subTest(blob=blob[:12]):
                with self.assertRaises(ins.InspectError):
                    ins.parse_im4p(blob)


class KernelBanner(TempCase):
    def test_raw_payload_banner_and_container(self):
        out = ins.kernelcache_banner(im4p(kernel_payload()))
        self.assertEqual(out["banner"], BANNER.decode())
        self.assertEqual(out["xnu"], "xnu-0000.1~1")
        self.assertEqual(out["kernel_config"], "RELEASE_ARM64_TESTCHIP")
        self.assertEqual(out["container"]["container"], "thin")
        self.assertEqual(out["container"]["macho"]["cputype"], "0x100000c")
        self.assertEqual(out["im4p_description"], "synthetic-kernelcache")

    def test_lzfse_wrapped_payload_is_decoded_to_the_banner(self):
        out = ins.kernelcache_banner(im4p(lzfse_raw(kernel_payload())))
        self.assertEqual(out["banner"], BANNER.decode())
        self.assertFalse(out["decoded_complete"], "the NUL after the banner lets the decoder stop before bvx$")

    def test_fat_container_is_described(self):
        thin = kernel_payload()
        fat = b"\xca\xfe\xba\xbe" + struct.pack(">I", 1) + struct.pack(">iiIII", 0x0100000C, 0, 28, len(thin), 14)
        fat += b"\0" * (28 - len(fat)) + thin
        out = ins.kernelcache_banner(im4p(fat))
        self.assertEqual(out["container"]["container"], "fat")
        self.assertEqual(out["container"]["slices"][0]["offset"], 28)
        self.assertEqual(out["banner"], BANNER.decode())

    def test_decoder_stops_after_the_banner_in_a_long_stream(self):
        first = b"\0" * 5000 + BANNER + b"\0"
        stream = (b"bvx-" + struct.pack("<I", len(first)) + first
                  + b"bvx-" + struct.pack("<I", 1000) + b"\1" * 1000 + b"bvx$")
        out = ins.kernelcache_banner(im4p(stream))
        self.assertEqual(out["banner"], BANNER.decode())
        self.assertFalse(out["decoded_complete"])
        self.assertEqual(out["decoded_prefix_bytes"], len(first))

    def test_banner_split_over_two_blocks_is_found(self):
        cut = 30
        a = b"\0" * 100 + BANNER[:cut]
        b = BANNER[cut:] + b"\0" + b"pad"
        stream = (b"bvx-" + struct.pack("<I", len(a)) + a + b"bvx-" + struct.pack("<I", len(b)) + b + b"bvx$")
        self.assertEqual(ins.kernelcache_banner(im4p(stream))["banner"], BANNER.decode())

    def test_banner_prefix_split_over_blocks_still_stops_the_decoder_early(self):
        # "Darwin Ker|nel Version ...": the search must re-scan the previous block's tail, otherwise the decoder
        # would run to the end of a 50 MB stream before the final search finds the text.
        cut = 10
        a = b"\0" * 100 + BANNER[:cut]
        b = BANNER[cut:] + b"\0"
        c = b"\1" * 500
        stream = (b"bvx-" + struct.pack("<I", len(a)) + a + b"bvx-" + struct.pack("<I", len(b)) + b
                  + b"bvx-" + struct.pack("<I", len(c)) + c + b"bvx$")
        out = ins.kernelcache_banner(im4p(stream))
        self.assertEqual(out["banner"], BANNER.decode())
        self.assertFalse(out["decoded_complete"])
        self.assertEqual(out["decoded_prefix_bytes"], len(a) + len(b))

    def test_unterminated_banner_is_not_reported_as_complete(self):
        out = ins.kernelcache_banner(im4p(lzfse_raw(b"\0" * 10 + BANNER)))
        # the stream ends right after the text with no NUL: the decoder reads to the end and reports what it saw
        self.assertEqual(out["banner"], BANNER.decode())
        self.assertTrue(out["decoded_complete"])

    def test_no_banner(self):
        out = ins.kernelcache_banner(im4p(lzfse_raw(thin_macho_header() + b"\0" * 64)))
        self.assertIsNone(out["banner"])

    def test_key_bag_is_not_decrypted(self):
        out = ins.kernelcache_banner(im4p(b"\xde\xad" * 16, extra=der(0x04, b"kbag")))
        self.assertTrue(out["key_bag"])
        self.assertIsNone(out["banner"])

    def test_unknown_payload_and_damaged_stream_are_errors(self):
        with self.assertRaises(ins.InspectError):
            ins.kernelcache_banner(im4p(b"MZ\x90\x00 not a mach-o"))
        with self.assertRaises(ins.InspectError):
            ins.kernelcache_banner(im4p(b"bvx2" + b"\0" * 20))
        with self.assertRaises(ins.InspectError):
            ins.kernelcache_banner(im4p(b"bvx1" + b"\0" * 20))

    def test_oversized_kernelcache_member_is_not_read_into_memory(self):
        path = write_ipsw(self.dir / "t.ipsw", members={"kernelcache.bin": im4p(lzfse_raw(kernel_payload()))})
        saved = ins.MAX_KERNELCACHE_BYTES
        ins.MAX_KERNELCACHE_BYTES = 16
        try:
            report = ins.inspect(path, with_kernel=True)
        finally:
            ins.MAX_KERNELCACHE_BYTES = saved
        self.assertEqual(report["verdict"], "accepted")
        self.assertIn("larger than", report["kernelcache"]["error"])

    def test_report_carries_the_kernel_section_and_failures_do_not_change_the_verdict(self):
        good = write_ipsw(self.dir / "good.ipsw", members={"kernelcache.bin": im4p(lzfse_raw(kernel_payload()))})
        report = ins.inspect(good, with_kernel=True)
        self.assertEqual(report["verdict"], "accepted")
        self.assertEqual(report["kernelcache"]["banner"], BANNER.decode())
        bad = write_ipsw(self.dir / "bad.ipsw")
        report = ins.inspect(bad, with_kernel=True)
        self.assertEqual(report["verdict"], "accepted")
        self.assertIn("error", report["kernelcache"])
        self.assertNotIn("kernelcache", ins.inspect(good))


class Cli(TempCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ins.main([str(a) for a in argv])
        return code, out.getvalue()

    def test_accepted_exit_zero_and_json(self):
        path = write_ipsw(self.dir / "t.ipsw", members={"kernelcache.bin": im4p(lzfse_raw(kernel_payload()))})
        code, text = self.run_main(path, "--json", "--sha256", "--kernel")
        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertEqual(report["verdict"], "accepted")
        self.assertEqual(report["archive_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_rejections_exit_nonzero_and_text_says_not_assessed(self):
        path = write_ipsw(self.dir / "t.ipsw", plist=manifest(build="x"))
        code, text = self.run_main(path)
        self.assertEqual(code, 2)
        self.assertIn("verdict: wrong-build", text)
        self.assertIn("not-assessed", text)

    def test_expectations_can_be_overridden(self):
        path = write_ipsw(self.dir / "t.ipsw", plist=manifest(build="X1", products=("iPhone99,1",), classes=("zz",)))
        code, _ = self.run_main(path, "--build", "X1", "--product-type", "iPhone99,1", "--device-class", "zz")
        self.assertEqual(code, 0)

    def test_kernel_failure_is_a_distinct_exit_code(self):
        path = write_ipsw(self.dir / "t.ipsw")
        code, _ = self.run_main(path, "--kernel")
        self.assertEqual(code, 3)

    def test_unsafe_names_never_reach_the_filesystem(self):
        path = self.dir / "slip.ipsw"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("BuildManifest.plist", plistlib.dumps(manifest()))
            z.writestr(zipfile.ZipInfo("../escaped.txt"), b"x")
        self.run_main(path, "--sha256", "--kernel")
        self.assertFalse((self.dir.parent / "escaped.txt").exists())
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["slip.ipsw"])


if __name__ == "__main__":
    unittest.main()
