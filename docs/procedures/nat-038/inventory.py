#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-038: regenerate the line counts and licence tags quoted in README.md from the pinned local clones.
Read-only: `git show` and `git rev-parse` in references/. Output: one JSON file in a new directory."""
import argparse, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PINS = {"s24-linux": "417484173abc2c4fa93e738ea82ad9f2e84911b1", "s24-port": "c8860decc62c6d6180e609036d027a2997972420"}
LINUX = """drivers/usb/dwc3/core.c drivers/usb/dwc3/core.h drivers/usb/dwc3/gadget.c drivers/usb/dwc3/ep0.c drivers/usb/dwc3/gadget.h
drivers/usb/dwc3/io.h drivers/usb/dwc3/dwc3-exynos.c drivers/usb/dwc3/dwc3-exynos-otg.c drivers/usb/dwc3/core-exynos.h
drivers/phy/samsung/phy-exynos-usbdrd-eusb.c drivers/phy/samsung/phy-exynos-eusb.c drivers/phy/samsung/eusb-phy-reg.h
drivers/phy/samsung/eusb-con-reg.h drivers/phy/samsung/phy-exynos-snps-usbdp.c drivers/phy/samsung/snps-usbdp-ram-code.h
drivers/phy/common/repeater_core.c drivers/phy/ti/tusb2e11/tusb2e11_repeater.c drivers/phy/nxp/ptn3222/ptn3222_repeater.c
arch/arm64/boot/dts/exynos/s5e9945-usb.dtsi""".split()
SWEET_FILES = ["0072-sweet-usb-probe.patch", "0073-sweet-usb-device-ep0.patch", "0074-sweet-usb-vbus-override.patch", "0075-sweet-usb-ecm.patch",
               "0076-sweet-usb-rx-mbuf.patch", "0077-sweet-usb-live-log.patch", "0081-sweet-usb-link-state.patch"]


def git_show(repo, rev, path):
    return subprocess.run(["git", "-C", str(ROOT / "references" / repo), "show", f"{rev}:{path}"], capture_output=True, check=True).stdout


def head(repo):
    return subprocess.run(["git", "-C", str(ROOT / "references" / repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    for name, pin in PINS.items():
        assert head(name) == pin, (name, head(name))
    rows = []
    for p in LINUX:
        data = git_show("s24-linux", PINS["s24-linux"], p)
        text = data.decode(errors="replace")
        m = re.search(r"SPDX-License-Identifier:\s*([^\n*]+?)\s*(\*/)?\n", text[:600])
        lic = m.group(1).strip() if m else ("GPL (header text)" if "General Public License" in text[:1500] else "unknown")
        rows.append(dict(path=p, lines=data.count(b"\n"), license=lic))
    for p in SWEET_FILES:
        data = git_show("s24-port", PINS["s24-port"], "xnu/legacy-sweet-patches/" + p)
        rows.append(dict(path="s24-port:xnu/legacy-sweet-patches/" + p, lines=data.count(b"\n"), license="patch (README: probe/loader GPL-2.0-only; XNU patch terms follow Apple's)"))
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / "inventory.json").write_text(json.dumps(dict(pins=PINS, files=rows), indent=1) + "\n")
    print(json.dumps({r["path"]: r["lines"] for r in rows}, indent=0))


if __name__ == "__main__":
    sys.exit(main())
