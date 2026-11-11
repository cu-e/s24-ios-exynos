#!/usr/bin/env python3
"""NAT-045: derive the USB bring-up ladder tables from the pinned vendor sources.

Reads `ladder_spec.json` (selection data: which vendor function/array, which base) and the vendor files at the pinned SHA
(`git -C references/s24-linux show <pin>:<path>`), and writes

  src/ladder_regs.h     the op tables compiled into the loader code (generated; `--check` compares it with the file)
  ladder_ops.json       every op with its rung, label, vendor source text and the NAT-040 plan step it covers

Nothing numeric about a register sequence is typed in the spec except the base addresses (each carries its vendor text, which
is verified here). Offsets, masks, values, bit positions, delays and the order of the sequence come from the vendor text.

The vendor function bodies are parsed by a small statement compiler that accepts only the shapes these bodies use:

    reg = readl(BASE + NAME);               -> LOAD   (reg := read; the written-bits mask restarts)
    ((T_p)(&reg))->b.FIELD = N;             -> SET    (field of the layout of T_p, LSB-first as the compiler lays out the unions)
    reg = N;                                -> CONST
    writel(reg, BASE + NAME);               -> STORE  (write reg; the driver reads back the bits written since the LOAD)
    udelay(N | VAR);                        -> DELAY
    pr_info(..., readl(BASE + NAME));       -> RDLOG  (the vendor reads the register for a log line; recorded, not compared)
    if (COND) / { / }                       -> only COND listed in the spec as true; anything else stops the derivation

Any other statement stops the derivation with its text: a silent skip would be a hole in the ladder.

Usage:  derive.py --write        regenerate the two files
        derive.py --check        exit 1 if they differ from what the pinned sources give
"""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VENDOR_REPO = ROOT / "references" / "s24-linux"
SPEC = HERE / "ladder_spec.json"
PLAN = ROOT / "docs" / "procedures" / "nat-040" / "plan.json"
OUT_H = HERE / "src" / "ladder_regs.h"
OUT_JSON = HERE / "ladder_ops.json"

LK = ["RD", "WRP", "WRM", "WAIT", "LOAD", "SET", "CONST", "STORE", "RDLOG", "DELAY"]


class DeriveError(Exception):
    pass


# --------------------------------------------------------------------------------------------- vendor access
_cache = {}


def vendor(pin, path):
    key = (pin, path)
    if key not in _cache:
        r = subprocess.run(["git", "-C", str(VENDOR_REPO), "show", f"{pin}:{path}"], capture_output=True, text=True)
        if r.returncode:
            raise DeriveError(f"git show {pin}:{path} failed: {r.stderr.strip()}")
        _cache[key] = r.stdout
    return _cache[key]


def check_pin(pin):
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise DeriveError("pin is not a full SHA")
    r = subprocess.run(["git", "-C", str(VENDOR_REPO), "rev-parse", f"{pin}^{{commit}}"], capture_output=True, text=True)
    if r.returncode or r.stdout.strip() != pin:
        raise DeriveError("pin does not resolve to itself in references/s24-linux")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def cint(expr):
    """Evaluate a C integer constant expression made of literals, <<, >>, |, &, +, -, ~ (32-bit)."""
    e = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", expr.strip())
    tree = ast.parse(e, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return n.value
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Invert):
            return ~ev(n.operand)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            ops = {ast.LShift: lambda: a << b, ast.RShift: lambda: a >> b, ast.BitOr: lambda: a | b,
                   ast.BitAnd: lambda: a & b, ast.Add: lambda: a + b, ast.Sub: lambda: a - b}
            if type(n.op) not in ops:
                raise DeriveError(f"operator in {expr!r}")
            return ops[type(n.op)]()
        raise DeriveError(f"not a constant expression: {expr!r}")

    return ev(tree) & 0xFFFFFFFF


def split_args(s):
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return out


def match_paren(s, i):
    """s[i] == '(' -> index just after the matching ')'."""
    depth, q = 0, None
    for j in range(i, len(s)):
        ch = s[j]
        if q:
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j + 1
    raise DeriveError("unbalanced parenthesis")


