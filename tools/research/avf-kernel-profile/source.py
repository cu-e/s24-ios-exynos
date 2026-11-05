#!/usr/bin/env python3
"""Read only explicit pinned public source blobs; never hydrate shared Git trees."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

GUARDS = {"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}
REPOS = {
    "scion-avf": ("a6f4bc38aa244359cd365c976244a88c9d6b3304", "Scion-Project/hackios-xnu-kernel"),
    "s24-port": ("c8860decc62c6d6180e609036d027a2997972420", "RNDMBG/iOS-On-S24"),
    "apple-xnu": ("c54f35ca767986246321eb901baf8f5ff7923f6a", "apple-oss-distributions/xnu"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, rows):
    result = subprocess.run(argv, capture_output=True, env=dict(os.environ) | GUARDS, timeout=20)
    rows.append({"argv": argv, "exit_code": result.returncode,
                 "stdout_sha256": digest(result.stdout), "stderr": result.stderr.decode(errors="replace"),
                 "environment_overrides": GUARDS})
    return result


def acquire(main, cache, requests, journal):
    result = {"recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "environment_overrides": GUARDS, "commands": [], "files": [], "errors": []}
    cache.mkdir(parents=True, exist_ok=True)
    def save():
        journal.write_text(json.dumps(result, indent=2) + "\n")
    for spec in requests:
        name, path = spec.split(":", 1)
        if name not in REPOS or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("Invalid named source input: " + spec)
        pin, upstream = REPOS[name]
        repo = main / "references" / name
        item = {"repo": name, "commit": pin, "path": path}
        result["files"].append(item)
        try:
            tree = run(["git", "-C", str(repo), "ls-tree", pin, "--", path], result["commands"])
            if tree.returncode or not tree.stdout:
                raise ValueError("Named source absent from pinned tree: " + spec)
            fields = tree.stdout.decode().split()
            if fields[1] != "blob":
                raise ValueError("Named input must be a file, not a directory: " + spec)
            item["blob_id"] = fields[2]
            target = cache / name / path
            if target.is_file():
                data = target.read_bytes()
                item["origin"] = "existing owned cache, reverified against pinned tree"
            else:
                shown = run(["git", "-C", str(repo), "show", pin + ":" + path], result["commands"])
                if shown.returncode == 0:
                    data = shown.stdout
                    item["origin"] = "guarded existing Git object"
                else:
                    url = "https://raw.githubusercontent.com/" + upstream + "/" + pin + "/" + path
                    item.update(origin="explicit pinned primary public text", url=url, attempts=[])
                    for attempt in range(2):
                        try:
                            with urllib.request.urlopen(url, timeout=20) as response:
                                data = response.read(8 * 1024 * 1024 + 1)
                            item["attempts"].append({"attempt": attempt + 1, "outcome": "received"})
                            break
                        except Exception as error:
                            item["attempts"].append({"attempt": attempt + 1, "outcome": "fail", "error": repr(error)})
                            save()
                    else:
                        raise RuntimeError("Bounded primary fetch failed: " + spec)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Source extent exceeds bounded text profile")
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            item.update(received_blob_id=blob, received_sha256=digest(data), received_size=len(data))
            if blob != item["blob_id"]:
                rejected = cache.parent / "rejected" / (name + "-" + digest(data))
                rejected.parent.mkdir(parents=True, exist_ok=True)
                rejected.write_bytes(data)
                item["rejected_bytes"] = str(rejected)
                raise ValueError("Source Git blob mismatch: " + spec)
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            item.update(sha256=digest(data), size=len(data), cache=str(target))
        except Exception as error:
            item["error"] = repr(error)
            result["errors"].append({"input": spec, "error": repr(error)})
        save()
    result["outcome"] = "fail" if result["errors"] else "pass"
    save()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    data = acquire(args.main.resolve(), args.cache, json.loads(args.requests.read_text()), args.journal)
    print(json.dumps({"outcome": data["outcome"], "files": len(data["files"]), "errors": data["errors"]}, indent=2))
    raise SystemExit(0 if data["outcome"] == "pass" else 2)
