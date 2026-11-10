"""Behavioral tests for coordination and evidence boundaries, without a phone."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def decision(self, name="0099-test.md"):
        (self.root / "docs/decisions").mkdir(exist_ok=True)
        (self.root / "docs/decisions" / name).write_text("Owner decision fixture")
        return "docs/decisions/" + name

    def test_permit_requires_existing_decision_record(self):
        before = (self.root / "state/lab.json").read_bytes()
        for path in ["docs/decisions/missing.md", "docs/procedure.md"]:
            result = self.cli("project", "permit", "--scope", "native", "--value", "true", "--decision", path, "--owner", "a")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("docs/decisions", result.stderr)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

    def test_permit_records_decision_and_event(self):
        path = self.decision()
        result = self.cli("project", "permit", "--scope", "native", "--value", "true", "--decision", path, "--owner", "a")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.root / "state/lab.json").read_text())
        self.assertIs(state["project"]["permissions"]["native"], True)
        self.assertEqual(state["project"]["permission_decisions"][-1]["decision"], path)
        self.assertEqual(state["events"][-1]["permissions"]["native"], True)
        self.assertEqual(self.cli("task", "claim", "NAT-001", "--owner", "a").returncode, 0)
        again = self.cli("project", "permit", "--scope", "native", "--value", "true", "--decision", path, "--owner", "a")
        self.assertEqual(again.returncode, 2)

    def test_transfer_moves_only_matching_active_claim(self):
        path = self.decision()
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "old").returncode, 0)
        wrong = self.cli("task", "transfer", "HOST-001", "--from-owner", "other", "--owner", "new", "--reason", "stopped", "--decision", path)
        self.assertEqual(wrong.returncode, 2)
        missing = self.cli("task", "transfer", "HOST-001", "--from-owner", "old", "--owner", "new", "--reason", "stopped", "--decision", path, "--handoff", "docs/none.md")
        self.assertEqual(missing.returncode, 2)
        pending = self.cli("task", "transfer", "HOST-002", "--from-owner", "old", "--owner", "new", "--reason", "stopped", "--decision", path)
        self.assertEqual(pending.returncode, 2)
        done = self.cli("task", "transfer", "HOST-001", "--from-owner", "old", "--owner", "new", "--reason", "stopped", "--decision", path, "--handoff", "docs/procedure.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        state = json.loads((self.root / "state/lab.json").read_text())
        moved = next(t for t in state["tasks"] if t["id"] == "HOST-001")
        self.assertEqual((moved["owner"], moved["status"], moved["handoff"]), ("new", "in_progress", "docs/procedure.md"))
        self.assertEqual(moved["ownership_history"][-1]["from"], "old")
        self.assertEqual(self.cli("task", "heartbeat", "HOST-001", "--owner", "old").returncode, 2)

    def narrow_fixture(self):
        self.state["tasks"][0]["paths"] = ["tools/a.py"]
        broad = task("HOST-003")
        broad["paths"] = ["tools/", "docs/"]
        self.state["tasks"].append(broad)
        self.save()

    def test_narrow_makes_an_overlapping_pending_task_claimable(self):
        self.narrow_fixture()
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "a").returncode, 0)
        blocked = self.cli("task", "claim", "HOST-003", "--owner", "b")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("HOST-001", blocked.stderr)
        result = self.cli("task", "narrow", "HOST-003", "--owner", "planner", "--paths", "tools/b.py", "docs/b.md",
                          "--reason", "only b is still open")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.root / "state/lab.json").read_text())
        narrowed = next(t for t in state["tasks"] if t["id"] == "HOST-003")
        self.assertEqual(narrowed["paths"], ["tools/b.py", "docs/b.md"])
        self.assertEqual(narrowed["path_history"][-1]["from"], ["tools/", "docs/"])
        self.assertEqual(narrowed["path_history"][-1]["owner"], "planner")
        self.assertEqual((narrowed["status"], narrowed["owner"]), ("pending", None))
        self.assertEqual(state["events"][-1]["action"], "task.narrow:HOST-003")
        self.assertEqual(state["events"][-1]["tasks"][0]["paths"], ["tools/b.py", "docs/b.md"])
        self.assertEqual(self.cli("task", "claim", "HOST-003", "--owner", "b").returncode, 0)

    def test_narrow_rejections_leave_the_registry_unchanged(self):
        self.narrow_fixture()
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "a").returncode, 0)
        before = (self.root / "state/lab.json").read_bytes()
        cases = [
            ("HOST-003", ["research/x.md"], "outside"),                 # widening to a new tree
            ("HOST-003", ["tools/", "docs/", "research/"], "wider"),    # superset
            ("HOST-003", ["tools/", "docs/"], "same"),                  # unchanged
            ("HOST-003", ["tools/b.py", "tools/b.py"], "duplicate"),
            ("HOST-003", ["tools/../research/x.md"], "traversal"),
            ("HOST-003", ["tools/b.py"], " "),                          # empty reason
            ("HOST-001", ["tools/a.py/x"], "claimed"),                  # in progress, owned
        ]
        for ident, paths, reason in cases:
            with self.subTest(ident=ident, paths=paths, reason=reason):
                result = self.cli("task", "narrow", ident, "--owner", "planner", "--paths", *paths, "--reason", reason)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

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


class ViewPublicationTests(unittest.TestCase):
    tearDown = LedgerTests.tearDown
    save = LedgerTests.save
    cli = LedgerTests.cli
    stamp = "2026-11-05T12:00:00+00:00"

    def setUp(self):
        LedgerTests.setUp(self)
        self.state["updated_at"] = self.stamp
        self.save()

    def publish(self, stamp=None):
        with (self.root / "state/.lab.lock").open("a") as lock:
            lab.fcntl.flock(lock, lab.fcntl.LOCK_EX)
            with patch.object(lab, "now", return_value=stamp or self.stamp):
                lab.publish_views(self.root, self.state)

    def versions(self):
        paths = [self.root / name for name in ["STATUS.md", "BOARD.md", "state/lab.json", "state/board.json"]]
        paths += sorted((self.root / "planning/tasks").glob("*.md"))
        result = {}
        for path in paths:
            # A distinct old mtime makes replacement observable even on coarse clocks.
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
            result[str(path.relative_to(self.root))] = (path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes())
        return result

    def assert_preserved(self, before, names):
        for name in names:
            path = self.root / name
            self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns, path.read_bytes()), before[name], name)

    def test_identical_publication_preserves_files_and_only_syncs_index(self):
        self.state["tasks"][0]["title"] = "Unicode view: café Δ"
        self.save()
        self.publish()
        before = self.versions()
        with patch.object(lab, "atomic_text", wraps=lab.atomic_text) as texts, patch.object(lab.os, "fsync", wraps=lab.os.fsync) as syncs:
            self.publish()
        self.assertEqual(texts.call_count, 0)
        self.assertEqual(syncs.call_count, 1)
        self.assert_preserved(before, set(before) - {"state/board.json"})
        self.assertEqual((self.root / "state/board.json").read_bytes(), before["state/board.json"][2])
        lab.check_views(self.root)

    def test_advancing_snapshot_only_replaces_board_and_index(self):
        self.publish()
        before = self.versions()
        with patch.object(lab, "atomic_text", wraps=lab.atomic_text) as texts:
            self.publish("2026-11-05T12:00:01+00:00")
        self.assertEqual([call.args[0].relative_to(self.root).as_posix() for call in texts.call_args_list], ["BOARD.md"])
        self.assert_preserved(before, set(before) - {"BOARD.md", "state/board.json"})
        lab.check_views(self.root)

    def test_task_change_replaces_only_affected_views_and_authoritative_state(self):
        self.publish()
        before = self.versions()
        with patch.object(lab, "atomic_text", wraps=lab.atomic_text) as texts, patch.object(lab, "atomic_json", wraps=lab.atomic_json) as jsons:
            with patch.object(lab, "now", return_value=self.stamp):
                with lab.transaction(self.root, "test.title", "fixture") as state:
                    state["tasks"][0]["title"] = "Changed title"
        self.assertEqual([call.args[0].relative_to(self.root).as_posix() for call in texts.call_args_list], ["STATUS.md", "BOARD.md", "planning/tasks/HOST-001.md"])
        self.assertEqual([call.args[0].relative_to(self.root).as_posix() for call in jsons.call_args_list], ["state/lab.json", "state/board.json"])
        changed = {"STATUS.md", "BOARD.md", "planning/tasks/HOST-001.md", "state/lab.json", "state/board.json"}
        self.assert_preserved(before, set(before) - changed)
        for name in changed:
            self.assertNotEqual((self.root / name).stat().st_mtime_ns, before[name][1], name)
        self.assertEqual(lab.read_json(self.root / "state/lab.json")["events"][-1]["action"], "test.title")
        lab.check_views(self.root)

    def test_missing_and_corrupt_bytes_are_repaired_selectively(self):
        self.publish()
        card = self.root / "planning/tasks/HOST-001.md"
        expected = card.read_bytes()
        for corruption in [None, b"\xff\xfe", expected.replace(b"\n", b"\r\n")]:
            with self.subTest(corruption=corruption is None and "missing" or "corrupt"):
                if corruption is None:
                    card.unlink()
                else:
                    card.write_bytes(corruption)
                with self.assertRaises(lab.LabError):
                    lab.check_views(self.root)
                with patch.object(lab, "atomic_text", wraps=lab.atomic_text) as texts:
                    self.publish()
                self.assertEqual([call.args[0] for call in texts.call_args_list], [card])
                self.assertEqual(card.read_bytes(), expected)
                lab.check_views(self.root)

    def test_containment_is_checked_before_skipping_identical_symlink(self):
        self.publish()
        path = self.root / "STATUS.md"
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / "same.md"
            outside.write_bytes(path.read_bytes())
            before = outside.stat()
            path.unlink()
            path.symlink_to(outside)
            with self.assertRaisesRegex(lab.LabError, "including symlinks"):
                self.publish()
            self.assertEqual(outside.stat(), before)

    def test_unreadable_view_uses_real_atomic_repair_and_fifo_is_not_read(self):
        self.publish()
        card = self.root / "planning/tasks/HOST-001.md"
        expected = card.read_bytes()
        original = Path.read_bytes
        def unreadable(path):
            if path == card:
                raise PermissionError("Injected read denial; parent remains writable")
            return original(path)
        with patch.object(Path, "read_bytes", unreadable), patch.object(lab, "atomic_text", wraps=lab.atomic_text) as texts:
            self.publish()
        self.assertEqual([call.args[0] for call in texts.call_args_list], [card])
        self.assertEqual(card.read_bytes(), expected)
        card.unlink()
        os.mkfifo(card)
        self.publish()
        self.assertTrue(card.is_file())
        self.assertEqual(card.read_bytes(), expected)
        lab.check_views(self.root)

    def test_interrupted_publication_keeps_old_index_after_registry_and_event_save(self):
        self.publish()
        before = self.versions()
        writer = lab.atomic_text
        writes = []
        def interrupted(path, text):
            writes.append(path.relative_to(self.root).as_posix())
            if path.name == "HOST-001.md":
                raise OSError("Interrupted after changed board; equal status was skipped")
            writer(path, text)
        with patch.object(lab, "atomic_text", side_effect=interrupted), patch.object(lab, "atomic_json", wraps=lab.atomic_json) as jsons:
            with patch.object(lab, "now", return_value=self.stamp):
                with self.assertRaisesRegex(lab.LabError, "Registry saved"):
                    with lab.transaction(self.root, "test.interrupt", "fixture") as state:
                        state["tasks"][0]["progress_note"] = "Changed progress"
        self.assertEqual(writes, ["BOARD.md", "planning/tasks/HOST-001.md"])
        self.assertEqual([call.args[0].relative_to(self.root).as_posix() for call in jsons.call_args_list], ["state/lab.json"])
        saved = lab.read_json(self.root / "state/lab.json")
        self.assertEqual(saved["tasks"][0]["progress_note"], "Changed progress")
        self.assertEqual(saved["events"][-1]["action"], "test.interrupt")
        self.assert_preserved(before, ["STATUS.md", "planning/tasks/HOST-001.md", "state/board.json"])
        self.assertEqual(self.cli("board", "--check").returncode, 2)
        self.state = saved
        self.publish()
        lab.check_views(self.root)


if __name__ == "__main__":
    unittest.main()