# --------------------------------------------------------------------------------------------- PMUCAL arrays
def parse_pmucal_row(line):
    m = re.search(r"PMUCAL_SEQ_DESC\(", line)
    if not m:
        raise DeriveError(f"not a PMUCAL_SEQ_DESC row: {line!r}")
    end = match_paren(line, m.end() - 1)
    a = split_args(line[m.end():end - 1])
    if len(a) != 10:
        raise DeriveError(f"PMUCAL_SEQ_DESC with {len(a)} arguments: {line!r}")
    row = {"type": a[0], "name": a[1].strip('"'), "base": cint(a[2]), "offset": cint(a[3]), "mask": cint(a[4]),
           "value": cint(a[5]), "cond_base": cint(a[6]), "cond_offset": cint(a[7]), "cond_mask": cint(a[8]),
           "cond_value": cint(a[9]), "text": norm(line[m.start():end])}
    return row


def used(row):
    """A row the ladder uses must be unconditional: a conditional row would need the condition modelled."""
    if row["cond_base"] or row["cond_offset"]:
        raise DeriveError(f"conditional PMUCAL row is not modelled: {row['name']}")
    return row


def pmucal_arrays(text):
    arrays = {}
    for m in re.finditer(r"struct pmucal_seq (\w+)\[\]\s*=\s*\{(.*?)\n\};", text, re.S):
        rows = [parse_pmucal_row(l) for l in m.group(2).splitlines() if "PMUCAL_SEQ_DESC" in l]
        arrays[m.group(1)] = rows
    return arrays


def sfr_table(text):
    return {m.group(1): (cint(m.group(2)), m.group(3)) for m in
            re.finditer(r"^\s*SFR\((\w+),\s*(0x[0-9a-fA-F]+),\s*(\w+)\)", text, re.M)}


# --------------------------------------------------------------------------------------------- C headers
def strip_comments(s):
    out, i, n = [], 0, len(s)
    while i < n:
        if s.startswith("/*", i):
            j = s.find("*/", i + 2)
            if j < 0:
                raise DeriveError("unterminated comment")
            i = j + 2
            out.append(" ")
        elif s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
        elif s[i] == '"':
            j = i + 1
            while s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            out.append(s[i:j + 1])
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def header_defines(text):
    d = {}
    for m in re.finditer(r"^\s*#define\s+(\w+)\s+(\(?0[xX][0-9a-fA-F]+\)?|\d+)\s*(?:/[/*].*)?$", text, re.M):
        d[m.group(1)] = cint(m.group(2))
    return d


def header_layouts(text):
    """typedef union { u32 data; struct { unsigned a:n; ... } b; } X_o, *Y_p;  ->  {Y_p: {field: (lsb, width)}}"""
    t = strip_comments(text)
    out = {}
    for m in re.finditer(r"typedef\s+union\s*\{\s*u32\s+data\s*;\s*struct\s*\{(.*?)\}\s*b\s*;\s*\}\s*(\w+)\s*,\s*\*\s*(\w+)\s*;", t, re.S):
        fields, pos = {}, 0
        for f in m.group(1).split(";"):
            f = f.strip()
            if not f:
                continue
            fm = re.fullmatch(r"unsigned\s+(\w+)\s*:\s*(\d+)", f)
            if not fm:
                raise DeriveError(f"bitfield line in {m.group(3)}: {f!r}")
            w = int(fm.group(2))
            fields[fm.group(1)] = (pos, w)
            pos += w
        if pos > 32:
            raise DeriveError(f"layout {m.group(3)} covers {pos} bits")
        out[m.group(3)] = fields
    return out


# --------------------------------------------------------------------------------------------- function bodies
def function_body(text, name):
    m = re.search(rf"^[A-Za-z_][\w \*]*\b{name}\s*\([^;{{]*\)\s*\n?\{{", text, re.M)
    if not m:
        raise DeriveError(f"function {name} not found")
    i = m.end()
    depth, j = 1, i
    while depth:
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        j += 1
    return text[i:j - 1]


def statements(body):
    """Split a comment-free body into statements; braces end a statement and are dropped; `if (...)` heads are returned
    as ('if', cond) pseudo statements."""
    out, cur, depth, q = [], [], 0, None
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if q:
            cur.append(ch)
            if ch == "\\":
                cur.append(body[i + 1])
                i += 1
            elif ch == q:
                q = None
            i += 1
            continue
        if ch == '"':
            q = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif depth == 0 and ch in ";{}":
            s = norm("".join(cur))
            cur = []
            if s:
                out.append(s)
        else:
            cur.append(ch)
        i += 1
    s = norm("".join(cur))
    if s:
        out.append(s)
    # split `if (cond) stmt` into the head and the statement
    res = []
    for s in out:
        while True:
            m = re.match(r"(else\s+)?if\s*\(", s)
            if not m:
                break
            if m.group(1):
                raise DeriveError(f"else branch is not modelled: {s!r}")
            e = match_paren(s, m.end() - 1)
            res.append(("if", norm(s[m.end():e - 1])))
            s = s[e:].strip()
        if s:
            res.append(("st", s))
    return res


