#!/usr/bin/env python3
"""Validate hardware evidence and render a capability view independently of task counts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import lab


def validate(root, data, ledger=None, sources=None):
    ledger = ledger or lab.validate(root, lab.read_json(root / "state/lab.json"))
    sources = sources or lab.read_json(root / "research/sources.json")
    if data.get("schema_version") != 1 or data.get("target") != "SM-S921B/e1s/s5e9945":
        raise lab.LabError("Unsupported capability schema or target")
    ids = set()
    task_ids = {t["id"] for t in ledger["tasks"]}
    source_ids = {s["id"] for s in sources["sources"]}
    if not data.get("capabilities"):
        raise lab.LabError("Capability matrix must not be empty")
    for cap in data["capabilities"]:
        if cap["id"] in ids:
            raise lab.LabError("Duplicate capability")
        ids.add(cap["id"])
        if not cap.get("acceptance") or not cap.get("next_check"):
            raise lab.LabError("Each capability needs acceptance and a next check")
        if set(cap["tasks"]) - task_ids or set(cap["sources"]) - source_ids:
            raise lab.LabError("Capability references unknown tasks or sources")
        if cap["implementation"] not in {"missing", "planned", "source-reviewed", "host-tested", "android-tested", "native-tested"}:
            raise lab.LabError("Invalid implementation status")
        if cap["native_status"] not in {"not-tested", "partial", "verified"}:
            raise lab.LabError("Invalid native status")
        if cap["native_status"] != "not-tested" or cap["implementation"] == "native-tested":
            if not cap.get("native_evidence"):
                raise lab.LabError("Native claims require native evidence")
            for ref in cap["native_evidence"]:
                doc = lab.evidence(root, ref["path"], "native-device")
                if doc["outcome"] != "pass" or lab.evidence_hash(root, ref["path"]) != ref["sha256"]:
                    raise lab.LabError("Native evidence must pass and retain its digest")
        for ref in cap.get("local_evidence", []):
            doc = lab.evidence(root, ref["path"])
            if doc["origin"] != "local-device" or doc["outcome"] != "pass":
                raise lab.LabError("Local hardware observations require passing local-device evidence")
            if lab.evidence_hash(root, ref["path"]) != ref["sha256"]:
                raise lab.LabError("Local evidence changed")
        if cap["implementation"] in {"host-tested", "android-tested"}:
            expected = "host-test" if cap["implementation"] == "host-tested" else "android-userland"
            if not cap.get("implementation_evidence"):
                raise lab.LabError("Tested implementation needs evidence, independent of inventory")
            for ref in cap["implementation_evidence"]:
                doc = lab.evidence(root, ref["path"], expected)
                if doc["outcome"] != "pass" or lab.evidence_hash(root, ref["path"]) != ref["sha256"]:
                    raise lab.LabError("Implementation evidence failed or changed")
    return data


def render(root, data, ledger):
    lines = ["# S24 hardware capabilities", "", "> Generated from state/capabilities.json. Task completion counts are not hardware coverage.", "",
             "Target: **" + data["target"] + "**. First OS target: **iOS 16.5**.", "",
             "Inventory describes running Android. Upstream claims and authored code are separate from this phone's native acceptance.", "",
             "| Capability | Local implementation | Native on this S24 | Local Android observation | Upstream / next check | Tasks |",
             "|---|---|---|---|---|---|"]
    for cap in data["capabilities"]:
        tasks = ", ".join(f"[{t}](planning/tasks/{t}.md)" for t in cap["tasks"])
        values = [cap["title"], cap["implementation"], cap["native_status"], cap["local_observation"], cap["upstream"] + " / " + cap["next_check"], tasks]
        lines.append("| " + " | ".join(lab.md(x) if i != 5 else x for i, x in enumerate(values)) + " |")
    lines += ["", "## Native acceptance", ""]
    for cap in data["capabilities"]:
        lines.append(f"- **{cap['title']}:** {cap['acceptance']}")
    lines += ["", "Apple services and iPhone-equivalent hardware security are separate research outcomes, with no promised compatibility.", "",
              "[Implementation sequence](docs/implementation.md) · [Kanban](BOARD.md)", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    root = args.root.resolve()
    ledger = lab.read_json(root / "state/lab.json")
    data = validate(root, lab.read_json(root / "state/capabilities.json"), ledger)
    output = render(root, data, ledger)
    if args.check:
        if not (root / "CAPABILITIES.md").is_file() or (root / "CAPABILITIES.md").read_text() != output:
            raise lab.LabError("Capability view is stale; run tools/capabilities.py --write")
        print("OK: capability references, evidence and generated view")
    elif args.write:
        lab.atomic_text(root / "CAPABILITIES.md", output)
        print("Wrote CAPABILITIES.md")
    else:
        print(json.dumps(data, indent=2) if args.json else output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (lab.LabError, OSError, ValueError, KeyError) as exc:
        print(f"capabilities: {exc}", file=sys.stderr)
        sys.exit(2)
