#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-032: what the payload kernel runs after assembly checkpoint 5, from the real bytes (host only).

Two parts, both read-only on local artifacts; nothing here touches a device:

* static reach: the direct-call closure (bl and tail b) of a kernel function in the payload (capstone), with
  the system registers it reads or writes, SIMD use, SVC/HVC/SMC, cache/TLB maintenance, indirect branches
  and the functions that reference a given data page. The closure is an over-approximation: it follows every
  direct call whether or not the path runs, and it does not follow indirect calls;
* a dynamic trace in the NAT-030 interpreter: resume the kernel at checkpoint 5 the way the NAT-032 design
  says (re-execute the kernel's own MMU enable), run to the first C checkpoint and list what executed.

Inputs: artifacts/nat-020/build-003/payload.bin (what the loader copies) and kernel.no-storage (symbol
names only). Usage: after5.py [--out FILE]
"""
import argparse
import bisect
import collections
import importlib.util
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAYLOAD = ROOT / "artifacts/nat-020/build-003/payload.bin"
KERNEL = ROOT / "artifacts/nat-020/build-003/kernel.no-storage"
ANALYSIS = ROOT / "artifacts/nat-029/payload-analysis.json"
M64 = (1 << 64) - 1


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ap = _load("nat029_analyze", ROOT / "docs/procedures/nat-029/analyze_payload.py")
ks = _load("nat030_kstart_sim", ROOT / "docs/procedures/nat-030/kstart_sim.py")
import capstone  # noqa: E402  (the NAT-030 interpreter already requires it)


class Image:
    """Payload bytes + symbol table with function bounds taken from the next symbol."""

    def __init__(self, payload=PAYLOAD, kernel=KERNEL):
        self.p = ap.Payload(str(payload))
        syms = ap.macho_symbols(str(kernel))
        self.vals = {k: (v if isinstance(v, int) else v["va"]) for k, v in syms.items()}
        self.items = sorted((v, k) for k, v in self.vals.items())
        self.addrs = [a for a, _ in self.items]
        self.md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        self.md.detail = False

    def sym_at(self, va):
        i = bisect.bisect_right(self.addrs, va) - 1
        return self.items[i] if i >= 0 else (va, "?")

    def name(self, va):
        a, n = self.sym_at(va)
        return "%s+%#x" % (n, va - a)

    def end_of(self, va):
        i = bisect.bisect_right(self.addrs, va)
        return self.addrs[i] if i < len(self.addrs) else va + 0x1000

    def scan(self, name):
        s = self.vals[name]
        e = self.end_of(s)
        r = dict(start=s, size=e - s, calls=set(), indirect=0, sysreg=set(), simd=0, svc=set(), maint=set(), pages=set())
        for ins in self.md.disasm(self.p.va(s, e - s), s):
            m, o = ins.mnemonic, ins.op_str
            if m == "bl":
                r["calls"].add(self.sym_at(int(o.split("#")[-1], 16))[1])
            elif m == "b" and o.startswith("#"):
                t = int(o.split("#")[-1], 16)
                if not s <= t < e:          # a tail call: a branch out of this function's own range
                    r["calls"].add(self.sym_at(t)[1])
            elif m in ("blr", "br"):
                r["indirect"] += 1
            elif m in ("msr", "mrs"):
                ops = [x.strip() for x in o.split(",")]
                r["sysreg"].add(("W " + ops[0]) if m == "msr" else ("R " + ops[1]))
            elif m in ("svc", "hvc", "smc"):
                r["svc"].add(m)
            elif m in ("dc", "ic", "tlbi"):
                r["maint"].add(m + " " + o)
            elif m == "adrp":
                r["pages"].add(int(o.split("#")[-1], 16))
            if re.search(r"\bv\d+\.|\b[qd]\d+\b", o) and m not in ("b", "bl"):
                r["simd"] += 1
        return r

    def closure(self, root, depth):
        seen = {}
        q = collections.deque([(root, 0)])
        while q:
            n, d = q.popleft()
            if n in seen or n not in self.vals:
                continue
            seen[n] = (d, self.scan(n))
            if d < depth:
                for c in sorted(seen[n][1]["calls"]):
                    q.append((c, d + 1))
        return seen

    def page_users(self, page):
        """Names of all functions with an adrp to `page` (a 4 KiB-aligned VA): who can reference a global there."""
        out = []
        for i, (a, n) in enumerate(self.items):
            e = self.addrs[i + 1] if i + 1 < len(self.addrs) else a + 0x1000
            if e - a > 0x4000 or e <= a:
                continue
            b = self.p.va(a, e - a)
            if b is None:
                continue
            for w in struct.unpack("<%dI" % (len(b) // 4), b[:len(b) // 4 * 4]):
                if w & 0x9F000000 == 0x90000000:
                    break
            else:
                continue
            for ins in self.md.disasm(b, a):
                if ins.mnemonic == "adrp" and int(ins.op_str.split("#")[-1], 16) == page:
                    out.append(n)
                    break
        return out


def _stores_to(img, page, offset):
    """Functions with a store whose base register came from `adrp reg, page` (+ an optional `add reg, reg, #imm`) and
    whose total offset is `offset`: the writers of a global at page + offset. A register-copy or a pointer loaded
    from elsewhere is not followed, so this finds direct stores only."""
    out = []
    for i, (a, n) in enumerate(img.items):
        e = img.addrs[i + 1] if i + 1 < len(img.addrs) else a + 0x1000
        if e <= a or e - a > 0x4000:
            continue
        b = img.p.va(a, e - a)
        if not b:
            continue
        held = {}
        for ins in img.md.disasm(b, a):
            o = ins.op_str
            if ins.mnemonic == "adrp":
                r, t = [x.strip() for x in o.split(",")]
                if int(t.split("#")[-1], 16) == page:
                    held[r] = 0
                else:
                    held.pop(r, None)
            elif ins.mnemonic == "add":
                f = [x.strip() for x in o.split(",")]
                if len(f) == 3 and f[1] in held and f[2].startswith("#"):
                    held[f[0]] = int(f[2][1:], 0)
            elif ins.mnemonic in ("str", "stp"):
                mm = re.search(r"\[(x\d+)(?:, #(0x[0-9a-f]+))?\]", o)
                if mm and mm.group(1) in held and held[mm.group(1)] + (int(mm.group(2), 16) if mm.group(2) else 0) == offset:
                    out.append(n)
    return sorted(set(out))


Image.stores_to = lambda self, page, offset: _stores_to(self, page, offset)


def summarise(closure):
    rows = []
    for n, (d, r) in sorted(closure.items(), key=lambda kv: (kv[1][0], kv[0])):
        rows.append(dict(depth=d, name=n, va="%#x" % r["start"], size=r["size"], sysreg=sorted(r["sysreg"]), simd=r["simd"],
                         svc=sorted(r["svc"]), maint=sorted(r["maint"]), indirect=r["indirect"], calls=sorted(r["calls"])))
    return rows


# ---------------------------------------------------------------------------------------------------------------
# dynamic part: the NAT-030 interpreter, resumed at checkpoint 5 the way the design says
# ---------------------------------------------------------------------------------------------------------------
BASE, SIZE = 0x9de400000, 0x20000000
STUB = BASE + 0x4a00000          # a stand-in for the loader's return stub (outside the kernel image)
RESUME_BACK = 28                 # bytes before the macro of checkpoint 5: the kernel's own `movk x0 ...` MMU-enable block


class Tracing(ks.Sim):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = []
        self.exc_regs = []

    def step(self):
        pc = self.pc
        ins = self.fetch()
        if ins.mnemonic in ("bl", "blr", "br"):
            self.calls.append((pc, ins.mnemonic, ins.op_str))
        super().step()


def analysis():
    return ks.load_analysis(str(ANALYSIS))


def stopped_at(n, cls=Tracing):
    """A model run from the kernel's entry with slot[2] = n: returns the simulator stopped at the arrival."""
    a = analysis()
    sim = cls(str(PAYLOAD), BASE, SIZE)
    sim.fill_slot(a["slot_va"], STUB, n, (BASE - sim.p.virt_base) & M64)
    sim.run(stop_pcs={STUB}, limit=200000)
    return sim, a


def resume_at_five(sim, a, next_ckpt, junk):
    """Resume as a stub would, with no loader code under the kernel's MMU: clobber the registers the stop
    path used, set slot[2], leave SCTLR_EL1.M clear and continue at the kernel's own `movk x0 ... ; msr sctlr_el1, x0 ;
    isb ; cbnz x21` block that turned the MMU on just before the checkpoint macro (site - 28 bytes)."""
    for r in (0, 1, 2, 3, 9, 10, 11):
        sim.x[r] = junk
        sim.taint[r] = {0, 1, 2, 3}
    sim.write_pa(sim.pa_of_kva(a["slot_va"]) + 16, struct.pack("<Q", next_ckpt))
    sim.pc = sim.pa_of_kva(a["sites"][5]) - RESUME_BACK


def trace_to_c10(junk=0xDEADBEEFCAFEF00D):
    """Stop at 5, resume per the design with slot[2] = 11, run to the call of loader_checkpoint(10)."""
    img = Image()
    sim, a = stopped_at(5)
    assert sim.mmu_on() == 0 and sim.x[2] == 2 and sim.x[3] == 5
    n0, ev0, c0 = sim.steps, len(sim.events), len(sim.calls)
    resume_at_five(sim, a, 11, junk)
    lc = img.vals["_loader_checkpoint"]
    sim.run(stop_pcs={lc}, limit=sim.steps + 5000)
    wr = [(n, v, pc) for (k, n, v, pc) in sim.events[ev0:] if k == "msr"]
    return dict(steps_after_resume=sim.steps - n0, x0_at_call=sim.x[0], violations=list(sim.violations),
                calls=list(sim.calls[c0:]),
                sysreg_writes=wr, image=img, sim=sim)


def main(argv=None):
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--out")
    ap_.add_argument("--depth", type=int, default=4)
    a = ap_.parse_args(argv)
    img = Image()
    out = {"payload": str(PAYLOAD.relative_to(ROOT)), "static": {}}
    for root in ("_loader_checkpoint", "_loader_jump", "_cpu_data_init", "_PE_init_platform"):
        out["static"][root] = summarise(img.closure(root, a.depth))
    t = trace_to_c10()
    out["dynamic"] = dict(steps_after_resume=t["steps_after_resume"], x0_at_c10_call="%#x" % t["x0_at_call"],
                          taint_violations=[(hex(pc), r, i) for pc, r, i in t["violations"]],
                          sysreg_writes=[(n, hex(v), hex(pc)) for n, v, pc in t["sysreg_writes"]],
                          calls=[(hex(pc), mn, op, img.name(int(op.split("#")[-1], 16)) if op.startswith("#") else op)
                                 for pc, mn, op in t["calls"]])
    text = json.dumps(out, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
