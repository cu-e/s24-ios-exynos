#!/usr/bin/env python3
"""Host pre-check of what the NAT-020 loader would do with a SWEETXNU payload (NAT-022 / NAT-026).

usage: check_payload.py LOADER_C PAYLOAD [--offset N] [--win-mib 256,512] [--win-base 0xC0000000]
                        [--mpidr 0x80000000] [--no-adt] [--no-align] [--json OUT]

LOADER_C is the loader.c of the build that will run (the NAT-020 build-003 source or a patched copy);
adt_patch.c is read from the same directory. PAYLOAD is payload.bin (OFFSET 0) or the loader
Image.payload (OFFSET = the loader Image size). Nothing here opens a phone.

What runs, and what is verbatim:
  1. header: the struct layout and the `if (p->version != 1 ...)` / `if (!p->mem_size ...)` conditions are
     cut out of loader.c and compiled unchanged; every `||` clause is evaluated on its own, so the output
     names the clause that would make fail() run (run 004: `adt_size & 7`).
  2. RAM/segment checks, ADT/boot_args room and the entry check: the text of those blocks is cut from
     loader.c and compiled unchanged (ui_set_stage becomes a no-op, fail() returns its message, and the
     one occurrence of `(uintptr_t)p` is replaced by the modelled runtime address of the payload). They
     are evaluated for each window size in --win-mib (the loader picks 256..512 MiB, capped by mem_size).
  3. ADT patching: the real adt_patch.c is compiled for the host and run on the ADT bytes of the
     payload in a guarded buffer of exactly adt_size bytes, with the argument expressions of loader.c
     (the four call sites are written out here, not extracted). Bytes changed and guard overruns are
     reported.
  4. alignment (NAT-027): the same ADT harness is rebuilt with gcc -fsanitize=alignment
     -fsanitize-undefined-trap-on-error and run again. The loader runs with the MMU off, so every data
     access is Device memory and must be naturally aligned (run 005 took an alignment fault in
     adt_set_dram); x86-64 and the plain run in step 3 tolerate misaligned accesses. A trap is reported as
     `FIRES adt_patch.c: MISALIGNED ACCESS in <call>`, with the ESR the S24 would show (EC 0x25, DFSC 0x21).
     --no-align skips it; it is `unavailable` if gcc cannot build it. It covers adt_patch.c only; the
     rest of the loader is covered by scan_unaligned.py (unscaled immediates only).
Not evaluated (no S-Boot DTB on the host): which RAM window choose_window() picks, the framebuffer
selection, GIC access and every hardware effect. A pass here says the payload is acceptable to those
code paths; it is host-test evidence only, not a run on the S24.
"""
from pathlib import Path
import argparse, json, re, shutil, subprocess, sys, tempfile

DEFS = ('#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n')

def split_top(expr):
    parts, depth, cur, i = [], 0, '', 0
    while i < len(expr):
        c = expr[i]
        depth += (c == '(') - (c == ')')
        if depth == 0 and expr.startswith('||', i):
            parts.append(cur.strip()); cur = ''; i += 2; continue
        cur += c; i += 1
    parts.append(cur.strip())
    return [' '.join(p.split()) for p in parts if p.strip()]

def cut(src, pattern, what):
    m = re.search(pattern, src, re.S)
    if not m:
        sys.exit(f'loader.c anchor not found: {what}')
    return m

