"""NAT-045 tests: the USB bring-up ladder of the loader (src/ladder.c, src/ladder_usb.c, generated src/ladder_regs.h).

    python3 -I docs/procedures/nat-045/test_nat045.py                       # table, x86 ladder, default build, L6-L8 (needs cc)
    capvenv/bin/python -I docs/procedures/nat-045/test_nat045.py            # + the aarch64 layer (needs unicorn, capstone, zig)

Layers
  Table      derive.py --check passes; the generated table is the one in the header and in ladder_ops.json; anchors from the
             vendor sources (addresses, masks, values, delays, order); coverage of the NAT-040 plan ladder; no hardware constant in
             ladder.c or ladder_usb.c.
  Generator  derive.py refuses what it cannot model: a vendor text that is not in the pinned source, a field value that does not fit its
             field, a conditional PMUCAL row, an unknown PMUCAL type, a plan row the ladder does not carry (by kind, mask and value).
  Ladder     the writing build on x86 against test_support/plat.c: the whole run (and a run with the domain already on) equals the
             reference interpreter in devmodel.py access by access with virtual time; stop-at-first-failure for every written
             address; wait timeout, power-on refusal, liveness words, DWC3 ids, stop rungs, no access to the HSI0 block while the
             domain is off.
  Default    the build without LAD_WRITING_RUNGS: stops after L2, never writes, never delays, refuses L3 and above.
  Usb        L6-L8: the NAT-041 engine behind the ladder, init after the last rung, stop codes of the three steps.
  Aarch64    the ladder compiled for aarch64 with the loader's port, run in unicorn: same accesses/values/times as the reference;
             the default object has no store to the platform and no counter read.

What this is not: the S24. plat.c / devmodel.py are the contract the ladder was written against (register file, a power domain gate,
virtual time); the NAT-041 DWC3 model is a reading of the databook. Nothing here ran on the phone.
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "test_support"))

import devmodel as D          # noqa: E402
import plathost as H          # noqa: E402

try:
    import unicorn            # noqa: F401
    import capstone
    HAVE_SIM = True
except ImportError:
    HAVE_SIM = False

SRC = H.SRC
PLAN = os.path.join(os.path.dirname(HERE), "nat-040", "plan.json")
_TMP = tempfile.mkdtemp(prefix="nat045-test-")
_LIBS = {}


def lib(writing):
    if writing not in _LIBS:
        _LIBS[writing] = H.build(writing=writing, out_dir=_TMP)
    return _LIBS[writing]


def table_variant(transform, tag):
    """A Plat built from a copy of src/ with `transform(text)` applied to ladder_regs.h (a table the generator would never write)."""
    import shutil
    d = tempfile.mkdtemp(prefix="nat045-variant-%s-" % tag, dir=_TMP)
    for n in ("ladder.c", "ladder_usb.c", "ladder.h", "ladder_regs.h"):
        shutil.copy(os.path.join(SRC, n), d)
    path = os.path.join(d, "ladder_regs.h")
    text = slurp(path)
    new_text = transform(text)
    assert new_text != text, "the transform changed nothing"
    with open(path, "w") as f:
        f.write(new_text)
    p = H.Plat(H.build(writing=True, ladder_dir=d, out_dir=_TMP))
    p.reset()
    return p


def slurp(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


TABLE = H.ops()
NOPS = len(TABLE)
FIRST = {r: min(o["i"] for o in TABLE if o["rung"] == r) for r in range(1, 6)}
WRITE_KINDS = ("WRP", "WRM", "STORE")
L5_DELAYS = [500, 500, 10, 10, 10, 1000, 28, 2500]
PMU_CFG_ADDR, PMU_STATUS_ADDR = H.PMU_CFG, H.PMU_STATUS


def new(writing=True, **kw):
    p = H.Plat(lib(writing))
    p.standard_fixture(**kw)
    return p


def ref(stop, writing=True, pd_on=False, allow_poweron=True, pd_wait_us=0, follow=True, delay_cost=lambda us: us, flip=None, gsnpsid=None):
    dev = D.DevModel(TABLE, pd_on=pd_on, follow=follow, delay_cost=delay_cost, **({"gsnpsid": gsnpsid} if gsnpsid is not None else {}))
    dev.flip = dict(flip or {})
    err, st = D.ref_run(TABLE, dev, stop, allow_poweron=allow_poweron, pd_wait_us=pd_wait_us, writing=writing)
    return dev, err, st


def err_tuple(rc):
    r, name = H.decode_err(rc)
    return None if rc == 0 else (r, name)


# ------------------------------------------------------------------------------------------------------------------------ Table
class Table(unittest.TestCase):
    def test_derive_check_passes_against_the_vendor_sources_and_the_plan(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "derive.py"), "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)

    def test_the_header_the_json_and_the_compiler_agree_on_the_table(self):
        d, bases = H.ops_json()
        self.assertEqual(len(d["ops"]), NOPS)
        for o, j in zip(TABLE, d["ops"]):
            self.assertEqual((o["i"], o["rung"], o["kind"]), (j["i"], j["rung"], j["kind"]))
            if "addr" in j:
                self.assertEqual(o["addr"], int(j["addr"], 0), j["label"])
            if "mask" in j:
                self.assertEqual(o["mask"], int(j["mask"], 0), j["label"])
            if "val" in j:
                self.assertEqual(o["val"], int(j["val"], 0), j["label"])
        p = new()
        self.assertEqual(p.lib.n_nops(), NOPS)
        self.assertEqual(p.lib.n_selfcheck(), 0)

    def test_rung_layout(self):
        kinds = {r: [o["kind"] for o in TABLE if o["rung"] == r] for r in range(1, 6)}
        self.assertEqual([len(kinds[r]) for r in range(1, 6)], [2, 3, 21, 1, 84])
        for r in (1, 2, 4):
            self.assertEqual(set(kinds[r]), {"RD"}, "L%d must be read-only" % r)
        self.assertEqual([o["rung"] for o in TABLE], sorted(o["rung"] for o in TABLE))        # rungs are contiguous and in order

    def test_l1_l2_l4_read_exactly_the_registers_the_plan_names(self):
        self.assertEqual([o["addr"] for o in TABLE if o["rung"] == 1], [0x12862000, 0x12862004])
        self.assertEqual([o["addr"] for o in TABLE if o["rung"] == 2], [0x22B210C8, 0x22B220C4, 0x22B218A8])
        l4 = [o for o in TABLE if o["rung"] == 4]
        self.assertEqual([(o["addr"], o["flags"]) for o in l4], [(0x1790C120, D.F_DWC3ID)])

    def test_l3_is_the_vendor_power_on_the_cmu_init_rows_and_the_documented_reads(self):
        l3 = [o for o in TABLE if o["rung"] == 3]
        writes = [(o["kind"], o["addr"], o["mask"], o["val"], o["flags"]) for o in l3 if o["kind"] != "RD"]
        self.assertEqual(writes, [
            ("WRM", 0x12862000, 0x1, 0x1, D.F_POWERON),
            ("WAIT", 0x12862004, 0x1, 0x1, D.F_POWERON),
            ("WRM", 0x17801000, 0x10, 0x00, D.F_CMUINIT),
            ("WRM", 0x17801004, 0x10, 0x00, D.F_CMUINIT),
            ("WRM", 0x17801008, 0x10, 0x10, D.F_CMUINIT),
            ("WRM", 0x17801800, 0x1F, 0x01, D.F_CMUINIT),
            ("WRM", 0x17800630, 0x10, 0x10, D.F_CMUINIT),
            ("WRM", 0x17800640, 0x10, 0x10, D.F_CMUINIT),
            ("WRM", 0x17800800, 0xFF000000, 0xF1000000, D.F_CMUINIT),
            ("WRP", 0x17820104, 0xFFFFFFFF, 0xFFFFFFFF, D.F_CMUINIT),     # plain write: the row's mask is U32_MAX
        ])
        self.assertEqual([o["addr"] for o in l3 if o["kind"] == "RD"],
                         [0x17801008, 0x17801800, 0x17800640, 0x17800630, 0x17800800,
                          0x1780305C, 0x17803054, 0x17803058, 0x1780300C, 0x17803060, 0x17820104])

    def test_l5_store_sequence_from_a_zero_register_file(self):
        p = new(pd_on=True)                                  # the domain is on: L3 writes nothing, so L5's writes are the whole log
        self.assertEqual(p.run(stop=5), 0)
        writes = [(a, v) for k, a, v, t in p.log() if k == "W"]
        self.assertEqual(writes, [
            (0x1286061C, 0x1),                               # isolation released (value 1 = bit set: the vendor's `on = 0 -> val = mask`)
            (0x178A0004, 0x1E00), (0x178A0004, 0x101FF0),    # init_link: LINKCTRL qact disables, then force_qact + bus_filter
            (0x178A000C, 0x1), (0x178A000C, 0x0),            # link_sw_rst pulse
            (0x178A0010, 0x3),                               # force bvalid + vbusvalid
            (0x178A0050, 0x0), (0x178A0058, 0x01000000), (0x178A005C, 0xFF00), (0x178A0060, 0x1),
            (0x178A0054, 0x1111), (0x178A006C, 0x70007),     # ready_rewa (not in the NAT-040 plan)
            (0x178A0004, 0x151FF0),                          # detach_pipe3
            (0x178A000C, 0x0),
            (0x178B0000, 0x33), (0x178B0004, 0x400), (0x178B0008, 0x17000), (0x178B000C, 0x0), (0x178B0008, 0x17000),
            (0x178B0014, 0x0), (0x178B0020, 0x0), (0x178B0004, 0x400),
            (0x178B0000, 0x32), (0x178B0004, 0x401), (0x178B0000, 0x02),
        ])
        # the same sequence with the domain off adds exactly the L3 writes before it
        q = new(pd_on=False)
        q.run(stop=5)
        qw = [(a, v) for k, a, v, t in q.log() if k == "W"]
        self.assertEqual(qw[9:], writes)
        self.assertEqual(qw[:9], [(0x12862000, 1), (0x17801000, 0), (0x17801004, 0), (0x17801008, 0x10), (0x17801800, 1),
                                  (0x17800630, 0x10), (0x17800640, 0x10), (0x17800800, 0xF1000000), (0x17820104, 0xFFFFFFFF)])

    def test_the_l5_isolation_release_is_one_masked_write_of_the_vendor_bit(self):
        l5 = [o for o in TABLE if o["rung"] == 5 and o["kind"] in ("WRM", "WRP", "WAIT")]
        self.assertEqual([(o["kind"], o["addr"], o["mask"], o["val"]) for o in l5], [("WRM", 0x1286061C, 0x1, 0x1)])

    def test_a_read_modify_write_group_loads_and_stores_the_same_register(self):
        """LOAD, SET..., STORE (possibly several STOREs of one LOAD) is `reg = readl(X); ...; writel(reg, X)`: the two addresses are the same register.
        A CONST group has no LOAD."""
        loaded, have = None, False
        for o in TABLE:
            if o["rung"] != 5:
                continue
            if o["kind"] == "LOAD":
                loaded, have = o["addr"], True
            elif o["kind"] == "CONST":
                loaded, have = None, True
            elif o["kind"] == "SET":
                self.assertTrue(have, "a SET before any LOAD or CONST: %s" % o["label"])
            elif o["kind"] == "STORE":
                self.assertTrue(have, "a STORE before any LOAD or CONST: %s" % o["label"])
                if loaded is not None:
                    self.assertEqual(o["addr"], loaded, o["label"])

    def test_every_set_row_is_what_the_c_compiler_makes_of_the_vendor_statements(self):
        """An oracle that shares nothing with derive.py's layout parser: the vendor register headers and the vendor statements of each SET row
        are compiled by cc, which lays out the bit-fields. mask = the bits of the fields assigned, val = the register after the assignments."""
        root = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        with open(os.path.join(HERE, "ladder_spec.json")) as f:
            spec = json.load(f)
        with open(os.path.join(HERE, "ladder_ops.json")) as f:
            sources = {o["i"]: o["source"] for o in json.load(f)["ops"]}

        def show(path):
            return subprocess.run(["git", "-C", os.path.join(root, "references", "s24-linux"), "show", spec["pin"] + ":" + path],
                                  capture_output=True, text=True, check=True).stdout
        body = []
        for o in TABLE:
            if o["kind"] != "SET":
                continue
            full, orig = [], []
            for stmt in sources[o["i"]].split(" ; "):
                m = re.fullmatch(r"(\(\(\w+\) \(&reg\)\)->b\.\w+) = (\w+)", stmt.strip())
                self.assertIsNotNone(m, stmt)
                full.append("%s = ~0u;" % m.group(1))
                orig.append("%s = %s;" % (m.group(1), m.group(2)))
            body.append('reg = 0; %s printf("%d %%08x ", reg); reg = 0; %s printf("%%08x\\n", reg);' % (" ".join(full), o["i"], " ".join(orig)))
        self.assertEqual(len(body), 22)
        src = ("#include <stdint.h>\n#include <stdio.h>\ntypedef uint32_t u32;\n" + show(spec["files"]["blkcon_h"]) + "\n" + show(spec["files"]["eusbcon_h"]) +
               "\nint main(void) { u32 reg;\n" + "\n".join(body) + "\nreturn 0; }\n")
        d = tempfile.mkdtemp(prefix="oracle-", dir=_TMP)
        with open(os.path.join(d, "o.c"), "w") as f:
            f.write(src)
        r = subprocess.run(["cc", "-w", "-o", os.path.join(d, "o"), os.path.join(d, "o.c")], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        out = subprocess.run([os.path.join(d, "o")], capture_output=True, text=True, check=True).stdout.split("\n")
        got = {int(l.split()[0]): (int(l.split()[1], 16), int(l.split()[2], 16)) for l in out if l}
        self.assertEqual(got, {o["i"]: (o["mask"], o["val"]) for o in TABLE if o["kind"] == "SET"})

    def test_l5_delays_are_the_vendor_ones_in_the_vendor_places(self):
        l5 = [o for o in TABLE if o["rung"] == 5]
        self.assertEqual([o["val"] for o in l5 if o["kind"] == "DELAY"], L5_DELAYS)

        def store_label(i, step):
            j = i + step
            while 0 <= j < NOPS and TABLE[j]["kind"] != "STORE":
                j += step
            return TABLE[j]["label"] if 0 <= j < NOPS and TABLE[j]["rung"] == 5 else None
        around = [(store_label(o["i"], -1), store_label(o["i"], 1)) for o in l5 if o["kind"] == "DELAY"]
        self.assertEqual(around, [
            (None, "USBCON_REG_LINKCTRL"), ("USBCON_REG_LINKCTRL", "USBCON_REG_LINKCTRL"),       # 500, 500 us around the LINKCTRL stores
            ("USBCON_REG_LINK_CLKRST", "USBCON_REG_LINK_CLKRST"),                                # 10 us link_sw_rst pulse
            ("EUSBCON_REG_CMN_CTRL", "EUSBCON_REG_RST_CTRL"), ("EUSBCON_REG_RST_CTRL", "EUSBCON_REG_CMN_CTRL"),   # 10 us, 10 us
            ("EUSBCON_REG_CMN_CTRL", "EUSBCON_REG_RST_CTRL"),                                    # 1000 / 28 / 2500 us after phy_enable
            ("EUSBCON_REG_CMN_CTRL", "EUSBCON_REG_RST_CTRL"), ("EUSBCON_REG_CMN_CTRL", "EUSBCON_REG_RST_CTRL")])
        # the three long delays are adjacent and in this order
        idx = [o["i"] for o in l5 if o["kind"] == "DELAY" and o["val"] in (1000, 28, 2500)]
        self.assertEqual(idx, list(range(idx[0], idx[0] + 3)))

    def test_l5_ends_with_the_read_backs_of_the_documented_registers(self):
        self.assertEqual([(o["kind"], o["addr"]) for o in TABLE[-5:]],
                         [("RD", 0x178A0004), ("RD", 0x178A000C), ("RD", 0x178A0010), ("RD", 0x178B0000), ("RD", 0x178B0004)])

    def test_every_masked_op_has_its_value_inside_its_mask(self):
        # derive.py computes val = vendor value & mask for the PMUCAL rows; on the pinned sources the vendor values are inside their masks anyway
        for o in TABLE:
            if o["kind"] in ("WRM", "WAIT", "SET"):
                self.assertEqual(o["val"] & ~o["mask"] & 0xFFFFFFFF, 0, (o["i"], o["label"]))

    def test_all_plan_ladder_steps_are_covered_or_documented(self):
        with open(PLAN) as f:
            plan = json.load(f)
        lad ={l["id"]: l for l in plan["ladder"]}
        d, _ = H.ops_json()
        documented = {                                         # the steps of L5 that no table row cites, and why (README)
            "1.03": "QCH enable of the PHY clocks is a platform write the ladder does not make (only QCH reads in L3)",
            "1.04": "wrapper call: its content is 2.10-2.13 and the ready_rewa tail",
            "1.06": "wrapper call: its content is 3.01-3.16",
            "3.07": "phy_exynos_eusb_tune returns early without tune_param (DT hs_tune_param disabled): no register access",
            "3.13": "the argument of the 1000 us delay: the row cites no step because its source is `udelay(value)`",
        }
        for r in range(1, 6):
            steps = set(lad["L%d" % r]["steps"])
            cited = {p for o in d["ops"] if o["rung"] == r for p in o["plan"]}
            self.assertEqual(steps - cited, set(documented) if r == 5 else set(), "L%d" % r)
            self.assertLessEqual(cited - steps, {"0.19", "0.20", "0.21"} if r in (1, 3) else set(), "L%d cites steps of another rung" % r)

    def test_ladder_c_and_ladder_usb_c_hold_no_hardware_constant(self):
        for name in ("ladder.c", "ladder_usb.c"):
            text = re.sub(r"/\*.*?\*/|//[^\n]*", "", slurp(os.path.join(SRC, name)), flags=re.S)
            self.assertEqual([h for h in re.findall(r"0x[0-9a-fA-F]{3,}", text) if h.lower() != "0xffffffff"], [], name)    # all-ones is a mask, not a register value

    def test_the_default_object_has_no_store_and_no_delay_symbol(self):
        out = os.path.join(_TMP, "ladder-default.o")
        r = subprocess.run(["cc", "-std=gnu11", "-O2", "-c", '-DUSBMON_PORT_HEADER="plat_port.h"', "-I", SRC, "-I", os.path.join(HERE, "test_support"),
                            "-I", H.ENGINE, os.path.join(SRC, "ladder.c"), "-o", out], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        undefined = {l.split()[-1] for l in subprocess.run(["nm", "-u", out], capture_output=True, text=True).stdout.splitlines() if l.strip()}
        self.assertEqual(undefined, {"usbmon_rd32"})
        out_w = os.path.join(_TMP, "ladder-writing.o")
        subprocess.run(["cc", "-std=gnu11", "-O2", "-c", "-DLAD_WRITING_RUNGS", '-DUSBMON_PORT_HEADER="plat_port.h"', "-I", SRC, "-I",
                        os.path.join(HERE, "test_support"), "-I", H.ENGINE, os.path.join(SRC, "ladder.c"), "-o", out_w], check=True)
        undefined_w = {l.split()[-1] for l in subprocess.run(["nm", "-u", out_w], capture_output=True, text=True).stdout.splitlines() if l.strip()}
        self.assertEqual(undefined_w, {"usbmon_rd32", "usbmon_wr32", "usbmon_delay_us"})       # the check above is not vacuous


# ------------------------------------------------------------------------------------------------------------------------ Generator
def load_derive():
    import importlib.util
    spec = importlib.util.spec_from_file_location("derive45", os.path.join(HERE, "derive.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Generator(unittest.TestCase):
    """derive.py refuses what it cannot model: a spec, a vendor text or a plan that has been made wrong in-process (nothing is written)."""

    @classmethod
    def setUpClass(cls):
        cls.G = load_derive()
        with open(cls.G.SPEC) as f:
            cls.spec = json.load(f)

    def refuses(self, spec, fragment):
        with self.assertRaises(self.G.DeriveError) as cm:
            self.G.build(spec)
        self.assertIn(fragment, str(cm.exception))

    def test_the_pinned_spec_builds_the_table_the_ladder_was_compiled_from(self):
        ops, bases, consts, fn = self.G.build(copy.deepcopy(self.spec))
        self.assertEqual(len(ops), NOPS)
        self.assertEqual([(o["rung"], o["k"]) for o in ops], [(o["rung"], o["kind"]) for o in TABLE])

    def test_a_base_whose_vendor_text_is_not_in_the_file_is_refused(self):
        s = copy.deepcopy(self.spec)
        s["bases"]["PMU"]["text"] += " (not in the vendor file)"
        self.refuses(s, "base PMU: vendor text not found")

    def test_a_base_value_that_is_not_in_its_vendor_text_is_refused(self):
        s = copy.deepcopy(self.spec)
        s["bases"]["PMU"]["value"] = "0x12860004"
        self.refuses(s, "base PMU: value")

    def test_a_constant_whose_vendor_text_is_missing_is_refused(self):
        s = copy.deepcopy(self.spec)
        name = sorted(s["constants"])[0]
        s["constants"][name]["text"] += " (not in the vendor file)"
        self.refuses(s, "constant %s: vendor text not found" % name)

    def test_the_pmucal_semantics_must_be_in_the_vendor_source(self):
        s = copy.deepcopy(self.spec)
        s["pmucal_semantics"]["verify"][0] = "if (seq->mask == NOT_THE_VENDOR_TEXT)"
        with self.assertRaises(self.G.DeriveError):
            self.G.build(s)

    def test_an_omitted_cmu_init_row_must_exist_in_the_vendor_array(self):
        s = copy.deepcopy(self.spec)
        s["rungs"]["L3"]["cmu_init"]["omit"].append({"name": "NO_SUCH_ROW", "plan_step": "0.20"})
        self.refuses(s, "a row the spec omits is not in the vendor array")
        s = copy.deepcopy(self.spec)
        s["rungs"]["L3"]["cmu_init"]["omit"] = s["rungs"]["L3"]["cmu_init"]["omit"][:1]       # a row the spec no longer omits is a row the ladder would write
        with self.assertRaises(self.G.DeriveError):
            self.G.build(s)
            problems, _ = self.G.check_plan(s, *[self.G.build(copy.deepcopy(s))[i] for i in (0, 3)])
            raise self.G.DeriveError("; ".join(problems) or "the ladder would write a row the plan does not list")

    def test_the_isolation_text_must_be_in_the_vendor_source(self):
        s = copy.deepcopy(self.spec)
        s["rungs"]["L5"]["isolation"]["verify"][0]["text"] += " (not in the vendor file)"
        self.refuses(s, "isolation verify text missing")

    def test_the_text_a_part_relies_on_must_be_in_the_vendor_source(self):
        for pi, part in enumerate(self.spec["rungs"]["L5"]["parts"]):
            for where, lst in (("verify", part.get("verify", [])), ("inline_call", part.get("inline_call", {}).get("verify", []))):
                for vi in range(len(lst)):
                    s = copy.deepcopy(self.spec)
                    p = s["rungs"]["L5"]["parts"][pi]
                    (p["verify"] if where == "verify" else p["inline_call"]["verify"])[vi]["text"] += " (not in the vendor file)"
                    self.refuses(s, "verify text missing")

    def test_the_gsnpsid_mask_must_be_the_upper_half(self):
        s = copy.deepcopy(self.spec)
        s["rungs"]["L4"]["ids"]["mask"] = "DWC3_IP"
        self.refuses(s, "DWC3_GSNPSID_MASK is not the upper half")

    def test_a_field_value_that_does_not_fit_its_field_is_refused(self):
        key = (self.spec["pin"], self.spec["files"]["blkcon_c"])
        original = self.G.vendor(*key)
        self.assertIn("b.link_sw_rst = 1;", original)
        self.G._cache[key] = original.replace("b.link_sw_rst = 1;", "b.link_sw_rst = 3;")
        try:
            self.refuses(copy.deepcopy(self.spec), "does not fit 1 bits")
        finally:
            self.G._cache[key] = original

    def test_a_conditional_pmucal_row_is_refused(self):
        row = {"cond_base": 0, "cond_offset": 0, "name": "X"}
        self.assertIs(self.G.used(row), row)
        for cond in ({"cond_base": 1, "cond_offset": 0}, {"cond_base": 0, "cond_offset": 8}):
            with self.assertRaises(self.G.DeriveError):
                self.G.used(dict(row, **cond))

    def test_the_pin_must_be_a_full_sha_that_resolves_in_the_vendor_checkout(self):
        self.G.check_pin(self.spec["pin"])
        for bad in ("abc", self.spec["pin"][:39], "0" * 40, self.spec["pin"].upper()):
            with self.assertRaises(self.G.DeriveError):
                self.G.check_pin(bad)

    def test_consecutive_sets_of_one_register_merge_with_the_later_field_winning(self):
        sets = [{"k": "SET", "mask": 0xF, "val": 0xF, "field": "a", "text": "x"}, {"k": "SET", "mask": 0x3, "val": 0x0, "field": "b", "text": "y"}]
        merged = self.G.merge_sets([dict(s) for s in sets])
        self.assertEqual([(o["k"], o["mask"], o["val"], o["field"]) for o in merged], [("SET", 0xF, 0xC, "a+b")])
        self.assertEqual(len(self.G.merge_sets([sets[0], {"k": "STORE"}, sets[1]])), 3)      # a store in between: no merge

    def plan_with(self, edit):
        import tempfile as _tf
        with open(self.G.PLAN) as f:
            plan = json.load(f)
        edit({s["id"]: s for s in plan["steps"]}, plan)
        d = _tf.mkdtemp(prefix="plan-", dir=_TMP)
        path = os.path.join(d, "plan.json")
        with open(path, "w") as f:
            json.dump(plan, f)
        return path

    def problems(self, edit):
        saved = self.G.PLAN
        self.G.PLAN = self.plan_with(edit)
        try:
            spec = copy.deepcopy(self.spec)
            ops, bases, consts, fn = self.G.build(spec)
            return self.G.check_plan(spec, ops, fn)
        finally:
            self.G.PLAN = saved

    def test_the_plan_cross_check_passes_on_the_real_plan_and_names_what_is_wrong_otherwise(self):
        problems, covered = self.problems(lambda steps, plan: None)
        self.assertEqual(problems, [])
        self.assertIn("0.20", covered)
        self.assertIn("3.01", covered)

        def drop_step(steps, plan):
            plan["steps"] = [s for s in plan["steps"] if s["id"] != "1.02"]
        problems, _ = self.problems(drop_step)
        self.assertEqual(problems, ["L5: plan step 1.02 does not exist"])

        def change_statement(steps, plan):
            steps["3.01"]["source"]["text"] = "((EUSBPHY_REG_RST_CTRL_p) (&reg))->b.phy_reset_ovrd_en = 0;"
        problems, covered = self.problems(change_statement)
        self.assertEqual(len(problems), 1)
        self.assertIn("plan step 3.01: statement", problems[0])
        self.assertNotIn("3.01", covered)

        def change_row(steps, plan):
            steps["0.20"]["source"]["text"] = steps["0.20"]["source"]["text"].replace("(0x1 << 0), (0x1 << 0)", "(0x3 << 0), (0x3 << 0)")
        problems, covered = self.problems(change_row)
        self.assertEqual(problems, ["plan step 0.20: PMUCAL row HSI0_CONFIGURATION has no derived op"])

        def change_value(steps, plan):
            steps["0.20"]["source"]["text"] = steps["0.20"]["source"]["text"].replace("(0x1 << 0), (0x1 << 0)", "(0x1 << 0), (0x0 << 0)")
        problems, _ = self.problems(change_value)
        self.assertEqual(problems, ["plan step 0.20: PMUCAL row HSI0_CONFIGURATION has no derived op"])

        def read_becomes_write(steps, plan):      # a WRITE row of the plan is not satisfied by the ladder's read of the same register
            steps["0.19"]["source"]["text"] = steps["0.19"]["source"]["text"].replace("PMUCAL_READ", "PMUCAL_WRITE")
        problems, _ = self.problems(read_becomes_write)
        self.assertEqual(problems, ["plan step 0.19: PMUCAL row HSI0_STATUS has no derived op"])

        def write_becomes_read(steps, plan):      # and the ladder's write of CONFIG is not a READ row's op
            steps["0.20"]["source"]["text"] = steps["0.20"]["source"]["text"].replace("PMUCAL_WRITE", "PMUCAL_READ")
        problems, _ = self.problems(write_becomes_read)
        self.assertEqual(problems, [])         # the RD of PD_CONFIG at L1 is a read of that register: the row is covered, by the right kind

        def change_mask_only(steps, plan):
            steps["0.24"]["source"]["text"] = steps["0.24"]["source"]["text"].replace("(0x1 << 4), (0x0 << 4)", "(0x3 << 4), (0x0 << 4)")
        problems, _ = self.problems(change_mask_only)
        self.assertEqual(problems, ["plan step 0.24: PMUCAL row CLK_CON_MUX_CLK_HSI0_NOC has no derived op"])

        def unknown_type(steps, plan):
            steps["0.21"]["source"]["text"] = steps["0.21"]["source"]["text"].replace("PMUCAL_WAIT", "PMUCAL_DELAY")
        problems, _ = self.problems(unknown_type)
        self.assertEqual(problems, ["plan step 0.21: PMUCAL row HSI0_STATUS has type PMUCAL_DELAY, which the ladder does not model"])


    def test_a_plan_row_is_carried_by_an_op_of_its_own_kind(self):
        """The ladder reads and waits on HSI0_STATUS and reads and writes HSI0_CONFIGURATION: a row of the plan is not satisfied by the other
        kind of access to the same register."""
        def problems(drop):
            spec = copy.deepcopy(self.spec)
            ops, bases, consts, fn = self.G.build(spec)
            kept = [o for o in ops if not drop(o)]
            self.assertEqual(len(kept), len(ops) - 1)
            return self.G.check_plan(spec, kept, fn)[0]
        self.assertEqual(problems(lambda o: (o["k"], o.get("addr")) == ("RD", 0x12862004) and o["rung"] == 1),
                         ["plan step 0.19: PMUCAL row HSI0_STATUS has no derived op"])        # the WAIT of the same register is not the READ
        self.assertEqual(problems(lambda o: (o["k"], o.get("addr")) == ("WAIT", 0x12862004)),
                         ["plan step 0.21: PMUCAL row HSI0_STATUS has no derived op"])        # the RD is not the WAIT
        self.assertEqual(problems(lambda o: (o["k"], o.get("addr")) == ("WRM", 0x12862000)),
                         ["plan step 0.20: PMUCAL row HSI0_CONFIGURATION has no derived op"])  # the RD of CONFIG is not the WRITE

    def test_a_read_row_whose_mask_and_value_equal_the_waits_is_still_not_carried_by_the_wait(self):
        """With the value of the READ row of HSI0_STATUS edited to the one of the WAIT row of the same register (same address, same mask,
        same value) the only thing that tells the two ops apart is their kind: the WAIT must neither satisfy the READ row nor be annotated
        with its step."""
        def same_as_the_wait(steps, plan):
            steps["0.19"]["source"]["text"] = steps["0.19"]["source"]["text"].replace("(0x1 << 0), 0, 0, 0, 0xffffffff", "(0x1 << 0), (0x1 << 0), 0, 0, 0xffffffff")
            self.assertIn("(0x1 << 0), (0x1 << 0)", steps["0.19"]["source"]["text"])
        saved = self.G.PLAN
        self.G.PLAN = self.plan_with(same_as_the_wait)
        try:
            spec = copy.deepcopy(self.spec)
            ops, bases, consts, fn = self.G.build(spec)
            wait = [o for o in ops if (o["k"], o.get("addr")) == ("WAIT", 0x12862004)]
            self.assertEqual(len(wait), 1)
            problems, covered = self.G.check_plan(spec, ops, fn)
            self.assertEqual(problems, [])                                   # the RD of the register carries the row
            self.assertEqual(wait[0]["plan"], ["0.21"])                      # the WAIT carries only its own row
            kept = [o for o in ops if (o["k"], o.get("addr")) != ("RD", 0x12862004)]
            problems, _ = self.G.check_plan(spec, kept, fn)
            self.assertEqual(problems, ["plan step 0.19: PMUCAL row HSI0_STATUS has no derived op"])     # without the RD only the WAIT is left
        finally:
            self.G.PLAN = saved


# ------------------------------------------------------------------------------------------------------------------------ Ladder
class Ladder(unittest.TestCase):
    def check_run(self, pd_on, **kw):
        p = new(pd_on=pd_on)
        rc = p.run(stop=5, **kw)
        dev, err, st = ref(5, pd_on=pd_on, **kw)
        self.assertEqual(rc, 0)
        self.assertIsNone(err)
        self.assertEqual(p.log(), dev.log)
        self.assertEqual(p.violations(), [])
        self.assertEqual(dev.viol, [])
        s = p.state()
        self.assertEqual((s["err"], s["err_op"], s["rung_done"], s["pd_was_on"], s["soft"], s["gsnpsid"]),
                         (0, NOPS, 5, int(pd_on), st["soft"], D.NAT041_MODEL_ID))
        self.assertEqual(len(s["recs"]), st["nrec"])
        return p, s

    def test_domain_off_run_equals_the_reference_access_by_access(self):
        p, s = self.check_run(False)
        self.assertEqual(p.lib.plat_now(), 50 + sum(L5_DELAYS))      # the domain wait (50 us in the fixture) + the vendor delays, nothing else

    def test_domain_on_run_makes_no_l3_write_and_never_touches_the_pmu_config(self):
        p, s = self.check_run(True)
        log = p.log()
        self.assertNotIn(("W", 0x12862000), [(k, a) for k, a, v, t in log])
        written = {a for k, a, v, t in log if k == "W"}
        self.assertEqual({a for a in written if 0x17800000 <= a < 0x17900000 or 0x17910000 <= a < 0x18000000}, {a for a in written if 0x178A0000 <= a < 0x178C0000})
        self.assertIn(0x1286061C, written)                                     # the isolation release is the one PMU write of a domain-on run
        self.assertEqual({a for a in written if a < 0x17000000}, {0x1286061C})
        self.assertEqual(p.lib.plat_now(), sum(L5_DELAYS))

    def test_records_are_what_was_read_and_written(self):
        p, s = self.check_run(False)
        by_op = {}
        for op, v0, v1 in s["recs"]:
            by_op.setdefault(op, []).append((v0, v1))
        self.assertEqual(by_op[5], [(0, 1)])                          # WRM PMU config: read 0, read back 1
        self.assertEqual(by_op[32], [(0x1E00, 0x1E00)])               # STORE LINKCTRL: written, read back
        self.assertEqual(by_op[6], [(1, 50)])                         # WAIT: last value 1 after 50 us
        self.assertEqual(by_op[26], [(D.NAT041_MODEL_ID, 0)])
        self.assertEqual(by_op[29], [(0, 0)])                         # LOAD: the value read
        self.assertEqual(by_op[61], [(0x101FF0, 0)])                  # the second LOAD of LINKCTRL sees what the earlier stores left
        self.assertEqual(by_op[64], [(0x151FF0, 0)])                  # RDLOG
        self.assertNotIn(30, by_op)                                   # SET / DELAY / CONST do not touch hardware and leave no record
        self.assertNotIn(31, by_op)

    def test_the_domain_is_never_accessed_while_it_is_off(self):
        p = new(pd_on=False)
        p.run(stop=5)
        self.assertEqual(p.violations(), [])
        log = p.log()
        first_hsi0 = next(k for k, (kind, a, v, t) in enumerate(log) if 0x17800000 <= a < 0x17910000)
        status_on = next(k for k, (kind, a, v, t) in enumerate(log) if a == 0x12862004 and v == 1)
        self.assertLess(status_on, first_hsi0)

    def test_the_harness_gate_is_not_vacuous(self):
        import ctypes
        p = new(pd_on=False)
        p.lib.usbmon_rd32.argtypes = [ctypes.c_uint32]
        p.lib.usbmon_rd32(0x17801000)                                          # a declared CMU_HSI0 register, domain off
        p.lib.usbmon_rd32(0x17802010)                                          # an undeclared register of the block, domain off
        v = p.violations()
        self.assertEqual((len([x for x in v if "domain is off" in x]), len([x for x in v if "undeclared" in x])), (2, 1))
        q = new(pd_on=True)
        q.lib.usbmon_rd32.argtypes = [ctypes.c_uint32]
        q.lib.usbmon_rd32(0x17801000)
        self.assertEqual(q.violations(), [])

    def test_final_register_values(self):
        p, _ = self.check_run(False)
        want = {0x12862000: 1, 0x17801000: 0, 0x17801004: 0, 0x17801008: 0x10, 0x17801800: 1, 0x17800630: 0x10, 0x17800640: 0x10,
                0x17800800: 0xF1000000, 0x17820104: 0xFFFFFFFF, 0x178A0004: 0x151FF0, 0x178A000C: 0, 0x178A0010: 3, 0x178A0050: 0,
                0x178A0058: 0x01000000, 0x178A005C: 0xFF00, 0x178A0060: 1, 0x178A0054: 0x1111, 0x178A006C: 0x70007,
                0x178B0000: 0x02, 0x178B0004: 0x401, 0x178B0008: 0x17000, 0x178B000C: 0, 0x178B0014: 0, 0x178B0020: 0}
        for a, v in want.items():
            self.assertEqual(p.get(a), v, hex(a))
        self.assertEqual(p.get(0x1286061C), 1)                          # isolation: bit 0 set (vendor `on = 0 -> val = mask`)

    def test_a_stale_state_block_does_not_leak_into_a_run(self):
        p = new(pd_on=True)
        p.lib.n_poison_state()
        self.assertEqual(p.run(stop=3), 0)
        s = p.state()
        self.assertEqual((s["err"], s["rung_done"], s["soft"], s["gsnpsid"]), (0, 3, 0, 0))
        self.assertEqual(len(s["recs"]), 2 + 3 + 11)

    def test_stop_rungs(self):
        for stop, want_reads in ((0, 0), (1, 2), (2, 5)):
            p = new()
            self.assertEqual(p.run(stop=stop), 0)
            self.assertEqual((len(p.log()), p.state()["rung_done"]), (want_reads, stop), stop)
        p = new()
        self.assertEqual(p.run(stop=6), -(0 * 16 + 5))                          # beyond the last rung: configuration error, nothing touched
        self.assertEqual(p.log(), [])
        p = new(pd_on=True)
        self.assertEqual(p.run(stop=4), 0)
        self.assertEqual(p.state()["gsnpsid"], D.NAT041_MODEL_ID)
        self.assertEqual(p.log()[-1][:2], ("R", 0x1790C120))                  # L4 ends with the GSNPSID read and nothing after it

    def same_state(self, p, st):
        """The state block after a stop equals the reference's: records, completed rung, L1 result, soft count."""
        s = p.state()
        self.assertEqual((len(s["recs"]), s["rung_done"], s["soft"]), (st["nrec"], st["rung_done"], st["soft"]))
        if st["pd_was_on"] is not None:
            self.assertEqual(s["pd_was_on"], st["pd_was_on"])

    def test_power_on_not_allowed_stops_before_the_first_write(self):
        p = new(pd_on=False)
        rc = p.run(stop=5, allow_poweron=0)
        self.assertEqual((err_tuple(rc), p.state()["err_op"]), ((3, "state"), 5))
        self.assertEqual([e for e in p.log() if e[0] == "W"], [])
        dev, err, st = ref(5, allow_poweron=False)
        self.assertEqual((err, p.log()), ((3, "state", 5), dev.log))
        self.same_state(p, st)
        q = new(pd_on=True)
        self.assertEqual(q.run(stop=5, allow_poweron=0), 0)                   # the flag only matters when the domain is off

    def test_a_domain_that_never_comes_up_is_a_bounded_wait_then_a_stop(self):
        for bound, run_arg in ((100, 100), (200000, 0)):
            p = new(pd_on=False, follow=False)
            rc = p.run(stop=5, pd_wait_us=run_arg)
            self.assertEqual((err_tuple(rc), p.state()["err_op"]), ((3, "timeout"), 6), bound)
            self.assertEqual(p.lib.plat_now(), bound + 1)                     # polls at 0..bound, one microsecond each, then the stop
            writes = [(a, v) for k, a, v, t in p.log() if k == "W"]
            self.assertEqual(writes, [(0x12862000, 1)])                       # the config write and nothing in the domain
            self.assertEqual(p.violations(), [])
            dev, err, st = ref(5, follow=False, pd_wait_us=run_arg)
            self.assertEqual((err, p.log()), ((3, "timeout", 6), dev.log))
            self.same_state(p, st)
            self.assertEqual(p.state()["recs"][-1], (6, 0, bound + 1))      # the failed wait is recorded: op 6, last value 0, bound + 1 us

    def test_every_written_address_stops_the_ladder_at_its_first_failed_readback(self):
        base = new(pd_on=False)
        base.run(stop=5)
        base_seq = [(k, a) for k, a, v, t in base.log()]
        targets = sorted({o["addr"] for o in TABLE if o["kind"] in WRITE_KINDS})
        self.assertGreaterEqual(len(targets), 20)
        for a in targets:
            writers = [o for o in TABLE if o["kind"] in WRITE_KINDS and o["addr"] == a and not o["flags"] & D.F_SOFT]
            p = new(pd_on=False)
            p.lib.plat_flip(a, 0xFFFFFFFF)
            rc = p.run(stop=5)
            if not writers:                                                   # only soft stores: recorded, not fatal
                n_soft = len([o for o in TABLE if o["kind"] == "STORE" and o["addr"] == a])
                self.assertEqual((rc, p.state()["soft"]), (0, n_soft), hex(a))
                continue
            first = writers[0]
            self.assertEqual((err_tuple(rc), p.state()["err_op"]), ((first["rung"], "readback"), first["i"]), hex(a))
            seq = [(k, x) for k, x, v, t in p.log()]
            self.assertEqual(seq, base_seq[:len(seq)], hex(a))                # nothing happened that the good run does not do in the same order
            self.assertEqual(p.log()[-1][:2], ("R", a), hex(a))              # the stop is at the readback: nothing after it touched the hardware
            self.assertLess(len(seq), len(base_seq))
            dev, err, st = ref(5, flip={a: 0xFFFFFFFF})
            self.assertEqual(p.log(), dev.log, hex(a))
            self.same_state(p, st)

    def test_a_partial_readback_error_is_caught_on_the_touched_bits_only(self):
        # WRM: a flipped bit outside the mask is not a failure; inside it is
        p = new(pd_on=False)
        p.lib.plat_flip(0x17801000, 0x1)            # CLK_CON_MUX_CLK_HSI0_NOC: mask 0x10
        self.assertEqual(p.run(stop=5), 0)
        p = new(pd_on=False)
        p.lib.plat_flip(0x17801000, 0x10)
        self.assertEqual(err_tuple(p.run(stop=5)), (3, "readback"))
        # STORE: only the bits the vendor code changed are compared. EUSBCON_RST_CTRL op 70 stores 0x33 with mask 0x33 touched
        p = new(pd_on=False)
        p.lib.plat_flip(0x178B0000, 0x100)
        self.assertEqual(p.run(stop=5), 0)

    def test_a_store_compares_exactly_the_bits_the_sets_since_its_load_touched(self):
        # LINKCTRL (0x178A0004) reads, in order: op 29 LOAD (#1), op 32 read-back (#2), op 35 read-back (#3), op 61 LOAD (#4), op 63 read-back (#5)
        # The store at op 35 follows two SETs after one LOAD: it compares the union of both masks (0x1F00 from op 30 included).
        p = new(pd_on=True)
        p.lib.plat_flip_from(0x178A0004, 0x1E00, 3)
        self.assertEqual((err_tuple(p.run(stop=5)), p.state()["err_op"]), ((5, "readback"), 35))
        # The store at op 63 follows a fresh LOAD: bits touched by the earlier SETs (0x10 is in op 34's mask) are not compared any more.
        p = new(pd_on=True)
        p.lib.plat_flip_from(0x178A0004, 0x10, 5)
        self.assertEqual(p.run(stop=5), 0)
        # ... and the bits of its own SET (0x10000 is in op 62's mask) are
        p = new(pd_on=True)
        p.lib.plat_flip_from(0x178A0004, 0x10000, 5)
        self.assertEqual((err_tuple(p.run(stop=5)), p.state()["err_op"]), ((5, "readback"), 63))

    def test_a_constant_store_compares_the_whole_word(self):
        # HSREWA_REFTO (0x178A005C) is stored from a CONST (0xFF00): any bit counts, not only the bits of the constant; the store is soft
        p = new(pd_on=True)
        p.lib.plat_flip(0x178A005C, 0x1)
        self.assertEqual((p.run(stop=5), p.state()["soft"]), (0, 1))

    def test_pd_was_on_comes_from_the_status_word_under_the_mask(self):
        for cfg_word, status, want in ((1, 0, 0), (0, 1, 1), (0, 0x3, 1), (0, 0x2, 0), (0, 0, 0)):
            p = new(pd_on=False, follow=False)
            p.declare(PMU_CFG_ADDR, cfg_word)
            p.declare(PMU_STATUS_ADDR, status)
            self.assertEqual(p.run(stop=1), 0)
            self.assertEqual(p.state()["pd_was_on"], want, (cfg_word, status))

    def test_l3_refuses_to_write_when_l1_never_learned_the_domain_state(self):
        p = table_variant(lambda t: t.replace("{ LK_RD, 1, 0, 0x12862004u", "{ LK_RD, 1, 0, 0x12862008u"), "nostatus")
        p.standard_fixture(pd_on=False, strict=False)
        rc = p.run(stop=5)
        self.assertEqual((err_tuple(rc), p.state()["err_op"], p.state()["pd_was_on"], p.state()["rung_done"]), ((3, "state"), 5, 0xFF, 2))
        self.assertEqual([e for e in p.log() if e[0] == "W"], [])

    def test_the_domain_wait_compares_under_its_mask(self):
        # HSI0_STATUS carries other bits: the wait is for (status & 1) == 1, not for the whole word to equal 1
        p = new(pd_on=False)
        p.declare(PMU_STATUS_ADDR, 0x2)
        self.assertEqual(p.run(stop=5), 0)
        self.assertEqual(p.get(PMU_STATUS_ADDR), 0x3)
        self.assertEqual(p.lib.plat_now(), 50 + sum(L5_DELAYS))

    def test_an_op_kind_the_interpreter_does_not_know_is_a_cfg_stop(self):
        p = table_variant(lambda t: t.replace("{ LK_WRP, 3, LAD_F_CMUINIT, 0x17820104u", "{ 11, 3, LAD_F_CMUINIT, 0x17820104u"), "unknownkind")
        p.standard_fixture(pd_on=False)
        rc = p.run(stop=5)
        self.assertEqual((err_tuple(rc), p.state()["err_op"], p.state()["rung_done"]), ((3, "cfg"), 14, 2))

    def test_a_null_cfg_is_a_cfg_error(self):
        p = new()
        self.assertEqual(p.lib.n_run_null(), -(0 * 16 + 5))
        self.assertEqual((p.log(), p.state()["err_op"]), ([], NOPS))

    def test_the_liveness_word_of_usbcon_stops_before_any_l5_write(self):
        for word in (0x0, 0xFFFFFFFF):
            p = new(pd_on=True)
            p.lib.plat_def(0x178A0000, word)
            rc = p.run(stop=5)
            self.assertEqual((err_tuple(rc), p.state()["err_op"]), ((5, "notalive"), 27), hex(word))
            self.assertEqual([e for e in p.log() if e[0] == "W"], [])
            self.assertEqual(p.log()[-1][:2], ("R", 0x178A0000))
        p = new(pd_on=True)
        p.lib.plat_def(0x178A0000, 0x1)
        self.assertEqual(p.run(stop=5), 0)

    def test_dwc3_ids(self):
        for ident, ok in ((0x5533330A, True), (0x55330000, True), (0x3331312A, True), (0x33310000, True), (0x5534330A, False), (0x3330312A, False),
                          (0x0, False), (0xFFFFFFFF, False), (0x5533, False)):         # 0x5533 alone: the id must be in the UPPER half
            p = new(pd_on=True)
            p.lib.model_set_id(ident)
            rc = p.run(stop=5)
            if ok:
                self.assertEqual((rc, p.state()["gsnpsid"]), (0, ident), hex(ident))
            else:
                self.assertEqual((err_tuple(rc), p.state()["err_op"], p.state()["rung_done"]), ((4, "notalive"), 26, 3), hex(ident))
                self.assertEqual([e for e in p.log() if e[0] == "W"], [])      # L5 never started

    def test_foreign_id_is_decided_by_the_upper_half_not_the_whole_word(self):
        # the model's low half is a revision: it must not matter
        for low in (0x0000, 0x330A, 0xFFFF):
            p = new(pd_on=True)
            p.lib.model_set_id(0x55330000 | low)
            self.assertEqual(p.run(stop=4), 0)

    def test_the_run_leaves_the_l1_result_unset_when_l1_did_not_run(self):
        p = new(pd_on=False)
        self.assertEqual(p.run(stop=0), 0)
        self.assertEqual((p.state()["pd_was_on"], p.state()["rung_done"], p.state()["err_op"]), (0xFF, 0, NOPS))
        p = new(pd_on=True)
        p.run(stop=1)
        self.assertEqual(p.state()["pd_was_on"], 1)

    def test_selfcheck_rejects_a_table_that_breaks_the_rung_contract(self):
        cases = {
            "a write in a read-only rung (L2)": lambda t: t.replace("{ LK_RD, 2, 0, 0x22b210c8u", "{ LK_WRP, 2, 0, 0x22b210c8u"),
            "a write in L1": lambda t: t.replace("{ LK_RD, 1, 0, 0x12862000u", "{ LK_WRP, 1, 0, 0x12862000u"),
            "a write in L4": lambda t: t.replace("{ LK_RD, 4, LAD_F_DWC3ID, 0x1790c120u", "{ LK_WRP, 4, LAD_F_DWC3ID, 0x1790c120u"),
            "an op of the last rung in the wrong rung": lambda t: t.replace("{ LK_RD, 5, 0, 0x178a0004u", "{ LK_RD, 4, 0, 0x178a0004u"),
            "an op in the wrong rung": lambda t: t.replace("{ LK_RD, 2, 0, 0x22b220c4u", "{ LK_RD, 3, 0, 0x22b220c4u"),
            "rung 1 not at index 0": lambda t: t.replace("{ 0, 0, 2, 5, 26, 27, 111 }", "{ 0, 1, 2, 5, 26, 27, 111 }"),
            "last rung end not at the table end": lambda t: t.replace("{ 0, 0, 2, 5, 26, 27, 111 }", "{ 0, 0, 2, 5, 26, 27, 110 }"),
            "non-monotonic rung starts": lambda t: t.replace("{ 0, 0, 2, 5, 26, 27, 111 }", "{ 0, 0, 2, 6, 5, 27, 111 }"),
        }
        for name, tr in cases.items():
            p = table_variant(tr, "selfcheck")
            self.assertEqual(p.lib.n_selfcheck(), -(0 * 16 + 5), name)
            p.standard_fixture(pd_on=True)
            self.assertEqual(p.run(stop=5), -(0 * 16 + 5), name)                       # lad_run refuses it ...
            self.assertEqual(p.state()["err_op"], NOPS, name)                          # ... as a table error, not at an op
            self.assertEqual(p.log(), [], name)                                       # ... before the first access

    def test_a_bad_cfg_is_refused_without_touching_hardware(self):
        p = new()
        self.assertEqual(p.lib.n_run(6, 1, 0), -(0 * 16 + 5))
        self.assertEqual(p.log(), [])
        self.assertEqual(p.state()["err_op"], NOPS)

    def test_error_codes_match_the_header(self):
        h = slurp(os.path.join(SRC, "ladder.h"))
        codes = {m.group(1): int(m.group(2)) for m in re.finditer(r"#define (LAD_E_\w+)\s+(\d+)", h)}
        self.assertEqual(codes, {"LAD_E_READBACK": 1, "LAD_E_TIMEOUT": 2, "LAD_E_STATE": 3, "LAD_E_NOTALIVE": 4, "LAD_E_CFG": 5, "LAD_E_DISABLED": 6})
        self.assertEqual(H.LAD_ERR_NAMES, {1: "readback", 2: "timeout", 3: "state", 4: "notalive", 5: "cfg", 6: "disabled"})
        self.assertIn("#define LAD_ERR(rung, code)\t(-((int)(rung) * 16 + (int)(code)))", h)

    def test_every_soft_store_is_a_vendor_write_the_plan_does_not_list(self):
        d, _ = H.ops_json()
        soft = [o["i"] for o in TABLE if o["flags"] & D.F_SOFT]
        self.assertEqual(soft, [o["i"] for o in d["ops_not_in_the_plan"] if o["kind"] == "STORE"])
        # a soft mismatch is not silent: it is counted in the state
        p = new(pd_on=True)
        p.lib.plat_flip(0x178A0058, 0xFFFFFFFF)
        self.assertEqual(p.run(stop=5), 0)
        self.assertEqual(p.state()["soft"], 1)


