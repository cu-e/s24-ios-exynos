"""Light real-Git/flock tests. Never publish to the project checkout."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[3] / "tools/integration_gate.py"
spec = importlib.util.spec_from_file_location("gate_fixture", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
ENV = dict(gate.ENV, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
RECORD = Path(os.environ["GATE_TEST_OUTPUT"]) if os.environ.get("GATE_TEST_OUTPUT") else None


class GateTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args], cwd=root, env=ENV, stderr=subprocess.PIPE).decode().strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "state").mkdir()
        (self.root / "artifacts").mkdir()
        (self.root / ".gitignore").write_text("worktrees/\nartifacts/\nstate/.integration.lock\nignored-new.txt\n")
        (self.root / "source.txt").write_text("baseline\n")
        (self.root / "state/lab.json").write_text('{"registry":"committed"}\n')
        self.git(self.root, "init", "-b", "main")
        self.git(self.root, "config", "user.name", "Integration gate fixture")
        self.git(self.root, "config", "user.email", "fixture@example.invalid")
        self.git(self.root, "add", ".")
        self.git(self.root, "commit", "-m", "baseline")
        self.base = self.git(self.root, "rev-parse", "HEAD")
        self.candidate = self.root / "worktrees/candidate"
        self.git(self.root, "worktree", "add", "-b", "candidate", str(self.candidate))
        (self.candidate / "source.txt").write_text("reviewed candidate\n")
        self.git(self.candidate, "commit", "-am", "candidate")
        self.tip = self.git(self.candidate, "rev-parse", "HEAD")
        capsule = self.root / "artifacts/review.json"
        capsule.write_text('{"synthetic_fixture":true}\n')
        self.plan = {"base_head": self.base, "candidate_head": self.tip,
                     "candidate_worktree": "worktrees/candidate", "commits": [self.tip],
                     "commit_map": [{"source": self.tip, "candidate": self.tip}],
                     "paths": ["source.txt"], "bindings": [{"path": "artifacts/review.json", "sha256": gate.sha(capsule)}]}
        self.plan_path = self.root / "artifacts/plan.json"
        self.counter = 0
        self.save_plan()

    def tearDown(self):
        self.temp.cleanup()

    def save_plan(self):
        self.plan_path.write_text(json.dumps(self.plan) + "\n")

    def start(self, mode="audit", *extra):
        self.counter += 1
        self.output = self.root / f"artifacts/run-{self.counter}"
        self.command = [sys.executable, "-s", str(SCRIPT), mode, "--root", str(self.root),
                        "--plan", str(self.plan_path), "--output", str(self.output), *extra]
        return subprocess.Popen(self.command, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(self, process):
        stdout, stderr = process.communicate(timeout=10)
        evidence = json.loads((self.output / "evidence.json").read_text())
        if RECORD:
            RECORD.mkdir(parents=True, exist_ok=True)
            (RECORD / f"{self._testMethodName}-{self.counter}.json").write_text(json.dumps(
                {"argv": self.command, "exit_code": process.returncode, "stdout": stdout,
                 "stderr": stderr, "evidence": evidence}, indent=2) + "\n")
        return process.returncode, evidence

    def test_audit_preserves_unrelated_dirty_registry_and_frozen_head(self):
        ledger = self.root / "state/lab.json"
        ledger.write_text('{"registry":"live dirty data"}\n')
        before = ledger.read_bytes()
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 0, evidence)
        self.assertFalse(evidence["publication_attempted"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.base)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(evidence["audit"]["dirty_primary_paths"], ["state/lab.json"])

    def test_dirty_source_and_staged_index_are_rejected_without_changes(self):
        source = self.root / "source.txt"
        source.write_text("uncommitted main source\n")
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("dirty primary paths", evidence["error"])
        self.assertEqual(source.read_text(), "uncommitted main source\n")
        self.git(self.root, "add", "source.txt")
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("staged changes", evidence["error"])
        self.assertEqual(self.git(self.root, "diff", "--cached", "--name-only"), "source.txt")

    def test_registry_candidate_is_rejected_even_when_main_is_clean(self):
        (self.candidate / "state/lab.json").write_text("stale worktree registry\n")
        self.git(self.candidate, "commit", "-am", "forbidden registry")
        tip = self.git(self.candidate, "rev-parse", "HEAD")
        self.plan.update(candidate_head=tip, commits=[self.tip, tip], paths=["source.txt", "state/lab.json"],
                         commit_map=[{"source": value, "candidate": value} for value in [self.tip, tip]])
        self.save_plan()
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("Registry/generated", evidence["error"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.base)

    def test_changed_capsule_and_wrong_approval_cannot_publish(self):
        approval = self.root / "artifacts/approval.json"
        approval.write_text(json.dumps({"approved_by": "root", "plan_sha256": "0" * 64, "resource_lease": "synthetic invalid receipt; no check allowed"}))
        code, evidence = self.finish(self.start("publish", "--approval", str(approval)))
        self.assertEqual(code, 2)
        self.assertFalse(evidence["publication_attempted"])
        self.assertIn("Approval must bind", evidence["error"])
        (self.root / "artifacts/review.json").write_text("changed capsule\n")
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("Capsule binding changed", evidence["error"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.base)

    def test_competing_process_waits_for_single_stable_lock_inode(self):
        program = "import importlib.util,pathlib,time; s=importlib.util.spec_from_file_location('g'," + repr(str(SCRIPT)) + "); g=importlib.util.module_from_spec(s); s.loader.exec_module(g)\nwith g.integration_lock(pathlib.Path(" + repr(str(self.root)) + ")):\n print('locked',flush=True)\n time.sleep(0.5)\n"
        holder = subprocess.Popen([sys.executable, "-s", "-c", program], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            inode = (self.root / "state/.integration.lock").stat().st_ino
            code, evidence = self.finish(self.start())
            self.assertEqual(code, 0, evidence)
            self.assertGreater(evidence["lock_wait_seconds"], 0.2)
            self.assertEqual((self.root / "state/.integration.lock").stat().st_ino, inode)
            stdout, stderr = holder.communicate(timeout=5)
            self.assertEqual(holder.returncode, 0, stderr)
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.communicate()

    def test_head_is_rechecked_after_waiting_for_lock(self):
        with gate.integration_lock(self.root):
            process = self.start()
            # Deliberately simulate a noncooperating HEAD writer in the fixture.
            (self.root / "other.txt").write_text("new main commit\n")
            self.git(self.root, "add", "other.txt")
            self.git(self.root, "commit", "-m", "move main while auditor waits")
            moved = self.git(self.root, "rev-parse", "HEAD")
            time.sleep(0.1)
        code, evidence = self.finish(process)
        self.assertEqual(code, 2)
        self.assertIn("Stale primary HEAD", evidence["error"])
        self.assertFalse(evidence["publication_attempted"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), moved)

    def publish_with_light_check(self, fail=False):
        approval = self.root / "artifacts/approval.json"
        approval.write_text(json.dumps({"approved_by": "root", "plan_sha256": gate.sha(self.plan_path),
                                       "resource_lease": "synthetic temporary repository only"}))
        self.counter += 1
        self.output = self.root / f"artifacts/run-{self.counter}"
        program = "import importlib.util,os,fcntl; s=importlib.util.spec_from_file_location('g'," + repr(str(SCRIPT)) + "); g=importlib.util.module_from_spec(s); s.loader.exec_module(g)\ndef check(root,out,fd,report):\n other=os.open(root/'state/.integration.lock',os.O_RDWR)\n try:\n  try: fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)\n  except BlockingIOError: report['common_check']={'synthetic':True,'same_lock_held':True}\n  else: raise AssertionError('Publication/check lost integration lock')\n finally: os.close(other)\n"
        if fail:
            program += " raise g.GateError('Synthetic check failure after real fixture publication')\n"
        program += "g.common_check=check\ng.admit=lambda *args: None\nraise SystemExit(g.main())\n"
        self.command = [sys.executable, "-s", "-c", program, "publish", "--root", str(self.root),
                        "--plan", str(self.plan_path), "--output", str(self.output), "--approval", str(approval)]
        return self.finish(subprocess.Popen(self.command, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))

    def test_real_fixture_fast_forward_holds_lock_through_light_check(self):
        ledger = self.root / "state/lab.json"
        ledger.write_text("preserve live fixture ledger\n")
        code, evidence = self.publish_with_light_check()
        self.assertEqual(code, 0, evidence)
        self.assertTrue(evidence["publication_attempted"])
        self.assertTrue(evidence["common_check"]["same_lock_held"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.tip)
        self.assertEqual(ledger.read_text(), "preserve live fixture ledger\n")

    def test_failed_light_check_retains_published_head_without_rollback(self):
        code, evidence = self.publish_with_light_check(fail=True)
        self.assertEqual(code, 2)
        self.assertTrue(evidence["common_check"]["same_lock_held"])
        self.assertEqual(evidence["published_head"], self.tip)
        self.assertIn("Synthetic check failure", evidence["error"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.tip)

    def test_unrelated_source_label_is_rejected(self):
        self.plan["commit_map"][0]["source"] = self.base
        self.save_plan()
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("exact patches differ", evidence["error"])

    def extra_commit(self, name):
        (self.candidate / name).write_text("new candidate content\n")
        self.git(self.candidate, "add", "-f", name)
        self.git(self.candidate, "commit", "-m", "extra candidate file")
        tip = self.git(self.candidate, "rev-parse", "HEAD")
        self.plan.update(candidate_head=tip, commits=[self.tip, tip], paths=["source.txt", name],
                         commit_map=[{"source": value, "candidate": value} for value in [self.tip, tip]])
        self.save_plan()

    def test_candidate_cannot_replace_held_integration_lock(self):
        self.extra_commit("state/.integration.lock")
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("Registry/generated view or lock", evidence["error"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.base)

    def test_new_candidate_file_cannot_overwrite_ignored_main_data(self):
        self.extra_commit("ignored-new.txt")
        (self.root / "ignored-new.txt").write_text("preserve ignored data\n")
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2)
        self.assertIn("including ignored files", evidence["error"])
        self.assertEqual((self.root / "ignored-new.txt").read_text(), "preserve ignored data\n")

    def history(self, transient="transient.txt", final="renamed.txt"):
        path = self.candidate / transient
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserved historical content\n")
        self.git(self.candidate, "add", "-f", transient)
        self.git(self.candidate, "commit", "-m", "historical addition")
        added = self.git(self.candidate, "rev-parse", "HEAD")
        self.git(self.candidate, "mv", transient, final)
        self.git(self.candidate, "commit", "-m", "historical rename")
        tip = self.git(self.candidate, "rev-parse", "HEAD")
        commits = [self.tip, added, tip]
        self.plan.update(candidate_head=tip, commits=commits,
                         commit_map=[{"source": value, "candidate": value} for value in commits],
                         paths=["source.txt", final], historical_paths=[transient])
        self.save_plan()

    def assert_history_rejected(self, message):
        self.save_plan()
        code, evidence = self.finish(self.start())
        self.assertEqual(code, 2, evidence)
        self.assertIn(message, evidence["error"])
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), self.base)

    def test_explicit_history_allows_real_add_rename_and_light_publication(self):
        self.history()
        code, evidence = self.publish_with_light_check()
        self.assertEqual(code, 0, evidence)
        self.assertEqual(evidence["audit"]["historical_paths"], ["transient.txt"])
        self.assertTrue(evidence["common_check"]["same_lock_held"])
        self.assertFalse((self.root / "transient.txt").exists())
        self.assertEqual((self.root / "renamed.txt").read_text(), "preserved historical content\n")

    def test_omitted_and_unused_history_are_rejected(self):
        self.history()
        del self.plan["historical_paths"]
        self.assert_history_rejected("exact net/historical plan")
        self.plan["historical_paths"] = ["transient.txt", "unused.txt"]
        self.assert_history_rejected("exact net/historical plan")

    def test_duplicate_overlapping_and_noncanonical_history_are_rejected(self):
        self.history()
        for values, message in [(["transient.txt", "transient.txt"], "unique and disjoint"),
                                (["transient.txt", "source.txt"], "unique and disjoint"),
                                (["./transient.txt"], "Literal relative"),
                                (["sub/../transient.txt"], "Literal relative"),
                                (["/transient.txt"], "Literal relative")]:
            with self.subTest(values=values):
                self.plan["historical_paths"] = values
                self.assert_history_rejected(message)

    def test_transient_lock_cannot_replace_held_inode(self):
        self.history("state/.integration.lock")
        with gate.integration_lock(self.root):
            inode = (self.root / "state/.integration.lock").stat().st_ino
        self.assert_history_rejected("Registry/generated view or lock")
        self.assertEqual((self.root / "state/.integration.lock").stat().st_ino, inode)

    def test_transient_generated_path_is_forbidden(self):
        self.history("planning/transient.md")
        self.assert_history_rejected("Registry/generated view or lock")

    def test_dirty_historical_path_and_ancestor_are_preserved(self):
        self.history("scratch/transient.txt")
        (self.root / "scratch").mkdir()
        data = self.root / "scratch/transient.txt"
        data.write_text("untracked primary data\n")
        self.assert_history_rejected("dirty primary paths")
        self.assertEqual(data.read_text(), "untracked primary data\n")
        data.unlink()
        data.parent.rmdir()
        (self.root / "scratch").write_text("untracked ancestor\n")
        self.assert_history_rejected("dirty primary paths")
        self.assertEqual((self.root / "scratch").read_text(), "untracked ancestor\n")

    def test_ignored_historical_path_cannot_overwrite_primary_data(self):
        self.history("ignored-new.txt")
        path = self.root / "ignored-new.txt"
        path.write_text("ignored primary data\n")
        self.assert_history_rejected("including ignored files")
        self.assertEqual(path.read_text(), "ignored primary data\n")

    def test_historical_symlink_parent_is_rejected(self):
        self.history("scratch/transient.txt")
        (self.root / ".git/info/exclude").write_text("scratch\n")
        (self.root / "scratch").symlink_to(self.root / "artifacts", target_is_directory=True)
        # Ignore the parent link so this reaches the distinct symlink-parent guard.
        self.assert_history_rejected("primary symlink")

    def test_historical_mapping_still_requires_exact_source_patch(self):
        self.history()
        self.plan["commit_map"][1]["source"] = self.base
        self.assert_history_rejected("exact patches differ")


if __name__ == "__main__":
    unittest.main()
