#!/usr/bin/env python3
"""Read-only IOKit shard admission evidence; never executes compiler recipes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys

MANIFEST = "afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd"
SELECTORS = "855246471cd69fc7b0e482b5247b1e249adc1453018c922698435bbc88972853"
COMPILER = "7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect(main, manifest, selectors):
    require(digest(manifest) == MANIFEST, "Manifest pin mismatch")
    require(digest(selectors) == SELECTORS, "Selector pin mismatch")
    rows = json.loads(manifest.read_text())
    groups = json.loads(selectors.read_text())
    require(len(rows) == 1080, "Unexpected complete graph size")
    ids = [row["id"] for row in rows]
    require(len(set(ids)) == len(ids), "Duplicate manifest ID")
    all_selected = [identifier for group in groups["shards"].values() for identifier in group]
    require(len(all_selected) == len(set(all_selected)) == 1080, "Overlapping or incomplete shards")
    require(set(all_selected) == set(ids), "Selectors do not partition the exact graph")
    chosen = groups["shards"]["iokit"]
    require(len(chosen) == len(set(chosen)) == 104, "IOKit selector must contain exactly 104 IDs")
    index = {row["id"]: row for row in rows}
    source_records, missing_search_roots, compilers = [], set(), {}
    include_sets = set()
    configs = {}
    for identifier in chosen:
        row = index[identifier]
        require(row["component"] == "iokit" and identifier == "iokit/" + row["target"], "Foreign shard member")
        require(row["language"] in {"c", "c++"}, "Unexpected IOKit source language")
        require(row["execution_requires_new_plan_and_resource_lease"] is True, "Missing execution gate")
        source = Path(row["bound_source"])
        require(digest(source) == row["bound_source_sha256"], "Bound source changed: " + identifier)
        if not row["generated_input"]:
            require(row["source"] == str(source), "Non-generated source remapped")
            require(row["source_sha256"] == row["bound_source_sha256"], "Direct source pin differs")
        config = Path(row["configuration"])
        if str(config) not in configs:
            configs[str(config)] = digest(config)
        require(configs[str(config)] == row["configuration_sha256"], "Configuration changed")
        argv = row["next_owned_compile_argv_template"]
        tool = Path(argv[0])
        if str(tool) not in compilers:
            compilers[str(tool)] = digest(tool)
        require(compilers[str(tool)] == COMPILER, "Compiler changed")
        require(argv.count("-o") == argv.count("-MF") == 1, "Ambiguous output/dependency options")
        require(argv[argv.index("-o") + 1] == "@NEXT_OBJECT_DIR@/" + identifier, "Output escapes shard")
        require(argv[argv.index("-MF") + 1] == "@NEXT_DEPENDENCY_DIR@/" + identifier + ".d", "Dependency escapes shard")
        require(argv[-1] == str(source), "Template does not consume its bound source")
        require(argv[argv.index("-target") + 1] == "arm64-apple-ios16.5", "Foreign target")
        for flag in ("-DARM64_BOARD_CONFIG_BCM2837", "-DDEVELOPMENT", "-DXNU_NO_TYPE_BUILTINS=0", "-nostdinc", "-mkernel"):
            require(flag in argv and flag in shlex.split(row["genuine_expanded_recipe"]), "Required genuine flag missing: " + flag)
        roots = []
        for position, argument in enumerate(argv):
            if argument == "-I":
                roots.append(Path(argv[position + 1]))
            elif argument.startswith("-I"):
                roots.append(Path(row["cwd"]) / argument[2:])
        roots = [root.resolve() for root in roots]
        include_sets.add(tuple(map(str, roots)))
        for root in roots:
            if not root.is_dir():
                missing_search_roots.add(str(root))
        forced = [argv[position + 1] for position, argument in enumerate(argv) if argument == "-include"]
        forced_records = []
        for name in forced:
            matches = list(dict.fromkeys(root / name for root in roots if (root / name).is_file()))
            found = matches[0] if matches else None
            require(found is not None, "Forced include unresolved: " + name)
            forced_records.append({"name": name, "path": str(found), "sha256": digest(found),
                "shadowed_candidates": [{"path": str(path), "sha256": digest(path)} for path in matches[1:]]})
        direct = re.findall(r'^\s*#\s*include\s*([<"])([^>"\n]+)[>"]', source.read_text(), re.M)
        literal = []
        for delimiter, name in direct:
            search = ([source.parent] if delimiter == '"' else []) + roots
            matches = list(dict.fromkeys(root / name for root in search if (root / name).is_file()))
            found = matches[0] if matches else None
            literal.append({"name": name, "path": str(found) if found else None,
                            "sha256": digest(found) if found else None,
                            "shadowed_candidates": [{"path": str(path), "sha256": digest(path)} for path in matches[1:]]})
        source_records.append({"id": identifier, "row_sha256": canonical(row),
            "bound_source": str(source), "bound_source_sha256": row["bound_source_sha256"],
            "generated_input": row["generated_input"], "language": row["language"], "configuration": str(config),
            "configuration_sha256": configs[str(config)],
            "recipe_sha256": hashlib.sha256(row["genuine_expanded_recipe"].encode()).hexdigest(),
            "argv_template_sha256": canonical(argv), "forced_includes": forced_records,
            "literal_direct_includes": literal})
    return {"schema_version": 1, "task": "VM-013", "shard": "iokit", "mode": "source-only",
        "source_manifest": str(manifest), "source_manifest_sha256": MANIFEST,
        "selectors": str(selectors), "selectors_sha256": SELECTORS,
        "object_ids": chosen, "selected_count": len(chosen),
        "source_classes": dict(Counter("generated_iig" if row["generated_input"] else "source_" + row["language"] for row in source_records)),
        "configurations": configs, "compilers": compilers,
        "include_search_orders": [list(roots) for roots in sorted(include_sets)],
        "missing_search_roots": sorted(missing_search_roots), "objects": source_records,
        "limitations": ["No compiler or preprocessor executed; conditional and transitive dependency closure is unmeasured.",
            "Literal include observations are lexical and preserve unresolved conditional or platform includes.",
            "No object, link, private IIG ABI, guest console, PID1 or device qualification.",
            "Compilation requires accepted VM008 namespace, independently accepted VM009 runner and explicit root lease."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--selectors", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.manifest or args.main / "worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/next-full-object-manifest.json"
    selectors = args.selectors or args.main / "artifacts/team-coordination/20261106-team/object-shards.json"
    try:
        worktree = Path(__file__).resolve().parents[4]
        allowed = [worktree / "docs/procedures/avf-object-shards/iokit",
                   worktree / "fixtures/public/avf-object-shards/iokit"]
        require(any(args.out.resolve().is_relative_to(root) for root in allowed), "Output outside owned shard paths")
        require(not args.out.exists(), "Output already exists")
        report = inspect(args.main, manifest, selectors)
        with args.out.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        memory = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                  for line in Path("/proc/self/status").read_text().splitlines()
                  if line.startswith(("VmRSS:", "VmHWM:"))}
        print(json.dumps({"selected": report["selected_count"], "classes": report["source_classes"],
                          "output_sha256": digest(args.out), "current_image_memory": memory}))
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