# ------------------------------------------------------------------------------------------------------------------------ Default build
class DefaultBuild(unittest.TestCase):
    def test_defaults(self):
        w, d = H.Plat(lib(True)), H.Plat(lib(False))
        self.assertEqual((d.lib.n_default_stop(), d.lib.n_default_poweron()), (2, 1))
        self.assertEqual((w.lib.n_default_stop(), w.lib.n_default_poweron()), (5, 1))

    def test_default_run_reads_only_and_takes_no_time(self):
        for pd_on in (False, True):
            p = new(writing=False, pd_on=pd_on)
            self.assertEqual(p.run(), 0)
            self.assertEqual([k for k, a, v, t in p.log()], ["R"] * 5)
            self.assertEqual(p.lib.plat_now(), 0)
            self.assertEqual(p.state()["rung_done"], 2)
            self.assertEqual(p.state()["pd_was_on"], int(pd_on))
            self.assertEqual(p.violations(), [])

    def test_every_rung_that_writes_is_refused_before_the_first_access_of_that_rung(self):
        for stop in (3, 4, 5):
            for pd_on in (False, True):
                p = new(writing=False, pd_on=pd_on)
                rc = p.run(stop=stop)
                self.assertEqual((err_tuple(rc), p.state()["err_op"], p.state()["rung_done"]), ((3, "disabled"), NOPS, 2), (stop, pd_on))
                self.assertEqual(p.log(), ref(2, writing=False, pd_on=pd_on)[0].log)
                self.assertEqual(p.lib.plat_now(), 0)
                self.assertEqual(p.get(0x12862000), int(pd_on))              # the PMU config word is untouched

    def test_the_default_build_does_not_include_the_write_path(self):
        text = slurp(os.path.join(SRC, "ladder.c"))
        m = re.search(r"#ifdef LAD_WRITING_RUNGS\nstatic int lad_exec_write.*?#endif /\* LAD_WRITING_RUNGS \*/", text, re.S)
        self.assertIsNotNone(m)
        rest = re.sub(r"/\*.*?\*/|//[^\n]*", "", text.replace(m.group(0), ""), flags=re.S)
        self.assertEqual(len(re.findall(r"usbmon_wr32|usbmon_delay_us", rest)), 0)


