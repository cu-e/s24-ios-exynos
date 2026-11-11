"""NAT-047 aarch64 layer: the built loader.elf (loader-diag-usbmon / -fault) executed instruction by instruction in unicorn, wired to

  * the NAT-041 DWC3 host model (x86, model/model.c) through unicorn MMIO windows: the loader's real aarch64 engine drives the
    model's registers and the model's raw-pointer DMA reaches the same bytes (the guest RAM is a host mmap at the same address),
  * the NAT-045 DevModel (power domain / platform registers the ladder touches, with its access-gate violations),
  * a PMU / WDT / DECON0 register model and a framebuffer decoded back to frames (as NAT-044 does),
  * the NAT-041 collector (s24_logd.py) as the host program, driven through Rig47 against the model's USB host.

Evidence kind: host-test. Time is simulated: every CNTVCT read (the loader's clock) advances 1 ms, every CNTPCT read (the engine's
clock) 1 us, so the 45 s deadline and the 83 s watchdog period run in seconds. Not modelled: caches, MMU, memory attributes, a
second CPU, interrupts, the real controller, the real USB stack. The loader image is linked at 0 and is loaded at 0x80080000.
"""
import ctypes
import importlib.util
import os
import struct
import subprocess
import sys

import unicorn
from unicorn import arm64_const as A

HERE = os.path.dirname(os.path.abspath(__file__))
NAT047 = os.path.dirname(HERE)
PROC = os.path.dirname(NAT047)
N22, N41, N45 = (os.path.join(PROC, n) for n in ("nat-022", "nat-041", "nat-045"))
ENGINE, MODEL = os.path.join(N41, "engine"), os.path.join(N41, "model")
for _p in (N41, os.path.join(N45, "test_support")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import modelhost as M  # noqa: E402
from a64sim import Elf  # noqa: E402
from devmodel import DWC3_HI, DWC3_LO, GATE_HI, GATE_LO  # noqa: E402,F401
import devmodel  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


dec = _load("nat047_decode_base", os.path.join(N22, "decode.py"))

FREQ = 24_000_000
STEP_V = 24_000          # one CNTVCT read = 1 ms (the loader's clock)
STEP_P = 24              # one CNTPCT read = 1 us (the engine's clock)
T0 = 5_000_000
REGION, REGION_SIZE = 0x80000000, 0x2000000       # host mmap at the same address as the guest sees
LOAD = 0x80080000
CB_STACK_TOP = 0x81010000
STOP = 0x81100000
CMU_LO, CMU_SIZE = 0x22B20000, 0x10000            # the ladder's clock-controller registers (L2): DevModel only
PMU, WDT, DECON, FB = 0x12860000, 0x10040000, 0x19100000, 0xFA200000
INFORM2, INFORM3, CMD, REBOOT = 0xB8, 0xBC, 0x190, 0x3C00
BRK_ESR = 0xF2001234
EXC_SPSR = 0x3C5
EXC_FAR = 0x00C0FFEE1000          # FAR_EL1 is UNKNOWN after a BRK; the harness makes it distinctive so a dropped or zeroed FAR shows
UC_ALL = unicorn.UC_PROT_ALL

POLL_CB = ctypes.CFUNCTYPE(None)
_libc = ctypes.CDLL(None, use_errno=True)
_libc.mmap.restype = ctypes.c_void_p
_libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
_libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]


