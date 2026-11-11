"""ctypes front end of the NAT-041 host model: builds engine/usbmon.c + model/model.c into a shared library and exposes the
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

CC_FLAGS = ["-shared", "-fPIC", "-O1", "-g", "-Wall", "-Wextra", "-DUSBMON_TESTING", '-DUSBMON_PORT_HEADER="host_port.h"']


def build(engine_src=None, out_dir=None, extra=(), strict=True):
    """Compile and return the path of the shared library. engine_src overrides engine/usbmon.c (mutation tests)."""
    engine_src = engine_src or os.path.join(ENGINE, "usbmon.c")
    out_dir = out_dir or tempfile.mkdtemp(prefix="nat041-")
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
            lib.t_init.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint8]
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
                 lpm=1, auto_init=True):
        self.lib = self.load(libpath)
        self.ring_size = ring_size
        self.boot_id = boot_id
        self.lib.t_new(ring_size)
        self.init_rc = None
        if auto_init:
            self.init_rc = self.lib.t_init(boot_id, ring_size, refclk, fladj, lpm)

    def close(self):
        self.lib.t_free()

    # -- engine side
    def init(self, **kw):
        return self.lib.t_init(kw.get("boot_id", self.boot_id), self.ring_size, kw.get("refclk", 19200000),
                               kw.get("fladj", 0x20), kw.get("lpm", 1))

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
