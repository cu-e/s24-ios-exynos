#!/usr/bin/env python3
"""NAT-133: Android read-only SuperSpeed facts (U1, U2, U3, U6 of NAT-131) plus the host side of the same link.

    capture133.py --out DIR [--label TEXT]

Every phone command is a read run as `adb shell su -c '<cmd>'` and is checked against the NAT-039 deny-list
(docs/procedures/nat-039/capture.py: assert_read_only) before anything runs. No debugfs, no sysfs writes, no devmem.
dmesg output is filtered to the USB/PHY lines (no complete dump is kept). Host side: sysfs speed of the phone's port.
"""
import argparse
import datetime
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("nat039_capture", HERE.parent / "nat-039" / "capture.py")
C39 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C39)

PHY_RE = ("PHY Boot mode|PMA version|PCS ID|Firmware ID|Timeout on the TCA|Fail usbdp|CR write failed|cr_port_clear|"
          "check_fw_update_done|sram_ext_ld_done|phy port|usbdp|pipe3|USB3|super-speed|SuperSpeed|usb31|force_gen1|usbdrd")

COMMANDS = [
    ("identity", "getprop ro.product.model; getprop ro.product.device; getprop ro.build.PDA; getprop sys.boot_completed; getprop sys.usb.state"),
    ("udc", "for u in /sys/class/udc/*; do echo \"$u current=$(cat $u/current_speed 2>/dev/null) max=$(cat $u/maximum_speed 2>/dev/null) state=$(cat $u/state 2>/dev/null)\"; done"),
    ("phy-driver", "ls /sys/bus/platform/drivers/phy_exynos_usbdrd/ 2>&1"),
    ("phy-port", "for f in /sys/bus/platform/drivers/phy_exynos_usbdrd/*/exynos_usbdrd_phy_port; do echo \"$f=$(cat $f 2>&1)\"; done"),
    ("phy-attrs", "for d in /sys/bus/platform/drivers/phy_exynos_usbdrd/*.phy; do ls $d; done 2>&1 | head -60"),
    ("typec", "for p in /sys/class/typec/*; do echo \"$p orientation=$(cat $p/orientation 2>/dev/null) data_role=$(cat $p/data_role 2>/dev/null) power_role=$(cat $p/power_role 2>/dev/null)\"; done 2>&1"),
    ("dmesg-phy", "dmesg | grep -iE '%s' | tail -200" % PHY_RE),
    ("dmesg-first-ts", "dmesg | head -1 | cut -c1-20"),
    ("regulators", "for r in /sys/class/regulator/regulator.*; do n=$(cat $r/name 2>/dev/null); case \"$n\" in *usb*|*USB*|*vdd075*|*vdd12*|*vdd18*|*vdd33*|*dp*|*DP*) "
                   "echo \"$(basename $r) name=$n state=$(cat $r/state 2>/dev/null) uV=$(cat $r/microvolts 2>/dev/null) users=$(cat $r/num_users 2>/dev/null)\";; esac; done"),
    ("regulator-consumers", "for r in /sys/class/regulator/regulator.*; do for c in $r/*; do case \"$c\" in *17900000*|*178a0000*|*usb*|*phy*) echo \"$(basename $r) $(cat $r/name) consumer $(basename $c)\";; esac; done; done 2>/dev/null | head -60"),
]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def host_side():
    rows = []
    base = Path("/sys/bus/usb/devices")
    for d in sorted(base.iterdir()):
        try:
            vid = (d / "idVendor").read_text().strip()
        except OSError:
            continue
        if vid != "04e8":
            continue
        rows.append(dict(path=d.name, pid=(d / "idProduct").read_text().strip(), speed=(d / "speed").read_text().strip(),
                         version=(d / "version").read_text().strip(), bus=(d / "busnum").read_text().strip(),
                         bus_speed=(base / ("usb" + (d / "busnum").read_text().strip()) / "speed").read_text().strip()))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    C39.assert_read_only(COMMANDS)
    a.out.mkdir(parents=True, exist_ok=False)
    doc = dict(recorded_at=now(), label=a.label, host_before=host_side(), commands=[])
    for name, cmd in COMMANDS:
        rc, out, err = C39.adb(["shell", "su -c '" + cmd.replace("'", "'\\''") + "'"], 60)
        doc["commands"].append(dict(name=name, cmd=cmd, exit_code=rc, stdout=out, stderr=err))
    doc["host_after"] = host_side()
    (a.out / "capture.json").write_text(json.dumps(doc, indent=1) + "\n")
    for c in doc["commands"]:
        print("== %s (rc %d)\n%s" % (c["name"], c["exit_code"], (c["stdout"] + c["stderr"]).rstrip()[:3000]))
    print("host", doc["host_before"], doc["host_after"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
