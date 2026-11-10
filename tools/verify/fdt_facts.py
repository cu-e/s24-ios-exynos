#!/usr/bin/env python3
"""Sanitized hardware facts from a flattened device tree (NAT-005).

Parses a DTB with no external tools and reports only selected facts: /memory ranges, /reserved-memory
regions, the names (not values) of /chosen properties and bootargs keys, the GIC, the architected timer,
CPUs and PSCI, and display, touch and UART nodes. Raw blobs may carry device identifiers and stay out of
Git; this output is meant to be publishable.

  fdt_facts.py DTB [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys

FDT_MAGIC = 0xD00DFEED
BEGIN_NODE, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9


class Node:
    def __init__(self, name, parent=None):
        self.name, self.parent, self.props, self.children = name, parent, {}, []

    @property
    def path(self):
        if self.parent is None:
            return "/"
        parent = self.parent.path
        return (parent if parent != "/" else "") + "/" + self.name

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def child(self, name):
        return next((c for c in self.children if c.name == name or c.name.split("@")[0] == name), None)

    def u32(self, prop, default=None):
        value = self.props.get(prop)
        return struct.unpack(">I", value[:4])[0] if value and len(value) >= 4 else default

    def strings(self, prop):
        value = self.props.get(prop)
        return [s.decode(errors="replace") for s in value.split(b"\0") if s] if value else []


def parse(blob: bytes) -> Node:
    if len(blob) < 40:
        raise ValueError("DTB shorter than its header")
    magic, total, off_struct, off_strings, _, version, _, _, size_strings, size_struct = struct.unpack_from(">10I", blob, 0)
    if magic != FDT_MAGIC:
        raise ValueError("not a flattened device tree")
    if total > len(blob) or off_struct + size_struct > total or off_strings + size_strings > total or version < 16:
        raise ValueError("DTB header points outside the blob or version < 16")
    strings = blob[off_strings:off_strings + size_strings]
    pos, end, root, node = off_struct, off_struct + size_struct, None, None
    while pos + 4 <= end:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == BEGIN_NODE:
            name_end = blob.index(b"\0", pos, end)
            name = blob[pos:name_end].decode(errors="replace")
            pos = (name_end + 1 + 3) & ~3
            new = Node(name, node)
            if node is None:
                if root is not None:
                    raise ValueError("second root node")
                root = new
            else:
                node.children.append(new)
            node = new
        elif token == END_NODE:
            if node is None:
                raise ValueError("unbalanced END_NODE")
            node = node.parent
        elif token == PROP:
            if node is None:
                raise ValueError("property outside a node")
            length, name_off = struct.unpack_from(">II", blob, pos)
            pos += 8
            if pos + length > end or name_off >= len(strings):
                raise ValueError("property runs outside the structure block")
            name = strings[name_off:strings.index(b"\0", name_off)].decode(errors="replace")
            node.props[name] = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == NOP:
            continue
        elif token == END:
            break
        else:
            raise ValueError(f"bad token {token:#x} at {pos - 4:#x}")
    if root is None or node is not None:
        raise ValueError("unterminated tree")
    return root


def cells(value: bytes, count: int) -> int:
    out = 0
    for i in range(count):
        out = out << 32 | struct.unpack_from(">I", value, 4 * i)[0]
    return out


def regs(node: Node):
    """(address, size) pairs using the parent's #address-cells/#size-cells (defaults 2 and 1)."""
    parent = node.parent or node
    ac, sc = parent.u32("#address-cells", 2), parent.u32("#size-cells", 1)
    value, out, step = node.props.get("reg", b""), [], 4 * (ac + sc)
    for i in range(0, len(value) - step + 1, step):
        out.append((cells(value[i:], ac), cells(value[i + 4 * ac:], sc) if sc else 0))
    return out


def hexregs(node):
    return [[f"{a:#x}", f"{s:#x}"] for a, s in regs(node)]


DISPLAY_WORDS = ("decon", "dsim", "framebuffer", "simple-framebuffer", "display", "panel", "drmdecon", "fb")
TOUCH_WORDS = ("stm,", "fts", "touch", "tsp")
UART_WORDS = ("uart", "serial", "usi")


def matches(node, words):
    text = " ".join([node.name.lower()] + [c.lower() for c in node.strings("compatible")])
    return any(w in text for w in words)


def facts(root: Node) -> dict:
    out = {"model": root.strings("model"), "compatible": root.strings("compatible"),
           "root_cells": [root.u32("#address-cells"), root.u32("#size-cells")]}
    out["memory"] = [{"path": n.path, "reg": hexregs(n)} for n in root.walk()
                     if n.parent is root and (n.name.split("@")[0] == "memory" or n.strings("device_type") == ["memory"])]
    rmem = root.child("reserved-memory")
    out["reserved_memory"] = []
    if rmem:
        for n in rmem.children:
            out["reserved_memory"].append({"name": n.name, "reg": hexregs(n), "no_map": "no-map" in n.props,
                                           "reusable": "reusable" in n.props, "compatible": n.strings("compatible"),
                                           "size_only": "reg" not in n.props and "size" in n.props})
    chosen = root.child("chosen")
    if chosen:
        bootargs = chosen.strings("bootargs")
        out["chosen"] = {"properties": sorted(chosen.props),
                         "bootargs_keys": sorted({t.split("=")[0] for t in (bootargs[0].split() if bootargs else [])}),
                         "initrd": [f"{cells(chosen.props[k], len(chosen.props[k]) // 4):#x}" for k in ("linux,initrd-start", "linux,initrd-end")
                                    if k in chosen.props]}
    out["gic"] = [{"path": n.path, "compatible": n.strings("compatible"), "reg": hexregs(n)} for n in root.walk()
                  if any("gic" in c for c in n.strings("compatible"))]
    out["timer"] = [{"path": n.path, "compatible": n.strings("compatible"), "clock_frequency": n.u32("clock-frequency"),
                     "interrupts_cells": len(n.props.get("interrupts", b"")) // 4} for n in root.walk()
                    if any(c in ("arm,armv8-timer", "arm,armv7-timer") for c in n.strings("compatible"))]
    cpus = root.child("cpus")
    if cpus:
        cpu_nodes = [n for n in cpus.walk() if n.strings("device_type") == ["cpu"]]
        out["cpus"] = {"count": len(cpu_nodes), "compatible": sorted({c for n in cpu_nodes for c in n.strings("compatible")}),
                       "enable_method": sorted({m for n in cpu_nodes for m in n.strings("enable-method")}),
                       "mpidr": [f"{a:#x}" for n in cpu_nodes for a, _ in regs(n)]}
    out["psci"] = [{"compatible": n.strings("compatible"), "method": n.strings("method")} for n in root.walk()
                   if any(c.startswith("arm,psci") for c in n.strings("compatible"))]
    def node_facts(n):
        return {"path": n.path, "compatible": n.strings("compatible"), "reg": hexregs(n), "status": n.strings("status")}
    out["display"] = [node_facts(n) for n in root.walk() if n is not root and matches(n, DISPLAY_WORDS) and ("reg" in n.props or "compatible" in n.props)]
    out["touch"] = [node_facts(n) for n in root.walk() if n is not root and matches(n, TOUCH_WORDS) and "compatible" in n.props]
    out["uart"] = [node_facts(n) for n in root.walk() if n is not root and matches(n, UART_WORDS) and "compatible" in n.props and "reg" in n.props]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dtb")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    result = facts(parse(open(args.dtb, "rb").read()))
    text = json.dumps(result, indent=2)
    if args.json:
        open(args.json, "w").write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
