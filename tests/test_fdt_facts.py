import importlib.util
import json
from pathlib import Path
import struct
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/verify/fdt_facts.py"
spec = importlib.util.spec_from_file_location("fdt_facts", SCRIPT)
fdt_facts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fdt_facts)


def u32s(*values):
    return b"".join(struct.pack(">I", v) for v in values)


def blob(tree):
    """Independent minimal FDT v17 writer: tree is (name, {prop: bytes}, [children])."""
    strings, offsets, body = bytearray(), {}, bytearray()

    def name_off(name):
        if name not in offsets:
            offsets[name] = len(strings)
            strings.extend(name.encode() + b"\0")
        return offsets[name]

    def pad():
        while len(body) % 4:
            body.append(0)

    def emit(node):
        name, props, children = node
        body.extend(u32s(1))
        body.extend(name.encode() + b"\0")
        pad()
        for key, value in props.items():
            body.extend(u32s(3, len(value), name_off(key)))
            body.extend(value)
            pad()
        for child in children:
            emit(child)
        body.extend(u32s(2))

    emit(tree)
    body.extend(u32s(9))
    off_rsv = 40
    off_struct = off_rsv + 16
    off_strings = off_struct + len(body)
    total = off_strings + len(strings)
    header = u32s(0xD00DFEED, total, off_struct, off_strings, off_rsv, 17, 16, 0, len(strings), len(body))
    return header + bytes(16) + bytes(body) + bytes(strings)


def s(text):
    return text.encode() + b"\0"


TREE = ("", {"#address-cells": u32s(2), "#size-cells": u32s(2), "model": s("Test E1S"), "compatible": s("samsung,test")}, [
    ("memory@80000000", {"device_type": s("memory"),
                         "reg": u32s(0, 0x80000000, 0, 0x40000000, 0x8, 0x80000000, 0x1, 0x0)}, []),
    ("reserved-memory", {"#address-cells": u32s(2), "#size-cells": u32s(2), "ranges": b""}, [
        ("framebuffer@fa200000", {"reg": u32s(0, 0xFA200000, 0, 0x9A4000), "no-map": b""}, []),
        ("pool", {"size": u32s(0, 0x1000000), "reusable": b"", "compatible": s("shared-dma-pool")}, []),
    ]),
    ("chosen", {"bootargs": s("console=ttySAC0 androidboot.serialno=SECRET123 quiet"),
                "linux,initrd-start": u32s(0, 0x84000000), "linux,initrd-end": u32s(0, 0x84100000)}, []),
    ("interrupt-controller@10200000", {"compatible": s("arm,gic-v3"),
                                       "reg": u32s(0, 0x10200000, 0, 0x10000, 0, 0x10240000, 0, 0x140000)}, []),
    ("timer", {"compatible": s("arm,armv8-timer"), "interrupts": u32s(1, 13, 8, 1, 14, 8)}, []),
    ("cpus", {"#address-cells": u32s(2), "#size-cells": u32s(0)}, [
        ("cpu@0", {"device_type": s("cpu"), "compatible": s("arm,cortex-a520"), "reg": u32s(0, 0), "enable-method": s("psci")}, []),
        ("cpu@900", {"device_type": s("cpu"), "compatible": s("arm,cortex-x4"), "reg": u32s(0, 0x900), "enable-method": s("psci")}, []),
    ]),
    ("psci", {"compatible": s("arm,psci-1.0"), "method": s("smc")}, []),
    ("soc", {"#address-cells": u32s(1), "#size-cells": u32s(1)}, [
        ("drmdecon@19100000", {"compatible": s("samsung,exynos-drmdecon"), "reg": u32s(0x19100000, 0x10000)}, []),
        ("touchscreen@49", {"compatible": s("stm,fts_touch"), "reg": u32s(0x49, 0x1)}, []),
        ("uart@10870000", {"compatible": s("samsung,exynos-uart"), "reg": u32s(0x10870000, 0x100)}, []),
    ]),
])


class FdtFactsTests(unittest.TestCase):
    def setUp(self):
        self.facts = fdt_facts.facts(fdt_facts.parse(blob(TREE)))

    def test_memory_uses_two_cells(self):
        self.assertEqual(self.facts["memory"], [{"path": "/memory@80000000",
                                                 "reg": [["0x80000000", "0x40000000"], ["0x880000000", "0x100000000"]]}])

    def test_reserved_memory(self):
        fb, pool = self.facts["reserved_memory"]
        self.assertEqual((fb["name"], fb["reg"], fb["no_map"]), ("framebuffer@fa200000", [["0xfa200000", "0x9a4000"]], True))
        self.assertTrue(pool["size_only"] and pool["reusable"])

    def test_chosen_hides_values(self):
        chosen = self.facts["chosen"]
        self.assertEqual(chosen["bootargs_keys"], ["androidboot.serialno", "console", "quiet"])
        self.assertEqual(chosen["initrd"], ["0x84000000", "0x84100000"])
        self.assertNotIn("SECRET123", json.dumps(self.facts))

    def test_gic_timer_cpus_psci(self):
        self.assertEqual(self.facts["gic"][0]["reg"], [["0x10200000", "0x10000"], ["0x10240000", "0x140000"]])
        self.assertEqual(self.facts["timer"][0]["interrupts_cells"], 6)
        self.assertEqual(self.facts["cpus"]["mpidr"], ["0x0", "0x900"])
        self.assertEqual(self.facts["psci"], [{"compatible": ["arm,psci-1.0"], "method": ["smc"]}])

    def test_single_cell_children(self):
        display = {d["path"]: d for d in self.facts["display"]}
        self.assertEqual(display["/soc/drmdecon@19100000"]["reg"], [["0x19100000", "0x10000"]])
        self.assertIn("/reserved-memory/framebuffer@fa200000", display)
        self.assertEqual(self.facts["touch"][0]["path"], "/soc/touchscreen@49")
        self.assertEqual(self.facts["uart"][0]["reg"], [["0x10870000", "0x100"]])

    def test_rejects_bad_blobs(self):
        good = blob(TREE)
        with self.assertRaises(ValueError):
            fdt_facts.parse(b"\0" * 40)
        with self.assertRaises(ValueError):
            fdt_facts.parse(good[:-len(good) // 2])
        broken = bytearray(good)
        struct.pack_into(">I", broken, 56, 7)  # first structure token
        with self.assertRaises(ValueError):
            fdt_facts.parse(bytes(broken))


if __name__ == "__main__":
    unittest.main()
