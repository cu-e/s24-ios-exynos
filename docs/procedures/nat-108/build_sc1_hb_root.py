#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-108 Stage C1 + heartbeat small root builder (host-only).

Combines NAT-106's Stage B + hb small root (`artifacts/nat-106/pid1-sb2-hb`, 29 files) with the
donor's Stage C SpringBoard userland configuration:
  * all 22 donor DARWIN_JOBS + `--rest` on-demand LaunchDaemons/LaunchAngels via pinned mkjobs.py
    (adding `com.apple.SpringBoard`, `com.apple.lsd`, `com.apple.wifid` and 382 on-demand services,
    while preserving `com.nat085.ps.plist`, `bin/hb`, and `etc/rc`);
  * pinned donor prebuilt `lib/libhakios.sb.dylib` (mode 0755);
  * two-line `etc/inject.conf` adding `/redwood/lib/libhakios.sb.dylib SpringBoard`;
  * donor `var/` preference plists (`references/hakios/userland/var`, 8 files under `mobile/Library/Preferences`),
    fixed zoneinfo symlinks in `etc/var.skel` (`UTC`, `/usr/share/zoneinfo.default`), and `var.skel`
    entries for the `var/` files, `/private/var/mobile/tmp`, and `/private/var/db/hakios-metal-cache`.

Nothing runs on a phone. Output defaults to `artifacts/nat-108/pid1-sc1-hb`.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

SB2_HB_ROOT_APFS_SHA256 = "182aead762086a1f322995bd0f05365d7115184d8d775bac3563aa527fa61c56"
SB2_HB_FILE_COUNT = 29
MKJOBS_SHA256 = "75a79f8ba1e3abd22608058337584f0c4b70a6fafc410c7e8c9622fb9180bea9"
LIBHAKIOS_SB_SHA256 = "d4f1c6b06b4b016b1a3ea77d741382053efde0093a5a8f77226a215bee87b232"
MD0_BYTES = 4194304

DARWIN_JOBS = (
    "com.apple.notifyd",
    "com.apple.cfprefsd.xpc.daemon",
    "com.apple.cfprefsd.xpc.daemon.system",
    "com.apple.logd",
    "com.apple.syslogd",
    "com.apple.distnoted.xpc.daemon",
    "com.apple.diagnosticd",
    "com.apple.fseventsd",
    "com.apple.containermanagerd",
    "com.apple.containermanagerd.system",
    "com.apple.runningboardd",
    "com.apple.backboardd",
    "com.apple.mobile.usermanagerd",
    "com.apple.mobilegestalt.xpc",
    "com.apple.lsd",
    "com.apple.powerd",
    "com.apple.analyticsd",
    "com.apple.logd_helper",
    "com.apple.iconservices.iconservicesagent",
    "com.apple.pluginkit.pkd",
    "com.apple.SpringBoard",
    "com.apple.wifid",
)

EXPECTED_VAR_FILES = (
    "mobile/Library/Preferences/com.apple.VideoProcessing.plist",
    "mobile/Library/Preferences/com.apple.assistant.support.plist",
    "mobile/Library/Preferences/com.apple.coremedia.plist",
    "mobile/Library/Preferences/com.apple.frontboard.plist",
    "mobile/Library/Preferences/com.apple.keyboard.preferences.plist",
    "mobile/Library/Preferences/com.apple.migration.plist",
    "mobile/Library/Preferences/com.apple.purplebuddy.plist",
    "mobile/Library/Preferences/com.apple.springboard.plist",
)

