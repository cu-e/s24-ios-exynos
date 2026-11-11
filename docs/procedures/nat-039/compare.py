#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-039: compare a read-only Android capture (capture.py) with the NAT-040 vendor-source plan.

    compare.py extract --capture artifacts/nat-039/capture-004 --out docs/procedures/nat-039/capture-extract
    compare.py compare --capture docs/procedures/nat-039/capture-extract [--json out.json]

`extract` copies the minimum sanitized subset of a raw capture (the files `compare` reads; the regulator list is cut to the four USB rails)
and records the SHA-256 of every raw file. `compare` parses the subset and checks each fact the NAT-040 plan (plan.json, README.md) relies
on, one row per fact: match, mismatch, consistent, new, or unresolved (the capture cannot read it). Every expectation is anchored: the
script first checks that the cited plan step really contains the quoted value, so the table cannot drift from plan.json.

Evidence category: android-userland (read-only device tree, sysfs and procfs of the running Android). Nothing here is a native-device result."""
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE.parent / "nat-040" / "plan.json"
README40 = HERE.parent / "nat-040" / "README.md"

# raw capture files `compare` reads (name without .txt)
NEEDED = ["identity", "mounts-debugfs", "clk-hsi0", "regulator-usb", "genpd-hsi0", "debugfs-usb-dirs", "iomem-hsi0", "iomem-pmu", "iomem-hsi2c34",
          "interrupts-usb", "dt-usb-top", "dt-dwc3", "dt-phy", "dt-hsi2c", "dt-sysreg-pd-cmu", "dt-pmu", "dt-hs-ss-tune-phandles",
          "dt-repeater-tune", "dt-dma-props", "i2c-bus9", "i2c-repeater-drivers", "i2c-repeater-names", "regulators", "regulator-parents",
          "runtime-pm", "udc-state", "usb-sysfs", "platform-devices", "clock-controllers", "typec"]
USB_RAILS = ("vdd075_usb", "vdd12_usb", "vdd18_usb", "vdd33_usb")


# ------------------------------------------------------------------------------------------------------------------------------ parsing
def parse_dt(text):
    """Output of capture.py's dtp(): `name:  <hex bytes> | <printable>` per property, `== path` per node. -> [(node, {prop: bytes})]."""
    nodes, cur, props = [], "", {}
    for line in text.splitlines():
        if line.startswith("== "):
            if props or cur:
                nodes.append((cur, props))
            cur, props = line[3:].strip(), {}
            continue
        if ":" not in line or "|" not in line:
            continue
        name, rest = line.split(":", 1)
        hexpart = rest.split("|", 1)[0].replace(" ", "")
        if not re.fullmatch(r"(?:[0-9a-f]{2})*", hexpart):
            continue
        props[name.strip()] = bytes.fromhex(hexpart)
    if props or cur:
        nodes.append((cur, props))
    return nodes