def extract(src):
    structs = cut(src, r'(struct payload_seg \{.*?\};\s*struct payload \{.*?\};)', 'payload struct').group(1)
    defs = [cut(src, r'(#define BOOT_LINE_LENGTH\s+\d+)', 'BOOT_LINE_LENGTH').group(1),
            cut(src, r'(#define PAGE_16K\s+\S+)', 'PAGE_16K').group(1)]
    checks = []
    for first in ('p->version != 1', '!p->mem_size'):
        mm = cut(src, r'if \((' + re.escape(first) + r'[^{]*?)\) \{\s*(?:ui_set_stage\([^;]*;\s*)?return fail\("([^"]+)"\);', 'condition ' + first)
        checks += [(mm.group(2), c) for c in split_top(mm.group(1))]
    a = cut(src, r'(uintptr_t mem_end = win_base \+ win_size;.*?return fail\("payload overlaps XNU RAM"\);\n\t\})', 'RAM block').group(1)
    a, n = re.subn(r'\(uintptr_t\)p\b', 'payload_runtime', a)
    if n != 1:
        sys.exit(f'expected one (uintptr_t)p in the RAM block, found {n}')
    b = cut(src, r'(uintptr_t adt_pa = kernel_end;.*?return fail\("no room for ADT/boot_args"\);\n\t\})', 'ADT room block').group(1)
    c = cut(src, r'(uintptr_t entry_pa = win_base.*?return fail\("entry outside kernel"\);\n\t\})', 'entry block').group(1)
    pram = cut(src, r'(uint64_t pram_base = [^;]*;)\s*(uint64_t pram_size = [^;]*;)', 'pram lines')
    return defs, structs, checks, a, b, c, pram.group(1), pram.group(2)

def harness(defs, structs, checks, a, b, c, pram_base, pram_size, adt_c):
    hdr = ''.join(f'  printf("H\\t%d\\t%s\\t%s\\n", !!({cl}), "{m}", "{cl.replace(chr(34), chr(39))}");\n' for m, cl in checks)
    return DEFS + '\n'.join(defs) + '''
#define UI_STAGE_RAM 0
#define UI_STAGE_ADT 0
#define UI_FAIL 0
#define ui_set_stage(a, b, c) ((void)0)
#define fail(s) (s)
''' + structs + '''
#include "adt_patch.h"
static const char *stages(const struct payload *p, uintptr_t payload_runtime, uint64_t win_base, uint64_t win_size,
                          uint64_t *ba_off, uint64_t *need)
{
''' + a + '''
''' + b + '''
  *ba_off = ba_pa - win_base;
''' + c + '''
  *need = (ba_pa + PAGE_16K) - win_base;
  return NULL;
}
static void adt_run(const struct payload *p, FILE *f, long base, uint64_t win_base, uint64_t win_size, uint32_t mpidr)
{
  uint64_t sz = p->adt_size;
  unsigned char *raw = malloc(sz + 128), *adt, *orig;
  if (!raw) { printf("A\\tnomem\\n"); return; }
  memset(raw, 0xa5, sz + 128); adt = raw + 64;
  orig = malloc(sz ? sz : 1);
  fseek(f, base + (long)p->adt_off, SEEK_SET);
  if (fread(adt, 1, sz, f) != sz) { printf("A\\tshort-read\\n"); return; }
  memcpy(orig, adt, sz);
  uintptr_t adt_pa = (uintptr_t)adt;
''' + '  ' + pram_base + '\n  ' + pram_size + '''
  printf("T\\tadt_set_boot_cpu_mpidr\\n");
  int r1 = adt_set_boot_cpu_mpidr(adt_pa, p->adt_size, mpidr);
  printf("T\\tadt_set_dram\\n");
  int r2 = adt_set_dram(adt_pa, p->adt_size, win_base, win_size);
  printf("T\\tadt_set_pram\\n");
  int r3 = adt_set_pram(adt_pa, p->adt_size, pram_base, pram_size);
  printf("T\\tadt_rebase_ramdisk\\n");
  int r4 = adt_rebase_ramdisk(adt_pa, p->adt_size, (int64_t)(win_base - p->phys_base));
  int guard = 0;
  for (int i = 0; i < 64; i++) guard |= (raw[i] != 0xa5) | (raw[64 + sz + i] != 0xa5);
  printf("A\\tmpidr=%d\\tdram=%d\\tpram=%d\\tramdisk=%d\\tguard_overrun=%d\\n", r1, r2, r3, r4, guard);
  uint64_t i = 0, changed = 0;
  while (i < sz) {
    if (adt[i] == orig[i]) { i++; continue; }
    uint64_t s = i; while (i < sz && adt[i] != orig[i]) i++;
    changed += i - s;
    printf("D\\t0x%llx\\t%llu\\n", (unsigned long long)s, (unsigned long long)(i - s));
  }
  printf("A\\tchanged_bytes=%llu\\n", (unsigned long long)changed);
  free(raw); free(orig);
}
int main(int argc, char **argv)
{
  setvbuf(stdout, NULL, _IONBF, 0);   /* a trap must not lose the trace lines printed before it */
  FILE *f = fopen(argv[1], "rb"); if (!f) return 2;
  long base = strtol(argv[2], 0, 0);
  uint64_t win_base = strtoull(argv[3], 0, 0);
  uint32_t mpidr = (uint32_t)strtoul(argv[4], 0, 0);
  int do_adt = atoi(argv[5]);
  uint64_t payload_runtime = strtoull(argv[6], 0, 0);
  static union { struct payload h; unsigned char raw[65536]; } u;
  fseek(f, base, SEEK_SET);
  if (fread(u.raw, 1, 4096, f) < sizeof(struct payload)) return 3;
  const struct payload *p = &u.h;
  if (p->magic[0] != 'S' || p->magic[7] != 'U') { printf("bad magic\\n"); return 4; }
''' + hdr + '''
  for (int i = 6 + 1; i < argc; i++) {
    uint64_t win_size = strtoull(argv[i], 0, 0) << 20;
    if (win_size > p->mem_size) win_size = p->mem_size;   /* loader.c: `if (win_size > p->mem_size) win_size = p->mem_size;` */
    uint64_t ba_off = 0, need = 0;
    const char *r = stages(p, (uintptr_t)payload_runtime, win_base, win_size, &ba_off, &need);
    printf("S\\t%llu\\t%s\\t%llu\\t%llu\\n", (unsigned long long)(win_size >> 20), r ? r : "ok", (unsigned long long)ba_off, (unsigned long long)need);
    if (do_adt) adt_run(p, f, base, win_base, win_size, mpidr);
  }
  return 0;
}
'''

