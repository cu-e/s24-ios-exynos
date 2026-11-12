#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074 host tests, second half: the loader variant `loader-diag-xnu-bigwin-md1` as built by docs/procedures/nat-074/build.py.
Evidence kind: host-test. Nothing here runs on, or is sent to, the phone. Needs unicorn and capstone (artifacts/nat-065/venv) and zig:

    artifacts/nat-065/venv/bin/python -W ignore -I docs/procedures/nat-074/test_model.py

Layers (each skips itself, and says why, when what it needs is missing):
  Binary   capstone over the built loader.elf: one call of s5e_wdt_pet in the whole image, inside nat074_pet(); nat074_pet is reached only from
           nat044_tick and nat074_final_pet; recovery_guard still arms once with 83 s and never pets or disarms (NAT-020's rule, unchanged);
           the number of cache-maintenance sites equals the NAT-065 loader's (nothing that cleans the window was removed); the offsets of the
           new struct fields are the compiler's.
  Plan     the compiled nat074_clear_plan() run in unicorn on a grid of layouts against an independent model: spans inside the window, never in the
           reserve, 16 KiB aligned, ordered, total bounded; the real layout of the built payload.
  Pet      the compiled recovery_guard (arms the watchdog and the cap), then the real mk_hold loop with the NAT-044 register model: a pet every 30 s
           while the cap has not passed, none at or after it, the NAT-044 reset sequence unchanged at the cap, no pet after a refused reset,
           nat074_final_pet only before the cap.
The unicorn model has no caches, no MMU and no real memory attributes. It shows the register/memory contract of the new code in the compiled
loader; it is not a measurement of the S24."""
import importlib.util
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROC = HERE.parent
LOADER_SRC = ROOT / "artifacts/nat-020/build-003/source"
NAT065_ELF = ROOT / "artifacts/nat-065/build-001/loader-diag-xnu-md0-usb/loader.elf"
NAME = "loader-diag-xnu-bigwin-md1"
CAP_S, PET_S = 150, 30
MIB = 1 << 20
PAGE = 0x4000


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


try:
    import unicorn
    from unicorn import arm64_const as A
    import capstone
    HAVE_TOOLS = True
except ImportError:
    HAVE_TOOLS = False

import shutil
needs_all = unittest.skipUnless(HAVE_TOOLS and shutil.which("zig") and LOADER_SRC.exists() and NAT065_ELF.exists(),
                                "unicorn/capstone (artifacts/nat-065/venv), zig, or the local NAT-020/NAT-065 artifacts are missing")

if HAVE_TOOLS:
    t44 = _load("nat074_t44", PROC / "nat-044" / "test_nat044.py")      # its Sim (unicorn + PMU/WDT/DECON models) and ElfImage
    Sim, ElfImage = t44.Sim, t44.ElfImage
    PMU, WDT, STACK, FREQ = t44.PMU, t44.WDT, t44.STACK, t44.FREQ
    INFORM2, INFORM3, CMD, REBOOT, DOWNLOAD, NORMAL = t44.INFORM2, t44.INFORM3, t44.CMD, t44.REBOOT, t44.DOWNLOAD, t44.NORMAL

# struct nat044 after NAT-074 (reset44.h): the first fields are NAT-044's; wdt (a struct s5e_wdt, 24 bytes) starts at 56
OFF74 = dict(t0=8, deadline_ticks=16, armed=24, fired=28, wdt=56, pet_ticks=80, t_pet=88, pets=96)

_state = {}


def built():
    """Build the variant once per run with the real build.py (about a minute), into a temporary directory."""
    if "out" not in _state:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name) / "out"
        r = subprocess.run([sys.executable, "-I", str(HERE / "build.py"), "--out", str(out), "--loader-source", str(LOADER_SRC),
                            "--deadline-s", str(CAP_S), "--pet-s", str(PET_S)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("build failed:\n" + r.stderr[-3000:])
        _state["tmp"], _state["out"] = tmp, out
    return _state["out"]


def tearDownModule():
    if "tmp" in _state:
        _state["tmp"].cleanup()


def header_values(tree):
    text = (Path(tree) / "nat074.h").read_text()
    vals = {}
    for k in ("NAT074_RESERVE_BYTES", "NAT074_CLEAR_AFTER", "NAT074_CLEAR_TOP", "NAT074_PET_S"):
        m = re.search(r"#define %s\s+\(?(\d+)(?:ULL)?(?: << (\d+))?\)?" % k, text)
        vals[k] = int(m.group(1)) << int(m.group(2) or 0)
    return vals


def disasm_functions(elf_path):
    """{name: [capstone instructions]} for every sized text symbol of the ELF, plus the symbol table."""
    img = ElfImage(elf_path)
    cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    out = {}
    for name, size in img.size.items():
        if not size or name not in img.sym:
            continue
        try:
            addr, code = img.code(name)
        except AssertionError:
            continue
        out[name] = list(cs.disasm(code, addr))
    return img, out


def bl_targets(insns):
    for i in insns:
        if i.mnemonic in ("bl", "b") and i.op_str.startswith("#"):
            yield i.mnemonic, int(i.op_str[1:], 16), i


@needs_all
class Binary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = built() / NAME / "loader.elf"
        cls.img, cls.fns = disasm_functions(cls.path)

    def callers(self, target):
        a = self.img.sym[target]
        return sorted((n, m) for n, ins in self.fns.items() for m, t, _ in bl_targets(ins) if t == a)

    def test_exactly_one_call_of_s5e_wdt_pet_in_the_whole_image_and_it_is_in_nat074_pet(self):
        self.assertEqual(self.callers("s5e_wdt_pet"), [("nat074_pet", "bl")])

    def test_nat074_pet_is_reached_only_from_the_tick_and_the_final_pet(self):
        self.assertEqual(self.callers("nat074_pet"), [("nat044_tick", "b"), ("nat074_final_pet", "b")])

    def test_nat074_final_pet_is_called_once_from_the_loader_before_the_jump(self):
        self.assertEqual(self.callers("nat074_final_pet"), [("loader_main", "bl")])

    def test_the_guard_arms_once_for_83_seconds_and_still_never_pets_or_disarms(self):
        ins = self.fns["recovery_guard"]
        arm = self.img.sym["s5e_wdt_arm"]
        calls = [i for m, t, i in bl_targets(ins) if m == "bl" and t == arm]
        self.assertEqual(len(calls), 1)
        before = [i for i in ins if calls[0].address - 20 <= i.address < calls[0].address]
        self.assertTrue(any(i.mnemonic == "mov" and i.op_str == "w1, #0x53" for i in before))
        forbidden = {self.img.sym["s5e_wdt_pet"], self.img.sym["s5e_wdt_disarm"]}
        self.assertFalse([i for m, t, i in bl_targets(ins) if t in forbidden])

    def test_the_cap_is_the_immediate_of_the_build_and_the_pet_period_is_computed_without_a_multiply(self):
        # the compiler turns freq * 30 into (freq << 5) - (freq << 1); the cap is a mov-immediate multiplied by the counter frequency.
        # The behaviour of both is tested by execution in Pet; this pins the build parameters in the binary.
        text = [(i.mnemonic, i.op_str) for i in self.fns["nat044_arm"]]
        self.assertIn(("mov", "w10, #0x96"), text)                       # 150 s
        self.assertIn(("lsl", "x10, x8, #5"), text)
        self.assertIn(("sub", "x10, x10, x8, lsl #1"), text)

    def test_cache_maintenance_sites_are_those_of_the_nat065_loader(self):
        def sites(path):
            _, fns = disasm_functions(path)
            return sum(1 for ins in fns.values() for i in ins if i.mnemonic == "dc" and "civac" in i.op_str)
        self.assertEqual(sites(self.path), sites(NAT065_ELF))
        self.assertGreater(sites(self.path), 0)

    def test_the_offsets_used_by_the_model_are_the_compilers(self):
        tree = built() / NAME / "source/shim/e1s-xnu"
        with tempfile.TemporaryDirectory() as t:
            c = Path(t) / "o.c"
            c.write_text('#include <stddef.h>\n#include <stdio.h>\n#include "reset44.h"\nint main(void){\n' +
                         "".join('printf("%s %%zu\\n", offsetof(struct nat044, %s));\n' % (k, k) for k in OFF74) + "return 0;}\n")
            r = subprocess.run(["cc", f"-I{tree}", "-DNAT044_DEADLINE_S=150", "-DNAT044_REASON=S5E_REASON_DOWNLOAD", str(c), "-o", str(Path(t) / "o")],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = {l.split()[0]: int(l.split()[1]) for l in subprocess.run([str(Path(t) / "o")], capture_output=True, text=True).stdout.splitlines()}
            self.assertEqual(got, OFF74)


def model_plan(win_base, mem_end, kernel_end, reserve, after, top):
    """Independent model of what the loader may clear (written from the design, not from the C text)."""
    rbase = kernel_end - reserve
    top_base = mem_end - top
    spans = [(win_base, rbase - win_base), (kernel_end, min(after, top_base - kernel_end)), (top_base, top)]
    return spans


@needs_all
class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = built()
        cls.tree = out / NAME / "source/shim/e1s-xnu"
        cls.elf = ElfImage(out / NAME / "loader.elf")
        cls.h = header_values(cls.tree)

    def run_plan(self, win_base, mem_end, kernel_end):
        s = Sim(self.elf)
        s.limit_s = 1e9
        buf = STACK + 0x8000
        total = s.call("nat074_clear_plan", win_base, mem_end, kernel_end, buf)
        raw = bytes(s.mu.mem_read(buf, 48))
        spans = [struct.unpack_from("<QQ", raw, 16 * i) for i in range(3)]
        return total, spans

    def check(self, win_base, win_size, kernel_off, reserve=None):
        h = self.h
        reserve = h["NAT074_RESERVE_BYTES"] if reserve is None else reserve
        mem_end = win_base + win_size
        kernel_end = win_base + kernel_off
        total, spans = self.run_plan(win_base, mem_end, kernel_end)
        want = model_plan(win_base, mem_end, kernel_end, reserve, h["NAT074_CLEAR_AFTER"], h["NAT074_CLEAR_TOP"])
        self.assertEqual(spans, want)
        self.assertEqual(total, sum(n for _, n in want))
        rb, re_ = kernel_end - reserve, kernel_end
        for base, n in spans:
            self.assertGreaterEqual(base, win_base)
            self.assertLessEqual(base + n, mem_end)
            self.assertFalse(base < re_ and base + n > rb and n, "a span touches the reserve: %#x+%#x vs [%#x,%#x)" % (base, n, rb, re_))
            self.assertEqual(base % PAGE, 0)
            self.assertEqual(n % PAGE, 0)
        self.assertEqual(spans, sorted(spans))
        return total, spans

    def test_the_layout_of_the_built_payload(self):
        p = (built() / NAME / "payload.adt8.bin").read_bytes()
        virt_base, _e, _ao, _as, kernel_end_va, _pb, mem_size = struct.unpack_from("<7Q", p, 0x10)
        win_base, win = 0x8FE400000, mem_size
        total, spans = self.check(win_base, win, kernel_end_va - virt_base)
        self.assertEqual(win, 4096 * MIB)
        self.assertLessEqual(total, 140 * MIB)             # kernel + md0 area, 64 MiB above the ADT, 2 MiB PRAM: about 139.5 MiB
        self.assertGreater(total, 100 * MIB)
        self.assertEqual(spans[0][0], win_base)
        self.assertEqual(spans[2][0] + spans[2][1], win_base + win)

    def test_a_grid_of_layouts_obeys_the_invariants(self):
        r = self.h["NAT074_RESERVE_BYTES"]
        for win_size in (4096 * MIB, 3000 * MIB, 2600 * MIB):
            for kernel_off in (r + 64 * MIB, r + 73 * MIB, r + 120 * MIB, win_size - 80 * MIB, win_size - 3 * MIB):
                if kernel_off > win_size - self.h["NAT074_CLEAR_TOP"] - MIB:
                    continue
                self.check(0x8FE400000, win_size, kernel_off)

    def test_little_room_above_the_adt_cuts_the_after_span_and_never_overlaps_the_top_span(self):
        r = self.h["NAT074_RESERVE_BYTES"]
        win = 4096 * MIB
        kernel_off = win - 10 * MIB                         # 8 MiB between kernel_end and the top span
        total, spans = self.check(0x8FE400000, win, kernel_off)
        self.assertEqual(spans[1][1], 8 * MIB)
        self.assertEqual(spans[1][0] + spans[1][1], spans[2][0])

    def test_the_reserve_is_skipped_when_it_is_the_only_thing_below_the_kernel(self):
        r = self.h["NAT074_RESERVE_BYTES"]
        total, spans = self.check(0x8FE400000, 4096 * MIB, r)      # kernel_end - reserve == win_base
        self.assertEqual(spans[0][1], 0)

    def test_a_zero_reserve_degrades_to_clearing_below_the_kernel_end_only(self):
        # the compiled constant is fixed; this checks the model's reading of the span arithmetic with the actual code at reserve == 0 is not possible
        # without a second build, so only the invariants of the model itself are asserted here
        want = model_plan(0x8FE400000, 0x8FE400000 + 4096 * MIB, 0x8FE400000 + 100 * MIB, 0, 64 * MIB, 2 * MIB)
        self.assertEqual(want[0], (0x8FE400000, 100 * MIB))


@needs_all
class Pet(unittest.TestCase):
    """The compiled recovery_guard arms the 83 s watchdog and the cap; the real mk_hold loop polls the tick."""
    @classmethod
    def setUpClass(cls):
        cls.elf = ElfImage(built() / NAME / "loader.elf")

    def armed_sim(self, i3=NORMAL, fault_off=None):
        s = Sim(self.elf, {INFORM3: i3, INFORM2: 0x0AA50011, CMD: 0xD})
        s.mu.mem_write(self.elf.sym["diagnostic_value"], struct.pack("<I", 0xD65F03C0))    # `ret`: no UI in this model
        s.limit_s = 1e9
        self.assertEqual(s.call("recovery_guard") & 0xFFFFFFFF, 0)
        s.fault_off = fault_off
        self.t0 = s.g("t0")
        self.refresh0 = len(s.wdt_events)
        return s

    def g74(self, s, name):
        a = self.elf.sym["g_nat044"] + OFF74[name]
        n = 8 if name in ("t0", "deadline_ticks", "pet_ticks", "t_pet") else 4
        return int.from_bytes(bytes(s.mu.mem_read(a, n)), "little")

    def hold(self, s, limit_s):
        s.limit_s = limit_s
        s.mu.reg_write(A.UC_ARM64_REG_SP, STACK + 0xF000)
        s.mu.reg_write(A.UC_ARM64_REG_X0, 0x40)
        s.mu.reg_write(A.UC_ARM64_REG_X1, 0)
        s.mu.reg_write(A.UC_ARM64_REG_X30, t44.STOPPAGE)
        s.mu.emu_start(s.elf.sym["mk_hold"], 0, count=4_000_000_000)

    def pets(self, s):
        """Times (seconds after the arm) of the pet stores: WTCLRINT (0xC) <- 0 followed by WTCNT (0x8) <- WTDAT."""
        # s5e_wdt_pet(): timer[3] = 0 (WTCLRINT, 0xC); timer[2] = timer[1] (read WTDAT at 4, store it to WTCNT at 8)
        wtdat = next(v for k, o, v, _ in s.wdt_events if k == "W" and o == 4)
        out, ev = [], s.wdt_events[self.refresh0:]
        for n, (k, o, v, c) in enumerate(ev):
            if k == "W" and o == 0xC and v == 0:
                nxt = [e[:3] for e in ev[n + 1:n + 3]]
                if nxt == [("R", 4, wtdat), ("W", 8, wtdat)]:
                    out.append((c - self.t0) / FREQ)
        return out

    def pmu_writes(self, s):
        return [(o, v) for k, o, v, _ in s.pmu_events if k == "W"]

    def test_a_pet_every_30_seconds_until_the_cap_and_the_nat044_reset_sequence_at_the_cap(self):
        s = self.armed_sim()
        self.assertEqual(self.g74(s, "deadline_ticks"), FREQ * CAP_S)
        self.assertEqual(self.g74(s, "pet_ticks"), FREQ * PET_S)
        s.pmu_events.clear()
        self.hold(s, 400)
        pets = self.pets(s)
        self.assertEqual(len(pets), 4, pets)
        for n, t in enumerate(pets, 1):
            self.assertGreaterEqual(t, PET_S * n)
            self.assertLess(t, PET_S * n + 0.2)
        self.assertEqual(self.g74(s, "pets"), 4)
        self.assertIsNotNone(s.trigger_clk)
        dt = (s.trigger_clk - self.t0) / FREQ
        self.assertGreaterEqual(dt, CAP_S)
        self.assertLess(dt, CAP_S + 0.2)
        self.assertLess(pets[-1], dt)
        self.assertEqual(self.pmu_writes(s), [(INFORM2, 0x0A4E0011), (INFORM3, DOWNLOAD), (CMD, 0x8), (REBOOT, 2)])

    def test_the_watchdog_is_refreshed_often_enough_that_it_could_not_expire_before_the_cap(self):
        s = self.armed_sim()
        self.hold(s, 400)
        marks = [0.0] + self.pets(s) + [(s.trigger_clk - self.t0) / FREQ]
        gaps = [b - a for a, b in zip(marks, marks[1:])]
        self.assertLess(max(gaps), 83 - 20)                # the longest stretch without a refresh, including the one into the reset

    def test_a_refused_reset_leaves_the_watchdog_unpetted_so_it_can_still_end_the_run(self):
        s = self.armed_sim(fault_off=INFORM3)               # the first read of INFORM3 after its store differs: s5e_reset_to() refuses
        s.stop_on_trigger = True
        self.hold(s, CAP_S + 120)
        pets = self.pets(s)
        self.assertIsNone(s.trigger_clk)                    # nothing was triggered
        self.assertEqual(len(pets), 4, pets)                # the four before the cap
        self.assertTrue(all(t < CAP_S for t in pets))       # none after it, although 120 s more were simulated
        self.assertEqual(self.g74(s, "armed"), 0)

    def test_final_pet_before_the_cap_pets_once_and_after_the_cap_not_at_all(self):
        s = self.armed_sim()
        s.clk += int(10 * FREQ)
        s.call("nat074_final_pet")
        self.assertEqual([round(t) for t in self.pets(s)], [10])
        s.clk += int((CAP_S + 1 - 10) * FREQ)
        before = len(s.wdt_events)
        s.call("nat074_final_pet")
        self.assertEqual(len(s.wdt_events), before)
        self.assertEqual(self.g74(s, "pets"), 1)

    def test_final_pet_does_nothing_when_the_cap_is_set_but_the_loader_is_not_armed(self):
        s = self.armed_sim()
        s.mu.mem_write(self.elf.sym["g_nat044"] + OFF74["armed"], struct.pack("<I", 0))     # deadline/t0 stay: armed == 0 (no PMU window)
        s.clk += int(10 * FREQ)
        n = len(s.wdt_events)
        s.call("nat074_final_pet")
        self.assertEqual(len(s.wdt_events), n)

    def test_final_pet_does_nothing_when_the_deadline_was_never_armed(self):
        s = Sim(self.elf, {INFORM3: NORMAL})
        s.limit_s = 1e9
        s.call("nat074_final_pet")
        self.assertEqual(s.wdt_events, [])

    def test_no_pet_without_the_arm_call(self):
        s = Sim(self.elf, {INFORM3: NORMAL})
        s.call("nat044_snapshot", PMU)
        s.pmu_events.clear()
        self.hold(s, 100)
        self.assertEqual([e for e in s.wdt_events if e[0] == "W"], [])

    def test_a_watchdog_that_did_not_arm_arms_no_cap_and_so_no_pet(self):
        s = Sim(self.elf, {INFORM3: NORMAL})
        s.wdt_fault = True
        s.mu.mem_write(self.elf.sym["diagnostic_value"], struct.pack("<I", 0xD65F03C0))
        s.limit_s = 1e9
        self.assertEqual(s.call("recovery_guard") & 0xFFFFFFFF, 0xFFFFFFFF)
        self.assertEqual(self.g74(s, "armed"), 0)
        n = len(s.wdt_events)
        self.hold(s, 100)
        self.assertEqual([e for e in s.wdt_events[n:] if e[0] == "W"], [])


needs_build = unittest.skipUnless(shutil.which("zig") and LOADER_SRC.exists(), "zig or the local NAT-020 build tree is missing")


@needs_build
class BuildRules(unittest.TestCase):
    """The pure checks of build.py: the root size, the pet/cap rules, the layout facts of a payload."""
    @classmethod
    def setUpClass(cls):
        cls.b = _load("nat074_build", HERE / "build.py")

    def test_the_reserve_is_the_root_size_rounded_up_to_16_kib_and_a_size_the_md_device_would_truncate_is_refused(self):
        self.assertEqual(self.b.reserve_for(2475712512), 2475720704)
        self.assertEqual(self.b.reserve_for(16384), 16384)
        self.assertEqual(self.b.reserve_for(4096), 16384)
        for bad in (0, -4096, 4097, 2475712513):
            with self.assertRaises(SystemExit):
                self.b.reserve_for(bad)

    def test_the_pet_and_cap_rules(self):
        ok = self.b.check_rules
        ok(83, 150, 30)
        ok(83, 600, 30)
        ok(83, 31, 30)
        ok(83, 150, 63)                                      # 63 + 20 == 83: the last pet period that leaves the margin
        for wdt, cap, pet in ((60, 150, 30),                  # the rules are written for the 83 s of guard.c
                              (83, 150, 64),                  # pet + 20 s > 83 s
                              (83, 150, 0), (83, 150, -1),
                              (83, 30, 30), (83, 29, 30),     # the cap must be longer than one pet period
                              (83, 601, 30)):
            with self.assertRaises(SystemExit, msg=(wdt, cap, pet)):
                ok(wdt, cap, pet)

    def test_the_layout_check_of_a_payload(self):
        payload = (built() / NAME / "payload.adt8.bin").read_bytes()
        r = self.b.reserve_for(2475712512)
        lay = self.b.check_layout(payload, r)
        self.assertEqual(lay["reserve_offset"] + lay["reserve_bytes"], lay["kernel_end_offset"])
        self.assertGreaterEqual(lay["free_above_boot_args_mib"], 1024)
        with self.assertRaises(SystemExit):                  # a reserve larger than everything below kernel_end
            self.b.check_layout(payload, lay["kernel_end_offset"] + 0x4000)
        small = bytearray(payload)
        struct.pack_into("<Q", small, 0x10 + 6 * 8, 512 * MIB)    # mem_size: the old 512 MiB limiter
        with self.assertRaises(SystemExit):
            self.b.check_layout(bytes(small), r)
        tight = bytearray(payload)
        struct.pack_into("<Q", tight, 0x10 + 6 * 8, 4096 * MIB)
        struct.pack_into("<Q", tight, 0x10 + 4 * 8, struct.unpack_from("<Q", payload, 0x10)[0] + 3200 * MIB)   # kernel_end 3200 MiB up
        with self.assertRaises(SystemExit):                  # less than 1024 MiB would be free above boot_args
            self.b.check_layout(bytes(tight), r)


@needs_all
class PayloadLayout(unittest.TestCase):
    """The reserve-only RAMDisk1 in the built payload: where it is, that it carries no bytes, that nothing else overlaps it."""
    @classmethod
    def setUpClass(cls):
        cls.payload = (built() / NAME / "payload.adt8.bin").read_bytes()
        tools = LOADER_SRC / "tools/e1s/xnu"
        cls.adt = _load("nat074_adt", tools / "adt.py")
        hdr = struct.unpack_from("<7Q", cls.payload, 0x10)
        (cls.virt_base, cls.entry, cls.adt_off, cls.adt_size, cls.kernel_end, cls.phys_base, cls.mem_size) = hdr
        cls.nseg = struct.unpack_from("<8sII", cls.payload)[2]
        cls.segs = [struct.unpack_from("<4Q", cls.payload, 0x2A8 + 32 * i) for i in range(cls.nseg)]
        root, _ = cls.adt.parse(cls.payload[cls.adt_off:cls.adt_off + cls.adt_size])
        chosen = next(c for c in root.children if c.name == "chosen")
        cls.mmap = next(c for c in chosen.children if c.name == "memory-map")
        cls.chosen = chosen

    def prop(self, name):
        return struct.unpack("<2Q", self.mmap.prop(name))

    def test_ramdisk1_is_the_reserve_and_ends_exactly_at_kernel_end(self):
        pa, size = self.prop("RAMDisk1")
        self.assertEqual(size, 2475720704)
        self.assertEqual(pa, self.phys_base + (self.kernel_end - size) - self.virt_base)
        self.assertEqual(pa % PAGE, 0)

    def test_md0_is_below_the_reserve_and_the_two_ranges_do_not_overlap(self):
        pa0, size0 = self.prop("RAMDisk")
        pa1, size1 = self.prop("RAMDisk1")
        self.assertEqual(size0, 0x8000)                      # the 16,635-byte probe, padded to 16 KiB pages
        self.assertLessEqual(pa0 + size0, pa1)
        self.assertEqual(pa0 + size0, pa1)                   # and adjacent: nothing in between

    def test_no_segment_and_no_payload_bytes_lie_in_the_reserve(self):
        pa1, size1 = self.prop("RAMDisk1")
        lo = self.virt_base + (pa1 - self.phys_base)
        hi = lo + size1
        for vm, vsz, off, n in self.segs:
            self.assertFalse(vm < hi and vm + vsz > lo, "segment %#x+%#x touches the reserve" % (vm, vsz))
        self.assertLess(len(self.payload), 128 * MIB)         # a 2.3 GiB reserve is not in the file

    def test_the_header_window_is_4_gib_and_the_adts_own_dram_size_is_untouched(self):
        self.assertEqual(self.mem_size, 4096 * MIB)
        orig, _ = self.adt.parse((ROOT / "artifacts/nat-020/build-003/e1s.adt").read_bytes())
        want = next(c for c in orig.children if c.name == "chosen").prop("dram-size")
        self.assertEqual(self.chosen.prop("dram-size"), want)

    def test_the_command_line_is_nat067s_with_the_nat075_tag(self):
        field = self.payload[0x48:0x48 + 608]                  # mkpayload.py: CMDLINE = 0x48, field 608 bytes, segment table at 0x2a8
        cmd = field.rstrip(b"\0").decode()
        self.assertEqual(field[len(cmd):], b"\0" * (608 - len(cmd)))
        b67 = _load("nat074_b67", PROC / "nat-067" / "build.py")
        self.assertTrue(cmd.startswith("rd=md0 "))
        self.assertEqual(cmd.count("nat_attempt=NAT075-md1"), 1)
        self.assertTrue(cmd.endswith(b67.APPEND), cmd)
        for must in ("e1stouch=0", "e1sbattery=0", "loader_return_after=8", "launchdsuffix=release", "cs_enforcement_disable=1"):
            self.assertIn(must, cmd.split())
        self.assertNotIn("NAT067", cmd)
        self.assertNotIn("NAT065", cmd)
        self.assertLess(len(cmd), 256)

    def test_adt_header_fields_are_aligned_for_the_loader(self):
        self.assertEqual(self.adt_off % 8, 0)
        self.assertEqual(self.adt_size % 8, 0)
        self.assertEqual(self.kernel_end % PAGE, 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