class Part:
    """Compile one vendor function (with the spec's drops / inline calls) into ops."""

    def __init__(self, pin, spec, files, bases, part):
        self.pin, self.spec, self.files, self.bases, self.part = pin, spec, files, bases, part
        fkey, fname = part["vendor_fn"]
        raw = function_body(vendor(pin, files[fkey]), fname)
        self.fn = f"{files[fkey]}::{fname}"
        for dr in part.get("drop", []):
            a = raw.index(dr["from"])
            b = raw.index(dr["to"], a)
            raw = raw[:a] + "}\n" + raw[b:]
        ic = part.get("inline_call")
        if ic:
            callee = function_body(vendor(pin, files[fkey]), ic["fn"])
            if raw.count(ic["call"]) != 1:
                raise DeriveError(f"inline call {ic['call']!r} occurs {raw.count(ic['call'])} times in {fname}")
            raw = raw.replace(ic["call"], f"__inline_begin({ic['fn']});\n" + callee + "\n__inline_end();")
            for v in ic.get("verify", []):
                if v["text"] not in vendor(pin, files[v["file"]]):
                    raise DeriveError(f"verify text missing: {v['text']!r}")
        for v in part.get("verify", []):
            if v["text"] not in vendor(pin, files[v["file"]]):
                raise DeriveError(f"verify text missing: {v['text']!r}")
        self.src = strip_comments(raw)
        self.base = bases[part["base"]]
        hdr = vendor(pin, files[part["header"]])
        self.defs = header_defines(hdr)
        self.layouts = header_layouts(hdr)
        self.true = {norm(c) for c in part.get("true_conditions", [])}
        self.ignored = {norm(c) for c in part.get("ignored_calls", [])}

    def reg_addr(self, name):
        if name not in self.defs:
            raise DeriveError(f"register {name} is not defined in the header of {self.fn}")
        return self.base + self.defs[name]

    def compile(self):
        ops, vars_ = [], {}
        self.seen = []
        via = [None]

        def emit(o):
            o["via"] = via[0]
            ops.append(o)
        stats = statements(self.src)
        for kind, s in stats:
            m = re.fullmatch(r"__inline_begin\((\w+)\)", s) if kind == "st" else None
            if m:
                via[0] = m.group(1)
                continue
            if kind == "st" and s == "__inline_end()":
                via[0] = None
                continue
            if kind == "st":
                self.seen.append(s)
            if kind == "if":
                if norm(s) not in self.true:
                    raise DeriveError(f"condition not listed as true in the spec ({self.fn}): {s!r}")
                continue
            if re.fullmatch(r"(u32|void)\b[^=()]*", s) or re.fullmatch(r"void( __iomem)? ?\*\s*\w+\s*=\s*\w+->regs_base", s) \
                    or re.fullmatch(r"\w+ = \w+->regs_base", s):
                continue
            m = re.fullmatch(r"reg = readl\((?:regs_)?base \+ (\w+)\)", s)
            if m:
                emit({"k": "LOAD", "addr": self.reg_addr(m.group(1)), "reg": m.group(1), "text": s})
                continue
            m = re.fullmatch(r"\(\((\w+)\) \(&reg\)\)->b\.(\w+) = (\w+)", s)
            if m:
                lay = self.layouts.get(m.group(1))
                if lay is None or m.group(2) not in lay:
                    raise DeriveError(f"field {m.group(1)}.{m.group(2)} has no layout ({self.fn})")
                lsb, w = lay[m.group(2)]
                v = cint(m.group(3))
                if v >> w:
                    raise DeriveError(f"value {v} does not fit {w} bits: {s!r}")
                mask = ((1 << w) - 1) << lsb
                emit({"k": "SET", "mask": mask, "val": v << lsb, "field": m.group(2), "text": s})
                continue
            m = re.fullmatch(r"reg = (0[xX][0-9a-fA-F]+|\d+)", s)
            if m:
                emit({"k": "CONST", "val": cint(m.group(1)), "text": s})
                continue
            m = re.fullmatch(r"value = (\d+)", s)
            if m:
                vars_["value"] = int(m.group(1))
                continue
            m = re.fullmatch(r"writel\(reg, (?:regs_)?base \+ (\w+)\)", s)
            if m:
                emit({"k": "STORE", "addr": self.reg_addr(m.group(1)), "reg": m.group(1), "text": s})
                continue
            m = re.fullmatch(r"udelay\((\w+)\)", s)
            if m:
                a = m.group(1)
                us = vars_[a] if a in vars_ else cint(a)
                emit({"k": "DELAY", "val": us, "text": s})
                continue
            if s.startswith("pr_info("):
                m = re.search(r"readl\((?:regs_)?base \+ (\w+)\)", s)
                if m:
                    emit({"k": "RDLOG", "addr": self.reg_addr(m.group(1)), "reg": m.group(1), "text": s})
                continue
            if s in self.ignored:
                continue
            raise DeriveError(f"unmodelled statement in {self.fn}: {s!r}")
        return merge_sets(ops)


