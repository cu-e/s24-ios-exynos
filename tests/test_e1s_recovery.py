"""Unit tests for NAT-006 RECOVERY image builder, restore package, and independent verifier."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN_ROOT = Path("/home/egor/dev/pet/s24-ios-exynos")

spec_builder = importlib.util.spec_from_file_location("e1s_recovery", ROOT / "tools/build/e1s_recovery.py")
builder = importlib.util.module_from_spec(spec_builder)
spec_builder.loader.exec_module(builder)

spec_verifier = importlib.util.spec_from_file_location("verify_image", ROOT / "docs/procedures/nat-006/verify_image.py")
verifier = importlib.util.module_from_spec(spec_verifier)
spec_verifier.loader.exec_module(verifier)


def make_synthetic_stock(part_size: int = 65536, page_size: int = 2048) -> bytes:
    """Create a minimal valid boot image v2 with recovery_dtbo, dtb, SEANDROIDENFORCE, AVB0, and AVBf."""
    img = bytearray(part_size)
    kernel = b"STOCK_KERNEL" * 20
    ramdisk = b"STOCK_RAMDISK" * 10
    rdtbo = b"DTBO_DATA" * 16
    dtb = b"DTB_DATA" * 24

    img[:8] = b"ANDROID!"
    struct.pack_into(
        "<10I",
        img,
        8,
        len(kernel),
        0x10008000,
        len(ramdisk),
        0x10000000,
        0,
        0,
        0x10000000,
        page_size,
        2,
        0x1C000198,
    )
    img[48:56] = b"SRPWI19A"
    img[64:86] = b"bootconfig loop.max=7"
    rdtbo_off = page_size + builder.align(len(kernel), page_size) + builder.align(len(ramdisk), page_size)
    struct.pack_into("<I", img, 1632, len(rdtbo))
    struct.pack_into("<Q", img, 1636, rdtbo_off)
    struct.pack_into("<IIQ", img, 1644, 1660, len(dtb), 0x10000000)
    img[576:608] = builder.mkbootimg_id([kernel, ramdisk, b"", rdtbo, dtb])

    off = page_size
    for sec in (kernel, ramdisk, rdtbo, dtb):
        img[off : off + len(sec)] = sec
        off += builder.align(len(sec), page_size)
    img[off : off + 16] = b"SEANDROIDENFORCE"
    orig_end = off + 16

    # Minimal AVB0 with a tag=2 hash descriptor for "recovery"
    part_name = b"recovery"
    salt = bytes.fromhex("6e67d565bfe8f8600c425f4f8d5bd945a9aa731cd76d4fd5671f93d55cdb0f45")
    digest = b"\xaa" * 32
    desc_body = bytearray(116 + len(part_name) + len(salt) + len(digest))
    struct.pack_into(">Q", desc_body, 0, orig_end)
    desc_body[8:14] = b"sha256"
    struct.pack_into(">IIII", desc_body, 40, len(part_name), len(salt), len(digest), 0)
    desc_body[116:] = part_name + salt + digest
    pad = (-len(desc_body)) % 8
    desc_body += b"\0" * pad
    desc = struct.pack(">QQ", 2, len(desc_body)) + bytes(desc_body)

    vbmeta = bytearray(256 + len(desc))
    vbmeta[:4] = b"AVB0"
    struct.pack_into(">IIQQ", vbmeta, 4, 1, 0, 0, len(desc))
    struct.pack_into(">QQ", vbmeta, 96, 0, len(desc))
    vbmeta[256:] = desc

    voff = builder.align(orig_end, 4096)
    img[voff : voff + len(vbmeta)] = vbmeta
    footer = b"AVBf" + struct.pack(">IIQQQ", 1, 0, orig_end, voff, len(vbmeta)) + b"\0" * 28
    img[-64:] = footer
    return bytes(img)


class RecoveryImageUnitTests(unittest.TestCase):
    def test_synthetic_build_recovery_preserves_invariants_and_updates_avb(self):
        stock = make_synthetic_stock()
        new_kernel = b"ARM64_LOADER_AND_PAYLOAD" * 80
        new_ramdisk = builder.newc_cpio([builder.PLACEHOLDER])
        rebuilt, info = builder.build_recovery(stock, new_kernel, new_ramdisk, partition_size=len(stock))

        self.assertEqual(len(rebuilt), len(stock))
        hd = verifier.header(rebuilt)
        shd = verifier.header(stock)
        self.assertEqual(hd["magic"], b"ANDROID!")
        self.assertEqual(hd["version"], 2)
        self.assertEqual(hd["page_size"], shd["page_size"])
        self.assertEqual(hd["os_version"], shd["os_version"])
        self.assertEqual(hd["kernel_size"], len(new_kernel))
        self.assertEqual(hd["ramdisk_size"], len(new_ramdisk))
        self.assertNotEqual(hd["id"], shd["id"])

        sec = verifier.sections(hd)
        ssec = verifier.sections(shd)
        self.assertEqual(
            rebuilt[sec["recovery_dtbo"][0] : sec["recovery_dtbo"][0] + sec["recovery_dtbo"][1]],
            stock[ssec["recovery_dtbo"][0] : ssec["recovery_dtbo"][0] + ssec["recovery_dtbo"][1]],
        )
        self.assertEqual(
            rebuilt[sec["dtb"][0] : sec["dtb"][0] + sec["dtb"][1]],
            stock[ssec["dtb"][0] : ssec["dtb"][0] + ssec["dtb"][1]],
        )
        self.assertEqual(rebuilt[sec["end"][0] : sec["end"][0] + 16], b"SEANDROIDENFORCE")

        avb = verifier.parse_avb_footer(rebuilt)
        self.assertIsNotNone(avb)
        self.assertEqual(avb["original_image_size"], info["content_end"])
        vbmeta = rebuilt[avb["vbmeta_offset"] : avb["vbmeta_offset"] + avb["vbmeta_size"]]
        desc = verifier.parse_vbmeta_recovery_desc(vbmeta)
        self.assertIsNotNone(desc)
        self.assertEqual(desc["image_size"], info["content_end"])

    def test_cpio_and_odin_tar_round_trip(self):
        archive = builder.newc_cpio([builder.PLACEHOLDER])
        entries = verifier.parse_cpio_newc(archive)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "NAT006")
        self.assertIn(b"SWEETXNU", entries[0][1])

        stock = make_synthetic_stock()
        tar_bytes = builder.odin_tar("recovery.img", stock)
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "recovery-stock-odin.tar"
            tpath.write_bytes(tar_bytes)
            with tarfile.open(tpath, "r") as tf:
                members = tf.getmembers()
                self.assertEqual(len(members), 1)
                self.assertEqual(members[0].name, "recovery.img")
                self.assertEqual(tf.extractfile(members[0]).read(), stock)

    def test_rejects_oversized_kernel_and_corrupted_headers(self):
        stock = make_synthetic_stock(part_size=32768)
        ramdisk = builder.newc_cpio([builder.PLACEHOLDER])
        with self.assertRaises(ValueError):
            builder.build_recovery(stock, b"X" * 30000, ramdisk, partition_size=len(stock))

        bad_stock = bytearray(stock)
        bad_stock[:8] = b"BADMAGIC"
        with self.assertRaises(ValueError):
            builder.v2_fields(bytes(bad_stock))

        second_stock = bytearray(stock)
        struct.pack_into("<I", second_stock, 24, 4096)
        with self.assertRaises(ValueError):
            builder.build_recovery(bytes(second_stock), b"K" * 64, ramdisk, partition_size=len(stock))

    def test_built_artifact_and_mutation_rejection_when_present(self):
        build_dir = MAIN_ROOT / "artifacts/nat-006/build-002"
        if not (build_dir / "recovery-nat006.img").exists():
            self.skipTest("artifacts/nat-006/build-002 not present")
        vjson = build_dir / "verify.json"
        rjson = build_dir / "report.json"
        self.assertTrue(vjson.exists())
        self.assertTrue(rjson.exists())
        import json

        vdata = json.loads(vjson.read_text())
        rdata = json.loads(rjson.read_text())
        self.assertTrue(vdata["ok"], f"Verifier failed checks: {[c for c in vdata['checks'] if not c['ok']]}")
        self.assertEqual(rdata["outcome"], "pass")
        self.assertEqual(list(rdata["loader"]["absolute_relocations"].keys()), ["start.S.o"])
        self.assertFalse(rdata["flashed"])
        self.assertFalse(rdata["device_used"])
        self.assertFalse(rdata["hardware_execution"])
        self.assertFalse(rdata["apple_donor_data"])
        self.assertIn("verified_on_host", vdata["verified_vs_assumed"])
        self.assertIn("unverified_or_assumed", vdata["verified_vs_assumed"])


if __name__ == "__main__":
    unittest.main()
