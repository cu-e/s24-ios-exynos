#!/usr/bin/env python3
"""IOS-011: build the donor's PID 1 chain (libmini, stage0, init, child) with the project's own arm64 toolchain
and make the small root image (root.apfs, the second RAM disk /dev/md1) with the donor's mkapfs.py.

The sources are the pinned HackiOS files staged by tools/ios/stage_hakios_recipe.py (MIT; libmini, init.c,
stage0.c, child.c).  What this script replaces is only the donor's compiler driver: build.sh calls
`xnu-clang -arch arm64 -Os -static -nostdlib -ffreestanding -fno-stack-protector -fno-builtin -Wall -Wextra`
with `-Wl,-e,_start -Wl,-pagezero_size,0x100000000`, and neither xnu-clang nor ld64 exists on this host.  Here the
same flags go to the project's own clang 17 (built from source under artifacts/) and cctools ld.  The layout of
root/ follows userland/build.sh (the lines named in LAYOUT below).

usage: python3 -I tools/ios/build_pid1_chain.py OUT_DIR [--recipe DIR] [--unpack DIR] [--rc rc.darwin|rc.launchd]
                                                [--jobs] [--report FILE]
Nothing here runs on the phone.  Apple files are only read (var.skel, LaunchDaemons) and nothing of them is copied
into the repository.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLANG = ROOT / "artifacts/xnu-compiler-cxx-storage/source-build-session2/clang"
HEADERS = ROOT / "artifacts/xnu-compiler-types/frontend-session1/compiler-build/lib/clang/17/include"
LD = ROOT / "artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld"
OTOOL = ROOT / "artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-otool"
CFLAGS = ["--target=arm64-apple-ios16.5", "-Os", "-ffreestanding", "-fno-stack-protector", "-fno-builtin", "-nostdinc",
          "-isystem", str(HEADERS), "-Wall", "-Wextra", "-fno-pic", "-fno-pie"]
LDFLAGS = ["-arch", "arm64", "-static", "-e", "_start", "-pagezero_size", "0x100000000",
           "-iphoneos_version_min", "16.5"]
LAYOUT = "userland/build.sh lines 151-170 (programs, motd, pattern.bin), 408 (var.skel), 449 (etc/rc), 464 (mkjobs)"
DARWIN_JOBS = ("com.apple.notifyd com.apple.cfprefsd.xpc.daemon com.apple.cfprefsd.xpc.daemon.system com.apple.logd "
               "com.apple.syslogd com.apple.distnoted.xpc.daemon com.apple.diagnosticd com.apple.fseventsd "
               "com.apple.containermanagerd com.apple.containermanagerd.system com.apple.runningboardd "
               "com.apple.backboardd com.apple.mobile.usermanagerd com.apple.mobilegestalt.xpc com.apple.lsd "
               "com.apple.powerd com.apple.analyticsd com.apple.logd_helper "
               "com.apple.iconservices.iconservicesagent com.apple.pluginkit.pkd com.apple.SpringBoard "
               "com.apple.wifid").split()

log = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(argv, **kw):
    r = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=kw.pop("timeout", 600), **kw)
    log.append({"argv": [str(a).replace(str(ROOT) + "/", "") for a in argv], "exit": r.returncode,
                "stderr_tail": (r.stderr or "")[-400:]})
    return r


def need(cond, msg):
    if not cond:
        print("build_pid1_chain:", msg, file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--recipe", type=Path, default=ROOT / "artifacts/ios-root/recipe")
    ap.add_argument("--unpack", type=Path, default=None)
    ap.add_argument("--rc", default="rc.darwin")
    ap.add_argument("--jobs", action="store_true", help="also copy the donor's job set with mkjobs.py")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    recipe = a.recipe
    unpack = a.unpack or recipe / "sysimage"
    out = a.out
    for tool in (CLANG, LD, OTOOL, HEADERS / "stdarg.h"):
        need(tool.exists(), "missing toolchain part: %s" % tool)
    for rel in ("userland/libmini/mini.c", "userland/libmini/mini.h", "userland/libmini/start.S",
                "userland/src/init.c", "userland/src/stage0.c", "userland/src/child.c", "userland/" + a.rc,
                "tools/apfs/mkapfs.py"):
        need((recipe / rel).is_file(), "recipe file missing (run tools/ios/stage_hakios_recipe.py): " + rel)
    need((unpack / "var.skel").is_file(), "unpack tree missing var.skel")
    if out.exists():
        shutil.rmtree(out)
    obj = out / "obj"
    obj.mkdir(parents=True)
    ul = recipe / "userland"

    # --- compile and link (donor flags, project toolchain) ---------------------------------------
    steps = [("mini.o", ["-I", ul / "libmini", "-c", ul / "libmini/mini.c"]),
             ("start.o", ["-c", ul / "libmini/start.S"])]
    programs = ["stage0", "init", "child"]
    for p in programs:
        steps.append((p + ".o", ["-I", ul / "libmini", "-c", ul / "src" / (p + ".c")]))
    for name, args in steps:
        r = run([CLANG, *CFLAGS, *args, "-o", obj / name])
        need(r.returncode == 0, "compile %s failed: %s" % (name, r.stderr[-600:]))
        need(not r.stderr.strip(), "compile %s printed diagnostics: %s" % (name, r.stderr[-600:]))
    for p in programs:
        r = run([LD, *LDFLAGS, obj / (p + ".o"), obj / "mini.o", obj / "start.o", "-o", out / p])
        need(r.returncode == 0, "link %s failed: %s" % (p, r.stderr[-600:]))

    # --- independent look at the result: load commands ----------------------------------------------
    macho = {}
    for p in programs:
        r = run([OTOOL, "-l", out / p])
        cmds = [ln.split()[1] for ln in r.stdout.splitlines() if ln.strip().startswith("cmd ")]
        macho[p] = {"bytes": (out / p).stat().st_size, "sha256": sha256(out / p), "load_commands": cmds}
        need("LC_LOAD_DYLIB" not in cmds and "LC_LOAD_DYLINKER" not in cmds and "LC_UNIXTHREAD" in cmds,
             "%s is not a static program with its own entry: %s" % (p, cmds))

    # --- compose the small root (the donor's layout) ---------------------------------------------------
    root = out / "root"
    for d in ("sbin", "bin", "etc", "share", "LaunchDaemons"):
        (root / d).mkdir(parents=True)
    shutil.copy2(out / "init", root / "sbin/init")
    shutil.copy2(out / "child", root / "bin/child")
    (root / "etc/motd").write_text("Darwin userland 16.5 on the S24 project: image built by tools/ios/build_pid1_chain.py\n")
    (root / "share/pattern.bin").write_bytes(bytes(((i * 31 + (i >> 8)) & 0xFF) for i in range(300000)))
    shutil.copy2(unpack / "var.skel", root / "etc/var.skel")
    shutil.copy2(ul / a.rc, root / "etc/rc")
    jobs_note = "none"
    if a.jobs:
        need((ul / "mkjobs.py").is_file() and (unpack / "rootfs").is_dir(), "mkjobs.py or rootfs missing")
        r = run([sys.executable, "-I", ul / "mkjobs.py", unpack / "rootfs", root / "LaunchDaemons", *DARWIN_JOBS])
        need(r.returncode == 0, "mkjobs.py failed: " + r.stderr[-600:])
        jobs_note = "%d plists" % len(list((root / "LaunchDaemons").iterdir()))

    # --- the image, by the donor's writer, then a content comparison with its reader ---------------------
    img = out / "root.apfs"
    r = run([sys.executable, "-I", recipe / "tools/apfs/mkapfs.py", "-z", "--plain", "fw", "-o", img, "redwood=" + str(root)])
    need(r.returncode == 0, "mkapfs.py failed: " + r.stderr[-600:])
    mk_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    r2 = run([sys.executable, "-I", recipe / "tools/apfs/verify.py", "content", img, root, "--all"])
    # the kernel's own apfs_lib (the same .c files the payload kernel is built from), built for this host by the donor's
    # build-tool.sh, reads every file back: contents and modes must equal the directory the image was made from
    tool = recipe / "apfs-work/apfs-tool"
    if not tool.exists():
        rb = run(["bash", recipe / "tools/apfs/build-tool.sh"], cwd=recipe)
        need(rb.returncode == 0 and tool.exists(), "build-tool.sh failed: " + rb.stderr[-600:])
    census = run([tool, "census", img]).stdout.splitlines()
    kernel_reader = {"entries": 0, "files_compared": 0, "mismatches": []}
    for line in census:
        parts = line.split("\t")
        if len(parts) != 7 or not parts[0].startswith("/"):
            continue
        kernel_reader["entries"] += 1
        path, kind, mode = parts[0], parts[1], parts[2]
        local = root / path.lstrip("/")
        if kind == "8":
            got = subprocess.run([str(tool), "cat", str(img), path], capture_output=True, timeout=60).stdout
            kernel_reader["files_compared"] += 1
            if got != local.read_bytes():
                kernel_reader["mismatches"].append(path)
            if int(mode, 8) & 0o7777 != local.stat().st_mode & 0o7777:
                kernel_reader["mismatches"].append(path + " (mode)")
    local_files = sum(1 for _ in root.rglob("*") if _.is_file())
    kernel_reader["local_files"] = local_files
    kernel_reader["ok"] = (not kernel_reader["mismatches"] and kernel_reader["files_compared"] == local_files)
    report = {"toolchain": {"clang": sha256(CLANG), "ld": sha256(LD), "otool": sha256(OTOOL), "cflags": CFLAGS,
                            "ldflags": LDFLAGS},
              "layout_follows": LAYOUT, "rc": a.rc, "jobs": jobs_note, "programs": macho,
              "root_apfs": {"bytes": img.stat().st_size, "sha256": sha256(img), "mkapfs_last_line": mk_line},
              "verify_content": {"exit": r2.returncode, "tail": (r2.stdout + r2.stderr).strip()[-400:]},
              "kernel_apfs_lib_readback": kernel_reader,
              "commands": log}
    text = (json.dumps(report, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", "")
    if a.report:
        a.report.write_text(text)
    print(text)
    return 0 if r2.returncode == 0 and kernel_reader["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
