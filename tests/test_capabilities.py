"""Prevent inventory, passing builds and upstream reports becoming native claims."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import capabilities


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = {"tasks": [{"id": "GPU-001"}]}
        self.sources = {"sources": [{"id": "radv"}]}
        self.data = {"schema_version": 1, "target": "SM-S921B/e1s/s5e9945", "capabilities": [{
            "id": "gpu", "title": "GPU", "implementation": "planned", "native_status": "not-tested",
            "tasks": ["GPU-001"], "sources": ["radv"], "upstream": "Author reports Vulkan on Android",
            "local_observation": "Android reports Xclipse 940", "acceptance": "Correct pixels on native XNU",
            "next_check": "Build the Android probe"}]}

    def tearDown(self):
        self.temp.cleanup()

    def check(self, data):
        return capabilities.validate(self.root, data, self.ledger, self.sources)

    def test_inventory_and_upstream_stay_separate_from_native(self):
        self.check(self.data)
        text = capabilities.render(self.root, self.data, self.ledger)
        self.assertIn("not-tested", text)
        self.assertNotIn("100%", text)

    def test_native_claim_without_native_evidence_is_rejected(self):
        for changes in [{"native_status": "verified"}, {"native_status": "partial"}, {"implementation": "native-tested"}]:
            d = copy.deepcopy(self.data)
            d["capabilities"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(capabilities.lab.LabError):
                self.check(d)

    def test_host_test_cannot_be_used_for_native_evidence(self):
        (self.root / "result.txt").write_text("synthetic host output")
        e = {"kind": "host-test", "origin": "local-host", "outcome": "pass", "recorded_at": "2026-11-05T00:00:00Z", "summary": "Host only", "artifacts": ["result.txt"]}
        capabilities.lab.atomic_json(self.root / "evidence.json", e)
        c = self.data["capabilities"][0]
        c.update(native_status="verified", native_evidence=[{"path": "evidence.json", "sha256": capabilities.lab.evidence_hash(self.root, "evidence.json")}])
        with self.assertRaises(capabilities.lab.LabError):
            self.check(self.data)

    def test_unknown_sources_tasks_duplicate_ids_and_unmeasured_tested_claims(self):
        for changes in [{"tasks": ["MISSING-999"]}, {"sources": ["missing"]}, {"implementation": "host-tested"}, {"implementation": "android-tested"}, {"acceptance": ""}]:
            d = copy.deepcopy(self.data)
            d["capabilities"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(capabilities.lab.LabError):
                self.check(d)
        self.data["capabilities"] *= 2
        with self.assertRaises(capabilities.lab.LabError):
            self.check(self.data)


if __name__ == "__main__":
    unittest.main()
