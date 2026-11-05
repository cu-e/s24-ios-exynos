#!/usr/bin/env python3
"""Verify the fixed platform-support source contract without executing recipes."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import resource
import sys
import time
from datetime import datetime, timezone


FLOOR = 4 * 1024**3
LIMIT = 256 * 1024**2
HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def status():
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmHWM:", "VmRSS:")):
            name, size, _ = line.split()
            fields[name[:-1] + "_bytes"] = int(size) * 1024
    return fields


def available():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable unavailable")


def option(argv, name):
    indexes = [i for i, item in enumerate(argv) if item == name]
    require(len(indexes) == 1 and indexes[0] + 1 < len(argv), "single " + name)
    return argv[indexes[0] + 1]


def roots(row):
    result = []
    argv = row["next_owned_compile_argv_template"]
    for i, item in enumerate(argv):
        if item == "-I":
            result.append(argv[i + 1])
        elif item.startswith("-I"):
            result.append(item[2:])
    return [str((Path(row["cwd"]) / p).resolve()) if not Path(p).is_absolute() else p for p in result]


def verify_rows(rows, selection, compiler):
    require([row["id"] for row in rows] == selection["object_ids"], "exact ordered shard IDs")
    require(len(rows) == len({row["id"] for row in rows}) == 13, "13 unique IDs")
    for row in rows:
        pin = selection["bindings"][row["id"]]
        argv = row["next_owned_compile_argv_template"]
        require(row["bound_source"] == pin["source"], "source path binding")
        require(row["bound_source_sha256"] == pin["source_sha256"], "source hash binding")
        require(row["source"] == row["bound_source"] and not row["generated_input"], "direct source identity")
        require(row["source_sha256"] == row["bound_source_sha256"], "original source hash")
        require(argv[0] == compiler["path"], "qualified compiler path")
        require(option(argv, "-target") == "arm64-apple-ios16.5", "iOS16.5 ARM64 target")
        require(option(argv, "-arch") == "arm64", "ARM64 architecture")
        for flag in ("-DARM64_BOARD_CONFIG_BCM2837", "-DDEVELOPMENT", "-DXNU_NO_TYPE_BUILTINS=0", "-nostdinc", "-c"):
            require(flag in argv, "required flag " + flag)
        require(not any(v.startswith("-DXNU_NO_TYPE_BUILTINS=") and v != "-DXNU_NO_TYPE_BUILTINS=0" for v in argv), "allocator builtins remain enabled")
        require(option(argv, "-o") == "@NEXT_OBJECT_DIR@/" + row["id"], "object output token")
        require(option(argv, "-MF") == "@NEXT_DEPENDENCY_DIR@/" + row["id"] + ".d", "dependency output token")
        require(row["bound_source"] in argv, "bound source operand")
        require(row["configuration"] == pin["configuration"], "component configuration path")
        require(row["configuration_sha256"] == pin["configuration_sha256"], "configuration hash binding")
        require(row["language"] == ("c++" if row["id"] == "libsa/bootstrap.cpo" else "c"), "source language")
        if row["language"] == "c++":
            require("-std=gnu++1z" in argv, "genuine C++ bootstrap language standard")
        require(canonical(row) == pin["row_sha256"], "frozen complete row")


def controls(rows, selection, compiler):
    result = []
    mutations = (
        ("duplicate-ID", lambda r: r.append(copy.deepcopy(r[0]))),
        ("foreign-shard-ID", lambda r: r[0].update(id="bsd/netboot.o")),
        ("changed-source-hash", lambda r: r[0].update(bound_source_sha256="0" * 64)),
        ("wrong-board", lambda r: r[0]["next_owned_compile_argv_template"].remove("-DARM64_BOARD_CONFIG_BCM2837")),
        ("disabled-builtins", lambda r: r[0]["next_owned_compile_argv_template"].append("-DXNU_NO_TYPE_BUILTINS=1")),
        ("foreign-output", lambda r: r[0]["next_owned_compile_argv_template"].__setitem__(r[0]["next_owned_compile_argv_template"].index("-o") + 1, "/tmp/foreign.o")),
    )
    for name, mutate in mutations:
        bad = copy.deepcopy(rows)
        mutate(bad)
        try:
            verify_rows(bad, selection, compiler)
        except (ValueError, KeyError) as exc:
            result.append({"control": name, "rejected": True, "reason": str(exc)})
        else:
            raise ValueError("mutation unexpectedly accepted: " + name)
    return result


def inventory(row):
    source = Path(row["bound_source"])
    search = [Path(p) for p in roots(row)]
    includes = []
    pattern = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]')
    for lineno, line in enumerate(source.read_text().splitlines(), 1):
        match = pattern.match(line)
        if not match:
            continue
        delimiter, name = match.groups()
        candidates = ([source.parent] if delimiter == '"' else []) + search
        resolved = next((p / name for p in candidates if (p / name).is_file()), None)
        includes.append({"line": lineno, "spelling": name, "first_existing_candidate": str(resolved) if resolved else None,
                         "sha256": digest(resolved) if resolved else None,
                         "preprocessor_condition_evaluated": False})
    forced = option(row["next_owned_compile_argv_template"], "-include")
    forced_path = next((p / forced for p in [Path(row["cwd"])] + search if (p / forced).is_file()), None)
    require(forced_path is not None, "forced meta_features.h exists")
    return {"id": row["id"], "include_roots_in_order": [str(p) for p in search],
            "absent_declared_roots": [str(p) for p in search if not p.is_dir()],
            "literal_direct_includes": includes,
            "forced_include": {"path": str(forced_path), "sha256": digest(forced_path)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    allowed = HERE.parents[3] / "docs/procedures/avf-object-shards/platform-support/runs"
    require(args.out.resolve().is_relative_to(allowed), "output must be a fresh owned procedure run")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "task": "VM-018", "started_at": datetime.now(timezone.utc).isoformat(),
              "argv": sys.argv, "outcome": "inconclusive", "initial_status": status(), "objects_produced": 0,
              "preprocessor_dependency_closure_verified": False, "compiler_or_guest_executed": False}
    start = time.monotonic()
    exit_code = 1
    try:
        samples = []
        report["memory_admission_bytes"] = samples
        for i in range(3):
            samples.append(available())
            require(samples[-1] >= FLOOR, "MemAvailable below 4GiB")
            if i != 2:
                time.sleep(1)
        selection = json.loads((HERE / "selection.json").read_text())
        report["selection_sha256"] = digest(HERE / "selection.json")
        report["implementation_sha256"] = digest(Path(__file__).resolve())
        allocation_path = args.main / selection["allocation"]
        manifest_path = args.main / selection["source_manifest"]
        prepared_path = args.main / selection["prepared_component"]
        for name, path in (("allocation", allocation_path), ("source_manifest", manifest_path), ("prepared_component", prepared_path)):
            require(digest(path) == selection[name + "_sha256"], name + " pin")
        allocation = json.loads(allocation_path.read_text())
        require(allocation["shards"]["platform-support"] == selection["object_ids"], "allocation exact selector")
        all_ids = [i for shard in allocation["shards"].values() for i in shard]
        require(len(all_ids) == len(set(all_ids)) == allocation["total"] == 1080, "disjoint complete allocation")
        manifest = json.loads(manifest_path.read_text())
        require(len(manifest) == len({r["id"] for r in manifest}) == 1080, "unique full manifest")
        by_id = {r["id"]: r for r in manifest}
        rows = [by_id[i] for i in selection["object_ids"]]
        prepared = json.loads(prepared_path.read_text())
        verify_rows(rows, selection, prepared["compiler"])
        report["controls"] = controls(rows, selection, prepared["compiler"])
        report["verified_files"] = []
        seen = {}
        for row in rows:
            for key, sha_key in (("bound_source", "bound_source_sha256"), ("configuration", "configuration_sha256")):
                require(digest(row[key]) == row[sha_key], "current file hash " + row[key])
                seen[row[key]] = row[sha_key]
            require(Path(row["cwd"]).is_dir(), "original recipe cwd exists")
        compiler = prepared["compiler"]
        require(digest(compiler["path"]) == compiler["sha256"], "current qualified compiler hash")
        seen[compiler["path"]] = compiler["sha256"]
        report["verified_files"] = [{"path": p, "sha256": h} for p, h in sorted(seen.items())]
        report["direct_include_inventory"] = [inventory(row) for row in rows]
        for row, entry in zip(rows, report["direct_include_inventory"]):
            expected = prepared["configurations"][row["component"]]["meta_features_sha256"]
            require(entry["forced_include"]["sha256"] == expected, "selected component meta_features.h hash")
        report["selected_row_hashes"] = {r["id"]: canonical(r) for r in rows}
        report["outcome"] = "pass"
        exit_code = 0
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        report["final_status"] = status()
        report["raw_ru_maxrss_bytes_historical_counter"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        if report["final_status"]["VmHWM_bytes"] > LIMIT:
            report["outcome"] = "inconclusive"
            report["error"] = "current executable image exceeded 256MiB VmHWM"
            exit_code = 1
        report["elapsed_seconds"] = time.monotonic() - start
        report["exit_code"] = exit_code
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "exit_code": exit_code, "report": str(args.out / "report.json")}))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
