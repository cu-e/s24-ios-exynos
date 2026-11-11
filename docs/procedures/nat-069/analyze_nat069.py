#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-069: the verdict of one native run of loader-diag-xnu-ne2-usb, and a structured reading of the kernel's `e1s-display:` lines.

    analyze_nat069.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json [--out RUN/analysis.json] [--log-out RUN/kernel-log.txt]

Two layers:
  * NAT-065's analyser (NAT-062's verdict on the log chain, plus `root` = what the kernel's own text says about the root device and PID 1) called under this
    image's name (boot id = FNV-1a-64 of the image name). `root.outcome` still separates probe-ran-to-exit, probe-no-console, ... as in NAT-067/068.
  * `display`: the lines printed by the pinned patch 0010-e1s-display.patch (framebuffer report; with e1sdisp>=2 also DECON/window/RDMA/DSIM/DCPHY registers) parsed
    into numbers, and `display.fork`: which of the milestone-4 situations the register values describe (see docs/strategy/2026-11-12-ios-critical-path.md section 3).
    The fork is a reading of register values the kernel printed. It does not say that the panel shows what the CPU writes; that is a separate question.
It reads delivered text and decides nothing about the phone."""
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-ne2-usb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A65 = _load("nat069_nat065_analyze", PROC / "nat-065" / "analyze_nat065.py")
classify_root = A65.classify_root
write_log = A65.write_log
stamp_of = A65.stamp_of
_ANALYZE65 = A65.analyze

# Number formats of the kernel's printf: %#x prints 0 as "0" and everything else as 0x...
H = r"(0x[0-9a-f]+|0)"
RE_FB = re.compile(r"e1s-display: framebuffer (\d+)x(\d+) depth (\d+) stride (\d+) phys " + H + " virt " + H)
RE_FBWORD = re.compile(r"e1s-display: fb\[(\d)\]=" + H)
RE_FBSUM = re.compile(r"e1s-display: framebuffer sample sum " + H + r" over 16 words")
RE_NOFB = re.compile(r"e1s-display: the console has no usable framebuffer")
RE_CANNOT = re.compile(r"e1s-display: cannot map the display registers")
RE_CANNOT_DSIM1 = re.compile(r"e1s-display: cannot map DSIM1")
RE_DECON = re.compile(r"e1s-display: DECON(\d) version " + H + r" frames (\d+) global " + H + r" (run|idle)( idle-status)? opmode " + H)
RE_WIN = re.compile(r"e1s-display: DECON0 win(\d+) con " + H + r" (on|off) start (\d+),(\d+) end (\d+),(\d+) secure " + H)
RE_RDMA = re.compile(r"e1s-display: RDMA(\d) enable " + H + r" (on|off) format (\d+) (\d+)x(\d+) stride (\d+) addr " + H)
RE_DSIM_A = re.compile(r"e1s-display: DSIM(\d) version " + H + " link " + H + " " + H + " " + H + " " + H + " mipi " + H + " dphy " + H + " clk " + H)
RE_DSIM_B = re.compile(r"e1s-display: DSIM(\d) video (\d+) line (\d+) cmdlock (\d+) pll (\d+) stable (\d+) hsclk (\d+) data (\d+) stopclk (\d+) stopdata " + H + r" TE (\d+)")
RE_DCPHY = re.compile(r"e1s-display: DCPHY0 pll " + H + r" lock (\d+) ready (\d+) enable (\d+)")
RE_PHYCON = re.compile(r"e1s-display: DPU_MIPI_PHY_CON " + H)

# What the pipeline function prints when it ran to the end: 4 DECON, >=4 windows, 4 RDMA, 2 DSIM (two lines each) or a DSIM1 mapping failure, DCPHY0, DPU_MIPI_PHY_CON.
N_DECON, N_WIN_MIN, N_RDMA, N_DSIM = 4, 4, 4, 2

FORKS = {
    "no-display-text": "no e1s-display line reached the host: the run did not get to the display probe (or the log chain failed); nothing is known about the display",
    "no-usable-framebuffer": "the kernel console reports no usable framebuffer; the loader's buffer is not available to the kernel",
    "framebuffer-only": "only the framebuffer report is present (e1sdisp=1, or the run ended before the pipeline read); the pipeline is not described",
    "cannot-map": "ml_io_map refused a display window; the pipeline was not read",
    "pipeline-partial": "pipeline lines are present but the set is incomplete (the read stopped, or the text was cut)",
    "pipeline-idle": "no enabled RDMA and no running DECON: the loader left no scan-out running that the registers show; a display driver is needed before any frame can appear (UI-003 ahead of milestone 5)",
    "decon-running-no-enabled-rdma": "a DECON runs but none of the four RDMA channels read is enabled: the scan-out source is something this dump does not cover; the dump window or the channel choice must be revisited before any decision",
    "rdma-reads-framebuffer-decon-idle": "an enabled RDMA points into the loader's framebuffer but no DECON is running and no window is on: the buffer is the source but nothing is displaying it",
    "scans-loader-framebuffer": "an enabled RDMA points into the loader's framebuffer while a DECON runs or a window is on: S-Boot's scan-out can be reused, the milestone-4 copy path is the candidate and UI-003 stays off the critical path (the panel actually showing CPU writes is still to be confirmed)",
    "scans-other-buffer": "an enabled RDMA points outside the loader's framebuffer: the displayed buffer is another one; its address is in display.rdma and must be understood before a frame can be delivered",
}


def _i(s):
    return int(s, 16) if s.startswith("0x") else int(s)


def parse_display(text):
    """Structured reading of the `e1s-display:` lines in `text` (the reconstructed kernel log). Duplicate lines (both dumps carry the same message buffer) collapse by index."""
    out = dict(lines=len(re.findall(r"e1s-display:", text)), framebuffer=None, fb_words=[], fb_sum=None, no_usable_framebuffer=bool(RE_NOFB.search(text)),
               cannot_map=bool(RE_CANNOT.search(text)), cannot_map_dsim1=bool(RE_CANNOT_DSIM1.search(text)),
               decon=[], windows=[], rdma=[], dsim=[], dcphy=None, dpu_mipi_phy_con=None, fork=None, answer=None, read_at_s=None, caveat=None)
    m = RE_FB.search(text)
    if m:
        out["framebuffer"] = dict(width=int(m.group(1)), height=int(m.group(2)), depth=int(m.group(3)), stride=int(m.group(4)), phys=_i(m.group(5)), virt=_i(m.group(6)))
        out["read_at_s"] = stamp_of(text, "e1s-display: framebuffer ")
    words = {}
    for m in RE_FBWORD.finditer(text):
        words[int(m.group(1))] = _i(m.group(2))
    out["fb_words"] = [words[k] for k in sorted(words)]
    m = RE_FBSUM.search(text)
    if m:
        out["fb_sum"] = _i(m.group(1))
    by = {}
    for m in RE_DECON.finditer(text):
        by[int(m.group(1))] = dict(index=int(m.group(1)), version=_i(m.group(2)), frames=int(m.group(3)), global_con=_i(m.group(4)), run=m.group(5) == "run",
                                   idle_status=bool(m.group(6)), opmode=_i(m.group(7)))
    out["decon"] = [by[k] for k in sorted(by)]
    by = {}
    for m in RE_WIN.finditer(text):
        by[int(m.group(1))] = dict(index=int(m.group(1)), con=_i(m.group(2)), on=m.group(3) == "on", start=(int(m.group(4)), int(m.group(5))),
                                   end=(int(m.group(6)), int(m.group(7))), secure=_i(m.group(8)))
    out["windows"] = [by[k] for k in sorted(by)]
    by = {}
    for m in RE_RDMA.finditer(text):
        by[int(m.group(1))] = dict(index=int(m.group(1)), enable=_i(m.group(2)), on=m.group(3) == "on", fmt=int(m.group(4)), width=int(m.group(5)), height=int(m.group(6)),
                                   stride=int(m.group(7)), addr=_i(m.group(8)))
    out["rdma"] = [by[k] for k in sorted(by)]
    by = {}
    for m in RE_DSIM_A.finditer(text):
        by.setdefault(int(m.group(1)), {}).update(index=int(m.group(1)), version=_i(m.group(2)), link=[_i(m.group(k)) for k in (3, 4, 5, 6)], mipi=_i(m.group(7)),
                                                  dphy=_i(m.group(8)), clk=_i(m.group(9)))
    for m in RE_DSIM_B.finditer(text):
        by.setdefault(int(m.group(1)), {}).update(index=int(m.group(1)), video=int(m.group(2)), line=int(m.group(3)), cmdlock=int(m.group(4)), pll=int(m.group(5)),
                                                  stable=int(m.group(6)), hsclk=int(m.group(7)), data=int(m.group(8)), stopclk=int(m.group(9)), stopdata=_i(m.group(10)),
                                                  te=int(m.group(11)))
    out["dsim"] = [by[k] for k in sorted(by)]
    m = RE_DCPHY.search(text)
    if m:
        out["dcphy"] = dict(pll=_i(m.group(1)), lock=int(m.group(2)), ready=int(m.group(3)), enable=int(m.group(4)))
    m = RE_PHYCON.search(text)
    if m:
        out["dpu_mipi_phy_con"] = _i(m.group(1))
    out["fork"] = fork_of(out)
    out["answer"] = FORKS[out["fork"]]
    if out["fork"] in ("scans-loader-framebuffer", "rdma-reads-framebuffer-decon-idle", "scans-other-buffer", "pipeline-idle", "decon-running-no-enabled-rdma"):
        out["caveat"] = ("register values printed by the kernel, read once at one moment of bsd_init; the RDMA/DECON register layout is the one the pinned patch assumes (UI-007 derivation), "
                         "not a Samsung-documented map; whether the panel shows CPU writes to that buffer is not established by this reading")
    return out


def complete(d):
    dsim_ok = len(d["dsim"]) == N_DSIM or (d["cannot_map_dsim1"] and len(d["dsim"]) == 1)
    return (len(d["decon"]) == N_DECON and len(d["windows"]) >= N_WIN_MIN and len(d["rdma"]) == N_RDMA and dsim_ok
            and all("video" in s and "version" in s for s in d["dsim"]) and d["dcphy"] is not None and d["dpu_mipi_phy_con"] is not None)


def fork_of(d):
    fb = d["framebuffer"]
    pipeline_lines = d["decon"] or d["windows"] or d["rdma"] or d["dsim"] or d["dcphy"] or d["dpu_mipi_phy_con"] is not None
    if d["lines"] == 0:
        return "no-display-text"
    if d["no_usable_framebuffer"] and not pipeline_lines:
        return "no-usable-framebuffer"
    if d["cannot_map"]:
        return "cannot-map"
    if not pipeline_lines:
        return "framebuffer-only" if fb else "no-display-text"
    if not complete(d):
        return "pipeline-partial"
    running = any(x["run"] for x in d["decon"]) or any(w["on"] for w in d["windows"])
    on = [r for r in d["rdma"] if r["on"]]
    if not on:
        return "decon-running-no-enabled-rdma" if any(x["run"] for x in d["decon"]) else "pipeline-idle"
    if fb is None:
        return "scans-other-buffer"        # no framebuffer address to compare with: the buffer cannot be shown to be the loader's
    lo, hi = fb["phys"], fb["phys"] + fb["stride"] * fb["height"]
    if any(lo <= r["addr"] < hi for r in on):
        return "scans-loader-framebuffer" if running else "rdma-reads-framebuffer-decon-idle"
    return "scans-other-buffer"


def analyze(root, events, report, allow_synthetic=False, **kw):
    old = A65.IMAGE
    A65.IMAGE = IMAGE
    try:
        out = _ANALYZE65(root, events, report, allow_synthetic, **kw)
    finally:
        A65.IMAGE = old
    kl = out.get("kernel_log")
    texts = (kl or {}).get("texts") or {}
    text = "\n".join(texts[k] for k in sorted(texts)) if texts else ""
    out["display"] = parse_display(text)
    return out


def main(argv=None):
    A65.analyze = analyze              # main() of NAT-065 calls analyze() by module-global name
    try:
        return A65.main(argv)
    finally:
        A65.analyze = _ANALYZE65


if __name__ == "__main__":
    sys.exit(main())
