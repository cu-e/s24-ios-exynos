#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-177: decode scS's read-only display-layer snapshot (`e1s-dpp:` lines of e1s_display.patch) from a kernel text dump.
Field meanings, Samsung e1s kernel 417484173abc (NAT-162 README):
  wincon +0x0   DECON_CON_WIN: bit 0 enable, bits 7:4 CHMAP = the DPP channel feeding the window (cal_rt/regs-decon.h:704-709)
  win +0xC/+0x10 start/end position (x 13:0, y 29:16); +0x800.. the shadow copies
  dma +0x08 IN_CTRL_0 (format 13:8), +0x10/+0x14 SRC_WIDTH/HEIGHT, +0x1C IMG_SIZE (h<<16 | w), +0x40 BASEADDR_P0, +0x400.. shadow
  dpp +0x0 id/version, +0x1C CFG_ERR, +0x3C source size, +0x80 SCL_CTRL (bit 0 enable), +0x84 scaled size, +0x88/+0x8C H/V ratio
  sramc +0x10 mode (bit 12 SCL_EN), +0x14 destination position
  sysmmu +0x0 MMU_CTRL (bit 0 enable), +0x8 STATUS, +0x34 VERSION, +0x8000 MMU_CTRL_VM (bit 0), +0x8404 FLPT base
     (drivers/iommu/samsung/samsung-iommu-v9.h:18-46)
  decon +0x4 FRAME_COUNT (read first and last), +0x30 TRIG_CON, +0x50 SHD_REG_UP_REQ, +0x60 DECON_INT_EN, +0x200/+0x204 DATA_PATH_CON

Verdicts (registered in docs/procedures/nat-176/README.md before the run):
  R-none     no e1s-dpp line at all (probe not reached, or e1sdpp=0)
  R-gated    a snapshot was skipped because a display power domain reported off (nothing but the PMU was read)
  R-partial  some of the 12 groups missing from a snapshot that was not skipped
  R-ok       all 12 groups in both snapshots

  python3 -B docs/procedures/nat-176/dpp177.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import sys

GROUPS = ('decon', 'win2', 'win3', 'wincon2', 'wincon3', 'dma0', 'dma1', 'dpp0', 'dpp1', 'sramc0', 'sramc1', 'sysmmu')
LINE = re.compile(r'e1s-dpp: (probe|late) (\w+) (0x[0-9a-f]+)((?: [0-9a-f]+=[0-9a-f]+)+)')
PMU = re.compile(r'e1s-dpp: (probe|late) pmu dpub (0x[0-9a-f]+|0) dpuf0 (0x[0-9a-f]+|0) dpuf1 (0x[0-9a-f]+|0)')
SKIP = re.compile(r'e1s-dpp: (probe|late) skipped')


def parse(text):
    snaps = {'probe': {}, 'late': {}}
    pmu, skipped = {}, set()
    for m in LINE.finditer(text):
        regs = {}
        for p in m.group(4).split():
            o, v = p.split('=')
            regs.setdefault(int(o, 16), []).append(int(v, 16))
        snaps[m.group(1)][m.group(2)] = regs
    for m in PMU.finditer(text):
        pmu[m.group(1)] = dict(dpub=int(m.group(2), 16), dpuf0=int(m.group(3), 16), dpuf1=int(m.group(4), 16))
    for m in SKIP.finditer(text):
        skipped.add(m.group(1))
    return snaps, pmu, skipped


def first(regs, off):
    v = regs.get(off)
    return v[0] if v else None


