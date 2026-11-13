#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-148: the kernel's own ml_parse_cpu_topology() on the NAT-035 host model, with a ten-CPU /cpus (host model only).

NAT-146 stopped on the phone between loader checkpoints 35 and 12, i.e. inside ml_parse_cpu_topology(). This runs that code of the
NAT-022 payload kernel (the NAT-035 model kernel; same HackiOS ml_parse_cpu_topology/ml_is_boot_cpu as the NAT-143 kernel, source
STR-014 derive-001) from a checkpoint-35 stop with the device tree replaced:

  baseline   the model's own loader-patched ADT (cpu0 only, reg 0), cmdline with cpus=1   -- expected: checkpoint 12, 1 cpu
  running    cpu1..cpu9 added by NAT-145's make_adt145.add_cpus (every node state "running"), cpus=1 removed
  waiting    make_adt148.add_cpus (the build's function: state "waiting" on cpu1..cpu9), cpus=1 removed

At the checkpoint-35 stop the kernel has already copied boot_args (const_boot_args) and initialised SecureDT; the replacement
ADT is written at the original ADT's PA (it may run into the old boot_args page, which nothing reads after the copy; the model
maps it up to topOfKernelData), _DTSize/_DTEnd are set to its length, and "cpus=1" in const_boot_args' command line is blanked.
The run then resumes to checkpoint 12 and stops early at _Assert or _panic.

    artifacts/nat-065/venv/bin/python -B docs/procedures/nat-148/model_topology.py [--json OUT]
"""
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "docs/procedures/nat-035"))
sys.path.insert(0, str(ROOT / "docs/procedures/nat-145"))
import cresume as cr  # noqa: E402
import make_adt145 as m145  # noqa: E402
sys.path.insert(0, str(HERE))
import make_adt148 as m148  # noqa: E402

LIMIT = 3000000


def cstr(sim, va, n=200):
    b = sim.read_pa(sim.pa_of_kva(va), n)
    return b.split(b"\0")[0].decode("latin1", "replace")


def topology(sim, img):
    t = img.vals["_topology_info"]
    num = sim.read(t + 4, 4) & 0xFFFFFFFF
    cpus = sim.read(t + 0x18, 8)
    boot = sim.read(t + 0x28, 8)
    rows = []
    for i in range(min(num, 10)):
        e = cpus + 0x78 * i
        rows.append(dict(cpu_id=sim.read(e, 4) & 0xFFFFFFFF, phys_id=hex(sim.read(e + 4, 4) & 0xFFFFFFFF)))
    return dict(num_cpus=num, boot_cpu_index=(boot - cpus) // 0x78 if boot else None, cpus=rows)


def run(variant):
    img = cr.a5.Image()
    sim, stops, kttbr0 = cr.chain(img, [35], adt_reg=0)
    assert sim.x[3] == 35, sim.x[3]
    a = cr.a5.analysis()
    adt = m145._adt()
    rec = dict(variant=variant)
    if variant != "baseline":
        raw = bytes(sim.adt_bytes)
        _, end = adt.parse(raw)          # the payload ADT is padded after its last node
        assert not any(raw[end:]), "non-zero bytes after the ADT"
        blob, srec = (m148.add_cpus if variant == "waiting" else m145.add_cpus)(raw[:end], adt)
        rec["input_adt"] = dict(bytes=end, padded=len(raw))
        room = sim.ba_pa + 0x4000 - sim.adt_pa
        assert len(blob) <= room, (len(blob), room)
        root_va = sim.read(img.vals["_DTRootNode"], 8)
        assert root_va == sim.p.virt_base + (sim.adt_pa - sim.base), hex(root_va)
        sim.write_pa(sim.adt_pa, blob)
        sim.write(img.vals["_DTSize"], 8, len(blob))
        sim.write(img.vals["_DTEnd"], 8, root_va + len(blob))
        cba = sim.pa_of_kva(img.vals["_const_boot_args"]) + cr.li.BA["CommandLine"]
        line = sim.read_pa(cba, 608)
        i = line.index(b"cpus=1")
        sim.write_pa(cba + i, b" " * 6)
        rec.update(adt_bytes=len(blob), adt_cpus=srec["cpus"], cmdline=sim.read_pa(cba, 608).split(b"\0")[0].decode())
    cr.c_resume(sim, a, img, cr.stub_save(sim), kttbr0, 12)
    stops_at = {cr.a5.STUB: "checkpoint", img.vals["_Assert"]: "_Assert"}
    if "_panic" in img.vals:
        stops_at[img.vals["_panic"]] = "_panic"
    sim.run(stop_pcs=set(stops_at), limit=sim.steps + LIMIT)
    rec["stopped_at"] = stops_at.get(sim.pc, hex(sim.pc))
    if rec["stopped_at"] == "checkpoint":
        rec["checkpoint"] = sim.x[3]
    if rec["stopped_at"] == "_Assert":
        # _Assert(const char *file, int line, const char *expression)
        rec["assert"] = dict(file=cstr(sim, sim.x[0]), line=sim.x[1] & 0xFFFFFFFF, expression=cstr(sim, sim.x[2]))
        rec["caller"] = hex(sim.x[30])
    rec["topology"] = topology(sim, img)
    if rec["stopped_at"] == "checkpoint" and variant == "waiting":
        # the rest of the model's reachable chain (NAT-035 CHAIN after 12): no assertion with ten CPUs
        later = []
        for nxt in (40, 41, 42, 43, 44, 13, 14):
            cr.c_resume(sim, a, img, cr.stub_save(sim), kttbr0, nxt)
            sim.run(stop_pcs=set(stops_at), limit=sim.steps + LIMIT)
            got = stops_at.get(sim.pc, hex(sim.pc))
            later.append(sim.x[3] if got == "checkpoint" else got)
            if got != "checkpoint":
                break
        rec["after_12"] = later
        rec["master_cpu"] = sim.read(img.vals["_master_cpu"], 4) & 0xFFFFFFFF if "_master_cpu" in img.vals else None
    return rec


def main():
    out = [run(v) for v in ("baseline", "running", "waiting")]
    text = json.dumps(out, indent=1)
    print(text)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(text + "\n")


if __name__ == "__main__":
    main()
