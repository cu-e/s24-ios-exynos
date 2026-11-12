#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-087 analysis of the run of loader-diag-xnu-rm-md1: the chain of NAT-083 (analyze_nat083.py, unchanged) and then what Apple's launchd did in its restore mode.

The image is NAT-085's (ADT /chosen `ephemeral-storage` = 1, the one job com.nat085.ps) with ONE change: the kernel command line ends in ` xrd=md0`. The kernel parses boot-args by
whole key (PE_parse_boot_argn_internal), so `xrd` is not `rd` and the root stays `rd=md1`; `kern.bootargs` returns the whole line, and Apple's launchd looks for the substring
`rd=md0` in it with strstr. NAT-086 (decision 0033) ended at the boot task `launchd_cache_loader`: the donor image has no /System/Library/xpc/launchd.plist on purpose, the loader
aborted and XNU panicked. Host disassembly of launchd (capstone over the pinned IPSW binary, NOT yet observed on the phone): the substring (or Restore/Ramdisk/RamDisk) sets a
restore flag; with it a boot task runs only if it is PerformAlways or PerformInRestore (commit-boot-mode, init-with-data-volume, restore-datapartition), and a missing service
cache is not fatal ("Restore environment starting." is logged). This image is the test of that reading. Nothing in this file is a measurement; it reads what a run's log chain returned.

Step 1, the chain: analyze_nat083.analyze() under this image's name gives the NAT-083 ladder (rows 1-9; the decision-0032 reading, its `pass` is row 1).
Step 2, the restore ladder over the console text AFTER the last `$ exec /sbin/launchd.darwin` line (pre-registered in decision 0034; the first row that applies wins; `pass` only for R1):

  R9  the chain row is not 1 (or no exec line): the launchd stage is not evaluated.
  R7  the chain reached the exec but the text after it has no launchd line (`com.apple.xpc.launchd|` / `libignition:`): launchd printed nothing.                      [absent + gap => R8]
  R5  a boot task started that restore mode should skip (a `Doing boot task` line for a task other than commit-boot-mode, init-with-data-volume, restore-datapartition):
      launchd did not skip as the disassembly says. The facts say whether the `Restore environment starting.` line was seen (not seen = the substring was not found).   [presence is never hidden by a gap]
  R6  no unexpected boot task, no `Restore environment starting.` line: launchd printed lines but gave no sign of restore mode.                                      [absent + gap => R8]
  R4  restore line present, no unexpected boot task, and launchd stopped: a PID 1 exit, a panic, a reboot request (`REBOOTING INTO RECOVERY MODE`, `MKB_INIT: Rebooting`)
      or the fatal `No service cache` line is in the text.
  R3  restore line present, no stop observed, but the job never printed a process list (no `PID TTY TIME CMD` header after the exec line).                           [absent + gap => R8]
  R2  restore line present, no stop observed, the job printed exactly one process list.
  R1  restore line present, no stop observed, the job printed at least two process lists (>= 10 s of a running launchd between two job runs).
  R8  anything else, in particular every case where a needed line is absent and bytes of the log were not sent.

