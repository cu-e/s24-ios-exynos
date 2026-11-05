#!/usr/bin/env python3
"""Audit frozen source candidates and serialize explicitly approved integration."""
import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time
import traceback

ENV = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0", LC_ALL="C",
           PYTHONUTF8="1", PYTHONNOUSERSITE="1")
FORBIDDEN = {"state/lab.json", "state/board.json", "BOARD.md", "STATUS.md"}
GIT_COMMANDS = []


class GateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(root, name):
    path = (root / name).resolve()
    require(path.is_relative_to(root), "Path escapes primary checkout")
    return path


def frozen_json(path):
    with path.open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    require(len(data) <= 1024 * 1024, "Plan/approval exceeds 1 MiB")
    return json.loads(data), hashlib.sha256(data).hexdigest()


def git(root, *args, fd=None):
    result = subprocess.run(["git", *args], cwd=root, env=ENV, capture_output=True,
                            timeout=30, pass_fds=() if fd is None else (fd,))
    GIT_COMMANDS.append({"argv": ["git", *args], "cwd": str(root), "exit_code": result.returncode,
                         "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace")})
    require(result.returncode == 0, f"git {args[0]} exited {result.returncode}: {result.stderr.decode(errors='replace')}")
    return result.stdout


def patch_sha(root, commit):
    command = ["git", "show", "--format=", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", "--no-renames", commit]
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run(command, cwd=root, env=ENV, stdout=output, stderr=errors, timeout=30)
        errors.seek(0)
        GIT_COMMANDS.append({"argv": command, "cwd": str(root), "exit_code": result.returncode, "stderr": errors.read(4096).decode(errors="replace")})
        require(result.returncode == 0, "Cannot read exact mapped commit patch")
        output.seek(0)
        return hashlib.file_digest(output, "sha256").hexdigest()


def head(root):
    return git(root, "rev-parse", "HEAD").decode().strip()


@contextlib.contextmanager
def integration_lock(root, timeout=30):
    """Never unlink the stable lock inode; child publication/check inherits it."""
    path = root / "state/.integration.lock"
    require(not path.is_symlink() and path.parent.resolve() == root / "state", "Integration lock must use primary state directory")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    started = time.monotonic()
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() - started < timeout, "Integration lock timeout")
                time.sleep(min(0.05, timeout))
        yield descriptor, time.monotonic() - started
    finally:
        os.close(descriptor)


def audit(root, plan):
    require(Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root,
            "Root must be the primary checkout root")
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()).resolve()
    require(common.parent == root, "Root must be the primary checkout, not another worktree")
    for value in [plan["base_head"], plan["candidate_head"], *plan["commits"]]:
        require(re.fullmatch(r"[0-9a-f]{40}", value), "Full commit SHA required")
    require(head(root) == plan["base_head"], "Stale primary HEAD: rebuild candidate and renew approval")
    candidate = inside(root, plan["candidate_worktree"])
    require(candidate.is_relative_to(root / "worktrees") and candidate != root / "worktrees", "Separate candidate worktree required")
    require(Path(git(candidate, "rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()).resolve() == common,
            "Candidate must share primary Git objects")
    require(head(candidate) == plan["candidate_head"], "Candidate HEAD changed")
    require(not git(candidate, "status", "--porcelain=v1", "--untracked-files=no"), "Candidate has tracked changes")
    git(root, "merge-base", "--is-ancestor", plan["base_head"], plan["candidate_head"])
    interval = plan["base_head"] + ".." + plan["candidate_head"]
    commits = git(root, "rev-list", "--reverse", interval).decode().splitlines()
    require(commits and commits == plan["commits"], "Candidate commit list differs")
    require(not git(root, "rev-list", "--min-parents=2", interval), "Merge commits require a separate reviewed protocol")
    mapping = plan["commit_map"]
    require([entry["candidate"] for entry in mapping] == commits, "Source-to-candidate mapping differs")
    for entry in mapping:
        require(re.fullmatch(r"[0-9a-f]{40}", entry["source"]), "Full source commit SHA required")
        require(git(root, "cat-file", "-t", entry["source"]).strip() == b"commit", "Source mapping is not a commit")
        require(patch_sha(root, entry["source"]) == patch_sha(root, entry["candidate"]), "Source/candidate exact patches differ")
    paths = set(plan["paths"])
    require(len(paths) == len(plan["paths"]) and paths, "Nonempty unique exact path set required")
    for name in paths:
        path = Path(name)
        require(not path.is_absolute() and path.as_posix() == name and ".." not in path.parts and name != ".", "Literal relative paths required")
        require(name not in FORBIDDEN and not name.startswith(("state/", "planning/")), "Registry/generated view or lock in source candidate")
    changed = set(filter(None, git(root, "diff", "--name-only", "--no-renames", "-z", plan["base_head"], plan["candidate_head"]).decode().split("\0")))
    require(changed == paths, "Candidate changed paths differ from exact plan")
    # Check every commit too: temporary changes to forbidden/unreviewed paths are not allowed.
    for commit in commits:
        touched = set(filter(None, git(root, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "-z", commit).decode().split("\0")))
        require(touched <= paths, "Candidate commit touches an unplanned path")
    require(not git(root, "diff", "--cached", "--name-only", "-z"), "Primary index has staged changes")
    dirty = set(filter(None, (git(root, "diff", "--name-only", "--no-renames", "-z", "HEAD") +
                             git(root, "ls-files", "--others", "--exclude-standard", "-z")).decode().split("\0")))
    require(not any(a == b or a.startswith(b + "/") or b.startswith(a + "/") for a in paths for b in dirty), "Candidate intersects dirty primary paths")
    tracked = set(filter(None, git(root, "ls-files", "-z", "--", *sorted(paths)).decode().split("\0")))
    for name in paths:
        require(name in tracked or not os.path.lexists(root / name), "New candidate path already exists in primary (including ignored files)")
        require(not any((root / parent).is_symlink() for parent in Path(name).parents), "Candidate parent is a primary symlink")
    bindings = plan["bindings"]
    require(bindings, "Existing review/evidence/dependency bindings required")
    for binding in bindings:
        require(re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]), "Full binding SHA256 required")
        require(sha(inside(root, binding["path"])) == binding["sha256"], "Capsule binding changed: " + binding["path"])
    return {"base_head": plan["base_head"], "candidate_head": plan["candidate_head"],
            "paths": sorted(paths), "dirty_primary_paths": sorted(dirty), "commit_map": mapping,
            "bindings": bindings}


