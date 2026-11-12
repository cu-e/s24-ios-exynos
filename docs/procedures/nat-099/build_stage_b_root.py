#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-099: build the Stage B small root on the host (nothing here ran on a phone).

Stage B small root = NAT-096's Stage A small root (18 Apple LaunchDaemons plists without lsd + the ps heartbeat, 25 files) plus EXACTLY three files:

  LaunchDaemons/com.apple.backboardd.plist   what the donor's userland/mkjobs.py writes for that label: Apple's plist with one key added, StandardErrorPath=/dev/console
  lib/libhakios.dylib                        the donor's tracked prebuilt (IOS-014; pinned SHA-256; a donor-built binary, not a build of anything here)
  etc/inject.conf                            one line "LIBRARY NAME NAME ...": the donor's init reads it and hands it to sysctl kern.exec_inject, so that the kernel starts the programs
                                             with those names with the library inserted (userland/src/init.c configure_inject; the same list as the donor's build.sh INJECT for the first line)

  build_stage_b_root.py --out DIR [--base artifacts/nat-096/pid1-sq] [--recipe artifacts/ios-root/recipe] [--dylib references/hakios/prebuilt/userland/libhakios.dylib]

Why a separate script and not a new option of tools/ios/build_pid1_chain.py: the chain tool builds the programs and the job set and its tests stay as they were; this script starts from the finished Stage A
tree, whose root.apfs hash it pins, and changes nothing else. The image is written by the donor's mkapfs.py with the arguments the chain tool uses, then checked twice: the donor's verify.py content
comparison and the kernel's own apfs_lib (apfs-tool census/cat) reading every file back with its mode.

It refuses: a base whose root.apfs is not the pinned one, a dylib that is not the pinned prebuilt, a backboardd plist (as mkjobs.py wrote it) that is not Apple's plist plus the single StandardErrorPath key, an
output directory that exists, and a result whose tree differs from the base's in any path but the three. Output: DIR/root/ (the tree), DIR/root.apfs, DIR/build.json.

What this does not show: that the donor's init reaches configure_inject in this project's chain and the kernel accepts the list, that dyld inserts the library, that backboardd starts, or that anything is drawn."""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

BASE_ROOT_APFS_SHA256 = "62801cecc5cdf1e2bfaff8c056bd02e2539295e516fe2011b82fa3d2a5a37057"   # NAT-096's small root (md0) of loader-diag-xnu-sq-md1
BASE_FILE_COUNT = 25
DYLIB_SHA256 = "530c2e681093ece2afe7f5180a4723bd46d92f7af39edc0a8c77136136a4dad6"             # donor prebuilt/userland/libhakios.dylib at 87bf485 (IOS-014)
APPLE_BACKBOARDD_PLIST_SHA256 = "d5f1e51f1a1354265ddc081681fb3a919157d9f8a1ddb20bc079b76fc74aa6c0"   # the 20F66 root's com.apple.backboardd.plist as unpacked by the donor recipe
MKJOBS_BACKBOARDD_PLIST_SHA256 = "e708b86f31e09ecf4bb5d88f9d71d3b1bab4ca023ad5ceefb191d4e674bc647d"  # what mkjobs.py writes for it
INJECT_CONF = b"/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system\n"
ADDED = ("LaunchDaemons/com.apple.backboardd.plist", "lib/libhakios.dylib", "etc/inject.conf")
LABEL = "com.apple.backboardd"


class BuildError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise BuildError(msg)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree(root):
    """{relative path: ("file", mode & 0o7777, sha256) | ("symlink", target) | ("dir",)} for everything under root."""
    root = Path(root)
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode):
            out[rel] = ("symlink", os.readlink(p))
        elif stat.S_ISDIR(st.st_mode):
            out[rel] = ("dir",)
        elif stat.S_ISREG(st.st_mode):
            out[rel] = ("file", st.st_mode & 0o7777, sha256_file(p))
        else:
            raise BuildError("%s is neither a file, a directory nor a symlink" % rel)
    return out


def tree_diff(before, after):
    """-> (added, removed, changed): sorted lists of paths."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    return added, removed, changed


def check_backboardd_plist(apple_bytes, made_bytes):
    """The mkjobs.py result must be Apple's plist with exactly one key added: StandardErrorPath=/dev/console."""
    need(sha256_bytes(apple_bytes) == APPLE_BACKBOARDD_PLIST_SHA256, "Apple's backboardd plist is sha256 %s, not the pinned %s" % (sha256_bytes(apple_bytes), APPLE_BACKBOARDD_PLIST_SHA256))
    a, b = plistlib.loads(apple_bytes), plistlib.loads(made_bytes)
    need(b.get("StandardErrorPath") == "/dev/console", "the plist mkjobs.py wrote has StandardErrorPath %r, not /dev/console" % (b.get("StandardErrorPath"),))
    rest = {k: v for k, v in b.items() if k != "StandardErrorPath"}
    need("StandardErrorPath" not in a, "Apple's plist already has a StandardErrorPath")
    need(rest == a, "the plist mkjobs.py wrote differs from Apple's in more than the StandardErrorPath key: %s" % sorted(k for k in set(a) | set(rest) if a.get(k) != rest.get(k)))
    need(sha256_bytes(made_bytes) == MKJOBS_BACKBOARDD_PLIST_SHA256, "the plist mkjobs.py wrote is sha256 %s, not the pinned %s" % (sha256_bytes(made_bytes), MKJOBS_BACKBOARDD_PLIST_SHA256))


def run(argv, **kw):
    return subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=900, **kw)


