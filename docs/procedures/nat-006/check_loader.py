#!/usr/bin/env python3
"""NAT-006: exercise the project-built E1S loader's DTB code on this phone's real runtime FDT (host only).

Extracts ranges_sort .. choose_window verbatim from the built loader.c, compiles it with the unchanged
fdt.c and window_harness.c under UBSan (ASan shadow memory occupies the low physical addresses the DTB must be mapped at), runs it for each placement scenario and checks the chosen
RAM window independently against every /memory range, /reserved-memory region, the measured boot
framebuffer and the Samsung sec_debug_next region. Writes a JSON report.

  check_loader.py --loader-source artifacts/e1s-build/RUN/source/shim/e1s-xnu --dtb DTB --out DIR
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
CLANG = '/home/egor/.local/bin/clang'
FB_MEASURED = (0xFA200000, 1080 * 2340 * 4)  # NAT-005: s3cfb.bootloaderfb and the 1080x2340 panel; 32 bpp assumed
SEC_DEBUG_NEXT = (0x91200000, 0x200000)
# Placements S-Boot could use for a recovery boot. Only the normal-boot kernel/initrd placement is measured
# (NAT-005: kernel code at 0x800f0000, initrd at 0x85100000); the DTB address is not.
SCENARIOS = {
    'measured-initrd': dict(dtb=0x84000000, image=0x80000000, image_end=0x80040000, payload=0x85100000),
    'dtb-after-image': dict(dtb=0x80200000, image=0x80000000, image_end=0x80040000, payload=0x85100000),
    'dtb-high-low-bank': dict(dtb=0xB0000000, image=0x80000000, image_end=0x80040000, payload=0x85100000),
}


def extract(loader_c: Path) -> str:
    text = loader_c.read_text()
    start = text.index('#define MAX_RANGES')
    end = text.index('uint64_t loader_main(')
    chunk = text[start:end]
    for name in ('ranges_sort', 'consider_gap', 'loader_reserved_size', 'choose_window'):
        if not re.search(rf'\n{name}\(', chunk):
            raise RuntimeError(f'{name} not found in the extracted range')
    return chunk


def overlaps(a, b):
    return a[0] < b[0] + b[1] and b[0] < a[0] + a[1]


def judge(result):
    win = (int(result['window']['base'], 16), int(result['window']['size'], 16))
    mem = [(int(a, 16), int(s, 16)) for a, s in result['memory']]
    rsv = [(int(a, 16), int(s, 16)) for a, s in result['reserved']]
    inside = any(m[0] <= win[0] and win[0] + win[1] <= m[0] + m[1] for m in mem)
    hits = [f'{a:#x}+{s:#x}' for a, s in rsv if s and overlaps(win, (a, s))]
    fb = result['framebuffer']
    fb_range = (int(fb['base'], 16), int(fb['size'], 16)) if fb['found'] else None
    fb_ok = fb_range is None or (any(m[0] <= fb_range[0] and sum(fb_range) <= m[0] + m[1] for m in mem)
                                 and not any(s and overlaps(fb_range, (a, s)) for a, s in rsv))
    bad = [overlaps(win, FB_MEASURED), overlaps(win, SEC_DEBUG_NEXT), bool(fb_range and overlaps(win, fb_range))]
    return dict(inside_one_memory_range=inside, overlapping_reservations=hits,
                overlaps_boot_framebuffer=bad[0], overlaps_sec_debug_next=bad[1], overlaps_selected_framebuffer=bad[2],
                framebuffer_matches_measured=fb_range == FB_MEASURED if fb_range else None,
                framebuffer_in_memory_and_unreserved=fb_ok,
                ok=inside and not hits and not any(bad) and fb_ok)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--loader-source', type=Path, required=True)
    p.add_argument('--dtb', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    chunk = extract(a.loader_source / 'loader.c')
    (a.out / 'window_extract.inc').write_text(chunk)
    exe = a.out / 'window_harness'
    argv = [CLANG, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-fsanitize=undefined', '-fno-sanitize-recover=all',  # ASan's shadow occupies the 2-4 GiB DTB addresses
            *(['-DHAVE_SELECT_FB'] if '\nloader_select_fb(' in chunk else []),
            '-I', str(a.loader_source), '-I', str(a.out), str(HERE / 'window_harness.c'), str(a.loader_source / 'fdt.c'), '-o', str(exe)]
    build = subprocess.run(argv, capture_output=True, text=True)
    report = dict(schema_version=1, loader_source=str(a.loader_source), dtb_sha256=hashlib.sha256(a.dtb.read_bytes()).hexdigest(),
                  extract_sha256=hashlib.sha256(chunk.encode()).hexdigest(),
                  fdt_c_sha256=hashlib.sha256((a.loader_source / 'fdt.c').read_bytes()).hexdigest(),
                  build=dict(argv=argv, exit_code=build.returncode, stderr=build.stderr[-2000:]), scenarios={})
    if build.returncode == 0:
        for name, s in SCENARIOS.items():
            run = subprocess.run([str(exe), str(a.dtb), *(hex(s[k]) for k in ('dtb', 'image', 'image_end', 'payload'))],
                                 capture_output=True, text=True, env={'ASAN_OPTIONS': 'detect_leaks=0'})
            entry = dict(placement={k: hex(v) for k, v in s.items()}, exit_code=run.returncode, stderr=run.stderr[-1000:])
            if run.returncode == 0:
                entry['result'] = json.loads(run.stdout)
                if entry['result']['window']['found']:
                    entry['judgement'] = judge(entry['result'])
            report['scenarios'][name] = entry
    (a.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    summary = {k: dict(exit=v['exit_code'], fb=v.get('result', {}).get('framebuffer', {}).get('found'),
                       window=v.get('result', {}).get('window'), ok=v.get('judgement', {}).get('ok'),
                       hits=v.get('judgement', {}).get('overlapping_reservations')) for k, v in report['scenarios'].items()}
    print(json.dumps(dict(build=build.returncode, scenarios=summary), indent=1))
    return 0 if build.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
