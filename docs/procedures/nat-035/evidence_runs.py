#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-035: the long host-model runs behind README.md (about five minutes; the unit tests do not repeat them).

  1. as-built:  the loader's ADT patch (boot-CPU `reg` = the whole 32-bit MPIDR_EL1, as loader.c passes it) -> run to
                checkpoint 15, resume with no further stops, and report the first assertion the kernel hits;
  2. masked:    `reg` = MPIDR_EL1 & 0xffff (what ml_get_cpu_number_local() compares) -> the resume chain through all
                checkpoints the model reaches (11 ... 15, 16) against an uninterrupted run to the last one.

Writes artifacts/nat-035/runs.json (gitignored) and prints it. Host only; reads local artifacts."""
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cresume as cr  # noqa: E402

ROOT = HERE.parents[2]
img = cr.a5.Image()
CHAIN = [11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16]
TOPO = 0xfffffff0071c2000      # topology_info: +0x76c num_cpus, +0x770 max_cpu_id, +0x780 cpu table (0x78 bytes each, phys_id at +4)


def cstr(sim, va, n=200):
    out = bytearray()
    for i in range(n):
        try:
            b = sim.read(va + i, 1) & 0xFF
        except Exception:
            break
        if not b:
            break
        out.append(b)
    return bytes(out).decode("latin1")


class Watch(cr.Assumed):
    """Records the first _Assert call."""
    first_assert = None
    seq = []
    _last = None

    def step(self):
        fn = img.name(self.pc).split("+")[0] if self.pc >> 63 else "<phys>"
        if fn != self._last:
            self.seq.append(fn)
            self._last = fn
        if self.pc == img.vals["_Assert"] and self.first_assert is None:
            self.first_assert = dict(file=cstr(self, self.x[0]), line=self.x[1], expr=cstr(self, self.x[2]),
                                     steps=self.steps, recent=[f for f in self.seq[-10:]])
            raise StopIteration
        super().step()


def as_built():
    sim = Watch(names=img)
    a = cr.a5.analysis()
    sim.fill_slot(a["slot_va"], cr.a5.STUB, 15, (cr.a5.BASE - sim.p.virt_base) & cr.M64)
    sim.run(stop_pcs={cr.a5.STUB}, limit=3000000)
    at15 = sim.steps
    cr.c_resume(sim, a, img, cr.stub_save(sim), 0x9e15ae000, 99)
    sim.seq = []
    try:
        while sim.steps < at15 + 200000:
            sim.steps += 1
            sim.step()
    except StopIteration:
        pass
    n = sim.read(TOPO + 0x76c, 4) & 0xFFFFFFFF
    tab = sim.read(TOPO + 0x780, 8)
    phys = [sim.read(tab + i * 0x78 + 4, 4) & 0xFFFFFFFF for i in range(n)]
    return dict(adt_reg=hex(sim.adt_reg), mpidr_el1=hex(sim.sr["mpidr_el1"]), mpidr_low16=hex(sim.sr["mpidr_el1"] & 0xFFFF),
                stop15_steps=at15, topology_num_cpus=n, topology_phys_ids=[hex(p) for p in phys],
                first_assert=sim.first_assert)


def masked():
    ref = cr.reference(img, CHAIN[-1], limit=8000000, adt_reg=0, id_zero=True)
    sim, stops, ttbr0 = cr.chain(img, CHAIN, limit=8000000, adt_reg=0, id_zero=True)
    ce = cr.compare_entry(ref, sim)
    cs = cr.compare(ref, sim, img)
    f = lambda d: {k: [hex(x) if isinstance(x, int) else x for x in v] for k, v in d.items()}
    return dict(adt_reg="0x0", chain=CHAIN, stops=[dict(n=s["n"], steps=s["steps"]) for s in stops],
                kernel_ttbr0_from_cp5_stop=hex(ttbr0), reference_steps=ref.steps, chain_steps=sim.steps,
                entry_strict_diff=f(ce["strict"]), entry_scratch_regs=sorted(ce["scratch"], key=lambda k: int(k[1:])),
                stop_reg_diff=sorted(cs["reg_diff"], key=lambda k: (len(k), k)), ram_diff_runs=len(cs["ram"]),
                taint_violations=len(sim.violations), daif_masked_at_every_entry=all(e["daif_masked"] for e in sim.jump_entries),
                assumed_reads=sorted({a for a, _ in sim.assumed}))


if __name__ == "__main__":
    out = dict(as_built=as_built(), masked=masked())
    p = ROOT / "artifacts/nat-035/runs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
