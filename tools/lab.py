#!/usr/bin/env python3
"""Dependency-free task and experiment ledger. This tool never controls a phone."""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

SCOPES = {"host", "android-readonly", "android-app", "native"}
KINDS = {"source-review", "host-test", "android-userland", "native-device"}
ORIGINS = {"synthetic", "upstream", "user-report", "local-host", "local-device"}
STATUSES = {"pending", "in_progress", "blocked", "done"}


class LabError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise LabError(f"Cannot read {path}: {exc}") from exc


def within(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise LabError("Paths must stay inside the project, including symlinks")
    return path


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".lab-", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def item(items, identifier):
    for obj in items:
        if obj["id"] == identifier:
            return obj
    raise LabError(f"Unknown ID: {identifier}")


def permitted(state, scope):
    return state["project"]["permissions"].get(scope) is True


def prerequisites(state, task):
    return [dep for dep in task["depends_on"] if item(state["tasks"], dep)["status"] != "done"]


def evidence(root, relative, expected_kind=None):
    path = within(root, relative)
    doc = read_json(path)
    if doc.get("kind") not in KINDS or doc.get("origin") not in ORIGINS:
        raise LabError("Evidence requires a valid kind and origin")
    if expected_kind and doc["kind"] != expected_kind:
        raise LabError(f"Expected {expected_kind} evidence, got {doc['kind']}")
    if doc.get("outcome") not in {"pass", "fail", "inconclusive"}:
        raise LabError("Evidence outcome must be pass, fail or inconclusive")
    if not str(doc.get("summary", "")).strip() or not doc.get("recorded_at"):
        raise LabError("Evidence requires summary and recorded_at")
    try:
        stamp = datetime.fromisoformat(doc["recorded_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone missing")
    except (ValueError, AttributeError) as exc:
        raise LabError("recorded_at must be a real ISO timestamp with timezone") from exc
    if doc["kind"] in {"android-userland", "native-device"}:
        if doc["origin"] != "local-device" or not doc.get("device_inventory"):
            raise LabError("Device evidence requires local-device origin and device_inventory")
        inventory = read_json(within(root, doc["device_inventory"]))
        if inventory.get("origin") != "local-device" or not inventory.get("observed_at"):
            raise LabError("Inventory must be an actual dated local-device observation")
        if doc["kind"] == "native-device" and inventory.get("matches_reference_target") is not True:
            raise LabError("Native evidence requires the verified reference model")
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise LabError("Evidence must reference at least one existing artifact")
    for name in artifacts:
        if not within(root, name).is_file():
            raise LabError(f"Missing evidence artifact: {name}")
    return doc


def evidence_hash(root, relative):
    return hashlib.sha256(within(root, relative).read_bytes()).hexdigest()


def validate(root, state):
    if state.get("schema_version") != 1:
        raise LabError("Unsupported ledger schema")
    if set(state["project"]["permissions"]) != SCOPES:
        raise LabError("Project must declare all execution scopes")
    if any(type(v) is not bool for v in state["project"]["permissions"].values()):
        raise LabError("Execution permissions must be booleans")
    tasks = state["tasks"]
    ids = [t["id"] for t in tasks]
    if any(not re.fullmatch(r"[A-Z][A-Z0-9]*-[0-9]{3,}", identifier) for identifier in ids):
        raise LabError("Task IDs must look like GPU-001")
    if len(set(ids)) != len(ids):
        raise LabError("Duplicate task IDs")
    visited, active = set(), set()

    def walk(identifier):
        if identifier in active:
            raise LabError(f"Dependency cycle at {identifier}")
        if identifier in visited:
            return
        active.add(identifier)
        task = item(tasks, identifier)
        for dep in task["depends_on"]:
            walk(dep)
        active.remove(identifier)
        visited.add(identifier)

    for task in tasks:
        walk(task["id"])
        if task["status"] not in STATUSES or task["scope"] not in SCOPES:
            raise LabError(f"Invalid status/scope: {task['id']}")
        if task.get("evidence_kind") not in KINDS:
            raise LabError(f"Missing evidence kind: {task['id']}")
        expected = {"host": {"host-test", "source-review"}, "android-readonly": {"android-userland"},
                    "android-app": {"android-userland"}, "native": {"native-device"}}
        if task["evidence_kind"] not in expected[task["scope"]]:
            raise LabError(f"Scope/evidence mismatch: {task['id']}")
        if not task.get("acceptance") or not task.get("paths"):
            raise LabError(f"Task needs acceptance criteria and file boundaries: {task['id']}")
        for name in task["paths"]:
            within(root, name)
        if task["status"] == "in_progress" and not task.get("owner"):
            raise LabError(f"Unowned active task: {task['id']}")
        if task["status"] == "done":
            if prerequisites(state, task):
                raise LabError(f"Completed task has incomplete dependencies: {task['id']}")
            doc = evidence(root, task.get("evidence", ""), task["evidence_kind"])
            if doc["outcome"] != "pass":
                raise LabError(f"Completed task needs passing evidence: {task['id']}")
            if task.get("evidence_sha256") != evidence_hash(root, task["evidence"]):
                raise LabError(f"Recorded evidence changed: {task['id']}")
    experiments = state["experiments"]
    if len({e["id"] for e in experiments}) != len(experiments):
        raise LabError("Duplicate experiment IDs")
    for exp in experiments:
        task = item(tasks, exp["task"])
        if exp["kind"] != task["evidence_kind"]:
            raise LabError("Experiment kind disagrees with its task")
        if exp["status"] not in {"planned", "recorded"}:
            raise LabError("Invalid experiment status")
        if not within(root, exp["procedure"]).is_file():
            raise LabError("Experiment procedure must exist")
        if exp["timeout_seconds"] <= 0:
            raise LabError("An experiment requires a positive timeout")
        if exp["status"] == "recorded":
            doc = evidence(root, exp["evidence"], exp["kind"])
            if exp["outcome"] != doc["outcome"]:
                raise LabError("Experiment outcome disagrees with evidence")
            if exp.get("evidence_sha256") != evidence_hash(root, exp["evidence"]):
                raise LabError(f"Recorded evidence changed: {exp['id']}")
    sources = read_json(root / "research/sources.json")
    source_ids = [s["id"] for s in sources["sources"]]
    if len(source_ids) != len(set(source_ids)):
        raise LabError("Duplicate source IDs")
    for source in sources["sources"]:
        if not source["url"].startswith("https://") or not source.get("relevance"):
            raise LabError("Each source needs an HTTPS URL and a relevance explanation")
    for task in tasks:
        if any(identifier not in source_ids for identifier in task.get("sources", [])):
            raise LabError(f"Unknown source reference: {task['id']}")
    return state


@contextlib.contextmanager
def transaction(root, action, owner):
    with (root / "state/.lab.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / "state/lab.json"
        state = validate(root, read_json(path))
        original = copy.deepcopy(state)
        yield state
        if state != original:
            state["updated_at"] = now()
            state["events"].append({"at": now(), "action": action, "owner": owner})
            validate(root, state)
            atomic_json(path, state)


def owned(task, owner):
    if task.get("owner") != owner:
        raise LabError(f"Task belongs to {task.get('owner')!r}, not {owner!r}")


def render(state):
    lines = ["# S24 iOS / Exynos — status", "", "> Generated by tools/lab.py from state/lab.json. Do not edit manually.", "",
             f"Phase: **{state['project']['phase']}**. Registry updated: {state['updated_at']}.", "",
             "Authorized scopes: " + ", ".join(s for s in sorted(SCOPES) if permitted(state, s)) + ".", "",
             "| Task | Status | Scope | Owner | Dependencies |", "|---|---|---|---|---|"]
    for task in state["tasks"]:
        title = task["title"].replace("|", "/")
        lines.append(f"| {task['id']} — {title} | {task['status']} | {task['scope']} | {task.get('owner') or '—'} | {', '.join(task['depends_on']) or '—'} |")
    lines += ["", "## Experiments", ""]
    if not state["experiments"]:
        lines.append("No experiments have been registered. No hardware runs have been recorded.")
    for exp in state["experiments"]:
        lines.append(f"- {exp['id']}: {exp['status']}, {exp['kind']}, outcome: {exp.get('outcome', 'not measured')}.")
    lines += ["", "Details: `python3 tools/lab.py task show ID`; next available task: `python3 tools/lab.py task next`.", ""]
    return "\n".join(lines)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("doctor")
    status = sub.add_parser("status")
    status.add_argument("--write", action="store_true")
    sub.add_parser("sources")
    sub.add_parser("history")
    task = sub.add_parser("task").add_subparsers(dest="operation", required=True)
    task.add_parser("list")
    add = task.add_parser("add")
    add.add_argument("--file", required=True)
    add.add_argument("--owner", required=True)
    nxt = task.add_parser("next")
    nxt.add_argument("--scope", choices=sorted(SCOPES), default="host")
    show = task.add_parser("show")
    show.add_argument("id")
    for name in ["claim", "release", "block", "done"]:
        q = task.add_parser(name)
        q.add_argument("id")
        q.add_argument("--owner", required=True)
        if name == "block":
            q.add_argument("--reason", required=True)
        if name == "done":
            q.add_argument("--evidence", required=True)
    exp = sub.add_parser("experiment").add_subparsers(dest="operation", required=True)
    plan = exp.add_parser("plan")
    plan.add_argument("id")
    plan.add_argument("--task", required=True)
    plan.add_argument("--owner", required=True)
    plan.add_argument("--hypothesis", required=True)
    plan.add_argument("--procedure", required=True)
    plan.add_argument("--timeout-seconds", type=int, required=True)
    record = exp.add_parser("record")
    record.add_argument("id")
    record.add_argument("--owner", required=True)
    record.add_argument("--evidence", required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    root = args.root.resolve()
    state = validate(root, read_json(root / "state/lab.json"))
    if args.command == "validate":
        print(f"OK: {len(state['tasks'])} tasks, {len(state['experiments'])} experiments; dependencies and evidence valid")
    elif args.command == "doctor":
        print("Host:", sys.version.split()[0], "; project:", root)
        for name in ["git", "python3", "adb", "clang", "cmake", "ninja", "qemu-system-aarch64", "aarch64-linux-gnu-gcc", "java", "gradle"]:
            print(f"{name}: {shutil.which(name) or 'not installed (only needed for the relevant task)'}")
        print("No phone commands executed. Bootloader unlock is user-reported; root, model and firmware are unverified.")
    elif args.command == "status":
        if args.write:
            # Lock through the read and publication so another agent cannot publish a stale snapshot.
            with (root / "state/.lab.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                state = validate(root, read_json(root / "state/lab.json"))
                (root / "STATUS.md").write_text(render(state))
            print("Updated STATUS.md")
        else:
            print(render(state), end="")
    elif args.command == "sources":
        for source in read_json(root / "research/sources.json")["sources"]:
            pin = source.get("revision") or "UNPINNED — inspect and pin before code reuse"
            print(f"{source['id']}: {source['url']} [{pin}]\n  {source['relevance']}")
    elif args.command == "history":
        for event in state["events"]:
            print(f"{event['at']} {event['owner']}: {event['action']}")
    elif args.command == "task":
        if args.operation == "add":
            task = read_json(within(root, args.file))
            if task.get("status") != "pending" or task.get("owner"):
                raise LabError("A new task must be pending and unowned")
            with transaction(root, f"task.add:{task['id']}", args.owner) as state:
                state["tasks"].append(task)
            print(f"Added task {task['id']}")
        elif args.operation == "show":
            print(json.dumps(item(state["tasks"], args.id), ensure_ascii=False, indent=2))
        elif args.operation in {"list", "next"}:
            for task in state["tasks"]:
                deps = prerequisites(state, task)
                if args.operation == "next" and not (task["status"] == "pending" and not deps and task["scope"] == args.scope and permitted(state, task["scope"])):
                    continue
                reason = f"waiting: {','.join(deps)}" if deps else ("scope not authorized" if not permitted(state, task["scope"]) else "dependencies ready")
                print(f"{task['id']} [{task['status']}] {task['title']} — {reason}")
        else:
            with transaction(root, f"task.{args.operation}:{args.id}", args.owner) as state:
                task = item(state["tasks"], args.id)
                if args.operation == "claim":
                    if task["status"] != "pending":
                        raise LabError("Only a pending task can be claimed; resolve or release an old claim explicitly")
                    if prerequisites(state, task):
                        raise LabError("Complete dependencies before claiming this task")
                    if not permitted(state, task["scope"]):
                        raise LabError("Execution scope is not authorized; a ledger flag is not user consent")
                    task.update(status="in_progress", owner=args.owner, started_at=now())
                else:
                    owned(task, args.owner)
                    if task["status"] not in {"in_progress", "blocked"}:
                        raise LabError("Task must be in progress or blocked")
                    if args.operation == "release":
                        task.update(status="pending", owner=None)
                        task.pop("blocked_reason", None)
                    elif args.operation == "block":
                        task.update(status="blocked", blocked_reason=args.reason)
                    elif args.operation == "done":
                        if not permitted(state, task["scope"]):
                            raise LabError("Execution scope is not authorized")
                        doc = evidence(root, args.evidence, task["evidence_kind"])
                        if doc["outcome"] != "pass":
                            raise LabError("A failing or inconclusive result cannot complete a task")
                        task.update(status="done", evidence=args.evidence, evidence_sha256=evidence_hash(root, args.evidence), finished_at=now())
                        task.pop("blocked_reason", None)
            print(f"Task {args.id}: {args.operation}")
    elif args.command == "experiment":
        with transaction(root, f"experiment.{args.operation}:{args.id}", args.owner) as state:
            if args.operation == "plan":
                if any(e["id"] == args.id for e in state["experiments"]):
                    raise LabError("Experiment ID already exists; retain the old result and use a new ID")
                task = item(state["tasks"], args.task)
                owned(task, args.owner)
                if task["status"] != "in_progress":
                    raise LabError("Claim the task before planning an experiment")
                state["experiments"].append({"id": args.id, "task": args.task, "owner": args.owner,
                    "kind": task["evidence_kind"], "status": "planned", "hypothesis": args.hypothesis,
                    "procedure": args.procedure, "timeout_seconds": args.timeout_seconds, "created_at": now()})
            else:
                exp = item(state["experiments"], args.id)
                if exp["owner"] != args.owner:
                    raise LabError("Experiment belongs to a different owner")
                if exp["status"] != "planned":
                    raise LabError("Recorded experiments are immutable; create a new experiment")
                task = item(state["tasks"], exp["task"])
                owned(task, args.owner)
                if task["status"] != "in_progress":
                    raise LabError("The task must still be active when recording its experiment")
                if not permitted(state, task["scope"]):
                    raise LabError("Execution scope is not authorized")
                doc = evidence(root, args.evidence, exp["kind"])
                exp.update(status="recorded", evidence=args.evidence, evidence_sha256=evidence_hash(root, args.evidence), outcome=doc["outcome"], recorded_at=now())
        print(f"Experiment {args.id}: {args.operation}; this command does not execute tests")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (LabError, KeyError, TypeError, ValueError) as exc:
        print(f"lab: {exc}", file=sys.stderr)
        sys.exit(2)