def decode(s):
    out = {}
    if 'decon' in s:
        fc = s['decon'].get(0x4, [])
        out['decon'] = dict(frame_count=fc, trig_con=hex(first(s['decon'], 0x30) or 0), shd_reg_up_req=hex(first(s['decon'], 0x50) or 0),
                            int_en=hex(first(s['decon'], 0x60) or 0), data_path=[hex(first(s['decon'], 0x200) or 0),
                                                                                 hex(first(s['decon'], 0x204) or 0)])
    for w in (2, 3):
        wc, wn = s.get('wincon%d' % w), s.get('win%d' % w)
        if wc is None:
            continue
        v = first(wc, 0x0)
        d = dict(raw=hex(v), enabled=bool(v & 1), chmap=(v >> 4) & 0xF)
        if wn is not None:
            st, en = first(wn, 0xC), first(wn, 0x10)
            d.update(start=[st & 0x3FFF, (st >> 16) & 0x3FFF], end=[en & 0x3FFF, (en >> 16) & 0x3FFF])
        out['win%d' % w] = d
    for i in (0, 1):
        dm, dp = s.get('dma%d' % i), s.get('dpp%d' % i)
        if dm is not None:
            img = first(dm, 0x1C)
            out['dma%d' % i] = dict(format=(first(dm, 0x8) >> 8) & 0x3F, src=[first(dm, 0x10), first(dm, 0x14)],
                                    img=[img & 0xFFFF, img >> 16], base=hex(first(dm, 0x40)),
                                    shadow_base=hex(first(dm, 0x440)) if first(dm, 0x440) is not None else None)
        if dp is not None:
            src, scl = first(dp, 0x3C), first(dp, 0x84)
            out['dpp%d' % i] = dict(id=hex(first(dp, 0x0)), cfg_err=hex(first(dp, 0x1C)), src=[src & 0xFFFF, src >> 16],
                                    scaler_on=bool(first(dp, 0x80) & 1), scaled=[scl & 0xFFFF, scl >> 16],
                                    ratio=[hex(first(dp, 0x88)), hex(first(dp, 0x8C))])
        sr = s.get('sramc%d' % i)
        if sr is not None:
            out['sramc%d' % i] = dict(mode=hex(first(sr, 0x10)), scl_en=bool((first(sr, 0x10) >> 12) & 1), dst=hex(first(sr, 0x14)))
    if 'sysmmu' in s:
        m = s['sysmmu']
        out['sysmmu'] = dict(ctrl=hex(first(m, 0x0)), status=hex(first(m, 0x8)), version=hex(first(m, 0x34)), ctrl_vm=hex(first(m, 0x8000)),
                             flpt_vm=hex(first(m, 0x8404)),
                             translating=bool(first(m, 0x0) & 1) and bool(first(m, 0x8000) & 1))
    # which layer feeds each enabled window, and whether that channel has a scaler (odd DPP ids, NAT-162 finding 2)
    out['visible'] = [dict(window=w, dpp=out[w]['chmap'], has_scaler=out[w]['chmap'] % 2 == 1)
                      for w in ('win2', 'win3') if w in out and out[w]['enabled']]
    return out


def analyse(text):
    snaps, pmu, skipped = parse(text)
    if not snaps['probe'] and not snaps['late'] and not pmu:
        return dict(verdict='R-none')
    r = dict(pmu=pmu, skipped=sorted(skipped), groups={k: sorted(v) for k, v in snaps.items()})
    if skipped:
        r['verdict'] = 'R-gated'
        return r
    full = all(set(snaps[w]) == set(GROUPS) for w in ('probe', 'late'))
    r['verdict'] = 'R-ok' if full else 'R-partial'
    r['probe'] = decode(snaps['probe'])
    r['late'] = decode(snaps['late'])
    changed = {}
    for g in GROUPS:
        a, b = snaps['probe'].get(g), snaps['late'].get(g)
        if a is None or b is None:
            continue
        diff = {hex(o): [hex(a[o][0]), hex(b[o][0])] for o in a if o in b and a[o][0] != b[o][0] and not (g == 'decon' and o == 0x4)}
        if diff:
            changed[g] = diff
    r['changed_probe_to_late'] = changed
    return r


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(json.dumps(dict(verdict=r['verdict'], visible=r.get('late', {}).get('visible'), sysmmu=r.get('late', {}).get('sysmmu'))))


if __name__ == '__main__':
    main()
