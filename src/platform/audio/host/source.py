#!/usr/bin/env python3
"""Read exact public ABOX text blobs without hydrating shared references."""
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import urllib.request

COMMIT = "417484173abc2c4fa93e738ea82ad9f2e84911b1"
PRIMARY = "https://raw.githubusercontent.com/dx4m/android-kernel-samsung-e1s/"
GUARDS = {"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}
FILES = (
    "include/sound/samsung/abox_ipc.h", "include/sound/samsung/abox.h",
    "sound/soc/samsung/exynos/abox/abox.h", "sound/soc/samsung/exynos/abox/abox_dma.h",
    "sound/soc/samsung/exynos/abox/abox_dma.c", "sound/soc/samsung/exynos/abox/abox_rdma.c",
    "sound/soc/samsung/exynos/abox/abox_wdma.c", "sound/soc/samsung/exynos/abox/abox_ipc.c",
    "arch/arm64/boot/dts/exynos/s5e9945-audio.dtsi",
    "arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi",
    "arch/arm64/boot/dts/samsung/e1s/e1s_eur_openx_w01_r17.dts",
    "sound/soc/codecs/cs35l43.h", "sound/soc/codecs/cs35l43.c",
    "include/sound/pcm.h", "sound/core/pcm_misc.c", "include/linux/sizes.h",
)
MAX_TEXT_BYTES = 2 * 1024 * 1024


def fetch(repo, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ) | GUARDS
    journal = {"commit": COMMIT, "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "environment_overrides": GUARDS, "files": []}
    for file in FILES:
        argv = ["git", "-C", str(repo), "ls-tree", COMMIT, "--", file]
        tree = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=10)
        if tree.returncode or not tree.stdout:
            raise RuntimeError("Missing pinned public tree entry without lazy fetch: " + file)
        blob = tree.stdout.split()[2]
        target = cache / file
        url, failures = PRIMARY + COMMIT + "/" + file, []
        if target.is_file():
            if target.stat().st_size > MAX_TEXT_BYTES:
                raise ValueError("Task source text exceeds bounded cache size: " + file)
            data, origin = target.read_bytes(), "existing task-local exact-blob cache"
            read = None
        else:
            read_argv = ["git", "-C", str(repo), "show", COMMIT + ":" + file]
            read = subprocess.run(read_argv, capture_output=True, env=env, timeout=10)
            if read.returncode == 0:
                data, origin = read.stdout, "existing guarded shared object"
            else:
                origin = "explicit pinned primary public text fetch into own cache"
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(url, timeout=20) as response:
                            data = response.read(MAX_TEXT_BYTES + 1)
                        if len(data) > MAX_TEXT_BYTES:
                            raise ValueError("Pinned source response exceeds bounded text size")
                        break
                    except (OSError, http.client.IncompleteRead) as error:
                        failures.append(type(error).__name__ + ": " + str(error))
                        if attempt == 2:
                            raise
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != blob:
            raise ValueError("Primary text differs from full pinned Git blob: " + file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        journal["files"].append({"path": file, "blob_id": blob, "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data), "origin": origin, "primary_url": url, "retries": failures,
            "tree_command": {"argv": argv, "exit_code": tree.returncode},
            "object_read": None if read is None else {"argv": read.args, "exit_code": read.returncode,
                                                       "stderr": read.stderr.decode(errors="replace")}})
        (cache / "verified-sources.json").write_text(json.dumps(journal, indent=2) + "\n")
    return journal


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    args = p.parse_args()
    result = fetch(args.repo, args.cache)
    print(f"Verified {len(result['files'])} exact public source blobs at {COMMIT}")
