#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-036: derive the loader source of loader-diag-xnu-ckpt3 from a copy of the NAT-020 build-003 source.

Host only. usage: patch_loader3.py SOURCE_ROOT   (a copy of build-003/source, already NAT-010-patched)

Step 1 is NAT-022's patch_loader.main with the loader-diag-xnu-ckpt2 options (--trig-hold --adt-aligned --ckpt2), unchanged.
Step 2 changes two things in loader.c, each anchored on text that must match exactly once:

  * the ADT boot-CPU `reg` value. NAT-035 found that the loader wrote the full MPIDR_EL1 (bit 31 is RES1: 0x8000xxxx) into the
    boot CPU node's `reg`, while the kernel's cpu_init compares it with MPIDR_EL1 & 0xffff and asserts on a mismatch. The
    patch passes `gi.mpidr & 0xffff`. (`gi.mpidr` is the raw `mrs mpidr_el1`, gic.c.) It is what makes the kernel survive
    checkpoint 15; without it the C resume chain would end in a panic after checkpoint 15.
  * the checkpoint installer: ckpt3.h instead of ckpt2.h, nat036_install (the resumable C-checkpoint stub with a stop list)
    instead of nat034_install, and its message function instead of the five-site table.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _p22():
    spec = importlib.util.spec_from_file_location("nat022_patch_loader", HERE.parent / "nat-022" / "patch_loader.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MPIDR_OLD = "adt_set_boot_cpu_mpidr(adt_pa, p->adt_size, (uint32_t)gi.mpidr)"
MPIDR_NEW = "adt_set_boot_cpu_mpidr(adt_pa, p->adt_size, (uint32_t)(gi.mpidr & 0xffff))"

INSTALL_OLD = '''\t{
\t\tstatic const char *const nat031_msg[] = {
\t\t\t"XNU checkpoint slot check failed", "XNU checkpoint site 1 check failed",
\t\t\t"XNU checkpoint site 2 check failed", "XNU checkpoint site 3 check failed",
\t\t\t"XNU checkpoint site 4 check failed", "XNU checkpoint site 5 check failed" };
\t\tuint32_t nat031_bad = 0;

\t\tif (nat034_install(win_base, p->virt_base, &nat031_bad))
\t\t\treturn fail(nat031_msg[nat031_bad]);
\t\tlog_str("\\nxnu checkpoint slot filled\\n");
\t}
'''

INSTALL_NEW = '''\t{
\t\tuint32_t nat031_bad = 0;
\t\tint nat036_rc = nat036_install(win_base, p->virt_base, &nat031_bad);

\t\tif (nat036_rc)
\t\t\treturn fail(nat036_msg(nat036_rc, nat031_bad));
\t\tlog_str("\\nxnu checkpoint slot filled\\n");
\t}
'''


def main(root):
    p22 = _p22()
    once = p22.once
    p22.main(root, trig_hold=True, adt_aligned=True, xnu_entry=False, ckpt=False, ckpt2=True)
    p = Path(root) / "shim/e1s-xnu/loader.c"
    s = p.read_text()
    s = once(s, '#include "ckpt2.h"\n', '#include "ckpt3.h"\n')
    s = once(s, INSTALL_OLD, INSTALL_NEW)
    s = once(s, MPIDR_OLD, MPIDR_NEW)
    p.write_text(s)
    return hashlib.sha256(s.encode()).hexdigest()


if __name__ == "__main__":
    main(sys.argv[1])
