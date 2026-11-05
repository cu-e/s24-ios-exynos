#!/usr/bin/env python3
"""Bind final owner capsule and new coherent manifest to independently audited inputs."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = Path("/home/egor/dev/pet/s24-ios-exynos")
WT = ROOT / "worktrees/krn-031-20261105"
report = dict(kind="source-review", origin="local-host", outcome="fail", recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), task="REV-017", checks=[], inputs={}, commands=[])


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(name, condition):
    report["checks"].append(dict(name=name, passed=bool(condition)))
    if not condition:
        raise AssertionError(name)


def bind(path, digest=None):
    path = Path(path)
    value = sha(path)
    report["inputs"][str(path)] = value
    check("hash-" + str(path), digest is None or value == digest)
    return path


def git(*args):
    argv = ["git", "-C", str(ROOT), *args]
    result = subprocess.run(argv, env=dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0"), capture_output=True, timeout=15)
    report["commands"].append(dict(argv=argv, exit_code=result.returncode, stdout_sha256=hashlib.sha256(result.stdout).hexdigest(), stderr_sha256=hashlib.sha256(result.stderr).hexdigest(), environment_overrides={"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}))
    check("git-success", result.returncode == 0)
    return result.stdout


try:
    capsule_path = WT / "docs/procedures/kernel-xts/qualified-evidence.json"
    capsule = json.loads(bind(capsule_path, "b5f772163a286e2586d1a76f38640ca8e3b75d38a681d3b1b09198e91e6e2a47").read_text())
    check("capsule-final-pass", capsule["outcome"] == "pass" and capsule["commit"] == "9dc0c9f92c26373263ed17439eb44d0f2ea2268d")
    for name, digest in capsule["sha256"].items():
        bind(ROOT / name, digest)
    prior = json.loads(bind(BASE / "full-audit.json").read_text())
    check("independent-final-audit-pass", prior["outcome"] == "pass" and prior["final_acceptance"] and len(prior["checks"]) == 6198)
    bind(BASE / "final-auditor-snapshot.py", prior["auditor_sha256"])
    for row in capsule["reports"].values():
        check("same-independently-bound-report", prior["inputs"][str(ROOT / row["path"])] == row["sha256"])
    changed = git("diff", "--name-only", "9dc0c9f92c26373263ed17439eb44d0f2ea2268d", "a84ac4ec571fd36b1d435036d453fa68982d88b3").decode().splitlines()
    check("metadata-only-final-followup", changed == ["docs/procedures/kernel-xts/README.md", "docs/procedures/kernel-xts/handoff.md", "docs/procedures/kernel-xts/qualified-evidence.json", "fixtures/public/xnu-kernel-xts/inputs.json"])
    for name in changed:
        raw = git("show", "a84ac4ec571fd36b1d435036d453fa68982d88b3:" + name)
        bind(WT / name, hashlib.sha256(raw).hexdigest())
    native = json.loads((ROOT / capsule["reports"]["strict_native"]["path"]).read_text())
    original = json.loads((ROOT / native["original_graph"]["path"]).read_text())
    components = [r for r in native["components"] if not r["id"].startswith("fixture/")]
    expected = {r["id"]: r for r in original}
    expected.update({r["id"]: r for r in components})
    manifest_row = capsule["coherent_component_manifest"]
    manifest = json.loads(bind(ROOT / manifest_row["path"], manifest_row["sha256"]).read_text())
    actual = {r["id"]: r for r in manifest["objects"]}
    check("coherent985-exact-identities", len(manifest["objects"]) == len(actual) == len(expected) == manifest["coherent_object_count"] == 985 and set(actual) == set(expected))
    for name, row in actual.items():
        check("exact-source-object-identity-" + name, all(row[field] == expected[name][field] for field in ["source", "source_sha256", "output", "output_sha256"]))
        for field in ["source", "output"]:
            check("previously-independent-hash-" + name + field, prior["inputs"][str(ROOT / row[field])] == row[field + "_sha256"])
    check("coherent-manifest-scope", manifest["base_objects"] == 982 and manifest["replacements"] == 2 and manifest["additional_real_kernel_objects"] == 3 and manifest["original_dependency_count"] == 3156 and not manifest["full_kernel_link_performed"])
    check("coherent-manifest-preserves-gates", len(manifest["remaining_unsupported_crypto_fields"]) == 19 and manifest["remaining_private_ARM_exports"] == native["remaining_exports"]["entries"] and manifest["qualified_link_only_runtime"] == native["qualified_link_runtime"])
    cpu = capsule["caller_CPU"]
    check("combined-eight-exact-scope", cpu["positive_vectors"] == 1220 and cpu["positive_checks"] == 7350 and cpu["combined_case_count"] == 8 and len(cpu["cases"]) == 8 and all(c["accepted"] for c in cpu["cases"]) and cpu["genuine_selected_patched_caller_executed"] and cpu["genuine_registration_function_executed"] and not cpu["genuine_full_mc_provider_startup_executed"] and cpu["owned_partial_test_table"])
    notices = json.loads((WT / "fixtures/public/xnu-kernel-xts/inputs.json").read_text())
    for source in notices["sources"]:
        for name, digest in source["files"].items():
            raw = git("--git-dir=" + str(ROOT / source["repository_path"] / ".git"), "show", source["commit"] + ":" + name)
            check("primary-source-notice-" + name, hashlib.sha256(raw).hexdigest() == digest)
    bind(WT / notices["accepted_backend"]["provenance"], notices["accepted_backend"]["sha256"])
    report["outcome"] = "pass"
    report["summary"] = "Final owner capsule, metadata-only followup, primary notices and exact985-object manifest bind to independent6198-check review; bounded integration acceptance recommended"
except Exception as error:
    report["error"] = repr(error)
report["auditor_sha256"] = sha(__file__)
(BASE / "final-binding.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: report.get(k) for k in ["outcome", "error", "summary"]}, indent=2))
raise SystemExit(0 if report["outcome"] == "pass" else 1)
