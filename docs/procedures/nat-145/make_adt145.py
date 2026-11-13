#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-145: the NAT-117 ADT (pinned e1s.adt + /chosen ephemeral-storage + D22AP /product) with all ten e1s CPUs in /cpus (host only).

The project ADT has only cpu0, so XNU registers one processor. The donor's own tools/e1s/xnu/mkadt.py (build(smp=True)) publishes the
ten cores; this does the same to the derived ADT, without rebuilding the rest of the tree:
  * cpu0 keeps its node and phandle and gains `small-core` = 1 (mkadt's smp table marks cluster 0 small);
  * cpu1..cpu9 are copies of cpu0's property list with the per-core values of mkadt's smp table and a fresh phandle each, above every
    phandle in the tree: reg (MPIDR), cpu-id, cluster-id, die-cluster-id, cluster-core-id, l2-cache-id, small-core (cluster 0 only).
The MPIDR map is the pinned Samsung DT's (references/s24-linux 417484173abc, arch/arm64/boot/dts/exynos/s5e9945-cpu.dtsi:175-268):
  cpu0-3 0x000-0x300 "arm,heyes" (Cortex-A520), cpu4-6 0x400-0x600 "arm,hunter-lf" and cpu7-8 0x700-0x800 "arm,hunter-hf"
  (Cortex-A720), cpu9 0x900 "arm,hunter-elp" (Cortex-X4); enable-method "psci" (psci-1.0). /chosen/psci-method is already "smc".
The GIC redistributor range in the ADT (0x10240000, 0x140000) is the DT's "GICR * 10" (s5e9945.dts:123-124).
"""
import hashlib
import importlib.util
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ADT_PY = ROOT / "artifacts/nat-020/build-003/source/tools/e1s/xnu/adt.py"

# (MPIDR, cluster, core in cluster, small) -- tools/e1s/xnu/mkadt.py build(smp=True), checked against s5e9945-cpu.dtsi
CPU_TABLE = [
    (0x000, 0, 0, True), (0x100, 0, 1, True), (0x200, 0, 2, True), (0x300, 0, 3, True),
    (0x400, 1, 0, False), (0x500, 1, 1, False), (0x600, 1, 2, False),
    (0x700, 2, 0, False), (0x800, 2, 1, False),
    (0x900, 3, 0, False),
]
PER_CORE = ("reg", "cpu-id", "cluster-id", "die-cluster-id", "cluster-core-id", "l2-cache-id")


def _adt():
    spec = importlib.util.spec_from_file_location("nat145_adt", ADT_PY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha(b):
    return hashlib.sha256(b).hexdigest()


def u32(v):
    return struct.pack("<I", v)


def max_phandle(node):
    v = node.prop("AAPL,phandle")
    m = struct.unpack("<I", v)[0] if v is not None and len(v) == 4 else 0
    return max([m] + [max_phandle(c) for c in node.children])


def _set(props, name, value):
    for i, (n, f, _) in enumerate(props):
        if n == name:
            props[i] = (n, f, value)
            return
    raise ValueError("cpu0 has no %s" % name)


def add_cpus(blob, adt=None):
    """-> (new blob, record): /cpus of `blob` with cpu0..cpu9."""
    adt = adt or _adt()
    root, end = adt.parse(blob)
    if end != len(blob) or adt.serialize(root) != blob:
        raise ValueError("the input ADT does not round-trip")
    cpus = [c for c in root.children if c.name == "cpus"]
    if len(cpus) != 1 or [c.name for c in cpus[0].children] != ["cpu0"]:
        raise ValueError("expected /cpus with cpu0 only")
    chosen = [c for c in root.children if c.name == "chosen"][0]
    if chosen.prop("psci-method") != b"smc\0":
        raise ValueError("/chosen/psci-method is not smc")
    cpu0 = cpus[0].children[0]
    for name in PER_CORE:
        if cpu0.prop(name) != u32(0):
            raise ValueError("cpu0 %s is not 0" % name)
    if cpu0.prop("small-core") is not None:
        raise ValueError("cpu0 already has small-core")
    template = list(cpu0.props)
    at = [n for n, _, _ in template].index("state")     # mkadt puts small-core right after state
    cpu0.props.insert(at + 1, ("small-core", 0, u32(1)))
    ph = max_phandle(root) + 1
    added = []
    for index, (mpidr, cluster, core, small) in enumerate(CPU_TABLE[1:], start=1):
        props = list(template)
        _set(props, "name", ("cpu%d" % index).encode() + b"\0")
        _set(props, "AAPL,phandle", u32(ph))
        values = dict(zip(PER_CORE, (mpidr, index, cluster, cluster, core, cluster)))
        for name, value in values.items():
            _set(props, name, u32(value))
        if small:
            props.insert(at + 1, ("small-core", 0, u32(1)))
        node = adt.Node()
        node.props = props
        cpus[0].children.append(node)
        added.append(dict(name="cpu%d" % index, mpidr=hex(mpidr), cluster=cluster, core=core, small=small, phandle=ph))
        ph += 1
    out = adt.serialize(root)
    return out, {"input_sha256": sha(blob), "output_sha256": sha(out), "output_bytes": len(out), "cpus": 1 + len(added),
                 "added": added}


def main(argv):
    if len(argv) != 3:
        print("make_adt145.py IN.adt OUT.adt", file=sys.stderr)
        return 2
    out, rec = add_cpus(Path(argv[1]).read_bytes())
    Path(argv[2]).write_bytes(out)
    print(rec)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
