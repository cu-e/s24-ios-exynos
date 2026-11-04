"""Behavioral tests for coordination and evidence boundaries, without a phone."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/lab.py"
spec = importlib.util.spec_from_file_location("lab", SCRIPT)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def task(identifier, scope="host", kind="host-test", deps=None):
    return {"id": identifier, "title": identifier, "status": "pending", "owner": None,
            "scope": scope, "evidence_kind": kind, "depends_on": deps or [],
            "paths": ["tools/"], "acceptance": ["Measured outcome"], "sources": []}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ["state", "research", "artifacts", "docs", "tools"]:
            (self.root / name).mkdir()
        self.state = {"schema_version": 1, "updated_at": lab.now(),
                      "project": {"phase": "test", "permissions": {"host": True, "android-readonly": True, "android-app": False, "native": False}},
                      "tasks": [task("HOST-001"), task("HOST-002", deps=["HOST-001"]),
                                task("NAT-001", "native", "native-device")], "experiments": [], "events": []}
        lab.atomic_json(self.root / "research/sources.json", {"sources": []})
        (self.root / "docs/procedure.md").write_text("A real test procedure")
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        lab.atomic_json(self.root / "state/lab.json", self.state)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args], capture_output=True, text=True, timeout=15)

    def evidence(self, name="evidence.json", **changes):
        (self.root / "artifacts/result.txt").write_text("Actual fixture measurement")
        doc = {"kind": "host-test", "origin": "local-host", "outcome": "pass",
               "recorded_at": lab.now(), "summary": "Measured fixture", "artifacts": ["artifacts/result.txt"]}
        doc.update(changes)
        lab.atomic_json(self.root / "artifacts" / name, doc)
        return "artifacts/" + name

    def test_dependency_blocks_claim_and_does_not_mutate_state(self):
        before = (self.root / "state/lab.json").read_bytes()
        result = self.cli("task", "claim", "HOST-002", "--owner", "a")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

    def test_two_agents_cannot_claim_one_task(self):
        processes = [subprocess.Popen([sys.executable, str(SCRIPT), "--root", str(self.root), "task", "claim", "HOST-001", "--owner", owner], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for owner in ["a", "b"]]
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            results.append(process.returncode)
        self.assertEqual(sorted(results), [0, 2])
        state = lab.read_json(self.root / "state/lab.json")
        self.assertIn(state["tasks"][0]["owner"], {"a", "b"})
        self.assertEqual(len(state["events"]), 1)

    def test_completion_unlocks_dependent_task(self):
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "a").returncode, 0)
        path = self.evidence()
        result = self.cli("task", "done", "HOST-001", "--owner", "a", "--evidence", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli("task", "claim", "HOST-002", "--owner", "b").returncode, 0)

    def test_owner_cannot_complete_another_agents_task(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        result = self.cli("task", "done", "HOST-001", "--owner", "b", "--evidence", self.evidence())
        self.assertEqual(result.returncode, 2)
        self.assertEqual(lab.read_json(self.root / "state/lab.json")["tasks"][0]["status"], "in_progress")

    def test_failed_evidence_cannot_complete_task(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        path = self.evidence(outcome="fail")
        result = self.cli("task", "done", "HOST-001", "--owner", "a", "--evidence", path)
        self.assertEqual(result.returncode, 2)

    def test_native_scope_is_not_claimable(self):
        result = self.cli("task", "claim", "NAT-001", "--owner", "a")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not authorized", result.stderr)

    def test_scope_cannot_be_disguised_as_host_evidence(self):
        self.state["tasks"][2]["evidence_kind"] = "host-test"
        with self.assertRaises(lab.LabError):
            lab.validate(self.root, self.state)

    def test_native_evidence_rejects_synthetic_origin(self):
        path = self.evidence(kind="native-device", origin="synthetic")
        with self.assertRaises(lab.LabError):
            lab.evidence(self.root, path)

    def test_device_evidence_requires_real_inventory(self):
        path = self.evidence(kind="android-userland", origin="local-device", device_inventory="devices/missing.json")
        with self.assertRaises(lab.LabError):
            lab.evidence(self.root, path)

    def test_evidence_cannot_escape_through_symlink(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / "outside.json"
            outside.write_text("{}")
            (self.root / "artifacts/link.json").symlink_to(outside)
            with self.assertRaises(lab.LabError):
                lab.evidence(self.root, "artifacts/link.json")

    def test_dependency_cycles_rejected(self):
        state = copy.deepcopy(self.state)
        state["tasks"][0]["depends_on"] = ["HOST-002"]
        with self.assertRaises(lab.LabError):
            lab.validate(self.root, state)

    def test_recording_failure_retains_experiment_without_completing_task(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        result = self.cli("experiment", "plan", "EXP-001", "--task", "HOST-001", "--owner", "a", "--hypothesis", "The fixture passes", "--procedure", "docs/procedure.md", "--timeout-seconds", "10")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.evidence(outcome="fail")
        result = self.cli("experiment", "record", "EXP-001", "--owner", "a", "--evidence", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = lab.read_json(self.root / "state/lab.json")
        self.assertEqual(state["experiments"][0]["outcome"], "fail")
        self.assertEqual(state["tasks"][0]["status"], "in_progress")
        self.assertEqual(self.cli("experiment", "record", "EXP-001", "--owner", "a", "--evidence", path).returncode, 2)

    def test_changed_recorded_evidence_is_detected(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        path = self.evidence()
        self.assertEqual(self.cli("task", "done", "HOST-001", "--owner", "a", "--evidence", path).returncode, 0)
        doc = lab.read_json(self.root / path)
        doc["summary"] = "Rewritten after completion"
        lab.atomic_json(self.root / path, doc)
        self.assertEqual(self.cli("validate").returncode, 2)

    def test_add_invalid_task_rolls_back_atomically(self):
        lab.atomic_json(self.root / "docs/new.json", task("NEW-001", deps=["UNKNOWN-999"]))
        before = (self.root / "state/lab.json").read_bytes()
        result = self.cli("task", "add", "--file", "docs/new.json", "--owner", "planner")
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

    def test_placeholder_timestamp_is_not_measurement(self):
        path = self.evidence(recorded_at="REPLACE_WITH_ACTUAL_UTC_TIME")
        with self.assertRaises(lab.LabError):
            lab.evidence(self.root, path)

    def test_experiment_requires_existing_procedure_and_timeout(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        result = self.cli("experiment", "plan", "EXP-001", "--task", "HOST-001", "--owner", "a", "--hypothesis", "test", "--procedure", "docs/missing.md", "--timeout-seconds", "0")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(lab.read_json(self.root / "state/lab.json")["experiments"], [])


if __name__ == "__main__":
    unittest.main()
