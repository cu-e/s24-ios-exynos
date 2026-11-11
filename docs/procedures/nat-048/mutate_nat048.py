#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-048 mutation check: each mutant changes one thing in usb_watch.py, analyze_reset.py or session_reset_canary.py; the host test
file must fail on it. A mutant whose source does not compile, or whose old text does not occur exactly once, is INVALID (not
killed). Survivors are listed; the expected equivalents are named in README.md.

    python3 -I docs/procedures/nat-048/mutate_nat048.py --out artifacts/nat-048/mutation-001 [--jobs 4] [--only NAME]

The mutated driver runs in a tree that mirrors the project root: symlinks to the real artifacts/nat-044, devices/ and docs/decisions
(so the real-tree gate tests see the same decision files as the unmutated run) and private artifacts/nat-022 and artifacts/nat-048
(the driver takes a non-blocking flock on artifacts/nat-022/recovery-write.lock: a shared lock made parallel mutants crash before
they wrote a report, which looked like a kill). The fake `adb` on PATH keeps a mutated driver from reaching any phone."""
import argparse, concurrent.futures, json, os, py_compile, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = {"watch": "usb_watch.py", "analyze": "analyze_reset.py", "driver": "session_reset_canary.py"}

M = []


def mut(name, which, old, new):
    M.append((name, which, old, new))


# --- usb_watch.py
mut("W01-interface-dirs-are-devices", "watch", 'DEV_RE = re.compile(r"^\\d+-\\d+(\\.\\d+)*$")', 'DEV_RE = re.compile(r"^\\d+-\\d+(\\.\\d+)*")')
mut("W02-devnum-change-ignored", "watch", 'elif old["devnum"] != new["devnum"]:', "elif False:")
mut("W03-product-change-ignored", "watch", '(old["product"], old["manufacturer"], old["pid"]) != (new["product"], new["manufacturer"], new["pid"])',
    '(old["manufacturer"], old["pid"]) != (new["manufacturer"], new["pid"])')
mut("W04-pid-change-ignored", "watch", '(old["product"], old["manufacturer"], old["pid"]) != (new["product"], new["manufacturer"], new["pid"])',
    '(old["product"], old["manufacturer"]) != (new["product"], new["manufacturer"])')
mut("W05-serial-leaks", "watch", 'busnum=a["busnum"], devnum=a["devnum"])', 'busnum=a["busnum"], devnum=a["devnum"], serial=read_attr(d, "serial"))')
mut("W06-no-vendor-filter", "watch", 'if self.vids is not None and a["idVendor"].lower() not in self.vids:', "if False:")
mut("W07-default-filter-too-wide", "watch", 'DEFAULT_VIDS = ("04e8", "18d1", "1209")', 'DEFAULT_VIDS = ("04e8", "18d1", "1209", "8087")')
mut("W08-partial-device-accepted", "watch", 'if not a["idVendor"] or not a["idProduct"] or a["devnum"] is None:', 'if not a["idVendor"]:')
mut("W09-no-fsync", "watch", "os.fsync(self.f.fileno())", "pass")
mut("W10-no-flush", "watch", "            self.f.flush()\n", "")
mut("W11-log-overwritten", "watch", 'self.f = open(out, "x") if out else None', 'self.f = open(out, "w") if out else None')
mut("W12-no-stop-record", "watch", 'rec = self.emit("stop")', "rec = None")
mut("W13-no-initial-devices", "watch", 'initial=sorted(self.known.values(), key=lambda d: d["path"])', "initial=[]")
mut("W14-known-not-updated", "watch", "        self.known = now\n        return out", "        return out")
mut("W15-wall-clock-is-monotonic", "watch", "t_unix=round(self.clock(), 6)", "t_unix=round(self.mono(), 6)")
mut("W16-sigterm-kills", "watch", "signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))", "signal.signal(signal.SIGTERM, signal.SIG_DFL)")
mut("W17-seconds-ignored", "watch", "while not stopping and time.monotonic() < end:", "while not stopping:")
mut("W18-all-ignored", "watch", "None if a.all else tuple(", "tuple(")
mut("W19-seq-not-counted", "watch", "self.seq += 1", "self.seq = 1")
mut("W20-vid-case-sensitive-start", "watch", 'vid=a["idVendor"].lower()', 'vid=a["idVendor"]')
# --- analyze_reset.py
mut("A01-deadline-boundary", "analyze", "if dt < deadline:", "if dt <= deadline:")
mut("A02-ceiling-boundary", "analyze", 'klass in ("download", "upload") and dt <= ceiling', 'klass in ("download", "upload") and dt < ceiling')
mut("A03-baseline-tolerance-boundary", "analyze", "abs(dt - BASELINE_UPLOAD_S) <= BASELINE_TOLERANCE_S", "abs(dt - BASELINE_UPLOAD_S) < BASELINE_TOLERANCE_S")
mut("A04-ceiling-formula", "analyze", "ceiling = BASELINE_UPLOAD_S - (wdt - deadline) / 2.0", "ceiling = BASELINE_UPLOAD_S - (wdt - deadline)")
mut("A05-late-watcher-accepted", "analyze", 'if starts[0]["t_unix"] > t0:', 'if starts[0]["t_unix"] > t0 + 1.0:')
mut("A06-coverage-too-short", "analyze", "COVERAGE_S = BASELINE_UPLOAD_S + 25.0", "COVERAGE_S = BASELINE_UPLOAD_S + 5.0")
mut("A07-coverage-boundary", "analyze", "if coverage_end >= COVERAGE_S:", "if coverage_end > COVERAGE_S:")
mut("A08-unsent-reboot-accepted", "analyze", 'report.get("reboot_requested_at") if report.get("reboot_sent") else None', 'report.get("reboot_requested_at")')
mut("A09-other-vendors-count", "analyze", 'e.get("vid") == SAMSUNG and e["t_unix"] >= t0', 'e["t_unix"] >= t0')
mut("A10-before-t0-counts", "analyze", 'e["t_unix"] >= t0]', 'e["t_unix"] >= t0 - 10]')
mut("A11-upload-class-lost", "analyze", 'if "UPLOAD" in p.upper():', 'if p == "UPLOAD":')
mut("A12-upload-supports-the-word", "analyze", 'if klass == "download":\n            out["U3_U4"]', 'if klass in ("download", "upload"):\n            out["U3_U4"]')
mut("A13-android-note-lost", "analyze", '    elif klass == "android":\n        out["U1_U2"]', '    elif False:\n        out["U1_U2"]')
mut("A14-android-not-refuting", "analyze", '    elif klass == "android":\n        out["U3_U4"]', '    elif False:\n        out["U3_U4"]')
mut("A15-never-left-not-checked", "analyze", "if leave is None:", "if False:")
mut("A16-earlier-appearance-is-the-return", "analyze", 'e["event"] == "appear" and e["t_unix"] > leave["t_unix"]', 'e["event"] == "appear"')
mut("A17-deadline-and-wdt-swapped", "analyze", 'deadline, wdt, reason = meta["deadline_s"], meta["wdt_s"], int(meta["reason"], 16)', 'wdt, deadline, reason = meta["deadline_s"], meta["wdt_s"], int(meta["reason"], 16)')
mut("A18-coverage-without-stop", "analyze", "(stops[-1] if stops else max(events, key=lambda e: e[\"t_unix\"]))", "(stops[-1] if stops else events[0])")
mut("A19-baseline-upload-time", "analyze", "BASELINE_UPLOAD_S = 95.0", "BASELINE_UPLOAD_S = 90.0")
mut("A20-analysis-not-written", "analyze", "    if a.out:\n", "    if False:\n")
mut("A21-missing-log-crashes", "analyze", "    except OSError:\n        events = []", "    except KeyError:\n        events = []")
mut("A22-no-stop-note-lost", "analyze", "    if not stops:\n", "    if False:\n")
mut("A23-verdict-for-the-bl-word", "analyze", '0x1234560D: "U4 (INFORM3 = bootloader word 0x1234560d)"', '0x1234560D: "U3 (INFORM3 = bootloader word 0x1234560d)"')
# --- session_reset_canary.py
mut("D01-no-gate", "driver", "report['decision_file']=gate(a.image,cfg).name;save()", "pass")
mut("D02-ambiguous-gate-accepted", "driver", "assert len(found)==1,", "assert len(found)>=1,")
mut("D03-hashes-not-required-in-the-decision", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in ('decision 0019',):")
mut("D04-decision-0019-not-required", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA']):")
mut("D05-glob-matches-the-other-image", "driver", "glob('*-nat046-%s-single-run-*.md'%image)", "glob('*-nat046-%s*.md'%image)")
mut("D06-marker-overwritable", "driver", "with marker.open('x') as f:", "with marker.open('w') as f:")
mut("D07-marker-shared-by-images", "driver", "('artifacts/nat-048/native-attempt-%s-used.json'%a.image)", "('artifacts/nat-048/native-attempt-used.json')")
mut("D08-no-watcher", "driver", "            watcher_start()\n", "            pass\n")
mut("D09-watcher-after-reboot", "driver", "            watcher_start()\n            # The sole native reboot in this session. No later reboot or retry.\n            report['reboot_sent']=True;report['reboot_requested_at']=now();save()\n            run(['adb','reboot','recovery'])\n",
    "            # The sole native reboot in this session. No later reboot or retry.\n            report['reboot_sent']=True;report['reboot_requested_at']=now();save()\n            run(['adb','reboot','recovery'])\n            watcher_start()\n")
mut("D10-start-record-not-awaited", "driver", "if any(e['event']=='start' for e in read_events(log)):", "if True:")
mut("D11-watcher-not-detached", "driver", "start_new_session=True", "start_new_session=False")
mut("D12-watcher-too-short", "driver", "WATCH_S=240 ", "WATCH_S=20 ")
mut("D13-no-selftest", "driver", "if not a.restore:watcher_selftest()", "pass")
mut("D14-watcher-failure-ignored", "driver", "raise RuntimeError('the USB watcher did not log its start record: no reboot')", "pass")
mut("D15-no-readback-check", "driver", "assert measured==expected,'full RECOVERY readback mismatch'", "pass")
mut("D16-no-restore-after-abort", "driver", "write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()", "pass")
mut("D17-low-battery-accepted", "driver", "assert int(values['level'])>=50", "assert int(values['level'])>=0")
mut("D18-busy-dd-ignored", "driver", "return result=='idle'", "return True")
mut("D19-decision-file-not-recorded", "driver", "report['decision_file']=gate(a.image,cfg).name;save()", "gate(a.image,cfg);save()")
mut("D20-report-dir-reusable", "driver", "a.out.mkdir(parents=True,exist_ok=False)", "a.out.mkdir(parents=True,exist_ok=True)")
mut("D21-restore-runs-the-selftest", "driver", "if not a.restore:watcher_selftest()", "watcher_selftest()")
mut("D22-start-record-flag-not-saved", "driver", "report['watcher']['start_record_seen']=True;save();return", "save();return")
mut("D23-pins-swapped", "driver", "NEW_SHA='a3189ca7914b48b0b5d3a575c2936b6425bccdafde16e66c34fedf1f3d1ea34e'", "NEW_SHA='d4e1454c198379328c91fc63a5aaf26e58c1747e2b696ca1b92719211bedfebd'")
mut("D24-stock-not-required-for-launch", "driver", "if not a.restore: assert initial==STOCK_SHA, 'launch requires unchanged stock RECOVERY'", "pass")
mut("D25-reboot-before-readback-report", "driver", "report['outcome']='candidate-written-readback-confirmed';save()\n", "report['outcome']='candidate-written-readback-confirmed'\n")


def build_tree(base, which, old, new):
    tree = base / "tree"
    d = tree / "docs/procedures/nat-048"
    d.mkdir(parents=True)
    (tree / "docs").mkdir(exist_ok=True)
    # private artifacts/nat-022 and artifacts/nat-048 (the driver's flock and one-shot markers must not be shared between parallel
    # mutants or with the real tree); the pinned package and the stock image are read through symlinks
    (tree / "artifacts/nat-022").mkdir(parents=True)
    (tree / "artifacts/nat-048").mkdir()
    os.symlink(ROOT / "artifacts/nat-044", tree / "artifacts/nat-044")
    os.symlink(ROOT / "devices", tree / "devices")
    os.symlink(ROOT / "docs/decisions", tree / "docs/decisions")
    for key, fn in FILES.items():
        shutil.copy(HERE / fn, d / fn)
    target = d / FILES[which]
    text = target.read_text()
    n = text.count(old)
    if n != 1:
        return None, "old text occurs %d times" % n
    target.write_text(text.replace(old, new))
    try:
        py_compile.compile(str(target), doraise=True, cfile=str(base / "x.pyc"))
    except py_compile.PyCompileError as exc:
        return None, "does not compile: %s" % exc.msg.splitlines()[-1]
    return d, None


def run_one(item, out):
    name, which, old, new = item
    with tempfile.TemporaryDirectory(prefix="mut048-") as t:
        base = Path(t)
        d, err = build_tree(base, which, old, new)
        if d is None:
            return dict(name=name, outcome="INVALID", detail=err)
        env = dict(os.environ, NAT048_DRIVER=str(d / FILES["driver"]), NAT048_WATCH=str(d / FILES["watch"]), NAT048_ANALYZE=str(d / FILES["analyze"]))
        try:
            r = subprocess.run([sys.executable, "-I", str(HERE / "test_nat048.py"), "-f"], capture_output=True, text=True, env=env, timeout=900)
        except subprocess.TimeoutExpired:
            return dict(name=name, outcome="killed", detail="timeout (a hang is a failure)")
        tail = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
        (out / (name + ".log")).write_text(r.stdout + r.stderr)
        if r.returncode == 0:
            return dict(name=name, outcome="SURVIVED", detail="")
        return dict(name=name, outcome="killed", detail=tail[0] if tail else "exit %d" % r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", action="append")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    base = subprocess.run([sys.executable, "-I", str(HERE / "test_nat048.py")], capture_output=True, text=True)
    (a.out / "baseline.log").write_text(base.stdout + base.stderr)
    if base.returncode != 0:
        print("the unmutated tests fail; nothing to compare against")
        return 2
    items = [m for m in M if not a.only or m[0] in a.only]
    results = []
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(lambda m: run_one(m, a.out), items):
            results.append(res)
            print("%-8s %-45s %s" % (res["outcome"], res["name"], res["detail"][:110]), flush=True)
    summary = dict(mutants=len(items), killed=sum(r["outcome"] == "killed" for r in results), survived=[r["name"] for r in results if r["outcome"] == "SURVIVED"],
                   invalid=[r["name"] for r in results if r["outcome"] == "INVALID"], results=results)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print("killed %d/%d; survived %s; invalid %s" % (summary["killed"], len(items), summary["survived"], summary["invalid"]))
    return 0 if not summary["survived"] and not summary["invalid"] else 1


if __name__ == "__main__":
    sys.exit(main())
