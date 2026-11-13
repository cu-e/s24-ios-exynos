#!/usr/bin/env python3
"""NAT-144 analyser (rule fixed by NAT-143 before the run): every NAT-142 verdict (nat-141/analyze142.py), plus whether a touch made
iOS do something.

    analyze144.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON --out OUT_JSON

Clocks: the text is two streams, the console (launchd lines with an os_log wall time `1970-01-01 HH:MM:SS.ffffff`, HakiOS `say`
lines without one) and then the kernel ring (`[ seconds]` on each printf line). Each line gets the interval between the last
time before it and the first one after it in its own stream. With no RTC the wall clock runs on the kernel's uptime, so the two
clocks are compared directly with CLOCK_TOL_S of slack. clock_check measures that per run: launchd's `spawned with pid N` (wall time)
against the kernel's first `memorystatus_update(enter): pid N` (kernel time) for every pid in both streams (NAT-142: 53 pairs, all
within -0.02..+0.54 s). It is ok when at least 3 pairs exist and their median offset is within 1 s; otherwise U2 is not given.

ui timeline: `hakios: input: touch detection mode M` lines (backboardd's TouchDetectionMode: 0xff no touches, 0xfe display off /
tap to wake, 0x1 touches reported) and `hakios: unlock: asked, answer 1` (the donor's automatic unlock 10 s after SpringBoard's
start, not a touch). home_at = the first unlock with answer 1.

presses: `e1s-touch: press N: finger F x X y Y` lines (NAT-143 kernel), each with its kernel time.

apps: launchd lines naming `UIKitApplication:<bundle>`; the first line of each bundle gives its time interval. com.apple.Spotlight
is excluded: SpringBoard starts it by itself (NAT-118 to NAT-142, no touch needed).

ui (first match):
  U2-app-launched-after-press          an application other than Spotlight first appears after home_at, and a press made on the
                                       home screen lies at most 20 s before it (CLOCK_TOL_S either way), with clock_check ok.
                                       This is the touch -> UI action evidence.
  U1-app-after-press-clock-unverified  the same, but clock_check failed
  U1-press-on-home-screen              at least one press after home_at, no such application
  U0-no-press-on-home-screen           no press after home_at (or no home screen)
wake: W1-press-then-wake when a mode 0xfe -> 0x1 change follows a press made in mode 0xfe within 5 s, else W0.
frames: recorded frames (pixels.json, `began` + `ns`, kernel ns) whose hash differs from the previous one, within 2 s after a press
on the home screen: reported as a count only. Frames also change without touches, so this is never a verdict.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat143_analyze142', HERE.parent / 'nat-141/analyze142.py')
A142 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A142)

RE_KT = re.compile(r'^\[\s*(\d+(?:\.\d+)?)\]')
RE_MODE = re.compile(r'hakios: input: touch detection mode (0x[0-9a-f]+|0)\b')
RE_UNLOCK = re.compile(r'hakios: unlock: asked, answer (\d+)')
RE_PRESS = re.compile(r'e1s-touch: press (\d+): finger (\d+) x (\d+) y (\d+)')
RE_RELEASE = re.compile(r'e1s-touch: release (\d+): finger (\d+) x (\d+) y (\d+)')
RE_APP = re.compile(r'UIKitApplication:([A-Za-z0-9_.-]+)\[')
AUTO_APPS = {'com.apple.Spotlight'}
APP_AFTER_PRESS_S = 20.0
CLOCK_TOL_S = 2.0
RE_SPAWN = re.compile(r'spawned with pid (\d+)\b')
RE_JETSAM = re.compile(r'^\[\s*(\d+(?:\.\d+)?)\]: memorystatus_update\(enter\): pid (\d+),')
RE_WALL = re.compile(r'1970-01-01 (\d\d):(\d\d):(\d\d(?:\.\d+)?)\b')
WAKE_AFTER_PRESS_S = 5.0
FRAME_AFTER_PRESS_S = 2.0


def _stamp(line, kernel):
    if kernel:
        m = RE_KT.match(line)
        return float(m[1]) if m else None
    m = RE_WALL.search(line)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def clocked(text):
    """-> [(line, t_lo, t_hi, stream)]: within its stream (console before the first kernel line, kernel after), a line lies between
    the last time before it and the first after it (None where there is none)."""
    lines = text.splitlines()
    k0 = next((i for i, l in enumerate(lines) if RE_KT.match(l)), len(lines))
    out = []
    for start, end, kernel in ((0, k0, False), (k0, len(lines), True)):
        seg = lines[start:end]
        stamps = [_stamp(l, kernel) for l in seg]
        lo, last = [], None
        for s in stamps:
            last = s if s is not None else last
            lo.append(last)
        hi, nxt = [None] * len(seg), None
        for i in range(len(seg) - 1, -1, -1):
            nxt = stamps[i] if stamps[i] is not None else nxt
            hi[i] = nxt
        out += [(l, lo[i], hi[i], 'kernel' if kernel else 'console') for i, l in enumerate(seg)]
    return out


def classify(text, pixels):
    out = A142.classify(text, pixels)
    rows = clocked(text)
    modes, unlocks, presses, releases, apps = [], [], [], [], {}
    spawned, jetsam = {}, {}
    for i, (l, lo, hi, _) in enumerate(rows):
        m = RE_SPAWN.search(l)
        if m and lo is not None:
            spawned.setdefault(int(m[1]), lo)
        m = RE_JETSAM.match(l)
        if m:
            jetsam.setdefault(int(m[2]), float(m[1]))
        m = RE_MODE.search(l)
        if m:
            modes.append(dict(line=i + 1, mode=int(m[1], 16) if m[1].startswith('0x') else int(m[1]), t_lo=lo, t_hi=hi))
        m = RE_UNLOCK.search(l)
        if m:
            unlocks.append(dict(line=i + 1, answer=int(m[1]), t_lo=lo, t_hi=hi))
        m = RE_PRESS.search(l)
        if m:
            presses.append(dict(line=i + 1, n=int(m[1]), finger=int(m[2]), x=int(m[3]), y=int(m[4]), t=lo))
        m = RE_RELEASE.search(l)
        if m:
            releases.append(dict(line=i + 1, n=int(m[1]), t=lo))
        m = RE_APP.search(l)
        if m and m[1] not in apps:
            apps[m[1]] = dict(bundle=m[1], line=i + 1, t_lo=lo, t_hi=hi)
    home = next((u for u in unlocks if u['answer'] == 1), None)
    offsets = sorted(spawned[p] - jetsam[p] for p in spawned if p in jetsam)
    median = offsets[len(offsets) // 2] if offsets else None
    clock_ok = len(offsets) >= 3 and abs(median) <= 1.0
    out['clock_check'] = dict(pairs=len(offsets), median_wall_minus_kernel_s=median, ok=clock_ok)
    out['ui_modes'] = modes
    out['unlocks'] = unlocks
    out['home_at'] = home
    out['press_count'] = len(presses)
    out['release_count'] = len(releases)
    on_home = [p for p in presses if home and home['t_lo'] is not None and p['t'] is not None
               and p['t'] >= home['t_lo'] - CLOCK_TOL_S]
    out['presses_on_home'] = len(on_home)
    out['apps'] = list(apps.values())
    hits = []
    for a in apps.values():
        if a['bundle'] in AUTO_APPS or not home or a['line'] < home['line'] or a['t_lo'] is None:
            continue
        before = [p for p in on_home if -CLOCK_TOL_S <= a['t_lo'] - p['t'] <= APP_AFTER_PRESS_S]
        if before:
            hits.append(dict(app=a, press=before[-1]))
    out['app_after_press'] = hits
    out['ui'] = ('U2-app-launched-after-press' if hits and clock_ok else 'U1-app-after-press-clock-unverified' if hits
                 else 'U1-press-on-home-screen' if on_home else 'U0-no-press-on-home-screen')
    wake = 'W0'
    for a, b in zip(modes, modes[1:]):
        if a['mode'] == 0xfe and b['mode'] == 0x1:
            if b['t_lo'] is not None and any(p['t'] is not None and a['t_lo'] is not None and p['t'] >= a['t_lo'] - CLOCK_TOL_S
                                             and -CLOCK_TOL_S <= b['t_lo'] - p['t'] <= WAKE_AFTER_PRESS_S for p in presses):
                wake = 'W1-press-then-wake'
    out['wake'] = wake
    rec = (pixels or {}).get('recording') or {}
    frames = (pixels or {}).get('frames') or []
    changed = []
    if rec.get('state') == 'ok' and 'began' in rec:
        prev = None
        for f in frames:
            t = (rec['began'] + f['ns']) / 1e9
            if prev is not None and f['fnv'] != prev:
                changed.append(t)
            prev = f['fnv']
    near = sum(1 for p in on_home if p['t'] is not None and any(0 <= t - p['t'] <= FRAME_AFTER_PRESS_S for t in changed))
    out['frame_changes'] = len(changed)
    out['home_presses_followed_by_a_frame_change'] = near
    if hits and clock_ok:
        out['physical_input'] = 'ui-action'
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kernel-text', required=True, type=Path)
    ap.add_argument('--pixels', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    r = classify(a.kernel_text.read_text(errors='replace'), json.loads(a.pixels.read_text()))
    a.out.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('window', 'display', 'power', 'touch', 'start', 'events', 'coord_total', 'reader', 'log',
                                         'ui', 'wake', 'press_count', 'presses_on_home', 'physical_input')}))


if __name__ == '__main__':
    main()
