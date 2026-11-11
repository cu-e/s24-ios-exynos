#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-047: decoder for the USB report frames (kind 13, MK_USB) that loader-diag-usbmon draws on the screen in addition to
everything NAT-022 / NAT-044 draw. The screen is only the fallback channel: the primary record is the archive written by the
NAT-041 collector. NAT-022's decode.py is used unchanged for the frame protocol.

  decode47.status(word)        -> the fields of the status word (idx 0)
  decode47.describe47(frames)  -> {"usb": {...}} from the last MK_USB frame of every idx; {} when there is none

Frame idx of kind 13 (markerlib47.c, patch_loader5.py):
  0 status word     1 ladder stop code (-err & 0xffff, 0 = none)   2 op index of the stop (0xffff = not an op)
  3 record count    5 engine bytes written (low 16 bits)
Status word: bit0 engine up, 1 host connected (bus reset seen), 2 configured, 3 nonce set, 4 a CPU exception was taken,
5 the exception happened inside the engine (engine taken out of service), 6 the HSI0 power domain was already on,
bits 8..11 phase, bits 12..15 last completed ladder rung.
Reads frames; it does not know whether the phone drew them."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _base():
    spec = importlib.util.spec_from_file_location("nat022_decode47", HERE.parent / "nat-022" / "decode.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base = _base()
KIND_USB = 13
I_STATUS, I_ERR, I_ERROP, I_NREC, I_WRITTEN = 0, 1, 2, 3, 5
BITS = {0x0001: "up", 0x0002: "connected", 0x0004: "configured", 0x0008: "nonce", 0x0010: "faulted", 0x0020: "poll_faulted",
        0x0040: "pd_was_on"}
PHASES = {0: "idle", 1: "ladder-ro", 2: "ladder-write", 3: "engine-start", 4: "connect-wait", 5: "up", 6: "stopped"}
LAD_ERR_NAMES = {1: "readback", 2: "timeout", 3: "state", 4: "notalive", 5: "cfg", 6: "disabled"}


def status(word):
    d = {name: bool(word & bit) for bit, name in BITS.items()}
    d["phase"] = PHASES.get(word >> 8 & 0xF, "phase%d" % (word >> 8 & 0xF))
    d["rung_done"] = word >> 12 & 0xF
    return d


def stop_code(raw):
    """Frame idx 1 -> (rung, name) of the ladder stop (LAD_ERR(rung, code) = -(rung*16 + code)); (0, 'none') when 0."""
    if raw == 0:
        return (0, "none")
    return (raw // 16, LAD_ERR_NAMES.get(raw % 16, "code%d" % (raw % 16)))


def describe47(frames):
    last = {}
    for f in frames:
        if f["kind"] == KIND_USB:
            last[f["idx"]] = f["data"]
    if not last:
        return {}
    u = {}
    if I_STATUS in last:
        u["status"] = status(last[I_STATUS])
    if I_ERR in last:
        u["stop"] = stop_code(last[I_ERR])
    if I_ERROP in last:
        u["stop_op"] = None if last[I_ERROP] == 0xFFFF else last[I_ERROP]
    if I_NREC in last:
        u["ladder_records"] = last[I_NREC]
    if I_WRITTEN in last:
        u["engine_bytes_written_low16"] = last[I_WRITTEN]
    return {"usb": u}
