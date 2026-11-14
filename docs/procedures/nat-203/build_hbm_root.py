#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-203 host build: the md0 root of NAT-110 (`pid1-sc2-hb`) with the donor's mediaserverd library, `artifacts/nat-203/pid1-sc2-hbm`.

NAT-202 recorded mediaserverd's fault (46 times, one site): a call through address 0 from CoreImage's OpenGL ES path
(glDisable(GL_DEPTH_TEST) through an empty dispatch table), under CMCapture's +[BWCoreImageFilterRenderer context:err:]. The
donor (references/hakios 87bf485, userland/src/inject_media.c) names the cause: the capture stack "prewarms" the portrait-mode
Core Image filters at start, Core Image wants an OpenGL ES context, there is no GPU, and the daemon jumps to address 0 every time
launchd restarts it. Its fix is its library libhakios.media.dylib, inserted into mediaserverd by the kernel's kern.exec_inject list:
+[BWCoreImageFilterRenderer prewarmPortraitFilterVersion:semanticStyleFilters:] becomes an empty method (only when the method is at
its 20F66 address; otherwise the library says "left alone"). Its other replacements act only with /dev/hakios-torch or
/dev/hakios-camera, which this kernel does not make, or inside a capture graph, which nothing starts here.

Two changes against NAT-110's tree, nothing else:
  1. lib/libhakios.media.dylib: the donor's prebuilt at the pinned SHA (mode 0755), the same way NAT-108 added libhakios.sb.dylib;
  2. etc/inject.conf: a third line `/redwood/lib/libhakios.media.dylib mediaserverd` (the donor's default INJECT has it).
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]

BASE_APFS_SHA256 = "6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c"   # NAT-110 pid1-sc2-hb/root.apfs
DONOR = ROOT / "references/hakios"
DONOR_SHA = "87bf4851bcc9cbb24fd79997820aa3661abe4ea5"
DONOR_PATH = "prebuilt/userland/libhakios.media.dylib"
MEDIA_SHA256 = "d8680034e5f0cdecd396cd7488e9d0f30037223ebc57f5309f99a6cd45a4ad26"
MEDIA_GIT_BLOB = "93a6028bfd051efd983e180a1eae2e3378344d79"
INJECT_OLD = (b"/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system\n"
              b"/redwood/lib/libhakios.sb.dylib SpringBoard\n")
INJECT_NEW = INJECT_OLD + b"/redwood/lib/libhakios.media.dylib mediaserverd\n"
MD0_BYTES = 4194304


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B110 = _load("nat203_b110", PROC / "nat-110" / "build_sc2_hb_root.py")
need, run, sha256_file, tree, tree_diff = B110.need, B110.run, B110.sha256_file, B110.tree, B110.tree_diff


def donor_blob():
    """The library from the pinned donor commit itself (git object), not from whatever the checkout has."""
    head = subprocess.run(["git", "-C", str(DONOR), "rev-parse", DONOR_SHA + "^{commit}"], capture_output=True, text=True, check=True).stdout.strip()
    need(head == DONOR_SHA, "donor commit %s missing" % DONOR_SHA)
    entry = subprocess.run(["git", "-C", str(DONOR), "ls-tree", DONOR_SHA, DONOR_PATH], capture_output=True, text=True, check=True).stdout.split()
    need(entry[:3] == ["100755", "blob", MEDIA_GIT_BLOB], "donor tree entry differs: %s" % entry)
    data = subprocess.run(["git", "-C", str(DONOR), "cat-file", "blob", MEDIA_GIT_BLOB], capture_output=True, check=True).stdout
    import hashlib
    need(hashlib.sha256(data).hexdigest() == MEDIA_SHA256, "libhakios.media.dylib sha256 differs")
    return data


