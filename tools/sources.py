#!/usr/bin/env python3
"""Explicit pinned checkouts. Never runs upstream programs, submodules or phone tools."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


class SourceError(Exception):
    pass


def git(path, *args, timeout=180):
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(path), *args],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise SourceError(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def target(root, source):
    identifier = source["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifier):
        raise SourceError("Invalid source identifier")
    path = root / "references" / identifier
    if path.resolve() != root.resolve() / "references" / identifier:
        raise SourceError("Checkout must not escape through a symlink")
    if not re.fullmatch(r"[0-9a-f]{40}", source.get("revision") or ""):
        raise SourceError("Source requires a full commit SHA")
    url = source.get("git_url", source["url"])
    if not re.fullmatch(r"https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url):
        raise SourceError("Only explicit GitHub HTTPS repository URLs are supported")
    return path, url.removesuffix(".git")


def verify(root, source):
    path, url = target(root, source)
    if not (path / ".git").is_dir() or (path / ".git").is_symlink():
        raise SourceError("Missing ordinary local Git checkout; fetch it explicitly")
    if git(path, "remote", "get-url", "origin").removesuffix(".git") != url:
        raise SourceError("Checkout origin differs from the source registry")
    head = git(path, "rev-parse", "HEAD")
    if head != source["revision"]:
        raise SourceError("Checkout HEAD differs from the pinned revision")
    dirty = git(path, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise SourceError("Checkout contains local changes; preserve them before reuse")
    files = {}
    for name in source.get("review_files", []):
        relative = Path(name)
        file = path / relative
        if relative.is_absolute() or ".." in relative.parts or file.resolve() != path.resolve() / relative:
            raise SourceError("Review files must be canonical paths inside the checkout")
        if not file.is_file():
            raise SourceError(f"Missing reviewed file: {name}")
        files[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    return {"id": source["id"], "origin": url, "revision": head, "clean": True,
            "review_file_sha256": files, "submodules_fetched": False,
            "local_device_verified": False}


def fetch(root, source):
    path, url = target(root, source)
    if path.exists():
        return verify(root, source)
    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    git(path, "remote", "add", "origin", url)
    # Blob filtering and sparse paths avoid downloading unrelated binaries/toolchains.
    git(path, "config", "remote.origin.promisor", "true")
    git(path, "config", "remote.origin.partialclonefilter", "blob:none")
    git(path, "fetch", "--depth", "1", "--filter=blob:none", "origin", source["revision"])
    paths = source.get("review_files", [])
    if paths:
        for name in paths:
            if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", name) or ".." in Path(name).parts or name.startswith("/"):
                raise SourceError("Invalid sparse review path")
        git(path, "sparse-checkout", "init", "--no-cone")
        git(path, "sparse-checkout", "set", "--no-cone", *["/" + n for n in paths])
    git(path, "checkout", "--detach", source["revision"])
    return verify(root, source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("operation", choices=["verify", "fetch"])
    parser.add_argument("ids", nargs="+")
    args = parser.parse_args()
    root = args.root.resolve()
    entries = json.loads((root / "research/sources.json").read_text())["sources"]
    results = []
    for identifier in args.ids:
        source = next((s for s in entries if s["id"] == identifier), None)
        if source is None:
            raise SourceError(f"Unknown source: {identifier}")
        result = (fetch if args.operation == "fetch" else verify)(root, source)
        results.append(result)
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SourceError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"sources: {exc}", file=sys.stderr)
        sys.exit(2)
