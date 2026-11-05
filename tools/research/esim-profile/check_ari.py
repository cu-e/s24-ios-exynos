#!/usr/bin/env python3
"""Exercise pinned libari only on owned offline bytes, never a device or trace."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import sources

PIN = "25cb9bb5c35993ed0c74248b96f0065d5479f447"
# Independently specified header and two nonempty TLVs. No capture, subscription
# identifiers, activation data or actual modem command is used.
WIRE = bytes.fromhex("dec07eab284e1f00455568240e400c00a1b2c302211000deadbeef")


class WireTests(unittest.TestCase):
    def test_mutable_payload_input_is_copied_and_parsed(self):
        for use_view in [False, True]:
            data = bytearray([0xA1, 0xB2, 0xC3])
            tlv = TLV(id=7, version=2, data=memoryview(data) if use_view else data)
            data[0] = 0
            self.assertEqual(bytes(tlv._data), bytes.fromhex("a1b2c3"))
            for wire in [bytearray(WIRE), memoryview(WIRE)]:
                self.assertEqual(bytes(Packet.fromBytes(wire).tlvs[0]._data), bytes.fromhex("a1b2c3"))

    def test_independent_nonempty_tlvs_and_split_sequence_bits(self):
        packet = Packet.fromBytes(WIRE)
        self.assertEqual((packet.group, packet.seq, packet.message_id, packet.trx, packet.length),
                         (5, 0x5a7, 0x155, 0x1234, 15))
        self.assertEqual([(v.id, v.version, bytes(v._data)) for v in packet.tlvs],
                         [(7, 2, bytes.fromhex("a1b2c3")), (129, 1, bytes.fromhex("deadbeef"))])
        self.assertEqual(bytes(packet.pack()), WIRE)

    def test_every_truncated_prefix_rejects_instead_of_partial_success(self):
        for size in range(len(WIRE)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                Packet.fromBytes(WIRE[:size])

    def test_magic_declared_extent_and_tlv_extents_are_checked(self):
        bad_magic = b"xxxx" + WIRE[4:]
        short_tlv_payload = bytes.fromhex("dec07eab00000a000000000002000800aa")
        short_tlv_header = bytes.fromhex("dec07eab000002000000000000")
        for wire in [bad_magic, WIRE + b"x", short_tlv_payload, short_tlv_header]:
            with self.subTest(wire=wire.hex()), self.assertRaises(ValueError):
                Packet.fromBytes(wire)

    def test_tlv_length_high_bits_across_encoding_boundaries(self):
        for size in [0, 1, 63, 64, 255, 256, 16383]:
            with self.subTest(size=size):
                data = bytes([0xA5]) * size
                encoded = TLV(id=1, version=0, data=data).pack()
                self.assertEqual(bytes(encoded[:4]), bytes([2, 0, (size & 63) << 2, size >> 6]))
                self.assertEqual(bytes(encoded[4:]), data)
                packet = Packet()
                packet.addTLV(TLV(id=1, version=0, data=data))
                decoded = Packet.fromBytes(packet.pack())
                self.assertEqual(bytes(decoded.tlvs[0]._data), data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--apply-patch", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Invalid unique run name")
    entries = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    entry = next(s for s in entries if s["id"] == "aristoteles")
    if entry["revision"] != PIN:
        raise ValueError("Use the exact reviewed donor")
    provenance = sources.verify(ROOT, entry)
    out = ROOT / "artifacts/esim-profile" / args.run
    if out.resolve() != out:
        raise ValueError("Run path cannot use symlinks")
    out.mkdir(parents=True, exist_ok=False)
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    donor = out / "donor"
    shutil.copytree(ROOT / "references/aristoteles", donor, ignore=shutil.ignore_patterns(".git"))
    report = {"kind": "host-test", "origin": "local-host", "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "outcome": "inconclusive", "provenance": [provenance], "commands": [],
              "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "patch_applied": args.apply_patch, "python": sys.version.split()[0],
              "fixture_sha256": hashlib.sha256(WIRE).hexdigest(), "actual_ios_components_supplied": False,
              "ios16_5_abi_qualified": False, "device_executed": False, "network_or_profile_operation": False}

    def command(argv, label):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
        log = out / (label + ".txt")
        log.write_text(result.stdout + result.stderr)
        report["commands"].append({"argv": list(map(str, argv)), "exit_code": result.returncode,
                                   "log": str(log.relative_to(ROOT)), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
        if result.returncode:
            raise RuntimeError("Failed private patch command: " + label)

    try:
        if args.apply_patch:
            command(["git", "-c", "core.hooksPath=/dev/null", "-C", donor, "init", "--quiet"], "init")
            report["patches_sha256"] = {}
            for name in ["0001-libari-offline-framing-corrections.patch", "0002-libari-owned-byte-payload.patch"]:
                patch = ROOT / "patches/cellular/ari" / name
                report["patches_sha256"][name] = hashlib.sha256(patch.read_bytes()).hexdigest()
                command(["git", "-c", "core.hooksPath=/dev/null", "-C", donor, "apply", "--check", patch], name + "-check")
                command(["git", "-c", "core.hooksPath=/dev/null", "-C", donor, "apply", patch], name + "-apply")
        # Only the inspected pure-Python offline packet package is imported.
        # No watcher, Ghidra, Frida, capture, injection or replay code is loaded.
        sys.path.insert(0, str(donor / "tools/libari"))
        global Packet, TLV
        from libari.packet import Packet
        from libari.tlv import TLV
        upstream_path = donor / "tools/libari/tests/test_libari.py"
        spec = importlib.util.spec_from_file_location("reviewed_upstream_ari_tests", upstream_path)
        upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upstream)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(WireTests)
        for name in ["test_default_header_only_all_zero", "test_default_header_only_all_zero_and_zero_tlv"]:
            suite.addTest(unittest.FunctionTestCase(getattr(upstream, name)))
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        log = out / "tests.txt"
        log.write_text(stream.getvalue())
        report.update(outcome="pass" if result.wasSuccessful() else "fail", tests_run=result.testsRun,
                      failures=len(result.failures), errors=len(result.errors), tests_log=str(log.relative_to(ROOT)),
                      tests_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        report["tested_source_sha256"] = {name: hashlib.sha256((donor / name).read_bytes()).hexdigest()
                                          for name in ["tools/libari/libari/packet.py", "tools/libari/libari/tlv.py"]}
    except Exception as error:
        report.update(outcome="fail", error=str(error))
    report["limits"] = ["Owned offline wire cases only; no real Apple binary/table extraction or Samsung transport",
                       "No selected iPhone identity, eSIM frontend, entitlement, IOKit or CommCenter ABI qualification",
                       "Encoder APIs remain research utilities, not a validated general modem command serializer"]
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["outcome", "patch_applied", "ios16_5_abi_qualified"]}))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