def build(out_dir, base_dir):
    for dep in (B110.MKAPFS, B110.VERIFY, B110.TOOL):
        need(Path(dep).is_file(), "required recipe tool missing: %s" % dep)
    out, base = Path(out_dir), Path(base_dir)
    need(sha256_file(base / "root.apfs") == BASE_APFS_SHA256, "base root.apfs is not NAT-110's")
    before = tree(base / "root")
    need((base / "root/etc/inject.conf").read_bytes() == INJECT_OLD, "base inject.conf differs")
    need((base / "root/LaunchDaemons/com.apple.mediaserverd.plist").is_file(), "base has no mediaserverd job")
    need(not (base / "root/lib/libhakios.media.dylib").exists(), "base already has the media library")
    data = donor_blob()

    shutil.rmtree(out, ignore_errors=True)
    root = out / "root"
    shutil.copytree(base / "root", root, symlinks=True)
    lib = root / "lib/libhakios.media.dylib"
    lib.write_bytes(data)
    os.chmod(lib, 0o755)
    conf = root / "etc/inject.conf"
    mode = conf.stat().st_mode & 0o7777
    conf.unlink()                      # a new inode: a hard link into the base is never written through
    conf.write_bytes(INJECT_NEW)
    os.chmod(conf, mode)

    after = tree(root)
    added, removed, changed = tree_diff(before, after)
    need(added == ["lib/libhakios.media.dylib"], "unexpected additions: %s" % (added,))
    need(not removed, "unexpected removals: %s" % (removed,))
    need(changed == ["etc/inject.conf"], "unexpected modifications: %s" % (changed,))

    img = out / "root.apfs"
    r = run([sys.executable, "-I", str(B110.MKAPFS), "-z", "--plain", "fw", "-o", str(img), "redwood=" + str(root)])
    need(r.returncode == 0, "mkapfs.py failed: " + r.stderr[-600:])
    mk_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    need(img.stat().st_size == MD0_BYTES, "root.apfs size %d != %d" % (img.stat().st_size, MD0_BYTES))
    r2 = run([sys.executable, "-I", str(B110.VERIFY), "content", str(img), str(root), "--all"])
    need(r2.returncode == 0, "verify.py content failed: " + (r2.stdout + r2.stderr)[-600:])
    # the kernel's own apfs_lib reading back the two changed files
    back = {}
    for rel in ("lib/libhakios.media.dylib", "etc/inject.conf"):
        got = subprocess.run([str(B110.TOOL), "cat", str(img), "/" + rel], capture_output=True, timeout=60).stdout
        back[rel] = got == (root / rel).read_bytes()
    need(all(back.values()), "apfs-tool readback differs: %s" % back)
    rec = {
        "kind": "host build record, nothing ran on a phone",
        "base": {"root_apfs_sha256": BASE_APFS_SHA256, "dir": str(base.relative_to(ROOT)) if base.is_relative_to(ROOT) else str(base)},
        "added": added, "changed": changed,
        "donor": {"repo": "references/hakios", "commit": DONOR_SHA, "path": DONOR_PATH, "git_blob": MEDIA_GIT_BLOB,
                  "sha256": MEDIA_SHA256, "bytes": len(data), "license": "MIT (references/hakios/LICENSE)",
                  "source": "userland/src/inject_media.c at the same commit"},
        "inject_conf": INJECT_NEW.decode(),
        "root_apfs": {"bytes": img.stat().st_size, "sha256": sha256_file(img), "mkapfs_last_line": mk_line},
        "verify_content": {"exit": r2.returncode, "tail": (r2.stdout + r2.stderr).strip()[-300:]},
        "apfs_tool_readback": back,
        "files": sum(1 for v in after.values() if v[0] == "file"),
        "script_sha256": sha256_file(Path(__file__)),
    }
    (out / "build.json").write_text((json.dumps(rec, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", ""))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/nat-203/pid1-sc2-hbm")
    ap.add_argument("--base", type=Path, default=ROOT / "artifacts/nat-110/pid1-sc2-hb")
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.base)
    except B110.BuildError as e:
        raise SystemExit("build_hbm_root: " + str(e))
    print(json.dumps({"root_apfs": rec["root_apfs"], "files": rec["files"], "readback": rec["apfs_tool_readback"]}, indent=1))


if __name__ == "__main__":
    main()
