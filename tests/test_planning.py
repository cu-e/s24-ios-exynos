"""Exercise coordination races, reservations and snapshot failure recovery."""
import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_lab as fixtures
from test_lab import SCRIPT, lab


class PlanningTests(unittest.TestCase):
    setUp = fixtures.LedgerTests.setUp
    tearDown = fixtures.LedgerTests.tearDown
    save = fixtures.LedgerTests.save
    cli = fixtures.LedgerTests.cli
    evidence = fixtures.LedgerTests.evidence

    def load(self):
        return lab.read_json(self.root / "state/lab.json")

    def independent_tasks(self):
        self.state["tasks"][0]["paths"] = ["src/a/"]
        self.state["tasks"][1].update(depends_on=[], paths=["src/b/"])
        self.save()

    def test_atomic_claim_next_distributes_independent_work(self):
        self.independent_tasks()
        processes = [subprocess.Popen([sys.executable, str(SCRIPT), "--root", str(self.root), "task", "claim-next", "--owner", owner], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for owner in ["agent-a", "agent-b"]]
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual({t["owner"] for t in self.load()["tasks"][:2]}, {"agent-a", "agent-b"})
        self.assertEqual(self.cli("board", "--check").returncode, 0)
        board = lab.read_json(self.root / "state/board.json")
        self.assertEqual(set(board["columns"]["in_progress"]), {"HOST-001", "HOST-002"})

    def test_claim_next_respects_priority_and_unauthorized_scope(self):
        self.independent_tasks()
        self.state["tasks"][1]["priority"] = 90
        self.state["tasks"][2]["priority"] = 100
        self.save()
        result = self.cli("task", "claim-next", "--owner", "agent-a")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.load()["tasks"][1]["owner"], "agent-a")
        before = (self.root / "state/lab.json").read_bytes()
        self.assertEqual(self.cli("task", "claim-next", "--scope", "native", "--owner", "agent-b").returncode, 2)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

    def test_overlapping_paths_stay_reserved_while_blocked_then_release(self):
        self.state["tasks"][1].update(depends_on=[], paths=["tools/parser.py"])
        self.save()
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "a").returncode, 0)
        self.assertEqual(self.cli("task", "block", "HOST-001", "--owner", "a", "--reason", "Need donor header").returncode, 0)
        before = (self.root / "state/lab.json").read_bytes()
        result = self.cli("task", "claim", "HOST-002", "--owner", "b")
        self.assertEqual(result.returncode, 2)
        self.assertIn("reserved", result.stderr)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)
        self.assertEqual(self.cli("task", "release", "HOST-001", "--owner", "a").returncode, 0)
        self.assertEqual(self.cli("task", "claim", "HOST-002", "--owner", "b").returncode, 0)

    def test_owner_only_progress_heartbeat_and_resume_preserve_history(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        for action, options in [("update", ["--note", "Steal progress"]), ("heartbeat", []), ("block", ["--reason", "Steal lock"]), ("release", []), ("resume", [])]:
            self.assertEqual(self.cli("task", action, "HOST-001", "--owner", "b", *options).returncode, 2)
        result = self.cli("task", "update", "HOST-001", "--owner", "a", "--note", "Checked parser", "--next-step", "Check bounds", "--handoff", "docs/procedure.md", "--branch", "task/parser", "--worktree", "worktrees/parser")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.cli("task", "block", "HOST-001", "--owner", "a", "--reason", "Need fixture")
        self.assertEqual(self.cli("task", "resume", "HOST-001", "--owner", "a").returncode, 0)
        state = self.load()
        current = state["tasks"][0]
        self.assertEqual(current["owner"], "a")
        self.assertEqual(current["status"], "in_progress")
        self.assertEqual(current["next_step"], "Check bounds")
        self.assertNotIn("blocked_reason", current)
        self.assertTrue(any(e.get("tasks", [{}])[0].get("progress_note") == "Checked parser" for e in state["events"]))

    def test_resume_rechecks_authorization(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        self.cli("task", "block", "HOST-001", "--owner", "a", "--reason", "External dependency")
        state = self.load();state["project"]["permissions"]["host"] = False
        lab.atomic_json(self.root / "state/lab.json", state)
        self.assertEqual(self.cli("task", "resume", "HOST-001", "--owner", "a").returncode, 2)
        self.assertEqual(self.load()["tasks"][0]["status"], "blocked")

    def test_no_eligible_work_leaves_state_unchanged(self):
        self.cli("task", "claim-next", "--owner", "a")
        before = (self.root / "state/lab.json").read_bytes()
        self.assertEqual(self.cli("task", "claim-next", "--owner", "b").returncode, 2)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)

    def test_stale_report_never_releases_claim(self):
        self.state["tasks"][0].update(status="in_progress", owner="a", last_heartbeat="2020-01-01T00:00:00+00:00")
        self.save()
        result = self.cli("board", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["agents"]["a"][0]["report_health"], "stale")
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "b").returncode, 2)
        self.assertEqual(self.load()["tasks"][0]["owner"], "a")
        self.assertEqual(self.cli("task", "heartbeat", "HOST-001", "--owner", "a").returncode, 0)
        self.assertEqual(json.loads(self.cli("board", "--json").stdout)["agents"]["a"][0]["report_health"], "recent")

    def test_view_check_detects_edited_card_missing_file_and_stale_registry(self):
        self.assertEqual(self.cli("board", "--write").returncode, 0)
        card = self.root / "planning/tasks/HOST-001.md"
        card.write_text("Manually moved card")
        self.assertEqual(self.cli("board", "--check").returncode, 2)
        self.cli("board", "--write");card.unlink()
        self.assertEqual(self.cli("board", "--check").returncode, 2)
        self.cli("board", "--write")
        index = lab.read_json(self.root / "state/board.json")
        index["tasks"][0]["owner"] = "unrecorded-owner"
        lab.atomic_json(self.root / "state/board.json", index)
        self.assertEqual(self.cli("board", "--check").returncode, 2)
        self.cli("board", "--write")
        self.state["project"]["phase"] = "Changed outside CLI"
        self.save()
        self.assertEqual(self.cli("board", "--check").returncode, 2)
        self.assertEqual(self.cli("board", "--write").returncode, 0)
        self.assertEqual(self.cli("board", "--check").returncode, 0)

    def test_concurrent_claims_cannot_reserve_overlapping_tasks(self):
        self.state["tasks"][1].update(depends_on=[], paths=["tools/parser.py"])
        self.save()
        processes = [subprocess.Popen([sys.executable, str(SCRIPT), "--root", str(self.root), "task", "claim", identifier, "--owner", owner], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for identifier, owner in [("HOST-001", "a"), ("HOST-002", "b")]]
        codes = []
        for process in processes:
            process.communicate(timeout=15)
            codes.append(process.returncode)
        self.assertEqual(sorted(codes), [0, 2])
        self.assertEqual(sum(t["status"] == "in_progress" for t in self.load()["tasks"]), 1)
        self.assertEqual(self.cli("board", "--check").returncode, 0)

    def test_partial_publication_is_detected_before_repair(self):
        self.cli("board", "--write")
        writer = lab.atomic_text
        calls = []
        def partial_write(path, text):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("Write interrupted after one view")
            writer(path, text)
        with patch.object(lab, "atomic_text", side_effect=partial_write):
            with self.assertRaisesRegex(lab.LabError, "Registry saved"):
                with lab.transaction(self.root, "task.claim:HOST-001", "a") as state:
                    lab.claim_task(state, state["tasks"][0], "a")
        self.assertEqual(self.load()["tasks"][0]["owner"], "a")
        self.assertEqual(self.cli("board", "--check").returncode, 2)
        self.assertEqual(self.cli("board", "--write").returncode, 0)
        self.assertEqual(self.cli("board", "--check").returncode, 0)

    def test_publish_failure_reports_committed_state_and_allows_repair(self):
        with patch.object(lab, "publish_views", side_effect=OSError("Disk full")):
            with self.assertRaisesRegex(lab.LabError, "Registry saved"):
                with lab.transaction(self.root, "task.claim:HOST-001", "a") as state:
                    lab.claim_task(state, state["tasks"][0], "a")
        self.assertEqual(self.load()["tasks"][0]["owner"], "a")
        self.assertEqual(self.cli("task", "claim", "HOST-001", "--owner", "b").returncode, 2)
        self.assertEqual(self.cli("board", "--write").returncode, 0)
        self.assertEqual(self.cli("board", "--check").returncode, 0)

    def test_invalid_context_and_path_aliases_roll_back(self):
        self.cli("task", "claim", "HOST-001", "--owner", "a")
        before = (self.root / "state/lab.json").read_bytes()
        self.assertEqual(self.cli("task", "update", "HOST-001", "--owner", "a", "--note", "Valid note", "--handoff", "docs/missing.md").returncode, 2)
        self.assertEqual(self.cli("task", "block", "HOST-001", "--owner", "a", "--reason", " ").returncode, 2)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)
        for path in ["tools/../docs", "tools/*", str(self.root / "tools")]:
            state = copy.deepcopy(self.state);state["tasks"][0]["paths"] = [path]
            with self.assertRaises(lab.LabError):lab.validate(self.root, state)
        (self.root / "tools/alias").symlink_to(self.root / "docs", target_is_directory=True)
        state = copy.deepcopy(self.state);state["tasks"][0]["paths"] = ["tools/alias"]
        with self.assertRaises(lab.LabError):lab.validate(self.root, state)

    def test_priority_edit_is_audited_and_does_not_assign_an_owner(self):
        result = self.cli("task", "prioritize", "HOST-001", "--owner", "planner", "--priority", "90", "--reason", "Unblocks the build")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.load()
        self.assertIsNone(state["tasks"][0]["owner"])
        self.assertEqual(state["events"][-1]["tasks"][0]["priority_reason"], "Unblocks the build")
        before = (self.root / "state/lab.json").read_bytes()
        self.assertEqual(self.cli("task", "prioritize", "HOST-001", "--owner", "planner", "--priority", "101", "--reason", "Invalid").returncode, 2)
        self.assertEqual((self.root / "state/lab.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
