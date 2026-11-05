#!/usr/bin/env python3
"""Independently verify retained provider-link bytes; execute no linker or device action."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

os.environ.update(GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0", PYTHONDONTWRITEBYTECODE="1")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    worktree = Path(__file__).resolve().parents[3]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run) or not worktree.is_relative_to(root / "worktrees"):
        raise ValueError("Separate worktree and plain fresh run name required")
    out = worktree / "artifacts/kernel-provider-link" / args.run
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out / "verifier.py")
    checks, parents, source_inputs = [], {}, {}
    def check(name, condition):
        checks.append(dict(name=name, pass_check=bool(condition)))
        if not condition:
            raise ValueError(name)
    def read(path):
        return json.loads((root / path).read_text())
    try:
        ledger = read("state/lab.json")
        for identifier in ["KPROV-001", "KPROV-002", "KPROV-003"]:
            entry = next(e for e in ledger["experiments"] if e["id"] == identifier)
            path = root / entry["evidence"]
            check(identifier + "-registered-capsule", sha(path) == entry["evidence_sha256"])
            evidence = json.loads(path.read_text())
            check(identifier + "-actual-outcome", evidence["outcome"] == ("fail" if identifier == "KPROV-001" else "pass"))
            for name, digest in evidence["sha256"].items():
                if sha(root / name) != digest:
                    raise ValueError("Changed retained artifact: " + name)
            parents[identifier] = dict(path=entry["evidence"], sha256=sha(path), artifacts_verified=len(evidence["sha256"]))
        prefix = worktree.relative_to(root) / "artifacts/kernel-provider-link"
        current = read(prefix / "native-session3/report.json")
        earlier = read(prefix / "native-session2/report.json")
        link = current["actual_link"]
        driver = current["driver_expansion"]
        check("all32-current-measurement-checks", len(current["checks"]) == 32 and all(c["pass_check"] for c in current["checks"]))
        check("real-intact-backend-library-order", [a for a in link["argv"] if a.startswith("-l")] == ["-lcc_kext", "-lfirehose_kernel", "-lpthread_kext"])
        removed = link["argv"].copy()
        removed.remove("-lcc_kext")
        check("only-restored-native-cc-library-differs", removed == driver["expanded_linker_argv"] and driver["source_justified_restored_native_arguments"] == ["-lcc_kext"])
        check("actual-missing-required-library-failure-no-image", link["exit_code"] == 1 and link["missing_cc_kext"]
              and not link["image_exists"] and not (root / link["output"]).exists())
        check("no-false-system-qualification", all(current[k] is False for k in ["full_kernel_qualified", "full_archive_link_qualified", "full_crypto_qualified", "apple_private_abi_qualified", "apple_interoperability_qualified", "runtime_qualified", "native_device_qualified", "device_executed", "sdk_used"]))
        check("six-real-wrong-input-rejections", len(current["negative_controls"]) == 6 and all(c["rejected"] for c in current["negative_controls"]))
        rows = read(prefix / "native-session3/current-compiled-objects.json")
        deps = read(prefix / "native-session3/current-dependency-files.json")
        check("all982-current-objects", len(rows) == 982 and len(current["staged_objects"]) == 982)
        for row in rows:
            for kind in ["source", "output"]:
                if sha(root / row[kind]) != row[kind + "_sha256"]:
                    raise ValueError("Changed original current source/object")
        for name, digest in deps.items():
            if sha(root / name) != digest:
                raise ValueError("Changed current dependency")
        check("all3156-current-dependencies", len(deps) == 3156)
        check("native-members-and-transforms", current["archive"]["expected_objects"] == 981 and len(current["HIB_processing"]) == 14 and len(current["KLD_processing"]) == 1)
        check("real-provider-closures", all(not p["missing_from_current_kernel_after_native_aliases"] and not p["overlap"] for p in current["providers"].values()))
        missing = re.findall(r'^  "([^"]+)", referenced from:', earlier["actual_link"]["diagnostic"], re.M)
        check("driver-omitted-attempt-has37-real-export-errors", len(missing) == len(set(missing)) == 37
              and earlier["actual_link"]["exit_code"] == 1 and not earlier["actual_link"]["image_exists"])
        base = Path("artifacts/xnu-prepare/e1s-dependency-source-session1/xnu")
        files = [base / "config/Private.arm64.exports", base / "config/Private.exports"]
        lines = {str(path): (root / path).read_text().splitlines() for path in files}
        for path in files:
            source_inputs[str(path)] = sha(root / path)
            check("selected-export-source-identity-" + path.name, current["source_inputs"][str(path)] == sha(root / path))
        providers = read(current["graph"]["symbol-providers"]["path"])
        supplied = set(providers) | {s for p in current["providers"].values() for s in p["definitions"]}
        mapping = {}
        for name in missing:
            hits = [dict(path=path, line=i + 1, sha256=source_inputs[path]) for path, text in lines.items()
                    for i, line in enumerate(text) if line.split(":", 1)[0].strip() == name]
            if len(hits) != 1 or current["driver_expansion"].get("actual_linker_argv") is None or name in supplied:
                raise ValueError("Export error does not match a unique absent selected provider: " + name)
            mapping[name] = hits[0]
        check("all37-selected-export-errors-have-exact-source-lines", len(mapping) == 37)
        check("actual-runtime-resource-absent", current["compiler_runtime_policy"]["runtime_exists"] is False
              and not Path(current["compiler_runtime_policy"]["expected_runtime"]).exists())
        check("commands-stayed-within-budget", all(c["timeout_seconds"] <= 120 and c["stop_reason"] is None
              and c["mem_available_kib"] >= 4 * 1024 * 1024 and c["peak_owned_group_plus_harness_rss_kib"] <= 1024 * 1024 for c in current["commands"]))
        check("recorded-process-peaks-below1GiB", current["max_child_rss_kib"] <= 1024 * 1024 and current["max_harness_rss_kib"] <= 1024 * 1024)
        (out / "remaining-export-inputs.json").write_text(json.dumps(mapping, indent=2) + "\n")
        outcome, error = "pass", None
    except Exception as exc:
        outcome, error = "fail", str(exc)
    report = dict(kind="host-test", origin="local-host", outcome=outcome, commit=locals().get("current", {}).get("commit"), recorded_at=datetime.now(timezone.utc).isoformat(),
                  summary="Independent retained-byte/provider/native-command acceptance; no full kernel or runtime qualification", checks=checks,
                  parents=parents, source_inputs=source_inputs, device_executed=False, full_kernel_qualified=False, error=error)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    artifacts = [p for p in out.iterdir() if p.is_file()]
    evidence = dict(kind="host-test", origin="local-host", outcome=outcome, recorded_at=report["recorded_at"], summary=report["summary"],
                    commit=report["commit"], commit_scope="Base of tested worktree; authored bytes captured by retained builder/verifier hashes",
                    commands=[dict(argv=[sys.executable, *sys.argv], exit_code=0 if outcome == "pass" else 1)],
                    artifacts=[str(p.relative_to(root)) for p in artifacts], sha256={str(p.relative_to(root)): sha(p) for p in artifacts})
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(dict(outcome=outcome, checks=len(checks), error=error, evidence=str((out / "evidence.json").relative_to(root)))))
    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
