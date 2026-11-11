#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-059: the verdict of one native run of loader-diag-xnu-ckpt4-usb (NAT-059), from what the host received and saw.

    analyze_nat059.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json [--out RUN/analysis.json] [--allow-synthetic]

This is NAT-057's analyze_nat052.py with the changes test_nat059.py pins: this image's name and its 27-entry stop list (the 22 of NAT-052 plus
the C checkpoints 17..21 after arm_vm_init), and the notes' own TTBR0 evidence as extra conditions for a PASS: the stub gave back the
checkpoint-5 table up to checkpoint 16 and ONE other table from checkpoint 17 on (a note's `kttbr0=` is the TTBR0 the stub gives back at that
stop), no note carries the loader's refusal bits (12: TTBR0 not a plausible table base, 14: unexpected state at a C stop).
The archive integrity, T0, boot-id, provenance and USB-log coverage rules are those of docs/procedures/nat-049/analyze_usblog.py, which is
imported and used read-only (NAT-055 owns edits to it). On top of them this reads the stop notes of the image (`CK n=.. arr=.. ...`, written by
docs/procedures/nat-052/decode52.py's contract) from the TEXT records of the one boot of this image:

  PASS       a live archive with one boot of this image, the transport checks of NAT-049 clean (banner, device sequence from 0, no drop,
             nothing unread, both ladder summaries err=0, manifest complete), the notes numbered 1..N without a gap, the last note carrying the
             final bit of the stop list and the announced `HOLD stage=.. code=..` after it, no exception record anywhere;
  EXCEPTION  a note carrying esr/elr/far (the kernel took an early exception) or a loader exception record: the values are the finding;
  PARTIAL    the channel works (a boot of this image with records) but something above is missing: the last note names how far XNU got, and the
             missing next note is the finding (also gaps, drops, no HOLD, a boot without any note);
  FAIL / undetermined   as in NAT-049: no readable record although 1209:0001 enumerated (FAIL); no host observation, a damaged or foreign or
             early archive, a non-live provenance (undetermined; --allow-synthetic labels a verdict simulated-* for host tests only).

A PASS is a statement about the transport and the notes, not about why the kernel stopped where it did. Reads files only; opens no device."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A49 = _load("nat059_nat049_analyze_usblog", PROC / "nat-049" / "analyze_usblog.py")
D52 = _load("nat059_nat052_decode52", PROC / "nat-052" / "decode52.py")

IMAGE = "loader-diag-xnu-ckpt4-usb"
VERDICTS = ("PASS", "PARTIAL", "EXCEPTION", "FAIL")
DEADLINE_S, WDT_S = 60, 83          # NAT-052's defaults (the image's own deadline is in its banner)
STOP_LIST = (1, 2, 3, 4, 5, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)   # `last` of each arrival: 5 assembly stops + 22 C stops
PRE_VM_N = STOP_LIST.index(16) + 1        # the notes n=5..22 are before arm_vm_init (the stub gives back the checkpoint-5 TTBR0); n=23..27 are checkpoints 17..21


def boot_texts(root, boot_name):
    """The TEXT records of one boot, in order (the loader's lines, the CK notes, HOLD, EXCEPTION)."""
    rows, _ = A49.load_boot(Path(root) / "boots" / boot_name)
    return [f["text"] for f in (r["frame"] for r in rows) if f["kind"] == "log" and "dev_seq" in f and f.get("text") is not None]


def transport_problems(b):
    """NAT-049's transport rules for one boot, without its stage-order and fault-image rules (this image's stages are the kernel's)."""
    why = []
    if b["kinds"]["boot"] != 1 or not b["frame_seq_contiguous"]:
        why.append("the boot's frames are not one boot record followed by a contiguous sequence")
    usb = b["usb"] or {}
    if usb.get("vid") != 0x1209 or usb.get("pid") != 1:
        why.append("the boot record does not name the monitor device 1209:0001: %r" % usb)
    banner = b["banner"] or ""
    if not banner.startswith("NAT047 %s deadline_s=" % IMAGE) or not banner.endswith(" fault=0"):
        why.append("the first record is not this image's banner (%r)" % b["banner"])
    if not b["dev_seq_contiguous"] or b["first_dev_seq"] != 0:
        why.append("the device record numbers are not contiguous from 0 (first %r)" % b["first_dev_seq"])
    if b["drop_frames"]:
        why.append("%d drop frame(s): the engine or the collector lost records" % b["drop_frames"])
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
    return why


def note_problems(prog):
    """What is missing from the stop notes for a PASS (empty = complete)."""
    why = []
    stops = prog["stops"]
    if not stops:
        return ["no CK note arrived: nothing is known about the kernel"]
    if stops[0]["n"] != 1:
        why.append("the first note is n=%d, not 1: earlier notes are missing" % stops[0]["n"])
    if prog["gaps"]:
        why.append("the notes skip numbers: %s" % ", ".join("%d->%d" % g for g in prog["gaps"]))
    last = stops[-1]
    if not prog["reached_final"]:
        why.append("the notes end at n=%d (arrival %d, checkpoint %d) before the final stop of the list" % (last["n"], last["arr"], last["last"]))
    elif (last["n"], last["last"]) != (len(STOP_LIST), STOP_LIST[-1]):
        why.append("the final-stop bit is set at n=%d (checkpoint %d) but this image's list has %d stops ending at checkpoint %d" % (
            last["n"], last["last"], len(STOP_LIST), STOP_LIST[-1]))
    wrong = [s["n"] for s in stops if 1 <= s["n"] <= len(STOP_LIST) and s["last"] != STOP_LIST[s["n"] - 1]]
    if wrong:
        why.append("notes whose checkpoint is not the one this image has at that position: n=%s" % ",".join(map(str, wrong)))
    if not prog["held"]:
        why.append("no HOLD record: the final hold was not announced")
    why += ttbr0_problems(stops)
    return why


def ttbr0_problems(stops):
    """What the notes say about the TTBR0 the stub gave back (NAT-059's one change to the resume). Empty = as designed."""
    why = []
    refused = [s for s in stops if s["mask"] & (D52.MASK_BAD_TTBR0 | D52.MASK_BAD_STATE)]
    for s in refused:
        what = "the TTBR0 to give back was not a plausible table base" if s["mask"] & D52.MASK_BAD_TTBR0 else "the C stop arrived in a state the stub does not understand"
        why.append("the loader refused to resume at n=%d (checkpoint %d, mask %s): %s" % (s["n"], s["last"], hex(s["mask"]), what))
    pre = [s for s in stops if 5 <= s["n"] <= PRE_VM_N]
    post = [s for s in stops if s["n"] > PRE_VM_N and s["n"] <= len(STOP_LIST)]
    if pre and len({s["kttbr0"] for s in pre}) != 1:
        why.append("kttbr0 differs between the stops up to checkpoint 16: %s" % ", ".join("n=%d %s" % (s["n"], hex(s["kttbr0"])) for s in pre))
    base = pre[0]["kttbr0"] if pre else None
    if post:
        values = sorted({s["kttbr0"] for s in post})
        if len(values) != 1:
            why.append("kttbr0 differs between the stops after arm_vm_init: %s" % ", ".join("n=%d %s" % (s["n"], hex(s["kttbr0"])) for s in post))
        v = post[0]["kttbr0"]
        if v == base:
            why.append("from checkpoint 17 the stub gave back the checkpoint-5 table (%s), not the one arm_vm_init installed" % hex(v))
        if v == 0 or v & 0xfff or v >> 48:
            why.append("kttbr0 after arm_vm_init is not a table base: %s" % hex(v))
    return why


def analyze(root, events, report, allow_synthetic=False, deadline=DEADLINE_S, wdt=WDT_S):
    """-> the analysis document. `root` is the collector's archive directory, `events` the usb_watch records, `report` the driver's report."""
    out = dict(image=IMAGE, archive=str(root), checks={}, reasons=[], notes=[], t0_unix=None)

    def done(verdict, why):
        out["why"] = why
        if verdict in VERDICTS and out.get("provenance") != A49.LIVE:
            if not allow_synthetic:
                verdict, out["why"] = "undetermined", "provenance %r is not %r: no verdict of its own (%s)" % (out.get("provenance"), A49.LIVE, why)
            else:
                verdict = "simulated-" + verdict
        out["verdict"] = verdict
        return out

    out["expected_boot_id_tail"] = A49.expected_tail(IMAGE)
    when = report.get("reboot_requested_at") if report.get("reboot_sent") else None
    if not when:
        return done("undetermined", "the driver report has no reboot request (reboot_sent is false): there is no T0")
    t0 = A49.ts(when)
    out["t0_unix"] = t0
    arch, err = A49.load_archive(Path(root))
    if arch is None:
        return done("undetermined", err)
    out["provenance"] = arch["attempt"].get("provenance")
    out["capture_errors"] = arch["capture_errors"]
    out["collector"] = (arch["summary"] or {}).get("stats")
    out["manifest"] = None if arch["manifest"] is None else dict(outcome=arch["manifest"].get("outcome"), errors=arch["manifest"].get("errors"),
                                                                 stop=arch["manifest"].get("stop"), bytes_received=arch["manifest"].get("bytes_received"))
    out["integrity_problems"] = arch["problems"]
    view = A49.usb_view(events, t0)
    out["usb"] = view
    started = A49.ts(arch["attempt"]["utc"])
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
        if b["first_received_unix"] - t0 > A49.RECEIVE_WINDOW_S:
            return done("undetermined", "the boot's first record arrived %.0f s after the reboot request, outside the %.0f s window" % (b["first_received_unix"] - t0, A49.RECEIVE_WINDOW_S))
        if view["covers_window"] and view["monitor_appear_dt"] is None:
            return done("undetermined", "the archive holds a boot, but the host USB log (covering %.0f s) never saw 1209:0001 appear: the two disagree" % view["covers_s"])
        prog = D52.progress(boot_texts(root, b["name"]))
        out["progress"] = dict(
            notes=len(prog["stops"]), last_checkpoint=prog["last"], held=prog["held"], hold=prog["hold"], reached_final=prog["reached_final"], gaps=prog["gaps"],
            stops=[dict(n=s["n"], arr=s["arr"], last=s["last"], mask=hex(s["mask"]), mmu_on=s["mmu_on"], sp=hex(s["sp"]), kttbr0=hex(s["kttbr0"]), setups=s["setups"])
                   for s in prog["stops"]])
        why = transport_problems(b)
        if len(mine) > 1:
            why.append("%d boots of this image in the archive (the loader restarted?)" % len(mine))
        if foreign:
            why.append("%d boot(s) of other images in the archive" % len(foreign))
        m = arch["manifest"]
        if m is None:
            why.append("no manifest.json: the collector did not finish (killed?)")
        elif m.get("outcome") != "complete-received-stream" or m.get("errors"):
            why.append("the collector's manifest says %r with %r capture error(s): %s" % (m.get("outcome"), m.get("errors"), ", ".join(arch["capture_errors"])))
        if out["collector"] and out["collector"].get("drops"):
            why.append("the collector counted %d drop(s)" % out["collector"]["drops"])
        exc = prog["exception"]
        loader_exc = b["exception_frames"] or b["exception_texts"] or b["exception_page"]
        if exc is not None or loader_exc:
            out["exception"] = (dict(source="kernel early-exception note", n=exc["n"], arr=exc["arr"], last=exc["last"], esr=hex(exc["esr"]), elr=hex(exc["elr"]), far=hex(exc["far"]))
                                if exc is not None else dict(source="loader exception record", frames=b["exception_frames"], texts=b["exception_texts"], page=b["exception_page"]))
            out["reasons"] = why
            out["checks"] = dict(boot_of_image=True, reasons=len(why))
            return done("EXCEPTION", "one boot of %s: %s (%s); the values are the finding" % (
                IMAGE, "the kernel reported an early exception at stop n=%d (checkpoint %d)" % (exc["n"], exc["last"]) if exc is not None else "the loader's exception handler ran",
                "; ".join(why) if why else "transport otherwise clean"))
        why += note_problems(prog)
        out["reasons"] = why
        out["checks"] = dict(boot_of_image=True, reasons=len(why))
        if not why:
            last = prog["stops"][-1]
            return done("PASS", "one boot of %s: %d records, %d stop notes (n=1..%d, final checkpoint %d), the hold announced, no drop, nothing unread, no exception" % (
                IMAGE, b["records"], len(prog["stops"]), last["n"], last["last"]))
        where = ("the last note is n=%d (arrival %d, checkpoint %d)" % (prog["stops"][-1]["n"], prog["stops"][-1]["arr"], prog["stops"][-1]["last"])) if prog["stops"] else "no note arrived"
        return done("PARTIAL", "the device enumerated and %d records were archived; %s, but: %s" % (b["records"], where, "; ".join(why)))
    if foreign:
        return done("undetermined", "the archive holds %d boot(s) but none has the boot id of %s (tail %s): not evidence about this run" % (
            len(foreign), IMAGE, out["expected_boot_id_tail"]))
    # nothing was archived: the USB log has to carry the verdict
    if not view["start_ok"]:
        return done("undetermined", "no boot in the archive and no usable USB log (%s): no host observation of the window" % ("; ".join(view["notes"]) or "absent"))
    if not view["covers_window"]:
        return done("undetermined", "no boot in the archive, and the USB log covers only %.0f s after the reboot request (< %.0f s)" % (view["covers_s"], A49.COVERAGE_S))
    if view["monitor_appear_dt"] is not None:
        cause = "host-access-denied" if "device-access-denied" in arch["capture_errors"] else None
        out["cause"] = cause
        return done("FAIL", "1209:0001 enumerated at +%.1f s but the archive holds no readable record%s" % (
            view["monitor_appear_dt"], " (the collector could not open the device: permission)" if cause else
            " (capture errors: %s)" % (", ".join(arch["capture_errors"]) or "none")))
    if view["monitor_preexisting"]:
        return done("undetermined", "a 1209:0001 device was already on the bus when the watcher started: an earlier run or a foreign device, not this one")
    ev = A49.loader_ran_evidence(view, deadline, wdt)
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
    ap.add_argument("--out")
    ap.add_argument("--allow-synthetic", action="store_true", help="host tests: label the verdict simulated-* instead of refusing it")
    a = ap.parse_args(argv)
    events, _ = A49.read_jsonl(a.events)
    report = A49.read_json(a.report) or {}
    res = analyze(a.archive, events, report, a.allow_synthetic)
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