def merge_sets(ops):
    out = []
    for o in ops:
        if o["k"] == "SET" and out and out[-1]["k"] == "SET":
            p = out[-1]
            p["val"] = (p["val"] & ~o["mask"]) | o["val"]
            p["mask"] |= o["mask"]
            p["field"] += "+" + o["field"]
            p["text"] += " ; " + o["text"]
        else:
            out.append(dict(o))
    return out


# --------------------------------------------------------------------------------------------- the ladder
def build(spec):
    pin = spec["pin"]
    check_pin(pin)
    files = spec["files"]
    # base addresses: the literal vendor text must be in the named file
    bases = {}
    for name, b in spec["bases"].items():
        if b["text"] not in vendor(pin, files[b["file"]]):
            raise DeriveError(f"base {name}: vendor text not found: {b['text']!r}")
        bases[name] = cint(b["value"])
        if f"0x{bases[name]:08x}".lower() not in b["text"].lower().replace("0x0 0x", "0x"):
            raise DeriveError(f"base {name}: value {b['value']} is not in its vendor text")
    consts = {}
    for name, c in spec["constants"].items():
        if c["text"] not in vendor(pin, files[c["file"]]):
            raise DeriveError(f"constant {name}: vendor text not found")
        consts[name] = cint(c["value"])
    sem = spec["pmucal_semantics"]
    for t in sem["verify"]:
        if t not in vendor(pin, files[sem["file"]]):
            raise DeriveError(f"PMUCAL semantics text missing: {t!r}")

    arrays = pmucal_arrays(vendor(pin, files["pmucal"]))
    sfr = sfr_table(vendor(pin, files["cmucal"]))
    ops = []
    fn_stmts = {}

    def add(rung, k, **kw):
        o = {"k": k, "rung": rung}
        o.update(kw)
        ops.append(o)
        return o

    def pm_row(arr, name):
        rows = [r for r in arrays[arr] if r["name"] == name]
        if len(rows) != 1:
            raise DeriveError(f"{arr}.{name}: {len(rows)} rows")
        return used(rows[0])

    def read_op(rung, r, plan_steps):
        if "pmucal" in r:
            row = pm_row(*r["pmucal"])
            addr, src = row["base"] + row["offset"], row["text"]
        elif "sfr" in r:
            off, b = sfr[r["sfr"]]
            if b != r["base"]:
                raise DeriveError(f"{r['sfr']} is in {b}, spec says {r['base']}")
            addr, src = bases[b] + off, f"SFR({r['sfr']}, 0x{off:x}, {b})"
        elif "define" in r:
            d = header_defines(vendor(pin, files[r["define"][0]]))[r["define"][1]]
            addr, src = bases[r["base"]] + d, f"#define {r['define'][1]} 0x{d:x}"
        else:
            hdr = header_defines(vendor(pin, files[r["header"]]))
            addr, src = bases[r["base"]] + hdr[r["name"]], f"#define {r['name']} 0x{hdr[r['name']]:x}"
        add(rung, "RD", addr=addr, label=r["label"], source=src, plan=plan_steps)

    R = spec["rungs"]
    for r in R["L1"]["reads"]:
        read_op(1, r, R["L1"]["plan_steps"])
    for r in R["L2"]["reads"]:
        read_op(2, r, R["L2"]["plan_steps"])

    # L3 (rung 3): the vendor power-on sequence, the cmu_init rows, then the reads.
    l3 = R["L3"]
    for row in map(used, arrays[l3["power_on"]["pmucal_seq"]]):
        if row["type"] == "PMUCAL_WRITE":
            add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],
                val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=["0.20"], poweron=True)
        elif row["type"] == "PMUCAL_WAIT":
            add(3, "WAIT", addr=row["base"] + row["offset"], mask=row["mask"], val=row["value"], label=row["name"],
                source=row["text"], plan=["0.21"], poweron=True)
        else:
            raise DeriveError(f"power-on row type {row['type']}")
    omit = {o["name"]: o["plan_step"] for o in l3["cmu_init"]["omit"]}
    seen_omit = set()
    for row in map(used, arrays[l3["cmu_init"]["pmucal_seq"]]):
        if row["type"] != "PMUCAL_WRITE":
            raise DeriveError(f"cmu_init row type {row['type']}")
        if row["name"] in omit:
            seen_omit.add(row["name"])
            continue
        add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],
            val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=[], cmu_init=True)
    if seen_omit != set(omit):
        raise DeriveError("a row the spec omits is not in the vendor array")
    for r in l3["reads"]:
        read_op(3, r, l3["plan_steps"])
    read_op(4, R["L4"]["reads"][0], R["L4"]["plan_steps"])
    ops[-1]["dwc3_id"] = True
    idspec = R["L4"]["ids"]
    idh = header_defines(vendor(pin, files[idspec["header"]]))
    consts["DWC3_ID_MASK"] = idh[idspec["mask"]]
    consts["DWC3_ID_0"] = idh[idspec["accept"][0]] << 16
    consts["DWC3_ID_1"] = idh[idspec["accept"][1]] << 16
    if consts["DWC3_ID_MASK"] != 0xFFFF0000:
        raise DeriveError("DWC3_GSNPSID_MASK is not the upper half")

    # L5 (rung 5)
    l5 = R["L5"]
    for pr in l5["pre_reads"]:
        hdr = header_defines(vendor(pin, files[pr["header"]]))
        a = bases[pr["base"]] + hdr[pr["name"]]
        add(5, "RD", addr=a, label=pr["label"], source=f"#define {pr['name']} 0x{hdr[pr['name']]:x}", plan=[],
            not_alive=[cint(x) for x in pr["not_alive"]])
    iso = l5["isolation"]
    for v in iso["verify"]:
        if v["text"] not in vendor(pin, files[v["file"]]):
            raise DeriveError(f"isolation verify text missing: {v['text']!r}")
    bit = 1 << iso["bit"]
    val = 0 if iso["on_arg"] else bit     # vendor: val = on ? 0 : mask
    add(5, "WRM", addr=bases[iso["base"]] + consts[iso["offset_const"]], mask=bit, val=val, label="PHY_ISOLATION",
        source="regmap_update_bits(reg_pmu, pmu_offset, mask, val) with val = on ? 0 : mask, on = 0", plan=["1.02"])
    for part in l5["parts"]:
        p = Part(pin, spec, files, bases, part)
        compiled = p.compile()
        fn_stmts[p.fn.split("::")[1]] = p.seen
        for o in compiled:
            o = dict(o)
            o.update({"rung": 5, "fn": p.fn})
            o["label"] = o.get("reg") or o.get("field") or o["k"]
            o["source"] = o.pop("text")
            ops.append(o)
    for r in l5["final_reads"]:
        read_op(5, r, ["4.06"])
    for o in ops:
        o.setdefault("plan", [])
    return ops, bases, consts, fn_stmts


