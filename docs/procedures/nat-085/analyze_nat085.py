#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-085 analysis of the run of loader-diag-xnu-ep-md1: the chain of NAT-083 (analyze_nat083.py, unchanged) and then what Apple's launchd did after keybagd.

The image is NAT-083's with two changes: the device tree carries /chosen `ephemeral-storage` = u32 1 (make_adt85.py), and the small root holds one launchd job, com.nat085.ps
(`/bin/ps -A` to the console, KeepAlive, 10 s throttle). NAT-084 ended at the launchd boot task `keybag`: keybagd --init went down the MKB_INIT path (no systembag.kb, no SEP), printed
`FATAL KEYBAG ERROR` and asked launchd to reboot into recovery. The shared cache's os_variant code makes keybagd skip that path when sysctl hw.ephemeral_storage is non-zero; this
image is the test of that hypothesis. Nothing in this file is a measurement; it reads what a run's log chain returned.

Step 1, the chain: analyze_nat083.analyze() under this image's name gives the NAT-083 ladder (rows 1-9; the decision-0032 reading, its `pass` is row 1 variant a).
Step 2, the stage ladder over the console text AFTER the last `$ exec /sbin/launchd.darwin` line (pre-registered in decision 0033; the first row that applies wins; `pass` only for S1):

  S9  the chain row is not 1 (or no exec line): the launchd stage is not evaluated.
  S7  the chain reached the exec but the text after it has no launchd line (`com.apple.xpc.launchd|` / `libignition:`): launchd printed nothing.      [absent + gap => S8]
  S6  launchd ran boot tasks but never started the `keybag` task.                                                                                     [absent + gap => S8]
  S5  the `keybag` task started and keybagd did NOT skip: no `DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT` line, or an `IN MKB_INIT` / `FATAL KEYBAG ERROR` line is present.
  S4  keybagd skipped, and launchd stopped: a PID 1 exit, a panic or a reboot request (`REBOOTING INTO RECOVERY MODE`, `MKB_INIT: Rebooting`) is in the text.
  S3  keybagd skipped, no stop observed, but the job never printed a process list (no `PID TTY TIME CMD` header after the exec line).                [absent + gap => S8]
  S2  keybagd skipped, no stop observed, the job printed exactly one process list.
  S1  keybagd skipped, no stop observed, the job printed at least two process lists (>= 10 s of a running launchd between two job runs).
  S8  anything else, in particular every case where a needed line is absent and bytes of the log were not sent.

