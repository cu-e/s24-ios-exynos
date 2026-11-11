#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-049: the verdict of the first native USB-log run (NAT-043), from what the host received and saw, in the wording fixed in
docs/procedures/nat-047/decision-template.md (PASS / PARTIAL / FAIL / undetermined).

    analyze_usblog.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json --image loader-diag-usbmon \\
        [--out RUN/analysis.json] [--allow-synthetic]

Inputs: the collector's archive directory (s24_logd.py, NAT-041; the NAT-016 layout), the NAT-048 USB event log, the session driver's
report.json (the reboot request time T0) and the image name (the boot id of an image ends with the FNV-1a-64 of its name, NAT-047).
Output: one JSON document: the verdict, why, the checks behind it and the numbers the decision text asks for (records, stages, the
ladder report and its stop rung, the exception frame, drops, unread bytes).

Rules that make a PASS hard to get by accident:
  * the archive must say `unqualified-live`; a `synthetic` archive (every simulator archive) never gives a verdict of its own. With
    --allow-synthetic (host tests only) the verdict is returned as `simulated-PASS` etc., never as `PASS`;
  * the archive must have been created before the reboot request (the collector was running first) and its boot must have arrived
    after it; the boot id must be that of this image (a boot of another image, an old archive or a foreign device is not evidence);
  * the archive must pass its own integrity checks: the manifest hashes, the chunk index against received.bin, every payload.bin
    against the frames it was written for. A corrupted archive is `undetermined`, never a partial result;
  * PASS needs one boot of this image, the banner first, the device sequence contiguous from 0, no drop, no unread bytes at the
    end, the stage records in order, both ladder summaries with err=0 and one line per hardware access, no collector error, and
    for the fault image exactly one exception frame with ESR 0xF2001234.
