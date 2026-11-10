#!/usr/bin/env python3
"""Sanitized display-pipeline facts from a runtime FDT (UI-007).

Reports only SoC structure: DECON/DPP/DSIM/SysMMU node paths, compatibles, reg/reg-names, status,
dpp/decon/dsim ids and a few scalar mode properties, the iommus target of each DMA node, the presence
(not the value) of boot-framebuffer handover properties, and whether any /memory or /reserved-memory
range covers the bootloader framebuffer base. No bootargs, serials or other values are emitted.

  dpu_dt_facts.py DTB [--json OUT] [--fb-base 0xfa200000]

Uses parse() from tools/verify/fdt_facts.py (NAT-005) without modifying it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools" / "verify"))
from fdt_facts import parse, regs  # noqa: E402

SCALARS = ("dpp,id", "dpuf,id", "port", "attr", "decon,id", "dsim,id", "op_mode", "trig_mode",
           "out_type", "max_win", "vmid_mask")
PRESENCE = ("memory-region", "lk-fb-win-id", "iommus")


def _phandles(root):
    table = {}
    for node in root.walk():
        ph = node.u32("phandle")
        if ph is not None and not node.path.startswith("/__"):
            table[ph] = node
    return table


def _describe(node, phandles):
    out = {"path": node.path, "compatible": node.strings("compatible"),
           "status": (node.strings("status") or ["okay"])[0],
           "reg": [{"name": name, "base": f"{a:#x}", "size": f"{s:#x}"}
                   for (a, s), name in zip(regs(node), node.strings("reg-names") + [None] * 64)]}
    for key in SCALARS:
        if key in node.props and len(node.props[key]) == 4:
            out[key] = node.u32(key)
    for key in PRESENCE:
        out["has_" + key.replace("-", "_").replace(",", "_")] = key in node.props
    if "port-name" in node.props:
        out["port_name"] = node.strings("port-name")
    io = node.props.get("iommus", b"")
    if io:
        targets = [phandles.get(struct.unpack_from(">I", io, i)[0]) for i in range(0, len(io) - 3, 4)]
        out["iommus"] = [t.path if t is not None else None for t in targets]
    return out


def facts(blob: bytes, fb_base: int) -> dict:
    root = parse(blob)
    phandles = _phandles(root)
    nodes = [n for n in root.walk() if not n.path.startswith("/__")]
    pick = lambda words: [n for n in nodes if set(words) & set(n.strings("compatible"))]
    decons = sorted(pick(["samsung,exynos-decon"]), key=lambda n: n.u32("decon,id", 99))
    dpps = sorted(pick(["samsung,exynos-dpp", "samsung,exynos-writeback"]), key=lambda n: n.u32("dpp,id", 99))
    dsims = sorted(pick(["samsung,exynos-dsim"]), key=lambda n: n.u32("dsim,id", 99))
    mmu_targets = {p for n in decons + dpps + dsims for p in _describe(n, phandles).get("iommus", []) if p}
    mmus = [n for n in nodes if n.path in mmu_targets]

    covering = []
    for n in nodes:
        is_mem = n.parent is root and n.name.split("@")[0] == "memory"
        is_rsv = n.parent is not None and n.parent.name == "reserved-memory"
        if not (is_mem or is_rsv):
            continue
        for a, s in regs(n):
            if a <= fb_base < a + s:
                covering.append({"path": n.path, "kind": "memory" if is_mem else "reserved-memory",
                                 "base": f"{a:#x}", "size": f"{s:#x}", "no_map": "no-map" in n.props})

    channels = {}
    for n in dpps:
        if "samsung,exynos-dpp" not in n.strings("compatible") or n.u32("dpp,id") is None:
            continue
        names = n.strings("reg-names")
        if "dma" in names:
            channels[str(n.u32("dpp,id"))] = f"{regs(n)[names.index('dma')][0]:#x}"

    return {
        "schema": "ui-007-dpu-dt-facts-1",
        "source": "runtime FDT (/sys/firmware/fdt) copied in NAT-005, normal Android boot, 2026-11-10",
        "fdt_sha256": hashlib.sha256(blob).hexdigest(),
        "decon": [_describe(n, phandles) for n in decons],
        "dpp": [_describe(n, phandles) for n in dpps],
        "dsim": [_describe(n, phandles) for n in dsims],
        "sysmmu": [_describe(n, phandles) for n in mmus],
        "dpp_dma_by_channel": channels,
        "boot_framebuffer": {"base": f"{fb_base:#x}", "covered_by": covering},
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dtb", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--fb-base", type=lambda s: int(s, 0), default=0xFA200000)
    args = p.parse_args(argv)
    out = json.dumps(facts(args.dtb.read_bytes(), args.fb_base), indent=2) + "\n"
    if args.json:
        args.json.write_text(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