def build(out, base, recipe, dylib):
    out, base, recipe, dylib = Path(out), Path(base), Path(recipe), Path(dylib)
    need(not out.exists(), "%s exists; the output directory must be new" % out)
    base_img, base_root = base / "root.apfs", base / "root"
    need(base_img.is_file() and base_root.is_dir(), "%s has no root.apfs and root/" % base)
    need(sha256_file(base_img) == BASE_ROOT_APFS_SHA256, "the base root.apfs is sha256 %s, not the pinned %s" % (sha256_file(base_img), BASE_ROOT_APFS_SHA256))
    before = tree(base_root)
    need(sum(1 for v in before.values() if v[0] == "file") == BASE_FILE_COUNT, "the base tree holds %d files, not %d" % (sum(1 for v in before.values() if v[0] == "file"), BASE_FILE_COUNT))
    need(not any(p in before for p in ADDED), "the base tree already holds one of %s" % (ADDED,))
    need(dylib.is_file() and sha256_file(dylib) == DYLIB_SHA256, "%s is not the pinned donor prebuilt (sha256 %s)" % (dylib, DYLIB_SHA256))
    mkjobs, rootfs, mkapfs, verify = recipe / "userland/mkjobs.py", recipe / "sysimage/rootfs", recipe / "tools/apfs/mkapfs.py", recipe / "tools/apfs/verify.py"
    for f in (mkjobs, mkapfs, verify):
        need(f.is_file(), "%s is missing" % f)
    apple_plist = rootfs / "System/Library/LaunchDaemons" / (LABEL + ".plist")
    need(apple_plist.is_file(), "%s is missing" % apple_plist)
    out.mkdir(parents=True)
    root = out / "root"
    shutil.copytree(base_root, root, symlinks=True)
    with tempfile.TemporaryDirectory(prefix="nat099-") as tmp:
        r = run([sys.executable, "-I", mkjobs, rootfs, tmp, LABEL])
        need(r.returncode == 0, "mkjobs.py failed: " + r.stderr[-600:])
        made = (Path(tmp) / (LABEL + ".plist")).read_bytes()
        need(sorted(os.listdir(tmp)) == [LABEL + ".plist"], "mkjobs.py wrote %s, not just the one plist" % sorted(os.listdir(tmp)))
    check_backboardd_plist(apple_plist.read_bytes(), made)
    (root / ADDED[0]).write_bytes(made)
    (root / "lib").mkdir()
    shutil.copy2(dylib, root / ADDED[1])
    (root / ADDED[2]).write_bytes(INJECT_CONF)
    after = tree(root)
    added, removed, changed = tree_diff(before, after)
    need(added == sorted(list(ADDED) + ["lib"]) and not removed and not changed, "the tree differs from the base in %s added, %s removed, %s changed" % (added, removed, changed))
    need(after["lib/libhakios.dylib"][1] == 0o755, "lib/libhakios.dylib has mode %o, not 755" % after["lib/libhakios.dylib"][1])
    img = out / "root.apfs"
    r = run([sys.executable, "-I", mkapfs, "-z", "--plain", "fw", "-o", img, "redwood=" + str(root)])
    need(r.returncode == 0, "mkapfs.py failed: " + r.stderr[-600:])
    mk_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    r2 = run([sys.executable, "-I", verify, "content", img, root, "--all"])
    need(r2.returncode == 0, "verify.py content failed: " + (r2.stdout + r2.stderr)[-600:])
    tool = recipe / "apfs-work/apfs-tool"
    need(tool.is_file(), "%s is missing (the donor's build-tool.sh builds it)" % tool)
    kernel = {"entries": 0, "files_compared": 0, "mismatches": []}
    for line in run([tool, "census", img]).stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 7 or not parts[0].startswith("/"):
            continue
        kernel["entries"] += 1
        path, kind, mode = parts[0], parts[1], parts[2]
        local = root / path.lstrip("/")
        if kind == "8":
            got = subprocess.run([str(tool), "cat", str(img), path], capture_output=True, timeout=60).stdout
            kernel["files_compared"] += 1
            if got != local.read_bytes():
                kernel["mismatches"].append(path)
            if int(mode, 8) & 0o7777 != local.stat().st_mode & 0o7777:
                kernel["mismatches"].append(path + " (mode)")
    files = sum(1 for v in after.values() if v[0] == "file")
    kernel["local_files"] = files
    need(not kernel["mismatches"] and kernel["files_compared"] == files, "the kernel's apfs_lib readback does not equal the tree: %s" % kernel)
    rec = {
        "kind": "host build record, nothing ran on a phone",
        "base": {"root_apfs_sha256": BASE_ROOT_APFS_SHA256, "files": BASE_FILE_COUNT},
        "added": {p: {"sha256": after[p][2], "mode": "%o" % after[p][1], "bytes": (root / p).stat().st_size} for p in ADDED},
        "inject_conf": INJECT_CONF.decode(),
        "apple_backboardd_plist_sha256": APPLE_BACKBOARDD_PLIST_SHA256,
        "mkjobs_backboardd_plist_sha256": MKJOBS_BACKBOARDD_PLIST_SHA256,
        "dylib_sha256": DYLIB_SHA256,
        "root_apfs": {"bytes": img.stat().st_size, "sha256": sha256_file(img), "mkapfs_last_line": mk_line},
        "verify_content": {"exit": r2.returncode, "tail": (r2.stdout + r2.stderr).strip()[-300:]},
        "kernel_apfs_lib_readback": kernel,
        "files": files,
        "script_sha256": sha256_file(Path(__file__)),
    }
    (out / "build.json").write_text((json.dumps(rec, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", ""))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--base", type=Path, default=ROOT / "artifacts/nat-096/pid1-sq")
    ap.add_argument("--recipe", type=Path, default=ROOT / "artifacts/ios-root/recipe")
    ap.add_argument("--dylib", type=Path, default=ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.base, a.recipe, a.dylib)
    except BuildError as e:
        raise SystemExit("build_stage_b_root: " + str(e))
    print(json.dumps({"root_apfs": rec["root_apfs"], "files": rec["files"], "kernel_readback_ok": not rec["kernel_apfs_lib_readback"]["mismatches"]}, indent=1))


if __name__ == "__main__":
    main()
