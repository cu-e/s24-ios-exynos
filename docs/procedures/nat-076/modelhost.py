"""ctypes front end of the NAT-076 host model (the NAT-041 model plus one bulk-OUT endpoint and a receive destination): builds engine/usbmon.c + model/model.c into a shared library and exposes the
simulated DWC3 controller, the simulated non-coherent cache and the USB host to Python.

One library = one simulated machine; a process that needs a fresh machine calls Machine.new() again (the C side keeps a
single global fixture, so only one Machine is live at a time).
"""
import ctypes
import hashlib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine")
MODEL = os.path.join(HERE, "model")

H_OK, H_STALL, H_TIMEOUT, H_NAKLOOP, H_PROTO = 0, 1, -1, -2, -3
RC_NAMES = {H_OK: "ok", H_STALL: "stall", H_TIMEOUT: "timeout", H_NAKLOOP: "nak-loop", H_PROTO: "protocol-error"}

# -ftrivial-auto-var-init=pattern: an automatic variable the engine forgets to initialise holds 0xFE.. instead of whatever the stack had
CC_FLAGS = ["-shared", "-fPIC", "-O1", "-g", "-Wall", "-Wextra", "-ftrivial-auto-var-init=pattern", "-DUSBMON_TESTING",
            '-DUSBMON_PORT_HEADER="host_port.h"']


