#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-110 host build: Stage C2 + heartbeat 4 MiB md0 APFS root (`artifacts/nat-110/pid1-sc2-hb/root.apfs`).

Derives cleanly on host from NAT-108's verified `pid1-sc1-hb` tree (`423` files, `root.apfs` SHA-256
`bb02a20bd9ec5ad87df634adbed93e9936ae24c3c32901ed1369b274850e9725`) with two targeted changes:
  1. Adds empty `etc/quiet` (`0644`), silencing `launchd`'s stderr (`2,086` lines / `280 KB` in NAT-109)
     via `sbin/init`'s `stat("/etc/quiet")` support while keeping daemon/hakios/hb/kernel console output;
  2. Removes `com.nat085.ps.plist` (duplicate heartbeat alongside `/redwood/bin/hb`) and 27 non-UI
     wireless/telemetry/cloud/widget/speech/sharing plists (`PRUNE_PLISTS`) so `SpringBoard` and
     `backboardd` receive CPU within the single-CPU (`cpus=1`) boot window.
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

SC1_HB_ROOT_APFS_SHA256 = "bb02a20bd9ec5ad87df634adbed93e9936ae24c3c32901ed1369b274850e9725"
SC1_HB_FILE_COUNT = 423
MD0_BYTES = 4194304

PRUNE_PLISTS = (
    "com.nat085.ps.plist",
    "com.apple.accessoryupdaterd.plist",
    "com.apple.aggregated.addaily.plist",
    "com.apple.aggregated.plist",
    "com.apple.analyticsd.plist",
    "com.apple.carkitd.plist",
    "com.apple.chronod.plist",
    "com.apple.cloudd.plist",
    "com.apple.contextstored.plist",
    "com.apple.coreduetd.plist",
    "com.apple.corespeechd.plist",
    "com.apple.dasd.plist",
    "com.apple.geod.plist",
    "com.apple.icloud.fmfd.plist",
    "com.apple.itunescloudd.plist",
    "com.apple.keychainsharingmessagingd.plist",
    "com.apple.MobileInternetSharing.plist",
    "com.apple.nsurlsessiond.plist",
    "com.apple.rapportd.plist",
    "com.apple.screensharingserver.plist",
    "com.apple.sharing.airdropui.plist",
    "com.apple.sharingd.plist",
    "com.apple.speechmodeltrainingd.plist",
    "com.apple.symptomsd-diag.plist",
    "com.apple.symptomsd.helper.plist",
    "com.apple.symptomsd.plist",
    "com.apple.wifid.plist",
    "com.apple.WirelessRadioManager.plist",
)

