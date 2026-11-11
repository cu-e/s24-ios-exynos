#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-051: read the regulator, pm_genpd and clock summaries of the running Android through a documented, reverted debugfs mount.

    capture.py --out artifacts/nat-051/capture-001

The only state change on the phone is `mount -t debugfs none /sys/kernel/debug`, undone by `umount /sys/kernel/debug` in the same
run (try/finally), and verified from /proc/mounts afterwards. The mount is read-only in effect: only the three summary files named in
the task are read, clk_summary last and under `timeout 20`. No regdump, no gpio file, no write to a debugfs node, no property or
setting is changed. Evidence kind: android-userland. Raw output stays under artifacts/ (git-ignored); sanitize.py makes the extract.

The command lists below are the specification. `assert_plan` checks them before the first adb call: only these verbs may reach the
device, and mount/umount appear exactly once each."""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DEBUGFS = "/sys/kernel/debug"
BEFORE = [
    ("identity", "getprop ro.product.model; getprop ro.product.device; getprop ro.build.PDA; getprop sys.boot_completed; getprop sys.usb.config; uname -r"),
    ("selinux-before", "getenforce"),
    ("mounts-before", "grep -e debugfs -e tracefs /proc/mounts; echo rc=$?"),
    ("debugfs-dir-before", "ls " + DEBUGFS + " | head -3; echo n=$(ls " + DEBUGFS + " | wc -l)"),
    ("filesystems", "grep debugfs /proc/filesystems"),
]
MOUNT = ("mount", "mount -t debugfs none " + DEBUGFS)
READS = [  # clk_summary last: rate recalculation of prepared clocks may read CMU registers
    ("regulator-summary", "cat " + DEBUGFS + "/regulator/regulator_summary"),
    ("pm-genpd-summary", "cat " + DEBUGFS + "/pm_genpd/pm_genpd_summary"),
    ("clk-summary", "timeout 20 cat " + DEBUGFS + "/clk/clk_summary"),
]
UMOUNT = ("umount", "umount " + DEBUGFS)
AFTER = [
    ("mounts-after", "grep -e debugfs -e tracefs /proc/mounts; echo rc=$?"),
    ("debugfs-dir-after", "echo n=$(ls " + DEBUGFS + " | wc -l)"),
    ("selinux-after", "getenforce"),
    ("usb-config-after", "getprop sys.usb.config; getprop sys.boot_completed"),
]

# Verbs a command in this plan may start with (after `;`/`&&` splitting). Anything else is refused before adb is touched.
ALLOWED_VERB = re.compile(r"^(getprop|uname|getenforce|grep|ls|echo|cat|timeout 20 cat|mount -t debugfs none /sys/kernel/debug|umount /sys/kernel/debug)\b")
FORBIDDEN = re.compile(r"[>]|\btee\b|\bsetprop\b|\bsettings\b|\bdd\b|\brm\b|\bmv\b|\bcp\b|\bchmod\b|\bkill\b|\breboot\b|\bregdump\b|\bgpio\b|\bdevmem\b|\binsmod\b")


def assert_plan():
    mounts = umounts = 0
    for name, cmd in BEFORE + [MOUNT] + READS + [UMOUNT] + AFTER:
        stripped = re.sub(r"\$\([^)]*\)", "", cmd)          # command substitutions are only `ls | wc -l` counters
        for part in re.split(r";|\|\|?|&&", stripped):
            part = part.strip()
            if not part or part.startswith("rc=") or part.startswith("n="):
                continue
            assert ALLOWED_VERB.match(part) or re.match(r"^(head|wc|grep)\b", part) , (name, part)
        assert not FORBIDDEN.search(cmd), (name, cmd)
        mounts += cmd.startswith("mount ")
        umounts += cmd.startswith("umount ")
    assert mounts == 1 and umounts == 1
    for _, cmd in READS:
        assert "regdump" not in cmd and "gpio" not in cmd
    assert READS[-1][0] == "clk-summary" and READS[-1][1].startswith("timeout 20 ")


def adb(args, timeout):
    r = subprocess.run(["adb", *args], capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    assert_plan()
    rc, out, _ = adb(["get-state"], 15)
    if out.strip() != "device":
        raise SystemExit("no adb device (get-state: %r)" % out)
    a.out.mkdir(parents=True, exist_ok=False)
    index = []

    def run(name, cmd, timeout=60):
        t = time.time()
        try:
            rc, so, se = adb(["shell", "su", "-c", "'%s'" % cmd.replace("'", "'\\''")], timeout)
        except subprocess.TimeoutExpired:
            rc, so, se = -1, "", "adb timeout after %ds" % timeout
        (a.out / (name + ".txt")).write_text(so)
        index.append(dict(name=name, command=cmd, exit_code=rc, bytes=len(so.encode()), stderr=se.strip()[:300], seconds=round(time.time() - t, 2)))
        (a.out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
        return rc, so

    for name, cmd in BEFORE:
        run(name, cmd)
    pre = (a.out / "mounts-before.txt").read_text()
    if "debugfs" in pre.split("rc=")[0]:
        raise SystemExit("debugfs is already mounted: nothing to do and nothing to undo; see mounts-before.txt")
    mounted = False
    try:
        rc, _ = run(*MOUNT)
        mounted = rc == 0
        if not mounted:
            raise SystemExit("mount failed (exit %s): stopping, nothing to undo" % rc)
        for name, cmd in READS:
            run(name, cmd, timeout=40 if name == "clk-summary" else 60)
    finally:
        if mounted:
            urc, _ = run(*UMOUNT)
            print("umount exit", urc)
    for name, cmd in AFTER:
        run(name, cmd)
    print(json.dumps([(i["name"], i["exit_code"], i["bytes"]) for i in index]))


if __name__ == "__main__":
    sys.exit(main())