Nothing is inferred from missing data; an absent or too short USB log is `undetermined` unless the archive itself is conclusive.
This is the host's observation: it does not say why the phone behaved as it did, and a PASS is not evidence about anything but
the transport."""
import argparse
import base64
import datetime
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AR = _load("nat048_analyze_reset_for_049", HERE.parent / "nat-048" / "analyze_reset.py")

IMAGES = {"loader-diag-usbmon": 0, "loader-diag-usbmon-fault": 1}          # image -> the NAT047_FAULT it was built with
FAULT_ESR = 0xF2001234                                                      # EC 0x3c (BRK, AArch64), ISS 0x1234
MONITOR_VID, MONITOR_PID = "1209", "0001"
COVERAGE_S = 120.0              # the USB log must reach this far past T0 to support a statement about an absence
RECEIVE_WINDOW_S = 300.0        # the first record of the boot must arrive within this long after T0
BOOT_DIR = re.compile(r"^(\d{6})-([0-9a-f]{32})-([0-9a-f]{32})$")
LADDER = re.compile(r"^LAD ([RW]) err=(-?\d+) err_op=(-?\d+) rung=(-?\d+) pd_was_on=(-?\d+) nrec=(\d+) soft=(\d+) gsnpsid=(0x[0-9a-f]+)$")
STAGE_ORDER = (0x20, 0x21, 0x30, 0x31, 0x32, 0x33, 0x34, 0x40)
STAGE_EXC = 0x1F                # MK_ST_EXC: the stage record of a CPU exception, last in the fault image
LIVE = "unqualified-live"
VERDICTS = ("PASS", "PARTIAL", "FAIL")


def fnv1a64(text):
    h = 0xCBF29CE484222325
    for c in text.encode():
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def expected_tail(image):
    """The last 8 bytes of the device boot id of `image`, as hex (NAT-047 nat047_bringup)."""
    return fnv1a64(image).to_bytes(8, "little").hex()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    rows, bad = [], 0
    try:
        text = Path(path).read_text()
    except OSError:
        return rows, bad
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return rows, bad


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def ts(s):
    return datetime.datetime.fromisoformat(s).timestamp()


# ---------------------------------------------------------------------------------------------------------------- the archive
def integrity(root, manifest):
    """Problems found when the archive is compared with the hashes it recorded about itself. [] = consistent."""
    problems = []
    actual = {str(p.relative_to(root)): p for p in root.rglob("*") if p.is_file()}
    if manifest is not None:
        listed = manifest.get("sha256") or {}
        for rel, h in listed.items():
            p = actual.get(rel)
            if p is None:
                problems.append("manifest lists %s but the file is missing" % rel)
            elif sha256_file(p) != h:
                problems.append("hash mismatch: %s" % rel)
        for rel in actual:
            if rel not in listed and rel != "manifest.json":
                problems.append("file not in the manifest: %s" % rel)
    raw = actual.get("received.bin")
    data = raw.read_bytes() if raw else b""
    chunks, bad = read_jsonl(root / "chunks.jsonl")
    if bad:
        problems.append("chunks.jsonl has %d unreadable lines" % bad)
    pos = 0
    for c in chunks:
        piece = data[c["offset"]:c["offset"] + c["length"]]
        if c["offset"] != pos:
            problems.append("chunk index: offset %d where %d was expected" % (c["offset"], pos))
        if len(piece) != c["length"] or hashlib.sha256(piece).hexdigest() != c["sha256"]:
            problems.append("chunk at offset %d does not match received.bin" % c["offset"])
        pos = c["offset"] + c["length"]
    if pos != len(data):
        problems.append("received.bin has %d bytes, the chunk index covers %d" % (len(data), pos))
    return problems


def load_boot(folder):
    rows, bad = read_jsonl(folder / "frames.jsonl")
    problems = ["%s: %d unreadable frame lines" % (folder.name, bad)] if bad else []
    try:
        payload = (folder / "payload.bin").read_bytes()
    except OSError:
        payload, problems = b"", problems + ["%s: payload.bin missing" % folder.name]
    try:
        joined = b"".join(base64.b64decode(r["frame"].get("data_b64", ""), validate=True) for r in rows)
    except (ValueError, KeyError, TypeError):
        joined = None
    if joined != payload:
        problems.append("%s: payload.bin is not the concatenation of the frames' data" % folder.name)
    return rows, problems


def decode_json_frame(frame):
    try:
        return json.loads(base64.b64decode(frame.get("data_b64", ""), validate=True))
    except (ValueError, TypeError):
        return None


def summarize_boot(name, rows):
    """What one boot of the archive holds (numbers and flags only; judgement is in analyze())."""
    frames = [r["frame"] for r in rows]
    m = BOOT_DIR.match(name)
    s = dict(name=name, boot_id=frames[0].get("boot_id") if frames else None, device_id=m.group(3) if m else None,
             index=int(m.group(1)) if m else None, frames=len(frames))
    s["kinds"] = {k: sum(1 for f in frames if f["kind"] == k) for k in ("boot", "log", "stage", "fault", "drop", "end")}
    recs = [f for f in frames if f["kind"] in ("log", "stage", "fault") and "dev_seq" in f]       # the ring's records
    seqs = [f.get("dev_seq") for f in recs]
    s["records"] = len(recs)
    s["first_dev_seq"] = seqs[0] if seqs else None
    s["dev_seq_contiguous"] = bool(seqs) and seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    s["frame_seq_contiguous"] = [f["seq"] for f in frames] == list(range(len(frames)))
    s["first_received_unix"] = ts(rows[0]["received"]["utc"]) if rows else None
    s["last_received_unix"] = ts(rows[-1]["received"]["utc"]) if rows else None
    s["banner"] = recs[0].get("text") if recs else None
    s["stages"] = [(f["stage"], f.get("text")) for f in recs if f["kind"] == "stage" and "stage" in f]
    ladder, lr = {}, {"R": 0, "W": 0}
    for f in recs:
        t = f.get("text") or ""
        mm = LADDER.match(t)
        if mm:
            tag = mm.group(1)
            ladder[tag] = dict(err=int(mm.group(2)), err_op=int(mm.group(3)), rung=int(mm.group(4)), pd_was_on=int(mm.group(5)),
                               nrec=int(mm.group(6)), soft=int(mm.group(7)), gsnpsid=mm.group(8))
        elif t.startswith("LR ") and t[3:4] in lr:
            lr[t[3]] += 1
    s["ladder"], s["ladder_op_lines"] = ladder, lr
    s["hold"] = next((f["text"] for f in recs if (f.get("text") or "").startswith("HOLD stage=")), None)
    s["exception_frames"] = [dict(esr=f.get("esr"), elr=f.get("elr"), far=f.get("far"), stage=f.get("stage")) for f in recs if f["kind"] == "fault"]
    s["exception_page"] = [dict(esr=f.get("esr"), elr=f.get("elr"), far=f.get("far"), valid=f.get("valid"), spsr=f.get("spsr"), sp=f.get("sp"))
                           for f in frames if f["kind"] == "fault" and f.get("source") == "get_exc"]       # the engine's exception page, read by GET_EXC
    s["exception_texts"] = [f["text"] for f in recs if (f.get("text") or "").startswith("EXCEPTION slot=")]
    s["drop_frames"] = s["kinds"]["drop"]
    end = next((decode_json_frame(f) for f in frames if f["kind"] == "end"), None)
    s["end"] = None if end is None else dict(reason=end.get("reason"), unread_bytes=end.get("unread_bytes"), next_offset=end.get("next_offset"),
                                             engine_written=(end.get("last_info") or {}).get("written"))
    bootj = decode_json_frame(frames[0]) if frames and frames[0]["kind"] == "boot" else None
    s["usb"] = (bootj or {}).get("usb")
    return s


def load_archive(root):
    """-> (dict, None) or (None, reason). Never raises on a damaged archive."""
    attempt = read_json(root / "attempt.json")
    if not isinstance(attempt, dict) or attempt.get("schema") != "early-log-archive-v1":
        return None, "no readable attempt.json in %s (the collector never started, or this is not its archive)" % root
    a = dict(root=root, attempt=attempt, manifest=read_json(root / "manifest.json"), summary=read_json(root / "collector-summary.json"))
    events, bad = read_jsonl(root / "events.jsonl")
    a["events"] = events
    a["capture_errors"] = [e.get("reason") for e in events if e.get("kind") == "capture-error"]
    a["problems"] = integrity(root, a["manifest"]) + (["events.jsonl has %d unreadable lines" % bad] if bad else [])
    a["boots"] = []
    boots = root / "boots"
    for folder in sorted(boots.iterdir()) if boots.is_dir() else []:
        rows, probs = load_boot(folder)
        a["problems"] += probs
        try:
            a["boots"].append(summarize_boot(folder.name, rows))
        except (KeyError, TypeError, ValueError) as e:
            a["problems"].append("%s: unreadable frames (%s)" % (folder.name, e))
    return a, None


# ---------------------------------------------------------------------------------------------------------------- the USB log
def usb_view(events, t0):
    v = dict(has_log=bool(events), start_ok=False, covers_s=None, covers_window=False, monitor_appear_dt=None, monitor_preexisting=False,
             phone_left_dt=None, first_return=None, notes=[])
    starts = [e for e in events if e.get("event") == "start"]
    if not starts:
        return v
    if starts[0]["t_unix"] > t0:
        v["notes"].append("the watcher started %.1f s after the reboot request" % (starts[0]["t_unix"] - t0))
        return v
    v["start_ok"] = True
    stops = [e for e in events if e.get("event") == "stop"]
    end = (stops[-1] if stops else max(events, key=lambda e: e["t_unix"]))["t_unix"] - t0
    v["covers_s"] = round(end, 2)
    v["covers_window"] = end >= COVERAGE_S
    if not stops:
        v["notes"].append("the log has no stop record: the watcher died or was killed")
    is_mon = lambda e: e.get("vid") == MONITOR_VID and e.get("pid") == MONITOR_PID   # noqa: E731
    v["monitor_preexisting"] = any(is_mon(d) for d in (starts[0].get("initial") or []))
    mon = next((e for e in events if e.get("event") == "appear" and is_mon(e) and e["t_unix"] >= t0), None)
    if mon:
        v["monitor_appear_dt"] = round(mon["t_unix"] - t0, 2)
    sam = [e for e in events if e.get("event") in ("appear", "disappear") and e.get("vid") == AR.SAMSUNG and e["t_unix"] >= t0]
    leave = next((e for e in sam if e["event"] == "disappear"), None)
    if leave:
        v["phone_left_dt"] = round(leave["t_unix"] - t0, 2)
        back = next((e for e in sam if e["event"] == "appear" and e["t_unix"] > leave["t_unix"]), None)
        if back:
            v["first_return"] = dict(dt=round(back["t_unix"] - t0, 2), klass=AR.classify(back), id="%s:%s" % (back["vid"], back["pid"]),
                                     product=back.get("product"))
    return v


def loader_ran_evidence(view, deadline, wdt):
    """The only thing the USB log can say about the loader running: the phone came back like the reset at the deadline or like the
    watchdog of runs 001-009 (not early, not as Android)."""
    r = view["first_return"]
    if not r or r["klass"] not in ("download", "upload"):
        return None
    ceiling = AR.BASELINE_UPLOAD_S - (wdt - deadline) / 2.0
    if deadline <= r["dt"] <= ceiling:
        return "returned as %s at +%.1f s: the reset at the %d s deadline" % (r["klass"], r["dt"], deadline)
    if r["klass"] == "upload" and abs(r["dt"] - AR.BASELINE_UPLOAD_S) <= AR.BASELINE_TOLERANCE_S:
        return "returned as upload at +%.1f s: the watchdog of runs 001-009 (no reset at the deadline)" % r["dt"]
    return None


# ---------------------------------------------------------------------------------------------------------------------- verdict
def _stage_problems(stages, fault):
    nums = [n for n, _ in stages]
    body = [n for n in nums if n != STAGE_EXC]
    if not body:
        return ["no stage record"]
    out = []
    if body[0] != STAGE_ORDER[0]:
        out.append("the first stage record is 0x%x, not 0x%x (loader_main)" % (body[0], STAGE_ORDER[0]))
    if any(b < a for a, b in zip(body, body[1:])):
        out.append("stage records out of order: %s" % " ".join("0x%x" % n for n in nums))
    if fault and STAGE_EXC in nums and [i for i, n in enumerate(nums) if n == STAGE_EXC] != [len(nums) - 1]:
        out.append("the exception stage is not the single last stage record")
    return out


def judge_boot(b, image, fault):
    """Reasons why the boot is not a PASS (empty = PASS), in the template's terms."""
    why = []
    if b["kinds"]["boot"] != 1 or not b["frame_seq_contiguous"]:
        why.append("the boot's frames are not one boot record followed by a contiguous sequence")
    usb = b["usb"] or {}
    if usb.get("vid") != 0x1209 or usb.get("pid") != 1:
        why.append("the boot record does not name the monitor device 1209:0001: %r" % usb)
    want_banner = "NAT047 %s deadline_s=" % image
    if not (b["banner"] or "").startswith(want_banner) or not (b["banner"] or "").endswith(" fault=%d" % fault):
        why.append("the first record is not this image's banner (%r)" % b["banner"])
    if not b["dev_seq_contiguous"] or b["first_dev_seq"] != 0:
        why.append("the device record numbers are not contiguous from 0 (first %r)" % b["first_dev_seq"])
    if b["drop_frames"]:
        why.append("%d drop frame(s): the engine or the collector lost records" % b["drop_frames"])
    why += _stage_problems(b["stages"], fault)
    for tag, name in (("R", "read-only"), ("W", "writing")):
        lad = b["ladder"].get(tag)
        if lad is None:
            why.append("no %s ladder summary" % name)
        elif lad["err"] != 0:
            why.append("the %s ladder stopped: err=%d at rung %d, op %d" % (name, lad["err"], lad["rung"], lad["err_op"]))
        elif b["ladder_op_lines"][tag] != lad["nrec"]:
            why.append("the %s ladder reports %d accesses but %d lines arrived" % (name, lad["nrec"], b["ladder_op_lines"][tag]))
    end = b["end"]
    if end is None:
        why.append("the boot has no end record (the collector stopped before the device went away)")
    elif end["unread_bytes"]:
        why.append("%d engine bytes were written but never read (engine wrote %s, next offset %s)" % (end["unread_bytes"], end["engine_written"], end["next_offset"]))
    efr = b["exception_frames"]
    if fault:
        if len(efr) != 1:
            why.append("%d exception records in the ring, one was expected from the controlled BRK" % len(efr))
        elif efr[0]["esr"] != FAULT_ESR:
            why.append("the exception record has ESR %s, expected 0x%x" % (hex(efr[0]["esr"]) if isinstance(efr[0]["esr"], int) else repr(efr[0]["esr"]), FAULT_ESR))
        if not b["exception_texts"]:
            why.append("no EXCEPTION text record")
        for pg in b["exception_page"]:
            if not pg["valid"] or (len(efr) == 1 and (pg["esr"], pg["elr"], pg["far"]) != (efr[0]["esr"], efr[0]["elr"], efr[0]["far"])):
                why.append("the engine's exception page (GET_EXC) is invalid or disagrees with the ring's exception record")
    elif efr or b["exception_texts"] or b["exception_page"] or STAGE_EXC in [n for n, _ in b["stages"]]:
        why.append("an exception was reported by the image that has no controlled fault")
    return why


