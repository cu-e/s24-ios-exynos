#!/usr/bin/env python3
"""Dependency-free task and experiment ledger. This tool never controls a phone."""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import sys
import tempfile

SCOPES = {"host", "android-readonly", "android-app", "native"}
KINDS = {"source-review", "host-test", "android-userland", "native-device"}
ORIGINS = {"synthetic", "upstream", "user-report", "local-host", "local-device"}
STATUSES = {"pending", "in_progress", "blocked", "done"}
ACTIVE = {"in_progress", "blocked"}
COLUMNS = [("ready", "Ready"), ("in_progress", "In progress"), ("blocked", "Blocked"),
           ("waiting", "Waiting"), ("gated", "Needs authorization"), ("done", "Done")]


class LabError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise LabError(f"Cannot read {path}: {exc}") from exc


def _within_resolved(root, value):
    """Resolve a candidate below an already canonical project root."""
    path = (root / value).resolve()
    if path.parts[:len(root.parts)] != root.parts:
        raise LabError("Paths must stay inside the project, including symlinks")
    return path


def within(root, value):
    return _within_resolved(root.resolve(), value)


class _ValidationFiles:
    """Filesystem observations reused only until one validate() call returns."""

    def __init__(self, root):
        self.root = root.resolve()
        self.paths = {}
        self.files = {}

    def within(self, value):
        try:
            return self.paths[value]
        except KeyError:
            path = _within_resolved(self.root, value)
            self.paths[value] = path
            return path

    def is_file(self, value):
        path = self.within(value)
        try:
            return self.files[path]
        except KeyError:
            result = path.is_file()
            self.files[path] = result
            return result


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


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".lab-", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
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


def path_conflicts(state, task):
    """Literal relative path ownership, including parent/child directory overlap."""
    result = []
    for other in state["tasks"]:
        if other["id"] == task["id"] or other["status"] not in ACTIVE:
            continue
        for left in task["paths"]:
            a = Path(left).parts
            if any(a[:len(b)] == b or b[:len(a)] == a for b in (Path(p).parts for p in other["paths"])):
                result.append(other["id"])
                break
    return result


def readiness(state, task):
    if task["status"] != "pending":
        return task["status"], [task["blocked_reason"]] if task["status"] == "blocked" else []
    reasons = []
    deps = prerequisites(state, task)
    if deps:
        reasons.append("Dependencies: " + ", ".join(deps))
    conflicts = path_conflicts(state, task)
    if conflicts:
        reasons.append("Paths reserved by: " + ", ".join(conflicts))
    if not permitted(state, task["scope"]):
        return "gated", ["Scope not authorized: " + task["scope"], *reasons]
    return ("waiting", reasons) if reasons else ("ready", [])


def ordered_tasks(state):
    return sorted(state["tasks"], key=lambda t: -t.get("priority", 50))


def claim_task(state, task, owner, branch=None, worktree=None):
    column, reasons = readiness(state, task)
    if column != "ready":
        raise LabError("Task is not claimable: " + ("; ".join(reasons) or task["status"]))
    task.update(status="in_progress", owner=owner, started_at=now(), last_heartbeat=now(), updated_at=now())
    for key, value in {"branch": branch, "worktree": worktree}.items():
        if value is not None:
            task[key] = value
        else:
            task.pop(key, None)


def evidence(root, relative, expected_kind=None, *, _files=None):
    resolve = _files.within if _files is not None else lambda name: within(root, name)
    path = resolve(relative)
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
        inventory = read_json(resolve(doc["device_inventory"]))
        if inventory.get("origin") != "local-device" or not inventory.get("observed_at"):
            raise LabError("Inventory must be an actual dated local-device observation")
        if doc["kind"] == "native-device" and inventory.get("matches_reference_target") is not True:
            raise LabError("Native evidence requires the verified reference model")
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise LabError("Evidence must reference at least one existing artifact")
    for name in artifacts:
        exists = _files.is_file(name) if _files is not None else resolve(name).is_file()
        if not exists:
            raise LabError(f"Missing evidence artifact: {name}")
    return doc