PMUCAL_KINDS = {"PMUCAL_READ": ("RD",), "PMUCAL_WRITE": ("WRP", "WRM"), "PMUCAL_WAIT": ("WAIT",)}


def check_plan(spec, ops, fn_stmts):
    """Cross-check against the NAT-040 plan: every step the spec lists exists; every plan step with a vendor statement as its
    source text is covered by a derived op of the same function; every PMUCAL row cited by the plan equals a derived op."""
    plan = json.load(open(PLAN))
    steps = {s["id"]: s for s in plan["steps"]}
    problems, covered = [], set()
    for rung, r in {**spec["rungs"], **spec["usb_rungs"]}.items():
        for sid in r["plan_steps"]:
            if sid not in steps:
                problems.append(f"{rung}: plan step {sid} does not exist")
    by_fn = {}
    for o in ops:
        if "fn" in o:
            by_fn.setdefault(o["fn"].split("::")[1], []).append(o)
    for rung in ("L5",):
        for sid in spec["rungs"][rung]["plan_steps"]:
            st = steps.get(sid)
            if not st or "func" not in st.get("source", {}):
                continue
            fn = st["source"]["func"]
            txt = norm(st["source"]["text"]).rstrip(";").strip()
            if fn not in fn_stmts:
                continue            # exynos_usbdrd_utmi_init: the wrapper order (isolation, clocks, init_link, initiate)
            if txt not in fn_stmts[fn]:
                problems.append(f"plan step {sid}: statement {txt!r} is not in the derived {fn}")
                continue
            covered.add(sid)
            for o in by_fn[fn]:
                if txt in norm(o["source"]).replace(" ;", ";").split(" ; ") or txt in [t.strip() for t in o["source"].split(" ; ")]:
                    o["plan"] = sorted(set(o["plan"]) | {sid})
    for rung in ("L1", "L2", "L3"):
        for sid in spec["rungs"][rung]["plan_steps"]:
            st = steps.get(sid)
            if not st or "PMUCAL_SEQ_DESC" not in st.get("source", {}).get("text", ""):
                continue
            row = parse_pmucal_row(st["source"]["text"])
            kinds = PMUCAL_KINDS.get(row["type"])
            if kinds is None:
                problems.append(f"plan step {sid}: PMUCAL row {row['name']} has type {row['type']}, which the ladder does not model")
                continue
            # the derived op must be of the kind the row's type means (a read of the same register is not the plan's write) and carry the row's
            # mask and value; ops without a mask / value of their own (RD, plain WRP) stand for the whole row
            hit = [o for o in ops if o.get("addr") == row["base"] + row["offset"] and o["k"] in kinds
                   and o.get("mask", row["mask"]) == row["mask"]
                   and (o["k"] == "RD" or o.get("val", row["value"]) == row["value"] & row["mask"])]
            if not hit:
                problems.append(f"plan step {sid}: PMUCAL row {row['name']} has no derived op")
            for o in hit:
                o["plan"] = sorted(set(o["plan"]) | {sid})
                covered.add(sid)
    for o in ops:
        o["plan"] = sorted(set(o["plan"]))
    return problems, covered