def build(engine_src=None, out_dir=None, extra=(), strict=True):
    """Compile and return the path of the shared library. engine_src overrides engine/usbmon.c (mutation tests)."""
    engine_src = engine_src or os.path.join(ENGINE, "usbmon.c")
    out_dir = out_dir or tempfile.mkdtemp(prefix="nat076-")
    with open(engine_src, "rb") as f:
        tag = hashlib.sha256(f.read() + repr(extra).encode()).hexdigest()[:12]
    out = os.path.join(out_dir, "libmodel-%s.so" % tag)
    if not os.path.exists(out):
        cmd = ["cc"] + CC_FLAGS + list(extra) + ["-I", ENGINE, "-I", MODEL, engine_src, os.path.join(MODEL, "model.c"),
                                                 "-o", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or (strict and r.stderr.strip()):
            raise RuntimeError("model build failed or warned (%d):\n%s" % (r.returncode, r.stderr))
    return out


class Machine:
    _lib = None
    _libpath = None

    @classmethod
    def load(cls, libpath):
        if cls._libpath != libpath:
            lib = ctypes.CDLL(libpath)
            u8p = ctypes.POINTER(ctypes.c_uint8)
            lib.t_new.restype = ctypes.c_void_p
            lib.t_new.argtypes = [ctypes.c_uint32]
            lib.t_init.restype = ctypes.c_int
            lib.t_init.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint8,
                                   ctypes.c_uint64, ctypes.c_uint8]
            lib.t_set_window.argtypes = [ctypes.c_uint64]
            lib.t_window_read.restype = ctypes.c_int
            lib.t_window_read.argtypes = [ctypes.c_uint64, u8p, ctypes.c_uint64]
            lib.t_window_poke.argtypes = [ctypes.c_uint64, ctypes.c_char_p, ctypes.c_uint64]
            lib.model_bulk_out.restype = ctypes.c_int
            lib.model_bulk_out.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
            lib.model_bulk_fault.argtypes = [ctypes.c_int, ctypes.c_uint32]
            lib.model_set_dma_limit.argtypes = [ctypes.c_uint64]
            lib.model_dest_cpu_dirty.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
            lib.model_dma_blocked.restype = ctypes.c_uint64
            lib.t_rx_state.restype = ctypes.c_uint32
            lib.t_ep_started.restype = ctypes.c_uint32
            lib.t_ep_started.argtypes = [ctypes.c_uint32]
            lib.t_rxtrb.restype = ctypes.c_uint32
            lib.t_rxtrb.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
            lib.model_stage_cpu_dirty.argtypes = [ctypes.c_uint64]
            lib.model_end_hw_transfer.argtypes = [ctypes.c_uint]
            lib.t_rx_spurious.restype = ctypes.c_uint32
            lib.t_log.argtypes = [ctypes.c_uint8, ctypes.c_char_p, ctypes.c_uint16]
            lib.t_text.argtypes = [ctypes.c_char_p]
            lib.t_stage.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
            lib.t_log_interrupted.argtypes = [ctypes.c_uint8, ctypes.c_char_p, ctypes.c_uint16, ctypes.c_uint32]
            lib.t_fault.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
            for n in ("t_written", "t_oldest"):
                getattr(lib, n).restype = ctypes.c_uint64
            for n in ("t_seq", "t_flags", "t_dropped", "t_stalls", "t_sizeof_usbmon", "t_dma_misaligned"):
                getattr(lib, n).restype = ctypes.c_uint32
            lib.t_last_err.restype = ctypes.c_int32
            lib.t_ring_copy.argtypes = [ctypes.c_uint64, u8p, ctypes.c_uint32]
            lib.model_ctrl.restype = ctypes.c_int
            lib.model_ctrl.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16,
                                       ctypes.c_char_p, u8p, ctypes.POINTER(ctypes.c_int)]
            lib.model_setup.restype = ctypes.c_int
            lib.model_setup.argtypes = [ctypes.c_char_p]
            lib.model_data_in.restype = ctypes.c_int
            lib.model_data_in.argtypes = [ctypes.c_uint, u8p, ctypes.POINTER(ctypes.c_int)]
            lib.model_data_out.restype = ctypes.c_int
            lib.model_data_out.argtypes = [ctypes.c_char_p, ctypes.c_uint]
            lib.model_status.restype = ctypes.c_int
            lib.model_status.argtypes = [ctypes.c_int, ctypes.c_int]
            lib.model_viol.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
            lib.model_wtrace.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
            lib.model_ctrace.argtypes = [ctypes.c_int] + [ctypes.POINTER(ctypes.c_uint32)] * 6
            lib.model_set_host.argtypes = [ctypes.c_int, ctypes.c_int]
            lib.model_set_id.argtypes = [ctypes.c_uint32]
            lib.t_set_stream_base.argtypes = [ctypes.c_uint64]
            lib.model_set_prefetch.argtypes = [ctypes.c_int]
            lib.model_bus_reset.argtypes = [ctypes.c_int]
            cls._lib, cls._libpath = lib, libpath
        return cls._lib

    def __init__(self, libpath, ring_size=4096, boot_id=b"BOOTID-0123456789"[:16], refclk=19200000, fladj=0x20,
                 lpm=1, auto_init=True, rx_size=0, rx_direct=False):
        self.lib = self.load(libpath)
        self.ring_size = ring_size
        self.boot_id = boot_id
        self.rx_size = rx_size
        self.rx_direct = rx_direct
        self.lib.t_new(ring_size)
        self.init_rc = None
        if auto_init:
            self.init_rc = self.lib.t_init(boot_id, ring_size, refclk, fladj, lpm, rx_size, 1 if rx_direct else 0)

    def close(self):
        self.lib.t_free()

    # -- engine side
    def init(self, **kw):
        return self.lib.t_init(kw.get("boot_id", self.boot_id), self.ring_size, kw.get("refclk", 19200000),
                               kw.get("fladj", 0x20), kw.get("lpm", 1), kw.get("rx_size", self.rx_size),
                               1 if kw.get("rx_direct", self.rx_direct) else 0)

    def poll(self, n=1):
        self.lib.t_poll(n)

    def log(self, kind, data):
        self.lib.t_log(kind, bytes(data), len(data))

    def text(self, s):
        self.lib.t_text(s.encode())

    def stage(self, n, s):
        self.lib.t_stage(n, s.encode())

    def log_interrupted(self, kind, data, ncopied):
        self.lib.t_log_interrupted(kind, bytes(data), len(data), ncopied)

    def fault(self, esr=0x96000045, elr=0xfffffff007004000, far=0x1000, spsr=0x3c5, sp=0xfffffff0070f0000, x=None):
        x = list(x) if x is not None else [0x1111111100000000 + i for i in range(31)]
        arr = (ctypes.c_uint64 * 36)(esr, elr, far, spsr, sp, *x)
        self.lib.t_fault(arr)

    @property
    def written(self): return self.lib.t_written()
    @property
    def oldest(self): return self.lib.t_oldest()
    @property
    def seq(self): return self.lib.t_seq()
    @property
    def flags(self): return self.lib.t_flags()
    @property
    def dropped(self): return self.lib.t_dropped()
    @property
    def stalls(self): return self.lib.t_stalls()
    @property
    def last_err(self): return self.lib.t_last_err()

    def ring_bytes(self, pos, n):
        buf = (ctypes.c_uint8 * n)()
        self.lib.t_ring_copy(pos, buf, n)
        return bytes(buf)

    # -- host side
    def attach(self): self.lib.model_attach()
    def bus_reset(self, conndone=True): self.lib.model_bus_reset(1 if conndone else 0)
    def detach(self): self.lib.model_detach()
    def set_host(self, polls_per_step=2, timeout_steps=40): self.lib.model_set_host(polls_per_step, timeout_steps)

    def ctrl(self, bm, req, value=0, index=0, length=0, data=b""):
        """-> (rc, bytes): rc is one of H_*; bytes is the IN data received (b'' for OUT or on failure)."""
        buf = (ctypes.c_uint8 * 4200)()
        got = ctypes.c_int(0)
        rc = self.lib.model_ctrl(bm, req, value, index, length, bytes(data), buf, ctypes.byref(got))
        return rc, bytes(buf[:got.value])

    def setup_only(self, s8): return self.lib.model_setup(bytes(s8))

    def enumerate(self, address=5):
        """What a USB host does first: device descriptor, SET_ADDRESS, device descriptor again, configuration, SET_CONFIGURATION."""
        steps = []
        rc, d = self.ctrl(0x80, 6, 0x0100, 0, 8)
        steps.append(("get_descriptor_8", rc, d))
        rc, d = self.ctrl(0x00, 5, address, 0, 0)
        steps.append(("set_address", rc, d))
        rc, d = self.ctrl(0x80, 6, 0x0100, 0, 18)
        steps.append(("get_descriptor_18", rc, d))
        rc, d = self.ctrl(0x80, 6, 0x0200, 0, 9)
        steps.append(("get_config_9", rc, d))
        rc, d = self.ctrl(0x80, 6, 0x0200, 0, 18)
        steps.append(("get_config_18", rc, d))
        rc, d = self.ctrl(0x00, 9, 1, 0, 0)
        steps.append(("set_configuration", rc, d))
        return steps

    # -- bulk-OUT endpoint and receive destination (NAT-076)
    def bulk_out(self, data):
        """One bulk-OUT transfer of len(data) bytes. -> (rc, accepted): rc is one of H_*."""
        n = ctypes.c_uint32(0)
        rc = self.lib.model_bulk_out(bytes(data), len(data), ctypes.byref(n))
        return rc, n.value

    def bulk_fault(self, kind, after=0):
        """kind 1: DMA bus error (event status BUSERR) after `after` bytes of the next TRB; kind 2: TRB status error (TRBSTS 3); kind 3: the TRB
        ends early with status OK, no event status bit and a residual (what no real controller does; it tests the engine's own residual
        check); kinds 4, 5, 6: all bytes arrive but exactly one completion signal reports an error (event BUSERR / TRBSTS 3 /
        event SHORT); 0: none."""
        self.lib.model_bulk_fault(kind, after)

    def set_dma_limit(self, off):
        """The controller's DMA writes into the destination are silently lost from window offset `off` on (0 = no limit): the
        S2MPU/PMMU case of NAT-040 item U5."""
        self.lib.model_set_dma_limit(off)

    def hold_endxfer(self, on=True):
        """Withhold the command-complete event of ENDTRANSFER (the vendor's DWC3_EP_END_TRANSFER_PENDING window) until release_held()."""
        self.lib.model_hold_endxfer(1 if on else 0)

    def release_held(self): self.lib.model_release_held()

    @property
    def held(self): return bool(self.lib.model_held())

    def inject_ep_event(self, ep, kind, status=0, params=0):
        """An endpoint event the controller was never asked for. kind is the DEPEVT_* number (XferComplete 1, XferInProgress 2)."""
        self.lib.model_inject_ep_event(ep, kind, status, params)

    def end_hw_transfer(self, ep):
        """The controller ended the transfer on endpoint ep by itself (follow with inject_ep_event(ep, 1) for its XferComplete)."""
        self.lib.model_end_hw_transfer(ep)

    def fail_next_cmd(self, code):
        """The next endpoint command with this DEPCMD code (e.g. 7 UPDATETRANSFER, 9 STARTTRANSFER) fails once with a bad status, without
        counting as a model violation."""
        self.lib.model_fail_next_cmd(code)

    def dma_blocked(self): return self.lib.model_dma_blocked()
    def dest_cpu_dirty(self, off, n): self.lib.model_dest_cpu_dirty(off, n)

    def stage_cpu_dirty(self, n):
        """The CPU holds the first n bytes of the staging block (staged mode) as dirty cache lines with stale content."""
        self.lib.model_stage_cpu_dirty(n)

    def trb_slot(self, i):
        """The four words (bpl, bph, size, ctrl) of slot i of the bulk-OUT TRB ring, as memory holds them."""
        return tuple(self.lib.t_rxtrb(i, w) for w in range(4))

    def engine_ep_started(self, ep):
        """The engine's own record that endpoint ep has an active transfer (compare with model_ep_started: the controller's)."""
        return self.lib.t_ep_started(ep)

    def hw_ep_started(self, ep):
        return self.lib.model_ep_started(ep)

    def dest(self, off, n):
        buf = (ctypes.c_uint8 * n)()
        if self.lib.t_window_read(off, buf, n) != 0:
            raise ValueError("destination read out of range")
        return bytes(buf)

    def dest_poke(self, off, data): self.lib.t_window_poke(off, bytes(data), len(data))
    @property
    def rx_state(self): return self.lib.t_rx_state()
    @property
    def rx_spurious(self): return self.lib.t_rx_spurious()

    def violations(self):
        out = []
        buf = ctypes.create_string_buffer(256)
        for i in range(self.lib.model_nviol()):
            self.lib.model_viol(i, buf, 256)
            out.append(buf.value.decode())
        return out

    def clear_violations(self): self.lib.model_clear_viol()

    def write_trace(self):
        out = []
        off, val = ctypes.c_uint32(), ctypes.c_uint32()
        for i in range(self.lib.model_wtrace_n()):
            self.lib.model_wtrace(i, ctypes.byref(off), ctypes.byref(val))
            out.append((off.value, val.value))
        return out

    def cmd_trace(self):
        out = []
        v = [ctypes.c_uint32() for _ in range(6)]
        for i in range(self.lib.model_ctrace_n()):
            self.lib.model_ctrace(i, *[ctypes.byref(x) for x in v])
            out.append(tuple(x.value for x in v))
        return out


if __name__ == "__main__":
    p = build()
    m = Machine(p)
    print("init", m.init_rc)
    m.attach()
    for s in m.enumerate():
        print(s[0], RC_NAMES.get(s[1], s[1]), s[2][:20].hex())
    print("violations", m.violations())
    sys.exit(0)