def evidence_hash(root, relative, *, _files=None):
    path = _files.within(relative) if _files is not None else within(root, relative)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
    files = _ValidationFiles(root)
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
            if Path(name).is_absolute() or ".." in Path(name).parts or any(c in name for c in "*?[]"):
                raise LabError("Task boundaries must be literal relative paths without traversal or globs")
            if files.within(name) != files.root / name:
                raise LabError("Use canonical task paths, not symlink aliases")
        if type(task.get("priority", 50)) is not int or not 0 <= task.get("priority", 50) <= 100:
            raise LabError("Task priority must be an integer from 0 to 100")
        if task.get("owner") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,79}", task["owner"]):
            raise LabError("Owner must be a stable identifier without whitespace, up to 80 characters")
        if task["status"] in ACTIVE and not task.get("owner"):
            raise LabError(f"Unowned active task: {task['id']}")
        if task["status"] == "pending" and task.get("owner"):
            raise LabError(f"Pending task must be unowned: {task['id']}")
        if task["status"] == "blocked" and not str(task.get("blocked_reason", "")).strip():
            raise LabError("Blocked tasks require a concrete reason")
        for key in ["progress_note", "next_step", "branch", "worktree", "priority_reason"]:
            if key in task and (not isinstance(task[key], str) or len(task[key]) > 4000):
                raise LabError(f"Invalid task context: {key}")
        if task.get("handoff") and not files.is_file(task["handoff"]):
            raise LabError("Handoff must reference an existing project file")
        if task.get("last_heartbeat"):
            try:
                if datetime.fromisoformat(task["last_heartbeat"]).tzinfo is None:
                    raise ValueError("timezone required")
            except (ValueError, TypeError) as exc:
                raise LabError("Heartbeat requires an ISO timestamp with timezone") from exc
        if task["status"] in ACTIVE and path_conflicts(state, task):
            raise LabError(f"Active task paths overlap: {task['id']}")
        if task["status"] == "done":
            if prerequisites(state, task):
                raise LabError(f"Completed task has incomplete dependencies: {task['id']}")
            doc = evidence(root, task.get("evidence", ""), task["evidence_kind"], _files=files)
            if doc["outcome"] != "pass":
                raise LabError(f"Completed task needs passing evidence: {task['id']}")
            if task.get("evidence_sha256") != evidence_hash(root, task["evidence"], _files=files):
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
        if not files.is_file(exp["procedure"]):
            raise LabError("Experiment procedure must exist")
        if exp["timeout_seconds"] <= 0:
            raise LabError("An experiment requires a positive timeout")
        if exp["status"] == "recorded":
            doc = evidence(root, exp["evidence"], exp["kind"], _files=files)
            if exp["outcome"] != doc["outcome"]:
                raise LabError("Experiment outcome disagrees with evidence")
            if exp.get("evidence_sha256") != evidence_hash(root, exp["evidence"], _files=files):
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
            event = {"at": now(), "action": action, "owner": owner}
            changes = []
            for task in state["tasks"]:
                old = next((t for t in original["tasks"] if t["id"] == task["id"]), {})
                if task != old:
                    change = {k: task[k] for k in ["id", "status", "owner", "priority", "priority_reason", "progress_note", "next_step", "blocked_reason", "last_heartbeat", "branch", "worktree", "handoff"] if k in task}
                    if old and task.get("paths") != old.get("paths"):
                        change["paths"] = list(task["paths"])
                    changes.append(change)
            if changes:
                event["tasks"] = changes
            if state["project"]["permissions"] != original["project"]["permissions"]:
                event["permissions"] = dict(state["project"]["permissions"])
            state["events"].append(event)
            validate(root, state)
            atomic_json(path, state)
            try:
                publish_views(root, state)
            except (OSError, LabError) as exc:
                raise LabError("Registry saved; generated views need refresh with 'board --write': " + str(exc)) from exc


def decision_record(root, relative):
    """An owner decision must be an existing regular file under docs/decisions/."""
    path = within(root, relative)
    if not path.is_file() or path.parent != (root / "docs/decisions").resolve():
        raise LabError("The decision must be an existing file directly under docs/decisions/")
    return path.relative_to(root.resolve()).as_posix()


def owned(task, owner):
    if task.get("owner") != owner:
        raise LabError(f"Task belongs to {task.get('owner')!r}, not {owner!r}")