# --------------------------------------------------------------------------------------------- output
def c_kind(k):
    return "LK_" + k


def gen_header(spec, ops, bases, consts):
    L = []
    L.append("/* SPDX-License-Identifier: GPL-2.0-only */")
    L.append("/* GENERATED by docs/procedures/nat-045/derive.py from the vendor sources pinned below; do not edit. */")
    L.append(f"/* vendor pin {spec['pin']} (references/s24-linux) */")
    L.append("#ifndef LADDER_REGS_H")
    L.append("#define LADDER_REGS_H")
    L.append("#include <stdint.h>")
    L.append("")
    L.append("enum lad_kind { " + ", ".join(f"{c_kind(k)} = {i}" for i, k in enumerate(LK)) + " };")
    L.append("")
    L.append("struct lad_op {")
    L.append("\tuint8_t kind;\t/* enum lad_kind */")
    L.append("\tuint8_t rung;\t/* 1..5 */")
    L.append("\tuint16_t flags;\t/* LAD_F_* */")
    L.append("\tuint32_t addr;\t/* RD WRP WRM WAIT LOAD STORE RDLOG */")
    L.append("\tuint32_t mask;\t/* WRM WAIT SET: bits touched / compared */")
    L.append("\tuint32_t val;\t/* WRP WRM WAIT SET CONST: value; DELAY: microseconds; RD: not-alive word when LAD_F_NOTALIVE */")
    L.append("\tuint32_t val2;\t/* RD with LAD_F_NOTALIVE: the second not-alive word */")
    L.append("};")
    L.append("")
    L.append("#define LAD_F_POWERON\t0x1\t/* part of the vendor domain power-on sequence (hsi0_on) */")
    L.append("#define LAD_F_NOTALIVE\t0x2\t/* RD: val and val2 are words that mean the block does not answer */")
    L.append("#define LAD_F_CMUINIT\t0x8\t/* part of the vendor hsi0_cmu_init rows (run only when the domain was off) */")
    L.append("#define LAD_F_DWC3ID\t0x10\t/* RD: the upper half must be one of LAD_DWC3_ID_0 / _1 */")
    L.append("#define LAD_F_SOFT\t0x4\t/* STORE: a read-back mismatch is recorded, not fatal (vendor init the NAT-040 plan does not list) */")
    L.append("")
    for n, b in sorted(bases.items()):
        L.append(f"#define LAD_BASE_{n}\t0x{b:08x}u")
    L.append(f"#define LAD_DWC3_ID_MASK\t0x{consts['DWC3_ID_MASK']:08x}u")
    L.append(f"#define LAD_DWC3_ID_0\t0x{consts['DWC3_ID_0']:08x}u")
    L.append(f"#define LAD_DWC3_ID_1\t0x{consts['DWC3_ID_1']:08x}u")
    L.append(f"#define LAD_WAIT_TIMEOUT_US\t{spec['pmucal_semantics']['wait_timeout_us']}u")
    L.append("")
    L.append(f"#define LAD_NOPS {len(ops)}")
    L.append("static const struct lad_op lad_ops[LAD_NOPS] = {")
    for i, o in enumerate(ops):
        fl = []
        if o.get("poweron"):
            fl.append("LAD_F_POWERON")
        if o.get("not_alive"):
            fl.append("LAD_F_NOTALIVE")
        if o.get("cmu_init"):
            fl.append("LAD_F_CMUINIT")
        if o.get("dwc3_id"):
            fl.append("LAD_F_DWC3ID")
        if o.get("via") and o["k"] == "STORE":
            fl.append("LAD_F_SOFT")
        addr = o.get("addr", 0)
        mask = o.get("mask", 0)
        val = o.get("val", 0)
        val2 = 0
        if o.get("not_alive"):
            val, val2 = o["not_alive"]
        L.append("\t/* %3d L%d %-24s */ { %s, %d, %s, 0x%08xu, 0x%08xu, 0x%08xu, 0x%08xu }," % (
            i, o["rung"], o["label"][:24], c_kind(o["k"]), o["rung"], "|".join(fl) or "0", addr, mask, val, val2))
    L.append("};")
    L.append("")
    starts = [next((i for i, o in enumerate(ops) if o["rung"] == r), len(ops)) for r in range(1, 6)] + [len(ops)]
    L.append("/* index of the first op of rung r (r = 1..5); [6] is LAD_NOPS */")
    L.append("static const uint16_t lad_rung_start[7] = { 0, " + ", ".join(str(x) for x in starts) + " };")
    L.append("#endif")
    return "\n".join(L) + "\n"