def analyze(root, events, report, image, allow_synthetic=False, deadline=45, wdt=83):
    """-> the analysis document. `root` is the collector's archive directory, `events` the usb_watch records, `report` the driver's report."""
    out = dict(image=image, archive=str(root), checks={}, reasons=[], notes=[], t0_unix=None)

    def done(verdict, why):
        out["why"] = why
        if verdict in VERDICTS and out.get("provenance") != LIVE:
            if not allow_synthetic:
                verdict, out["why"] = "undetermined", "provenance %r is not %r: no verdict of its own (%s)" % (out.get("provenance"), LIVE, why)
            else:
                verdict = "simulated-" + verdict
        out["verdict"] = verdict
        return out

    if image not in IMAGES:
        return done("undetermined", "unknown image %r" % image)
    fault = IMAGES[image]
    out["expected_boot_id_tail"] = expected_tail(image)
    when = report.get("reboot_requested_at") if report.get("reboot_sent") else None
    if not when:
        return done("undetermined", "the driver report has no reboot request (reboot_sent is false): there is no T0")
    t0 = ts(when)
    out["t0_unix"] = t0
    arch, err = load_archive(Path(root))
    if arch is None:
        return done("undetermined", err)
    out["provenance"] = arch["attempt"].get("provenance")
    out["capture_errors"] = arch["capture_errors"]
    out["collector"] = (arch["summary"] or {}).get("stats")
    out["manifest"] = None if arch["manifest"] is None else dict(outcome=arch["manifest"].get("outcome"), errors=arch["manifest"].get("errors"),
                                                                 stop=arch["manifest"].get("stop"), bytes_received=arch["manifest"].get("bytes_received"))
    out["integrity_problems"] = arch["problems"]
    view = usb_view(events, t0)
    out["usb"] = view
    started = ts(arch["attempt"]["utc"])
    out["collector_started_before_t0_s"] = round(t0 - started, 3)
    out["boots_in_archive"] = [dict(name=b["name"], device_id=b["device_id"], records=b["records"]) for b in arch["boots"]]
    if arch["problems"]:
        return done("undetermined", "the archive failed its own integrity checks, so none of it can be relied on: " + "; ".join(arch["problems"][:4]))
    if started > t0:
        return done("undetermined", "the collector's archive was created %.1f s after the reboot request: the run did not follow the protocol" % (started - t0))
    mine = [b for b in arch["boots"] if (b["device_id"] or "")[16:] == out["expected_boot_id_tail"]]
    foreign = [b for b in arch["boots"] if b not in mine]
    out["boots_of_image"], out["foreign_boots"] = len(mine), len(foreign)
    if mine:
        b = mine[0]
        out["boot"] = b
        if b["first_received_unix"] < t0:
            return done("undetermined", "the boot's first record arrived %.1f s BEFORE the reboot request: it belongs to an earlier run" % (t0 - b["first_received_unix"]))
        if b["first_received_unix"] - t0 > RECEIVE_WINDOW_S:
            return done("undetermined", "the boot's first record arrived %.0f s after the reboot request, outside the %.0f s window" % (b["first_received_unix"] - t0, RECEIVE_WINDOW_S))
        if view["covers_window"] and view["monitor_appear_dt"] is None:
            return done("undetermined", "the archive holds a boot, but the host USB log (covering %.0f s) never saw 1209:0001 appear: the two disagree" % view["covers_s"])
        why = judge_boot(b, image, fault)
        if len(mine) > 1:
            why.append("%d boots of this image in the archive (the loader restarted?)" % len(mine))
        if foreign:
            why.append("%d boot(s) of other images in the archive" % len(foreign))
        m = arch["manifest"]
        if m is None:
            why.append("no manifest.json: the collector did not finish (killed?)")
        else:
            if m.get("outcome") != "complete-received-stream" or m.get("errors"):
                why.append("the collector's manifest says %r with %r capture error(s): %s" % (m.get("outcome"), m.get("errors"), ", ".join(arch["capture_errors"])))
        if out["collector"] and out["collector"].get("drops"):
            why.append("the collector counted %d drop(s)" % out["collector"]["drops"])
        out["reasons"] = why
        out["checks"] = dict(boot_of_image=True, reasons=len(why))
        if not why:
            return done("PASS", "one boot of %s: %d records, %d stage records, both ladder summaries clean, no drop, nothing unread%s" % (
                image, b["records"], len(b["stages"]), ", the controlled exception frame with ESR 0x%x" % FAULT_ESR if fault else ""))
        return done("PARTIAL", "the device enumerated and %d records were archived, but: %s" % (b["records"], "; ".join(why)))
    if foreign:
        return done("undetermined", "the archive holds %d boot(s) but none has the boot id of %s (tail %s): not evidence about this run" % (
            len(foreign), image, out["expected_boot_id_tail"]))
    # nothing was archived: the USB log has to carry the verdict
    if not view["start_ok"]:
        return done("undetermined", "no boot in the archive and no usable USB log (%s): no host observation of the window" % ("; ".join(view["notes"]) or "absent"))
    if not view["covers_window"]:
        return done("undetermined", "no boot in the archive, and the USB log covers only %.0f s after the reboot request (< %.0f s)" % (view["covers_s"], COVERAGE_S))
    if view["monitor_appear_dt"] is not None:
        cause = "host-access-denied" if "device-access-denied" in arch["capture_errors"] else None
        out["cause"] = cause
        return done("FAIL", "1209:0001 enumerated at +%.1f s but the archive holds no readable record%s" % (
            view["monitor_appear_dt"], " (the collector could not open the device: permission, see the README)" if cause else
            " (capture errors: %s)" % (", ".join(arch["capture_errors"]) or "none")))
    if view["monitor_preexisting"]:
        return done("undetermined", "a 1209:0001 device was already on the bus when the watcher started: an earlier run or a foreign device, not this one")
    ev = loader_ran_evidence(view, deadline, wdt)
    out["loader_ran_evidence"] = ev
    if ev is None:
        return done("undetermined", "no 1209:0001 enumeration and nothing shows that the loader ran (phone left the bus: %s; first return: %s)" % (
            view["phone_left_dt"], view["first_return"]))
    return done("FAIL", "no enumeration of 1209:0001 although the loader ran (%s)" % ev)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--events", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out")
    ap.add_argument("--allow-synthetic", action="store_true", help="host tests: label the verdict simulated-* instead of refusing it")
    a = ap.parse_args(argv)
    events, _ = read_jsonl(a.events)
    report = read_json(a.report) or {}
    res = analyze(a.archive, events, report, a.image, a.allow_synthetic)
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
