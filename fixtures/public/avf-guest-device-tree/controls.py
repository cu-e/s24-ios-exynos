#!/usr/bin/env python3
"""Independent byte-level controls; the example is owned, never a runtime dump."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("device_tree", ROOT / "tools/build/avf_guest_device_tree.py")
dt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dt)


def example():
    """Selected writer's required subset with documented QEMU example addresses."""
    u32 = lambda value: struct.pack("<I", value)
    u64 = lambda value: struct.pack("<Q", value)
    text = lambda value: value.encode("ascii") + b"\0"
    node = lambda name, props=None, children=None: {
        "properties": {"name": text(name), **(props or {})}, "children": children or []}
    cpu = node("cpu0", {"device_type": text("cpu"), "state": text("running"),
                       "reg": u32(0), "cpu-id": u32(0),
                       **{name: u64(value) for name, value in {
                           "timebase-frequency": 62500000, "fixed-frequency": 62500000,
                           "clock-frequency": 2000000000, "bus-frequency": 100000000,
                           "memory-frequency": 100000000, "peripheral-frequency": 24000000}.items()}})
    return node("device-tree", {"platform-name": text("t8015"), "#address-cells": u32(2),
                               "#size-cells": u32(2)}, [
        node("chosen", {"random-seed": bytes(range(64)), "dram-base": u64(0x40000000),
                        "dram-size": u64(0xe000000), "psci-method": text("hvc"),
                        "embedded-panic-log-size": u32(0x80000)}, [
            node("memory-map", {"RAMDisk": struct.pack("<QQ", 0x46000000, 0x1000)})]),
        node("pram", {"reg": struct.pack("<QQ", 0x4ff80000, 0x80000)}),
        node("cpus", children=[cpu]),
        node("arm-io", {"device_type": text("crosvm"), "#address-cells": u32(2),
                        "#size-cells": u32(2), "ranges": struct.pack("<QQQ", 0, 0x100, 0x3fffff00)}, [
            node("gic", {"device_type": text("interrupt-controller"), "compatible": text("arm,gic-v3"),
                         "reg": struct.pack("<QQQQ", 0x7ffff00, 0x10000, 0x809ff00, 0xf60000),
                         "virtual-timer-intid": u32(27)}),
            node("uart0", {"device_type": text("uart"), "compatible": text("arm,pl011"),
                           "reg": struct.pack("<QQ", 0x8ffff00, 0x1000), "boot-console": u32(1)})]),
        node("pci0", {"compatible": text("pci-host-ecam-generic"),
                      "ecam": struct.pack("<QQ", 0x4010000000, 0x10000000),
                      "bus-range": struct.pack("<II", 0, 255), "pci-ranges": b"",
                      "intx-map": b"", "intx-mask": struct.pack("<II", 0xffff00, 7), "probe-only": u32(0)})])


def encode(node):
    props = node["properties"]
    result = struct.pack("<II", len(props), len(node["children"]))
    for name, value in props.items():
        name = name.encode("ascii")
        result += name + b"\0" * (32 - len(name)) + struct.pack("<I", len(value))
        result += value + b"\0" * ((-len(value)) % 4)
    return result + b"".join(encode(child) for child in node["children"])


