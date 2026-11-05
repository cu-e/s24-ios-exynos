"""Input diagnostics must not confuse SDK labels, file presence or source reports with a build."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build/describe_kernel_inputs.py"
spec = importlib.util.spec_from_file_location("describe_kernel_inputs", SCRIPT)
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)
PROFILE = json.loads((ROOT / "fixtures/public/xnu-build-inputs/profile.json").read_text())


class KernelInputTests(unittest.TestCase):
    def test_theos_label_can_have_16_4_metadata_without_claiming_abi(self):
        with tempfile.TemporaryDirectory() as td:
            sdk = Path(td) / "iPhoneOS16.5.sdk"
            (sdk / "usr/include").mkdir(parents=True)
            (sdk / "System/Library/Frameworks").mkdir(parents=True)
            data = json.dumps({"Version": "16.4", "CanonicalName": "iphoneos16.4"}).encode()
            (sdk / "SDKSettings.json").write_bytes(data)
            report = inputs.sdk_observation(sdk, hashlib.sha256(data).hexdigest())
            self.assertEqual(report["version"], "16.4")
            self.assertTrue(report["matches_reviewed_metadata_only"])
            self.assertFalse(report["sdk_abi_verified"])
            self.assertFalse(report["complete_sdk_verified"])
            self.assertNotIn("error", report)

    def test_empty_or_malformed_sdk_files_are_not_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            sdk = Path(td)
            for data in [b"[1]", b"{", b" " * 65537]:
                (sdk / "SDKSettings.json").write_bytes(data)
                self.assertIn("error", inputs.sdk_observation(sdk, "unused"))
            archive = sdk / "libpthread_kext.a"
            archive.touch()
            self.assertFalse(inputs.file_observation(archive)["present"])

    def test_changed_prepared_source_cannot_reuse_a_pass_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            names = ["config/MASTER.arm64.e1s", "pexpert/pexpert/arm64/E1S.h"]
            for name in names:
                f = root / "xnu" / name
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b"changed")
            (root / "report.json").write_text(json.dumps({"outcome": "pass",
                "provenance": [{"id": k, "revision": v} for k, v in PROFILE["kernel_source_pins"].items()],
                "required_files": {name: hashlib.sha256(b"original").hexdigest() for name in names}}))
            args = argparse.Namespace(tools=root, sdk=None, theos=root, overlay=None,
                                      driverkit_headers=None, prepared_run=root)
            with patch.object(inputs, "tool_observation", return_value={"pin_verified": True}):
                report = inputs.describe(args, PROFILE)
            self.assertFalse(report["prepared_source"]["source_preparation_verified"])
            self.assertIn("bytes changed", report["prepared_source"]["error"])
            self.assertFalse(report["kernel_compiled"])

    def test_path_compiler_does_not_satisfy_donor_absolute_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = argparse.Namespace(tools=root, sdk=None, theos=root, overlay=None,
                                      driverkit_headers=None, prepared_run=None)
            profile = dict(PROFILE, wrapper_absolute_compilers=[str(root / "absent-clang")])
            with patch.object(inputs, "tool_observation", return_value={"pin_verified": True}), \
                 patch.object(inputs.shutil, "which", return_value="/available/path/compiler"):
                report = inputs.describe(args, profile)
            self.assertTrue(report["host_commands"]["clang"])
            self.assertFalse(report["absolute_compilers"][str(root / "absent-clang")]["present"])
            self.assertTrue(any("Donor absolute compiler" in item for item in report["missing_inputs"]))
            self.assertEqual(report["outcome"], "blocked")

    def test_cli_never_sources_untrusted_setup_or_environment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sentinel = root / "executed"
            (root / "xnu-deps").mkdir()
            for script in [root / "xnu-env.sh", root / "xnu-deps/setup.sh", root / "xnu-build.sh"]:
                script.write_text("#!/bin/sh\ntouch '" + str(sentinel) + "'\n")
                script.chmod(0o755)
            run = subprocess.run(["python3", str(SCRIPT), "--tools", str(root)], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 2, run.stderr)
            report = json.loads(run.stdout)
            self.assertFalse(report["tools"]["pin_verified"])
            self.assertFalse(report["upstream_setup_executed"])
            self.assertFalse(report["device_executed"])
            self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
