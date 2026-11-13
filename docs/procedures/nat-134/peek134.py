#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-134: the read-only SuperSpeed prerequisite probe (NAT-131 section 5), host side.

TABLE is the single list of registers; engine/usbmon.c carries the same addresses in the same order (peek_addr[], checked by
test_nat134.py). The host reads them one PEEK at a time, in table order, and writes each reply to the journal (fsync) before
the next request. Groups are read from known-clocked to unknown; a group with a `gate` is read only if the CMU gate register
read earlier in the run does not show the clock manually off (MANUAL bit 20 = 1 and CGVAL bit 21 = 0: cmucal-sfr.c SFR_ACCESS
rows for the gates, NAT-131 pin 41748417). A skipped group is recorded as skipped, never read.

Nothing is written by a PEEK. The engine has no arbitrary-address form.
"""
import json
import os
import struct

PEEK_REQ = 0x05
PEEK_KEY = 0x5045
PEEK_FORMAT = "<4sHHII"
PEEK_SIZE = struct.calcsize(PEEK_FORMAT)
MAGIC = b"S24P"

# (address, group, name)
TABLE = [
    # 1 PMU, always on
    (0x1286061C, "pmu", "PMU USB2 PHY isolation (+0x61c)"),
    (0x12860620, "pmu", "PMU USBDP PHY isolation (+0x620)"),
    # 2 DWC3, clocked while the HS link runs
    (0x1790C120, "dwc3", "GSNPSID"),
    (0x1790C1A0, "dwc3", "VER_NUMBER"),
    (0x1790C1A4, "dwc3", "VER_TYPE"),
    (0x1790C14C, "dwc3", "GHWPARAMS3"),
    (0x1790C2C0, "dwc3", "GUSB3PIPECTL0"),
    (0x1790C12C, "dwc3", "GUCTL"),
    (0x1790C11C, "dwc3", "GUCTL1"),
    (0x1790D020, "dwc3", "LSKIPFREQ"),
    (0x1790D024, "dwc3", "LLUCTL0"),
    (0x1790D060, "dwc3", "LCSR_TX_DEEMPH"),
    (0x1790D064, "dwc3", "LCSR_TX_DEEMPH_1"),
    (0x1790D068, "dwc3", "LCSR_TX_DEEMPH_2"),
    (0x1790D06C, "dwc3", "LCSR_TX_DEEMPH_3"),
    (0x1790D800, "dwc3", "BU31RHBDBG"),
    (0x1790C700, "dwc3", "DCFG"),
    (0x1790C70C, "dwc3", "DSTS"),
    # 3 USBCON (HSI0 USB wrapper), clocked: the USB2 ladder writes it
    (0x178A0000, "usbcon", "USBCON VERSION"),
    (0x178A0004, "usbcon", "LINKCTRL"),
    (0x178A000C, "usbcon", "LINK_CLKRST"),
    (0x178A0014, "usbcon", "USBCON +0x14"),
    (0x178A0080, "usbcon", "LTSTATE_HIS"),
    (0x178A0114, "usbcon", "HSP_MISC"),
    # 4 CMU_HSI0 (0x17800000), read by the USB2 ladder already
    (0x17802054, "cmu_hsi0", "GAT EUSB_CTRL_PCLK"),
    (0x17802058, "cmu_hsi0", "GAT USBDPPHY_CTRL_PCLK"),
    (0x1780205C, "cmu_hsi0", "GAT USBDPPHY_TCA_APB_CLK"),
    (0x17802060, "cmu_hsi0", "GAT USBLINK_ACLK"),
    (0x17802064, "cmu_hsi0", "GAT USBSUBCTL_APB_PCLK"),
    (0x17803054, "cmu_hsi0", "QCH USB32DRD S_CTRL"),
    (0x17803058, "cmu_hsi0", "QCH USB32DRD S_EUSBCTL"),
    (0x1780305C, "cmu_hsi0", "QCH USB32DRD S_LINK"),
    (0x17803060, "cmu_hsi0", "QCH USB32DRD S_SUBCTRL"),
    (0x17803064, "cmu_hsi0", "QCH USB32DRD S_TCA"),
    (0x17807064, "cmu_hsi0", "DBG_NFO QCH S_TCA"),
    # 5 USBDP PHY control (0x178d0000): plain reads only, no CR-port access
    (0x178D0000, "usbdp", "RST_CTRL"),
    (0x178D0004, "usbdp", "CR_PARA_CON0"),
    (0x178D0008, "usbdp", "CR_PARA_CON1"),
    (0x178D000C, "usbdp", "CR_PARA_CON2"),
    (0x178D0100, "usbdp", "PHY_CONFIG0"),
    (0x178D0108, "usbdp", "PHY_CONFIG2"),
    (0x178D0110, "usbdp", "PHY_SRAM_CON"),
    (0x178D016C, "usbdp", "TCA_CONFIG"),
    (0x178D0234, "usbdp", "DP_CONFIG12"),
    (0x178D0238, "usbdp", "DP_CONFIG13"),
    # 6 TCA (0x178e0000)
] + [(0x178E0000 + o, "tca", "TCA +0x%02x" % o) for o in range(0, 0x38, 4)] + [
    (0x178E00FC, "tca", "TCA INFO"),
    # 7 CMU_PERIC2 (0x11800000): the GPIO block's clock
    (0x11802054, "cmu_peric2", "GAT GPIO_PERIC2_PCLK"),
    (0x11803040, "cmu_peric2", "QCH GPIO_PERIC2"),
    # 8 GPIO PERIC2, bank GPC7 (0x118301a0): the orientation pin GPC7_1, last
    (0x118301A0, "gpio", "GPC7 CON"),
    (0x118301A4, "gpio", "GPC7 DAT"),
]

# group -> table address of the CMU gate whose value decides whether the group is read
GATES = {"usbdp": 0x17802058, "tca": 0x1780205C, "gpio": 0x11802054}
GROUP_ORDER = ["pmu", "dwc3", "usbcon", "cmu_hsi0", "usbdp", "tca", "cmu_peric2", "gpio"]


def manually_gated(value):
    """CLK_CON_GAT_*: MANUAL (bit 20) = 1 selects CGVAL (bit 21) as the clock enable; CGVAL 0 then means the clock is off."""
    return bool(value >> 20 & 1) and not (value >> 21 & 1)


def parse(raw):
    if len(raw) < PEEK_SIZE:
        raise ValueError("short PEEK reply: %d bytes" % len(raw))
    magic, index, count, addr, value = struct.unpack_from(PEEK_FORMAT, raw)
    if magic != MAGIC:
        raise ValueError("PEEK reply magic %r" % magic)
    return dict(index=index, count=count, addr=addr, value=value)


def run(peek, journal_path, log=print, stop_after=None):
    """peek(index) -> raw reply bytes (raises on stall/timeout). Returns the result dict; each step is in the journal first."""
    seen = {}
    rows = []
    out = dict(rows=rows, skipped=[], error=None, complete=False)
    fd = os.open(journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)

    def emit(rec):
        os.write(fd, (json.dumps(rec, sort_keys=True) + "\n").encode())
        os.fsync(fd)

    try:
        assert [g for g in GROUP_ORDER if any(t[1] == g for t in TABLE)] == GROUP_ORDER
        assert [t[1] for t in TABLE] == sorted((t[1] for t in TABLE), key=GROUP_ORDER.index), "TABLE not in group order"
        skip = set()
        for index, (addr, group, name) in enumerate(TABLE):
            if stop_after is not None and index >= stop_after:
                break
            if group in skip:
                continue
            gate = GATES.get(group)
            if gate is not None:
                if gate not in seen:
                    skip.add(group)
                    out["skipped"].append(dict(group=group, reason="gate %#x not read" % gate))
                    emit(dict(event="skip", group=group, reason="gate not read", gate=gate))
                    continue
                if manually_gated(seen[gate]):
                    skip.add(group)
                    out["skipped"].append(dict(group=group, reason="gate %#x = %#010x: clock manually off" % (gate, seen[gate])))
                    emit(dict(event="skip", group=group, reason="clock manually off", gate=gate, gate_value=seen[gate]))
                    continue
            emit(dict(event="request", index=index, addr=addr, group=group, name=name))
            try:
                r = parse(peek(index))
            except Exception as exc:  # noqa: BLE001 - the probe records any transport failure and stops
                out["error"] = dict(index=index, addr=addr, name=name, error=str(exc))
                emit(dict(event="error", index=index, addr=addr, error=str(exc)))
                log("PEEK %d %#x %s: %s" % (index, addr, name, exc))
                return out
            if r["index"] != index or r["addr"] != addr or r["count"] != len(TABLE):
                out["error"] = dict(index=index, addr=addr, name=name, error="reply mismatch %r" % r)
                emit(dict(event="error", index=index, addr=addr, error="reply mismatch", reply=r))
                return out
            seen[addr] = r["value"]
            rows.append(dict(index=index, addr=addr, group=group, name=name, value=r["value"]))
            emit(dict(event="value", index=index, addr=addr, value=r["value"]))
            log("PEEK %2d %#010x %-28s = %#010x" % (index, addr, name, r["value"]))
        out["complete"] = stop_after is None
        return out
    finally:
        os.close(fd)


def c_table():
    """The C initialiser engine/usbmon.c must contain (test_nat134 compares)."""
    return "\n".join("\t0x%08xu,\t/* %2d %s: %s */" % (a, i, g, n) for i, (a, g, n) in enumerate(TABLE))


if __name__ == "__main__":
    print(c_table())
