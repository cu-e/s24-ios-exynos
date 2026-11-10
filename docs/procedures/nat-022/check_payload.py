#!/usr/bin/env python3
"""Evaluate the NAT-020 loader's own payload-header conditions on a payload, on the host.

usage: check_payload.py LOADER_C PAYLOAD [--offset N] [--json OUT]

LOADER_C is a loader.c (the NAT-020 build-003 source or a patched copy). The struct layout and the
`if (...) { ... return fail("...") }` conditions that depend only on the payload header are cut out of
that source text and compiled unchanged into a small host program, which is run on the payload bytes at
OFFSET (0 for payload.bin, the loader Image size for an Image.payload). Each `||` clause is evaluated
on its own, so the output names the clause that would make fail() run. Conditions that need the
S-Boot DTB or the RAM window (window choice, segment bounds against win_size, room for ADT/boot_args)
are not evaluated here. Host only: this never opens a phone.
"""
from pathlib import Path
import argparse, json, re, subprocess, sys, tempfile

def split_top(expr):
    parts, depth, cur = [], 0, ''
    i = 0
    while i < len(expr):
        c = expr[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if depth == 0 and expr.startswith('||', i):
            parts.append(cur.strip()); cur = ''; i += 2; continue
        cur += c; i += 1
    parts.append(cur.strip())
    return [' '.join(p.split()) for p in parts if p.strip()]

def extract(src):
    m = re.search(r'(struct payload_seg \{.*?\};\s*struct payload \{.*?\};)', src, re.S)
    assert m, 'payload struct not found'
    defs = re.search(r'#define BOOT_LINE_LENGTH\s+\d+', src)
    assert defs, 'BOOT_LINE_LENGTH not found'
    checks = []
    for pat, msg_re in ((r'if \((p->version != 1[^{]*?)\) \{\s*(?:ui_set_stage\([^;]*;\s*)?return fail\("([^"]+)"\);', None),
                        (r'if \((!p->mem_size[^{]*?)\) \{\s*(?:ui_set_stage\([^;]*;\s*)?return fail\("([^"]+)"\);', None)):
        mm = re.search(pat, src)
        assert mm, 'condition not found: ' + pat[:40]
        for clause in split_top(mm.group(1)):
            checks.append((mm.group(2), clause))
    return defs.group(0), m.group(1), checks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('loader_c'); ap.add_argument('payload')
    ap.add_argument('--offset', type=lambda s: int(s, 0), default=0)
    ap.add_argument('--json')
    a = ap.parse_args()
    define, structs, checks = extract(Path(a.loader_c).read_text())
    body = ''.join(f'  printf("%d\\t%s\\t%s\\n", !!({c}), "{m}", "{c.replace(chr(34), chr(39))}");\n' for m, c in checks)
    prog = f'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
{define}
{structs}
int main(int argc, char **argv) {{
  FILE *f = fopen(argv[1], "rb"); if (!f) return 2;
  fseek(f, strtol(argv[2], 0, 0), SEEK_SET);
  static union {{ struct payload h; unsigned char raw[4096]; }} u;
  if (fread(u.raw, 1, sizeof u.raw, f) < sizeof(struct payload)) return 3;
  const struct payload *p = &u.h;
  if (p->magic[0] != 'S' || p->magic[7] != 'U') {{ printf("bad magic\\n"); return 4; }}
{body}  return 0;
}}
'''
    with tempfile.TemporaryDirectory() as t:
        c, exe = Path(t) / 'chk.c', Path(t) / 'chk'
        c.write_text(prog)
        r = subprocess.run(['zig', 'cc', '-Wall', '-Werror', '-O1', str(c), '-o', str(exe)], capture_output=True, text=True)
        if r.returncode:
            sys.exit('compile failed:\n' + r.stderr)
        r = subprocess.run([str(exe), a.payload, str(a.offset)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'harness exit {r.returncode}: {r.stdout}{r.stderr}')
    rows = []
    for line in r.stdout.splitlines():
        v, msg, clause = line.split('\t', 2)
        rows.append({'fires': v == '1', 'fail_message': msg, 'clause': clause})
    for row in rows:
        print(('FIRES ' if row['fires'] else 'ok    ') + f"[{row['fail_message']}] {row['clause']}")
    if a.json:
        Path(a.json).write_text(json.dumps({'loader_c': a.loader_c, 'payload': a.payload, 'offset': a.offset, 'clauses': rows}, indent=1) + '\n')
    return 1 if any(x['fires'] for x in rows) else 0

if __name__ == '__main__':
    sys.exit(main())
