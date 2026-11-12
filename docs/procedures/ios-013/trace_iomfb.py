#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""IOS-013 source-review helper: which IOMobileFramebuffer user-client selectors does the
iOS 16.5 (20F66) userland call, and which of them does the project's kernel stand-in
(MiniIOMobileFramebuffer.cpp) implement?

Evidence kind: source-review (static reading of the shared cache and of our own kernel source).
It does not execute anything and says nothing about how Apple's backboardd behaves at run time.

Method (all of it is a heuristic and is labelled as such in the note):
  * read the IOMobileFramebuffer image out of the dyld shared cache under artifacts/ (Apple input,
    never committed);
  * walk its __text; remember the last `mov w1, #imm` and, at each direct bl/b, follow up to four
    branch islands (`b #x`, `adrp+add+br`, `adrp+ldr+br` through the cache's GOT) to the final target;
  * a target equal to one of IOKit's IOConnectCall*Method exports is a user-client call and the
    remembered immediate is its selector (argument 2 of IOConnectCallMethod and friends);
  * the owning export of a call site is the nearest preceding export, so static helpers are
    attributed to it: the per-export column is an approximation, the selector SET is not.
Output is a sanitized JSON (selector numbers, export names, counts: no bytes of Apple code).

Run with a python that has capstone, e.g. artifacts/nat-065/venv/bin/python -W ignore -I.
"""
import argparse, bisect, importlib.util, json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "artifacts/ios-root/recipe/sysimage/20F66__iPhone10,3_6/dyld_shared_cache_arm64"
KDIR = ROOT / "references/s24-port/xnu/hackios/files/iokit/Kernel"
STANDIN = KDIR / "MiniIOMobileFramebuffer.cpp"
SURFACE_STANDIN = KDIR / "MiniIOSurface.cpp"
IOMFB = "/System/Library/PrivateFrameworks/IOMobileFramebuffer.framework/IOMobileFramebuffer"
IOSURFACE = "/System/Library/Frameworks/IOSurface.framework/IOSurface"
IOKIT = "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit"
QC = "/System/Library/Frameworks/QuartzCore.framework/QuartzCore"


def load_ma():
    spec = importlib.util.spec_from_file_location("macho_audit", ROOT / "tools/ios/macho_audit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["macho_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def exports(d, ma, path):
    m, _ = d.macho(path)
    lk = next(s for s in m["segments"] if s["name"] == "__LINKEDIT")
    off, size = m["exports_trie"]
    trie = d.read(lk["vmaddr"] + (off - lk["fileoff"]), size)
    tb = next(s for s in m["segments"] if s["name"] == "__TEXT")["vmaddr"]
    return {k.lstrip("_"): tb + v[1] for k, v in ma.parse_exports(trie).items() if v[1] is not None}, m


def standin_selectors(path, prefix):
    """Selectors the stand-in names in its enum (all) and the subset it handles in a switch (a name alone is not enough)."""
    src = path.read_text()
    enum = {n: int(v) for n, v in re.findall(r"\b(%s\w+)\s*=\s*(\d+)" % prefix, src)}
    handled = set(re.findall(r"case\s+(%s\w+)\s*:" % prefix, src))
    return {v: n for n, v in enum.items() if n in handled}, {v: n for n, v in enum.items()}


def scan(d, cs, ma, conn, text_sec):
    inv = {a: n for n, a in conn.items()}
    text = bytes(d.read(text_sec["addr"], text_sec["size"]))

    def step(addr):
        try:
            ins = list(cs.disasm(bytes(d.read(addr, 12)), addr))
        except Exception:
            return addr
        if ins and ins[0].mnemonic == "b" and ins[0].op_str.startswith("#"):
            return int(ins[0].op_str[1:], 16)
        if len(ins) >= 3 and ins[0].mnemonic == "adrp" and ins[2].mnemonic == "br":
            page = int(ins[0].op_str.split("#")[1], 16)
            if ins[1].mnemonic == "add":
                return page + int(ins[1].op_str.split("#")[-1], 16)
            if ins[1].mnemonic == "ldr":
                mm = re.search(r"#(0x[0-9a-f]+)\]", ins[1].op_str)
                return struct.unpack("<Q", d.read(page + (int(mm.group(1), 16) if mm else 0), 8))[0] & 0xFFFFFFFFFF
        return addr

    sites, last, direct = [], None, 0
    for i in cs.disasm(text, text_sec["addr"]):
        if i.mnemonic in ("mov", "movz") and i.op_str.startswith("w1, #"):
            last = int(i.op_str.split("#")[1], 0)
        elif i.mnemonic in ("bl", "b") and i.op_str.startswith("#"):
            direct += 1
            r = int(i.op_str[1:], 16)
            for _ in range(4):
                r2 = step(r)
                if r2 == r:
                    break
                r = r2
            if r in inv and last is not None:
                sites.append((i.address, last, inv[r]))
            last = None
        elif i.mnemonic == "ret":
            last = None
    return sites, direct


def census(d, cs, ma, conn, image, standin, prefix):
    ex, m = exports(d, ma, image)
    text_sec = next(s for s in m["sections"] if s["name"] == "__text")
    sites, direct = scan(d, cs, ma, conn, text_sec)
    starts = sorted((v, k) for k, v in ex.items())
    keys = [v for v, _ in starts]
    per = {}
    for addr, sel, via in sites:
        k = bisect.bisect_right(keys, addr) - 1
        per.setdefault(starts[k][1] if k >= 0 else "?", set()).add(sel)
    selectors = sorted({s for _, s, _ in sites})
    handled, named = standin_selectors(standin, prefix)
    return {
        "image": image.rsplit("/", 1)[-1],
        "exports": len(ex),
        "text_direct_branches": direct,
        "user_client_call_sites": len(sites),
        "ioconnect_entry_points_seen": sorted({v for _, _, v in sites}),
        "userland_selectors": selectors,
        "standin_handled_in_switch": sorted(handled),
        "standin_named_only": sorted(s for s in named if s not in handled),
        "standin_missing": [s for s in selectors if s not in named],
        "standin_named_not_seen_in_image": sorted(s for s in named if s not in selectors),
        "per_export_approx": {k: sorted(v) for k, v in sorted(per.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    ma = load_ma()
    d = ma.Dsc(str(a.cache))
    iok, _ = exports(d, ma, IOKIT)
    conn = {n: v for n, v in iok.items() if n.startswith("IOConnectCall")}
    out = {
        "kind": "source-review",
        "cache": "20F66 iPhone10,3 dyld_shared_cache_arm64 (local, not committed)",
        "IOMobileFramebuffer": census(d, cs, ma, conn, IOMFB, STANDIN, "kFBMethod"),
        "IOSurface": census(d, cs, ma, conn, IOSURFACE, SURFACE_STANDIN, "kSurfaceMethod"),
    }
    # QuartzCore: does it carry a software renderer? Names only, from the image's own C strings.
    qm, _ = d.macho(QC)
    blob = b"".join(bytes(d.read(s["addr"], s["size"])) for s in qm["sections"] if s["name"] == "__cstring" and s["size"])
    pat = re.compile(rb"(?i)(software.?render|sw_render|CA_FORCE\w*|CA_DISABLE\w*|CA_USE_\w*|cpu.?render)")
    out["quartzcore_renderer_strings"] = sorted({mm.group(0).decode("latin1") for mm in pat.finditer(blob)})
    txt = json.dumps(out, indent=1, sort_keys=True)
    if a.json:
        a.json.write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
