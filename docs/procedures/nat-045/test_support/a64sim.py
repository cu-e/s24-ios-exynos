"""NAT-045 aarch64 layer: the ladder compiled for aarch64 with the loader's real port (nat-041/engine/port_aarch64.h) and run in
unicorn against devmodel.DevModel. Needs zig and unicorn (the interpreter the caller uses must import unicorn).

Shows: the instruction stream the loader would run does the same accesses, in the same order, with the same values as the x86 build and
the reference interpreter; the default build contains no store to the platform and no delay. Does not show: caches, MMU, memory
attributes, SError, the real bus (unicorn has none of them)."""
import os
import struct
import subprocess

import unicorn
from unicorn import arm64_const as A

HERE = os.path.dirname(os.path.abspath(__file__))
NAT045 = os.path.dirname(HERE)
SRC = os.environ.get("NAT045_SRC") or os.path.join(NAT045, "src")
ENGINE = os.path.join(os.path.dirname(NAT045), "nat-041", "engine")

BASE = 0x40000000
STACK, STATE, CFG, STOPPAGE = 0x50000000, 0x51000000, 0x51100000, 0x52000000
FREQ = 1_000_000          # 1 tick = 1 microsecond
STATE_SIZE = 1348         # checked against the compiler by the tests (n_sizeof_state)

ZIG = ["zig", "cc", "-target", "aarch64-freestanding", "-nostdlib", "-static", "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
       "-mgeneral-regs-only", "-O2", "-Wall", "-Wextra", "-Werror", "-Wl,--image-base=0x%x" % BASE, "-Wl,--entry=lad_run"]


def build_elf(out_dir, writing=False, src_dir=None):
    src_dir = src_dir or SRC
    out = os.path.join(out_dir, "ladder-%s.elf" % ("w" if writing else "d"))
    cmd = ZIG + (["-DLAD_WRITING_RUNGS"] if writing else []) + ["-I", src_dir, "-I", ENGINE, os.path.join(src_dir, "ladder.c"), "-o", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        raise RuntimeError("zig build failed (%d):\n%s" % (r.returncode, r.stderr))
    return out


class Elf:
    def __init__(self, path):
        b = open(path, "rb").read()
        assert b[:4] == b"\x7fELF" and b[4] == 2 and b[5] == 1
        phoff, = struct.unpack_from("<Q", b, 32)
        phentsize, phnum = struct.unpack_from("<HH", b, 54)
        self.segments = []
        for i in range(phnum):
            t, flags, off, vaddr, paddr, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", b, phoff + i * phentsize)
            if t == 1:
                self.segments.append(dict(vaddr=vaddr, memsz=memsz, data=b[off:off + filesz], exec=bool(flags & 1)))
        out = subprocess.run(["nm", "-S", path], capture_output=True, text=True, check=True).stdout
        self.sym, self.size = {}, {}
        for line in out.splitlines():
            p = line.split()
            if len(p) == 4:
                self.sym[p[3]], self.size[p[3]] = int(p[0], 16), int(p[1], 16)

    def text(self):
        return [(s["vaddr"], s["data"]) for s in self.segments if s["exec"]]


class A64:
    def __init__(self, elf, dev, pages):
        self.elf, self.dev = elf, dev
        self.mu = mu = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
        mapped = set()
        for seg in elf.segments:
            for page in range(seg["vaddr"] & ~0xFFF, (seg["vaddr"] + seg["memsz"] + 0xFFF) & ~0xFFF, 0x1000):
                if page not in mapped:
                    mu.mem_map(page, 0x1000)
                    mapped.add(page)
            mu.mem_write(seg["vaddr"], seg["data"])
        mu.mem_map(STACK, 0x10000)
        mu.mem_map(STATE, 0x2000)
        mu.mem_map(CFG, 0x1000)
        mu.mem_map(STOPPAGE, 0x1000)
        mu.mem_write(STOPPAGE, b"\x1f\x20\x03\xd5" * 16)
        self.pages = sorted(set(a & ~0xFFF for a in pages))
        for p in self.pages:
            mu.mem_map(p, 0x1000)
        for p in self.pages:
            mu.hook_add(unicorn.UC_HOOK_MEM_READ, self._r, None, p, p + 0xFFF)
            mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._w, None, p, p + 0xFFF)
        mu.hook_add(unicorn.UC_HOOK_INSN, self._mrs, None, 1, 0, A.UC_ARM64_INS_MRS)
        self.insns = 0
        self.stores_to_devices = 0

    def _r(self, uc, access, addr, size, value, ud):
        assert size == 4, "device read of %d bytes @%#x" % (size, addr)
        uc.mem_write(addr, struct.pack("<I", self.dev.rd(addr)))

    def _w(self, uc, access, addr, size, value, ud):
        assert size == 4, "device write of %d bytes @%#x" % (size, addr)
        self.stores_to_devices += 1
        self.dev.wr(addr, value & 0xFFFFFFFF)

    def _mrs(self, uc, reg, cp, ud):
        if (cp.crn, cp.crm, cp.op0, cp.op1) == (14, 0, 3, 3):
            if cp.op2 in (1, 2):                                # CNTPCT_EL0 (the port) or CNTVCT_EL0: one tick = one microsecond, every read advances time
                self.dev.t += 1
                uc.reg_write(reg, self.dev.t)
                return True
            if cp.op2 == 0:                                     # CNTFRQ_EL0
                uc.reg_write(reg, FREQ)
                return True
        return False

    def call(self, name, *args, max_insn=60_000_000):
        mu = self.mu
        mu.reg_write(A.UC_ARM64_REG_SP, STACK + 0xF000)
        for i, a in enumerate(args):
            mu.reg_write(A.UC_ARM64_REG_X0 + i, a)
        mu.reg_write(A.UC_ARM64_REG_X30, STOPPAGE)
        try:
            mu.emu_start(self.elf.sym[name], STOPPAGE, count=max_insn)
        except unicorn.UcError as e:
            raise AssertionError("%s: %s at pc=%#x" % (name, e, mu.reg_read(A.UC_ARM64_REG_PC)))
        return mu.reg_read(A.UC_ARM64_REG_X0)

    def default_cfg(self):
        self.mu.mem_write(CFG, b"\xa5" * 12)
        self.call("lad_default_cfg", CFG)
        return struct.unpack("<III", bytes(self.mu.mem_read(CFG, 12)))

    def run(self, stop, allow_poweron=1, pd_wait_us=0):
        self.mu.mem_write(STATE, b"\xa5" * STATE_SIZE)          # lad_run must clear it itself
        self.mu.mem_write(CFG, struct.pack("<III", stop, allow_poweron, pd_wait_us))
        rc = self.call("lad_run", STATE, CFG)
        rc = struct.unpack("<i", struct.pack("<I", rc & 0xFFFFFFFF))[0]
        raw = bytes(self.mu.mem_read(STATE, STATE_SIZE))
        nops = (STATE_SIZE - 16) // 12
        nrec, err, err_op, rung_done, pd_was_on, soft = struct.unpack_from("<HhHBBH", raw, nops * 12)
        gsnpsid, = struct.unpack_from("<I", raw, nops * 12 + 12)
        return rc, dict(err=err, err_op=err_op, rung_done=rung_done, pd_was_on=pd_was_on, soft=soft, gsnpsid=gsnpsid, nrec=nrec)