What a row does not say: that launchd keeps running after the log was returned (the returned text ends at the loader's return), that any service other than the one job started, that
the real iOS services exist, or anything about graphics or input. The tasks launchd ran, the lines about the service cache, `Skipping boot-task` lines and the notable lines (failure
words) after the restore line are listed in the facts without a rule: they are the next blocker's evidence."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-rm-md1"
RESTORE_LINE = "Restore environment starting."
NO_CACHE = "No service cache"
CACHE_SEARCH = "disk will be searched for uncached services"
PLIST_MISSING = "Unable to open /System/Library/xpc/launchd.plist"
SKIPPING = "Skipping boot-task"
ALLOWED_TASKS = ("commit-boot-mode", "init-with-data-volume", "restore-datapartition")    # PerformAlways, PerformAlways, PerformInRestore in the Boot dictionary of the pinned launchd
REBOOT_REQUEST = re.compile(r"REBOOTING INTO RECOVERY MODE|MKB_INIT: Rebooting")
LAUNCHD_LINE = re.compile(r"com\.apple\.xpc\.launchd\||^libignition:", re.M)
TASK = re.compile(r"\((?P<task>[^()\s]+)\) <Notice>: Doing boot task")
PS_HEADER = re.compile(r"^[ \t]*PID[ \t]+TTY[ \t]+TIME[ \t]+CMD[ \t]*$", re.M)
PS_ROW = re.compile(r"^[ \t]*(\d+)[ \t]+(\S+)[ \t]+([\d:.]+)[ \t]+(.+?)[ \t]*$")
NOTABLE = re.compile(r"fail|error|fatal|panic|abort|crash|reboot|killed|exited|cannot|unable|denied|refus", re.I)
NOTABLE_KEEP = 25
LINE_KEEP = 200
PS_KEEP = 40
KEEP_LINES = 10
ROWS = {1: "restore-mode-job-heartbeat", 2: "restore-mode-job-ran-once", 3: "restore-mode-launchd-alive-no-job", 4: "restore-mode-launchd-stopped",
        5: "boot-tasks-not-skipped", 6: "restore-line-absent", 7: "launchd-silent", 8: "not-established", 9: "not-evaluated"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A83 = _load("nat087_analyze83", PROC / "nat-083" / "analyze_nat083.py")
A65, A80, S = A83.A65, A83.A80, A83.S
write_log = A83.write_log


def after_exec_text(text):
    """The console text after the LAST `$ exec ...` echo line of the console part (launchd's own output and its children's), or None when there is no such line."""
    text = (text or "").replace("\r\n", "\n")
    k = text.find(A83.KMARK)
    user = text[:k] if k >= 0 else text
    em = [m for m in A83.ECHO.finditer(user) if m.group(1).split()[0] == "exec"]
    return user[em[-1].end():] if em else None


def read_restore(after):
    """The reading of launchd's console text. `after` is after_exec_text(); None reads as an empty text."""
    after = (after or "").replace("\r\n", "\n")
    lines = after.split("\n")
    tasks = [m.group("task") for m in TASK.finditer(after)]
    unexpected = [t for t in tasks if t not in ALLOWED_TASKS]
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
    k = after.find(RESTORE_LINE)
    tail = after[k:] if k >= 0 else ""
    notable = [ln.strip()[:LINE_KEEP] for ln in tail.split("\n") if ln.strip() and NOTABLE.search(ln)]
    return dict(
        bytes=len(after), lines=len(lines), launchd_lines=len(LAUNCHD_LINE.findall(after)), tasks=tasks, unexpected_tasks=unexpected, last_task=tasks[-1] if tasks else None,
        restore_line=k >= 0, no_cache=NO_CACHE in after, cache_search_line=CACHE_SEARCH in after, plist_missing_line=PLIST_MISSING in after,
        skipping_lines=[ln.strip()[:LINE_KEEP] for ln in lines if SKIPPING in ln][:KEEP_LINES], skipping_total=sum(SKIPPING in ln for ln in lines),
        keybag_ran="keybag" in tasks, cache_loader_ran="launchd_cache_loader" in tasks, reboot_request=bool(REBOOT_REQUEST.search(after)),
        fips_all_passed="all tests PASSED" in after, libignition_failed=next((ln.strip()[:LINE_KEEP] for ln in lines if "ignition boot failed" in ln), None),
        job_runs=len(heartbeats), last_heartbeat=heartbeats[-1][:PS_KEEP] if heartbeats else [], job_label_lines=[ln.strip()[:LINE_KEEP] for ln in lines if "nat085" in ln][:KEEP_LINES],
        notable_after_restore=notable[:NOTABLE_KEEP], notable_total=len(notable))


def decide_restore(chain, st, kern):
    """-> dict(row, name, reasons, pass, facts). `chain`: A83.decide()'s dict; `st`: read_restore(); `kern`: A83.read_userland() of the same text (gaps, PID 1 exit, panic)."""
    unknown = bool(kern["gaps"])
    pid1 = kern["pid1_exit"] or kern["pid1_exit_printf"]
    facts = dict(chain_row=chain["row"], chain_variant=chain["variant"], gap_bytes=kern["gap_bytes"], pid1_exit=pid1, panic=kern["panic"], **{k: v for k, v in st.items()})

    def done(row, *reasons):
        return {"row": row, "name": ROWS[row], "reasons": list(reasons), "pass": row == 1, "facts": facts}

    def not_established(what):
        return done(8, "%s is absent and %d bytes of the log were not sent: absence is not established" % (what, kern["gap_bytes"]))

    if chain["row"] != 1:
        return done(9, "the chain row is %s (%s): the launchd stage is not evaluated" % (chain["row"], chain["name"]))
    if not kern["exec_seen"]:
        return done(9, "no `$ exec` line in the console text")
    if not st["launchd_lines"]:
        return not_established("any launchd line") if unknown else done(7, "%d bytes of console text after the exec line, none of them from launchd" % st["bytes"])
    if st["unexpected_tasks"]:
        return done(5, "boot task(s) %s started (%d unexpected of %d; only %s are expected in restore mode); the `%s` line was %s" % (
            st["unexpected_tasks"][:6], len(st["unexpected_tasks"]), len(st["tasks"]), list(ALLOWED_TASKS), RESTORE_LINE, "seen" if st["restore_line"] else "not seen"))
    if not st["restore_line"]:
        if unknown:
            return not_established("the `%s` line" % RESTORE_LINE)
        return done(6, "launchd printed %d line(s), %d boot task(s) started (last `%s`), none unexpected, and there is no `%s` line" % (
            st["launchd_lines"], len(st["tasks"]), st["last_task"], RESTORE_LINE))
    stopped = []
    if pid1:
        stopped.append("PID 1 exit %s" % (pid1,))
    if kern["panic"]:
        stopped.append("panic %s" % kern["panic"])
    if st["reboot_request"]:
        stopped.append("a reboot request line")
    if st["no_cache"]:
        stopped.append("`%s`" % NO_CACHE)
    base = "restore mode entered; boot tasks started: %s" % (st["tasks"] or "none")
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
    """NAT-083's analysis under `image`, then the restore reading. `image` is the name the chain judges the boot against (a test may pass another run's)."""
    old = A83.IMAGE
    A83.IMAGE = image
    try:
        out = A83.analyze(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic, **kw)
    finally:
        A83.IMAGE = old
    dump_used, text = A83.pick_text((out.get("kernel_log") or {}).get("texts"))
    kern = A83.read_userland(text)
    chain = out["nat083"]["decision"]
    st = read_restore(after_exec_text(text))
    out["nat087"] = dict(restore=decide_restore(chain, st, kern), launchd=st, dump_used=dump_used, ending=out["nat083"]["ending"], chain_row=chain["row"], chain_pass=chain["pass"])
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