KEEP_REQUIRED = (
    "bin/hb",
    "etc/rc",
    "etc/inject.conf",
    "lib/libhakios.dylib",
    "lib/libhakios.sb.dylib",
    "LaunchDaemons/com.apple.SpringBoard.plist",
    "LaunchDaemons/com.apple.backboardd.plist",
    "LaunchDaemons/com.apple.lsd.plist",
    "LaunchDaemons/com.apple.donotdisturbd.plist",
    "var/mobile/Library/Preferences/com.apple.springboard.plist",
    "var/mobile/Library/Preferences/com.apple.frontboard.plist",
    "var/mobile/Library/Preferences/com.apple.purplebuddy.plist",
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SB = _load("nat110_nat099_sb", PROC / "nat-099" / "build_stage_b_root.py")
BuildError = SB.BuildError
need = SB.need
run = SB.run
sha256_file = SB.sha256_file
tree = SB.tree
tree_diff = SB.tree_diff

RECIPE = ROOT / "artifacts/ios-root/recipe"
MKAPFS = RECIPE / "tools/apfs/mkapfs.py"
VERIFY = RECIPE / "tools/apfs/verify.py"
TOOL = RECIPE / "apfs-work/apfs-tool"


def build(out_dir, base_dir, mkapfs=MKAPFS, verify=VERIFY, tool=TOOL):
    """Build Stage C2 + hb root.apfs at `out_dir` from `base_dir` (NAT-108 pid1-sc1-hb)."""
    for dep in (mkapfs, verify, tool):
        need(Path(dep).is_file(), "required recipe tool missing: %s" % dep)
    out = Path(out_dir)
    base = Path(base_dir)
    base_root = base / "root"
    base_apfs = base / "root.apfs"
    need(base_root.is_dir() and base_apfs.is_file(), "base dir missing root or root.apfs: %s" % base)
    need(sha256_file(base_apfs) == SC1_HB_ROOT_APFS_SHA256,
         "base root.apfs sha256 != pinned NAT-108 %s" % SC1_HB_ROOT_APFS_SHA256)

    before = tree(base_root)
    base_files = sum(1 for v in before.values() if v[0] == "file")
    need(base_files == SC1_HB_FILE_COUNT, "base file count %d != %d" % (base_files, SC1_HB_FILE_COUNT))
    need("etc/quiet" not in before, "base unexpectedly contains etc/quiet")

    shutil.rmtree(out, ignore_errors=True)
    root = out / "root"
    shutil.copytree(base_root, root, symlinks=True)

    quiet = root / "etc/quiet"
    quiet.write_bytes(b"")
    os.chmod(quiet, 0o644)

    for name in PRUNE_PLISTS:
        p = root / "LaunchDaemons" / name
        need(p.is_file(), "expected pruned plist missing in base: %s" % name)
        p.unlink()

    for rel in KEEP_REQUIRED:
        need((root / rel).is_file(), "required file missing after prune: %s" % rel)

    after = tree(root)
    added, removed, changed = tree_diff(before, after)
    need(added == ["etc/quiet"], "unexpected additions: %s" % (added,))
    expected_removed = sorted("LaunchDaemons/" + n for n in PRUNE_PLISTS)
    need(removed == expected_removed, "unexpected removals: %s" % (removed,))
    need(not changed, "unexpected modifications: %s" % (changed,))

    img = out / "root.apfs"
    r = run([sys.executable, "-I", str(mkapfs), "-z", "--plain", "fw", "-o", str(img), "redwood=" + str(root)])
    need(r.returncode == 0, "mkapfs.py failed: " + r.stderr[-600:])
    mk_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    need(img.stat().st_size == MD0_BYTES, "root.apfs size %d != %d" % (img.stat().st_size, MD0_BYTES))

    r2 = run([sys.executable, "-I", str(verify), "content", str(img), str(root), "--all"])
    need(r2.returncode == 0, "verify.py content failed: " + (r2.stdout + r2.stderr)[-600:])

    kernel = {"entries": 0, "files_compared": 0, "mismatches": []}
    for line in run([str(tool), "census", str(img)]).stdout.splitlines():
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
    need(not kernel["mismatches"] and kernel["files_compared"] == files,
         "kernel apfs_lib readback mismatch: %s" % kernel)

    ld_plists = sorted(p.name for p in (root / "LaunchDaemons").glob("*.plist"))
    rec = {
        "kind": "host build record, nothing ran on a phone",
        "base": {"root_apfs_sha256": SC1_HB_ROOT_APFS_SHA256, "files": SC1_HB_FILE_COUNT},
        "added": added,
        "pruned_plists": list(PRUNE_PLISTS),
        "launchdaemons_plist_count": len(ld_plists),
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
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/nat-110/pid1-sc2-hb")
    ap.add_argument("--base", type=Path, default=ROOT / "artifacts/nat-108/pid1-sc1-hb")
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.base)
    except BuildError as e:
        raise SystemExit("build_sc2_hb_root: " + str(e))
    print(
        json.dumps(
            {
                "root_apfs": rec["root_apfs"],
                "files": rec["files"],
                "launchdaemons_plist_count": rec["launchdaemons_plist_count"],
                "kernel_readback_ok": not rec["kernel_apfs_lib_readback"]["mismatches"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
