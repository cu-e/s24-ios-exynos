#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-080: the verdict of the NAT-078 run (loader-diag-xnu-rx-md1: root image delivered over USB into the md1 reserve, PID 1 = the NAT-077 hash probe).

    analyze_nat080.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json --delivery RUN/delivery
                      --root PADDED_ROOT --size 2475720704 --sha256 H [--out RUN/analysis.json] [--log-out RUN/kernel-log.txt]

It applies the pass table of docs/procedures/nat-079/decision-template-nat078.md (section 6; rows 1-8 are those of docs/procedures/nat-077/decision-draft.md,
rows 9 and 10 were added by NAT-079/NAT-080) to what the run left behind, and decides nothing else:

  * the chain verdict of NAT-065 (the boot's frames, the banner of THIS image, contiguous records), under this image's name;
  * the loader's own values (`nat079_status`, `nat079_committed`, ... as `key=0xHEX` records, and the `NAT079 rx MiB=` progress lines);
  * the companion's record (`delivery.json`, or `delivery.jsonl` when the summary was not written): outcome, the DEVICE's committed offset, the rate;
  * the probe's lines in the kernel text (`SWEET hash: at=... sha256=...`, the final line, `cannot open`, `read failed`) compared, line by line, with the
    SHA-256 of the corresponding PREFIX of the root file, recomputed here from the file;
  * the ending: the host's first return of the phone, classified against the deadline clock of NAT-068/NAT-075 scaled to this image's 360 s deadline.

Row numbers are stable (the decision refers to them): 1 pass, 2 digest or length mismatch inside the delivered span, 3 short transfer (3a: delivery complete,
hash cut short by the kernel's return), 4 SEC_UPLOAD ending with a cut hash, 5 /dev/rmd1 cannot be opened, 6 read failure or empty device, 7 the delivery path never
worked (not ready, refused, the first chunk failed, the engine did not come up), 8 anything else, 9 the loader refused or distrusted the receive phase, 10 a chunk
failed its checksum repeatedly. The rows are tried in the order 9, 7, 10, 2, 5/6, 3, then 1/3a/4/8: a row earlier in that list is the more basic finding and
makes the read-back results below it void or secondary. Everything the rule used is returned in `facts`, so a reader can re-derive the row.

It reads delivered text and a host-side observation, and it decides nothing about the phone. Nothing in it is a measurement."""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-rx-md1"
DEADLINE_S = 360                            # build.py --deadline-s of the image: the NAT-044 hard deadline, in loader seconds
BASELINE_RETURN_S, BASELINE_DEADLINE_S = 87.72, 60     # NAT-068 (decision 0028): Download Mode at +87.7 s for a 60 s deadline
LOADER_SECOND = (0.95, 1.0)                 # host seconds per loader second, as measured in NAT-068/NAT-075
CAP_RETURN = (364.0, 405.0)                 # 87.72 + (360 - 60) * (0.95 .. 1.0) = 372.7 .. 387.7, widened by NAT-075's margins (-8.2 s, +17.3 s)
EXIT_OK = 81                                # 0x51: PID 1 exits with 0x50 + its pid
EXIT_CLASSES = {0x60: "no-console", 0x61: "cannot-open-root-device", 0x62: "read-failed", 0x63: "empty-device"}
STATUS = {0: "done", 1: "no-engine", 2: "not-present", 3: "bad-args", 4: "premature", 5: "selftest", 6: "timeout", 7: "engine-down", 8: "inconsistent"}
LOADER_VOID = (3, 4, 5, 8)                  # row 9
LOADER_NO_PATH = (1, 2, 7)                  # row 7 while the committed offset is short
LOADER_VAL = re.compile(r"\bnat079_([a-z0-9_]+)=0x([0-9a-fA-F]+)")
LOADER_PROGRESS = re.compile(r"NAT079 rx MiB=(\d+) trbs=(\d+) err=(\d+) t=(\d+)s")
PROBE_BANNER = re.compile(r"\*\*\* SWEET hash probe: init running as PID (\d+) \*\*\*")
PROBE_READING = re.compile(r"SWEET hash: reading (\S+) in chunks of (\d+)")
PROBE_AT = re.compile(r"SWEET hash: at=(\d+) sha256=([0-9a-f]{64}) sec=(\d+\.\d{3})")
PROBE_FINAL = re.compile(r"SWEET hash: bytes=(\d+) sha256=([0-9a-f]{64}) sec=(\d+\.\d{3})")
PROBE_OPEN = re.compile(r"SWEET hash: cannot open (\S+), errno (\d+)")
PROBE_READ = re.compile(r"SWEET hash: read failed after (\d+) bytes, errno (\d+)")
PROBE_DONE = "SWEET probe: done, exiting"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A75 = _load("nat080_nat075_analyze", PROC / "nat-075" / "analyze_nat075.py")
A65 = A75.A65
write_log = A65.write_log
read_md, read_vm, read_loader = A75.read_md, A75.read_vm, A75.read_loader
_ANALYZE65 = A65.analyze


# ---------------------------------------------------------------------------------------------------------------- the pieces of the record
def read_loader_values(lines):
    """-> dict(values={name: int} (the last record of each `nat079_name=0x..`), status, status_name, progress=[(MiB, trbs, err, t)])."""
    text = "\n".join(lines or [])
    values = {m.group(1): int(m.group(2), 16) for m in LOADER_VAL.finditer(text)}
    progress = [tuple(int(g) for g in m.groups()) for m in LOADER_PROGRESS.finditer(text)]
    st = values.get("status")
    if st is not None and st >= 1 << 63:                       # the loader writes (uint64_t)(int64_t)status
        st -= 1 << 64
    return dict(found=bool(values), values=values, status=st, status_name=STATUS.get(st, "unknown(%s)" % st) if st is not None else None,
                progress=progress)


def read_probe(text):
    """The probe's lines in a kernel text. The lines may carry a prefix (a timestamp) and are not anchored."""
    m = PROBE_BANNER.search(text)
    at = [dict(at=int(a), sha256=d, sec=float(s)) for a, d, s in PROBE_AT.findall(text)]
    fin = PROBE_FINAL.search(text)
    op, rd, rg = PROBE_OPEN.search(text), PROBE_READ.search(text), PROBE_READING.search(text)
    return dict(banner_pid=int(m.group(1)) if m else None, reading=dict(device=rg.group(1), chunk=int(rg.group(2))) if rg else None, progress=at,
                final=dict(bytes=int(fin.group(1)), sha256=fin.group(2), sec=float(fin.group(3))) if fin else None,
                cannot_open=dict(device=op.group(1), errno=int(op.group(2))) if op else None,
                read_failed=dict(after=int(rd.group(1)), errno=int(rd.group(2))) if rd else None,
                done_line=PROBE_DONE in text, seen=bool(m or at or fin or op or rd or rg))


def read_delivery(directory):
    """The companion's record. delivery.json is the summary written last; delivery.jsonl is the fsynced journal and is what remains if the process was killed.
    -> None when neither exists."""
    d = Path(directory) if directory else None
    if d is None or not d.is_dir():
        return None
    doc, events = None, []
    p = d / "delivery.json"
    if p.exists():
        try:
            doc = json.loads(p.read_text())
        except ValueError:
            pass                                                  # a torn or foreign summary: the journal below is what is left
    j = d / "delivery.jsonl"
    if j.exists():
        for line in j.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass                                              # a torn last line of a killed process
    if doc is None and not events:
        return None
    marks = [e for e in events if e.get("event") == "progress"]
    final_ev = next((e for e in reversed(events) if e.get("event") == "final"), None)
    ready = next((e for e in events if e.get("event") == "ready"), None)
    out = dict(source="json" if doc is not None else "journal", summary_written=doc is not None, events=len(events),
               reconnects=sum(1 for e in events if e.get("event") == "reconnect"),
               waited_s=ready.get("waited_s") if ready else None, marks=[dict(host_bytes=e.get("host_bytes"), seconds=e.get("seconds"),
                                                                            mb_per_s_total=e.get("mb_per_s_total")) for e in marks])
    if doc is not None:
        dev = doc.get("device") if isinstance(doc.get("device"), dict) else None
        out.update(outcome=doc.get("outcome"), size=doc.get("size"), sha256=doc.get("sha256"), error=doc.get("error"), device=dev,
                   committed=dev.get("committed") if dev else None, seconds=doc.get("seconds"), mb_per_s=doc.get("mb_per_s"), mib_per_s=doc.get("mib_per_s"),
                   host_bytes_written=doc.get("host_bytes_written"))
    else:
        out.update(outcome=final_ev.get("outcome") if final_ev else "killed-no-final", size=None, sha256=None, error=None, device=None, committed=None,
                   seconds=None, mb_per_s=None, mib_per_s=None, host_bytes_written=None,
                   last_host_bytes=marks[-1].get("host_bytes") if marks else None)
    return out


def classify_return(first_return):
    """The ending, against the clocks measured before this image (see the module docstring)."""
    if not first_return:
        return dict(klass=None, dt=None, cls="no-return-seen")
    dt, klass = first_return.get("dt"), first_return.get("klass")
    if klass == "download":
        cls = "download-other-early" if dt < CAP_RETURN[0] else "cap-reset" if dt <= CAP_RETURN[1] else "download-other-late"
    elif klass == "upload":
        cls = "upload"
    else:
        cls = "not-download-" + str(klass)
    return dict(klass=klass, dt=dt, cls=cls)


def expected_return_window():
    """The window the deadline clock gives for this image's deadline, before the margins: (low, high) in host seconds."""
    return tuple(BASELINE_RETURN_S + (DEADLINE_S - BASELINE_DEADLINE_S) * k for k in LOADER_SECOND)


def host_prefix_digests(path, ats):
    """{at: sha256 hex of the first `at` bytes of the file} for each distinct `at` that fits in the file. One pass over the file."""
    want = sorted({a for a in ats if a >= 0})
    out, h, pos = {}, hashlib.sha256(), 0
    with open(path, "rb") as f:
        for a in want:
            while pos < a:
                b = f.read(min(8 << 20, a - pos))
                if not b:
                    break
                h.update(b)
                pos += len(b)
            if pos == a:
                out[a] = h.copy().hexdigest()
    return out


def check_lines(probe, delivered, size, digests):
    """Compare each digest line of the probe with the host's prefix digest. A line that covers bytes the device never reported as committed is not
    judged (the reserve holds whatever was there before). -> dict(lines, bad_within, bad_beyond, last_good, first_bad, final_match, final_ok, final_bad)."""
    lines = []
    for p in probe["progress"]:
        want = digests.get(p["at"])
        lines.append(dict(at=p["at"], sec=p["sec"], match=None if want is None else want == p["sha256"], inside=p["at"] <= delivered))
    fin = probe["final"]
    final_match = final_ok = None
    final_bad = False
    if fin is not None:
        want = digests.get(fin["bytes"])
        final_match = want is not None and want == fin["sha256"]
        final_ok = final_match and fin["bytes"] == size
        # inside the delivered span, a wrong digest is a mismatch; so is a final line that covers less than the image when all of it was delivered
        final_bad = (fin["bytes"] <= delivered and not final_match) or (delivered == size and fin["bytes"] != size)
    bad_within = [l["at"] for l in lines if l["inside"] and l["match"] is not True]
    good = [l["at"] for l in lines if l["match"] is True]
    bad_ats = bad_within + ([fin["bytes"]] if final_bad else [])
    return dict(lines=lines, bad_within=bad_within, bad_beyond=[l["at"] for l in lines if not l["inside"] and l["match"] is not True],
                last_good=max(good) if good else None, first_bad=min(bad_ats) if bad_ats else None, final_match=final_match, final_ok=final_ok,
                final_bad=final_bad)


# ---------------------------------------------------------------------------------------------------------------- the rule
ROWS = {1: "pass", 2: "digest-or-length-mismatch", 3: "short-transfer", 4: "upload-ending-with-cut-hash", 5: "cannot-open-root-device", 6: "read-failure-or-empty-device",
        7: "delivery-path-never-worked", 8: "other", 9: "loader-refused-the-receive-phase", 10: "chunk-checksum-failure"}


def decide(size, delivery, loader, probe, root, ending, digests, chain_verdict=None):
    """-> dict(row, name, reasons, facts). `delivery` may be None (no record); `loader` is read_loader_values(); `probe` is read_probe(); `root` is the NAT-065
    root reading (outcome, exit_status); `ending` is classify_return(); `digests` maps a byte count to the host's SHA-256 of that prefix;
    `chain_verdict` is NAT-065's verdict for the boot (row 1 needs PASS: the text is this image's own, from one contiguous boot)."""
    st = loader["status"]
    dev_committed = delivery.get("committed") if delivery else None
    ld_committed = loader["values"].get("committed")
    ld_bytes = loader["values"].get("bytes")
    committed = ld_committed if ld_committed is not None else dev_committed
    exit_status = (root or {}).get("exit_status")
    outcome = delivery.get("outcome") if delivery else None
    error = (delivery or {}).get("error") or ""
    chk = check_lines(probe, committed or 0, size, digests)
    facts = dict(size=size, loader_bytes=ld_bytes, committed=committed, committed_device=dev_committed, committed_loader=ld_committed, delivery_outcome=outcome, delivery_error=error or None,
                 loader_status=st, loader_status_name=loader["status_name"], exit_status=exit_status, exit_class=EXIT_CLASSES.get(exit_status), ending=ending["cls"],
                 return_dt=ending["dt"], probe=dict(banner_pid=probe["banner_pid"], progress_lines=len(probe["progress"]), final=probe["final"],
                                                    cannot_open=probe["cannot_open"], read_failed=probe["read_failed"]),
                 check=chk, rate=dict(seconds=(delivery or {}).get("seconds"), mb_per_s=(delivery or {}).get("mb_per_s"),
                                      mib_per_s=(delivery or {}).get("mib_per_s"), reconnects=(delivery or {}).get("reconnects")))
    why = []
    if dev_committed is not None and ld_committed is not None and dev_committed > ld_committed:
        why.append("the companion read committed=%d from the device but the loader's final record says %d: the records disagree" % (dev_committed, ld_committed))

    if ld_bytes is not None and ld_bytes != size:
        why.append("the loader reserved %d bytes but the host's image is %d" % (ld_bytes, size))

    def done(row, *reasons, variant=None):
        return {"row": row, "name": ROWS[row], "variant": variant, "reasons": list(reasons) + why, "pass": row == 1, "facts": facts}

    short = committed is not None and committed < size
    if st in LOADER_VOID:
        return done(9, "the loader's receive phase ended %s (%s): the stream was not accepted or not trusted, read-back results are void" % (loader["status_name"], st))
    if outcome in ("never-ready", "refused-by-device") or (st in LOADER_NO_PATH and short):
        return done(7, "the delivery path never worked: companion %s, loader %s" % (outcome, loader["status_name"]))
    sent = (delivery or {}).get("host_bytes_written")
    if outcome == "failed" and (committed == 0 or (committed is None and not sent)):
        return done(7, "the companion failed before the device accepted a byte: %s" % (error or "no error text"))
    if "DeliveryError" in error and short:
        return done(10, "a chunk failed its checksum on every retry: %s" % error)
    if chk["bad_within"] or chk["final_bad"]:
        where = chk["first_bad"]
        return done(2, "a digest line differs from the host's prefix digest inside the delivered span (first at %s, last good at %s)" % (where, chk["last_good"]))
    if probe["cannot_open"] or exit_status == 0x61:
        return done(5, "the probe could not open the root device: %s" % (probe["cannot_open"] or "exit status 0x61"))
    if probe["read_failed"] or exit_status in (0x62, 0x63):
        return done(6, "the probe's read failed or the device is empty: %s (exit status %s)" % (probe["read_failed"], exit_status))
    if short:
        if outcome == "failed":
            cause = "the companion failed: %s" % (error or "no error text")
        elif outcome == "cap-reached":
            cause = "the companion's delivery cap"
        elif st == 6:
            cause = "the loader's cap"
        else:
            cause = "unknown (companion %s, loader %s)" % (outcome or "no record", loader["status_name"])
        return done(3, "committed %d of %d bytes; ended by %s; every digest line inside the delivered span matches" % (committed, size, cause))
    # Everything below needs the whole image committed.
    if committed != size:
        return done(8, "no committed offset in any record (loader values absent; companion outcome %s%s)" % (outcome or "none", ": " + error if error else ""))
    conds = {
        "the chain verdict is PASS": chain_verdict == "PASS",
        "the companion delivered": outcome == "delivered",
        "the loader reports done": st == 0,
        "the loader's reserve is the size of the image": ld_bytes == size,
        "the probe's final line is the host's digest of the whole image": chk["final_ok"] is True,
        "every progress line equals the host's prefix digest": all(l["match"] is True for l in chk["lines"]),
        "PID 1 exited with status 81": exit_status == EXIT_OK,
        "the ending is the cap reset": ending["cls"] == "cap-reset",
    }
    if all(conds.values()):
        return done(1, "the whole image was committed and read back unchanged: " + "; ".join(conds))
    if probe["final"] is None:
        if not probe["seen"]:
            return done(8, "the whole image was committed but no probe line was seen: the probe did not run, or the ring lost it")
        if ending["cls"] == "upload":
            return done(4, "no final digest line and the phone returned as SEC_UPLOAD (+%.1f s): the unpetted watchdog ended the run" % (ending["dt"] or 0))
        if outcome == "delivered" and st == 0:
            return done(3, "delivery complete and every digest line equals the host's, but the hash was cut short (last at %s) and the ending is %s" %
                        (chk["last_good"], ending["cls"]), variant="a")
    return done(8, "pass conditions not met: " + "; ".join(k for k, v in conds.items() if not v))


# ---------------------------------------------------------------------------------------------------------------- the run
def analyze(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic=False, **kw):
    old = A65.IMAGE
    A65.IMAGE = IMAGE
    try:
        out = _ANALYZE65(root, events, report, allow_synthetic, **kw)
    finally:
        A65.IMAGE = old
    texts = (out.get("kernel_log") or {}).get("texts") or {}
    text = "\n".join(texts[k] for k in sorted(texts)) if texts else ""
    lines = []
    boot = out.get("boot")
    if boot and boot.get("name"):
        lines = A65.A59.boot_texts(root, boot["name"])
    loader = read_loader_values(lines)
    probe = read_probe(text)
    delivery = read_delivery(delivery_dir)
    ending = classify_return((out.get("usb") or {}).get("first_return"))
    ats = [p["at"] for p in probe["progress"]] + ([probe["final"]["bytes"]] if probe["final"] else []) + [size]
    digests = host_prefix_digests(image_path, ats) if image_path else {}
    if digests.get(size) != sha256:
        raise ValueError("the root file is not the image the run is judged against (sha256 %s, expected %s)" % (digests.get(size), sha256))
    out["image"] = IMAGE
    out["nat078"] = dict(decision=decide(size, delivery, loader, probe, out.get("root"), ending, digests, out.get("verdict")), loader=dict(
        found=loader["found"], status=loader["status"], status_name=loader["status_name"], values=loader["values"], progress=loader["progress"]),
        delivery=delivery, probe=probe, ending=ending, kernel=dict(md=read_md(text), vm=read_vm(text)), chain_verdict=out.get("verdict"),
        loader_text=A75.read_loader(lines))
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