def alignment_run(c, loader, argv, tmp):
    """Rebuild the same harness with gcc's alignment sanitizer in trap mode and run it (NAT-027).

    The loader runs with the MMU off, so every data access is Device memory and must be naturally
    aligned (run 005: `*(volatile uint64_t *)(adt + off + 36)` with off + 36 = 4 mod 8 took an
    alignment fault). x86 allows such stores, so the normal run cannot see them. A SIGILL here means
    adt_patch.c made a misaligned access; the last `T` trace line names the call that was running.
    zig's own -fsanitize=alignment did not flag a misaligned volatile store in a probe, so gcc is used."""
    gcc = shutil.which('gcc')
    if not gcc:
        return dict(status='unavailable', detail='gcc not found')
    exe = tmp / 'chk_align'
    cmd = [gcc, '-Wall', '-O1', '-fsanitize=alignment', '-fsanitize-undefined-trap-on-error',
           '-I', str(loader.parent), str(c), str(loader.parent / 'adt_patch.c'), '-o', str(exe)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return dict(status='unavailable', detail='gcc compile failed: ' + r.stderr[-300:])
    r = subprocess.run([str(exe)] + argv[1:], capture_output=True, text=True)
    last = win = None
    for line in r.stdout.splitlines():
        f = line.split('\t')
        if f[0] == 'T':
            last = f[1]
        elif f[0] == 'S':
            win = int(f[1])
    if r.returncode == 0:
        return dict(status='ok')
    if r.returncode < 0:
        return dict(status='fault', signal=-r.returncode, call=last, win_mib=win)
    return dict(status='error', detail=f'exit {r.returncode}')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-align', action='store_true', help='skip the alignment-trap run of adt_patch.c')
    ap.add_argument('loader_c'); ap.add_argument('payload')
    ap.add_argument('--offset', type=lambda s: int(s, 0), default=0)
    ap.add_argument('--win-mib', default='256,512')
    ap.add_argument('--win-base', type=lambda s: int(s, 0), default=0xC0000000)
    ap.add_argument('--mpidr', type=lambda s: int(s, 0), default=0x80000000)
    ap.add_argument('--runtime-image', type=lambda s: int(s, 0), default=0x801a0000,
                    help='runtime address of the loader Image (inferred from run 003); the payload is modelled at this plus --offset')
    ap.add_argument('--no-adt', action='store_true')
    ap.add_argument('--json')
    a = ap.parse_args()
    loader = Path(a.loader_c)
    parts = extract(loader.read_text())
    prog = harness(*parts, None)
    wins = [int(x) for x in a.win_mib.split(',') if x]
    with tempfile.TemporaryDirectory() as t:
        c, exe = Path(t) / 'chk.c', Path(t) / 'chk'
        c.write_text(prog)
        cmd = ['zig', 'cc', '-Wall', '-O1', '-I', str(loader.parent), str(c), str(loader.parent / 'adt_patch.c'), '-o', str(exe)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit('compile failed:\n' + r.stderr)
        argv = [str(exe), a.payload, str(a.offset), hex(a.win_base), hex(a.mpidr), '0' if a.no_adt else '1',
                hex(a.runtime_image + a.offset)] + [str(w) for w in wins]
        r = subprocess.run(argv, capture_output=True, text=True)
        align = None if (a.no_align or a.no_adt) else alignment_run(c, loader, argv, Path(t))
    if r.returncode:
        sys.exit(f'harness exit {r.returncode}: {r.stdout}{r.stderr}')
    out = dict(loader_c=a.loader_c, payload=a.payload, offset=a.offset, win_base=hex(a.win_base), mpidr=hex(a.mpidr),
               header=[], windows=[], alignment=align,
               notes='host-test only; see the module docstring for what is verbatim and what is not evaluated')
    bad = False
    if align is not None:
        if align['status'] == 'ok':
            print('ok    adt_patch.c: no misaligned access (gcc -fsanitize=alignment, trap mode)')
        elif align['status'] == 'fault':
            print(f"FIRES adt_patch.c: MISALIGNED ACCESS in {align['call']} (window {align['win_mib']} MiB, signal {align['signal']}); "
                  'on the phone (MMU off, Device memory) this is an alignment fault, ESR EC 0x25 DFSC 0x21')
            bad = True
        else:
            print(f"UNKNOWN alignment check: {align['status']} {align.get('detail', '')}; pass --no-align to skip explicitly")
            bad = True
    for line in r.stdout.splitlines():
        f = line.split('\t')
        if f[0] == 'T':
            continue
        if f[0] == 'H':
            row = dict(fires=f[1] == '1', fail_message=f[2], clause=f[3]); out['header'].append(row)
            print(('FIRES ' if row['fires'] else 'ok    ') + f"[{row['fail_message']}] {row['clause']}")
            bad |= row['fires']
        elif f[0] == 'S':
            w = dict(win_mib=int(f[1]), result=f[2], boot_args_offset=int(f[3]), min_window_bytes=int(f[4]), adt=None, adt_changes=[])
            out['windows'].append(w)
            print(f"window {w['win_mib']} MiB: {w['result']} (boot_args at +0x{w['boot_args_offset']:x}, needs 0x{w['min_window_bytes']:x} bytes)")
            bad |= w['result'] != 'ok'
        elif f[0] == 'A' and out['windows']:
            w = out['windows'][-1]
            if len(f) > 2:
                w['adt'] = dict(x.split('=') for x in f[1:])
                print('  adt_patch return codes (0 = ok): ' + ' '.join(f[1:]))
                bad |= any(v not in ('0',) for v in w['adt'].values())
            else:
                print('  ' + f[1])
        elif f[0] == 'D' and out['windows']:
            out['windows'][-1]['adt_changes'].append(dict(offset=f[1], length=int(f[2])))
    for w in out['windows']:
        if w['adt_changes']:
            print(f"  window {w['win_mib']} MiB: ADT bytes changed in {len(w['adt_changes'])} ranges: " +
                  ', '.join(f"{x['offset']}+{x['length']}" for x in w['adt_changes']))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1) + '\n')
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main())
