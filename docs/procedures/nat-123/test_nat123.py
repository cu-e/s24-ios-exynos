#!/usr/bin/env python3
"""Host-only execution of the patched ACPM/PMIC C against a synthetic APM.

The fake peer is not hardware evidence. Each case runs in a fresh process.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PATCH_DIR = Path(os.environ.get('NAT123_PATCH_DIR', str(HERE)))
ROOT = HERE.parents[2]
DONOR = ROOT / "worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd"


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nat123-", dir=os.environ.get("TMPDIR"))
        cls.work = Path(cls.tmp.name)
        (cls.work / "sys").mkdir()
        (cls.work / "sys/e1s_pmic.h").write_bytes((DONOR / "sys/e1s_pmic.h").read_bytes())
        for name in ("e1s_acpm", "e1s_pmic"):
            target = cls.work / (name + ".c")
            target.write_bytes((DONOR / "dev" / target.name).read_bytes())
            subprocess.run(["patch", "--no-backup-if-mismatch", "-s", str(target), str(PATCH_DIR / (name + ".patch"))], check=True)
            text = "\n".join(line for line in target.read_text().splitlines() if not line.startswith("#include <"))
            target.write_text('#include "shim.h"\n#include "sys/e1s_pmic.h"\n' + text + '\n')
        cls.exe = cls.work / "test"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Werror", "-Wno-format", "-Wno-unused-parameter",
                        "-I", str(HERE / "host"), "-I", str(cls.work), str(cls.work / "e1s_acpm.c"),
                        str(cls.work / "e1s_pmic.c"), str(HERE / "host/fakeapm.c"), str(HERE / "host/main.c"),
                        "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, case="normal", mode=2):
        return subprocess.run([str(self.exe), str(mode), case], check=True, text=True,
                              capture_output=True, timeout=10).stdout

    def test_two_rails_verified(self):
        out = self.run_case()
        self.assertIn("writes=2 bad=0 ldo9=0xf0 ldo18=0xd8", out)
        self.assertIn("touch rails are on", out)

    def test_transport_and_preread_failures_do_not_write(self):
        for case in ("rail-read-error", "chip-error", "wrong-sequence", "no-response"):
            with self.subTest(case=case):
                out = self.run_case(case)
                self.assertIn("writes=0 ", out)
                self.assertNotIn("touch rails are on", out)

    def test_invalid_channel_metadata_sends_nothing(self):
        for case in ("bad-pointer", "bad-type", "bad-id", "bad-queue"):
            with self.subTest(case=case):
                self.assertIn("cmds=0 writes=0", self.run_case(case))

    def test_already_enabled_wrong_voltage_is_not_success(self):
        out = self.run_case("already-wrong")
        self.assertIn("writes=0 ", out)
        self.assertNotIn("touch rails are on", out)

    def test_wrong_identity_refuses_writes(self):
        self.assertIn("writes=0 ", self.run_case("chip-other"))

    def test_zero_identity_refuses_writes(self):
        self.assertIn("writes=0 ", self.run_case("chip-zero"))

    def test_forbidden_transport_writes_are_not_sent(self):
        self.assertIn("writes=0 bad=0", self.run_case("forbidden", mode=1))

    def test_mode3_never_writes(self):
        self.assertIn("writes=0 ", self.run_case(mode=3))

    def test_readback_mismatch_stops_before_second_rail(self):
        out = self.run_case("readback-mismatch")
        self.assertIn("writes=1 ", out)
        self.assertNotIn("touch rails are on", out)

    def test_readback_error_stops_before_second_rail(self):
        out = self.run_case("readback-error")
        self.assertIn("writes=1 ", out)
        self.assertNotIn("touch rails are on", out)


class AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location('nat123_analyzer_test', HERE / 'analyze124.py')
        cls.analyzer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.analyzer)
        cls.text = (ROOT / 'artifacts/nat-122/analysis/kernel-text.txt').read_text(errors='replace')
        cls.pixels = json.loads((ROOT / 'artifacts/nat-122/analysis/pixels.json').read_text())

    def test_actual_nat122_does_not_prove_power(self):
        result = self.analyzer.classify(self.text, self.pixels)
        self.assertEqual(result['power'], 'P0-no-verified-rails')
        self.assertEqual(result['physical_input'], 'not-established')

    def test_actual_host_log_proves_only_synthetic_rail_state(self):
        TransportTests.setUpClass()
        try:
            out = subprocess.run([str(TransportTests.exe), '2', 'normal'], check=True,
                                 text=True, capture_output=True).stdout
        finally:
            TransportTests.tearDownClass()
        result = self.analyzer.classify(self.text + '\n' + out, self.pixels)
        self.assertEqual(result['power'], 'P2-both-rails-verified')
        self.assertEqual(result['physical_input'], 'not-established')
        result = self.analyzer.classify(self.text + '\n' + out.replace('-> 0xd8)', '-> 0xd9)'), self.pixels)
        self.assertNotEqual(result['power'], 'P2-both-rails-verified')
        result = self.analyzer.classify(self.text + '\n' + out + '\nread-back failed', self.pixels)
        self.assertEqual(result['power'], 'P1-refused-or-unverified')


if __name__ == "__main__":
    unittest.main(verbosity=2)