def derive():
    spec = json.load(open(SPEC))
    ops, bases, consts, fn_stmts = build(spec)
    problems, covered = check_plan(spec, ops, fn_stmts)
    if problems:
        raise DeriveError("plan cross-check failed:\n  " + "\n  ".join(problems))
    header = gen_header(spec, ops, bases, consts)
    js = {"schema_version": 1, "task": "NAT-045", "pin": spec["pin"],
          "spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
          "plan_steps_covered": sorted(covered),
          "ops_not_in_the_plan": [{"i": i, "via": o["via"], "kind": o["k"], "source": o["source"]} for i, o in enumerate(ops) if o.get("via")],
          "bases": {k: f"0x{v:08x}" for k, v in bases.items()}, "ops": []}
    for i, o in enumerate(ops):
        e = {"i": i, "rung": o["rung"], "kind": o["k"], "label": o["label"], "plan": o["plan"], "source": o["source"]}
        for k in ("addr", "mask", "val"):
            if k in o:
                e[k] = f"0x{o[k]:08x}"
        if o.get("fn"):
            e["fn"] = o["fn"]
        if o.get("via"):
            e["via"] = o["via"]
        js["ops"].append(e)
    return header, json.dumps(js, indent=1) + "\n"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--header", default=str(OUT_H))
    ap.add_argument("--json", default=str(OUT_JSON))
    a = ap.parse_args()
    try:
        header, js = derive()
    except DeriveError as e:
        print(f"derive: {e}", file=sys.stderr)
        return 2
    if a.write:
        Path(a.header).parent.mkdir(parents=True, exist_ok=True)
        Path(a.header).write_text(header)
        Path(a.json).write_text(js)
        print(f"wrote {a.header} and {a.json}")
        return 0
    ok = Path(a.header).read_text() == header and Path(a.json).read_text() == js
    print("up to date" if ok else "OUT OF DATE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