def md(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")


def board_snapshot(root, state, stamp=None):
    stamp = stamp or now()
    columns = {key: [] for key, _ in COLUMNS}
    cards, agents = [], {}
    for task in ordered_tasks(state):
        column, reasons = readiness(state, task)
        card = copy.deepcopy(task)
        card.update(column=column, reasons=reasons, priority=task.get("priority", 50),
                    card_path=f"planning/tasks/{task['id']}.md")
        columns[column].append(task["id"])
        if task["status"] in ACTIVE:
            heartbeat = task.get("last_heartbeat")
            age = max(0, (datetime.fromisoformat(stamp) - datetime.fromisoformat(heartbeat)).total_seconds()) if heartbeat else None
            card["report_health"] = "unknown" if age is None else ("stale" if age > 1800 else "recent")
            agents.setdefault(task["owner"], []).append({k: card.get(k) for k in ["id", "status", "last_heartbeat", "report_health", "progress_note", "next_step", "handoff", "branch", "worktree"]})
        cards.append(card)
    return {"schema_version": 1, "generated_at": stamp, "ledger_updated_at": state["updated_at"],
            "registry_sha256": hashlib.sha256((root / "state/lab.json").read_bytes()).hexdigest(),
            "phase": state["project"]["phase"], "columns": columns, "tasks": cards, "agents": agents,
            "recent_events": state["events"][-20:]}


def render_board(snapshot):
    lines = ["# S24 iOS / Exynos — Kanban", "",
             "> Generated from state/lab.json. Use the CLI; do not edit this board or its task cards.", "",
             f"Phase: **{md(snapshot['phase'])}**. Snapshot: {snapshot['generated_at']}.", "",
             f"Registry SHA256: `{snapshot['registry_sha256']}`. Run `python3 tools/lab.py board --check` to detect stale files.", "",
             "[Workflow](docs/planning.md) · [All task details](planning/README.md) · [Machine view](state/board.json) · [Status](STATUS.md)", "",
             "| " + " | ".join(f"{label} ({len(snapshot['columns'][key])})" for key, label in COLUMNS) + " |",
             "| " + " | ".join("---" for _ in COLUMNS) + " |"]
    tasks = {t["id"]: t for t in snapshot["tasks"]}
    for row in range(max((len(v) for v in snapshot["columns"].values()), default=0)):
        cells = []
        for key, _ in COLUMNS:
            ids = snapshot["columns"][key]
            if row >= len(ids):
                cells.append("—")
                continue
            card = tasks[ids[row]]
            detail = [f"[**{card['id']}**]({card['card_path']}) · P{card['priority']}", md(card["title"]),
                      f"{md(card['scope'])} · {md(card.get('owner') or 'unassigned')}"]
            if card["reasons"]:
                detail.append(md("; ".join(card["reasons"])))
            cells.append("<br>".join(detail))
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Claimed work and agent reports", "",
              "Owner names identify cooperating agents, not authenticated processes. A recent report is not proof that an agent is running. Reports older than 30 minutes are marked stale at snapshot time; claims never expire automatically.", "",
              "| Owner | Task | State | Last heartbeat (UTC) | Report | Progress / next step | Context |",
              "|---|---|---|---|---|---|---|"]
    for owner, reports in sorted(snapshot["agents"].items()):
        for report in reports:
            context = "; ".join(f"{k}: {report[k]}" for k in ["branch", "worktree", "handoff"] if report.get(k))
            progress = (report.get("progress_note") or "No progress note") + " / " + (report.get("next_step") or "Next step not reported")
            lines.append("| " + " | ".join(md(x) for x in [owner, report["id"], report["status"], report.get("last_heartbeat") or "not reported", report["report_health"], progress, context or "—"]) + " |")
    if not snapshot["agents"]:
        lines.append("| — | — | No claimed work | — | — | — | — |")
    lines += ["", "## Recent activity", ""]
    for event in snapshot["recent_events"]:
        lines.append(f"- {event['at']} · {md(event['owner'])} · {md(event['action'])}")
        for change in event.get("tasks", []):
            detail = change.get("progress_note") or change.get("blocked_reason") or change["status"]
            lines.append(f"  - {change['id']}: {md(detail)}")
    lines += ["", "Use a unique owner per agent session. Atomically take ready work:", "",
              "```sh", "python3 tools/lab.py task claim-next --owner agent-your-session --scope host", "```", ""]
    return "\n".join(lines)


