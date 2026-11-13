#!/usr/bin/env python3
"""NAT-146 analyser (rule fixed by NAT-145 before the run): every NAT-144 verdict (nat-143/analyze144.py), plus the processors and the
frame rate of the software display path.

    analyze146.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON --out OUT_JSON

cpus:
  registered   distinct `GenericARMCPU: cpu N (phys id 0x...) registered` lines (the ADT cores the platform expert took)
  started      distinct `cpu_start() cpu: N` lines (the boot processor's own counts as one)
  failed       `psci: cpu N ... was not started` / `took an exception on its way in` / `has not joined` lines
  ncpu         the `memory M MB, page size P, K cpu(s)` banner of /redwood/sbin/init (hw.ncpu as user space sees it)
  running      the last count of GenericARMPE's `N of M processors are running` / `the slower cores started too: N processors
               running` (HackiOS iokit/Kernel/GenericARMPE.cpp: the small cores cpu1-3 join small_cores_after=28 s later)
  verdict (first match):
    C2-all-ten   10 started, no failure line, banner says 10, last running count 10
    C1-some      more than one started
    C0-one       one processor only
stop: the `psci: cpu N ends the system ...` / `cannot return ...` / `did not stop` notes of the return path (written straight to the
  loader log by psci_smp_note), listed.
fps: MiniIOMobileFramebuffer's `from one frame to the next` lines report a histogram of the frame intervals since the previous such
line. For each line: frames = the sum of its five counts, window = its kernel time minus the previous line's. rate = frames / window.
  fps_best_window      the highest rate over windows with 0 pauses and at least 20 frames (a sustained stretch, not a burst)
  fps_median_interval  the median of the lines' "half under N ms" over those windows
This is the rate at which frames reached the panel's memory, measured by the kernel; it is not a camera measurement of the panel.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat145_analyze144', HERE.parent / 'nat-143/analyze144.py')
A144 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A144)

RE_REG = re.compile(r'GenericARMCPU: cpu (\d+) \(phys id (0x[0-9a-f]+)\) registered')
RE_START = re.compile(r'cpu_start\(\) cpu: (\d+)')
RE_FAIL = re.compile(r'psci: cpu (\d+) \(MPIDR [0-9a-fx]+\) (was not started|took an exception on its way in|was started \d+ seconds ago '
                     r'and has not joined)')
RE_RUN = re.compile(r'GenericARMPE: (?:(\d+) of \d+ processors are running|the slower cores started too: (\d+) processors running)')
RE_NCPU = re.compile(r'memory \d+ MB, page size \d+, (\d+) cpus?\b')
RE_STOP = re.compile(r'psci: cpu (\d+) (ends the system|cannot return to the boot loader|did not stop)')
RE_FT = re.compile(r'^\[\s*(\d+(?:\.\d+)?)\]: MiniIOMobileFramebuffer: from one frame to the next: (\d+) times under 10 ms, (\d+) under 18, '
                   r'(\d+) under 26, (\d+) under 35, (\d+) longer \(the longest (\d+) ms\); half under (\d+) ms, 95 in 100 under (\d+) ms; '
                   r'(\d+) pauses')
MIN_FRAMES = 20


def frame_windows(text):
    rows, prev = [], None
    for l in text.splitlines():
        m = RE_FT.match(l)
        if not m:
            continue
        t = float(m[1])
        frames = sum(int(m[i]) for i in range(2, 7))
        if prev is not None and t > prev:
            rows.append(dict(t=t, window=round(t - prev, 3), frames=frames, rate=round(frames / (t - prev), 2), longest=int(m[7]),
                             half=int(m[8]), p95=int(m[9]), pauses=int(m[10])))
        prev = t
    return rows


def classify(text, pixels):
    out = A144.classify(text, pixels)
    reg = sorted({int(m[0]) for m in RE_REG.findall(text)})
    started = sorted({int(m) for m in RE_START.findall(text)})
    failed = [dict(cpu=int(m[0]), what=m[1]) for m in RE_FAIL.findall(text)]
    n = RE_NCPU.search(text)
    ncpu = int(n[1]) if n else None
    runs = [int(a or b) for a, b in RE_RUN.findall(text)]
    running = runs[-1] if runs else None
    out['cpus'] = dict(registered=reg, started=started, failed=failed, ncpu=ncpu, running=running,
                       stop_notes=[dict(cpu=int(a), what=b) for a, b in RE_STOP.findall(text)])
    out['smp'] = ('C2-all-ten' if len(started) == 10 and not failed and ncpu == 10 and running == 10 else 'C1-some' if len(started) > 1 else 'C0-one')
    rows = frame_windows(text)
    steady = [r for r in rows if r['pauses'] == 0 and r['frames'] >= MIN_FRAMES]
    out['frame_windows'] = rows
    out['fps_best_window'] = max((r['rate'] for r in steady), default=None)
    halves = sorted(r['half'] for r in steady)
    out['fps_median_interval_ms'] = halves[len(halves) // 2] if halves else None
    out['fps_steady_windows'] = len(steady)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kernel-text', required=True, type=Path)
    ap.add_argument('--pixels', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    r = classify(a.kernel_text.read_text(errors='replace'), json.loads(a.pixels.read_text()))
    a.out.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('window', 'display', 'start', 'events', 'reader', 'ui', 'physical_input', 'smp',
                                         'fps_best_window', 'fps_median_interval_ms', 'fps_steady_windows')}))
    print(json.dumps(r['cpus']))


if __name__ == '__main__':
    main()