# ------------------------------------------------------------------------------------------------------------------------ L6-L8
class Usb(unittest.TestCase):
    BOOT = b"BOOTID-0123456789"[:16]

    def test_usbmon_init_runs_after_the_last_rung_and_the_engine_comes_up(self):
        p = new(writing=True, pd_on=False)
        self.assertEqual(p.run(stop=5), 0)
        ladder_accesses = len(p.log())
        p.lib.n_usb_new(4096)
        self.assertEqual(p.lib.n_usb_start(self.BOOT, 4096), 0)
        log = p.log()
        self.assertGreater(len(log), ladder_accesses)
        self.assertTrue(all(0x17900000 <= a < 0x17910000 for k, a, v, t in log[ladder_accesses:]))   # everything after the ladder is DWC3
        self.assertEqual(log[ladder_accesses][:2], ("R", 0x1790C120))                              # usbmon_init starts by checking GSNPSID again
        self.assertEqual(p.violations(), [])

    def test_l7_connect_and_l8_nonce(self):
        import ctypes
        p = new(writing=True, pd_on=False)
        self.assertEqual(p.run(stop=5), 0)
        p.lib.n_usb_new(4096)
        self.assertEqual(p.lib.n_usb_start(self.BOOT, 4096), 0)
        # nobody on the bus: L7 stops with its own code
        self.assertEqual(p.lib.n_usb_wait(7, 1 << 3, 5, 10), -(7 * 16 + 2))
        p.lib.model_attach()
        p.lib.model_bus_reset(1)
        self.assertEqual(p.lib.n_usb_wait(7, 1 << 3, 50, 10), 0)
        self.assertTrue(p.lib.n_usb_flags() & (1 << 3))
        # L8: the host has not sent the nonce
        self.assertEqual(p.lib.n_usb_wait(8, 1 << 0, 5, 10), -(8 * 16 + 2))
        nonce = bytes(range(0xA0, 0xB0))
        buf, got = (ctypes.c_uint8 * 64)(), ctypes.c_int(0)
        self.assertEqual(p.lib.model_ctrl(0x40, 0x04, 0, 0, 16, nonce, buf, ctypes.byref(got)), 0)
        self.assertEqual(p.lib.n_usb_wait(8, 1 << 0, 5, 10), 0)
        self.assertEqual(p.violations(), [])

    def test_the_waits_poll_the_engine_a_bounded_number_of_times_with_the_requested_pause(self):
        p = new(writing=True, pd_on=False)
        self.assertEqual(p.run(stop=5), 0)
        p.lib.n_usb_new(4096)
        self.assertEqual(p.lib.n_usb_start(self.BOOT, 4096), 0)
        t0, n0 = p.lib.plat_now(), len(p.log())
        self.assertEqual(p.lib.n_usb_wait(7, 1 << 3, 5, 10), -(7 * 16 + 2))
        self.assertEqual(p.lib.plat_now() - t0, 5 * 10)                                # five polls, ten microseconds after each
        polls_5 = len(p.log()) - n0
        n1 = len(p.log())
        t_before = p.lib.plat_now()
        self.assertEqual(p.lib.n_usb_wait(7, 1 << 3, 10, 0), -(7 * 16 + 2))
        polls_10 = len(p.log()) - n1
        self.assertEqual(p.lib.plat_now(), t_before)                                   # no pause requested: no time spent
        self.assertEqual((polls_5, polls_10), (5, 10))                                 # one GEVNTCOUNT read per poll: exactly max_polls polls
        t1 = p.lib.plat_now()
        self.assertEqual(t1 - t0, 5 * 10)                                              # (the zero-pause wait below must add nothing to it)
        self.assertEqual(p.lib.n_usb_wait(7, 1 << 3, 0, 10), -(7 * 16 + 2))             # zero polls: a timeout without touching the engine
        self.assertEqual(len(p.log()), n1 + polls_10)
        self.assertEqual(p.lib.plat_now(), t1)

    def test_a_wait_polls_the_engine_itself(self):
        """With the model's host steps not polling the engine, the CONNECT_DONE event stays pending until lad_usb_wait polls."""
        p = new(writing=True, pd_on=False)
        self.assertEqual(p.run(stop=5), 0)
        p.lib.n_usb_new(4096)
        self.assertEqual(p.lib.n_usb_start(self.BOOT, 4096), 0)
        p.lib.model_set_host(0, 40)
        try:
            p.lib.model_attach()
            self.assertGreater(p.lib.model_events_pending(), 0)
            self.assertFalse(p.lib.n_usb_flags() & (1 << 3))
            self.assertEqual(p.lib.n_usb_wait(7, 1 << 3, 5, 10), 0)
            self.assertTrue(p.lib.n_usb_flags() & (1 << 3))
            self.assertEqual(p.lib.model_events_pending(), 0)
        finally:
            p.lib.model_set_host(2, 40)

    def test_a_core_that_stops_answering_between_l4_and_l6_is_an_l6_stop(self):
        p = new(writing=True, pd_on=False)
        self.assertEqual(p.run(stop=5), 0)
        p.lib.n_usb_new(4096)
        p.lib.model_set_id(0x12345678)
        self.assertEqual(p.lib.n_usb_start(self.BOOT, 4096), -(6 * 16 + 4))

    def start_with(self, inject, ring=4096):
        p = new(writing=True, pd_on=False)
        self.assertEqual(p.run(stop=5), 0)
        p.lib.n_usb_new(4096)
        inject(p)
        return p, p.lib.n_usb_start(self.BOOT, ring)

    def test_usbmon_init_failures_are_l6_stops_with_the_ladder_codes(self):
        cases = {
            "core id": (lambda p: p.lib.model_set_id(0x12345678), (6, "notalive")),
            "soft reset never completes": (lambda p: p.lib.model_set_sr_latency(100000), (6, "timeout")),
            "core never leaves halt": (lambda p: p.lib.plat_dwc3_overlay(0xC70C, 1 << 22, 1 << 22), (6, "timeout")),
            "endpoint command never completes": (lambda p: p.lib.model_set_cmd_latency(100000), (6, "readback")),
            "endpoint command fails": (lambda p: p.lib.model_fail_next_cmd(2), (6, "readback")),
        }
        for name, (inject, want) in cases.items():
            p, rc = self.start_with(inject)
            self.assertEqual(err_tuple(rc), want, name)
        p, rc = self.start_with(lambda p: None, ring=16)                                  # a ring too small for the engine: its argument check
        self.assertEqual(err_tuple(rc), (6, "cfg"))
        p, rc = self.start_with(lambda p: None)
        self.assertEqual(rc, 0)

    def test_a_wait_on_a_rung_that_is_not_a_wait_is_a_cfg_error(self):
        p = new(writing=True, pd_on=True)
        p.run(stop=5)
        p.lib.n_usb_new(4096)
        p.lib.n_usb_start(self.BOOT, 4096)
        self.assertEqual(p.lib.n_usb_wait(5, 1, 3, 1), -(5 * 16 + 5))


