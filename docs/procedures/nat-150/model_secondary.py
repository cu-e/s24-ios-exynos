#!/usr/bin/env python3
"""NAT-150 host model: the path of a core that PSCI CPU_ON starts, from LowResetVectorBase to the point where its MMU is on,
executed instruction by instruction (unicorn) on the built kernel image, for the NAT-143 kernel (as run in NAT-149) and the
NAT-150 kernel (with the early marks).

Memory: the kernel's segments at a physical base (VA - link address + PA_BASE), the boot processor's side filled in as
psci_smp_start_cpu()/cpu_start() leave it (ResetHandlerData.cpu_data_entries, CpuDataEntries[i].cpu_data_paddr, each cpu data's
phys id, number, stacks and reset handler, const_boot_args), the MMU off. System registers are the model's: MRS of MPIDR_EL1,
CurrentEL, SCTLR_EL1, TTBR1_EL1 and TCR_EL1 returns its values, and every MSR is recorded instead of executed (so the MMU stays
off and the stage-6 store goes to its physical address, which the V=P mapping makes the same). The run stops at the first MSR to
CPACR_EL1 (the first instruction after the MMU block) or where a core spins (b .).

What it shows: for a core whose cpu data is found, the NAT-150 path executes the NAT-143 path's instructions in the same order with
only the mark blocks inserted, ends with the same registers (bar the marks' scratch x9-x12) and the same system-register writes,
and leaves marks 1, 2, 4, 5, 6 at the expected place with the expected values; a core with no cpu data, or with no valid reset
handler, leaves mark 3 and spins where NAT-143's spins.

What it does not show: anything about the phone's firmware, the hypervisor, caches, or the real page tables (no MMU here).

  artifacts/nat-065/venv/bin/python -B docs/procedures/nat-150/model_secondary.py [--out artifacts/nat-150/model-secondary.json]
"""
import argparse
import difflib
import glob
import importlib.util
import json
import struct
import sys
from pathlib import Path

import capstone
import unicorn
from unicorn import arm64_const as A

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KERNELS = {'nat143': ROOT / 'artifacts/nat-143/kernel-001', 'nat150': ROOT / 'artifacts/nat-150/kernel-001'}
LINK = 0xfffffff007004000
PA_BASE = 0x880000000
CPUDATA_PA = 0x8f0000000
MAGIC = 0x5EC00000
# assym.s of the start.o compile (STR-035 kernel-log-001 cwd/osfmk)
OFF = dict(CPU_DATA_ENTRIES=8, CPU_DATA_PADDR=0, CPU_PHYS_ID=448, CPU_RESET_HANDLER=176, CPU_NUMBER_GS=0, CPU_INTSTACK_TOP=24,
           CPU_EXCEPSTACK_TOP=40, BA_VIRT_BASE=8, BA_PHYS_BASE=16, BA_MEM_SIZE=24, BA_BOOT_FLAGS=720)
MAX_CPUS = 10
MEM_SIZE = 0x100000000
SYS = {(3, 0, 0, 0, 5): 'MPIDR_EL1', (3, 0, 4, 2, 2): 'CurrentEL', (3, 0, 1, 0, 0): 'SCTLR_EL1', (3, 0, 2, 0, 1): 'TTBR1_EL1',
       (3, 0, 2, 0, 2): 'TCR_EL1', (3, 0, 2, 0, 0): 'TTBR0_EL1', (3, 0, 12, 0, 0): 'VBAR_EL1', (3, 0, 10, 2, 0): 'MAIR_EL1',
       (2, 0, 1, 0, 4): 'OSLAR_EL1', (3, 3, 13, 0, 2): 'TPIDR_EL0', (3, 3, 13, 0, 3): 'TPIDRRO_EL0', (3, 0, 1, 0, 2): 'CPACR_EL1',
       (3, 0, 13, 0, 4): 'TPIDR_EL1'}


