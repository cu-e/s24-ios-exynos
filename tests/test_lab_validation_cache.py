"""Real filesystem freshness and containment controls for validation-local reuse."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(os.environ.get("LAB_VALIDATION_TARGET", Path(__file__).resolve().parents[1] / "tools/lab.py"))
spec = importlib.util.spec_from_file_location("validation_lab", SCRIPT)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class ValidationFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        for name in ["state", "research", "artifacts", "docs", "src/owned"]:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.write("research/sources.json", {"sources": []})
        (self.root / "docs/procedure.md").write_text("Real procedure")
        (self.root / "artifacts/result.txt").write_text("Real artifact")
        self.doc = {"kind": "host-test", "origin": "local-host", "outcome": "pass",
                    "recorded_at": "2026-11-06T00:00:00+00:00", "summary": "Real fixture",
                    "artifacts": ["artifacts/result.txt", "artifacts/result.txt"]}
        self.state = {"schema_version": 1, "updated_at": lab.now(), "events": [],
                      "project": {"phase": "fixture", "permissions": dict.fromkeys(lab.SCOPES, False)},
                      "tasks": [{"id": "HOST-001", "title": "Completed fixture", "status": "done",
                                 "owner": "fixture-owner", "scope": "host", "evidence_kind": "host-test",
                                 "depends_on": [], "paths": ["src/owned"], "sources": [],
                                 "acceptance": ["Real validation"], "handoff": "docs/procedure.md",
                                 "evidence": "artifacts/evidence.json"}],
                      "experiments": [{"id": "EXP-001", "task": "HOST-001", "kind": "host-test",
                                       "owner": "fixture-owner", "status": "recorded", "outcome": "pass",
                                       "procedure": "docs/procedure.md", "timeout_seconds": 1,
                                       "evidence": "artifacts/evidence.json"}]}
        self.state["project"]["permissions"]["host"] = True
        self.save_doc()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data, indent=2) + "\n")

    def save_doc(self):
        self.write("artifacts/evidence.json", self.doc)
        digest = hashlib.sha256((self.root / "artifacts/evidence.json").read_bytes()).hexdigest()
        self.state["tasks"][0]["evidence_sha256"] = digest
        self.state["experiments"][0]["evidence_sha256"] = digest

    def validate(self, root=None):
        return lab.validate(root or self.root, copy.deepcopy(self.state))

    def test_repeated_validations_return_full_unchanged_state(self):
        self.assertEqual(self.validate(), self.state)
        self.assertEqual(self.validate(), self.state)

    def test_deleted_artifact_is_rechecked_next_validation(self):
        self.validate()
        (self.root / "artifacts/result.txt").unlink()
        with self.assertRaisesRegex(lab.LabError, "Missing evidence artifact"):
            self.validate()

    def test_artifact_replaced_by_directory_is_rejected(self):
        self.validate()
        artifact = self.root / "artifacts/result.txt"
        artifact.unlink()
        artifact.mkdir()
        with self.assertRaisesRegex(lab.LabError, "Missing evidence artifact"):
            self.validate()

    def test_capsule_content_change_keeps_actual_hash_check(self):
        self.validate()
        self.doc["summary"] = "Changed after validation"
        self.write("artifacts/evidence.json", self.doc)
        with self.assertRaisesRegex(lab.LabError, "Recorded evidence changed"):
            self.validate()

    def test_deleted_capsule_is_rejected(self):
        self.validate()
        (self.root / "artifacts/evidence.json").unlink()
        with self.assertRaisesRegex(lab.LabError, "Cannot read"):
            self.validate()

    def test_capsule_outcome_and_expected_kind_are_not_cached(self):
        self.validate()
        self.doc["outcome"] = "fail"
        self.save_doc()
        with self.assertRaisesRegex(lab.LabError, "Completed task needs passing evidence"):
            self.validate()
        self.doc["outcome"] = "pass"
        self.doc["kind"] = "source-review"
        self.save_doc()
        with self.assertRaisesRegex(lab.LabError, "Expected host-test evidence"):
            self.validate()

    def test_shared_capsule_still_checks_each_expected_kind(self):
        self.validate()
        self.state["tasks"][0]["evidence_kind"] = "source-review"
        self.state["experiments"][0]["kind"] = "source-review"
        with self.assertRaisesRegex(lab.LabError, "Expected source-review evidence"):
            self.validate()

    def test_artifact_symlink_retargeted_outside_is_rejected(self):
        link = self.root / "artifacts/link"
        link.symlink_to("result.txt")
        self.doc["artifacts"] = ["artifacts/link"]
        self.save_doc()
        self.validate()
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("Real outside file")
        link.unlink()
        link.symlink_to(outside)
        with self.assertRaisesRegex(lab.LabError, "Paths must stay inside"):
            self.validate()

    def test_capsule_symlink_retargeted_outside_is_rejected(self):
        capsule = self.root / "artifacts/evidence.json"
        stored = self.root / "artifacts/stored.json"
        capsule.rename(stored)
        capsule.symlink_to(stored.name)
        self.validate()
        outside = Path(self.temp.name) / "outside.json"
        outside.write_bytes(stored.read_bytes())
        capsule.unlink()
        capsule.symlink_to(outside)
        with self.assertRaisesRegex(lab.LabError, "Paths must stay inside"):
            self.validate()

    def test_symlinked_project_root_is_resolved_fresh(self):
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.validate(alias)
        other = Path(self.temp.name) / "other"
        shutil.copytree(self.root, other)
        (other / "artifacts/result.txt").unlink()
        alias.unlink()
        alias.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(lab.LabError, "Missing evidence artifact"):
            self.validate(alias)

    def test_task_paths_reject_new_alias_and_traversal(self):
        self.validate()
        target = self.root / "src/actual"
        target.mkdir()
        (self.root / "src/owned").rmdir()
        (self.root / "src/owned").symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(lab.LabError, "canonical task paths"):
            self.validate()
        self.state["tasks"][0]["paths"] = ["src/../src/actual"]
        with self.assertRaisesRegex(lab.LabError, "without traversal"):
            self.validate()

    def test_sibling_prefix_escape_and_in_root_normalization(self):
        sibling = self.root.with_name("project-other")
        sibling.mkdir()
        (sibling / "file").write_text("Outside")
        with self.assertRaisesRegex(lab.LabError, "Paths must stay inside"):
            lab.within(self.root, "../project-other/file")
        self.doc["artifacts"] = ["artifacts/../artifacts/result.txt"]
        self.save_doc()
        self.assertEqual(self.validate(), self.state)

    def test_inventory_content_is_read_again(self):
        inventory = {"origin": "local-device", "observed_at": "2026-11-06T00:00:00+00:00"}
        self.write("artifacts/inventory.json", inventory)
        self.state["tasks"][0].update(scope="android-readonly", evidence_kind="android-userland")
        self.state["experiments"][0]["kind"] = "android-userland"
        self.doc.update(kind="android-userland", origin="local-device", device_inventory="artifacts/inventory.json")
        self.save_doc()
        self.validate()
        inventory["origin"] = "synthetic"
        self.write("artifacts/inventory.json", inventory)
        with self.assertRaisesRegex(lab.LabError, "actual dated local-device"):
            self.validate()

    def test_transaction_second_validation_observes_deleted_artifact(self):
        self.write("state/lab.json", self.state)
        before = (self.root / "state/lab.json").read_bytes()
        with self.assertRaisesRegex(lab.LabError, "Missing evidence artifact"):
            with lab.transaction(self.root, "test-change", "fixture-owner") as state:
                state["project"]["phase"] = "Actual changed transaction"
                (self.root / "artifacts/result.txt").unlink()
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

    def test_standalone_evidence_is_always_fresh(self):
        lab.evidence(self.root, "artifacts/evidence.json")
        (self.root / "artifacts/result.txt").unlink()
        with self.assertRaisesRegex(lab.LabError, "Missing evidence artifact"):
            lab.evidence(self.root, "artifacts/evidence.json")

    def test_large_capsule_hash_uses_all_real_bytes(self):
        self.doc["large_fixture"] = "0123456789abcdef" * (128 * 1024)
        self.save_doc()
        self.validate()
        self.assertEqual(lab.evidence_hash(self.root, "artifacts/evidence.json"),
                         hashlib.sha256((self.root / "artifacts/evidence.json").read_bytes()).hexdigest())

    def test_concurrent_claims_remain_atomic(self):
        self.state["tasks"][0].update(status="pending", owner=None)
        self.state["tasks"][0].pop("evidence")
        self.state["tasks"][0].pop("evidence_sha256")
        self.state["experiments"] = []
        self.write("state/lab.json", self.state)
        argv = [sys.executable, str(SCRIPT), "--root", str(self.root), "task", "claim-next", "--scope", "host", "--owner"]
        children = [subprocess.Popen([*argv, owner], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for owner in ["claim-a", "claim-b"]]
        codes = []
        for child in children:
            stdout, stderr = child.communicate(timeout=20)
            codes.append(child.returncode)
        self.assertEqual(sorted(codes), [0, 2])
        state = json.loads((self.root / "state/lab.json").read_text())
        self.assertIn(state["tasks"][0]["owner"], ["claim-a", "claim-b"])
        self.assertEqual(len(state["events"]), 1)


if __name__ == "__main__":
    unittest.main()