# ------------------------------------------------------------------------------------------------------------------------ Aarch64
@unittest.skipUnless(HAVE_SIM and subprocess.run(["which", "zig"], capture_output=True).returncode == 0, "unicorn, capstone or zig is missing")
class Aarch64(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import a64sim
        cls.S = a64sim
        cls.elf = {w: a64sim.Elf(a64sim.build_elf(_TMP, writing=w)) for w in (False, True)}

    def sim(self, writing, dev):
        return self.S.A64(self.elf[writing], dev, list(dev.regs))

    def test_state_size_matches_the_compiler(self):
        self.assertEqual(H.Plat(lib(True)).lib.n_sizeof_state(), self.S.STATE_SIZE)

    def test_no_undefined_symbol_the_objects_need_no_libc_or_runtime(self):
        for w in (False, True):
            path = os.path.join(_TMP, "ladder-%s.elf" % ("w" if w else "d"))
            self.assertEqual(subprocess.run(["nm", "-u", path], capture_output=True, text=True).stdout.strip(), "")

    def test_default_cfg(self):
        for w, want in ((False, (2, 1, 0)), (True, (5, 1, 0))):
            dev = D.DevModel(TABLE)
            self.assertEqual(self.sim(w, dev).default_cfg(), want)

    def disasm(self, w):
        out = []
        cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        for addr, code in self.elf[w].text():
            seq = list(cs.disasm(code, addr))
            self.assertEqual(len(seq) * 4, len(code), "the text did not decode completely")
            out += [(i.mnemonic, i.op_str) for i in seq]
        return out

    def test_the_default_object_has_no_barrier_store_no_counter_read(self):
        d, w = self.disasm(False), self.disasm(True)
        for banned in ("dsb", "dmb", "isb"):
            self.assertEqual([i for i in d if i[0] == banned], [], banned)
        self.assertEqual([i for i in d if i[0] == "mrs"], [])
        self.assertTrue([i for i in w if i[0] == "dsb"], "the writing object must contain the port's dsb (otherwise the check above is vacuous)")
        self.assertTrue([i for i in w if i[0] == "mrs" and "cntpct" in i[1]])

    def test_the_default_object_never_writes_to_a_device_window(self):
        for pd_on in (False, True):
            dev = D.DevModel(TABLE, pd_on=pd_on)
            sim = self.sim(False, dev)
            rc, st = sim.run(5)
            self.assertEqual(err_tuple(rc), (3, "disabled"))
            self.assertEqual((sim.stores_to_devices, [e for e in dev.log if e[0] == "W"]), (0, []))
            self.assertEqual(dev.t, 0)

    def check_equal(self, writing, stop, **kw):
        pd_on = kw.pop("pd_on", False)
        follow = kw.pop("follow", True)
        flip = kw.pop("flip", None)
        dev = D.DevModel(TABLE, pd_on=pd_on, follow=follow)
        dev.flip = dict(flip or {})
        sim = self.sim(writing, dev)
        rc, st = sim.run(stop, **kw)
        # in unicorn every read of the counter costs one microsecond, so a delay of N microseconds takes N + 1 (documented in a64sim.py)
        rdev, err, rst = ref(stop, writing=writing, pd_on=pd_on, follow=follow, flip=flip, delay_cost=lambda us: us + 1,
                             **{k: v for k, v in kw.items() if k in ("allow_poweron", "pd_wait_us")})
        self.assertEqual(dev.log, rdev.log)
        self.assertEqual(dev.viol, [])
        want = (0, "ok") if err is None else (err[0], err[1])
        self.assertEqual(H.decode_err(rc), want)
        self.assertEqual((st["rung_done"], st["soft"], st["nrec"]), (rst["rung_done"], rst["soft"], rst["nrec"]))
        if err:
            self.assertEqual(st["err_op"], err[2])
        return dev, rc, st

    def test_the_full_run_equals_the_reference(self):
        for pd_on in (False, True):
            dev, rc, st = self.check_equal(True, 5, pd_on=pd_on)
            self.assertEqual((rc, st["rung_done"], st["pd_was_on"], st["gsnpsid"]), (0, 5, int(pd_on), D.NAT041_MODEL_ID))
        dev, rc, st = self.check_equal(True, 5, pd_on=False)
        self.assertGreaterEqual(dev.t, 50 + sum(L5_DELAYS))                       # no delay is shorter than the vendor's

    def test_the_read_only_stop_equals_the_reference_in_both_objects(self):
        for w in (False, True):
            for pd_on in (False, True):
                self.check_equal(w, 2, pd_on=pd_on)

    def test_failures_equal_the_reference(self):
        self.check_equal(True, 5, allow_poweron=0)
        self.check_equal(True, 5, follow=False, pd_wait_us=64)
        self.check_equal(True, 5, flip={0x17800800: 0xFFFFFFFF})
        self.check_equal(True, 5, flip={0x178B0004: 0xFFFFFFFF})
        self.check_equal(True, 5, flip={0x178A0058: 0xFFFFFFFF})           # soft
        for a in sorted({o["addr"] for o in TABLE if o["kind"] in WRITE_KINDS})[::3]:
            self.check_equal(True, 5, flip={a: 0xFFFFFFFF})


if __name__ == "__main__":
    unittest.main(verbosity=1)
