"""ctypes front end of the NAT-045 host platform (test_support/plat.c): builds the ladder (src/ladder.c, src/ladder_usb.c), the
NAT-041 engine and the NAT-041 DWC3 model into one shared library, with MMIO routed through plat.c's register file.

Two builds: default (no LAD_WRITING_RUNGS: the image that may not write) and writing. `ladder_dir` overrides src/ (mutation tests
build a mutated copy of ladder.c / ladder_regs.h / ladder_usb.c from a temp directory).
One library = one simulated machine (global state in C).
"""
import ctypes
import hashlib
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAT045 = os.path.dirname(HERE)
SRC = os.environ.get("NAT045_SRC") or os.path.join(NAT045, "src")      # mutation runs point this at a mutated copy
JSON = os.environ.get("NAT045_JSON") or os.path.join(NAT045, "ladder_ops.json")
NAT041 = os.path.join(os.path.dirname(NAT045), "nat-041")
ENGINE = os.path.join(NAT041, "engine")
MODEL = os.path.join(NAT041, "model")

CFLAGS = ["-std=gnu11", "-fPIC", "-O1", "-g", "-Wall", "-Wextra", "-DUSBMON_TESTING", '-DUSBMON_PORT_HEADER="plat_port.h"']
MODEL_RENAMES = ["-Dusbmon_rd32=model_rd32", "-Dusbmon_wr32=model_wr32", "-Dusbmon_delay_us=model_delay_us", "-Dusbmon_ticks=model_ticks"]


