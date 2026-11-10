#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-033: run the real payload kernel in the NAT-030 model (extended with the SIMD forms of simd.py) to the C
checkpoint 11 stop, two ways, and describe the arrival. Host only; reads local artifacts, writes nothing but --out.

  reference: from the kernel entry with slot[2] = 11 (nothing else stops it);
  resumed:   from the kernel entry with slot[2] = 5, stop at assembly checkpoint 5, resume the way NAT-032 designs it
             (x0..x3 and x9..x11 clobbered, slot[2] = 11, MMU-off branch to site5 - 28), run to the same stop.

Usage: c11.py [--out FILE]
"""
import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import simd as sd  # noqa: E402

a5, ks = sd.a5, sd.ks
M64 = (1 << 64) - 1
JUNK = 0xDEADBEEFCAFEF00D
LIMIT = 100000


class Probe(sd.SimdSim):
    """Also records the sequence of functions the PC enters (by symbol), every memory page it writes outside the kernel's
    own image, and the instruction count per function."""

    def __init__(self, *a, names=None, **k):
        super().__init__(*a, **k)
        self.names = names
        self.fn_seq = []
        self._last = None

    def step(self):
        if self.names is not None:
            n = self.names.sym_at(self.pc)[1] if self.pc >> 63 else "<physical>"
            if n != self._last:
                self.fn_seq.append((self.steps, n))
                self._last = n
        super().step()


def fresh(slot_ckpt, img):
    a = a5.analysis()
    sim = Probe(str(a5.PAYLOAD), a5.BASE, a5.SIZE, names=img)
    sim.fill_slot(a["slot_va"], a5.STUB, slot_ckpt, (a5.BASE - sim.p.virt_base) & M64)
    return sim, a


def reference(img):
    sim, a = fresh(11, img)
    sim.run(stop_pcs={a5.STUB}, limit=LIMIT)
    return sim, a


def resumed(img, junk=JUNK):
    sim, a = fresh(5, img)
    sim.run(stop_pcs={a5.STUB}, limit=LIMIT)
    assert sim.x[2] == 2 and sim.x[3] == 5 and not sim.mmu_on(), sim.stop_state()
    at_stop = sim.steps
    a5.resume_at_five(sim, a, 11, junk)
    sim.run(stop_pcs={a5.STUB}, limit=sim.steps + LIMIT)
    return sim, a, at_stop


def arrival(sim, img, a):
    """What the stub would see: registers, the system registers the kernel set, the loader_log counters."""
    p = sim.p
    log_len_va = img.vals["_loader_log_len"]
    log_va = img.vals["_loader_log"]
    ln = sim.read(log_len_va, 8)
    return dict(
        steps=sim.steps, mmu_on=bool(sim.mmu_on()),
        x0=sim.x[0], x1=sim.x[1], x2=sim.x[2], x3=sim.x[3], x5=sim.x[5],
        log_pa=sim.pa_of_kva(log_va), log_len=ln,
        log_head=bytes(sim.read_pa(sim.pa_of_kva(log_va), min(ln, 64))).hex(),
        sctlr=sim.sr["sctlr_el1"], tcr=sim.sr["tcr_el1"], ttbr0=sim.sr["ttbr0_el1"], ttbr1=sim.sr["ttbr1_el1"],
        vbar=sim.sr["vbar_el1"], mair=sim.sr.get("mair_el1"),
        cpacr=sim.sr.get("cpacr_el1"), tpidr=sim.sr.get("tpidr_el1"),
        daif_masked=sim.daif_masked,
        loader_return_entered=sim.read_pa(sim.pa_of_kva(img.vals["_loader_return_entered"]), 1)[0]
        if "_loader_return_entered" in img.vals else None,
        simd_instructions=len(sim.simd_executed), unaligned=len(sim.unaligned),
    )


def functions(sim):
    """Ordered distinct function entries since the kernel went virtual (consecutive repeats collapsed)."""
    return [n for _, n in sim.fn_seq if n != "<physical>"]


def snapshot(sim):
    return {pa: bytes(pg) for pa, pg in sim.pages.items() if any(pg)}


def main(argv=None):
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--out")
    args = ap_.parse_args(argv)
    img = a5.Image()
    ref, a = reference(img)
    res, a, at5 = resumed(img)
    out = dict(
        reference=arrival(ref, img, a), resumed=arrival(res, img, a), steps_at_checkpoint5=at5,
        functions=functions(ref),
        sysreg_writes=[(n, hex(v), hex(pc)) for k, n, v, pc in ref.events if k == "msr"],
        simd_executed=[(hex(pc), m, "%#010x" % w) for pc, m, w in ref.simd_executed],
        unaligned=[(hex(pc), hex(va), n, None if m is None else hex(m)) for pc, va, n, m in ref.unaligned],
        registers_equal=ref.x == res.x and ref.vr == res.vr,
        ram_equal=snapshot(ref) == snapshot(res),
    )
    text = json.dumps(out, indent=1, default=lambda o: hex(o) if isinstance(o, int) else str(o))
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