def load_elf(path):
    """a64sim.Elf (symbols with sizes) plus the size-less ones (_stack_top, vectors, ...)."""
    e = Elf(path)
    out = subprocess.run(["nm", path], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        p = line.split()
        if len(p) == 3 and p[2] not in e.sym:
            e.sym[p[2]] = int(p[0], 16)
    return e


class RegionUnavailable(Exception):
    pass


def build_glue(out_dir):
    """The NAT-041 model with its poll redirected, plus the x86 engine only so the library links."""
    out = os.path.join(out_dir, "libglue47.so")
    cmd = ["cc", "-shared", "-fPIC", "-O1", "-g", "-Wall", "-Wextra", "-DUSBMON_TESTING", '-DUSBMON_PORT_HEADER="host_port.h"',
           "-I", ENGINE, "-I", MODEL, os.path.join(HERE, "glue47.c"), os.path.join(ENGINE, "usbmon.c"), "-o", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        raise RuntimeError("glue build failed or warned (%d):\n%s" % (r.returncode, r.stderr))
    return out


def load_lib(path):
    lib = M.Machine.load(path)
    lib.h_set_poll_cb.argtypes = [POLL_CB]
    lib.h_reset.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.h_rd32.restype = ctypes.c_uint32
    lib.h_rd32.argtypes = [ctypes.c_uint64]
    lib.h_wr32.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    for n in ("h_sizeof_dma", "h_sizeof_usbmon", "h_offsetof_dma"):
        getattr(lib, n).restype = ctypes.c_uint32
    lib.model_nviol.restype = ctypes.c_int
    lib.model_wtrace_n.restype = ctypes.c_int
    lib.model_ctrace_n.restype = ctypes.c_int
    return lib


class Machine47(M.Machine):
    """The NAT-041 Machine API the collector's rig needs, over the glue library (the engine is the guest's)."""
    def __init__(self, sim):
        self.lib, self.sim = sim.lib, sim
        self.ring_size, self.boot_id, self.init_rc = 32768, b"", 0

    def close(self):
        pass


class Sim47:
    def __init__(self, elf, lib, table, pd_on=False, pd_delay_us=50, init=None, dev_kw=None):
        self.elf, self.lib = elf, lib
        self.dev = devmodel.DevModel(table, pd_on=pd_on, pd_delay=pd_delay_us, **(dev_kw or {}))
        self.t = self.t0 = T0
        self.target = 0
        self.in_cb = 0
        self.queue, self.cur, self.pc = [], None, 0
        self.paused = self.stopped = False
        self.done_calls = []
        self.done_polls = []               # self.polls when each of the done_calls completed
        self.insn_budget = 4_000_000_000
        self.pmu_events, self.wdt_events = [], []
        self.reset_t = None                # simulated time of the PMU reboot trigger store
        self.frames = []
        self.fb_at_reset = None
        self.stop_on_reset = True
        self.exc = None                    # (esr, elr, far, spsr) while a controlled exception is being taken
        self.excs = []
        self.fault_off = None
        self._written = set()
        self.mmio_viol = []
        self.nmmio = 0
        self.polls = 0                     # entries into the engine's usbmon_poll made by the loader itself (not by the USB host model)
        self.poll_inject = None            # (n, pc): at the n-th loader poll, jump to pc instead (a controlled fault inside the poll)
        self.exc_t = []                    # simulated time of every controlled exception taken
        self.watched = {}                  # function name -> simulated times of its entries (watch())
        self._map_region()
        self.mu = mu = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
        mu.mem_map_ptr(REGION, REGION_SIZE, UC_ALL, REGION)
        for seg in elf.segments:
            ctypes.memmove(LOAD + seg["vaddr"], seg["data"], len(seg["data"]))
        for base, size in ((PMU, 0x10000), (WDT, 0x1000), (DECON, 0x10000), (FB, 0x900000)):
            mu.mem_map(base, size)
        mu.mem_write(DECON + 0x20, struct.pack("<I", 0x113))
        mu.mem_write(DECON + 0x30, struct.pack("<I", 0x3063))
        for off, v in (init or {}).items():
            mu.mem_write(PMU + off, struct.pack("<I", v))
        mu.mmio_map(GATE_LO, GATE_HI - GATE_LO, self._hsi_r, None, self._hsi_w, None)
        mu.mmio_map(CMU_LO, CMU_SIZE, self._cmu_r, None, self._cmu_w, None)
        mu.hook_add(unicorn.UC_HOOK_INSN, self._mrs, None, 1, 0, A.UC_ARM64_INS_MRS)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._pmu_w, None, PMU, PMU + 0xFFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_READ, self._pmu_r, None, PMU, PMU + 0xFFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._wdt_w, None, WDT, WDT + 0xFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_READ, self._wdt_r, None, WDT, WDT + 0xFFF)
        mu.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._draw_start, None, FB, FB + 7)
        mu.hook_add(unicorn.UC_HOOK_INTR, self._intr)
        poll = self.sym("usbmon_poll")                  # the engine's one entry point: nothing is half done when it is called
        mu.hook_add(unicorn.UC_HOOK_CODE, self._poll_entry, None, poll, poll)
        self._cb = POLL_CB(self._guest_poll)
        lib.h_set_poll_cb(self._cb)
        g = self.sym("g_nat047")
        lib.h_reset(g, g + lib.h_sizeof_dma())
        self.machine = Machine47(self)

    def watch(self, name):
        """Record the simulated time of every entry into the function (the loader's own thread and callbacks alike)."""
        a = self.sym(name)
        times = self.watched.setdefault(name, [])
        self.mu.hook_add(unicorn.UC_HOOK_CODE, lambda uc, addr, size, ud: times.append(self.t), None, a, a)

    # ------------------------------------------------------------------------------------------------ memory
    def _map_region(self):
        p = _libc.mmap(REGION, REGION_SIZE, 3, 0x22 | 0x100000, -1, 0)      # PROT_RW, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE
        if p != REGION:
            raise RegionUnavailable("cannot map %#x..%#x in this process" % (REGION, REGION + REGION_SIZE))

    def close(self):
        self.lib.h_set_poll_cb(POLL_CB(0))
        self.mu = None
        _libc.munmap(REGION, REGION_SIZE)

    def sym(self, name):
        return LOAD + self.elf.sym[name]

    def read(self, addr, n):
        return ctypes.string_at(addr, n)

    def write(self, addr, data):
        ctypes.memmove(addr, bytes(data), len(data))

    def u32(self, addr):
        return struct.unpack("<I", self.read(addr, 4))[0]

    def g(self, field, off, fmt="<I"):
        n = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read(self.sym(field) + off, n))[0]

    def seconds(self, t=None):
        return ((self.t if t is None else t) - self.t0) / FREQ

    # ------------------------------------------------------------------------------------------------ devices
    def _hsi_r(self, uc, off, size, ud):
        a = GATE_LO + off
        self.nmmio += 1
        if size != 4:
            self.mmio_viol.append("read of %d bytes @%#x" % (size, a))
        self.dev.t = self.t // 24
        if a in self.dev.regs:
            return self.dev.rd(a)
        self.dev._settle()
        self.dev._gate(a)
        if DWC3_LO <= a < DWC3_HI:
            return self.lib.h_rd32(a)
        self.mmio_viol.append("read of an unmodelled HSI0 address %#x" % a)
        return 0

    def _hsi_w(self, uc, off, size, value, ud):
        a = GATE_LO + off
        self.nmmio += 1
        if size != 4:
            self.mmio_viol.append("write of %d bytes @%#x" % (size, a))
        self.dev.t = self.t // 24
        value &= 0xFFFFFFFF
        if a in self.dev.regs:
            self.dev.wr(a, value)
            return
        self.dev._settle()
        self.dev._gate(a)
        if DWC3_LO <= a < DWC3_HI:
            self.lib.h_wr32(a, value)
            return
        self.mmio_viol.append("write of an unmodelled HSI0 address %#x" % a)

    def _cmu_r(self, uc, off, size, ud):
        self.nmmio += 1
        self.dev.t = self.t // 24
        return self.dev.rd(CMU_LO + off)

    def _cmu_w(self, uc, off, size, value, ud):
        self.nmmio += 1
        self.dev.t = self.t // 24
        self.dev.wr(CMU_LO + off, value & 0xFFFFFFFF)

    def _pmu_w(self, uc, access, addr, size, value, ud):
        off = addr - PMU
        value &= 0xFFFFFFFF
        if addr in self.dev.regs:                       # the ladder's power-domain registers live in the PMU window
            self.dev.t = self.t // 24
            self.dev.wr(addr, value)
            return
        self.pmu_events.append(("W", off, value, self.t))
        self._written.add(off)
        if off == REBOOT and value == 2:
            self.reset_t = self.t
            self.fb_at_reset = self.sample_fb()
            if self.stop_on_reset:
                self.stopped = True
                uc.emu_stop()

    def _pmu_r(self, uc, access, addr, size, value, ud):
        off = addr - PMU
        if addr in self.dev.regs:
            self.dev.t = self.t // 24
            uc.mem_write(addr, struct.pack("<I", self.dev.rd(addr)))
            return
        cur, = struct.unpack("<I", bytes(uc.mem_read(addr, 4)))
        if off == self.fault_off and off in self._written:
            cur ^= 1
            uc.mem_write(addr, struct.pack("<I", cur))
        self.pmu_events.append(("R", off, cur, self.t))

    def _wdt_w(self, uc, access, addr, size, value, ud):
        self.wdt_events.append(("W", addr - WDT, value & 0xFFFFFFFF, self.t))

    def _wdt_r(self, uc, access, addr, size, value, ud):
        off = addr - WDT
        cur, = struct.unpack("<I", bytes(uc.mem_read(addr, 4)))
        if off == 8:
            cur = max(1, cur - 1000)
            uc.mem_write(addr, struct.pack("<I", cur))
        self.wdt_events.append(("R", off, cur, self.t))

    def sample_fb(self):
        levels = [1.0 if bytes(self.mu.mem_read(FB + b * 0x40000, 8)) != b"\0" * 8 else 0.0 for b in range(dec.BANDS)]
        return dec.decode_bands(levels)

    def _draw_start(self, uc, access, addr, size, value, ud):
        f = self.sample_fb()
        if f:
            self.frames.append((f, self.t))

    def final_frames(self):
        f = self.sample_fb()
        return [x for x, _ in self.frames] + ([f] if f else [])

    def wdt_armed(self):
        return any(k == "W" and o == 0 and v & 0x21 == 0x21 for k, o, v, _ in self.wdt_events) or bool(self.wdt_events)

    # ------------------------------------------------------------------------------------------------ cpu hooks
    def _mrs(self, uc, reg, cp, ud):
        if (cp.crn, cp.crm, cp.op0, cp.op1) == (14, 0, 3, 3):
            if cp.op2 == 2:                                     # CNTVCT_EL0
                self.t += STEP_V
            elif cp.op2 == 1:                                   # CNTPCT_EL0
                self.t += STEP_P
            elif cp.op2 == 0:
                uc.reg_write(reg, FREQ)
                return True
            else:
                return False
            uc.reg_write(reg, self.t)
            return True
        if self.exc is not None and cp.op0 == 3 and cp.op1 == 0:
            esr, elr, far, spsr = self.exc
            val = {(5, 2, 0): esr, (4, 0, 1): elr, (6, 0, 0): far, (4, 0, 0): spsr}.get((cp.crn, cp.crm, cp.op2))
            if val is not None:
                uc.reg_write(reg, val)
                return True
        return False

    def _intr(self, uc, intno, ud):
        pc = uc.reg_read(A.UC_ARM64_REG_PC)
        insn, = struct.unpack("<I", self.read(pc, 4))
        self.excs.append((intno, pc, insn))
        self.exc_t.append(self.t)
        assert intno == 7 and insn & 0xFFE0001F == 0xD4200000, "unexpected exception %d at %#x (%#x)" % (intno, pc, insn)
        self.exc = ((BRK_ESR & ~0xFFFF) | ((insn >> 5) & 0xFFFF), pc, EXC_FAR, EXC_SPSR)       # ELR_EL1 = the BRK itself
        uc.reg_write(A.UC_ARM64_REG_PC, self.sym("vectors") + 0x200)                        # current EL, SPx, synchronous

    def _poll_entry(self, uc, addr, size, ud):
        if self.in_cb:
            return
        if self.t >= self.target:
            self.paused = True
            uc.emu_stop()
            return
        self.polls += 1
        if self.poll_inject and self.polls == self.poll_inject[0]:
            uc.reg_write(A.UC_ARM64_REG_PC, self.poll_inject[1])

    # ------------------------------------------------------------------------------------------------ the host calls the engine
    def _guest_poll(self):
        """Called by the model each time the USB host lets the device side run: the aarch64 usbmon_poll, on its own stack."""
        mu = self.mu
        ctx = mu.context_save()
        self.in_cb += 1
        try:
            mu.reg_write(A.UC_ARM64_REG_SP, CB_STACK_TOP)
            mu.reg_write(A.UC_ARM64_REG_X0, self.sym("g_nat047"))
            mu.reg_write(A.UC_ARM64_REG_X30, STOP)
            mu.emu_start(self.sym("usbmon_poll"), STOP, count=20_000_000)
        except unicorn.UcError as e:
            raise AssertionError("usbmon_poll: %s at pc=%#x" % (e, mu.reg_read(A.UC_ARM64_REG_PC)))
        finally:
            self.in_cb -= 1
            mu.context_restore(ctx)

    # ------------------------------------------------------------------------------------------------ the loader's own thread
    def queue_call(self, name, *args):
        self.queue.append((name, args))

    def _begin(self, name, args):
        mu = self.mu
        mu.reg_write(A.UC_ARM64_REG_SP, self.sym("_stack_top"))
        for i, a in enumerate(args):
            mu.reg_write(A.UC_ARM64_REG_X0 + i, a)
        mu.reg_write(A.UC_ARM64_REG_X30, STOP)
        self.pc, self.cur = (name, "%#x" % name) if isinstance(name, int) else (self.sym(name), name)

    def advance(self, target_s=None, target_t=None, slice_insn=20_000_000):
        """Run the loader's queued calls until simulated time reaches the target (stopping at the next engine poll), the queue
        is empty, or the reset trigger fired. An empty queue means the CPU is parked: time passes."""
        self.target = target_t if target_t is not None else self.t0 + int(target_s * FREQ)
        mu = self.mu
        while self.t < self.target and not self.stopped:
            if self.cur is None:
                if not self.queue:
                    self.t = self.target
                    break
                self._begin(*self.queue.pop(0))
            self.paused = False
            try:
                mu.emu_start(self.pc, STOP, count=slice_insn)
            except unicorn.UcError as e:
                raise AssertionError("%s: %s at pc=%#x (image offset %#x)" % (self.cur, e, mu.reg_read(A.UC_ARM64_REG_PC),
                                                                               mu.reg_read(A.UC_ARM64_REG_PC) - LOAD))
            self.pc = mu.reg_read(A.UC_ARM64_REG_PC)
            if not (self.paused or self.stopped or self.pc == STOP):      # the slice ran out of instructions: charge it
                self.insn_budget -= slice_insn
                assert self.insn_budget > 0, "instruction budget exhausted (the simulation does not make progress)"
            if self.pc == STOP:
                self.done_calls.append((self.cur, mu.reg_read(A.UC_ARM64_REG_X0)))
                self.done_polls.append(self.polls)
                self.cur = None
        return self.t

    def run_to_end(self, limit_s=200.0):
        self.advance(target_s=limit_s)
