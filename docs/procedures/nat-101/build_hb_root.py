#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-101: build the observability small root on the host (nothing here ran on a phone).

Observability small root = NAT-096's quiet Stage A small root (18 Apple LaunchDaemons plists without lsd + the com.nat085.ps heartbeat job, 25 files) with exactly two changes:

  bin/hb       NEW   the static heartbeat program built by build_hb.py from src/hb.c (mode 0755)
  etc/rc       CHANGED  NAT-083's rc plus one comment block and one line, `/redwood/bin/hb &`, placed directly before `exec /sbin/launchd.darwin`
                        (the donor init forks the program and does not wait; it then lives on as a child of process 1, which becomes Apple's launchd)

  build_hb_root.py --out DIR --hb PATH_TO_hb [--base artifacts/nat-096/pid1-sq] [--recipe artifacts/ios-root/recipe]

It refuses: a base whose root.apfs or etc/rc is not the pinned one, an hb that is not a static arm64 Mach-O (build_hb.audit), an rc whose last line is not the
`exec /sbin/launchd.darwin` line, an output directory that exists, and a result whose tree differs from the base's in any path but those two. The image is
written by the donor's mkapfs.py with the arguments the chain tool uses (the same call as NAT-099), then read back twice (the donor's verify.py content
comparison and the kernel's own apfs_lib, every file with its mode). Output: DIR/root/, DIR/root.apfs, DIR/build.json.

What this does not show: that hb starts on the phone, that its lines reach the kernel log, or anything about launchd's jobs."""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


B99 = _load("nat101_nat099_build", ROOT / "docs/procedures/nat-099/build_stage_b_root.py")
BH = _load("nat101_build_hb", HERE / "build_hb.py")
BuildError, need, sha256_bytes, sha256_file, tree, tree_diff = B99.BuildError, B99.need, B99.sha256_bytes, B99.sha256_file, B99.tree, B99.tree_diff

BASE_ROOT_APFS_SHA256 = B99.BASE_ROOT_APFS_SHA256          # NAT-096's small root (md0) of loader-diag-xnu-sq-md1
BASE_FILE_COUNT = B99.BASE_FILE_COUNT
BASE_RC_SHA256 = "990910b5450753b07491013519fb3c1e181d4086ef885c4b288c6d3aee08b9c7"   # docs/procedures/nat-083/rc.nat083
EXEC_LINE = "exec /sbin/launchd.darwin\n"
HB_LINE = "/redwood/bin/hb &\n"
RC_ADDITION = (
    "# NAT-101 (this project): a launchd-independent heartbeat. /redwood/bin/hb writes a marker line and runs Apple's /bin/ps with its output on the console every 10 s,\n"
    "# without going through launchd, logd or a job plist (NAT-098 lost both launchd's console lines and the com.nat085.ps job's lists after logd ran).\n"
    "# init forks it and does not wait; it stays a child of process 1, which becomes Apple's launchd on the next line.\n"
    + HB_LINE
)
ADDED = ("bin/hb",)
CHANGED = ("etc/rc",)


def new_rc(base_rc):
    """The base rc with RC_ADDITION directly before its last line, which must be the exec line."""
    need(sha256_bytes(base_rc) == BASE_RC_SHA256, "the base etc/rc is sha256 %s, not the pinned %s" % (sha256_bytes(base_rc), BASE_RC_SHA256))
    text = base_rc.decode()
    need(text.endswith(EXEC_LINE) and text.count(EXEC_LINE) == 1, "the base etc/rc does not end with the single line %r" % EXEC_LINE.strip())
    return (text[:-len(EXEC_LINE)] + RC_ADDITION + EXEC_LINE).encode()


def write_image(root, img, recipe):
    """mkapfs (the NAT-099 call), verify.py content and the kernel's apfs_lib readback -> (record dict)."""
    mkapfs, verify, tool = recipe / "tools/apfs/mkapfs.py", recipe / "tools/apfs/verify.py", recipe / "apfs-work/apfs-tool"
    for f in (mkapfs, verify, tool):
        need(f.is_file(), "%s is missing" % f)
    r = B99.run([sys.executable, "-I", mkapfs, "-z", "--plain", "fw", "-o", img, "redwood=" + str(root)])
    need(r.returncode == 0, "mkapfs.py failed: " + r.stderr[-600:])
    mk_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    r2 = B99.run([sys.executable, "-I", verify, "content", img, root, "--all"])
    need(r2.returncode == 0, "verify.py content failed: " + (r2.stdout + r2.stderr)[-600:])
    kernel = {"entries": 0, "files_compared": 0, "mismatches": []}
    for line in B99.run([tool, "census", img]).stdout.splitlines():
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
    return {"mkapfs_last_line": mk_line, "verify": {"exit": r2.returncode, "tail": (r2.stdout + r2.stderr).strip()[-300:]}, "kernel": kernel}


def build(out, base, recipe, hb):
    out, base, recipe, hb = Path(out), Path(base), Path(recipe), Path(hb)
    need(not out.exists(), "%s exists; the output directory must be new" % out)
    base_img, base_root = base / "root.apfs", base / "root"
    need(base_img.is_file() and base_root.is_dir(), "%s has no root.apfs and root/" % base)
    need(sha256_file(base_img) == BASE_ROOT_APFS_SHA256, "the base root.apfs is sha256 %s, not the pinned %s" % (sha256_file(base_img), BASE_ROOT_APFS_SHA256))
    before = tree(base_root)
    nfiles = sum(1 for v in before.values() if v[0] == "file")
    need(nfiles == BASE_FILE_COUNT, "the base tree holds %d files, not %d" % (nfiles, BASE_FILE_COUNT))
    need(not any(p in before for p in ADDED), "the base tree already holds one of %s" % (ADDED,))
    need(hb.is_file(), "%s is not a file" % hb)
    hb_bytes = hb.read_bytes()
    try:
        BH.audit(hb_bytes)
    except BH.BuildError as e:
        raise BuildError("the heartbeat program is not a static arm64 Mach-O: %s" % e)
    rc = new_rc((base_root / "etc/rc").read_bytes())
    out.mkdir(parents=True)
    root = out / "root"
    shutil.copytree(base_root, root, symlinks=True)
    (root / "etc/rc").write_bytes(rc)          # same inode mode as the base file (the file exists, write keeps its mode)
    (root / "bin/hb").write_bytes(hb_bytes)
    (root / "bin/hb").chmod(0o755)
    after = tree(root)
    added, removed, changed = tree_diff(before, after)
    need(added == sorted(ADDED) and not removed and changed == sorted(CHANGED), "the tree differs from the base in %s added, %s removed, %s changed" % (added, removed, changed))
    need(after["bin/hb"][1] == 0o755 and after["etc/rc"][1] == before["etc/rc"][1], "modes: bin/hb %o, etc/rc %o (base %o)" % (after["bin/hb"][1], after["etc/rc"][1], before["etc/rc"][1]))
    img = out / "root.apfs"
    w = write_image(root, img, recipe)
    files = sum(1 for v in after.values() if v[0] == "file")
    w["kernel"]["local_files"] = files
    need(not w["kernel"]["mismatches"] and w["kernel"]["files_compared"] == files, "the kernel's apfs_lib readback does not equal the tree: %s" % w["kernel"])
    rec = {
        "kind": "host build record, nothing ran on a phone",
        "base": {"root_apfs_sha256": BASE_ROOT_APFS_SHA256, "rc_sha256": BASE_RC_SHA256, "files": BASE_FILE_COUNT},
        "added": {"bin/hb": {"sha256": sha256_bytes(hb_bytes), "mode": "755", "bytes": len(hb_bytes)}},
        "changed": {"etc/rc": {"sha256": sha256_bytes(rc), "bytes": len(rc), "base_sha256": BASE_RC_SHA256, "addition": RC_ADDITION}},
        "root_apfs": {"bytes": img.stat().st_size, "sha256": sha256_file(img), "mkapfs_last_line": w["mkapfs_last_line"]},
        "verify_content": w["verify"],
        "kernel_apfs_lib_readback": w["kernel"],
        "files": files,
        "script_sha256": sha256_file(Path(__file__)),
    }
    (out / "build.json").write_text((json.dumps(rec, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", ""))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--hb", required=True, type=Path)
    ap.add_argument("--base", type=Path, default=ROOT / "artifacts/nat-096/pid1-sq")
    ap.add_argument("--recipe", type=Path, default=ROOT / "artifacts/ios-root/recipe")
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.base, a.recipe, a.hb)
    except BuildError as e:
        raise SystemExit("build_hb_root: " + str(e))
    print(json.dumps({"root_apfs": rec["root_apfs"], "files": rec["files"], "kernel_readback_ok": not rec["kernel_apfs_lib_readback"]["mismatches"]}, indent=1))


if __name__ == "__main__":
    main()
