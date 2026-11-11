#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-048: verdicts of the NAT-046 reset canary run from what the host saw, per the wording fixed in
docs/procedures/nat-044/decision-template.md (U1+U2 and U3/U4).

    analyze_reset.py --events RUN/usb-events.jsonl --report RUN/report.json --build artifacts/nat-044/build-002 \\
        --image loader-diag-reset [--out RUN/analysis.json]

Inputs: the usb_watch.py log, the session driver's report.json (reboot_requested_at) and the NAT-044 build record (the image's
reason word, deadline and watchdog seconds). Output: one JSON document with, for each question, `supported`, `refuted` or
`undetermined` and the timestamps it was derived from. Nothing is inferred from missing data: no log, a log that starts after the
reboot request or ends before the window closed, no reboot request, or no device leaving the bus all give `undetermined`.

Baseline (constants, with their source): in runs 001-009 the phone's USB identity vanished about 4 s after the reboot request and
`04e8:685d` with iProduct SEC_UPLOAD appeared about 95 s after it (the loader waited for its 83 s watchdog); see
docs/procedures/nat-022/README.md ("USB vanish at +4 s and SEC_UPLOAD at +95 s", run 001 and later). A loader reset at the
deadline therefore shows up earlier than the watchdog does: the split point is the midpoint between "deadline" and "watchdog" shifted
by the baseline, `BASELINE_UPLOAD_S - (wdt_s - deadline_s) / 2`.

This is the host's observation. It does not say why the phone re-enumerated, and `supported` is not "return to Android is solved"."""
import argparse
import datetime
import json
import sys
from pathlib import Path

BASELINE_VANISH_S = 4.0         # request -> the Android USB identity leaves the bus (runs 001-009)
BASELINE_UPLOAD_S = 95.0        # request -> SEC_UPLOAD on 04e8:685d after the 83 s watchdog (runs 001-009)
BASELINE_TOLERANCE_S = 10.0
COVERAGE_S = BASELINE_UPLOAD_S + 25.0     # the watcher must have run this long after the request to judge an absence
SAMSUNG = "04e8"
ANDROID_PIDS = {"6860", "6861", "6862", "6863", "6864", "685c"}
WORDS = {0x12345601: "U3 (INFORM3 = download word 0x12345601)", 0x1234560D: "U4 (INFORM3 = bootloader word 0x1234560d)"}


def parse_time(s):
    return datetime.datetime.fromisoformat(s).timestamp()


def classify(ev):
    p = (ev.get("product") or "").strip()
    if p == "SAMSUNG USB":
        return "download"
    if "UPLOAD" in p.upper():
        return "upload"
    if ev.get("vid") == SAMSUNG and ev.get("pid") in ANDROID_PIDS:
        return "android"
    return "other"


def load_events(path):
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _v(verdict, why, **kw):
    return dict(verdict=verdict, why=why, **kw)


