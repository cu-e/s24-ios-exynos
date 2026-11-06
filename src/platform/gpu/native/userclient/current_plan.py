#!/usr/bin/env python3
"""GPU-012 source-only current-profile binding. No process execution interface."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

sys.dont_write_bytecode = True
POLICY_SHA = "5a62d789a61749139c6629846bf9c4c754efef442be3ac7a8514df794f0fac61"
HELPER_SHA = "af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0"
MANIFEST_SHA = "be02fbfc38a73831d3570e69b24277917e69efc09cd696cc853521c393edc298"
OWNER = "codex-gpu-userclient-20261106-eh"
SCOPES = {"src/platform/gpu/native/userclient", "fixtures/public/gpu-userclient", "docs/procedures/gpu-userclient"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot(path, expected, maximum=1024*1024):
    path = Path(path)
    if path != path.resolve() or any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Canonical non-symlink input required")
    with path.open("rb") as stream:
        raw = stream.read(maximum+1)
    if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Changed pinned input: " + str(path))
    return raw


def pin(path, expected=None):
    digest = sha(path)
    if expected is not None and digest != expected:
        raise ValueError("Changed source freeze: " + str(path))
    return {"path": str(path), "sha256": digest}


def validate_contract(value):
    if value != {"resource_profile": "project-budget-v1", "max_jobs_per_executor": 1,
                 "max_compiler_jobs_total": 6, "max_total_project_rss_bytes": 6*1024**3,
                 "light_rss_budget_bytes": 2*1024**3, "max_owned_rss_bytes": 256*1024**2}:
        raise ValueError("Exact serial project-budget contract required; stale two-job contract refused")


def derive(row, source, name, actual):
    original = row["next_owned_compile_argv_template"]
    if original.count(row["bound_source"]) != 1 or original.count("-o") != 1 or original.count("-MF") != 1:
        raise ValueError("Exactly one genuine source/object/dependency operand required")
    if original[original.index("-target")+1] != "arm64-apple-ios16.5" or "-DXNU_NO_TYPE_BUILTINS=0" not in original:
        raise ValueError("Genuine target/builtin contract changed")
    argv = list(original)
    changes = []
    for index, replacement, purpose in [(original.index(row["bound_source"]), str(source), "owned source"),
            (original.index("-o")+1, str(actual/(name+".o")), "owned object"),
            (original.index("-MF")+1, str(actual/(name+".d")), "owned dependencies")]:
        changes.append({"index": index, "before": original[index], "after": replacement, "purpose": purpose})
        argv[index] = replacement
    return {"id": name, "derived_from": row["id"], "source": pin(source), "cwd": row["cwd"],
            "argv": argv, "argv_sha256": canonical(argv), "genuine_template_sha256": canonical(original),
            "ordered_substitutions": changes, "object": str(actual/(name+".o")),
            "depfile": str(actual/(name+".d")), "timeout_seconds": 120}


def unchanged_flags(row, command):
    original = row["next_owned_compile_argv_template"]
    reconstructed = list(command["argv"])
    if len(reconstructed) != len(original) or len(command["ordered_substitutions"]) != 3:
        raise ValueError("Full genuine argv length/order changed")
    allowed = {original.index(row["bound_source"]), original.index("-o")+1, original.index("-MF")+1}
    for change in command["ordered_substitutions"]:
        i = change["index"]
        if i not in allowed or original[i] != change["before"] or reconstructed[i] != change["after"]:
            raise ValueError("Undeclared genuine argument substitution")
        reconstructed[i] = original[i]
    if reconstructed != original or command["cwd"] != row["cwd"]:
        raise ValueError("Full genuine flags/order/cwd changed")


def prepare(args, owned, report):
    policy_path = owned/"fixtures/public/gpu-userclient/current-policy.json"
    policy = json.loads(snapshot(policy_path, POLICY_SHA))
    report["policy"] = pin(policy_path, POLICY_SHA)
    contract = {"resource_profile": "project-budget-v1", "max_jobs_per_executor": 1,
                "max_compiler_jobs_total": 6, "max_total_project_rss_bytes": 6*1024**3,
                "light_rss_budget_bytes": 2*1024**3, "max_owned_rss_bytes": 256*1024**2}
    if args.control == "stale-budget": contract["max_jobs_per_executor"] = 2
    validate_contract(contract)
    report["resource_contract"] = contract
    helper_item = policy["pins"]["helper"]
    helper_sha = "0"*64 if args.control == "changed-helper" else HELPER_SHA
    raw = snapshot(helper_item["path"], helper_sha)
    helper = ModuleType("gpu_current_shared_policy")
    helper.__file__ = helper_item["path"]
    exec(compile(raw, helper.__file__, "exec"), helper.__dict__)
    report["shared_helper"] = helper_item
    for item in policy["pins"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("Changed accepted pin: " + item["path"])
    ledger = helper.load_project(args.main/"state/lab.json")
    task = next(t for t in ledger["tasks"] if t["id"] == "GPU-012")
    experiment = next(e for e in ledger["experiments"] if e["id"] == args.experiment)
    if task["owner"] != OWNER or task["status"] != "in_progress" or set(task["paths"]) != SCOPES:
        raise ValueError("Original owner/active task/literal paths required")
    if any(experiment[k] != v for k, v in [("owner", OWNER), ("task", "GPU-012"), ("status", "planned")]):
        raise ValueError("Original registered planned source experiment required")
    report["authority"] = {"task": task["id"], "owner": task["owner"], "literal_paths": task["paths"],
                           "experiment": args.experiment, "ledger_sha256_observed": sha(args.main/"state/lab.json")}
    pins = policy["pins"]
    binding = SimpleNamespace(main=args.main, manifest=Path(pins["manifest"]["path"]),
        manifest_sha256=MANIFEST_SHA, qualification_sha256=pins["qualification"]["sha256"],
        selectors=Path(pins["selectors"]["path"]), selectors_sha256=pins["selectors"]["sha256"])
    if args.control == "stale-profile": binding.manifest_sha256 = helper.PIN
    helper.accepted_profile(binding)
    rows = helper.load_project(binding.manifest, MANIFEST_SHA)
    helper.validate_graph(rows)  # Real accepted 1080 rows, never manufactured GPU rows.
    descriptor = helper.load_project(pins["qualification"]["path"], pins["qualification"]["sha256"])
    qualified, keys, receipt = helper.firehose_profile(binding, rows, descriptor)
    index = helper.normalized_index(helper.load_project(qualified["artifact_index"], qualified["artifact_index_sha256"])["files"], args.main)
    cache = helper.Digests()
    actual_namespace = helper.namespace(rows, index, cache)
    for name, expected in receipt["files"].items():
        if cache.get(name) != expected or index.get(name) != expected:
            raise ValueError("Changed complete accepted namespace member: " + name)
        actual_namespace["files"][name] = expected
    actual_namespace["sha256"] = helper.canonical({k: actual_namespace[k] for k in ["roots", "absent_search_roots", "files"]})
    if actual_namespace != receipt or receipt["sha256"] != policy["namespace_sha256"]:
        raise ValueError("Actual complete namespace differs from accepted current receipt")
    report["namespace"] = {"sha256": receipt["sha256"], "file_count": len(receipt["files"]),
                           "roots": receipt["roots"], "absent_search_roots": receipt["absent_search_roots"],
                           "receipt": pins["namespace"], "all_genuine_object_keys_validated": len(keys)}
    report["accepted_inputs"] = pins
    report["source_freeze"] = policy["source_freeze"]
    for name, expected in policy["source_freeze"]["files"].items():
        pin(owned/name, expected)
        pin(Path(policy["source_freeze"]["worktree"])/name, expected)
    gpu011 = helper.load_project(pins["gpu011"]["path"], pins["gpu011"]["sha256"])
    for name in ["src/platform/gpu/abi/sgpu_abi.c", "src/platform/gpu/abi/sgpu_abi.h"]:
        pin(owned/name, gpu011["sha256"][name])
    report["owned_source_namespace"] = [pin(p) for root in [owned/"src/platform/gpu/native/userclient", owned/"src/platform/gpu/abi"]
        for p in sorted(root.rglob("*")) if p.is_file()]
    cpp = next(row for row in rows if row["id"] == "iokit/IOUserClient.cpo")
    c = next(row for row in rows if row["id"] == "iokit/IOStringFuncs.o")
    if sum(row["component"] == "iokit" for row in rows) != 104:
        raise ValueError("Actual selected 104 IOKit context changed")
    report["genuine_recipes"] = [cpp, c]
    commands = [derive(row, owned/source, name, args.actual_output) for row, source, name in [
        (cpp, "src/platform/gpu/native/userclient/SGPUUserClient.cpp", "adapter"),
        (cpp, "src/platform/gpu/native/userclient/Policy.cpp", "policy"),
        (c, "src/platform/gpu/abi/sgpu_abi.c", "dispatcher")]]
    if args.control == "changed-flag": commands[0]["argv"].append("-std=gnu++20")
    for row, command in zip([cpp, cpp, c], commands): unchanged_flags(row, command)
    report["target_commands"] = commands
    report["future_actual_output"] = str(args.actual_output)
    report["current_shared_api"] = {"approval": "project_approval(args, approval, executor_path=exact_caller)",
        "reservation": "budget.reserve(); try: run_child(..., budget=budget); finally: release only after verified owned-session cleanup",
        "supervisor": pins["supervisor"], "shard": "gpu-userclient", "source_plan_sha256": "exact final plan file hash required",
        "root_allocation": "Absent for GPU; root alone creates immutable allocation and live MAIN resource-queue slot",
        "caller": "Future separately reviewed scoped executor, exact source hash must match approval and allocation",
        "admission": "3 samples >=4GiB MemAvailable, 1s apart, 45s window; serial compiler; 25ms RSS sampling; Landlock only own output",
        "cancellation": "Require exact reviewed root launcher/deadline and verified process/session cleanup; no unrelated signals"}
    flags = ["-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    cc, cxx = Path("/usr/bin/cc").resolve(), Path("/usr/bin/c++").resolve()
    report["prospective_host_tools"] = [pin(cc), pin(cxx)]
    host = args.actual_output/"host"
    report["prospective_host_commands"] = [
        {"argv": [str(cc), "-std=c11", *flags, "-c", str(owned/"src/platform/gpu/abi/sgpu_abi.c"), "-o", str(host/"dispatcher.o")]},
        {"argv": [str(cxx), "-std=c++17", *flags, str(owned/"src/platform/gpu/native/userclient/Policy.cpp"),
            str(owned/"fixtures/public/gpu-userclient/policy_controls.cpp"), str(host/"dispatcher.o"), "-o", str(host/"policy-controls")]},
        {"argv": [str(host/"policy-controls")]}]
    report["sanitizer_contract_gap"] = {"status": "future independently reviewed contract required",
        "current_helper_rlimit_as_bytes": 2*1024**3, "reason": "64-bit ASan shadow virtual address reservation conflicts with 2GiB RLIMIT_AS",
        "environment": "Current run_child has fixed environment and no environment argument; do not assume ASAN_OPTIONS/UBSAN_OPTIONS forwarding",
        "proposed_boundary": "RSS-only supervised sanitizer children, preserving finite deadline, verified cleanup, Landlock, global ProjectBudget and exact caller/argv/source-plan pins",
        "shared_change_gate": "VM044 ownership release, separate reviewed task and explicit root allocation before any shared API change; no implementation or bypass here"}
    report["pending_adoption"] = policy["pending_adoption"]
    report["final_binding_gate"] = "Explicitly repin final independently accepted helper/profile ONCE in a new source-plan freeze before execution; never silently upgrade or relabel old products"
    report["inspection_plan"] = {"tool": pin(owned/"src/platform/gpu/native/userclient/inspect_objects.py"),
        "checks": ["three actual ARM64 MH_OBJECT", "typed genuine overrides/provider symbols", "actual nonzero __kalloc metadata", "C _sgpu_dispatch", "all actual undefined XNU imports retained without stubs"],
        "future_argv": [sys.executable, "-s", str(owned/"src/platform/gpu/native/userclient/inspect_objects.py"), "--directory", str(args.actual_output), "--output", str(args.actual_output/"object-inspection.json")]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actual-output", type=Path, required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--control", choices=["stale-budget", "changed-helper", "stale-profile", "changed-flag"])
    args = parser.parse_args()
    owned = Path(__file__).resolve().parents[5]
    for name in ["main", "output", "actual_output"]:
        value = getattr(args, name).absolute()
        if value != value.resolve() or any(p.is_symlink() for p in [value, *value.parents]):
            parser.error("Canonical non-symlink paths required")
        setattr(args, name, value)
    if args.main != owned.parent.parent:
        parser.error("Use the sole MAIN above the original owned worktrees directory")
    scope = owned/"artifacts/gpu-userclient"
    if not all(p.is_relative_to(scope) and p != scope and not p.exists() for p in [args.output, args.actual_output]):
        parser.error("Fresh separate plan/actual directories within original GPU artifact scope required")
    if args.output == args.actual_output or args.output.is_relative_to(args.actual_output) or args.actual_output.is_relative_to(args.output):
        parser.error("Plan and actual output must be disjoint")
    args.output.mkdir(parents=True)
    started = time.monotonic()
    report = {"schema": "gpu-userclient-current-plan-v1", "resource_profile": "project-budget-v1", "task": "GPU-012", "owner": OWNER,
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "argv": [sys.executable, *sys.argv],
        "planner": pin(Path(__file__).resolve()), "control": args.control, "execution_authorized": False,
        "compiler_executed": False, "sanitizer_executed": False, "loader_tool_main_executed": False,
        "root_allocation_requested": False, "actual_output_created": False,
        "unmeasured_gates": ["typed ARM64 compile/override/symbol/allocator/import results", "host policy controls/ASan/UBSan", "IOConnect/task credentials at runtime", "actual Xclipse provider/memory/IRQ/cache/submit/completion/retirement/quiescence", "guest/native ABI/hardware"]}
    code = 0
    try:
        prepare(args, owned, report)
        if args.control: raise ValueError("Negative control unexpectedly passed")
        report["outcome"] = "source-plan-pass-execution-blocked"
    except (OSError, ValueError, KeyError, StopIteration) as error:
        report["outcome"] = "rejected" if args.control else "fail"
        report["error"] = str(error)
        code = 2 if args.control else 1
    report["exit_code"] = code
    report["elapsed_seconds"] = time.monotonic()-started
    report["proc_status"] = [line for line in Path("/proc/self/status").read_text().splitlines() if line.startswith(("VmRSS:", "VmHWM:"))]
    (args.output/"plan.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"outcome": report["outcome"], "exit_code": code, "error": report.get("error"), "plan": str(args.output/"plan.json")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