def build(writing=False, ladder_dir=None, out_dir=None, engine_src=None):
    """Compile and return the path of the shared library; any warning is an error."""
    ladder_dir = ladder_dir or SRC
    out_dir = out_dir or tempfile.mkdtemp(prefix="nat045-")
    engine_src = engine_src or os.path.join(ENGINE, "usbmon.c")
    srcs = [os.path.join(ladder_dir, n) for n in ("ladder.c", "ladder_usb.c", "ladder.h", "ladder_regs.h")]
    h = hashlib.sha256()
    for f in srcs + [engine_src, os.path.join(HERE, "plat.c"), os.path.join(HERE, "plat_port.h")]:
        h.update(open(f, "rb").read())
    h.update(repr(writing).encode())
    out = os.path.join(out_dir, "libplat-%s.so" % h.hexdigest()[:12])
    if os.path.exists(out):
        return out
    flags = CFLAGS + (["-DLAD_WRITING_RUNGS"] if writing else [])
    inc = ["-I", ladder_dir, "-I", HERE, "-I", ENGINE, "-I", MODEL]
    objs = []
    jobs = [(os.path.join(ladder_dir, "ladder.c"), []), (os.path.join(ladder_dir, "ladder_usb.c"), []),
            (os.path.join(HERE, "plat.c"), []), (engine_src, []), (os.path.join(MODEL, "model.c"), MODEL_RENAMES)]
    for n, (src, extra) in enumerate(jobs):
        o = os.path.join(out_dir, "%s-%d-%s.o" % (os.path.basename(src), n, h.hexdigest()[:8]))
        r = subprocess.run(["cc", "-c"] + flags + extra + inc + [src, "-o", o], capture_output=True, text=True)
        if r.returncode != 0 or r.stderr.strip():
            raise RuntimeError("build of %s failed or warned (%d):\n%s" % (src, r.returncode, r.stderr))
        objs.append(o)
    r = subprocess.run(["cc", "-shared"] + objs + ["-o", out], capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        raise RuntimeError("link failed (%d):\n%s" % (r.returncode, r.stderr))
    return out


KINDS = ["RD", "WRP", "WRM", "WAIT", "LOAD", "SET", "CONST", "STORE", "RDLOG", "DELAY"]
F_POWERON, F_NOTALIVE, F_SOFT, F_CMUINIT, F_DWC3ID = 0x1, 0x2, 0x4, 0x8, 0x10


def ops(ladder_dir=None):
    """The op table exactly as the compiled code sees it: parsed from ladder_regs.h. [{i, kind, rung, flags, addr, mask, val, val2, label}]"""
    import re
    with open(os.path.join(ladder_dir or SRC, "ladder_regs.h")) as f:
        text = f.read()
    flag_names = dict(re.findall(r"#define (LAD_F_\w+)\s+(0x[0-9a-f]+)", text))
    out = []
    for m in re.finditer(r"/\*\s*(\d+) L(\d) (.*?)\s*\*/ \{ LK_(\w+), (\d+), ([^,]+), (0x[0-9a-f]+)u, (0x[0-9a-f]+)u, (0x[0-9a-f]+)u, (0x[0-9a-f]+)u \}", text):
        i, rung, label, kind, rung2, flags, addr, mask, val, val2 = m.groups()
        fl = 0
        for f in flags.split("|"):
            f = f.strip()
            fl |= int(flag_names[f], 16) if f != "0" else 0
        assert int(rung) == int(rung2)
        out.append(dict(i=int(i), kind=kind, rung=int(rung), flags=fl, addr=int(addr, 0), mask=int(mask, 0), val=int(val, 0),
                        val2=int(val2, 0), label=label.strip()))
    assert [o["i"] for o in out] == list(range(len(out)))
    return out


def ops_json():
    with open(JSON) as f:
        d = json.load(f)
    return d, {k: int(v, 0) for k, v in d["bases"].items()}


PMU_CFG, PMU_STATUS = 0x12862000, 0x12862004

LAD_ERR_NAMES = {1: "readback", 2: "timeout", 3: "state", 4: "notalive", 5: "cfg", 6: "disabled"}


def decode_err(e):
    """(rung, code-name) of a ladder stop code, (0, 'ok') for 0."""
    if e == 0:
        return (0, "ok")
    return ((-e) // 16, LAD_ERR_NAMES.get((-e) % 16, "code%d" % ((-e) % 16)))


class Plat:
    _libpath = None

    def __init__(self, libpath):
        lib = ctypes.CDLL(libpath)
        u32, u32p = ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)
        lib.plat_def.argtypes = [u32, u32]
        lib.plat_strict.argtypes = [ctypes.c_int]
        for n in ("plat_ro", "plat_defined"):
            getattr(lib, n).argtypes = [u32]
        lib.plat_stuck.argtypes = [u32, u32, u32]
        lib.plat_selfclear.argtypes = [u32, u32]
        lib.plat_flip.argtypes = [u32, u32]
        lib.plat_flip_from.argtypes = [u32, u32, u32]
        lib.plat_get.argtypes = [u32]
        lib.plat_get.restype = u32
        lib.plat_follow.argtypes = [u32, u32, u32, u32, u32]
        lib.plat_gate.argtypes = [u32, u32]
        lib.plat_dwc3_overlay.argtypes = [u32, u32, u32]
        lib.plat_now.restype = ctypes.c_uint64
        lib.plat_nlog.restype = ctypes.c_uint
        lib.plat_log.argtypes = [ctypes.c_uint, u32p, u32p, u32p, ctypes.POINTER(ctypes.c_uint64)]
        lib.plat_nviol.restype = ctypes.c_uint
        lib.plat_viol.argtypes = [ctypes.c_uint]
        lib.plat_viol.restype = ctypes.c_char_p
        for n in ("n_nops", "n_default_stop", "n_default_poweron", "n_selfcheck", "n_err", "n_err_op", "n_nrec", "n_rung_done",
                  "n_pd_was_on", "n_soft", "n_usb_flags", "n_run_null"):
            getattr(lib, n).restype = ctypes.c_int
        lib.n_usb_flags.restype = u32
        lib.n_run.argtypes = [u32, u32, u32]
        lib.n_run.restype = ctypes.c_int
        lib.n_rec.argtypes = [ctypes.c_int, u32p, u32p, u32p]
        lib.n_gsnpsid.restype = u32
        lib.n_sizeof_state.restype = u32
        lib.n_usb_new.argtypes = [u32]
        lib.n_usb_start.argtypes = [ctypes.c_char_p, u32]
        lib.n_usb_start.restype = ctypes.c_int
        lib.n_usb_wait.argtypes = [ctypes.c_uint, u32, u32, u32]
        lib.n_usb_wait.restype = ctypes.c_int
        lib.model_set_id.argtypes = [u32]
        lib.model_bus_reset.argtypes = [ctypes.c_int]
        lib.model_ctrl.restype = ctypes.c_int
        lib.model_ctrl.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_char_p,
                                   ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int)]
        self.lib = lib

    # -- fixture
    def reset(self):
        self.lib.plat_reset()

    def declare(self, addr, val=0):
        self.lib.plat_def(addr, val)

    def get(self, addr):
        return self.lib.plat_get(addr)

    def standard_fixture(self, pd_on=False, pd_delay_us=50, strict=True, follow=True):
        """Every register of the op table declared with a plausible value; HSI0 PMU config/status follow each other after
        pd_delay_us; the HSI0 block is gated by HSI0_STATUS bit 0. Values the ladder is supposed to write are not pre-set."""
        self.reset()
        table = ops()
        for o in table:
            if o["kind"] not in ("SET", "CONST", "DELAY"):
                self.declare(o["addr"], 0x00010203 if o["flags"] & F_NOTALIVE else 0)
        # QCH / CMU registers read non-zero when alive; the PMU pair says on/off
        self.declare(PMU_CFG, 1 if pd_on else 0)
        self.declare(PMU_STATUS, 1 if pd_on else 0)
        if follow:
            self.lib.plat_follow(PMU_CFG, 1, PMU_STATUS, 1, pd_delay_us)
        self.lib.plat_gate(PMU_STATUS, 1)
        self.lib.plat_strict(1 if strict else 0)
        return table

    # -- run
    def run(self, stop=None, allow_poweron=1, pd_wait_us=0):
        stop = self.lib.n_default_stop() if stop is None else stop
        rc = self.lib.n_run(stop, allow_poweron, pd_wait_us)
        return rc

    def state(self):
        recs = []
        v0, v1, op = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32()
        for i in range(self.lib.n_nrec()):
            self.lib.n_rec(i, ctypes.byref(op), ctypes.byref(v0), ctypes.byref(v1))
            recs.append((op.value, v0.value, v1.value))
        return dict(err=self.lib.n_err(), err_op=self.lib.n_err_op(), rung_done=self.lib.n_rung_done(), pd_was_on=self.lib.n_pd_was_on(),
                    soft=self.lib.n_soft(), gsnpsid=self.lib.n_gsnpsid(), recs=recs)

    def log(self):
        """[(kind 'R'/'W', addr, value, virtual_us)] of every platform access in order."""
        out = []
        k, a, v, t = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint64()
        for i in range(self.lib.plat_nlog()):
            self.lib.plat_log(i, ctypes.byref(k), ctypes.byref(a), ctypes.byref(v), ctypes.byref(t))
            out.append(("W" if k.value else "R", a.value, v.value, t.value))
        return out

    def violations(self):
        return [self.lib.plat_viol(i).decode() for i in range(min(self.lib.plat_nviol(), 32))]