INJECT_CONF = (
    b"/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system\n"
    b"/redwood/lib/libhakios.sb.dylib SpringBoard\n"
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B99 = _load("nat108_b99", HERE.parent / "nat-099" / "build_stage_b_root.py")
BuildError = B99.BuildError
need = B99.need
sha256_file = B99.sha256_file
tree = B99.tree
tree_diff = B99.tree_diff
run = B99.run


def rewrite_var_skel(text, var_rel_files):
    """Apply donor zoneinfo/timezone fixes and append var/ file + tmp/cache directory entries."""
    zoneinfo_old = "l\t/usr/share/zoneinfo\t/private/var/db/timezone/zoneinfo"
    zoneinfo_new = "l\t/usr/share/zoneinfo.default\t/private/var/db/timezone/zoneinfo"
    need(text.count(zoneinfo_old) == 1, "expected 1 zoneinfo link in var.skel")
    out = text.replace(zoneinfo_old, zoneinfo_new)

    tz_pat = re.compile(r"^l\t/var/db/timezone/zoneinfo/[^\t\n]+\t/private/var/db/timezone/localtime$", re.M)
    matches = tz_pat.findall(out)
    need(len(matches) == 1, "expected 1 localtime link in var.skel, found %d" % len(matches))
    out = tz_pat.sub("l\t/var/db/timezone/zoneinfo/UTC\t/private/var/db/timezone/localtime", out)

    if out and not out.endswith("\n"):
        out += "\n"
    extra = []
    for rel in sorted(var_rel_files):
        owner = 501 if rel.startswith("mobile/") else 0
        extra.append("f\t644\t%d\t%d\t/private/var/%s\t/var/%s" % (owner, owner, rel, rel))
    extra.append("d\t700\t501\t501\t/private/var/mobile/tmp")
    extra.append("d\t1777\t0\t0\t/private/var/db/hakios-metal-cache")
    return out + "\n".join(extra) + "\n"


def _clean_env():
    env = dict(os.environ)
    env.pop("OSLOG", None)
    env.pop("ALLOW", None)
    return env


def build(out, base, recipe, sb_dylib, var_dir):
    """Build Stage C1 + hb small root APFS image on top of pinned NAT-106 pid1-sb2-hb."""
    out, base, recipe, sb_dylib, var_dir = Path(out), Path(base), Path(recipe), Path(sb_dylib), Path(var_dir)
    need(not out.exists(), "%s exists; the output directory must be new" % out)
    base_img, base_root = base / "root.apfs", base / "root"
    need(base_img.is_file() and base_root.is_dir(), "%s has no root.apfs and root/" % base)
    need(sha256_file(base_img) == SB2_HB_ROOT_APFS_SHA256,
         "base root.apfs is sha256 %s, not pinned %s" % (sha256_file(base_img), SB2_HB_ROOT_APFS_SHA256))
    before = tree(base_root)
    base_files = sum(1 for v in before.values() if v[0] == "file")
    need(base_files == SB2_HB_FILE_COUNT, "base tree holds %d files, not %d" % (base_files, SB2_HB_FILE_COUNT))

    need(sb_dylib.is_file() and sha256_file(sb_dylib) == LIBHAKIOS_SB_SHA256,
         "%s is not pinned libhakios.sb.dylib (sha256 %s)" % (sb_dylib, LIBHAKIOS_SB_SHA256))
    need(var_dir.is_dir(), "%s is missing" % var_dir)
    var_files = sorted(str(p.relative_to(var_dir)) for p in var_dir.rglob("*") if p.is_file())
    need(tuple(var_files) == EXPECTED_VAR_FILES, "unexpected var/ files: %s" % (var_files,))

    mkjobs = recipe / "userland/mkjobs.py"
    rootfs = recipe / "sysimage/rootfs"
    mkapfs = recipe / "tools/apfs/mkapfs.py"
    verify = recipe / "tools/apfs/verify.py"
    tool = recipe / "apfs-work/apfs-tool"
    for f in (mkjobs, mkapfs, verify, tool):
        need(f.is_file(), "%s is missing" % f)
    need(sha256_file(mkjobs) == MKJOBS_SHA256, "mkjobs.py sha256 mismatch")
    need((rootfs / "System/Library/LaunchDaemons/com.apple.SpringBoard.plist").is_file(), "SpringBoard plist missing from rootfs")

    out.mkdir(parents=True)
    root = out / "root"
    shutil.copytree(base_root, root, symlinks=True)

    r_jobs = subprocess.run(
        [sys.executable, "-I", str(mkjobs), "--rest", str(rootfs), str(root / "LaunchDaemons"), *DARWIN_JOBS],
        capture_output=True, text=True, timeout=120, env=_clean_env(),
    )
    need(r_jobs.returncode == 0, "mkjobs.py --rest failed: " + r_jobs.stderr[-600:])

    # Keep NAT-099 check on backboardd plist intact
    apple_bb = (rootfs / "System/Library/LaunchDaemons/com.apple.backboardd.plist").read_bytes()
    B99.check_backboardd_plist(apple_bb, (root / "LaunchDaemons/com.apple.backboardd.plist").read_bytes())

    shutil.copy2(sb_dylib, root / "lib/libhakios.sb.dylib")
    os.chmod(root / "lib/libhakios.sb.dylib", 0o755)

    need(len(INJECT_CONF) <= 4096, "inject.conf exceeds init.c 4096 B buffer")
    (root / "etc/inject.conf").write_bytes(INJECT_CONF)

    shutil.copytree(var_dir, root / "var")
    for p in (root / "var").rglob("*"):
        if p.is_file():
            os.chmod(p, 0o644)

    skel_old = (root / "etc/var.skel").read_text()
    (root / "etc/var.skel").write_text(rewrite_var_skel(skel_old, var_files))

    need((root / "LaunchDaemons/com.nat085.ps.plist").read_bytes() == (base_root / "LaunchDaemons/com.nat085.ps.plist").read_bytes(),
         "com.nat085.ps.plist changed")
    need((root / "bin/hb").is_file() and b"/redwood/bin/hb" in (root / "etc/rc").read_bytes(), "hb/rc lost")

    after = tree(root)
    added, removed, changed = tree_diff(before, after)
    need(not removed, "unexpected removals from base: %s" % (removed,))
    need(after["lib/libhakios.sb.dylib"][1] == 0o755, "libhakios.sb.dylib mode %o != 755" % after["lib/libhakios.sb.dylib"][1])
    need("LaunchDaemons/com.apple.SpringBoard.plist" in after, "SpringBoard plist missing")
    need("LaunchDaemons/com.apple.lsd.plist" in after, "lsd plist missing")

    img = out / "root.apfs"
    r = run([sys.executable, "-I", mkapfs, "-z", "--plain", "fw", "-o", img, "redwood=" + str(root)])
    need(r.returncode == 0, "mkapfs.py failed: " + r.stderr[-600:])
    mk_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    need(img.stat().st_size == MD0_BYTES, "root.apfs size %d != %d" % (img.stat().st_size, MD0_BYTES))

    r2 = run([sys.executable, "-I", verify, "content", img, root, "--all"])
    need(r2.returncode == 0, "verify.py content failed: " + (r2.stdout + r2.stderr)[-600:])

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
    need(not kernel["mismatches"] and kernel["files_compared"] == files,
         "kernel apfs_lib readback mismatch: %s" % kernel)

    ld_plists = sorted(p.name for p in (root / "LaunchDaemons").glob("*.plist"))
    rec = {
        "kind": "host build record, nothing ran on a phone",
        "base": {"root_apfs_sha256": SB2_HB_ROOT_APFS_SHA256, "files": SB2_HB_FILE_COUNT},
        "added_count": len(added),
        "changed_files": changed,
        "darwin_jobs": list(DARWIN_JOBS),
        "launchdaemons_plist_count": len(ld_plists),
        "inject_conf": INJECT_CONF.decode(),
        "libhakios_sb_dylib_sha256": LIBHAKIOS_SB_SHA256,
        "var_files": {f: sha256_file(root / "var" / f) for f in var_files},
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
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/nat-108/pid1-sc1-hb")
    ap.add_argument("--base", type=Path, default=ROOT / "artifacts/nat-106/pid1-sb2-hb")
    ap.add_argument("--recipe", type=Path, default=ROOT / "artifacts/ios-root/recipe")
    ap.add_argument("--sb-dylib", type=Path, default=ROOT / "references/hakios/prebuilt/userland/libhakios.sb.dylib")
    ap.add_argument("--var-dir", type=Path, default=ROOT / "references/hakios/userland/var")
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.base, a.recipe, a.sb_dylib, a.var_dir)
    except BuildError as e:
        raise SystemExit("build_sc1_hb_root: " + str(e))
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
