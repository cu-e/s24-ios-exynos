#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-083 analysis: did the kernel boot the delivered APFS (md1) as its root, did the donor PID 1 chain run on it, and what happened to Apple's launchd?

Reads what the project's own log chain delivered (the collector archive of one run of loader-diag-xnu-rt-md1), the companion's delivery record and the host's copy of
the root image. It never opens a phone. Evidence class of what it reports: native-device, from the kernel text and the USB observations of that run only.

The chain verdict, the boot selection (NAT-081's replay rule) and the delivery reading are the shipped ones (analyze_nat065 under this image's name, sessions.py, analyze_nat080's
`read_delivery`/`read_loader_values`); this file adds the reading of the NAT-083 kernel and console text and the pre-registered ladder below.

The text is the head (8192 bytes) and the tail (32768 bytes) of the kernel's log buffer at its return, with a marker `[... N bytes of the log were not sent ...]` between them
when the log was longer. The console ring (everything PID 1 and its children write) comes first in that text, the kernel message buffer after `--- kernel message buffer ---`.
A line that is absent while such a marker exists is UNKNOWN, not absent: the ladder never turns it into a negative finding.

The ladder (pre-registered in decision 0032; the first row that applies wins; `pass` is true only for row 1 variant a):

  9  the chain verdict is not PASS (the text is not this image's own, or not one contiguous boot): void, nothing below is claimed.
  7  the root image was not fully delivered (loader status not `done`, companion outcome not `delivered`, committed offset not the image size).
  6  the kernel did not take md1 as its root: no `BSD root:` line, a root device other than md1, no md1 of the reserve's size, or the "specified root memory device" panic.
  5  md1 is the root but the APFS did not mount from it: no `apfs: volume` line (the kernel's `cannot mount root, errno`, the `apfs:` error lines and the panic are reported).
  3  the donor's stage0 (/sbin/launchd on the root) printed `stage0: cannot ...`: the small image on /dev/md0 did not mount or /redwood/sbin/init did not run.
  4  the root mounted but no `=== init: process` banner: stage0 or the kernel's exec of /sbin/launchd failed silently (the panic, exit status and any console text are reported).
  2  init ran but: the rc file was not reached, or one of the four Apple programs (df, mount, ps -A, vm_stat) did not run clean (could not run / killed / non-zero exit / exec error
     line), or the `exec /sbin/launchd.darwin` line was not reached or printed an exec error.
  1  init ran, the four Apple programs ran clean and `exec /sbin/launchd.darwin` was reached without an exec error line:
       a  no PID 1 exit and no panic was observed in the text (launchd was running or silent when the kernel returned);
       b  the PID 1 exit (`initproc exited ...` with signal/status) or a panic is in the text after the exec line.
  8  anything else, in particular every case where a needed line is absent and bytes of the log were not sent.

What a row does not say: that Apple's launchd works (row 1a is "no exit observed"), that any service started (the job list of this image is empty by design), or that any
graphics or input component ran. Failed init checks (`[FAIL]` lines) are listed in the facts and are not part of the rule: the donor's init checks assume the donor's environment.
The delivered image's integrity is judged by the kernel's use of it only; NAT-078's whole-image digest is still open."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-rt-md1"
RESERVE = 2475720704                    # the md1 reserve (ADT RAMDisk1), bytes
ROOT_DEVICE = "md1"
DARWIN_COMMANDS = ("/bin/df", "/sbin/mount", "/bin/ps", "/usr/bin/vm_stat")      # argv[0] of the four Apple programs rc.nat083 runs, in order
EXEC_PROGRAM = "/sbin/launchd.darwin"
KMARK = "--- kernel message buffer ---"
BLOCK_KEEP = 3000                       # characters of one command's output kept in the record
LAUNCHD_KEEP = 40                       # lines of console text after the exec line kept in the record

GAP = re.compile(r"\[\.\.\. (\d+) bytes of the log were not sent \.\.\.\]")
MD_LINE = re.compile(r"Added memory device (md\d+)/rmd\d+ \(([0-9A-Fa-f]+)/([0-9A-Fa-f]+)\) at ([0-9A-Fa-f]+) for ([0-9A-Fa-f]+)")
APFS_VOLUME = re.compile(r'apfs: volume (\d+) "(.*?)" of container (\d+) \(at (\d+) MB\): (\d+) files, (\d+) directories, (\d+) blocks of (\d+) used')
APFS_ERRORS = (re.compile(r"apfs: cannot read the container: (-?\d+)"), re.compile(r"apfs: no readable volume with a root directory"),
               re.compile(r"apfs: container (\d+): (\d+) blocks of (\d+) do not fit the device"), re.compile(r"apfs: device (\d+),(\d+): requests to it .*"))
MOUNTROOT_ERROR = re.compile(r"cannot mount root, errno = (-?\d+)")
STAGE0_ERROR = re.compile(r"^stage0: cannot (mount|run) (.*)$", re.M)
INIT_BANNER = re.compile(r"^=== init: process (\d+), started as (\S+) ===$", re.M)
SECTION = re.compile(r"^-- (.*) --$", re.M)
CHECK = re.compile(r"^\[( ok |FAIL)\] (.*)$", re.M)
SUMMARY = re.compile(r"^=== (\d+) checks, (\d+) failed ===$", re.M)
RC_START = re.compile(r"^=== (/\S+) ===$", re.M)
INIT_DONE = "=== init: done ==="
ECHO = re.compile(r"^\$ (\S.*)$", re.M)
EXIT_MARK = re.compile(r"^\[(exit status (\d+)|killed by signal (\d+)|could not run: (.*))\]$", re.M)
STRERROR = ("Operation not permitted|No such file or directory|No such process|Interrupted system call|Input/output error|Device not configured|Argument list too long|"
            "Exec format error|Bad file descriptor|No child processes|Cannot allocate memory|Permission denied|Bad address|Resource busy|File exists|"
            "Operation not supported by device|Not a directory|Is a directory|Invalid argument|Inappropriate ioctl for device|No space left on device|"
            "Read-only file system|Operation not supported|Function not implemented|Unknown error")
PANIC = re.compile(r"^panic\(cpu \d+ caller 0x[0-9a-f]+\): (.*?)\r?$", re.M)
INIT_EXIT = re.compile(r"initproc (exited|failed to start) -- no exit reason available -- \(signal (\d+), exit status (\d+)")
INIT_EXIT_PRINTF = re.compile(r"pid (\d+) exited -- no exit reason available -- \(signal (\d+), exit (\d+)\)")

ROWS = {1: "pass", 2: "init-ran-with-a-failure", 3: "stage0-failed", 4: "root-mounted-no-init", 5: "apfs-root-mount-failed", 6: "kernel-root-not-md1",
        7: "root-not-fully-delivered", 8: "other-or-not-established", 9: "chain-verdict-not-pass"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A80 = _load("nat083_nat080_analyze", PROC / "nat-080" / "analyze_nat080.py")
S = _load("nat083_nat081_sessions", PROC / "nat-081" / "sessions.py")
A65 = A80.A65
write_log = A65.write_log


# ---------------------------------------------------------------------------------------------------------------- the text
def split_blocks(user):
    """The commands the rc runner echoed (`$ cmd args`) and what each printed: [dict(argv0, line, text, marks, exec_error)]. A block ends at the next echo, at the
    `=== init: done ===` line or at the end of the text; `marks` are the runner's `[exit status N]`-style lines; `exec_error` is the child's own `prog: strerror` line."""
    echoes = list(ECHO.finditer(user))
    out = []
    for i, m in enumerate(echoes):
        end = echoes[i + 1].start() if i + 1 < len(echoes) else len(user)
        body = user[m.end():end]
        stop = body.find("\n" + INIT_DONE)
        if stop >= 0:
            body = body[:stop]
        argv = m.group(1).split()
        argv0 = argv[0]
        target = argv[1] if argv0 == "exec" and len(argv) > 1 else argv0       # the program the line is about
        marks = []
        for mk in EXIT_MARK.finditer(body):
            if mk.group(2) is not None:
                marks.append(dict(kind="exit-status", value=int(mk.group(2))))
            elif mk.group(3) is not None:
                marks.append(dict(kind="killed", value=int(mk.group(3))))
            else:
                marks.append(dict(kind="could-not-run", value=mk.group(4)))
        em = re.search(r"^%s: (%s)$" % (re.escape(target), STRERROR), body, re.M)
        out.append(dict(command=m.group(1), argv0=argv0, target=target, text=body.strip("\n")[:BLOCK_KEEP], bytes=len(body), marks=marks,
                        exec_error=em.group(1) if em else None))
    return out


def read_userland(text):
    """The reading of one kernel/console text. Every field is None/empty when its line is not in the text; `gaps` says whether absence means anything."""
    text = (text or "").replace("\r\n", "\n")
    gaps = [int(g) for g in GAP.findall(text)]
    k = text.find(KMARK)
    user = text[:k] if k >= 0 else text
    root = A65.BSD_ROOT.search(text)
    md = [dict(name=m.group(1), size=int(m.group(5), 16)) for m in MD_LINE.finditer(text)]
    vol = APFS_VOLUME.search(text)
    apfs_err = [m.group(0) for rx in APFS_ERRORS for m in [rx.search(text)] if m]
    mr = MOUNTROOT_ERROR.search(text)
    st0 = STAGE0_ERROR.search(user)
    banner = INIT_BANNER.search(text)
    checks = [dict(ok=m.group(1) == " ok ", what=m.group(2)) for m in CHECK.finditer(text)]
    summ = SUMMARY.search(text)
    rc = RC_START.search(text)
    blocks = split_blocks(user)
    exec_block = next((b for b in blocks if b["argv0"] == "exec"), None)
    em = [m for m in ECHO.finditer(user) if m.group(1).split()[0] == "exec"]
    after_exec = user[em[-1].end():] if em else ""                  # console text after the last `$ exec ...` line (launchd's own output, if any)
    panic = PANIC.search(text)
    ie = INIT_EXIT.search(text)
    ip = INIT_EXIT_PRINTF.search(text)
    return dict(
        gaps=gaps, gap_bytes=sum(gaps), text_bytes=len(text), has_kernel_marker=k >= 0,
        bsd_root=dict(device=root.group(1), major=int(root.group(2)), minor=int(root.group(3))) if root else None,
        md=md, root_panic_no_device=("specified root memory device" in text),
        apfs_volume=dict(index=int(vol.group(1)), name=vol.group(2), container=int(vol.group(3)), at_mb=int(vol.group(4)), files=int(vol.group(5)),
                         directories=int(vol.group(6)), blocks_used=int(vol.group(7)), block_size=int(vol.group(8))) if vol else None,
        apfs_errors=apfs_err, mountroot_errno=int(mr.group(1)) if mr else None,
        stage0_error=dict(what=st0.group(1), detail=st0.group(2)) if st0 else None,
        init=dict(banner=dict(pid=int(banner.group(1)), argv0=banner.group(2)) if banner else None, sections=SECTION.findall(user),
                  checks_total=len(checks), checks_failed=[c["what"] for c in checks if not c["ok"]],
                  summary=dict(checks=int(summ.group(1)), failed=int(summ.group(2))) if summ else None,
                  rc=rc.group(1) if rc else None, done=INIT_DONE in text),
        commands=blocks, exec_seen=exec_block is not None,
        after_exec=dict(bytes=len(after_exec.strip("\n")), lines=after_exec.strip("\n").split("\n")[:LAUNCHD_KEEP] if after_exec.strip("\n") else []),
        panic=panic.group(1) if panic else None,
        pid1_exit=dict(how=ie.group(1), signal=int(ie.group(2)), status=int(ie.group(3))) if ie else None,
        pid1_exit_printf=dict(pid=int(ip.group(1)), signal=int(ip.group(2)), status=int(ip.group(3))) if ip else None)


def command_problem(block):
    """Why a command block counts as not clean, or None."""
    if block is None:
        return "no echo line"
    if block["exec_error"]:
        return "exec error: %s" % block["exec_error"]
    if block["marks"]:
        m = block["marks"][0]
        return {"exit-status": "exit status %s", "killed": "killed by signal %s", "could-not-run": "could not run: %s"}[m["kind"]] % m["value"]
    return None


# ---------------------------------------------------------------------------------------------------------------- the rule
def decide(chain_verdict, delivery, loader, size, kern):
    """-> dict(row, name, variant, reasons, pass, facts). `delivery`: read_delivery() or None; `loader`: read_loader_values(); `size`: the image's byte count; `kern`: read_userland()."""
    st = loader["status"]
    ld_committed = loader["values"].get("committed")
    dev_committed = (delivery or {}).get("committed")
    committed = ld_committed if ld_committed is not None else dev_committed
    outcome = (delivery or {}).get("outcome")
    unknown = bool(kern["gaps"])
    by_cmd = {}
    for b in kern["commands"]:
        by_cmd.setdefault(b["argv0"], b)
    facts = dict(size=size, committed=committed, delivery_outcome=outcome, loader_status=st, loader_status_name=loader["status_name"], gap_bytes=kern["gap_bytes"],
                 bsd_root=kern["bsd_root"], md=kern["md"], apfs_volume=kern["apfs_volume"], apfs_errors=kern["apfs_errors"], mountroot_errno=kern["mountroot_errno"],
                 stage0_error=kern["stage0_error"], init_banner=kern["init"]["banner"], init_sections=kern["init"]["sections"], init_checks_failed=kern["init"]["checks_failed"],
                 init_summary=kern["init"]["summary"], rc=kern["init"]["rc"], commands=[dict(command=b["command"], bytes=b["bytes"], marks=b["marks"], exec_error=b["exec_error"])
                                                                                  for b in kern["commands"]],
                 panic=kern["panic"], pid1_exit=kern["pid1_exit"] or kern["pid1_exit_printf"], after_exec_bytes=kern["after_exec"]["bytes"])

    def done(row, *reasons, variant=None):
        return {"row": row, "name": ROWS[row], "variant": variant, "reasons": list(reasons), "pass": row == 1 and variant == "a", "facts": facts}

    def not_established(what):
        return done(8, "%s is absent and %d bytes of the log were not sent: absence is not established" % (what, kern["gap_bytes"]))

    if chain_verdict != "PASS":
        return done(9, "the chain verdict is %s: the text is not established as this image's own contiguous boot" % chain_verdict)
    if not (committed == size and outcome == "delivered" and st == 0):
        return done(7, "committed %s of %s bytes, companion outcome %s, loader status %s: the root image was not fully delivered" % (committed, size, outcome, loader["status_name"]))

    md1 = next((m for m in kern["md"] if m["name"] == ROOT_DEVICE), None)
    root = kern["bsd_root"]
    if root is None:
        if kern["root_panic_no_device"]:
            return done(6, "the kernel panicked on the specified root memory device")
        if unknown:
            return not_established("the `BSD root:` line")
        return done(6, "no `BSD root:` line in the text")
    if root["device"] != ROOT_DEVICE:
        return done(6, "the kernel's root device is %s, not %s" % (root["device"], ROOT_DEVICE))
    if md1 is None or md1["size"] != RESERVE:
        if md1 is None and unknown:
            return not_established("the `Added memory device md1` line")
        return done(6, "md1 is %s; the reserve is %d bytes" % ("not configured" if md1 is None else "%d bytes" % md1["size"], RESERVE))

    if kern["apfs_volume"] is None:
        if kern["mountroot_errno"] is not None or kern["apfs_errors"] or kern["panic"]:
            return done(5, "md1 is the root but no APFS volume was mounted: cannot-mount-root errno %s; apfs lines %s; panic %s" %
                        (kern["mountroot_errno"], kern["apfs_errors"] or "none", kern["panic"] or "none"))
        if unknown:
            return not_established("the `apfs: volume` line")
        return done(5, "md1 is the root, no `apfs: volume` line and no error line in the text")
    if kern["stage0_error"]:
        return done(3, "stage0: cannot %s %s" % (kern["stage0_error"]["what"], kern["stage0_error"]["detail"]))
    init = kern["init"]
    if init["banner"] is None:
        if unknown:
            return not_established("the `=== init: process` banner")
        return done(4, "the APFS root mounted (volume %r) but PID 1 printed no init banner; panic %s, PID 1 exit %s, console text before the kernel buffer: %d bytes" %
                    (kern["apfs_volume"]["name"], kern["panic"] or "none", facts["pid1_exit"] or "none", kern["after_exec"]["bytes"]))

    problems = []
    if init["rc"] is None:
        if unknown:
            return not_established("the rc file's `=== /path ===` line")
        return done(2, "init ran (%d sections, summary %s) but never reached its rc file; the last section is %r" %
                    (len(init["sections"]), init["summary"] or "absent", init["sections"][-1] if init["sections"] else None), variant="rc-not-reached")
    for c in DARWIN_COMMANDS:
        b = by_cmd.get(c)
        if b is None and unknown:
            return not_established("the echo line of %s" % c)
        p = command_problem(b)
        if p:
            problems.append("%s: %s" % (c, p))
    if problems:
        return done(2, "an Apple program did not run clean: " + "; ".join(problems), variant="darwin-program")
    if not kern["exec_seen"]:
        if unknown:
            return not_established("the `$ exec %s` line" % EXEC_PROGRAM)
        return done(2, "the four Apple programs ran clean but the rc did not reach `exec %s`" % EXEC_PROGRAM, variant="exec-not-reached")
    eb = next(b for b in kern["commands"] if b["argv0"] == "exec")
    if eb["target"] != EXEC_PROGRAM:
        return done(8, "the exec line is for %s, not %s" % (eb["target"], EXEC_PROGRAM))
    if eb["exec_error"]:
        return done(2, "exec %s failed: %s" % (EXEC_PROGRAM, eb["exec_error"]), variant="launchd-exec-failed")
    exit_info = facts["pid1_exit"]
    base = "init ran, df/mount/ps/vm_stat ran clean, `exec %s` reached without an exec error line" % EXEC_PROGRAM
    if exit_info or kern["panic"]:
        return done(1, base + "; after it: PID 1 exit %s, panic %s" % (exit_info or "none", kern["panic"] or "none"), variant="b")
    return done(1, base + "; no PID 1 exit and no panic in the text (%d bytes of console text after the exec line)" % kern["after_exec"]["bytes"], variant="a")


# ---------------------------------------------------------------------------------------------------------------- the run
def pick_text(texts):
    """-> (dump key, text): the highest non-empty return dump. It is the dump at the kernel's own return; the earlier dump is a prefix of the same log."""
    live = [k for k in sorted(texts or {}) if texts[k]]
    return (live[-1], texts[live[-1]]) if live else (None, "")


def analyze(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic=False, **kw):
    """The shipped chain under this image's name and NAT-081's boot selection, then the NAT-083 reading."""
    S.LAST.clear()
    undo = S.install(A65.A49)
    old = A65.IMAGE
    A65.IMAGE = IMAGE
    try:
        out = A80._ANALYZE65(root, events, report, allow_synthetic, **kw)
    finally:
        A65.IMAGE = old
        undo()
    dump_used, text = pick_text((out.get("kernel_log") or {}).get("texts"))
    lines = []
    boot = out.get("boot")
    if boot and boot.get("name"):
        lines = A65.A59.boot_texts(root, boot["name"])
    loader = A80.read_loader_values(lines)
    delivery = A80.read_delivery(delivery_dir)
    ending = A80.classify_return((out.get("usb") or {}).get("first_return"))
    digests = A80.host_prefix_digests(image_path, [size]) if image_path else {}
    if digests.get(size) != sha256:
        raise ValueError("the root file is not the image the run is judged against (sha256 %s, expected %s)" % (digests.get(size), sha256))
    kern = read_userland(text)
    out["image"] = IMAGE
    out["nat083"] = dict(decision=decide(out.get("verdict"), delivery, loader, size, kern), kernel=dict(
        gaps=kern["gaps"], text_bytes=kern["text_bytes"], dump_used=dump_used, md=kern["md"], vm=A80.read_vm(text), bsd_root=kern["bsd_root"],
        apfs_volume=kern["apfs_volume"], init=kern["init"], commands=kern["commands"], after_exec=kern["after_exec"], panic=kern["panic"],
        pid1_exit=kern["pid1_exit"], pid1_exit_printf=kern["pid1_exit_printf"]),
        loader=dict(found=loader["found"], status=loader["status"], status_name=loader["status_name"], values=loader["values"]),
        delivery=delivery, ending=ending, chain_verdict=out.get("verdict"), nat081=S.LAST.get("info"))
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
        res = analyze(a.archive, events, report, a.delivery, a.root, a.size, a.sha256, a.allow_synthetic)
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
