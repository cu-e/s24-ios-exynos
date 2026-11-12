#!/usr/bin/env python3
"""IOS-012 mutation pass over tools/ios/macho_audit.py (host-test).

Each mutant is one textual change to a copy of the tool inside a temporary tree that also holds the tests; the tests must fail for the
mutant to count as killed.  The repository is never modified.  Usage: python3 -I docs/procedures/ios-012/mutants.py [--json OUT]
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

MUTANTS = [
    ("svc scan: accept any destination register", "if (p & 0x1F) == 16 and ((p >> 21) & 3) == 0:", "if ((p >> 21) & 3) == 0:"),
    ("svc scan: accept shifted immediates", "if (p & 0x1F) == 16 and ((p >> 21) & 3) == 0:", "if (p & 0x1F) == 16:"),
    ("svc scan: movn not recognised", "elif p & 0xFF800000 == 0x92800000:", "elif False:"),
    ("svc scan: movn number not inverted", "pairs.append((base + 4 * (i - 1), ~imm))", "pairs.append((base + 4 * (i - 1), -imm))"),
    ("svc scan: address of the svc instead of the movz", "pairs.append((base + 4 * (i - 1), imm))", "pairs.append((base + 4 * i, imm))"),
    ("svc scan: first word dropped from the total", "        if w == SVC_80:\n            total += 1\n            if i:", "        if w == SVC_80 and i:\n            total += 1\n            if i:"),
    ("uleb: ignore the continuation bit", "if not b & 0x80:\n            return result, off", "if True:\n            return result, off"),
    ("uleb: no shift limit", "if off >= len(data) or shift > 63:", "if off >= len(data):"),
    ("trie: reexports read as addresses", "if flags & 0x8:", "if False:"),
    ("trie: child offsets unchecked", "if child >= len(trie):", "if False:"),
    ("trie: edge text not prefixed", "stack.append((child, prefix + edge))", "stack.append((child, edge))"),
    ("macho: any magic accepted", "!= MH_MAGIC_64:", "!= MH_MAGIC_64 and False:"),
    ("macho: command size alignment unchecked", "if csize < 8 or csize % 4 or off + csize > end:", "if csize < 8 or off + csize > end:"),
    ("macho: command area bound unchecked", "or 32 + sizeofcmds > (size if size is not None else len(data) - base):", "or False:"),
    ("macho: command count unbounded", "if ncmds > 4096 or", "if False or"),
    ("macho: section table unchecked", "if so + 80 > off + csize:", "if False:"),
    ("macho: weak dylib not distinguished", '"LOAD_WEAK_DYLIB": 0x80000018', '"LOAD_WEAK_DYLIB": 0x80000099'),
    ("fat: first slice taken", "if cpu == CPU_TYPE_ARM64:", "if True:"),
    ("fat: no arm64 slice accepted", 'raise AuditError("no arm64 slice")', "return 0, len(data)"),
    ("cache: .dylddata files not part of the set", r"(\.dylddata|\.dyldlinkedit)?)?", r")?)?"),
    ("cache: symbols files part of the set", r'(\.\d+(\.dylddata|\.dyldlinkedit)?)?", p.name)',
     r'(\.\d+(\.dylddata|\.dyldlinkedit)?|\.symbols)?", p.name)'),
    ("cache: mapping past the file end accepted", "if foff + size > len(mm):", "if False:"),
    ("cache: read ignores the mapping end", "if a <= addr and addr + n <= a + size:", "if a <= addr:"),
    ("cache: read picks the wrong file offset", "return mm[foff + addr - a: foff + addr - a + n]", "return mm[addr - a: addr - a + n]"),
    ("cache: not-a-cache file accepted", 'if mm[:6] != b"dyld_v":', "if False:"),
    ("closure: weak libraries count as required", 'kind != "LOAD_WEAK_DYLIB"', "True"),
    ("closure: nothing is followed through the cache", "todo.extend((l[\"name\"], l[\"kind\"], name) for l in dm[\"libraries\"])", "pass"),
    ("master: #else does not flip the guard", "stack.append((name, not want))", "stack.append((name, want))"),
    ("master: #ifndef treated as #if", '(kind != "ifndef") != (neg == "!")', '(neg != "!")'),
    ("master: negation ignored", '(kind != "ifndef") != (neg == "!")', '(kind != "ifndef")'),
    ("master: unbalanced #if accepted", 'raise AuditError("unbalanced #if in syscalls.master")', "pass"),
    ("master: #elif accepted silently", 'raise AuditError("#elif in syscalls.master is not handled")', "continue"),
    ("config: bundles are not expanded", "todo.extend(bundles[t])", "pass"),
    ("config: upper-case tokens taken as tags", "elif not t.isupper():", "else:"),
    ("config: first tag list used instead of the last", "for t in lists[-1].split(\",\")", "for t in lists[0].split(\",\")"),
    ("config: a tag list needs all tags", "any(t.strip() in tags for t in lists[-1].split(\",\"))", "all(t.strip() in tags for t in lists[-1].split(\",\"))"),
    ("resolve: an undefined option counts as off", "if opt not in states:\n                    unresolved.add(opt)\n                    verdict = None\n                    break", "if opt not in states:\n                    verdict = False\n                    break"),
    ("resolve: guards beyond the first ignored", "for opt, want in guards:", "for opt, want in guards[:1]:"),
    ("norm: sys_ prefix kept", 'for pre in ("sys_", "syscall_"):', "for pre in ():"),
    ("norm: _trap suffix kept", 'return n[:-5] if n.endswith("_trap") else n', "return n"),
    ("norm: NOCANCEL variants kept", 'n = name.split("$")[0].lstrip("_")', 'n = name.lstrip("_")'),
    ("compare: nosys entries counted as matches", 'elif num > 0 and norm(kname) in ("nosys", "enosys"):', "elif False:"),
    ("compare: slot 0 reported", "elif num == 0:\n            exact += 1", "elif False:\n            exact += 1"),
    ("compare: unresolved entries judged anyway", 'elif status.startswith("unresolved"):', "elif False:"),
    ("compare: mach trap numbers not negated", "kname, status = mach.get(-num), \"mach trap table\"", "kname, status = mach.get(num), \"mach trap table\""),
    ("compare: names ignored", "elif any(norm(n) == norm(kname) for n in names):", "elif True:"),
    ("exports: trie placed at the wrong address", "lk[\"vmaddr\"] + (dataoff - lk[\"fileoff\"])", "lk[\"vmaddr\"] + dataoff"),
    ("exports: offsets relative to the section", "names_at.setdefault(text_base + off, [])", "names_at.setdefault(taddr + off, [])"),
    ("commpage: orr shape not recognised", "elif (w & ~0x1F) == _ORR_HIGH and (w & 0x1F) != 31:", "elif False:"),
    ("commpage: orr shape accepts sp as destination", "elif (w & ~0x1F) == _ORR_HIGH and (w & 0x1F) != 31:", "elif (w & ~0x1F) == _ORR_HIGH:"),
    ("commpage: orr low lane searched without a bound", "for j in range(i + 1, min(len(words), i + 5)):", "for j in range(i + 1, len(words)):"),
    ("commpage: orr low lane searched one instruction short", "for j in range(i + 1, min(len(words), i + 5)):", "for j in range(i + 1, min(len(words), i + 4)):"),
    ("commpage: movk window too small", "window = range(max(0, i - 5), min(len(words), i + 6))", "window = range(max(0, i - 4), min(len(words), i + 5))"),
    ("commpage: movk window too large", "window = range(max(0, i - 5), min(len(words), i + 6))", "window = range(max(0, i - 6), min(len(words), i + 7))"),
    ("commpage: lane 1 of another register accepted", "if any(words[j] == _MOVK16 | rd for j in window):", "if any((words[j] & ~0x1F) == _MOVK16 for j in window):"),
    ("commpage: shifted low lane accepted", "and (x & 0x1F) == rd and ((x >> 21) & 3) == 0:", "and (x & 0x1F) == rd:"),
    ("commpage: low lane of another register accepted", "and (x & 0x1F) == rd and ((x >> 21) & 3) == 0:", "and ((x >> 21) & 3) == 0:"),
    ("commpage: movz low lane refused", "in (0xF2800000, 0xD2800000)", "in (0xF2800000,)"),
    ("commpage: read-only offsets taken from the rw base", "return name, addr - start", "return name, addr - COMMPAGE_RW"),
    ("commpage: pages twice as long", "if start <= addr < start + COMMPAGE_SPAN:", "if start <= addr < start + 2 * COMMPAGE_SPAN:"),
    ("commpage: page start excluded", "if start <= addr < start + COMMPAGE_SPAN:", "if start < addr < start + COMMPAGE_SPAN:"),
    ("commpage: hits not merged", "return sorted(set(hits))", "return sorted(hits)"),
    ("commpage: names of the two pages merged", '("ro" if m.group(2) == "RO" else "rw", int(m.group(3), 16))', '("rw", int(m.group(3), 16))'),
    ("commpage: nearest field is the lowest", "o = max(lower)", "o = min(lower)"),
    ("commpage: nearest field ignores the page", "lower = [o for (r, o) in names if r == region and o < off]", "lower = [o for (r, o) in names if o < off]"),
    ("sysregs: msr not recognised", "if (w >> 20) in (0xD51, 0xD53):", "if (w >> 20) in (0xD53,):"),
    ("sysregs: mrs not recognised", "if (w >> 20) in (0xD51, 0xD53):", "if (w >> 20) in (0xD51,):"),
    ("sysregs: mrs and msr swapped", '"mrs" if (w >> 20) == 0xD53 else "msr"', '"msr" if (w >> 20) == 0xD53 else "mrs"'),
    ("sysregs: op0 always 3", "2 + ((w >> 19) & 1)", "3"),
    ("sysregs: op1 and CRn swapped", "(w >> 16) & 7, (w >> 12) & 15, (w >> 8) & 15", "(w >> 12) & 15, (w >> 16) & 7, (w >> 8) & 15"),
    ("sysregs: op2 read from the wrong bits", "(w >> 5) & 7)\n            out.append", "(w >> 6) & 7)\n            out.append"),
    ("sysregs: CRn 10 counted as implementation defined", "crn in (11, 15)", "crn in (10, 11, 15)"),
    ("sysregs: CRn 11 not implementation defined", "crn in (11, 15)", "crn in (15,)"),
    ("sysregs: op0 ignored for implementation defined", "return op0 == 3 and crn in (11, 15)", "return crn in (11, 15)"),
    ("cstrings: all strings returned", "for p in pats}}", "for p in pats} if False else {p.pattern: sorted(set(strings)) for p in pats}}"),
]


def run(tree, timeout=90):
    try:
        r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-p", "test_macho_audit.py"],
                           cwd=tree, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, "timeout after %d s" % timeout
    return r.returncode, (r.stderr or "")[-300:]


def main():
    out_path = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    src = (ROOT / "tools/ios/macho_audit.py").read_text()
    results = []
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        (tree / "tools/ios").mkdir(parents=True)
        (tree / "tests").mkdir(parents=True)
        shutil.copy(ROOT / "tests/test_macho_audit.py", tree / "tests/test_macho_audit.py")
        (tree / "tools/ios/macho_audit.py").write_text(src)
        code, tail = run(tree)
        if code != 0:
            print("baseline fails:", tail)
            return 2
        for name, old, new in MUTANTS:
            if src.count(old) != 1:
                results.append({"mutant": name, "status": "invalid", "occurrences": src.count(old)})
                print("INVALID  %s (%d occurrences)" % (name, src.count(old)), flush=True)
                continue
            (tree / "tools/ios/macho_audit.py").write_text(src.replace(old, new))
            code, tail = run(tree)
            row = {"mutant": name, "status": "survived" if code == 0 else "killed"}
            if code == -1:
                row["by"] = "timeout"
            results.append(row)
            print("%-8s %s" % (row["status"], name), flush=True)
    killed = sum(r["status"] == "killed" for r in results)
    survived = [r["mutant"] for r in results if r["status"] == "survived"]
    invalid = [r["mutant"] for r in results if r["status"] == "invalid"]
    print("mutants %d killed %d survived %d invalid %d" % (len(results), killed, len(survived), len(invalid)))
    if out_path:
        Path(out_path).write_text(json.dumps({"mutants": results, "killed": killed, "survived": survived, "invalid": invalid}, indent=1) + "\n")
    return 0 if not survived and not invalid else 1


if __name__ == "__main__":
    sys.exit(main())
