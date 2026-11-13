#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-148: NAT-145's ten-CPU ADT with the boot-CPU fix (host only).

make_adt145.add_cpus copies cpu0's property list, including `state` = "running", to cpu1..cpu9 (as the donor's
tools/e1s/xnu/mkadt.py:175 does). XNU's ml_is_boot_cpu() takes every "running" node as the boot CPU, and
ml_parse_cpu_topology() asserts that there is only one (machine_routines.c:1193 in the model kernel). NAT-146 stopped there on
the phone. This gives cpu1..cpu9 `state` = "waiting" (same 8-byte length). GenericARMPE only requires that a `state` exists, and
pe_identify_machine looks for the one "running" CPU.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("nat148_make_adt145", HERE.parent / "nat-145/make_adt145.py")
m145 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m145)
RUNNING, WAITING = b"running\0", b"waiting\0"


def fix_states(blob, adt=None):
    adt = adt or m145._adt()
    root, end = adt.parse(blob)
    if end != len(blob):
        raise ValueError("trailing bytes after the ADT")
    cpus = [c for c in root.children if c.name == "cpus"][0]
    changed = []
    for i, n in enumerate(cpus.children):
        for j, (k, f, v) in enumerate(n.props):
            if k == "state":
                want = RUNNING if i == 0 else WAITING
                if v not in (RUNNING, WAITING):
                    raise ValueError("%s state %r" % (n.name, v))
                if v != want:
                    n.props[j] = (k, f, want)
                    changed.append(n.name)
    out = adt.serialize(root)
    return out, changed


def add_cpus(blob, adt=None):
    """make_adt145.add_cpus, then fix_states: -> (blob, record)."""
    adt = adt or m145._adt()
    out, rec = m145.add_cpus(blob, adt)
    out, changed = fix_states(out, adt)
    rec = dict(rec, nat148_waiting=changed, output_sha256=hashlib.sha256(out).hexdigest(), output_bytes=len(out))
    return out, rec


def main(argv):
    if len(argv) != 3:
        print("make_adt148.py IN.adt OUT.adt", file=sys.stderr)
        return 2
    out, rec = add_cpus(Path(argv[1]).read_bytes())
    Path(argv[2]).write_bytes(out)
    print(rec)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