def analyze(events, report, meta, image):
    """events: usb_watch records; report: the driver's report.json; meta: build.json["image_meta"][image]."""
    deadline, wdt, reason = meta["deadline_s"], meta["wdt_s"], int(meta["reason"], 16)
    ceiling = BASELINE_UPLOAD_S - (wdt - deadline) / 2.0
    out = dict(image=image, reason="0x%08x" % reason, deadline_s=deadline, wdt_s=wdt, early_ceiling_s=ceiling,
               baseline=dict(vanish_s=BASELINE_VANISH_S, upload_s=BASELINE_UPLOAD_S, source="docs/procedures/nat-022/README.md, runs 001-009"),
               timeline=[], notes=[])
    u12, u34 = "U1+U2 (the loader's PMU stores reach the hardware; 0x3c00 := 2 resets without the ACPM STOP request)", WORDS.get(reason, "U3/U4")

    def undetermined(why):
        out["U1_U2"] = dict(question=u12, **_v("undetermined", why))
        out["U3_U4"] = dict(question=u34, **_v("undetermined", why))
        return out

    when = report.get("reboot_requested_at") if report.get("reboot_sent") else None
    if not when:
        return undetermined("the driver report has no reboot request (reboot_sent is false): there is no T0")
    t0 = parse_time(when)
    out["t0_unix"] = t0
    starts = [e for e in events if e["event"] == "start"]
    if not starts:
        return undetermined("no watcher log (no start record)")
    if starts[0]["t_unix"] > t0:
        return undetermined("the watcher started %.1f s after the reboot request" % (starts[0]["t_unix"] - t0))
    stops = [e for e in events if e["event"] == "stop"]
    coverage_end = (stops[-1] if stops else max(events, key=lambda e: e["t_unix"]))["t_unix"] - t0
    out["watcher_covers_s_after_t0"] = round(coverage_end, 2)
    if not stops:
        out["notes"].append("the log has no stop record: the watcher died or was killed; coverage ends at its last record")
    sam = [e for e in events if e["event"] in ("appear", "disappear", "change") and e.get("vid") == SAMSUNG and e["t_unix"] >= t0]
    out["timeline"] = [dict(dt=round(e["t_unix"] - t0, 2), event=e["event"], id="%s:%s" % (e["vid"], e["pid"]), product=e.get("product"),
                            klass=classify(e), path=e["path"]) for e in sam]
    leave = next((e for e in sam if e["event"] == "disappear"), None)
    if leave is None:
        return undetermined("the phone's USB identity never left the bus after the request (or was not on it at the start)")
    out["vanish_dt_s"] = round(leave["t_unix"] - t0, 2)
    first = next((e for e in sam if e["event"] == "appear" and e["t_unix"] > leave["t_unix"]), None)
    if first is None:
        why = "nothing re-enumerated"
        if coverage_end >= COVERAGE_S:
            out["U1_U2"] = dict(question=u12, **_v("undetermined", why + " within the covered window (%.0f s after the request): neither a reset at the deadline "
                                                  "nor the baseline watchdog upload was seen; a hang, a dead loop or a host-side miss are all possible" % coverage_end))
        else:
            out["U1_U2"] = dict(question=u12, **_v("undetermined", why + ", but the watcher covered only %.0f s after the request (< %.0f s)" % (coverage_end, COVERAGE_S)))
        out["U3_U4"] = dict(question=u34, **_v("undetermined", "no re-enumeration to classify"))
        return out
    dt, klass = first["t_unix"] - t0, classify(first)
    out["first_appearance"] = dict(dt=round(dt, 2), id="%s:%s" % (first["vid"], first["pid"]), product=first.get("product"), klass=klass)
    if dt < deadline:
        out["U1_U2"] = dict(question=u12, **_v("undetermined", "the device re-enumerated %.1f s after the request, before the %d s deadline can have elapsed: "
                                              "not the loader's reset (another cause, e.g. a crash handled by S-Boot)" % (dt, deadline)))
    elif klass in ("download", "upload") and dt <= ceiling:
        out["U1_U2"] = dict(question=u12, **_v("supported", "re-enumeration at +%.1f s: after the %d s deadline and before the split point %.1f s that separates it from the "
                                              "baseline watchdog upload (+%.0f s)" % (dt, deadline, ceiling, BASELINE_UPLOAD_S)))
    elif klass == "upload" and abs(dt - BASELINE_UPLOAD_S) <= BASELINE_TOLERANCE_S:
        out["U1_U2"] = dict(question=u12, **_v("refuted", "SEC_UPLOAD at +%.1f s, the baseline of runs 001-009 (watchdog reset at +%.0f s): no reset happened at the deadline" % (dt, BASELINE_UPLOAD_S)))
    elif klass == "android":
        out["U1_U2"] = dict(question=u12, **_v("undetermined", "the Android identity came back at +%.1f s: a normal boot hides when the reset happened" % dt))
        out["notes"].append("Android came back without an owner action; runs 001-009 never did that: record it, it is a result for U3/U4 below")
    else:
        out["U1_U2"] = dict(question=u12, **_v("undetermined", "%s at +%.1f s matches neither the early window [%d, %.1f] s nor the baseline %.0f s +/- %.0f" % (klass, dt, deadline, ceiling, BASELINE_UPLOAD_S, BASELINE_TOLERANCE_S)))
    if out["U1_U2"]["verdict"] == "supported":
        if klass == "download":
            out["U3_U4"] = dict(question=u34, **_v("supported", "after the reset at +%.1f s the device enumerated as SAMSUNG USB (Download Mode) with no owner action" % dt))
        else:
            out["U3_U4"] = dict(question=u34, **_v("refuted", "after the reset at +%.1f s the device enumerated as %r (%s), not Download Mode" % (dt, first.get("product"), klass)))
    elif klass == "android":
        out["U3_U4"] = dict(question=u34, **_v("refuted", "the phone booted back to Android at +%.1f s; Download Mode was not entered (the reset time is unknown, so this is about S-Boot's choice only)" % dt))
    else:
        out["U3_U4"] = dict(question=u34, **_v("undetermined", "the reset at the deadline was not observed, so what S-Boot did with the word is confounded by the other reset cause"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--build", required=True, type=Path)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    build = json.loads((a.build / "build.json").read_text())
    try:
        events = load_events(a.events)
    except OSError:
        events = []
    res = analyze(events, json.loads(Path(a.report).read_text()), build["image_meta"][a.image], a.image)
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
