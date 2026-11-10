#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-035: model of resuming the NAT-022 kernel from a C checkpoint stop (host model only).

Run 009 (decision 0017) stopped the kernel at C checkpoint 11 inside `loader_jump` with the loader's private TTBR0 and
`loader_return_entered` = 1. This module is the specification, executable in the NAT-030/033 instruction-level model,
of what a return stub must do to give the kernel back, and how it is checked:

  * `Assumed`        the loader-equal model (loader_inputs.LoaderEqual) plus the few system-register reads the code
                     after checkpoint 11 needs and the model does not have. Every use is recorded in `.assumed`.
  * `c_resume`       the resume primitives, each one a thing a stub can do on the phone (MMU off, loader-owned memory,
                     a cache-maintained store by PA; MMU on with the private TTBR0 that already maps the stub; a branch
                     to the kernel's own `_set_mmu_ttb` and `_loader_jump` epilogue). `omit=` removes one primitive
                     (negative control); `kernel_ttbr0=` and `saved=` are the stub's own captures.
  * `chain`          cp5 stop -> resume_at_five -> C stops in order, resuming each one;
  * `reference`      an uninterrupted run that stops only at the last checkpoint (slot[2] = n from the start);
  * `compare`        register, system-register and RAM comparison of the two.

Not modelled: caches, TLB, exceptions, the stub's own MMU-off/on sequence (it is the Python code here), the loader's
display. See README.md for what that leaves unproven. Host only: reads local artifacts, writes nothing.
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import loader_inputs as li  # noqa: E402

c11, sd = li.c11, li.sd
a5 = li.a5
M64 = (1 << 64) - 1
JUNK = 0xDEADBEEFCAFEF00D
KERNEL_SET_TTB = "_set_mmu_ttb"        # dsb ish; msr ttbr0_el1, x0; isb; ret  (16 bytes; the only TTBR0 writer besides loader_jump)
KERNEL_JUMP_EPILOGUE = 0x4c            # _loader_jump + 0x4c: ldp x29, x30, [sp, #0x30]; add sp, sp, #0x40; ret (early return)
FLAG = "_loader_return_entered"
SCTLR_MC = 0x5                         # M | C

# Primitives that omit= may remove (negative controls).
PRIMS = ("flag", "slot", "sp", "callee", "ttbr0", "ttbr0_private", "x18")


class Assumed(li.LoaderEqual):
    """LoaderEqual plus reads the model lacks. Each is an assumption about the phone, listed in `assumed`:
    cntkctl_el1 = 0 (reset value), cntvct/cntpct_el0 = a counter that advances 1000 per read, daif = 0x3c0 when the
    model's all-masked flag is set, and (only with id_zero=True) ccsidr_el1 = clidr_el1 = id_aa64dfr0_el1 = 0."""

    CNT0 = 1000000
    ID_ZERO_REGS = ("ccsidr_el1", "clidr_el1", "id_aa64dfr0_el1")   # read by cpu_init before checkpoint 16

    def __init__(self, *a, id_zero=False, **k):
        super().__init__(*a, **k)
        self.id_zero = id_zero                 # assume the three ID registers above read 0 (they are hardware facts)
        self.assumed = []
        self.jump_entries = []                 # the kernel's own state at each entry of loader_jump (before it changes anything)
        self._lj = self.names.vals["_loader_jump"] if self.names is not None else None

    def step(self):
        if self.pc == self._lj:
            self.jump_entries.append(dict(steps=self.steps, x=list(self.x), sp=sp_of(self), sr=dict(self.sr),
                                          nzcv=(self.n, self.z, self.c, self.v), daif_masked=self.daif_masked))
        super().step()

    def mrs(self, name):
        n = name.strip()
        if n in ("cntvct_el0", "cntpct_el0"):
            self.CNT0 += 1000
            self.assumed.append((n, self.pc))
            return self.CNT0
        if n == "cntkctl_el1" and n not in self.sr:
            self.assumed.append((n, self.pc))
            return 0
        if self.id_zero and n in self.ID_ZERO_REGS and n not in self.sr:
            self.assumed.append((n, self.pc))
            return 0
        if n == "daif":
            self.assumed.append((n, self.pc))
            return 0x3c0 if self.daif_masked else 0
        return super().mrs(n)


def sp_of(sim):
    return sim.sp_el[sim.spsel]


def stub_save(sim):
    """What the stub's prologue saves into loader-owned memory, from the state it is entered with. It cannot know the
    kernel's TTBR0 (loader_jump has already replaced it); that comes from the checkpoint-5 stop (see chain)."""
    return dict(sp=sp_of(sim), callee=list(sim.x[19:29]), x18=sim.x[18], sctlr=sim.sr["sctlr_el1"])


def c_resume(sim, a, img, saved, kernel_ttbr0, next_ckpt, omit=(), junk=JUNK):
    """Resume the kernel from a C-checkpoint stop at `a5.STUB`. Returns when the PC is back in kernel code."""
    bad = set(omit) - set(PRIMS)
    if bad:
        raise ValueError("unknown primitive(s) %s" % sorted(bad))
    lj = img.vals["_loader_jump"]
    gadget = img.vals[KERNEL_SET_TTB]
    # the stub is ordinary code: the caller-saved registers, x29 and x30 are its scratch
    for r in list(range(0, 18)) + [29, 30]:
        sim.x[r] = junk
        sim.taint[r] = {0, 1, 2, 3}
    flag_pa = sim.pa_of_kva(img.vals[FLAG])
    if "flag" not in omit:
        sim.write_pa(flag_pa, b"\0")                       # MMU off, by PA, cache-maintained (as the slot[2] store)
    if "slot" not in omit:
        sim.write_pa(sim.pa_of_kva(a["slot_va"]) + 16, struct.pack("<Q", next_ckpt))
    if "callee" in omit:
        for r in range(19, 29):
            sim.x[r] = junk
            sim.taint[r] = {0, 1, 2, 3}
    else:
        sim.x[19:29] = saved["callee"]
    if "x18" in omit:
        sim.x[18] = junk
        sim.taint[18] = {0, 1, 2, 3}
    else:
        sim.x[18] = saved["x18"]
    sim.sp_el[sim.spsel] = junk if "sp" in omit else saved["sp"]
    sim.sr["sctlr_el1"] = saved["sctlr"]                   # M|C back on with the private TTBR0 still installed
    # branch to the kernel's own TTBR0 setter: x0 = the kernel's TTBR0, x30 = the early-return epilogue of loader_jump
    sim.x[0] = junk if "ttbr0" in omit else kernel_ttbr0
    sim.taint.pop(0, None)
    sim.x[30] = lj + KERNEL_JUMP_EPILOGUE
    sim.taint.pop(30, None)
    # "ttbr0_private": no TTBR0 restore at all (the private table stays installed), straight to the epilogue
    sim.pc = lj + KERNEL_JUMP_EPILOGUE if "ttbr0_private" in omit else gadget


def stub_pc_reached(sim, limit):
    sim.run(stop_pcs={a5.STUB}, limit=limit)
    return sim


def new(img, **kw):
    sim = Assumed(names=img, **kw)
    return sim, a5.analysis()


def reference(img, n, limit=3000000, **kw):
    """Uninterrupted: slot[2] = n from the start; the first loader_jump entry is the stop at n."""
    sim, a = new(img, **kw)
    sim.fill_slot(a["slot_va"], a5.STUB, n, (a5.BASE - sim.p.virt_base) & M64)
    sim.run(stop_pcs={a5.STUB}, limit=limit)
    return sim


def chain(img, order, omit=(), limit=3000000, observe=None, **kw):
    """checkpoint-5 stop, the run-008/009 resume to order[0], then resume from each C stop to the next in `order`.
    Returns (sim, stops) with stops[i] = state at the stop for order[i]; the sim is left at the last stop."""
    sim, a = new(img, **kw)
    sim.fill_slot(a["slot_va"], a5.STUB, 5, (a5.BASE - sim.p.virt_base) & M64)
    sim.run(stop_pcs={a5.STUB}, limit=limit)
    assert sim.x[2] == 2 and sim.x[3] == 5 and not sim.mmu_on(), sim.stop_state()
    kernel_ttbr0 = sim.sr["ttbr0_el1"]                    # captured while the MMU is off and the kernel's TTBR0 is intact
    a5.resume_at_five(sim, a, order[0], JUNK)
    stops = []
    for i, n in enumerate(order):
        sim.run(stop_pcs={a5.STUB}, limit=sim.steps + limit)
        stops.append(dict(n=n, steps=sim.steps, x3=sim.x[3], ttbr0=sim.sr["ttbr0_el1"], sp=sp_of(sim)))
        if observe:
            observe(sim, n)
        if i + 1 < len(order):
            c_resume(sim, a, img, stub_save(sim), kernel_ttbr0, order[i + 1], omit=omit)
    return sim, stops, kernel_ttbr0


SCRATCH = tuple(range(4, 18))        # at the stop: x4..x17 are caller-saved and dead across the checkpoint call
ENTRY_SCRATCH = tuple(range(2, 18))  # at loader_jump's entry only x0, x1 are arguments; x2, x3 are set by loader_jump itself


def compare_entry(ref, got):
    """The kernel's own state at the last loader_jump entry of two runs (what the resume must give back): all system
    registers, SP, NZCV, DAIF, x0, x1 and x18..x30 must be equal; x2..x17 are caller-saved scratch (reported separately)."""
    a, b = ref.jump_entries[-1], got.jump_entries[-1]
    strict, scratch = {}, {}
    for r in range(31):
        if a["x"][r] != b["x"][r]:
            (scratch if r in ENTRY_SCRATCH else strict)["x%d" % r] = (a["x"][r], b["x"][r])
    for k in ("sp", "nzcv", "daif_masked"):
        if a[k] != b[k]:
            strict[k] = (a[k], b[k])
    for k in sorted(set(a["sr"]) | set(b["sr"])):
        if a["sr"].get(k) != b["sr"].get(k):
            strict[k] = (a["sr"].get(k), b["sr"].get(k))
    return dict(strict=strict, scratch=scratch)


def regs(sim):
    return dict(x=list(sim.x), sp=sp_of(sim), nzcv=(sim.n, sim.z, sim.c, sim.v), daif_masked=sim.daif_masked,
                pc=sim.pc, sr=dict(sim.sr))


def compare(ref, got, img):
    """Registers and system registers that must be equal, and the RAM differences with their classification."""
    ra, rb = regs(ref), regs(got)
    reg_diff = {}
    for r in range(31):
        if ra["x"][r] != rb["x"][r]:
            reg_diff["x%d" % r] = (ra["x"][r], rb["x"][r])
    for k in ("sp", "nzcv", "daif_masked", "pc"):
        if ra[k] != rb[k]:
            reg_diff[k] = (ra[k], rb[k])
    for k in sorted(set(ra["sr"]) | set(rb["sr"])):
        if ra["sr"].get(k) != rb["sr"].get(k):
            reg_diff[k] = (ra["sr"].get(k), rb["sr"].get(k))
    ram = ram_diff(ref, got)
    return dict(reg_diff=reg_diff, ram=ram)


def ram_diff(ref, got):
    """Byte-level RAM differences, as (pa_start, length) runs."""
    runs = []
    for pa in sorted(set(ref.pages) | set(got.pages)):
        pa_ = ref.pages.get(pa, bytes(sd.a5.PAGE if hasattr(sd.a5, "PAGE") else 4096))
        pb_ = got.pages.get(pa, bytes(len(pa_)))
        if pa_ == pb_:
            continue
        i = 0
        n = len(pa_)
        while i < n:
            if pa_[i] != pb_[i]:
                j = i
                while j < n and pa_[j] != pb_[j]:
                    j += 1
                runs.append((pa + i, j - i))
                i = j
            else:
                i += 1
    return runs


if __name__ == "__main__":
    img = a5.Image()
    order = [int(x) for x in sys.argv[1:]] or [11, 30]
    sim, stops, ttbr0 = chain(img, order)
    ref = reference(img, order[-1])
    print("kernel TTBR0 captured at the cp5 stop: %#x" % ttbr0)
    for s in stops:
        print(s)
    d = compare(ref, sim, img)
    print("reg diff:", {k: tuple(hex(x) if isinstance(x, int) else x for x in v) for k, v in d["reg_diff"].items()})
    print("ram diff runs:", len(d["ram"]), sum(n for _, n in d["ram"]), "bytes", [(hex(a), n) for a, n in d["ram"][:12]])
    print("violations:", len(sim.violations), sim.violations[:3])
