#!/usr/bin/env python3
"""NAT-022: decode band markers from a phone-camera video of the screen.

Host-side analysis of an observation (the owner's recording); it infers nothing
about the phone beyond what a CRC-valid frame shows. Per sampled video frame:
  1. take the luminance profile down the screen (median over a column strip that
     avoids the camera cut-out) and find the sub-pixel bright/dark transitions;
  2. fit a camera model to them: transition k sits at
         y = y0 + u*K/(1 + q*K)  (+ bloom correction)
     with K the integer band boundary index (K = 0 is the top of band 0, the first
     bright bar). u (band height in pixels), q (perspective) and the bloom width are
     free; the row stride of the framebuffer is not assumed. The model that puts
     every transition closest to an integer K wins;
  3. read the 34 bands from the K-labelled transitions (rising edge: bright until the
     next edge) and accept the 32 payload bits only if sync (band 0 bright, band 1
     dark) and the CRC-8 of decode.parse_frame hold.
Frames that fail any step are reported as such, never guessed.

usage: decode_video.py VIDEO --out RESULT.json [--step N]
"""
from __future__ import annotations
import argparse, importlib.util, json
from collections import Counter
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("decode", HERE / "decode.py")
dec = importlib.util.module_from_spec(spec); spec.loader.exec_module(dec)
BANDS = dec.BANDS


def transitions(gray, x0, x1, y0, y1):
    """Sub-pixel transitions of the strip profile: [(y, +1 rising dark->bright | -1 falling)]."""
    p = np.median(gray[:, x0:x1], axis=1).astype(float)
    pp = p[y0:y1]
    lo, hi = np.percentile(pp, 5), np.percentile(pp, 95)
    if hi - lo < 60:
        return None, (lo, hi)
    thr = (lo + hi) / 2
    out = []
    for y in range(y0 + 1, y1):
        a, b = p[y - 1], p[y]
        if (a > thr) != (b > thr):
            out.append((y - 1 + (thr - a) / (b - a), 1 if b > thr else -1))
    return out, (lo, hi)


def fit_grid(ed, cfg):
    """Best (u, q, bloom) and integer boundary indices K for the transitions ed."""
    ys = np.array([e[0] for e in ed]); sg = np.array([e[1] for e in ed])
    best = None
    for bloom in cfg["blooms"]:
        yc = ys + sg * bloom / 2.0            # rising edge is early, falling edge late, when white blooms
        for q in cfg["qs"]:
            for u in np.arange(cfg["umin"], cfg["umax"], cfg["ustep"]):
                # invert y = yc[0] + u K / (1 + q K): K = d / (u - q d)
                d = yc - yc[0]
                den = u - q * d
                if np.any(den <= 0):
                    continue
                Kf = d / den
                K = np.round(Kf)
                res = (Kf - K) * u
                if np.any(np.diff(K) <= 0) or K[-1] >= BANDS + 1:
                    continue
                sc = float(np.sqrt(np.mean(res ** 2)))
                if best is None or sc < best[0]:
                    best = (sc, float(u), float(q), float(bloom), K.astype(int), float(np.abs(res).max()))
    return best


def bits_from_edges(K, sg):
    """Band states from the labelled edges; None if the first edge is not a rising edge at K=0."""
    if sg[0] != 1 or K[0] != 0:
        return None
    lv = [0.0] * BANDS
    for i in range(len(K)):
        s = 1.0 if sg[i] == 1 else 0.0
        end = K[i + 1] if i + 1 < len(K) else BANDS
        for b in range(K[i], min(end, BANDS)):
            lv[b] = s
    return lv


def analyse(gray, cfg):
    ed, (lo, hi) = transitions(gray, cfg["x0"], cfg["x1"], cfg["y0"], cfg["y1"])
    if ed is None:
        return {"status": "no-contrast"}
    # drop transitions before the first rising edge (logo, status bar remnants)
    while ed and ed[0][1] != 1:
        ed = ed[1:]
    if len(ed) < 4:
        return {"status": "too-few-edges", "edges": len(ed)}
    # edges beyond the 34-band extent cannot be told from clutter below the pattern: fit the
    # leading run only, nearest-integer residual keeps it honest
    best = fit_grid(ed, cfg)
    if best is None:
        return {"status": "no-grid", "edges": len(ed)}
    sc, u, q, bloom, K, mx = best
    out = {"status": "grid", "rms_px": round(sc, 2), "max_px": round(mx, 1), "u": round(u, 2), "q": round(q, 5),
           "bloom": bloom, "edges": len(ed), "K": K.tolist(), "top": round(ed[0][0], 1)}
    if sc > cfg["max_rms"]:
        out["status"] = "grid-poor"
        return out
    lv = bits_from_edges(K, [e[1] for e in ed])
    if lv is None:
        out["status"] = "no-sync"
        return out
    out["bits"] = "".join("1" if v > 0.5 else "0" for v in lv)
    frame = dec.decode_bands(lv)
    if frame is None:
        out["status"] = "sync-or-crc-fail"
    else:
        out["status"] = "ok"; out["frame"] = frame
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--x0", type=int, default=230); ap.add_argument("--x1", type=int, default=360)
    ap.add_argument("--y0", type=int, default=60); ap.add_argument("--y1", type=int, default=1100)
    ap.add_argument("--max-rms", type=float, default=3.0)
    ap.add_argument("--umin", type=float, default=21.0); ap.add_argument("--umax", type=float, default=29.0)
    ap.add_argument("--t0", type=float, default=0.0, help="first second to analyse")
    ap.add_argument("--t1", type=float, default=1e9, help="last second to analyse")
    a = ap.parse_args(argv)
    import cv2
    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cfg = dict(x0=a.x0, x1=a.x1, y0=a.y0, y1=a.y1, umin=a.umin, umax=a.umax, ustep=0.05,
               qs=[x for x in np.arange(-0.012, 0.0121, 0.001)],
               blooms=[0.0, 1.0, 2.0, 3.0, 4.0], max_rms=a.max_rms)
    rows, i = [], int(a.t0 * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    while i / fps <= a.t1:
        ok, bgr = cap.read()
        if not ok: break
        if i % a.step == 0:
            r = analyse(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cfg)
            r["t"] = round(i / fps, 3); r["i"] = i
            rows.append(r)
        i += 1
    cfg2 = {k: (v if not isinstance(v, list) else f"{len(v)} values") for k, v in cfg.items()}
    a.out.write_text(json.dumps({"video": a.video, "fps": fps, "frames_read": i, "cfg": cfg2, "rows": rows}, indent=1))
    print(Counter(r["status"] for r in rows))


if __name__ == "__main__":
    main()