def render_card(task):
    lines = [f"# {task['id']} — {md(task['title'])}", "",
             "> Generated task card. Edit state through tools/lab.py, not this file.", "",
             "[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)", "",
             "| Field | Value |", "|---|---|",
             f"| State / column | {task['status']} / {task['column']} |",
             f"| Owner | {md(task.get('owner') or 'unassigned')} |",
             f"| Priority | {task['priority']} (higher first; default 50) |",
             f"| Scope / evidence | {task['scope']} / {task['evidence_kind']} |",
             f"| Dependencies | {md(', '.join(task['depends_on']) or 'none')} |"]
    for key in ["started_at", "last_heartbeat", "report_health", "progress_note", "next_step", "branch", "worktree", "handoff"]:
        if task.get(key):
            lines.append(f"| {key} | {md(task[key])} |")
    lines += ["", "## Readiness", "", md("; ".join(task["reasons"]) or task["column"]),
              "", "## Reserved paths", ""]
    lines += [f"- `{name}`" for name in task["paths"]]
    lines += ["", "## Acceptance", ""] + [f"- {md(text)}" for text in task["acceptance"]]
    lines += ["", "## Steps", ""] + [f"{i}. {md(text)}" for i, text in enumerate(task.get("steps", []), 1)]
    if task.get("evidence"):
        path = task.get("evidence_translation") or task["evidence"]
        lines += ["", f"Evidence: [{path}](../../{path}).", f"Original evidence SHA256: `{task.get('evidence_sha256', 'unrecorded')}`."]
    lines += ["", "## CLI", "", "```sh", f"python3 tools/lab.py task show {task['id']}"]
    if task["status"] == "pending":
        lines.append(f"python3 tools/lab.py task claim {task['id']} --owner agent-your-session")
    elif task["status"] in ACTIVE:
        lines.append(f"python3 tools/lab.py task update {task['id']} --owner {shlex.quote(task['owner'])} --note 'Observed result' --next-step 'Next concrete check'")
    lines += ["```", ""]
    return "\n".join(lines)


def publish_views(root, state):
    """Caller holds the ledger lock. Publish the JSON index last to detect partial refreshes."""
    snapshot = board_snapshot(root, state)
    views = view_texts(state, snapshot)
    for name, text in views.items():
        path = within(root, name)
        try:
            unchanged = path.is_file() and path.read_bytes() == text.encode()
        except OSError:
            unchanged = False  # Preserve atomic replacement when an existing view cannot be read.
        if not unchanged:
            atomic_text(path, text)
    snapshot["view_sha256"] = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in views.items()}
    atomic_json(within(root, "state/board.json"), snapshot)


def view_texts(state, snapshot):
    return {"STATUS.md": render(state), "BOARD.md": render_board(snapshot),
            **{card["card_path"]: render_card(card) for card in snapshot["tasks"]}}