What a row does not say: that launchd keeps running after the log was returned (the returned text ends at the loader's return), that any service other than the one job started, that
the keybag, SEP or data volume exist (keybagd SKIPPED its init; nothing was created), or anything about graphics or input. `hw.ephemeral_storage` itself is not read: the skip line is the
observable. Boot tasks after `keybag` and the notable lines (failure words) after it are listed in the facts without a rule: they are the next blocker's evidence."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-ep-md1"
SKIP_LINE = "DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT"
MKB_LINE = "IN MKB_INIT"
KB_FATAL = re.compile(r"FATAL KEYBAG ERROR")
REBOOT_REQUEST = re.compile(r"REBOOTING INTO RECOVERY MODE|MKB_INIT: Rebooting")
LAUNCHD_LINE = re.compile(r"com\.apple\.xpc\.launchd\||^libignition:", re.M)
TASK = re.compile(r"\((?P<task>[^()\s]+)\) <Notice>: Doing boot task")
PS_HEADER = re.compile(r"^[ \t]*PID[ \t]+TTY[ \t]+TIME[ \t]+CMD[ \t]*$", re.M)
PS_ROW = re.compile(r"^[ \t]*(\d+)[ \t]+(\S+)[ \t]+([\d:.]+)[ \t]+(.+?)[ \t]*$")
NOTABLE = re.compile(r"fail|error|fatal|panic|abort|crash|reboot|killed|exited|cannot|unable|denied|refus", re.I)
NOTABLE_KEEP = 25
LINE_KEEP = 200
PS_KEEP = 40
STAGE_ROWS = {1: "keybag-skipped-job-heartbeat", 2: "keybag-skipped-job-ran-once", 3: "keybag-skipped-launchd-alive-no-job", 4: "keybag-skipped-launchd-stopped",
              5: "keybag-not-skipped", 6: "keybag-not-reached", 7: "launchd-silent", 8: "not-established", 9: "not-evaluated"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A83 = _load("nat085_analyze83", PROC / "nat-083" / "analyze_nat083.py")
A65, A80, S = A83.A65, A83.A80, A83.S
write_log = A83.write_log


def after_exec_text(text):
    """The console text after the LAST `$ exec ...` echo line of the console part (launchd's own output and its children's), or None when there is no such line."""
    text = (text or "").replace("\r\n", "\n")
    k = text.find(A83.KMARK)
    user = text[:k] if k >= 0 else text
    em = [m for m in A83.ECHO.finditer(user) if m.group(1).split()[0] == "exec"]
    return user[em[-1].end():] if em else None


def read_stage(after):
    """The reading of launchd's console text. `after` is after_exec_text(); None reads as an empty text."""
    after = (after or "").replace("\r\n", "\n")
    tasks = [m.group("task") for m in TASK.finditer(after)]
    kb = tasks.index("keybag") if "keybag" in tasks else None
    lines = after.split("\n")
    heartbeats, cur = [], None
    for ln in lines:
        if PS_HEADER.match(ln):
            cur = []
            heartbeats.append(cur)
        elif cur is not None:
            m = PS_ROW.match(ln)
            if m:
                cur.append(m.group(4))
            else:
                cur = None
    kb_text = after[[m.start() for m in TASK.finditer(after) if m.group("task") == "keybag"][0]:] if kb is not None else ""
    notable = [ln.strip()[:LINE_KEEP] for ln in kb_text.split("\n") if ln.strip() and NOTABLE.search(ln)]
    return dict(
        bytes=len(after), lines=len(lines), launchd_lines=len(LAUNCHD_LINE.findall(after)), tasks=tasks,
        keybag_reached=kb is not None, tasks_after_keybag=tasks[kb + 1:] if kb is not None else [], last_task=tasks[-1] if tasks else None,
        keybag_skip=SKIP_LINE in after, mkb_init=MKB_LINE in after, keybag_fatal=bool(KB_FATAL.search(after)), reboot_request=bool(REBOOT_REQUEST.search(after)),
        fips_all_passed="all tests PASSED" in after, libignition_failed=next((ln.strip()[:LINE_KEEP] for ln in lines if "ignition boot failed" in ln), None),
        job_runs=len(heartbeats), last_heartbeat=heartbeats[-1][:PS_KEEP] if heartbeats else [], job_label_lines=[ln.strip()[:LINE_KEEP] for ln in lines if "nat085" in ln][:10],
        notable_after_keybag=notable[:NOTABLE_KEEP], notable_total=len(notable))


def decide_stage(chain, st, kern):
    """-> dict(row, name, reasons, pass, facts). `chain`: A83.decide()'s dict; `st`: read_stage(); `kern`: A83.read_userland() of the same text (gaps, PID 1 exit, panic)."""
    unknown = bool(kern["gaps"])
    pid1 = kern["pid1_exit"] or kern["pid1_exit_printf"]
    facts = dict(chain_row=chain["row"], chain_variant=chain["variant"], gap_bytes=kern["gap_bytes"], pid1_exit=pid1, panic=kern["panic"],
                 **{k: v for k, v in st.items()})

    def done(row, *reasons):
        return {"row": row, "name": STAGE_ROWS[row], "reasons": list(reasons), "pass": row == 1, "facts": facts}

    def not_established(what):
        return done(8, "%s is absent and %d bytes of the log were not sent: absence is not established" % (what, kern["gap_bytes"]))

    if chain["row"] != 1:
        return done(9, "the chain row is %s (%s): the launchd stage is not evaluated" % (chain["row"], chain["name"]))
    if not kern["exec_seen"]:
        return done(9, "no `$ exec` line in the console text")
    if not st["launchd_lines"]:
        return not_established("any launchd line") if unknown else done(7, "%d bytes of console text after the exec line, none of them from launchd" % st["bytes"])
    if not st["keybag_reached"]:
        if unknown:
            return not_established("the `keybag` boot task")
        return done(6, "launchd ran %d boot task(s), last `%s`, and never started `keybag`" % (len(st["tasks"]), st["last_task"]))
    if st["mkb_init"] or st["keybag_fatal"]:
        return done(5, "keybagd went down the MKB_INIT path (`IN MKB_INIT` %s, fatal keybag line %s)" % (st["mkb_init"], st["keybag_fatal"]))
    if not st["keybag_skip"]:
        return not_established("the keybagd skip line") if unknown else done(5, "the `keybag` task started and its output has no skip line and no MKB_INIT line")
    stopped = []
    if pid1:
        stopped.append("PID 1 exit %s" % (pid1,))
    if kern["panic"]:
        stopped.append("panic %s" % kern["panic"])
    if st["reboot_request"]:
        stopped.append("a reboot request line")
    base = "keybagd skipped its init; %d boot task(s) followed `keybag` (last `%s`)" % (len(st["tasks_after_keybag"]), st["last_task"])
    if stopped:
        return done(4, base + "; launchd stopped: " + "; ".join(stopped) + "; job runs seen: %d" % st["job_runs"])
    if st["job_runs"] >= 2:
        return done(1, base + "; no PID 1 exit, panic or reboot request in the text; the job printed %d process lists" % st["job_runs"])
    if st["job_runs"] == 1:
        return done(2, base + "; no stop observed; the job printed exactly one process list")
    if unknown:
        return not_established("the job's process list")
    return done(3, base + "; no stop observed; the job printed no process list")


def analyze(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic=False, image=IMAGE, **kw):
    """NAT-083's analysis under `image`, then the stage reading. `image` is the name the chain judges the boot against (a test may pass NAT-083's)."""
    old = A83.IMAGE
    A83.IMAGE = image
    try:
        out = A83.analyze(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic, **kw)
    finally:
        A83.IMAGE = old
    dump_used, text = A83.pick_text((out.get("kernel_log") or {}).get("texts"))
    kern = A83.read_userland(text)
    chain = out["nat083"]["decision"]
    st = read_stage(after_exec_text(text))
    out["nat085"] = dict(stage=decide_stage(chain, st, kern), launchd=st, dump_used=dump_used, ending=out["nat083"]["ending"], chain_row=chain["row"], chain_pass=chain["pass"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--events", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--delivery", type=Path, help="the companion's output directory (delivery.json, delivery.jsonl)")
    ap.add_argument("--root", required=True, type=Path, help="the padded root image the run delivered")
    ap.add_argument("--size", required=True, type=int)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--image", default=IMAGE, help="the image name the chain judges the boot against (default: this run's image)")
    ap.add_argument("--out")
    ap.add_argument("--log-out")
    ap.add_argument("--allow-synthetic", action="store_true", help="host tests: label the verdict simulated-* instead of refusing it")
    a = ap.parse_args(argv)
    if a.out and Path(a.out).exists():
        print("refused: %s already exists" % a.out, file=sys.stderr)
        return 2
    events, _ = A65.A49.read_jsonl(a.events)
    report = A65.A49.read_json(a.report) or {}
    try:
        res = analyze(a.archive, events, report, a.delivery, a.root, a.size, a.sha256, a.allow_synthetic, image=a.image)
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")
    if a.log_out:
        write_log(res, a.log_out)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
