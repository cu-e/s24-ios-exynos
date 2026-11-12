#!/usr/bin/env python3
"""IOS-010: build the resident root image (system.apfs, the first RAM disk /dev/md0) with the donor's tools.

This reproduces the "system image" step of the pinned HackiOS userland/build.sh (lines 642-746 at the pinned
revision) on the host, from the tree that the donor's sysimage/unpack.sh made out of the owner's IPSW:

  sysroot  = hard-link copy of sysimage/rootfs                         (the donor's `cp -al`)
  - System/Library/{LaunchDaemons,NanoLaunchDaemons,LaunchAngels}, xpc/launchd.plist removed, and
    System/Library/LaunchDaemons = symlink to /redwood/LaunchDaemons    (the jobs come from the small root, IOS-011)
  - redwood/, sbin/, System/Volumes/Darwin made; private/var/staged_system_apps moved to Applications
  - sbin/launchd -> sbin/launchd.darwin (Apple's), stage0 installed as sbin/launchd
  - System/Cryptexes/OS and /App = hard-link copies of the cryptex trees; the dyld shared cache files (not *.symbols)
    hard-linked into System/Cryptexes/OS/System/Library/Caches/com.apple.dyld
  image    = tools/apfs/mkapfs.py -z -o system.apfs System=sysroot,manifest=system.manifest   (unmodified, pinned)
  check    = tools/apfs/check-image.sh (apfsck -cw built from the pinned apfsprogs + the kernel's apfs_lib reader)

Deviations from the donor script, all by omission, none by change: mkhighrate.py (the 120 Hz frame-rate bundle keys; it is not
in the pinned review set), the audio DSP / modem firmware and speaker files (../fw-*, never in the repository), the package
manager prefix (../jb), the HakiosAudio.driver and HakiosMetal links, and big/ (Turnip/M2V).  Each of them is a feature of the
donor's phone, not part of "Apple's launchd, backboardd and SpringBoard are on the disk".

usage: python3 -I tools/ios/build_system_image.py OUT_DIR [--recipe DIR] [--stage0 FILE] [--no-check] [--keep-sysroot] [--report FILE]
Apple files are only read and hard-linked under artifacts/; nothing of them is copied into the repository.  Nothing runs on the phone.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEPS = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(argv, log, **kw):
    t = time.time()
    with open(log, "wb") as lf:
        r = subprocess.run([str(a) for a in argv], stdout=lf, stderr=subprocess.STDOUT, **kw)
    STEPS.append({"argv": [str(a).replace(str(ROOT) + "/", "") for a in argv], "exit": r.returncode,
                  "seconds": round(time.time() - t, 1), "log": str(log).replace(str(ROOT) + "/", "")})
    return r.returncode


def tail(path, n=6):
    try:
        return Path(path).read_text(errors="replace").strip().splitlines()[-n:]
    except OSError:
        return []


def need(cond, msg):
    if not cond:
        print("build_system_image:", msg, file=sys.stderr)
        sys.exit(1)


def tree_stats(path):
    files = links = size = 0
    for dirpath, _d, names in os.walk(path):
        for n in names:
            p = os.path.join(dirpath, n)
            if os.path.islink(p):
                links += 1
            else:
                files += 1
                size += os.path.getsize(p)
    return {"files": files, "symlinks": links, "bytes": size}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--recipe", type=Path, default=ROOT / "artifacts/ios-root/recipe")
    ap.add_argument("--stage0", type=Path, default=ROOT / "artifacts/ios-root/pid1-launchd/stage0")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--keep-sysroot", action="store_true")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    recipe = a.recipe.resolve()
    dar = recipe / "sysimage"
    cache = dar / "20F66__iPhone10,3_6"
    for rel in ("rootfs", "cryptex", "cryptex-app"):
        need((dar / rel).is_dir() and not (dar / rel).is_symlink(), "unpack tree part missing or a symlink: " + rel)
    need((dar / "system.manifest").is_file() and (dar / "var.skel").is_file(), "system.manifest missing")
    need(a.stage0.is_file(), "stage0 missing (run tools/ios/build_pid1_chain.py): %s" % a.stage0)
    need((recipe / "tools/apfs/mkapfs.py").is_file(), "recipe not staged")
    caches = sorted(p for p in cache.glob("dyld_shared_cache_arm64*") if not p.name.endswith(".symbols"))
    need(caches, "no dyld_shared_cache_arm64* in " + str(cache))

    launchd_src = dar / "rootfs/sbin/launchd"
    before = {"launchd_sha256": sha256(launchd_src), "launchd_inode": launchd_src.stat().st_ino}
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    sysroot = out / "sysroot"
    t0 = time.time()

    # --- compose (the donor's lines 655-668, 729-745) -----------------------------------------------------
    need(run(["cp", "-al", dar / "rootfs", sysroot], out / "01-cp-rootfs.log") == 0, "cp -al rootfs failed")
    sl = sysroot / "System/Library"
    for d in ("LaunchDaemons", "NanoLaunchDaemons", "LaunchAngels"):
        shutil.rmtree(sl / d, ignore_errors=True)
    (sl / "xpc/launchd.plist").unlink(missing_ok=True)
    os.symlink("/redwood/LaunchDaemons", sl / "LaunchDaemons")
    (sysroot / "redwood").mkdir(exist_ok=True)
    (sysroot / "sbin").mkdir(exist_ok=True)
    (sysroot / "System/Volumes/Darwin").mkdir(parents=True, exist_ok=True)
    staged = sysroot / "private/var/staged_system_apps"
    moved = 0
    if staged.is_dir():
        (sysroot / "Applications").mkdir(exist_ok=True)
        for p in sorted(staged.iterdir()):
            shutil.move(str(p), str(sysroot / "Applications" / p.name))
            moved += 1
        shutil.rmtree(sysroot / "private/var")
    os.rename(sysroot / "sbin/launchd", sysroot / "sbin/launchd.darwin")
    shutil.copyfile(a.stage0, sysroot / "sbin/launchd")
    os.chmod(sysroot / "sbin/launchd", 0o755)
    (sysroot / "System/Cryptexes").mkdir(parents=True, exist_ok=True)
    need(run(["cp", "-al", dar / "cryptex", sysroot / "System/Cryptexes/OS"], out / "02-cp-cryptex-os.log") == 0, "cp cryptex failed")
    need(run(["cp", "-al", dar / "cryptex-app", sysroot / "System/Cryptexes/App"], out / "03-cp-cryptex-app.log") == 0, "cp app cryptex failed")
    dyld_dir = sysroot / "System/Cryptexes/OS/System/Library/Caches/com.apple.dyld"
    dyld_dir.mkdir(parents=True, exist_ok=True)
    for f in caches:
        target = dyld_dir / f.name
        target.unlink(missing_ok=True)
        os.link(f, target)
    t_compose = time.time() - t0

    after = {"launchd_sha256": sha256(launchd_src), "launchd_inode": launchd_src.stat().st_ino}
    stats = tree_stats(sysroot)
    stage0_ok = sha256(sysroot / "sbin/launchd") == sha256(a.stage0)
    darwin_ok = sha256(sysroot / "sbin/launchd.darwin") == before["launchd_sha256"]

    # --- image -------------------------------------------------------------------------------------------------
    img = out / "system.apfs"
    t1 = time.time()
    rc = run([sys.executable, "-I", recipe / "tools/apfs/mkapfs.py", "-z", "-o", img,
              "System=%s,manifest=%s" % (sysroot, dar / "system.manifest")], out / "04-mkapfs.log")
    t_mk = time.time() - t1
    need(rc == 0 and img.is_file(), "mkapfs.py failed: " + " | ".join(tail(out / "04-mkapfs.log")))
    check = None
    t_check = None
    if not a.no_check:
        t2 = time.time()
        cr = run(["bash", recipe / "tools/apfs/check-image.sh", img, "System=%s,manifest=%s" % (sysroot, dar / "system.manifest")],
                 out / "05-check-image.log", cwd=recipe)
        t_check = time.time() - t2
        check = {"exit": cr, "tail": tail(out / "05-check-image.log", 8)}

    report = {
        "recipe_revision_note": "scripts staged from the pinned hakios tree (docs/procedures/ios-011/recipe-manifest.json)",
        "stage0": {"path": str(a.stage0).replace(str(ROOT) + "/", ""), "bytes": a.stage0.stat().st_size, "sha256": sha256(a.stage0)},
        "sysroot": dict(stats, staged_apps_moved=moved, stage0_installed_as_launchd=stage0_ok,
                        apple_launchd_kept_as_launchd_darwin=darwin_ok),
        "unpack_tree_untouched": before == after,
        "dyld_shared_cache_files": [{"name": f.name, "bytes": f.stat().st_size} for f in caches],
        "image": {"bytes": img.stat().st_size, "sha256": sha256(img), "mkapfs_tail": tail(out / "04-mkapfs.log")},
        "seconds": {"compose": round(t_compose, 1), "mkapfs": round(t_mk, 1), "check": None if t_check is None else round(t_check, 1)},
        "check_image": check, "steps": STEPS,
    }
    if not a.keep_sysroot:
        shutil.rmtree(sysroot)
    text = (json.dumps(report, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", "")
    if a.report:
        a.report.write_text(text)
    print(text[:3000])
    ok = report["unpack_tree_untouched"] and stage0_ok and darwin_ok and (check is None or check["exit"] == 0)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