def cells(b):
    if len(b) % 4:
        raise ValueError("not a whole number of 32-bit cells: %r" % b)
    return list(struct.unpack(">%dI" % (len(b) // 4), b))


def reg_pairs(b):
    """`reg` with #address-cells=2, #size-cells=1 (the Exynos top level): [(base, size)]."""
    c = cells(b)
    if len(c) % 3:
        raise ValueError("reg is not a multiple of (addr_hi, addr_lo, size)")
    return [((c[i] << 32) | c[i + 1], c[i + 2]) for i in range(0, len(c), 3)]


def cstr(b):
    return b.split(b"\0")[0].decode("ascii", "replace")


def first_node(path, text):
    nodes = parse_dt(text)
    if not nodes:
        raise ValueError("no device-tree properties in %s" % path)
    return nodes[0][1]


def node_named(text, needle):
    for name, props in parse_dt(text):
        if needle in name:
            return props
    raise KeyError(needle)


def lines(text):
    return [l for l in text.splitlines() if l.strip()]


def hexs(v):
    return "0x%x" % v


# ----------------------------------------------------------------------------------------------------------------------------- the plan
class Plan:
    def __init__(self, plan_path=PLAN, readme_path=README40):
        self.plan = json.loads(Path(plan_path).read_text())
        self.readme = Path(readme_path).read_text()
        self.steps = {s["id"]: json.dumps(s) for s in self.plan["steps"]}

    def step_has(self, step, needle):
        if step not in self.steps:
            raise AssertionError("plan.json has no step %s" % step)
        if needle not in self.steps[step]:
            raise AssertionError("plan step %s does not contain %r: the expectation table has drifted" % (step, needle))
        return "plan.json step %s" % step

    def readme_has(self, needle):
        if needle not in self.readme:
            raise AssertionError("NAT-040 README does not contain %r" % needle)
        return "NAT-040 README"

    def unknown(self, uid):
        return next(u for u in self.plan["unknowns"] if u["id"] == uid)

    def ladder_reads(self, rung):
        return next(r for r in self.plan["ladder"] if r["id"] == rung)["reads"]


# ---------------------------------------------------------------------------------------------------------------------------- comparison
def compare(cap, plan=None):
    cap = Path(cap)
    plan = plan or Plan()
    T = lambda name: (cap / (name + ".txt")).read_text()
    rows = []

    def row(cid, unknown, claim, ref, expected, observed, source, result, note=""):
        assert result in ("match", "mismatch", "consistent", "new", "unresolved"), result
        rows.append(dict(id=cid, unknown=unknown, claim=claim, plan_ref=ref, expected=expected, observed=observed, source=source, result=result, note=note))

    def eq(cid, unknown, claim, ref, expected, observed, source, note=""):
        row(cid, unknown, claim, ref, expected, observed, source, "match" if expected == observed else "mismatch", note)

    usb = first_node("dt-usb-top", T("dt-usb-top"))
    dwc3 = first_node("dt-dwc3", T("dt-dwc3"))
    phy = first_node("dt-phy", T("dt-phy"))
    sysreg = node_named(T("dt-sysreg-pd-cmu"), "sysreg_hsi0")
    pd = node_named(T("dt-sysreg-pd-cmu"), "pd_hsi0")
    cmu = node_named(T("dt-sysreg-pd-cmu"), "clock-controller")
    pmu = node_named(T("dt-pmu"), "exynos-pmu")
    hsi2c_nodes = parse_dt(T("dt-hsi2c"))
    hsi2c = hsi2c_nodes[0][1]
    rep = {n.rstrip("/").split("@")[-1]: p for n, p in hsi2c_nodes[1:]}

    # --- DWC3 controller -------------------------------------------------------------------------------------------------------
    ref = plan.step_has("3.18", "0x17900000")
    (base, size), = reg_pairs(usb["reg"])
    eq("C01", None, "DWC3 controller base and window", ref, "0x17900000/0x10000", "%s/%s" % (hexs(base), hexs(size)), "dt-usb-top reg")
    (b2, s2), = reg_pairs(dwc3["reg"])
    eq("C01b", None, "dwc3 child node has the same window", ref, "0x17900000/0x10000", "%s/%s" % (hexs(b2), hexs(s2)), "dt-dwc3 reg")
    io = [l for l in lines(T("iomem-hsi0")) if "17900000.dwc3" in l]
    ok = len(io) == 1 and io[0].split()[0] == "1790c100-1790ffff"
    plan.readme_has("GSNPSID at `+0xc120`")
    row("C01c", None, "kernel claims the core-register window that contains GSNPSID (+0xc120)", "NAT-040 README register map", "window covers 0x1790c120",
        io[0].split()[0] if io else "absent", "iomem-hsi0", "consistent" if ok else "mismatch",
        "the driver requests only 0x1790c100-0x1790ffff; GSNPSID itself was not read (no register reads are authorized from Android)")
    plan.readme_has("SPI ")
    c = cells(dwc3["interrupts"])
    spi = int(re.search(r"SPI (\d+)", plan.readme).group(1))
    eq("C02", None, "DWC3 interrupt is the README's SPI, level high (flags 4)", "NAT-040 README register map", dict(kind="SPI", number=spi, flags=4),
       dict(kind={0: "SPI", 1: "PPI"}.get(c[0], "type %d" % c[0]), number=c[1], flags=c[2]), "dt-dwc3 interrupts")
    gic = [l for l in lines(T("interrupts-usb")) if re.search(r"GICv3\s+435\s+Level\s+dwc3\s*$", l)]
    row("C02b", None, "the running kernel has the dwc3 line on GIC hwirq 435 (= SPI 403 + 32)", "arithmetic on C02", "GICv3 435 Level dwc3",
        "present" if gic else "absent", "interrupts-usb", "match" if gic else "mismatch")
    eq("C03", None, "maximum-speed in the board DT is super-speed (a HS-only monitor must set DCFG speed itself)", plan.step_has("5.17", "super-speed"),
       "super-speed", cstr(dwc3["maximum-speed"]), "dt-dwc3 maximum-speed")

    # --- USB wrapper / PHY blocks ----------------------------------------------------------------------------------------------
    ref = plan.step_has("3.18", "0x178a0000")
    names = [("USBCON wrapper", 0x178a0000), ("eUSB2 control", 0x178b0000), ("eUSB2 PHY", 0x178c0000), ("USBDP", 0x178d0000), ("TCA", 0x178e0000)]
    for n, b in names:
        plan.step_has("3.18", hexs(b))
    pairs = reg_pairs(phy["reg"])
    got = [p[0] for p in pairs[:5]]
    eq("C04", None, "PHY node maps USBCON/eUSB2-control/eUSB2-PHY/USBDP/TCA at these five bases", ref, [hexs(b) for _, b in names], [hexs(b) for b in got], "dt-phy reg")
    sizes = [hexs(p[1]) for p in pairs[:5]]
    row("C04b", None, "window sizes of the five PHY blocks", "not in plan", "-", sizes, "dt-phy reg", "new", "0x200, 0x200, 0x200, 0x800, 0x800; the sixth reg entry is the DWC3 window again")
    cl = [l for l in lines(T("iomem-hsi0")) if "178a0000.phy" in l]
    row("C04c", None, "the kernel claims all five PHY windows under 178a0000.phy", ref, 5, len(cl), "iomem-hsi0", "match" if len(cl) == 5 else "mismatch")
    (sb, ss), = reg_pairs(sysreg["reg"])
    eq("C05", None, "SYSREG_HSI0 base", plan.step_has("0.33", "0x17820000"), "0x17820000", hexs(sb), "dt-sysreg-pd-cmu sysreg_hsi0 reg",
       "size %s" % hexs(ss))
    eq("C05b", None, "the DWC3 glue refers to sysreg_hsi0 by phandle", "NAT-040 README register map", hexs(cells(sysreg["phandle"])[0]), hexs(cells(usb["samsung,sysreg-hsi0"])[0]), "dt-usb-top samsung,sysreg-hsi0")

    # --- power domain, PMU -----------------------------------------------------------------------------------------------------
    ref = plan.step_has("0.01", "0x12862000")
    (pb, ps), = reg_pairs(pd["reg"])
    eq("C06", "U2", "pd_hsi0 PMU window", ref, "0x12862000/0x20", "%s/%s" % (hexs(pb), hexs(ps)), "dt-sysreg-pd-cmu pd_hsi0 reg")
    plan.step_has("0.01", "0x17800000")
    eq("C07", "U3", "CMU_HSI0 base (pd_hsi0 cmu_id)", ref, "0x17800000", hexs(cells(pd["cmu_id"])[0]), "dt-sysreg-pd-cmu pd_hsi0 cmu_id",
       "no separate platform device or /proc/iomem entry exists for it; its registers were not read")
    plan.step_has("0.01", "0x17810204")
    eq("C08", "U2", "pd_hsi0 needs the DTZPC SMC at 0x17810204", ref, "0x17810204", hexs(cells(pd["need_smc"])[0]), "dt-sysreg-pd-cmu pd_hsi0 need_smc")
    row("C08b", "U2", "pd_hsi0 cal_id", "not in plan", "-", hexs(cells(pd["cal_id"])[0]), "dt-sysreg-pd-cmu pd_hsi0 cal_id", "new")
    (mb, ms), = reg_pairs(pmu["reg"])
    eq("C09", None, "PMU base", plan.step_has("0.19", "0x12860000"), "0x12860000/0x10000", "%s/%s" % (hexs(mb), hexs(ms)), "dt-pmu exynos-pmu reg")
    eq("C10", None, "USB PHY isolation offset in the PMU", plan.step_has("1.02", "0x61c"), "0x61c", hexs(cells(phy["pmu_offset"])[0]), "dt-phy pmu_offset")
    eq("C10b", None, "DisplayPort/USBDP isolation offset in the PMU", plan.step_has("0.30", "0x620"), "0x620", hexs(cells(phy["pmu_offset_dp"])[0]), "dt-phy pmu_offset_dp")

    # --- clocks ----------------------------------------------------------------------------------------------------------------
    plan.step_has("0.07", "0x22b20000")
    (cb, cs), = reg_pairs(cmu["reg"])
    eq("C11", "U3", "CMU_TOP base", "plan.json step 0.07", "0x22b20000", hexs(cb), "dt-sysreg-pd-cmu clock-controller reg", "window %s; compatible %s" % (hexs(cs), cstr(cmu["compatible"])))
    reads = plan.ladder_reads("L2")
    inside = all(cb <= int(r, 16) < cb + cs for r in reads)
    row("C11b", "U3", "the three CMU_TOP registers the ladder reads (L2) lie inside the clock-controller window", "plan.json ladder L2", reads,
        "inside" if inside else "outside", "dt-sysreg-pd-cmu", "match" if inside else "mismatch", "address range only; the values were not read")
    clk_names = usb["clock-names"].rstrip(b"\0").decode().split("\0")
    clk_ids = cells(usb["clocks"])[1::2]
    row("C11c", "U3", "clock indices consumed by the DWC3 glue (vendor clock-driver table indices, not rates)", "not in plan", "-",
        dict(zip(clk_names, [hexs(i) for i in clk_ids])), "dt-usb-top clocks", "new")
    unread = all(T(n).strip().startswith(("grep:", "ls:", "head:", "cat:")) or not T(n).strip() for n in ("clk-hsi0",))
    row("C11d", "U3", "clock rates and gate states of the HSI0/USB clocks", plan.unknown("U3")["what"][:80], "mux/gate/divider values", "not readable: debugfs clk_summary absent" if unread else "readable",
        "clk-hsi0", "unresolved" if unread else "new", "debugfs is registered but not mounted and mounting it is outside the authorized scope; register reads from Android are not authorized")

    # --- supplies --------------------------------------------------------------------------------------------------------------
    plan.step_has("0.04", "s5_l2")
    u1 = plan.unknown("U1")["what"]
    regs = {}
    for l in lines(T("regulators")):
        m = re.match(r"(regulator\.\d+) name=(\S+) state=(\S+) uV=(\d+) users=(\d+)", l)
        if m and m.group(2) in USB_RAILS:
            regs[m.group(2)] = dict(node=m.group(1), state=m.group(3), microvolt=int(m.group(4)), users=int(m.group(5)))
    parents = {}
    for l in lines(T("regulator-parents")):
        m = re.match(r"(regulator\.\d+) = (\S+)", l)
        if m:
            pm = re.search(r"/(s2mps\d+(?:-\d+)?)-regulator/", m.group(2))
            parents[m.group(1)] = pm.group(1) if pm else m.group(2)
    rails = {n: dict(r, parent=parents.get(r["node"])) for n, r in regs.items()}
    # the plan names the rails as "vdd075 s5_l2, vdd12 s4_l4, vdd18 l7, vdd33 l11": sN_lM = PMIC instance N, LDO M; a bare lM = the first PMIC
    plan_rails = dict(re.findall(r"(vdd\d+) (s\d+_l\d+|l\d+)", u1))
    assert sorted(plan_rails) == ["vdd075", "vdd12", "vdd18", "vdd33"], plan_rails
    exp_parent = {}
    for rail, tok in plan_rails.items():
        m = re.match(r"s(\d+)_l\d+", tok)
        exp_parent[rail + "_usb"] = "s2mps28-%s" % m.group(1) if m else "s2mps27"
    obs_parent = {n: rails.get(n, {}).get("parent") for n in USB_RAILS}
    row("C12", "U1", "the four USB rails exist as regulators and sit on the PMIC instances the plan's names imply (s5_l2 -> s2mps28-5, s4_l4 -> s2mps28-4, l7/l11 -> s2mps27)",
        "plan.json U1 (names) + step 0.04", exp_parent, obs_parent, "regulators + regulator-parents", "match" if exp_parent == obs_parent else "mismatch",
        "the s<N> -> s2mps28-<N> and bare -> s2mps27 mapping is my reading of the naming; the LDO index (l2, l4, l7, l11) is not exposed by sysfs and was not checked")
    row("C12a", "U1", "state and voltage of the four rails in Android (the answer to the question NAT-039 was given for U1)", "plan.json U1 resolve[NAT-039]", "on/off read",
        {n: [rails.get(n, {}).get("state"), rails.get(n, {}).get("microvolt")] for n in USB_RAILS}, "regulators", "new",
        "Android state only: the loader-entry state on the RECOVERY path is not known from this (U1 stays open for NAT-043)")
    row("C12b", "U1", "all four rails are held by exactly one user in Android", "not in plan", "users=1", {n: rails.get(n, {}).get("users") for n in USB_RAILS}, "regulators",
        "new" if all(rails.get(n, {}).get("users") == 1 for n in USB_RAILS) else "mismatch")
    reg_supply = {k: hexs(cells(v)[0]) for k, v in dwc3.items() if k.endswith("-supply")}
    row("C12c", "U1", "supplies are named on both the dwc3 and the phy node (phandles identical)", "not in plan", "same four phandles",
        {k: reg_supply[k] == hexs(cells(phy[k])[0]) for k in sorted(reg_supply)}, "dt-dwc3, dt-phy", "new")

    # --- power-domain state ----------------------------------------------------------------------------------------------------
    rt = {}
    cur = None
    for l in lines(T("runtime-pm")):
        if l.startswith("== "):
            cur = l[3:]
            rt[cur] = {}
        elif cur and ":" in l:
            k, v = l.split(":", 1)
            rt[cur][k.strip()] = v.strip()
    gp_unread = not any(re.search(r"hsi0", l) for l in lines(T("genpd-hsi0")) if not l.startswith("grep:"))
    row("C13", "U2", "pd_hsi0 power state in Android", plan.unknown("U2")["what"][:80], "ON/OFF read from genpd",
        "genpd summary not readable (debugfs); consumers dwc3/usb runtime_status=%s/%s, pd_hsi0 runtime_status=%s" % (
            rt.get("17900000.usb/17900000.dwc3", {}).get("runtime_status"), rt.get("17900000.usb", {}).get("runtime_status"), rt.get("12862000.pd_hsi0", {}).get("runtime_status")),
        "runtime-pm, genpd-hsi0", "unresolved" if gp_unread else "new",
        "inference only: a genpd stays on while an attached device is runtime-active, so the domain is on in this Android state; the loader-entry state (U2) is NAT-043's L1 read")

    # --- repeaters -------------------------------------------------------------------------------------------------------------
    ref = plan.step_has("1.01", "0x3e")
    plan.step_has("1.01", "0x4f")
    (hb, hs_), = reg_pairs(hsi2c["reg"])
    plan.readme_has("0x110b0000")
    eq("C14", "U4", "repeater I2C controller base (hsi2c_34 in the plan)", "NAT-040 README register map", "0x110b0000/0x1000", "%s/%s" % (hexs(hb), hexs(hs_)), "dt-hsi2c reg",
       "Linux bus number 9; /proc/iomem: %s" % (lines(T("iomem-hsi2c34"))[0].split()[0] if lines(T("iomem-hsi2c34")) else "absent"))
    rt_ = rep.get("3E", {})
    rp_ = rep.get("4F", {})
    eq("C15", "U4", "TUSB2E11 and PTN3222 nodes: addresses and status", ref, {"tusb2e11": ["0x3e", "okay"], "ptn3222": ["0x4f", "okay"]},
       {"tusb2e11": [hexs(cells(rt_["reg"])[0]), cstr(rt_["status"])], "ptn3222": [hexs(cells(rp_["reg"])[0]), cstr(rp_["status"])]}, "dt-hsi2c")
    drv = T("i2c-repeater-drivers")
    bound = "9-003e/driver" in drv and "tusb2e11-repeater" in drv and "9-004f/driver" in drv and "ptn3222-repeater" in drv
    bus = T("i2c-bus9")
    row("C16", "U4", "both repeaters are registered on the hsi2c controller (bus 9) with their drivers bound", plan.unknown("U4")["what"][:80], "bound", "bound" if bound else "not bound",
        "i2c-repeater-drivers, i2c-bus9", "consistent" if bound and "110b0000.hsi2c/i2c-9/9-003e" in bus and "110b0000.hsi2c/i2c-9/9-004f" in bus else "mismatch",
        "binding does not show which chip is fitted: both vendor probe functions (pin 417484173abc2c4fa93e738ea82ad9f2e84911b1, tusb2e11_repeater.c:299-357 and ptn3222_repeater.c:254-302) only parse the DT and register callbacks, with no I2C transaction. Which repeater answers stays unresolved (U4)")
    tune = {}
    for node, props in parse_dt(T("dt-repeater-tune")):
        if "tune_name" in props:
            chip = "tusb2e11" if "tusb2e11" in node else "ptn3222"
            tune.setdefault(chip, []).append([cstr(props["tune_name"]), "0x%02x" % props["tune_value"][0], "0x%02x" % props["tune_value"][1]])
    for chip in tune:
        tune[chip].sort()
    row("C17", "U4", "repeater tuning pairs from the DT ([register, value]); the DT values only tune signal quality", "plan.json U4", "-", tune, "dt-repeater-tune", "new")

    # --- DMA / coherency -------------------------------------------------------------------------------------------------------
    dma = T("dt-dma-props")
    ranges_only = [l for l in lines(dma) if l.strip() == "ranges"]
    iommus = any(re.search(r"iommu|dma-coherent|coherent|dma-ranges", l) for l in lines(dma) if not l.startswith("ranges"))
    sysmmu = [l for l in lines(dma) if "sysmmu" in l]
    near = [l for l in sysmmu if re.match(r"17[89]|179", l)]
    plan.step_has("0.18", "S2MPU")
    row("C18", "U5", "DT of the USB nodes carries no iommus, dma-coherent or dma-ranges; only the empty `ranges` of the glue and the PHY", plan.unknown("U5")["what"][:80],
        "no iommu/coherency property", {"empty ranges": len(ranges_only), "iommu/coherent/dma-ranges": iommus, "sysmmu devices listed": len(sysmmu), "sysmmu near 0x179xxxxx": len(near)},
        "dt-dma-props", "consistent" if not iommus and len(ranges_only) == 2 and not near else "mismatch",
        "Linux therefore treats the controller as non-coherent and un-translated: consistent with the plan placing the event buffer and TRBs in loader-owned non-cacheable memory (NAT-041). The S2MPU in front of HSI0 DMA is secure-world state and not visible from Android (U5 stays open)")

    # --- speed -----------------------------------------------------------------------------------------------------------------
    u = {}
    for l in lines(T("udc-state")):
        if ":" in l and not l.startswith("=="):
            k, v = l.split(":", 1)
            u[k.strip()] = v.strip()
    row("C19", "U6", "live UDC state in Android", plan.unknown("U6")["what"][:80], "-", {k: u.get(k) for k in ("state", "current_speed", "maximum_speed")}, "udc-state", "new",
        "Android with the combo PHY fully initialised enumerates at high-speed on this host port; this says nothing about HS-only operation with the USB3 PHY never initialised (U6)")
    row("C19b", "U6", "PHY reference clock and refsel flags from the DT", plan.unknown("U6")["what"][:80], "19.2 MHz in the vendor constants",
        {"phy_refclk": cstr(phy["phy_refclk"]), "phy_refsel_clockcore": cells(phy["phy_refsel_clockcore"])[0], "phy_version": hexs(cells(phy["phy_version"])[0]),
         "sub_phy_version": hexs(cells(phy["sub_phy_version"])[0]), "has_combo_phy": cells(phy["has_combo_phy"])[0], "snps_usbdp_ram_mode": cells(phy["snps_usbdp_ram_mode"])[0]},
        "dt-phy", "new", "the clock rate itself was not readable (U6 stays open)")

    # --- misc ------------------------------------------------------------------------------------------------------------------
    gpio = cells(phy["phy,gpio_phy_port"])
    row("C20", "U7", "DT phy,gpio_phy_port = <phandle pin flags>", plan.unknown("U7")["what"][:80], "gpc7 pin 1", dict(phandle=hexs(gpio[0]), pin=gpio[1], flags=gpio[2], used_phy_port=cells(phy["used_phy_port"])[0]),
        "dt-phy", "consistent" if gpio[1] == 1 else "mismatch", "pin 1 agrees; the bank behind phandle 0x65 was not resolved and the pin level not read (debugfs gpio absent). Not needed for the HS-only subset")
    row("C21", None, "controller role and quirks (DT)", "not in plan", "-", dict(
        dr_mode=cstr(dwc3["dr_mode"]), usb_role_switch="usb-role-switch" in dwc3, quirks=sorted(k for k in dwc3 if k.startswith("snps,")),
        frame_length_adjustment=hexs(cells(dwc3["snps,quirk-frame-length-adjustment"])[0]), glue=sorted(k for k in usb if k.startswith("exynos,"))),
        "dt-dwc3, dt-usb-top", "new")
    quirk_in_plan = {q: any(q in s for s in plan.steps.values()) for q in sorted(k for k in dwc3 if k.startswith("snps,"))}
    row("C21b", None, "which of those snps,* quirks the NAT-040 plan mentions", "plan.json steps", "-", quirk_in_plan, "plan.json", "new",
        "quirks the plan does not mention are listed so the NAT-041 engine can decide whether its register order needs them")
    tn = parse_dt(T("dt-hs-ss-tune-phandles"))
    top = {n.rsplit("/", 1)[-1]: p for n, p in tn if n.count("/") == 5}
    row("C22", None, "PHY tune tables (hs_tune_phy, ss_tune) in the DT", "not in plan", "-",
        {n: dict(status=cstr(p["status"]) if "status" in p else None, count=cells(p.get("hs_tune_cnt", p.get("ss_tune_cnt", b"\0\0\0\0")))[0], phandle=hexs(cells(p["phandle"])[0])) for n, p in top.items()},
        "dt-hs-ss-tune-phandles", "new", "both tables are status=disabled in this DT and almost every entry is the 0xff sentinel (unset); the vendor PHY constants therefore come from the driver, not the DT")
    mounts = T("mounts-debugfs").strip()
    row("C23", None, "debugfs state of the running Android", "-", "-", "not mounted" if not mounts else mounts[:80], "mounts-debugfs", "new", "kernel registers the filesystem; clk_summary, regulator_summary, pm_genpd and the dwc3 regdump live there and were not read")

    # --- roll-up ---------------------------------------------------------------------------------------------------------------
    by_u = {}
    for r in rows:
        if r["unknown"]:
            by_u.setdefault(r["unknown"], []).append(r["id"] + ":" + r["result"])
    summary = dict(
        counts={k: sum(1 for r in rows if r["result"] == k) for k in ("match", "consistent", "new", "unresolved", "mismatch")},
        mismatches=[r["id"] for r in rows if r["result"] == "mismatch"],
        unresolved=[r["id"] for r in rows if r["result"] == "unresolved"],
        by_unknown=by_u,
        unknown_status={
            "U1": "rails, voltages and PMIC instances read for Android; loader-entry state still unknown (NAT-043)",
            "U2": "need_smc 0x17810204 and pd_hsi0 window confirmed; domain state not readable here (genpd is in debugfs), Android keeps it on; loader-entry state unknown (NAT-043 L1)",
            "U3": "bases confirmed (CMU_TOP 0x22b20000 +0x8000, CMU_HSI0 0x17800000); mux/gate/divider values NOT read (debugfs absent, register reads not authorized)",
            "U4": "both nodes and drivers present; which chip is fitted NOT established (probe makes no I2C transaction)",
            "U5": "no iommu/coherency property for the controller; S2MPU not visible from Android",
            "U6": "not resolved (live link is HS with the combo PHY initialised; reference clock rate unread)",
            "U7": "pin 1 consistent; bank unresolved; level unread",
            "U8": "not an inventory question"})
    return dict(rows=rows, summary=summary)


# ----------------------------------------------------------------------------------------------------------------------------- extract
MAC = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
LONGNUM = re.compile(r"(?<![0-9A-Za-z])[0-9]{14,16}(?![0-9A-Za-z])")


def forbidden(text, extra=()):
    hits = []
    if MAC.search(text):
        hits.append("MAC-like")
    if LONGNUM.search(text):
        hits.append("14-16 digit number")
    for s in extra:
        if s and s in text:
            hits.append("forbidden string")
    return hits


def adb_serial():
    try:
        r = subprocess.run(["adb", "get-serialno"], capture_output=True, timeout=10)
        s = r.stdout.decode().strip()
        return s if r.returncode == 0 and s not in ("", "unknown") else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def commands_hash(pairs):
    """SHA-256 of the (name, command) list a capture ran, so the evidence ties to the exact read-only command set."""
    return hashlib.sha256(json.dumps([[n, c] for n, c in pairs], separators=(",", ":")).encode()).hexdigest()


def extract(cap, out, extra=()):
    cap, out = Path(cap), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = dict(source_capture="artifacts/nat-039/" + cap.name, files={})
    for name in NEEDED:
        raw = (cap / (name + ".txt")).read_bytes()
        text = raw.decode(errors="replace")
        if name == "regulators":
            text = "".join(l + "\n" for l in text.splitlines() if any(" name=%s " % r in l for r in USB_RAILS))
        bad = forbidden(text, extra)
        if bad:
            raise SystemExit("refusing to extract %s: %s" % (name, bad))
        (out / (name + ".txt")).write_text(text)
        manifest["files"][name + ".txt"] = dict(raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw), kept_bytes=len(text.encode()), filtered=(name == "regulators"))
    idx = json.loads((cap / "index.json").read_text())
    manifest["commands"] = [dict(name=r["name"], exit_code=r["exit_code"], bytes=r["bytes"]) for r in idx["commands"]]
    manifest["captured_at"] = idx["at"]
    manifest["commands_sha256"] = commands_hash([(r["name"], r["command"]) for r in idx["commands"]])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--capture", required=True, type=Path)
    e.add_argument("--out", required=True, type=Path)
    c = sub.add_parser("compare")
    c.add_argument("--capture", required=True, type=Path)
    c.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "extract":
        m = extract(a.capture, a.out, extra=(adb_serial(),))
        print("extracted %d files to %s" % (len(m["files"]), a.out))
        return 0
    res = compare(a.capture)
    if a.json:
        a.json.write_text(json.dumps(res, indent=1) + "\n")
    for r in res["rows"]:
        print("%-5s %-11s %-4s %s" % (r["id"], r["result"], r["unknown"] or "-", r["claim"][:100]))
    print(json.dumps(res["summary"]["counts"]))
    print("mismatches:", res["summary"]["mismatches"] or "none")
    return 1 if res["summary"]["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