def check_views(root):
    snapshot = read_json(within(root, "state/board.json"))
    if snapshot.get("registry_sha256") != hashlib.sha256((root / "state/lab.json").read_bytes()).hexdigest():
        raise LabError("Planning views are stale; run 'board --write'")
    state = read_json(root / "state/lab.json")
    try:
        if datetime.fromisoformat(snapshot["generated_at"]).tzinfo is None:
            raise ValueError("timezone required")
        expected = board_snapshot(root, state, snapshot["generated_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LabError("Invalid planning snapshot timestamp; run 'board --write'") from exc
    texts = view_texts(state, expected)
    expected["view_sha256"] = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in texts.items()}
    if snapshot != expected:
        raise LabError("Planning machine view or renderer is out of date; run 'board --write'")
    required = {"BOARD.md", "STATUS.md"} | {f"planning/tasks/{t['id']}.md" for t in read_json(root / "state/lab.json")["tasks"]}
    if set(snapshot.get("view_sha256", {})) != required:
        raise LabError("Planning view index is incomplete; run 'board --write'")
    for name, expected in snapshot["view_sha256"].items():
        path = within(root, name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise LabError(f"Planning view missing or edited: {name}; run 'board --write'")


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
    board = sub.add_parser("board")
    board_mode = board.add_mutually_exclusive_group()
    board_mode.add_argument("--write", action="store_true")
    board_mode.add_argument("--check", action="store_true")
    board_mode.add_argument("--json", action="store_true")
    sub.add_parser("sources")
    sub.add_parser("history")
    task = sub.add_parser("task").add_subparsers(dest="operation", required=True)
    task.add_parser("list")
    add = task.add_parser("add")
    add.add_argument("--file", required=True)
    add.add_argument("--owner", required=True)
    nxt = task.add_parser("next")
    nxt.add_argument("--scope", choices=sorted(SCOPES), default="host")
    take = task.add_parser("claim-next")
    take.add_argument("--scope", choices=sorted(SCOPES), default="host")
    take.add_argument("--owner", required=True)
    take.add_argument("--branch")
    take.add_argument("--worktree")
    show = task.add_parser("show")
    show.add_argument("id")
    for name in ["claim", "release", "block", "resume", "done", "update", "heartbeat", "prioritize", "transfer", "narrow"]:
        q = task.add_parser(name)
        q.add_argument("id")
        q.add_argument("--owner", required=True)
        if name == "block":
            q.add_argument("--reason", required=True)
        if name == "done":
            q.add_argument("--evidence", required=True)
        if name in {"claim", "update"}:
            q.add_argument("--branch")
            q.add_argument("--worktree")
        if name == "update":
            q.add_argument("--note", required=True)
            q.add_argument("--next-step")
            q.add_argument("--handoff")
        if name == "prioritize":
            q.add_argument("--priority", type=int, required=True)
            q.add_argument("--reason", required=True)
        if name == "narrow":
            q.add_argument("--paths", nargs="+", required=True)
            q.add_argument("--reason", required=True)
        if name == "transfer":
            q.add_argument("--from-owner", required=True)
            q.add_argument("--reason", required=True)
            q.add_argument("--decision", required=True)
            q.add_argument("--handoff")
            q.add_argument("--branch")
            q.add_argument("--worktree")
    project = sub.add_parser("project").add_subparsers(dest="operation", required=True)
    permit = project.add_parser("permit")
    permit.add_argument("--scope", choices=sorted(SCOPES), required=True)
    permit.add_argument("--value", choices=["true", "false"], required=True)
    permit.add_argument("--decision", required=True)
    permit.add_argument("--owner", required=True)
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
        print("No phone commands executed. Consult dated device evidence for model/firmware; actual unlock, root access and recovery are not established by this tool.")
    elif args.command in {"status", "board"}:
        if args.write or getattr(args, "check", False):
            # Lock through the read and publication so another agent cannot publish a stale snapshot.
            with (root / "state/.lab.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                state = validate(root, read_json(root / "state/lab.json"))
                if args.write:
                    publish_views(root, state)
                else:
                    check_views(root)
            print("Updated STATUS.md, BOARD.md, task cards and state/board.json" if args.write else "OK: planning views match the current registry")
        else:
            with (root / "state/.lab.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_SH)
                state = validate(root, read_json(root / "state/lab.json"))
                if args.command == "status":
                    print(render(state), end="")
                else:
                    snapshot = board_snapshot(root, state)
                    print(json.dumps(snapshot, ensure_ascii=False, indent=2) if args.json else render_board(snapshot), end="\n" if args.json else "")
    elif args.command == "sources":
        for source in read_json(root / "research/sources.json")["sources"]:
            pin = source.get("revision") or "UNPINNED — inspect and pin before code reuse"
            print(f"{source['id']}: {source['url']} [{pin}]\n  {source['relevance']}")
    elif args.command == "history":
        for event in state["events"]:
            print(f"{event['at']} {event['owner']}: {event['action']}")
    elif args.command == "project":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,79}", args.owner):
            raise LabError("Use a stable owner identifier without whitespace (up to 80 characters)")
        decision = decision_record(root, args.decision)
        with transaction(root, f"project.permit:{args.scope}", args.owner) as state:
            value = args.value == "true"
            if state["project"]["permissions"][args.scope] is value:
                raise LabError("The permission already has this value; nothing changed")
            state["project"]["permissions"][args.scope] = value
            state["project"].setdefault("permission_decisions", []).append(
                {"scope": args.scope, "value": value, "decision": decision, "owner": args.owner, "at": now()})
        print(f"Permission {args.scope} = {args.value} per {decision}; this records an owner decision and grants nothing by itself")
    elif args.command == "task":
        if hasattr(args, "owner") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,79}", args.owner):
            raise LabError("Use a stable owner identifier without whitespace (up to 80 characters)")
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
            for task in ordered_tasks(state):
                column, reasons = readiness(state, task)
                if args.operation == "next" and not (column == "ready" and task["scope"] == args.scope):
                    continue
                print(f"{task['id']} [{column}] P{task.get('priority', 50)} owner={task.get('owner') or 'unassigned'} {task['title']} — {'; '.join(reasons) or column}")
        elif args.operation == "claim-next":
            with transaction(root, "task.claim-next", args.owner) as state:
                candidate = next((t for t in ordered_tasks(state) if t["scope"] == args.scope and readiness(state, t)[0] == "ready"), None)
                if candidate is None:
                    raise LabError("No eligible task in the requested scope; no claim changed")
                claim_task(state, candidate, args.owner, args.branch, args.worktree)
                identifier = candidate["id"]
            print(f"Claimed {identifier} for {args.owner}")
        else:
            with transaction(root, f"task.{args.operation}:{args.id}", args.owner) as state:
                task = item(state["tasks"], args.id)
                if args.operation == "claim":
                    claim_task(state, task, args.owner, args.branch, args.worktree)
                elif args.operation == "transfer":
                    decision = decision_record(root, args.decision)
                    owned(task, args.from_owner)
                    if task["status"] not in {"in_progress", "blocked"}:
                        raise LabError("Only active or blocked work can be transferred")
                    if args.owner == args.from_owner:
                        raise LabError("A transfer needs a different new owner")
                    if not args.reason.strip():
                        raise LabError("A transfer needs a concrete reason")
                    if args.handoff is not None:
                        if not within(root, args.handoff).exists():
                            raise LabError("The transfer handoff must be an existing project path")
                        task["handoff"] = args.handoff
                    for key in ["branch", "worktree"]:
                        if getattr(args, key) is not None:
                            task[key] = getattr(args, key)
                    task.setdefault("ownership_history", []).append(
                        {"from": args.from_owner, "to": args.owner, "reason": args.reason, "decision": decision, "at": now()})
                    task.update(owner=args.owner, updated_at=now(), last_heartbeat=now())
                elif args.operation == "prioritize":
                    if task["status"] != "pending":
                        raise LabError("Only pending work can be reprioritized")
                    if not args.reason.strip():
                        raise LabError("Priority changes need a reason")
                    task.update(priority=args.priority, priority_reason=args.reason, updated_at=now())
                elif args.operation == "narrow":
                    # Planner-only shrinking of an unclaimed task's reservation; never a widening.
                    if task["status"] != "pending" or task.get("owner"):
                        raise LabError("Only pending, unowned work can be narrowed")
                    if not args.reason.strip():
                        raise LabError("Narrowing needs a reason")
                    new = list(args.paths)
                    if len(set(new)) != len(new):
                        raise LabError("Narrowed paths must be distinct")
                    old_parts = [Path(p).parts for p in task["paths"]]
                    for name in new:
                        parts = Path(name).parts
                        if not parts or not any(parts[:len(b)] == b for b in old_parts):
                            raise LabError(f"Narrowing cannot widen the boundary: {name} is not inside {task['paths']}")
                    if sorted(new) == sorted(task["paths"]):
                        raise LabError("Narrowing must change the boundary")
                    task.setdefault("path_history", []).append(
                        {"from": list(task["paths"]), "to": new, "reason": args.reason, "owner": args.owner, "at": now()})
                    task.update(paths=new, updated_at=now())
                else:
                    owned(task, args.owner)
                    if task["status"] not in {"in_progress", "blocked"}:
                        raise LabError("Task must be in progress or blocked")
                    if args.operation == "release":
                        task.update(status="pending", owner=None, released_at=now(), updated_at=now())
                        task.pop("blocked_reason", None)
                        task.pop("last_heartbeat", None)
                    elif args.operation == "block":
                        if not args.reason.strip():
                            raise LabError("A blocked task requires a concrete reason")
                        task.update(status="blocked", blocked_reason=args.reason, updated_at=now(), last_heartbeat=now())
                    elif args.operation == "resume":
                        if task["status"] != "blocked":
                            raise LabError("Only blocked work can be resumed")
                        if prerequisites(state, task) or not permitted(state, task["scope"]) or path_conflicts(state, task):
                            raise LabError("Dependencies, scope or path reservations prevent resuming")
                        task.update(status="in_progress", updated_at=now(), last_heartbeat=now())
                        task.pop("blocked_reason", None)
                    elif args.operation in {"update", "heartbeat"}:
                        if args.operation == "update":
                            if not args.note.strip():
                                raise LabError("Progress notes must describe an actual observation")
                            task["progress_note"] = args.note
                            for key in ["next_step", "handoff", "branch", "worktree"]:
                                value = getattr(args, key)
                                if value is not None:
                                    task[key] = value
                        task.update(updated_at=now(), last_heartbeat=now())
                    elif args.operation == "done":
                        if not permitted(state, task["scope"]):
                            raise LabError("Execution scope is not authorized")
                        doc = evidence(root, args.evidence, task["evidence_kind"])
                        if doc["outcome"] != "pass":
                            raise LabError("A failing or inconclusive result cannot complete a task")
                        task.update(status="done", evidence=args.evidence, evidence_sha256=evidence_hash(root, args.evidence), finished_at=now(), updated_at=now())
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
