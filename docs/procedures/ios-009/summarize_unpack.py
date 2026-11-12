#!/usr/bin/env python3
"""Summarise a donor sysimage/unpack.sh result without copying any Apple file.

Reads the unpack directory (default artifacts/ios-root/recipe/sysimage) and prints JSON: counts, sizes, the
SHA-256 of the donor's listing files (system.files, system.manifest, var.skel) and of four key programs, and the
absence of unfinished LZBITMAP leftovers.  Hashes identify the extracted bytes; they do not publish them.

usage: python3 -I docs/procedures/ios-009/summarize_unpack.py [UNPACK_DIR]
"""
import hashlib
import json
import os
import sys
from pathlib import Path

KEY = {
    "launchd": "rootfs/sbin/launchd",
    "dyld": "rootfs/usr/lib/dyld",
    "backboardd": "rootfs/usr/libexec/backboardd",
    "SpringBoard": "rootfs/System/Library/CoreServices/SpringBoard.app/SpringBoard",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree(path):
    files = size = links = leftovers = 0
    for dirpath, _dirs, names in os.walk(path):
        for n in names:
            p = os.path.join(dirpath, n)
            if ":com.apple." in n:
                leftovers += 1
            if os.path.islink(p):
                links += 1
                continue
            files += 1
            size += os.path.getsize(p)
    return {"files": files, "symlinks": links, "bytes": size, "lzbitmap_leftovers": leftovers}


def main(argv):
    base = Path(argv[1] if len(argv) > 1 else "artifacts/ios-root/recipe/sysimage")
    out = {"unpack_dir": str(base)}
    for name in ("rootfs", "cryptex", "cryptex-app", "20F66__iPhone10,3_6"):
        out[name] = tree(base / name)
    out["dyld_shared_cache_files"] = sorted(os.listdir(base / "20F66__iPhone10,3_6"))[:3] + ["..."]
    out["dyld_shared_cache_count"] = len(os.listdir(base / "20F66__iPhone10,3_6"))
    out["listing_sha256"] = {n: sha256(base / n) for n in ("system.files", "system.manifest", "var.skel")}
    out["manifest_lines"] = sum(1 for _ in open(base / "system.manifest", "rb"))
    out["system_files_lines"] = sum(1 for _ in open(base / "system.files", "rb"))
    out["key_programs"] = {k: {"path": v, "bytes": os.path.getsize(base / v), "sha256": sha256(base / v)}
                           for k, v in KEY.items()}
    out["device_tree_im4p_bytes"] = os.path.getsize(base / "DeviceTree.d22ap.im4p")
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