def admit(out, phase):
    stable = 0
    deadline = time.monotonic() + 180
    with (out / (phase + "-admission.jsonl")).open("x") as samples:
        while time.monotonic() < deadline:
            available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))) * 1024
            samples.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "mem_available_bytes": available}) + "\n")
            samples.flush()
            stable = stable + 1 if available >= 4 * 1024**3 else 0
            if stable >= 3:
                break
            time.sleep(1)
    require(stable >= 3, "Stable 4 GiB admission not achieved")


def common_check(root, out, fd, report):
    admit(out, "check")
    supervisor_path = root / "tools/build/qemu_host.py"
    spec = importlib.util.spec_from_file_location("integration_supervisor", supervisor_path)
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    report["supervisor_sha256"] = sha(supervisor_path)
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    environment = dict(ENV, MAKEFLAGS="-j2", CMAKE_BUILD_PARALLEL_LEVEL="2", MAX_JOBS="2")
    record = {"argv": ["make", "check"], "address_space_limit_bytes": 2 * 1024**3,
              "aggregate_rss_stop_bytes": 2 * 1024**3, "max_jobs": 2, "peak_owned_tree_rss_bytes": 0}
    report["common_check"] = record
    with (out / "make-check.log").open("xb") as log, (out / "make-check.samples.jsonl").open("x") as samples:
        process = subprocess.Popen(["make", "check"], cwd=root, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True,
                                   pass_fds=(fd,), preexec_fn=limits)
        started = time.monotonic()
        record["owned_session"] = process.pid
        try:
            while process.poll() is None:
                current = supervisor.sample(process.pid)
                samples.write(json.dumps(current) + "\n")
                samples.flush()
                record["peak_owned_tree_rss_bytes"] = max(record["peak_owned_tree_rss_bytes"], current["owned_tree_rss_bytes"])
                reason = ("deadline" if time.monotonic() - started > 180 else
                          "aggregate-rss-limit" if current["owned_tree_rss_bytes"] > 2 * 1024**3 else
                          "host-pressure" if current["MemAvailable_bytes"] < 4 * 1024**3 or supervisor.pressured(current) else None)
                if reason:
                    record["stop_reason"] = reason
                    supervisor.terminate(process)
                    break
                time.sleep(0.2)
            record["exit_code"] = process.wait(timeout=5)
        except BaseException:
            supervisor.terminate(process)
            raise
        finally:
            after = supervisor.sample(process.pid)
            if any(entry["state"] != "Z" for entry in after["owned_processes"]):
                supervisor.terminate(process)
                after = supervisor.sample(process.pid)
            record["after"] = after
    require(record["exit_code"] == 0 and not record.get("stop_reason") and not any(entry["state"] != "Z" for entry in after["owned_processes"]), "Common check failed; published HEAD is retained")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["audit", "publish"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--lock-timeout", type=float, default=30)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    require(0 < args.lock_timeout <= 3600, "Lock timeout must be positive and at most one hour")
    require(out.is_relative_to(root / "artifacts") or out.is_relative_to(root / "worktrees"), "Output must stay in primary artifacts or worktrees")
    out.mkdir(parents=True, exist_ok=False)
    report = {"kind": "host-test", "origin": "local-host", "outcome": "fail", "mode": args.mode,
              "started_at": datetime.now(timezone.utc).isoformat(), "command": sys.orig_argv,
              "tool_sha256": sha(Path(__file__).resolve()), "publication_attempted": False}
    try:
        plan, report["plan_sha256"] = frozen_json(args.plan)
        with integration_lock(root, args.lock_timeout) as (fd, waited):
            report["lock_wait_seconds"] = waited
            report["audit"] = audit(root, plan)
            if args.mode == "publish":
                require(args.approval is not None, "Concrete root approval receipt required")
                approval, report["approval_sha256"] = frozen_json(args.approval)
                require(approval["approved_by"] == "root" and approval["plan_sha256"] == report["plan_sha256"] and approval["resource_lease"], "Approval must bind this exact plan and root resource lease")
                admit(out, "publication")
                require(head(root) == plan["base_head"], "Primary HEAD moved after audit")
                report["publication_attempted"] = True
                git(root, "merge", "--ff-only", "--no-edit", plan["candidate_head"], fd=fd)
                report["published_head"] = head(root)
                require(report["published_head"] == plan["candidate_head"], "Published HEAD differs from candidate")
                common_check(root, out, fd, report)
                require(head(root) == plan["candidate_head"], "Primary HEAD moved during common check")
            report["outcome"] = "pass"
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        report["recorded_at"] = datetime.now(timezone.utc).isoformat()
        report["actual_primary_head_after"] = head(root)
        report["git_commands"] = GIT_COMMANDS
        report["artifacts"] = {str(path.relative_to(root)): sha(path) for path in out.iterdir() if path.is_file()}
        (out / "evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "evidence": str(out / "evidence.json"), "error": report.get("error")}, indent=2))
    return 0 if report["outcome"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
