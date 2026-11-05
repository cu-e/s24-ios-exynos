"""Drive passive collector guards with a synthetic local ADB peer; no phone I/O."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ril_capture", ROOT / "tools/research/ril-capture/capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def owned_elf(machine=183):
    header = bytearray(192)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", header, 16, 3, machine, 1)
    struct.pack_into("<H", header, 52, 64)
    return bytes(header)


class Peer:
    def __init__(self, data=None, model=None, stat=None, mutate=False, changed_build=False, deny_hash=False, mutate_copy=False):
        self.data = owned_elf() if data is None else data
        self.model, self.stat, self.mutate, self.changed_build = model, stat, mutate, changed_build
        self.deny_hash, self.mutate_copy, self.copies = deny_hash, mutate_copy, 0
        self.calls, self.hash_reads, self.build_reads = [], 0, 0

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[-1] == "devices" or argv[-2:] == ["devices", "-l"]:
            return subprocess.CompletedProcess(argv, 0, "List of devices attached\nPRIVATE-ENDPOINT\tdevice model:SM_S921B device:e1s\n", "")
        tail = argv[3:]
        if tail[0] == "pull":
            self.copies += 1
            Path(tail[2]).write_bytes(self.data + b"x" if self.mutate_copy and self.copies > 1 else self.data)
            return subprocess.CompletedProcess(argv, 0, "PRIVATE-ENDPOINT: copied vendor code\n", "")
        script = tail[1]
        if script.startswith("getprop "):
            key = script.split()[1]
            result = capture.EXPECTED[key]
            if self.model and key == "ro.product.model":
                result = self.model
            if key == "ro.build.version.incremental":
                self.build_reads += 1
                if self.changed_build and self.build_reads > 1:
                    result = "DIFFERENT-FIRMWARE"
            return subprocess.CompletedProcess(argv, 0, result, "")
        if script == "id -u":
            return subprocess.CompletedProcess(argv, 0, "2000", "")
        if not script.endswith("/libsitril.so"):
            return subprocess.CompletedProcess(argv, 1, "", "unavailable")
        if script.startswith("stat "):
            return subprocess.CompletedProcess(argv, 0, self.stat or "regular file|" + str(len(self.data)), "")
        if script.startswith("sha256sum "):
            if self.deny_hash:
                return subprocess.CompletedProcess(argv, 1, "", "Permission denied")
            self.hash_reads += 1
            value = "f" * 64 if self.mutate and self.hash_reads > 1 else hashlib.sha256(self.data).hexdigest()
            return subprocess.CompletedProcess(argv, 0, value + "  /vendor/lib64/libsitril.so", "")
        raise AssertionError("Unexpected command")


class PassiveCaptureTests(unittest.TestCase):
    def test_optional_sync_reads_require_actual_duplicate_bytes_and_leave_remote_hash_unknown(self):
        for changed in [False, True]:
            peer = Peer(deny_hash=True, mutate_copy=changed)
            with tempfile.TemporaryDirectory() as directory:
                report = {"commands": [], "files": []}
                bridge = capture.Bridge("owned-fake-adb", Path(directory), report, runner=peer, sync_verify=True)
                if changed:
                    with self.assertRaises(ValueError):
                        capture.collect(bridge, report, Path(directory))
                else:
                    capture.collect(bridge, report, Path(directory))
                    record = next(f for f in report["files"] if f["status"] == "captured")
                    self.assertIsNone(record["remote_sha256_before"])
                    self.assertIsNone(record["remote_sha256_after"])
                    self.assertEqual(peer.copies, 2)
                    self.assertEqual(report["outcome"], "pass")

    def test_reference_selection_requires_unique_metadata_and_rechecks_properties(self):
        for suffix, expected in [("", True), ("OTHER device model:SM_S921B device:e1s\n", False)]:
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                text = "List of devices attached\nPRIVATE-ENDPOINT device model:SM_S921B device:e1s\nEMU device model:OTHER device:other\n" + suffix
                return subprocess.CompletedProcess(argv, 0, text, "")
            with tempfile.TemporaryDirectory() as directory:
                report = {"commands": []}
                bridge = capture.Bridge("owned-fake-adb", Path(directory), report, runner=runner, select_reference=True)
                if expected:
                    bridge.select()
                    self.assertEqual(bridge.endpoint, "PRIVATE-ENDPOINT")
                else:
                    with self.assertRaises(RuntimeError):
                        bridge.select()
                self.assertEqual(calls, [["owned-fake-adb", "devices", "-l"]])
        peer = Peer(model="SM-S928B")
        with tempfile.TemporaryDirectory() as directory:
            report = {"commands": [], "files": []}
            bridge = capture.Bridge("owned-fake-adb", Path(directory), report, runner=peer, select_reference=True)
            with self.assertRaises(ValueError):
                capture.collect(bridge, report, Path(directory))
            self.assertFalse(any("pull" in call for call in peer.calls))

    def perform(self, peer, directory):
        out = Path(directory)
        report = {"commands": [], "files": []}
        bridge = capture.Bridge("owned-fake-adb", out, report, runner=peer)
        capture.collect(bridge, report, out)
        return report

    def test_identity_hashes_and_header_are_real_checks_but_not_native_claims(self):
        peer = Peer()
        with tempfile.TemporaryDirectory() as directory:
            report = self.perform(peer, directory)
            self.assertEqual(report["outcome"], "pass")
            record = next(f for f in report["files"] if f["status"] == "captured")
            self.assertEqual(record["sha256"], hashlib.sha256(peer.data).hexdigest())
            self.assertEqual(record["elf"]["machine"], "AArch64")
            self.assertEqual((Path(directory) / "libsitril.so").stat().st_mode & 0o777, 0o600)
            all_saved = json.dumps(report) + "".join(p.read_text() for p in Path(directory).glob("*.txt"))
            self.assertNotIn("PRIVATE-ENDPOINT", all_saved)

    def test_wrong_device_stops_before_any_file_access(self):
        peer = Peer(model="SM-S928B")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            self.perform(peer, directory)
        self.assertFalse(any("pull" in call or any("stat -c" in a for a in call) for call in peer.calls))

    def test_nonregular_unbounded_and_unreadable_inputs_are_not_pulled(self):
        for stat in ["symbolic link|192", "regular file|0", "regular file|" + str(capture.MAX_BYTES + 1)]:
            peer = Peer(stat=stat)
            with self.subTest(stat=stat), tempfile.TemporaryDirectory() as directory:
                report = self.perform(peer, directory)
                self.assertEqual(report["outcome"], "inconclusive")
                self.assertFalse(any("pull" in call for call in peer.calls))

    def test_wrong_architecture_and_changed_remote_bytes_cannot_pass(self):
        for peer in [Peer(data=owned_elf(machine=62)), Peer(mutate=True), Peer(changed_build=True)]:
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                self.perform(peer, directory)

    def test_mutating_or_nonvendor_operations_rejected_before_runner(self):
        peer = Peer()
        with tempfile.TemporaryDirectory() as directory:
            bridge = capture.Bridge("owned-fake-adb", Path(directory), {"commands": []}, "PRIVATE-ENDPOINT", runner=peer)
            for script in ["su -c id", "setprop x y", "reboot", "cat /dev/umts_ipc0", "getprop", "ls /data"]:
                with self.assertRaises(ValueError):
                    bridge.shell(script)
            with self.assertRaises(ValueError):
                bridge.pull("/data/private", Path(directory) / "private")
            self.assertEqual(peer.calls, [])

    def test_ambiguous_or_unauthorized_endpoint_never_reads_properties(self):
        for rows in ["A\tdevice\nB\tdevice\n", "A\tunauthorized\n", ""]:
            calls = []
            def runner(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, "List of devices attached\n" + rows, "")
            with tempfile.TemporaryDirectory() as directory:
                bridge = capture.Bridge("owned-fake-adb", Path(directory), {"commands": []}, runner=runner)
                with self.assertRaises(RuntimeError):
                    bridge.select()
                self.assertEqual(calls, [["owned-fake-adb", "devices"]])


if __name__ == "__main__":
    unittest.main()
