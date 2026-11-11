#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-039: read-only inventory of the live USB stack of the running Android (SM-S921B / e1s), through ADB and `su`.

    capture.py --out artifacts/nat-039/capture-001            # raw captures (kept local, not committed)

Every command is a read: dmesg/proc/sysfs/debugfs reads, `ls`, `grep`, `cat`. Nothing is written to any node, no property or setting
is changed, no service is started. The command list is checked against a deny-list before anything runs (`assert_read_only`); the
checks are a safety net, the reviewer's reading of COMMANDS is the real control.

The raw output may contain device identifiers; it is stored only under artifacts/ (git-ignored). `sanitize.py` makes the committed
extract. Evidence kind: android-userland (a measurement on this S24, read-only)."""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Output redirections that cannot write a file; everything else containing ">" is refused.
HARMLESS_REDIRECT = re.compile(r"2>&1|2>/dev/null")
DENY = re.compile(r">|\btee\b|\bsetprop\b|\bsettings\s+(put|delete)\b|\bsvc\b|\bmount\b|\bumount\b|\binsmod\b|\brmmod\b|\bmodprobe\b|\bdd\b|\brm\b|"
                  r"\bmv\b|\bcp\b|\bchmod\b|\bchown\b|\bkill\b|\breboot\b|\bam\b|\bpm\b|\bcmd\b|\bstart\b|\bstop\b|\bsed\s+-i\b|"
                  r"-exec\b|-delete\b|-fprint|\bip\b|\bifconfig\b|\bmagisk\b|\bresetprop\b|\bbusybox\b|(?:ba|z|k|da)?sh\s+-c\b|\bperl|\bpython|\beval\b|\bexec\b|\bxargs\b|\bsource\b|\bdevmem\b|\bsvc\b|\bsetenforce\b|\bsetsid\b|\bnohup\b")

# Device-tree property dump: hex of the first 192 bytes, then the same bytes as printable text (NUL -> space). Reads only.
DTP = ('dtp() { for p in "$1"/*; do [ -f "$p" ] || continue; b=$(basename "$p"); '
       'echo "$b: $(head -c 320 "$p" | od -An -tx1 -v | tr -s " \\n" " ") | $(head -c 320 "$p" | tr "\\000" " " | tr -c "[:print:]" ".")"; done; }; ')

# (name, shell command run as root). Each is a read; pipes into grep/sed/head/sort/od/tr only.
COMMANDS = [
    ("identity", "getprop ro.product.model; getprop ro.product.device; getprop ro.build.PDA; getprop sys.boot_completed; getprop sys.usb.state; getprop sys.usb.config; uname -r"),
    ("selinux", "getenforce"),
    ("dmesg-usb", "dmesg | grep -iE 'dwc3|usbdrd|eusb|usbdp|repeater|tusb2e11|ptn3222|hsi0|usb[0-9]*_|udc|exynos-usb|xhci|typec|phy-exynos|usb phy|usb_phy' | head -300"),
    ("dmesg-count", "dmesg | wc -l"),
    ("iomem-hsi0", "grep -E '^1[78][0-9a-f]{6}-' /proc/iomem | head -120"),
    ("iomem-pmu", "grep -E '^1286[0-9a-f]{4}-' /proc/iomem | head -20"),
    ("iomem-cmu-top", "grep -E '^22b2[0-9a-f]{4}-' /proc/iomem | head -20"),
    ("iomem-hsi2c34", "grep -E '^110b[0-9a-f]{4}-' /proc/iomem | head -20"),
    ("platform-devices", "ls /sys/bus/platform/devices | grep -iE 'usb|dwc3|eusb|hsi0|phy|typec|udc' | head -80"),
    ("platform-drivers", "ls /sys/bus/platform/drivers | grep -iE 'usb|dwc3|eusb|phy|typec' | head -60"),
    ("udc-list", "ls -l /sys/class/udc"),
    ("udc-state", "for d in /sys/class/udc/*; do echo \"== $d\"; for f in state current_speed maximum_speed is_a_peripheral is_otg function; do [ -r \"$d/$f\" ] && echo \"$f: $(cat \"$d/$f\" 2>&1)\"; done; done"),
    ("usb-gadget", "ls /config/usb_gadget 2>&1 | head; for g in /config/usb_gadget/*; do echo \"== $g\"; cat \"$g/UDC\" 2>&1; cat \"$g/idVendor\" \"$g/idProduct\" 2>&1; ls \"$g/functions\" 2>&1; done"),
    ("debugfs-usb-dirs", "ls /sys/kernel/debug/usb 2>&1 | head -40"),
    ("debugfs-regdump-find", "find /sys/kernel/debug -maxdepth 4 \\( -iname 'regdump' -o -iname '*dwc3*' -o -iname '*usbdrd*' -o -iname '*eusb*' \\) 2>/dev/null | head -40"),
    ("clk-hsi0", "grep -iE 'hsi0|usb|eusb|usbdp|dwc3' /sys/kernel/debug/clk/clk_summary 2>&1 | head -120"),
    ("clk-summary-header", "head -3 /sys/kernel/debug/clk/clk_summary 2>&1"),
    ("regulator-usb", "grep -iE 'usb|eusb|usbdp|hsi0|ldo.*(0p8|1p2|1p8)' /sys/kernel/debug/regulator/regulator_summary 2>&1 | head -80"),
    ("regulator-summary-header", "head -3 /sys/kernel/debug/regulator/regulator_summary 2>&1"),
    ("genpd-hsi0", "grep -iE 'hsi0|usb' /sys/kernel/debug/pm_genpd/pm_genpd_summary 2>&1 | head -40"),
    ("pmdomain-find", "ls /sys/kernel/debug/pm_genpd 2>&1 | head -40"),
    ("i2c-devices", "ls /sys/bus/i2c/devices | head -80"),
    ("i2c-repeater-names", "for d in /sys/bus/i2c/devices/*; do n=$(cat \"$d/name\" 2>/dev/null); case \"$n\" in *tusb*|*ptn*|*repeater*|*eusb*|*usb*) echo \"$d $n\";; esac; done"),
    ("i2c-adapter-hsi2c34", "for d in /sys/bus/i2c/devices/i2c-*; do n=$(cat \"$d/name\" 2>/dev/null); echo \"$d $n\"; done | grep -iE '110b0000|hsi2c' | head -20"),
    ("dt-usb-nodes", "ls /proc/device-tree 2>&1 | head -5; find /sys/firmware/devicetree/base -maxdepth 4 \\( -iname '*usb*' -o -iname '*dwc3*' -o -iname '*eusb*' \\) 2>/dev/null | head -60"),
    ("dmesg-head", "dmesg | head -2; dmesg | tail -1"),
    ("interrupts-usb", "grep -iE 'dwc3|usb|eusb' /proc/interrupts | head -20"),
    ("mounts-debugfs", "grep -E ' debugfs ' /proc/mounts; ls /sys/kernel/debug 2>&1 | head -3"),
    ("dt-find-support", "find /sys/firmware/devicetree/base -maxdepth 3 \\( -iname '*ptn3222*' -o -iname '*pd_hsi0*' -o -iname '*sysreg_hsi0*' -o -iname 'cmu*' -o -iname 'clock-controller*' -o -iname 'hsi2c@110B0000*' \\) 2>/dev/null | head -40"),
    ("dt-usb-top", DTP + "dtp /sys/firmware/devicetree/base/usb@17900000"),
    ("dt-dwc3", DTP + "dtp /sys/firmware/devicetree/base/usb@17900000/dwc3"),
    ("dt-phy", DTP + "dtp /sys/firmware/devicetree/base/phy@178A0000"),
    ("dt-hsi2c", DTP + "dtp /sys/firmware/devicetree/base/hsi2c@110B0000; for n in /sys/firmware/devicetree/base/hsi2c@110B0000/*/; do echo \"== $n\"; dtp \"$n\"; done"),
    ("i2c-bus9", "readlink -f /sys/bus/i2c/devices/9-003e; readlink -f /sys/bus/i2c/devices/9-004f; readlink -f /sys/bus/i2c/devices/i2c-9; cat /sys/bus/i2c/devices/i2c-9/name"),
    ("regulators", "for d in /sys/class/regulator/regulator.*; do echo \"${d##*/} name=$(cat $d/name 2>&1) state=$(cat $d/state 2>&1) uV=$(cat $d/microvolts 2>&1) users=$(cat $d/num_users 2>&1)\"; done"),
    ("regulator-0", "ls /sys/class/regulator/regulator.0; cat /sys/class/regulator/regulator.0/name"),
    ("runtime-pm", "for d in 12862000.pd_hsi0 17900000.usb 17900000.usb/17900000.dwc3 178a0000.phy 17820000.sysreg_hsi0; do echo \"== $d\"; for f in runtime_status control runtime_active_time runtime_suspended_time; do [ -r /sys/devices/platform/$d/power/$f ] && echo \"$f: $(cat /sys/devices/platform/$d/power/$f 2>&1)\"; done; done"),
    ("usb-sysfs", "cd /sys/devices/platform/17900000.usb; for f in state usb_state id b_sess usb_data_enabled 17900000.dwc3/usb_role 17900000.dwc3/wakeup; do echo \"$f: $(cat $f 2>&1)\"; done"),
    ("clock-controllers", "ls /sys/bus/platform/devices | grep -iE 'clock-controller|cmu' | head -60"),
    ("dt-sysreg-pd-cmu", DTP + "for n in sysreg_hsi0@17820000 pd_hsi0@12862000 clock-controller@22B20000; do echo \"== $n\"; dtp /sys/firmware/devicetree/base/$n; done"),
    ("dt-pmu", DTP + "for n in $(ls /sys/firmware/devicetree/base | grep -iE '^exynos-pmu|^pmu@|^syscon.*12860000|@12860000'); do echo \"== $n\"; dtp /sys/firmware/devicetree/base/$n; done"),
    ("dt-phy-tune-nodes", DTP + "for n in $(find /sys/firmware/devicetree/base/phy@178A0000 -mindepth 1 -type d 2>/dev/null | head -40); do echo \"== $n\"; dtp $n; done"),
    ("dt-repeater-tune", DTP + "for n in $(find /sys/firmware/devicetree/base/hsi2c@110B0000 -mindepth 2 -type d 2>/dev/null | head -60); do echo \"== $n\"; dtp $n; done"),
    ("dt-hs-ss-tune-phandles", DTP + "for n in $(find /sys/firmware/devicetree/base -maxdepth 2 -type d \\( -iname '*usb*tune*' -o -iname '*hs_tune*' -o -iname '*ss_tune*' -o -iname 'usb2_tune*' -o -iname 'usb3_tune*' -o -iname '*phy_tune*' \\) 2>/dev/null | grep -v is_sensor | head -20); do echo \"== $n\"; dtp $n; done"),
    ("dt-dma-props", "ls /sys/firmware/devicetree/base/usb@17900000 /sys/firmware/devicetree/base/usb@17900000/dwc3 /sys/firmware/devicetree/base/phy@178A0000 | grep -iE 'dma|iommu|coherent|ranges' ; ls /sys/devices/platform/17900000.usb /sys/devices/platform/17900000.usb/17900000.dwc3 | grep -iE 'iommu|dma'; ls /sys/class/iommu 2>&1 | head -20"),
    ("i2c-repeater-drivers", "ls -l /sys/bus/i2c/devices/9-003e/driver /sys/bus/i2c/devices/9-004f/driver 2>&1; ls /sys/bus/i2c/drivers | grep -iE 'tusb|ptn|repeater'"),
    ("regulator-parents", "for n in 0 38 42 85 93; do echo \"regulator.$n = $(readlink -f /sys/class/regulator/regulator.$n)\"; done"),
    ("logcat-usb-grep", "logcat -b all -d 2>/dev/null | grep -iE 'dwc3|usbdrd|usb3|eusb|usbdp|exynos-usb' | head -40"),
    ("typec", "ls /sys/class/typec 2>&1 | head"),
    ("power-supply-usb", "for d in /sys/class/power_supply/usb /sys/class/power_supply/otg; do [ -d \"$d\" ] && { echo \"== $d\"; cat \"$d/online\" \"$d/type\" 2>&1; }; done"),
    ("devfreq-none", "ls /sys/class/devfreq | head -20"),
]


def assert_read_only(commands=None):
    # looked up at call time: a default argument would bind the list that existed at import, not the one main() runs
    for name, cmd in (COMMANDS if commands is None else commands):
        m = DENY.search(HARMLESS_REDIRECT.sub("", cmd))
        if m:
            raise SystemExit("refusing: command %r matches the deny-list at %r" % (name, m.group(0)))


def adb(args, timeout):
    r = subprocess.run(["adb", *args], capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    assert_read_only(COMMANDS)
    a.out.mkdir(parents=True, exist_ok=False)
    rc, out, _ = adb(["get-state"], 15)
    if rc != 0 or out.strip() != "device":
        raise SystemExit("no adb device (get-state: %r)" % out)
    rows = []
    for name, cmd in COMMANDS:
        t = time.time()
        # the whole command is one argument to `su -c`; the device-side shell is not given anything else
        rc, so, se = adb(["shell", "su", "-c", "'%s'" % cmd.replace("'", "'\\''")], 60)
        (a.out / ("%s.txt" % name)).write_text(so)
        rows.append(dict(name=name, command=cmd, exit_code=rc, bytes=len(so.encode()), stderr=se.strip()[:300], seconds=round(time.time() - t, 2)))
    (a.out / "index.json").write_text(json.dumps(dict(at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), commands=rows), indent=1) + "\n")
    print(json.dumps([(r["name"], r["exit_code"], r["bytes"]) for r in rows]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