def load_vi():
    spec = importlib.util.spec_from_file_location('nat150_vi', ROOT / 'fixtures/public/e1s-native-link-image/verify_image.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Kernel:
    def __init__(self, key):
        d = KERNELS[key]
        self.unstripped = Path(glob.glob(str(d / 'link*/kernel/kernel.unstripped'))[0])
        self.image = (d / 'kernel.no-storage').read_bytes()
        vi = load_vi()
        self.segments = vi.parse(self.unstripped.read_bytes())['segments']
        self.sym = {}
        for line in vi.tool('nm', str(self.unstripped)).splitlines():
            f = line.split()
            if len(f) == 3:
                self.sym.setdefault(f[2], int(f[0], 16))

    def pa(self, name_or_va):
        va = self.sym[name_or_va] if isinstance(name_or_va, str) else name_or_va
        return va - LINK + PA_BASE


def run(key, mpidr, handler='start_cpu', limit=200000, entry_sym='_LowResetVectorBase'):
    k = Kernel(key)
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
    top = max(s['vmaddr'] + s['vmsize'] for s in k.segments if s['vmsize'])
    size = (top - LINK + 0xfffff) & ~0xfffff
    uc.mem_map(PA_BASE, size)
    for s in k.segments:
        if s['filesize'] if 'filesize' in s else s['vmsize']:
            n = s.get('filesize', s['vmsize'])
            uc.mem_write(s['vmaddr'] - LINK + PA_BASE, k.image[s['fileoff']:s['fileoff'] + n])
    uc.mem_map(CPUDATA_PA, 0x10000 * 1)
    w64 = lambda a, v: uc.mem_write(a, struct.pack('<Q', v))
    r64 = lambda a: struct.unpack('<Q', bytes(uc.mem_read(a, 8)))[0]
    # the boot processor's side
    entries = k.pa('_CpuDataEntries')
    w64(k.pa('_ResetHandlerData') + OFF['CPU_DATA_ENTRIES'], entries)
    handler_pa = k.pa('_' + handler) if handler else 0
    for i in range(MAX_CPUS):
        cd = CPUDATA_PA + i * 0x1000
        w64(entries + 16 * i + OFF['CPU_DATA_PADDR'], cd)
        uc.mem_write(cd + OFF['CPU_PHYS_ID'], struct.pack('<I', i << 8))
        uc.mem_write(cd + OFF['CPU_NUMBER_GS'], struct.pack('<h', i))
        w64(cd + OFF['CPU_INTSTACK_TOP'], 0xfffffff0aa000000 + i * 0x10000)
        w64(cd + OFF['CPU_EXCEPSTACK_TOP'], 0xfffffff0bb000000 + i * 0x10000)
        w64(cd + OFF['CPU_RESET_HANDLER'], handler_pa if i else 0)
    ba = k.pa('_const_boot_args')
    w64(ba + OFF['BA_VIRT_BASE'], LINK)
    w64(ba + OFF['BA_PHYS_BASE'], PA_BASE)
    w64(ba + OFF['BA_MEM_SIZE'], 0x100000000)
    w64(ba + OFF['BA_BOOT_FLAGS'], 0)
    w64(k.pa('_cpu_ttep'), 0x8a0000000)
    w64(k.pa('_sysreg_restore'), 0x00000035b5193519)

    sysregs = {'MPIDR_EL1': mpidr, 'CurrentEL': 0x4, 'SCTLR_EL1': 0x30d00800 ^ 0x4, 'TTBR1_EL1': 0, 'TCR_EL1': 0}
    writes, trace, state = [], [], {}
    cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

    def key_of(cp):
        return SYS.get((cp.op0, cp.op1, cp.crn, cp.crm, cp.op2), 'S%d_%d_C%d_C%d_%d' % (cp.op0, cp.op1, cp.crn, cp.crm, cp.op2))

    def on_mrs(uc_, reg, cp, _):
        name = key_of(cp)
        if name not in sysregs:
            state['unknown_mrs'] = name
            uc_.emu_stop()
            return True
        uc_.reg_write(reg, sysregs[name])
        return True

    def on_msr(uc_, reg, cp, _):
        name = key_of(cp)
        val = uc_.reg_read(reg)
        writes.append((name, val))
        if name in ('SCTLR_EL1', 'TTBR1_EL1', 'TCR_EL1'):
            sysregs[name] = val
        if name == 'CPACR_EL1':
            state['stop'] = 'CPACR_EL1'
            state['pc'] = uc_.reg_read(A.UC_ARM64_REG_PC)
            uc_.emu_stop()
        return True

    def on_code(uc_, addr, size_, _):
        insn = bytes(uc_.mem_read(addr, 4))
        trace.append((addr, insn))
        if insn == b'\x00\x00\x00\x14':                     # b .
            state['stop'] = 'spin'
            state['pc'] = addr
            uc_.emu_stop()

    def on_intr(uc_, intno, _):
        state['stop'] = 'exception %d' % intno
        state['pc'] = uc_.reg_read(A.UC_ARM64_REG_PC)
        uc_.emu_stop()

    uc.hook_add(unicorn.UC_HOOK_INSN, on_mrs, None, 1, 0, A.UC_ARM64_INS_MRS)
    uc.hook_add(unicorn.UC_HOOK_INSN, on_msr, None, 1, 0, A.UC_ARM64_INS_MSR)
    uc.hook_add(unicorn.UC_HOOK_CODE, on_code)
    uc.hook_add(unicorn.UC_HOOK_INTR, on_intr)
    if entry_sym == '__start':
        # the boot processor's cold start (start_first_cpu): x0 = the loader's boot arguments
        boot = CPUDATA_PA + 0xc000
        w64(boot + OFF['BA_VIRT_BASE'], LINK)
        w64(boot + OFF['BA_PHYS_BASE'], PA_BASE)
        w64(boot + OFF['BA_MEM_SIZE'], 0x40000000)
        w64(boot + OFF['BA_BOOT_FLAGS'], 0)
        uc.reg_write(A.UC_ARM64_REG_X0, boot)
    uc.emu_start(k.pa(entry_sym), 0, count=limit)
    regs = {'x%d' % i: uc.reg_read(getattr(A, 'UC_ARM64_REG_X%d' % i)) for i in range(29)}
    regs.update(lr=uc.reg_read(A.UC_ARM64_REG_LR), x29=uc.reg_read(A.UC_ARM64_REG_X29))
    sp0, sp1 = uc.reg_read(A.UC_ARM64_REG_SP_EL0), uc.reg_read(A.UC_ARM64_REG_SP_EL1)
    regs.update(sp_el0=sp0, sp_el1=sp1)
    insns = []
    for addr, b in trace:
        d = next(cs.disasm(b, addr), None)
        insns.append((addr, d.mnemonic if d else '?', d.op_str if d else b.hex()))
    marks = None
    if '_psci_smp_early_marks' in k.sym:
        slot = (mpidr >> 8) & 0xf
        base = k.pa('_psci_smp_early_marks') + 128 * slot
        marks = [r64(base + 8 * i) for i in range(16)]
    sym_at = {v: n for n, v in k.sym.items()}
    stop_sym = None
    if 'pc' in state:
        va = state['pc'] - PA_BASE + LINK
        best = max((v for v in sym_at if v <= va), default=None)
        stop_sym = '%s+0x%x' % (sym_at[best], va - best) if best else hex(va)
    return dict(kernel=key, mpidr=mpidr, handler=handler, stop=state.get('stop', 'limit'), stop_at=stop_sym,
                unknown_mrs=state.get('unknown_mrs'), instructions=len(trace), regs=regs, writes=writes, insns=insns,
                marks=marks, k=k)


def compare(old, new):
    """New trace = old trace with only whole mark blocks inserted; same final registers (bar x9-x12) and sysreg writes."""
    a = [(m, o) for _, m, o in old['insns']]
    b = [(m, o) for _, m, o in new['insns']]
    # addresses move by the inserted code: compare mnemonics, and operands where they are not PC-relative
    norm = lambda s: [(m, '' if m in ('adrp', 'b', 'bl', 'cbz', 'cbnz', 'tbz', 'tbnz', 'b.eq', 'b.ne', 'adr') else o) for m, o in s]
    sm = difflib.SequenceMatcher(a=norm(a), b=norm(b), autojunk=False)
    inserted = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'insert':
            return dict(ok=False, why='%s at old %d-%d new %d-%d: %s -> %s' % (tag, i1, i2, j1, j2, a[i1:i2], b[j1:j2]))
        inserted.append([m for m, _ in b[j1:j2]])
    body = ['mrs', 'ubfx', 'adrp', 'add', 'add', 'str', 'str', 'mrs', 'str', 'mov', 'movk', 'str', 'dc', 'add', 'dc', 'dsb']   # (capstone writes movz as mov)
    blocks = 0
    for blk in inserted:
        # a mark block, after at most three instructions that load its two values (mrs/mov) and skip it (cbz); stage 1's two
        # loads stand alone, before the vector set-up that comes between them and its block
        if blk[-len(body):] == body:
            pre, blocks = blk[:-len(body)], blocks + 1
        else:
            pre = blk
        if len(pre) > 3 or any(m not in ('mrs', 'mov', 'cbz') for m in pre):
            return dict(ok=False, why='inserted run is not a mark block: %s' % blk)
    ra = {k: v for k, v in old['regs'].items() if k not in ('x9', 'x10', 'x11', 'x12')}
    rb = {k: v for k, v in new['regs'].items() if k not in ('x9', 'x10', 'x11', 'x12')}
    diff = {k: (hex(ra[k]), hex(rb[k])) for k in ra if ra[k] != rb[k]}
    return dict(ok=not diff and old['writes'] == new['writes'] and old['stop'] == new['stop'], mark_blocks=blocks,
                inserted_runs=len(inserted),
                inserted_instructions=sum(map(len, inserted)), register_differences=diff,
                sysreg_writes_equal=old['writes'] == new['writes'], same_stop=(old['stop'], new['stop']))


def summary(r):
    k = r['k']
    out = {x: r[x] for x in ('kernel', 'mpidr', 'handler', 'stop', 'stop_at', 'unknown_mrs', 'instructions')}
    out['mpidr'] = hex(r['mpidr'])
    out['lr_is_arm_init_cpu'] = r['regs']['lr'] == k.sym['_arm_init_cpu']
    out['sysreg_writes'] = [(n, hex(v)) for n, v in r['writes']]
    if r['marks'] is not None:
        m = r['marks']
        out['marks'] = dict(last=hex(m[0]), mpidr=hex(m[1]),
                            stages={s: [hex(m[2 * s]), hex(m[2 * s + 1])] for s in range(1, 7) if m[2 * s] or m[2 * s + 1]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    res = {}
    cases = {'match_cpu4': (0x81000400, 'start_cpu'), 'no_cpu_data_0xa00': (0x81000a00, 'start_cpu'),
             'null_handler_cpu4': (0x81000400, None), 'resume_idle_cpu4': (0x81000400, 'resume_idle_cpu')}
    cases['boot_cpu_cold_start'] = (0x81000000, None, '__start')
    for name, (mpidr, handler, *entry) in cases.items():
        kw = dict(entry_sym=entry[0]) if entry else {}
        old, new = run('nat143', mpidr, handler, **kw), run('nat150', mpidr, handler, **kw)
        res[name] = dict(nat143=summary(old), nat150=summary(new), compare=compare(old, new))
    print(json.dumps(res, indent=1))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1) + '\n')
    return res


if __name__ == '__main__':
    main()
