#!/usr/bin/env python3
"""Verify pinned research provenance, without opening a device or running upstream code."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


class AuditError(ValueError):
    pass


def git(repo, *args):
    # A read must not hydrate a shared promisor checkout or update its objects.
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", "-C", str(repo), *args], env=env,
                            capture_output=True, timeout=30)
    if result.returncode:
        raise AuditError("Git object unavailable; use a separately populated local reference")
    return result.stdout


def audit(manifest, repo, comparison):
    if manifest.get("schema_version") != 1 or manifest.get("native_qualified") is not False:
        raise AuditError("Source evidence cannot qualify native operation")
    src = manifest["source"]
    for revision in (src["revision"], src["comparison_revision"]):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise AuditError("Require full SHA-1 commit identity")
    for checkout, revision in ((repo, src["revision"]), (comparison, src["comparison_revision"])):
        resolved = git(checkout, "rev-parse", "--verify", revision + "^{commit}").decode().strip()
        if resolved != revision:
            raise AuditError("Revision must identify the commit itself")
    files = manifest["files"]
    if not 1 <= len(files) <= 100:
        raise AuditError("Invalid source file count")
    seen = set()
    anchors = 0
    report = []
    for item in files:
        path = item["path"]
        if (not isinstance(path, str) or PurePosixPath(path).is_absolute()
                or any(p in ("", ".", "..") for p in path.split("/")) or path in seen):
            raise AuditError("Invalid or duplicate source path")
        seen.add(path)
        data = git(repo, "cat-file", "blob", src["revision"] + ":" + path)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise AuditError("Source digest/size mismatch: " + path)
        lines = data.decode("utf-8").splitlines()
        if not item["anchors"]:
            raise AuditError("Each source needs an explicit reviewed anchor")
        for anchor in item["anchors"]:
            line = anchor["line"]
            if type(line) is not int or not 1 <= line <= len(lines) or anchor["text"] not in lines[line-1]:
                raise AuditError("Source anchor mismatch: " + path)
            anchors += 1
        prior = git(comparison, "cat-file", "blob", src["comparison_revision"] + ":" + path)
        if hashlib.sha256(prior).hexdigest() != item["comparison_sha256"]:
            raise AuditError("Comparison digest mismatch: " + path)
        status = "same" if data == prior else "different"
        if status != item["comparison_status"]:
            raise AuditError("Comparison classification mismatch: " + path)
        report.append({"path": path, "sha256": item["sha256"], "comparison": status})
    return {"outcome": "pass", "kind": "source-review", "native_qualified": False,
            "files_verified": len(files), "anchors_verified": anchors, "files": report}


def negative_controls(manifest, repo, comparison):
    def revision(m):
        m["source"]["revision"] = m["source"]["revision"][:12]
    def digest(m):
        m["files"][0]["sha256"] = "0" * 64
    def missing(m):
        m["files"][0]["path"] = "MISC-001-missing-object"
    def anchor(m):
        m["files"][0]["anchors"][0]["text"] = "MISC-001-absent-source-anchor"
    def native(m):
        m["native_qualified"] = True
    def compare(m):
        m["files"][0]["comparison_sha256"] = "0" * 64
    def traversal(m):
        m["files"][0]["path"] = "../outside"
    results = []
    for change in (revision, digest, missing, anchor, native, compare, traversal):
        altered = copy.deepcopy(manifest)
        change(altered)
        try:
            audit(altered, repo, comparison)
        except AuditError as error:
            results.append({"control": change.__name__, "rejected": True, "reason": str(error)})
        else:
            raise AuditError("Negative control accepted: " + change.__name__)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--comparison-repo", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("sources.json"))
    parser.add_argument("--negative-controls", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        result = audit(manifest, args.repo, args.comparison_repo)
        if args.negative_controls:
            result["negative_controls"] = negative_controls(manifest, args.repo, args.comparison_repo)
        print(json.dumps(result, indent=2))
    except (AuditError, KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"outcome": "fail", "kind": "source-review", "native_qualified": False,
                          "error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
