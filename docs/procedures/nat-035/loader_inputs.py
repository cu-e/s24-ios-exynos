#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-035: give the NAT-030/033 model the kernel inputs the NAT-022 loader really writes.

NAT-030 wrote the kernel segments and a boot_args blob with only the memory fields and a zeroed ADT region; the ADT
bytes, `Video`, `CommandLine` and the real `deviceTreeLength` were never written (found in NAT-035: the kernel's
SecureDT lookups in the model all failed on the zero ADT). This module builds those inputs the way loader.c does:

  * the ADT is the payload's ADT after the loader's own patch functions (`adt_patch.c`, compiled for the host with gcc
    and driven in loader.c's order: boot-CPU MPIDR, dram, pram, ramdisk rebase);
  * boot_args is filled as loader.c fills it: Revision/Version 2, virtBase, physBase, memSize, topOfKernelData,
    Video, deviceTreeP, deviceTreeLength = the (padded) ADT size, CommandLine = cmdline_xnu() of the payload's command
    line, memSizeActual.

What is assumed, not measured (the loader reads them from the phone at run time and run 009 did not report them):
the boot CPU's MPIDR_EL1 value and the framebuffer geometry. Both are parameters here, with defaults that are labelled
as assumptions in the output of `describe()`. Host only; reads local artifacts; writes only the cache directory.
"""
import hashlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "docs/procedures/nat-033"))
import c11  # noqa: E402
import simd as sd  # noqa: E402

a5, ks = sd.a5, sd.ks
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source/shim/e1s-xnu"
# The payload the ckpt2 image carries: the NAT-020 payload with the NAT-026 adt_size padding (13956 -> 13960).
FIXED_PAYLOAD = ROOT / "artifacts/nat-034/build-001/loader-diag-xnu-ckpt2/payload.adt8.bin"
PAGE_16K = 0x4000
BOOT_LINE_LENGTH = 608
CMDLINE_OFF = 72                  # struct payload: magic[8] version nsegs virt_base entry adt_off adt_size kernel_end phys_base mem_size
BA = dict(Revision=0, Version=2, virtBase=8, physBase=16, memSize=24, topOfKernelData=32, v_baseAddr=40,
          v_display=48, v_rowBytes=56, v_width=64, v_height=72, v_depth=80, machineType=88, deviceTreeP=96,
          deviceTreeLength=104, CommandLine=108, bootFlags=716, memSizeActual=728)

# Assumed values (the loader reads them from the phone). The model only needs them to be self-consistent: the
# ADT's boot-CPU reg and MPIDR_EL1 come from the same register on the phone.
ASSUMED_MPIDR = 0x80000000
ASSUMED_FB = dict(base=0xFA200000, width=1080, height=2340, stride=4320)   # base measured; geometry assumed

_DRIVER = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "adt_patch.h"
int main(int c, char **v)
{
  FILE *f = fopen(v[1], "rb"); size_t n = strtoul(v[2], 0, 0);
  unsigned char *raw = malloc(n + 64), *adt = raw + 16;
  if (!f || fread(adt, 1, n, f) != n) return 2;
  uint64_t wb = strtoull(v[3], 0, 0), ws = strtoull(v[4], 0, 0), phys = strtoull(v[5], 0, 0);
  uint32_t mpidr = (uint32_t)strtoul(v[6], 0, 0);
  uint64_t pb = (wb + ws - 0x100000ULL) & ~(16384ULL - 1);
  int r[4];
  r[0] = adt_set_boot_cpu_mpidr((uintptr_t)adt, n, mpidr);
  r[1] = adt_set_dram((uintptr_t)adt, n, wb, ws);
  r[2] = adt_set_pram((uintptr_t)adt, n, pb, 0x80000);
  r[3] = adt_rebase_ramdisk((uintptr_t)adt, n, (int64_t)(wb - phys));
  fprintf(stderr, "%d %d %d %d\n", r[0], r[1], r[2], r[3]);
  fwrite(adt, 1, n, stdout);
  return 0;
}
"""


def cmdline_xnu(src: bytes) -> bytes:
    """loader.c cmdline_xnu(): drop an `e1s.hold=N` word, trim trailing spaces, NUL-terminated, BOOT_LINE_LENGTH."""
    s = src.split(b"\0")[0]
    out = bytearray()
    i = 0
    while i < len(s) and len(out) < BOOT_LINE_LENGTH - 1:
        if (i == 0 or s[i - 1:i] == b" ") and s[i:].startswith(b"e1s.hold="):
            j = i + 9
            while j < len(s) and s[j:j + 1].isdigit():
                j += 1
            while j < len(s) and s[j:j + 1] == b" ":
                j += 1
            i = j
            continue
        out.append(s[i])
        i += 1
    while out and out[-1:] == b" ":
        out.pop()
    return bytes(out)


def patched_adt(payload_path, win_base, win_size, mpidr, workdir):
    """The payload's ADT after loader.c's adt_set_* calls, using the real adt_patch.c compiled with gcc."""
    p = ks.Payload(str(payload_path)) if hasattr(ks, "Payload") else sd.a5.ap.Payload(str(payload_path))
    adt = p.b[p.adt_off:p.adt_off + p.adt_size]
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    (work / "driver.c").write_text(_DRIVER)
    (work / "adt.in").write_bytes(adt)
    exe = work / "adtdrv"
    r = subprocess.run(["gcc", "-O1", "-I", str(LOADER_SRC), "-o", str(exe), str(work / "driver.c"),
                        str(LOADER_SRC / "adt_patch.c")], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("gcc: " + r.stderr[:400])
    r = subprocess.run([str(exe), str(work / "adt.in"), str(len(adt)), hex(win_base), hex(win_size), hex(p.phys_base),
                        hex(mpidr)], capture_output=True)
    if r.returncode or r.stderr.split() != [b"0"] * 4:
        raise RuntimeError("adt_patch driver: rc=%d %r" % (r.returncode, r.stderr))
    return r.stdout


class LoaderEqual(c11.Probe):
    """The NAT-033 probe with the loader's ADT and boot_args in RAM and the assumed boot-CPU MPIDR_EL1."""

    def __init__(self, payload_path=FIXED_PAYLOAD, window_base=a5.BASE, window_size=a5.SIZE, names=None,
                 mpidr=ASSUMED_MPIDR, fb=None, workdir=None, adt_reg=None):
        fb = dict(ASSUMED_FB, **(fb or {}))
        self._tmp = None
        if workdir is None:
            self._tmp = tempfile.TemporaryDirectory()
            workdir = self._tmp.name
        super().__init__(str(payload_path), window_base, window_size, names=names)
        p = self.p
        raw = p.b[CMDLINE_OFF:CMDLINE_OFF + BOOT_LINE_LENGTH]
        self.mpidr = mpidr
        # loader.c passes (uint32_t)gi.mpidr, the whole register, to adt_set_boot_cpu_mpidr; `adt_reg` overrides that
        # (NAT-035 tests the kernel with the value ml_get_cpu_number_local() compares against: MPIDR_EL1 & 0xffff)
        self.adt_reg = (mpidr & 0xFFFFFFFF) if adt_reg is None else adt_reg
        adt = patched_adt(payload_path, window_base, window_size, self.adt_reg, workdir)
        self.adt_pa = window_base + (p.kernel_end - p.virt_base)
        ba_pa = (self.adt_pa + p.adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1)
        if ba_pa != self.ba_pa:       # NAT-030 hard-codes the measured run-007 value; they must agree for this payload
            raise RuntimeError("boot_args base %#x != loader formula %#x" % (self.ba_pa, ba_pa))
        self.write_pa(self.adt_pa, adt)
        blob = bytearray(c11.ks.BOOT_ARGS_SIZE)
        struct.pack_into("<H", blob, BA["Revision"], 2)
        struct.pack_into("<H", blob, BA["Revision"] + 2, 2)
        for k, v in (("virtBase", p.virt_base), ("physBase", window_base), ("memSize", window_size),
                     ("topOfKernelData", ba_pa + PAGE_16K), ("v_baseAddr", fb["base"]), ("v_display", 1),
                     ("v_rowBytes", fb["stride"]), ("v_width", fb["width"]), ("v_height", fb["height"]),
                     ("v_depth", 32), ("deviceTreeP", p.virt_base + (self.adt_pa - window_base)),
                     ("memSizeActual", window_size)):
            struct.pack_into("<Q", blob, BA[k], v)
        struct.pack_into("<I", blob, BA["deviceTreeLength"], p.adt_size)
        cl = cmdline_xnu(bytes(raw))
        blob[BA["CommandLine"]:BA["CommandLine"] + len(cl)] = cl
        self.write_pa(ba_pa, bytes(blob))
        self.adt_bytes = adt
        self.cmdline = cl
        self.boot_args_blob = bytes(blob)
        self.sr["mpidr_el1"] = mpidr


def describe(sim):
    return dict(adt_pa=hex(sim.adt_pa), adt_len=len(sim.adt_bytes), adt_sha256=hashlib.sha256(sim.adt_bytes).hexdigest(),
                ba_pa=hex(sim.ba_pa), cmdline=sim.cmdline.decode("latin1"), mpidr_assumed=hex(sim.mpidr),
                boot_args_sha256=hashlib.sha256(sim.boot_args_blob).hexdigest())


if __name__ == "__main__":
    img = a5.Image()
    s = LoaderEqual(names=img)
    import json
    print(json.dumps(describe(s), indent=1))
