#!/usr/bin/env python3
"""Light console controls; all generated console bytes are labeled test inputs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("console", ROOT / "tools/build/avf_guest_console.py")
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class ConsoleControls(unittest.TestCase):
    def diagnostic(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authored-test-input.txt"
            path.write_text(text, encoding="utf-8")
            return console.diagnose(path)

    def test_genuine_source_preflight(self):
        result = console.preflight(Path("/home/egor/dev/pet/s24-ios-exynos"))
        self.assertEqual(len(result["console_objects"]), 5)
        self.assertEqual(result["kernel_execution"], "unmeasured")

    def test_altered_source_pin_rejected(self):
        pins = json.loads(console.PINS.read_text())
        pins["files"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-pins.json"
            path.write_text(json.dumps(pins))
            with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                console.preflight(Path("/home/egor/dev/pet/s24-ios-exynos"), pins_path=path)

    def test_marker_poison_rejected(self):
        pins = json.loads(console.PINS.read_text())
        pins["files"][0]["facts"][0]["text"] = "fabricated source fact"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-facts.json"
            path.write_text(json.dumps(pins))
            with self.assertRaisesRegex(ValueError, "source fact mismatch"):
                console.preflight(Path("/home/egor/dev/pet/s24-ios-exynos"), pins_path=path)

    def test_conflicting_or_silent_boot_args_rejected(self):
        for value in (console.DEFAULT_ARGS + " serial=0", "debug=0x8 serial=3",
                      console.DEFAULT_ARGS.replace("-enable_kprintf_spam ", ""),
                      console.DEFAULT_ARGS.replace("serial=3", "serial=67"),
                      console.DEFAULT_ARGS.replace("console_quiet=0", "console_quiet=1")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                console.boot_args(value)

    def test_synthetic_fixture_never_kernel_success(self):
        text = "VM005 SYNTHETIC PASS\nDarwin Kernel Version 22.5.0: spoofed\n"
        result = self.diagnostic(text)
        self.assertEqual(result["classification"], "rejected-synthetic-input")
        self.assertFalse(result["genuine_kernel_success"])

    def test_banner_alone_is_unverified(self):
        result = self.diagnostic("Darwin Kernel Version 22.5.0: authored test\n")
        self.assertEqual(result["classification"], "kernel-like-text-observed-unverified")
        self.assertFalse(result["genuine_kernel_success"])
        self.assertFalse(result["pid1_success"])

    def test_shim_claim_of_xnu_is_only_shim_text(self):
        result = self.diagnostic("avfboot: HakiOS XNU boot for crosvm/AVF and QEMU virt\n"
                                 "avfboot: jumping to XNU at 0xfffffff007004000\n")
        self.assertEqual(result["classification"], "shim-handoff-text-only")

    def test_reordered_markers_rejected(self):
        result = self.diagnostic("Darwin Kernel Version 22.5.0: authored test\n"
                                 "kprintf initialized\n")
        self.assertEqual(result["classification"], "inconsistent-marker-order")

    def test_fatal_survives_later_banner(self):
        result = self.diagnostic("avfboot: FATAL: bad image\n"
                                 "Darwin Kernel Version 22.5.0: authored test\n")
        self.assertEqual(result["classification"], "failure-observed")

    def test_overlong_line_rejected(self):
        with self.assertRaisesRegex(ValueError, "line exceeds"):
            self.diagnostic("x" * 65537)

    def test_synthetic_line_storage_is_bounded(self):
        result = self.diagnostic("SYNTHETIC\n" * 100)
        self.assertEqual(result["synthetic_count"], 100)
        self.assertEqual(len(result["synthetic_lines"]), 32)


if __name__ == "__main__":
    unittest.main(verbosity=2)
