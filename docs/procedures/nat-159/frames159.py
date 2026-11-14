#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-159: MiniIOMobileFramebuffer's 5 s statistics lines from a kernel text dump (nat-097 kl_reader2 output), one rule for NAT-153
(scH, bilinear) and NAT-159 (scJ, fb_filter=0). Kernel counts, not a camera.

A window is steady when it spans 4500-5600 ms and has at least 10 frames, and when it comes after the recording ended
("recording finished") if the run recorded; record() costs the driver time while it records.

  python3 -B docs/procedures/nat-159/frames159.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import statistics
import sys

LINE = re.compile(r'\[\s*([0-9.]+)\]: MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\), (\d+) us each in the driver, '
                  r'after (\d+) us waiting for the GPU and, (\d+) of them, (\d+) us for the next refresh; (\d+) swaps waited for the frame '
                  r'before, (\d+) gave up; (\d+) swaps came a refresh late themselves')
REC_END = re.compile(r'\[\s*([0-9.]+)\]: MiniIOMobileFramebuffer: recording finished')
REC_BEGIN = re.compile(r'MiniIOMobileFramebuffer: recording \d+ s of the screen')


def stamp(s):
    """kl_reader2 prints the fraction without zero padding in some lines (e.g. 290.1000893); the seconds part is what is compared."""
    return float(s.split('.')[0])


def parse(text):
    wins = [dict(t=stamp(m.group(1)), frames=int(m.group(2)), ms=int(m.group(3)), driver_us=int(m.group(5)), gpu_us=int(m.group(6)),
                 refresh_waits=int(m.group(7)), refresh_us=int(m.group(8)), late=int(m.group(11))) for m in LINE.finditer(text)]
    ends = [stamp(m.group(1)) for m in REC_END.finditer(text)]
    recorded = bool(REC_BEGIN.search(text))
    return wins, recorded, (ends[0] if ends else None)


def summarize(text):
    wins, recorded, rec_end = parse(text)
    steady = [w for w in wins if 4500 <= w['ms'] <= 5600 and w['frames'] >= 10
              and (not recorded or (rec_end is not None and w['t'] > rec_end))]
    out = dict(windows=len(wins), recorded=recorded, recording_end_s=rec_end, steady_windows=len(steady))
    if steady:
        fps = [w['frames'] * 1000.0 / w['ms'] for w in steady]
        out.update(first_steady_s=steady[0]['t'], last_steady_s=steady[-1]['t'],
                   driver_ms_median=statistics.median(w['driver_us'] for w in steady) / 1000.0,
                   driver_ms_min=min(w['driver_us'] for w in steady) / 1000.0,
                   driver_ms_max=max(w['driver_us'] for w in steady) / 1000.0,
                   fps_median=round(statistics.median(fps), 2), fps_min=round(min(fps), 2), fps_max=round(max(fps), 2),
                   frame_interval_ms_median=round(1000.0 / statistics.median(fps), 1),
                   gpu_wait_us_max=max(w['gpu_us'] for w in steady), late_swaps=sum(w['late'] for w in steady))
        # what is left of a frame's interval once the driver's own time is taken out: rendering and everything else on the core
        out['other_ms_median'] = round(out['frame_interval_ms_median'] - out['driver_ms_median'], 1)
    return out, steady


def main():
    text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    out, steady = summarize(text)
    out['steady'] = steady
    s = json.dumps(out, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'steady'}))


if __name__ == '__main__':
    main()
