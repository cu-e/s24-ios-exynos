#!/usr/bin/env python3
"""Verify retained runtime-link evidence independently without another full link."""
from datetime import datetime, timezone
import argparse
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
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    worktree = Path(__file__).resolve().parents[3]
    if not worktree.is_relative_to(root / "worktrees") or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run):
        raise ValueError("Separate worktree and plain fresh output name required")
    out = worktree / "artifacts/kernel-runtime-link" / args.run
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out / "verifier.py")
    checks, parents = [], {}
    def read(path):
        return json.loads((root / path).read_text())
    def check(name, condition):
        checks.append(dict(name=name, pass_check=bool(condition)))
        if not condition:
            raise ValueError(name)
    try:
        ledger = read("state/lab.json")
        identifiers = ["KRUNLINK-001", "KPROV-003", "KPROV-004", "CCKEXT-015", "CCKEXT-017", "CCREV-002"]
        for identifier in identifiers:
            entry = next(e for e in ledger["experiments"] if e["id"] == identifier)
            path = root / entry["evidence"]
            check(identifier + "-capsule-identity", sha(path) == entry["evidence_sha256"])
            doc = json.loads(path.read_text())
            check(identifier + "-passing-measurement", doc["outcome"] == "pass")
            for name, digest in doc["sha256"].items():
                if sha(root / name) != digest:
                    raise ValueError("Changed retained artifact: " + name)
            parents[identifier] = dict(evidence=entry["evidence"], sha256=sha(path), artifacts_verified=len(doc["sha256"]))
        prefix = worktree.relative_to(root) / "artifacts/kernel-runtime-link/native-session1"
        report = read(prefix / "report.json")
        old = read("worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3/report.json")
        link = report["actual_link"]
        backend = read(prefix / "actual-backend.json")["argv"]
        resource = root / report["runtime"]["resource_dir"]
        runtime = root / report["runtime"]["archive"]
        check("exact-qualified-runtime-resource-and-archive", runtime == resource / "lib/darwin/libclang_rt.cc_kext_ios.a"
              and sha(runtime) == "67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5")
        check("all12-host-measurement-checks-pass", len(report["checks"]) == 12 and all(c["pass_check"] for c in report["checks"]))
        check("six-executed-input-controls", len(report["negative_controls"]) == 6 and all(c["rejected"] for c in report["negative_controls"]))
        check("one-actual-full-link-in-three-processes", len(report["commands"]) == 3
              and [c["exit_code"] for c in report["commands"]] == [0, 0, 1]
              and sum(Path(c["stdout"]).name == "actual-native-full-kernel-link.stdout.txt" for c in report["commands"]) == 1)
        frontend = link["frontend_argv"].copy()
        check("outer-native-reserved-option-retained", frontend.count("-lcc_kext") == 1 and "-Wl,-lcc_kext" not in frontend)
        index = frontend.index("-resource-dir")
        check("explicit-link-only-resource", frontend[index + 1] == str(resource))
        del frontend[index:index + 2]
        frontend[frontend.index("-o") + 1] = old["driver_expansion"]["compiler_argv"][old["driver_expansion"]["compiler_argv"].index("-o") + 1]
        frontend = ["--ld-path=" + old["driver_expansion"]["expanded_linker_argv"][0] if a.startswith("--ld-path=") else a for a in frontend]
        check("all-other-native-frontend-inputs-unchanged", frontend == old["driver_expansion"]["compiler_argv"])
        check("actual-journal-equals-expanded-and-recorded-backend", backend == link["observed_backend"] == link["expanded_backend"])
        check("native-absolute-runtime-once-no-literal-restoration", backend.count(str(runtime)) == 1 and "-lcc_kext" not in backend)
        normalized = backend.copy()
        normalized.remove(str(runtime))
        normalized[normalized.index("-o") + 1] = old["driver_expansion"]["expanded_linker_argv"][old["driver_expansion"]["expanded_linker_argv"].index("-o") + 1]
        check("all-other-native-backend-inputs-unchanged", normalized == old["driver_expansion"]["expanded_linker_argv"])
        check("no-forced-members-skipped-libraries-or-exports", "-all_load" not in backend and "-force_load" not in backend
              and backend.count("-lfirehose_kernel") == backend.count("-lpthread_kext") == 1
              and "-exported_symbols_list" in backend and "-alias_list" in backend)
        prior_exports = read("worktrees/krn-024-20261105/artifacts/kernel-provider-link/acceptance-session1/remaining-export-inputs.json")
        missing = re.findall(r'^  "([^"]+)", referenced from:', link["diagnostic"], re.M)
        check("same37-genuine-export-requirements-no-new-diagnosis", len(missing) == len(set(missing)) == 37
              and set(missing) == prior_exports.keys() and not report["new_diagnosed_names"])
        check("actual-link-failure-no-produced-image", link["exit_code"] == 1 and not link["image_exists"]
              and not (root / link["output"]).exists() and link["kernel_link_succeeded"] is False)
        check("resource-availability-not-all-member-runtime-closure", len(report["runtime_archive_inventory"]["external_imports"]) == 47
              and report["runtime_archive_inventory"]["selected_members_observed"] is None
              and report["runtime_archive_inventory"]["diagnosed_runtime_import_names"] == [])
        check("all-system-qualification-gates-remain-false", all(report[key] is False for key in ["full_kernel_qualified", "full_crypto_qualified",
              "apple_private_abi_qualified", "apple_interoperability_qualified", "full_runtime_behavior_qualified", "native_device_qualified", "device_executed", "sdk_used"]))
        check("bounded-single-owned-job-records", all(c["timeout_seconds"] <= 120 and c["stop_reason"] is None
              and c["peak_owned_group_plus_harness_rss_kib"] <= 1024 * 1024 and c["mem_available_kib"] >= 4 * 1024 * 1024 for c in report["commands"]))
        outcome, error = "pass", None
    except Exception as exc:
        outcome, error = "fail", str(exc)
    result = dict(kind="host-test", origin="local-host", outcome=outcome, recorded_at=datetime.now(timezone.utc).isoformat(),
        commit=locals().get("report", {}).get("commit"), summary="Independent retained-byte native compiler-runtime link assessment; no full kernel or runtime result",
        checks=checks, parents=parents, error=error, full_kernel_qualified=False, device_executed=False)
    (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    files = [p for p in out.iterdir() if p.is_file()]
    evidence = dict(kind="host-test", origin="local-host", outcome=outcome, recorded_at=result["recorded_at"], commit=result["commit"],
        summary=result["summary"], commands=[dict(argv=[sys.executable, *sys.argv], exit_code=0 if outcome == "pass" else 1)],
        artifacts=[str(p.relative_to(root)) for p in files], sha256={str(p.relative_to(root)): sha(p) for p in files})
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(dict(outcome=outcome, checks=len(checks), error=error, evidence=str((out / "evidence.json").relative_to(root)))))
    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
