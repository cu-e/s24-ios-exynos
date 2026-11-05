#!/usr/bin/env python3
"""Bounded Apple serialized DT parser and pinned AVF guest contract preflight.

This reads data; it never starts a compiler, emulator or device operation.
Passing preflight describes this source profile, not hardware compatibility.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

MAX_BYTES = 0x10000  # Genuine avfboot.c DT_MAX.
MAX_DEPTH = 16  # Genuine dt_writer.counts capacity, including the root.
MAX_NODES = 512
MAX_PROPERTIES = 2048
U64_MAX = (1 << 64) - 1


class TreeError(ValueError):
    """Malformed serialization or unsupported selected-profile contract."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cstring(value, label, *, padded=False):
    end = value.find(b"\0")
    if end < 0 or (not padded and end != len(value) - 1):
        raise TreeError(f"{label}: expected one terminated string")
    if padded and any(value[end + 1:]):
        raise TreeError(f"{label}: nonzero string padding")
    try:
        result = value[:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise TreeError(f"{label}: expected ASCII") from error
    if not result or any(ord(c) < 32 or ord(c) > 126 for c in result):
        raise TreeError(f"{label}: invalid string")
    return result


def parse(data):
    """Read the selected little-endian writer's exact format, with finite bounds.

    Duplicate names, trailing bytes, nonzero padding and nonterminated names are
    refused deliberately: they are ambiguous or absent from the selected writer.
    This is stricter than some kernel lookup paths, not an Apple DT universal ABI.
    """
    if not 8 <= len(data) <= MAX_BYTES:
        raise TreeError("tree size outside selected shim bounds")
    position = 0
    nodes = {}
    total_properties = 0

    def take(size):
        nonlocal position
        if size < 0 or size > len(data) - position:
            raise TreeError(f"truncated tree at offset {position}, need {size}")
        start = position
        position += size
        return data[start:position]

    def node(parent, depth):
        nonlocal total_properties
        if depth > MAX_DEPTH or len(nodes) >= MAX_NODES:
            raise TreeError("node/depth limit exceeded")
        start = position
        nprops, nchildren = struct.unpack("<II", take(8))
        total_properties += nprops
        if not nprops or total_properties > MAX_PROPERTIES or nchildren > MAX_NODES:
            raise TreeError("property/child count outside selected bounds")
        properties = {}
        offsets = {}
        for _ in range(nprops):
            header = take(36)
            name = cstring(header[:32], "property name", padded=True)
            if name in properties:
                raise TreeError(f"duplicate property {name}")
            length, = struct.unpack_from("<I", header, 32)
            offsets[name] = position
            properties[name] = take(length)
            if any(take((-length) % 4)):
                raise TreeError("nonzero property alignment padding")
        if "name" not in properties:
            raise TreeError("node has no name property")
        name = cstring(properties["name"], "node name")
        if len(name) > 63 or "/" in name or name in (".", ".."):
            raise TreeError("invalid node path component")
        if depth == 1:
            if name != "device-tree":
                raise TreeError("selected shim root name must be device-tree")
            path = "/"
        else:
            path = parent.rstrip("/") + "/" + name
        if path in nodes:
            raise TreeError(f"duplicate node {path}")
        nodes[path] = {"properties": properties, "offset": start,
                       "value_offsets": offsets, "child_count": nchildren}
        for _ in range(nchildren):
            node(path, depth + 1)

    node("", 1)
    if position != len(data):
        raise TreeError(f"trailing bytes: consumed {position} of {len(data)}")
    return nodes


def preflight(nodes, *, require_ramdisk=False, require_pci=False):
    checks = []

    def prop(path, name, size=None):
        if path not in nodes or name not in nodes[path]["properties"]:
            raise TreeError(f"missing {path}:{name}")
        value = nodes[path]["properties"][name]
        if size is not None and len(value) != size:
            raise TreeError(f"{path}:{name}: expected {size} bytes, got {len(value)}")
        checks.append(f"{path}:{name}")
        return value

    def integer(path, name, size=4):
        return int.from_bytes(prop(path, name, size), "little")

    def text(path, name):
        return cstring(prop(path, name), f"{path}:{name}")

    def region(base, size, label):
        if not base or not size or size > U64_MAX - base:
            raise TreeError(f"{label}: zero or overflowing physical extent")
        return (base, base + size)

    for name in ("#address-cells", "#size-cells"):
        if integer("/", name) != 2:
            raise TreeError(f"root {name}: expected selected two-cell writer")
    if text("/", "platform-name") != "t8015":
        raise TreeError("unexpected selected shim platform-name")
    prop("/chosen", "random-seed", 64)
    dram = region(integer("/chosen", "dram-base", 8),
                  integer("/chosen", "dram-size", 8), "DRAM")
    psci = text("/chosen", "psci-method")
    if psci not in ("hvc", "smc"):
        raise TreeError("PSCI method must be hvc or smc")
    panic_size = integer("/chosen", "embedded-panic-log-size")
    pram = struct.unpack("<QQ", prop("/pram", "reg", 16))
    region(*pram, "pram")
    if not panic_size or panic_size > pram[1]:
        raise TreeError("panic log exceeds pram extent")
    if "/chosen/memory-map" not in nodes:
        raise TreeError("missing /chosen/memory-map")
    ramdisk_present = "RAMDisk" in nodes["/chosen/memory-map"]["properties"]
    if require_ramdisk or ramdisk_present:
        rd = struct.unpack("<QQ", prop("/chosen/memory-map", "RAMDisk", 16))
        region(*rd, "RAMDisk")

    if text("/arm-io", "device_type") != "crosvm":
        raise TreeError("unexpected selected arm-io device_type")
    child_base, io_base, io_size = struct.unpack("<QQQ", prop("/arm-io", "ranges", 24))
    region(io_base, io_size, "arm-io")
    if child_base != 0:
        raise TreeError("selected arm-io range child base must be zero")
    for name in ("#address-cells", "#size-cells"):
        if integer("/arm-io", name) != 2:
            raise TreeError(f"arm-io {name}: expected two cells")
    if text("/arm-io/gic", "compatible") != "arm,gic-v3":
        raise TreeError("selected AVF shim emits GICv3 only")
    if text("/arm-io/gic", "device_type") != "interrupt-controller":
        raise TreeError("unexpected GIC device_type")
    registers = struct.unpack("<QQQQ", prop("/arm-io/gic", "reg", 32))
    extents = []
    for offset, size in (registers[:2], registers[2:]):
        if offset >= io_size or size > io_size - offset:
            raise TreeError("GIC register extent outside arm-io")
        extents.append(region(io_base + offset, size, "GIC"))
    if max(extents[0][0], extents[1][0]) < min(extents[0][1], extents[1][1]):
        raise TreeError("overlapping GIC distributor and redistributor")
    # gic_v3_irq.c uses the compile-time architectural PPI 27, not this DT property.
    if integer("/arm-io/gic", "virtual-timer-intid") != 27:
        raise TreeError("timer PPI differs from selected kernel constant 27")

    uart = text("/arm-io/uart0", "compatible")
    if uart not in ("ns16550a", "arm,pl011"):
        raise TreeError("no selected console driver match")
    if text("/arm-io/uart0", "device_type") != "uart":
        raise TreeError("unexpected UART device_type")
    offset, size = struct.unpack("<QQ", prop("/arm-io/uart0", "reg", 16))
    if offset >= io_size or size > io_size - offset:
        raise TreeError("UART register extent outside arm-io")
    region(io_base + offset, size, "UART")
    if integer("/arm-io/uart0", "boot-console") != 1:
        raise TreeError("selected UART is not boot console")

    if "/cpus" not in nodes:
        raise TreeError("missing /cpus")
    cpu_paths = [path for path in nodes if path.startswith("/cpus/") and path.count("/") == 2]
    if not 1 <= len(cpu_paths) <= 8:
        raise TreeError("CPU count outside selected shim MAX_CPUS=8")
    phys_ids, cpu_ids, running = set(), set(), 0
    for path in cpu_paths:
        if text(path, "device_type") != "cpu":
            raise TreeError("unexpected CPU device_type")
        state = text(path, "state")
        if state not in ("running", "waiting"):
            raise TreeError("unsupported CPU state")
        running += state == "running"
        phys, cpu_id = integer(path, "reg"), integer(path, "cpu-id")
        if phys in phys_ids or cpu_id in cpu_ids:
            raise TreeError("duplicate CPU physical or logical identifier")
        phys_ids.add(phys)
        cpu_ids.add(cpu_id)
        for name in ("timebase-frequency", "fixed-frequency", "clock-frequency",
                     "bus-frequency", "memory-frequency", "peripheral-frequency"):
            if not integer(path, name, 8):
                raise TreeError(f"zero CPU {name}")
    if running != 1 or cpu_ids != set(range(len(cpu_paths))):
        raise TreeError("selected topology requires one running CPU and consecutive cpu-id")

    pci_present = "/pci0" in nodes
    if require_pci or pci_present:
        compatible = text("/pci0", "compatible")
        if compatible not in ("pci-host-cam-generic", "pci-host-ecam-generic"):
            raise TreeError("no selected PCI configuration driver match")
        ecam, size = struct.unpack("<QQ", prop("/pci0", "ecam", 16))
        region(ecam, size, "PCI configuration")
        shift = 16 if compatible == "pci-host-cam-generic" else 20
        first, last = struct.unpack("<II", prop("/pci0", "bus-range", 8))
        if first > last or last > 255 or size >> shift < last - first + 1:
            raise TreeError("PCI bus range exceeds configuration space")
        for name, stride in (("pci-ranges", 32), ("intx-map", 16)):
            if len(prop("/pci0", name)) % stride:
                raise TreeError(f"{name}: partial record")
        prop("/pci0", "intx-mask", 8)
        if integer("/pci0", "probe-only") not in (0, 1):
            raise TreeError("invalid PCI probe-only")
    return {"checks": checks, "node_count": len(nodes), "cpu_count": len(cpu_paths),
            "dram": list(dram), "psci_method": psci, "uart_driver": uart,
            "pci_present": pci_present, "ramdisk_present": ramdisk_present,
            "kernel_executed": False, "hardware_compatibility_qualified": False}


def read_tree(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    return data, parse(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("--require-ramdisk", action="store_true")
    parser.add_argument("--require-pci", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = {"kind": "host-test", "input": str(args.tree),
              "actual_runtime_capture_provenance_verified": False}
    try:
        data, nodes = read_tree(args.tree)
        report.update(preflight(nodes, require_ramdisk=args.require_ramdisk,
                                require_pci=args.require_pci))
        report.update(outcome="pass", sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    except (OSError, TreeError) as error:
        report.update(outcome="fail", error=str(error))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    print(rendered, end="")
    return 0 if report["outcome"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
