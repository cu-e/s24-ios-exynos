"""C preprocessor-constant helpers for the vendor cross-check (parse_defs, call_text, c_eval).

Copied unchanged from docs/procedures/nat-041/test_engine.py (same repository, same author) so that the NAT-076 tests do not
import NAT-041's test module (which puts its own `modelhost` first on sys.path). Pure Python, no I/O.
"""
import re


def parse_defs(src):
    """#define NAME[(params)] body -> {NAME: (params or None, body)}; comments stripped; later duplicates win."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"\\\n", " ", src)
    out = {}
    for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+(\w+)(\(([^)]*)\))?[ \t]+([^\n]*)$", src, re.M):
        params = None if m.group(2) is None else [x.strip() for x in m.group(3).split(",") if x.strip()]
        out[m.group(1)] = (params, m.group(4).strip())
    return out


def call_text(name, args, params):
    return name if params is None else "%s(%s)" % (name, ",".join(str(a) for a in args))


def _split_args(s, i):
    """s[i] == '(' -> (list of argument strings, index after the matching ')')"""
    depth, args, cur = 0, [], ""
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "(":
            depth += 1
            if depth > 1:
                cur += ch
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append(cur)
                return [a.strip() for a in args], j + 1
            cur += ch
        elif ch == "," and depth == 1:
            args.append(cur)
            cur = ""
        else:
            cur += ch
        j += 1
    raise ValueError("unbalanced parentheses in %r" % s)


def _expand(expr, defs, depth=0):
    if depth > 24:
        raise ValueError("macro expansion too deep: %r" % expr)
    out, i = "", 0
    while i < len(expr):
        m = re.compile(r"[A-Za-z_]\w*").match(expr, i)
        if not m:
            out += expr[i]
            i += 1
            continue
        name = m.group(0)
        i = m.end()
        if name in ("BIT", "GENMASK"):
            out += name
            continue
        if name not in defs:
            out += name
            continue
        params, body = defs[name]
        if params is None:
            out += "(" + _expand(body, defs, depth + 1) + ")"
            continue
        if i >= len(expr) or expr[i] != "(":
            out += name
            continue
        args, i = _split_args(expr, i)
        args = [_expand(a, defs, depth + 1) for a in args]
        b = body
        for p, a in zip(params, args):
            b = re.sub(r"\b%s\b" % re.escape(p), "(" + a + ")", b)
        out += "(" + _expand(b, defs, depth + 1) + ")"
    return out


def c_eval(expr, defs):
    e = _expand(expr, defs)
    e = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", e)
    e = re.sub(r"\(u(8|16|32|64)\)", "", e)
    return eval(e, {"__builtins__": {}}, {"BIT": lambda n: 1 << n,
                                          "GENMASK": lambda h, l: ((1 << (h - l + 1)) - 1) << l})