def locate(model, path):
    if path == "/":
        return model
    current = model
    for part in path.strip("/").split("/"):
        current = next(child for child in current["children"]
                       if child["properties"]["name"] == part.encode() + b"\0")
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--main", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    records = []

    def check(name, function, rejects=False):
        try:
            function()
        except dt.TreeError as error:
            records.append({"name": name, "pass": rejects, "rejection": str(error)})
        else:
            records.append({"name": name, "pass": not rejects})

    model = example()
    raw = encode(model)
    (args.out / "owned-example.adt").write_bytes(raw)
    check("source-contract-example", lambda: dt.preflight(dt.parse(raw), require_ramdisk=True, require_pci=True))
    # A fixed wire-format vector, independently written as literal hex, exercises
    # little-endian counts and the one-byte property alignment without encode().
    literal = bytes.fromhex("0100000000000000") + b"name" + bytes(28) + bytes.fromhex("0c000000") + b"device-tree\0"
    check("independent-literal-wire-vector", lambda: dt.parse(literal))
    for name, bad in (("truncated-header", raw[:7]), ("truncated-value", raw[:-1]),
                      ("trailing-data", raw + b"\0"), ("oversize", bytes(dt.MAX_BYTES + 1)),
                      ("big-endian-counts", struct.pack(">II", 4, 5) + raw[8:]),
                      ("huge-property-count", struct.pack("<I", 0xffffffff) + raw[4:]),
                      ("huge-child-count", raw[:4] + struct.pack("<I", 0xffffffff) + raw[8:]),
                      ("nonterminated-property-name", raw[:8] + b"x" * 32 + raw[40:]),
                      ("length-wrap-attempt", raw[:40] + struct.pack("<I", 0xffffffff) + raw[44:])):
        check(name, lambda bad=bad: dt.parse(bad), True)

    def mutation(path, name, value=None, remove=False):
        changed = copy.deepcopy(model)
        props = locate(changed, path)["properties"]
        if remove:
            del props[name]
        else:
            props[name] = value
        dt.preflight(dt.parse(encode(changed)), require_ramdisk=True, require_pci=True)

    for name, path, prop in (("missing-gic-reg", "/arm-io/gic", "reg"),
                             ("missing-psci", "/chosen", "psci-method"),
                             ("missing-ramdisk", "/chosen/memory-map", "RAMDisk"),
                             ("missing-pci-ecam", "/pci0", "ecam"),
                             ("missing-cpu-state", "/cpus/cpu0", "state")):
        check(name, lambda path=path, prop=prop: mutation(path, prop, remove=True), True)
    for name, path, prop, value in (
            ("short-gic-reg", "/arm-io/gic", "reg", bytes(24)),
            ("gic-driver-mismatch", "/arm-io/gic", "compatible", b"arm,gic-400\0"),
            ("timer-consumer-mismatch", "/arm-io/gic", "virtual-timer-intid", struct.pack("<I", 26)),
            ("uart-driver-mismatch", "/arm-io/uart0", "compatible", b"unsupported\0"),
            ("psci-method-mismatch", "/chosen", "psci-method", b"bad\0"),
            ("zero-frequency", "/cpus/cpu0", "timebase-frequency", bytes(8)),
            ("dram-extent-overflow", "/chosen", "dram-base", bytes([255]) * 8),
            ("invalid-pci-bus-range", "/pci0", "bus-range", struct.pack("<II", 2, 1)),
            ("partial-pci-record", "/pci0", "pci-ranges", bytes(31)),
            ("zero-gic-extent", "/arm-io/gic", "reg", struct.pack("<QQQQ", 0x7ffff00, 0, 0x809ff00, 0xf60000)),
            ("gic-outside-io", "/arm-io/gic", "reg", struct.pack("<QQQQ", 0x3fffff00, 1, 0x809ff00, 0xf60000))):
        check(name, lambda path=path, prop=prop, value=value: mutation(path, prop, value), True)

    duplicate = copy.deepcopy(model)
    duplicate["children"].append(copy.deepcopy(duplicate["children"][0]))
    check("duplicate-node", lambda: dt.parse(encode(duplicate)), True)
    duplicate_prop = struct.pack("<II", 2, 0) + literal[8:] * 2
    check("duplicate-property", lambda: dt.parse(duplicate_prop), True)
    bad_padding = bytearray(raw)
    chosen = dt.parse(raw)["/chosen"]
    bad_padding[chosen["value_offsets"]["name"] + len(b"chosen\0")] = 1
    check("nonzero-alignment-padding", lambda: dt.parse(bytes(bad_padding)), True)
    deep = {"properties": {"name": b"device-tree\0"}, "children": []}
    cursor = deep
    for _ in range(dt.MAX_DEPTH):
        child = {"properties": {"name": b"nested\0"}, "children": []}
        cursor["children"].append(child)
        cursor = child
    check("depth-overflow", lambda: dt.parse(encode(deep)), True)
    # Missing optional nodes remain optional unless the caller requests them.
    optional = copy.deepcopy(model)
    optional["children"] = optional["children"][:-1]
    del locate(optional, "/chosen/memory-map")["properties"]["RAMDisk"]
    check("optional-ramdisk-pci-absent", lambda: dt.preflight(dt.parse(encode(optional))))
    check("required-pci-absent", lambda: dt.preflight(dt.parse(encode(optional)), require_pci=True), True)

    pins = json.loads((Path(__file__).parent / "source-pins.json").read_text())
    source_checks = []
    for row in pins["files"]:
        path = args.main / row["path"]
        if not path.resolve().is_relative_to(args.main.resolve()):
            raise ValueError("source pin escaped main root")
        matched = dt.sha256(path) == row["sha256"]
        source_checks.append({"path": row["path"], "pass": matched})
    with open("/proc/self/status", encoding="ascii") as stream:
        status = dict(line.split(":", 1) for line in stream if ":" in line)
    hwm = int(status["VmHWM"].split()[0]) * 1024
    report = {"kind": "host-test", "origin": "local-host", "task": "VM-027",
              "outcome": "pass" if all(r["pass"] for r in records + source_checks) else "fail",
              "recorded_at": datetime.now(timezone.utc).isoformat(), "commands": [{"argv": sys.argv, "exit_code": None}],
              "controls": records, "source_checks": source_checks,
              "example_origin": "owned-source-contract-example-not-runtime-data",
              "example_sha256": hashlib.sha256(raw).hexdigest(),
              "module_sha256": dt.sha256(ROOT / "tools/build/avf_guest_device_tree.py"),
              "controls_sha256": dt.sha256(__file__), "pins_sha256": dt.sha256(Path(__file__).parent / "source-pins.json"),
              "current_image_VmHWM_bytes": hwm, "elapsed_seconds": time.monotonic() - started,
              "actual_serialized_shim_data_verified": False,
              "compiler_executed": False, "guest_executed": False, "kernel_executed": False}
    result = 0 if report["outcome"] == "pass" else 1
    report["commands"][0]["exit_code"] = result
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "controls": len(records),
                      "source_checks": len(source_checks), "current_image_VmHWM_bytes": hwm}))
    return result


if __name__ == "__main__":
    sys.exit(main())
