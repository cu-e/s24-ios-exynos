#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-057 mutation check: apply one small change at a time to the session driver or the analyser and require that test_nat057.py fails.

Driver mutants run the flow tests only (OpenGateFlow, with the source-text pins switched off by NAT057_BEHAVIOUR_ONLY=1, so a kill is a
behavioural kill: the driver copy is run in a scratch tree against the fake adb). Analyser mutants run Verdicts. A mutant is "equivalent"
when no input the program can see distinguishes it; those are listed with the reason and are not counted as survivors.
Usage: python3 -I mutants.py [--json OUT] [--jobs N] [--only ID,ID]. Host only; no device, no network."""
import argparse, concurrent.futures, json, os, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DRIVER = HERE / "session_nat052.py"
ANALYZE = HERE / "analyze_nat052.py"
TESTS = HERE / "test_nat057.py"

# (id, target, old, new, what it breaks)
MUTANTS = [
    ("D01-nat043-not-required", "driver", "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052')", "REQUIRED_DONE=('NAT-039','NAT-046','NAT-052')", "the log channel need not be proven first"),
    ("D02-nat052-not-required", "driver", "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052')", "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043')", "the image task need not be done"),
    ("D03-no-registry-need-for-nat046", "driver", "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052')", "REQUIRED_DONE=('NAT-039','NAT-043','NAT-052')", "the reset canary need not be done"),
    ("D04-decision-glob-of-nat043", "driver", "glob('*-nat052-%s-single-run-*.md'%image)", "glob('*-nat043-%s-single-run-*.md'%image)", "another task's decision file opens the gate"),
    ("D05-marker-elsewhere", "driver", "native-attempt-%s-used.json'%a.image", "native-attempt-%s-done.json'%a.image", "the one-shot marker has another name"),
    ("D06-marker-overwritable", "driver", "marker.open('x')", "marker.open('w')", "the marker no longer stops a second run"),
    ("D07-payload-hash-not-needed", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['NEW_SHA'],'decision 0019')", "the decision need not name the payload hash"),
    ("D08-recovery-hash-not-needed", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['CANARY_SHA'],'decision 0019')", "the decision need not name the RECOVERY hash"),
    ("D09-decision-0019-not-needed", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'])", "the decision need not name decision 0019"),
    ("D10-any-decision-count", "driver", "assert len(found)==1,", "assert len(found)>=1,", "two decision files are accepted (the first is taken)"),
    ("D11-native-flag-ignored", "driver", "if state['project']['permissions'].get('native') is not True:return", "if False:return", "the native permission flag is not read"),
    ("D12-decision-value-ignored", "driver", "native[-1].get('value') is not True or ", "", "a closing record is taken for an opening one"),
    ("D13-first-decision-used", "driver", "native[-1].get('value') is not True or native[-1].get('decision')!='docs/decisions/'+decision.name", "native[0].get('value') is not True or native[0].get('decision')!='docs/decisions/'+decision.name", "an older opening record is used"),
    ("D14-citation-ignored", "driver", " or native[-1].get('decision')!='docs/decisions/'+decision.name", "", "the native decision need not cite this decision file"),
    ("D15-blocker-not-enforced", "driver", "assert not (a.execute and blocker),blocker", "assert True", "a closed registry does not stop a launch"),
    ("D16-host-access-skipped", "driver", "host_access();collector_selftest()", "collector_selftest()", "the udev check is skipped"),
    ("D17-collector-selftest-skipped", "driver", "host_access();collector_selftest()", "host_access()", "the collector self-test is skipped"),
    ("D18-watcher-selftest-skipped", "driver", "if not a.restore:watcher_selftest()", "pass", "the watcher self-test is skipped"),
    ("D19-stock-not-required", "driver", "if not a.restore: assert initial==STOCK_SHA, 'launch requires unchanged stock RECOVERY'", "pass", "a launch starts from a RECOVERY that is not stock"),
    ("D20-readback-not-compared", "driver", "assert measured==expected,'full RECOVERY readback mismatch'", "pass", "a wrong readback is accepted"),
    ("D21-collector-not-started", "driver", "            collector_start()\n", "            pass\n", "the collector is not running at the reboot"),
    ("D22-watcher-not-started", "driver", "            watcher_start()\n", "            pass\n", "the USB watcher is not running at the reboot"),
    ("D23-collector-before-watcher", "driver", "            watcher_start()\n            collector_start()\n", "            collector_start()\n            watcher_start()\n", "the start order changes"),
    ("D24-restore-after-abort-missing", "driver", "write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()", "report['outcome']='launch-aborted-stock-restored';save()", "an aborted launch leaves the candidate on RECOVERY"),
    ("D25-battery-floor", "driver", "int(values['level'])>=50", "int(values['level'])>=0", "a low battery is accepted"),
    ("D26-dd-busy-ignored", "driver", "    def dd_idle():\n        # No restoration is launched alongside an unconfirmed remote writer.\n        result=shell(\"su -c 'if pidof dd >/dev/null; then echo busy; else echo idle; fi'\")\n        return result=='idle'",
     "    def dd_idle():\n        return True", "a running remote dd is ignored"),
    ("D27-reboot-flag-late", "driver", "report['reboot_sent']=True;report['reboot_requested_at']=now();save()\n            run(['adb','reboot','recovery'])", "run(['adb','reboot','recovery'])\n            report['reboot_sent']=True;report['reboot_requested_at']=now();save()",
     "T0 is recorded after the reboot command returns, and a failed command is not marked as sent"),
    ("D28-marker-after-write", "driver", "            with marker.open('x') as f:\n                json.dump(dict(at=now(),image=a.image,image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\\n');f.flush();os.fsync(f.fileno())\n            write(candidate,NEW_SHA)",
     "            write(candidate,NEW_SHA)\n            with marker.open('x') as f:\n                json.dump(dict(at=now(),image=a.image,image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\\n');f.flush();os.fsync(f.fileno())",
     "the marker is written after the RECOVERY write, so a failed write can be repeated"),
    # --- analyser
    ("A01-provenance-ignored", "analyze", "if verdict in VERDICTS and out.get(\"provenance\") != A49.LIVE:", "if False:", "a synthetic archive gets a plain verdict"),
    ("A02-synthetic-plain", "analyze", "verdict = \"simulated-\" + verdict", "verdict = verdict", "allow-synthetic leaves a plain verdict"),
    ("A03-integrity-ignored", "analyze", "    if arch[\"problems\"]:\n        return done(", "    if False:\n        return done(", "a corrupted archive is judged"),
    ("A04-t0-ignored", "analyze", "    if not when:\n        return done(", "    if False:\n        return done(", "a run without T0 is judged"),
    ("A05-late-collector-accepted", "analyze", "    if started > t0:", "    if False:", "a collector started after the reboot request is accepted"),
    ("A06-foreign-boot-id", "analyze", "(b[\"device_id\"] or \"\")[16:] == out[\"expected_boot_id_tail\"]", "True", "any boot is taken as this image's"),
    ("A07-early-record-accepted", "analyze", "        if b[\"first_received_unix\"] < t0:", "        if False:", "a record from before the request is accepted"),
    ("A08-late-record-accepted", "analyze", "        if b[\"first_received_unix\"] - t0 > A49.RECEIVE_WINDOW_S:", "        if False:", "a record far after the request is accepted"),
    ("A09-usb-log-disagreement-ignored", "analyze", "        if view[\"covers_window\"] and view[\"monitor_appear_dt\"] is None:", "        if False:", "a boot the USB log never saw appear is accepted"),
    ("A10-exception-not-found", "analyze", "        if exc is not None or loader_exc:", "        if False:", "an exception is reported as PASS/PARTIAL"),
    ("A11-notes-not-required", "analyze", "        why += note_problems(prog)\n", "", "the channel alone is a PASS"),
    ("A12-no-note-is-pass-ready", "analyze", "        return [\"no CK note arrived: nothing is known about the kernel\"]", "        return []", "an empty note list is complete"),
    ("A13-first-note-any", "analyze", "    if stops[0][\"n\"] != 1:", "    if False:", "a missing first note is accepted"),
    ("A14-gaps-ignored", "analyze", "    if prog[\"gaps\"]:", "    if False:", "skipped note numbers are accepted"),
    ("A15-final-bit-ignored", "analyze", "    if not prog[\"reached_final\"]:", "    if False:", "a run that ends early is complete"),
    ("A16-hold-ignored", "analyze", "    if not prog[\"held\"]:", "    if False:", "a missing HOLD is accepted"),
    ("A17-final-position-ignored", "analyze", "    elif (last[\"n\"], last[\"last\"]) != (len(STOP_LIST), STOP_LIST[-1]):", "    elif False:", "a final-stop bit on a short list is accepted"),
    ("A18-checkpoint-values-ignored", "analyze", "    if wrong:", "    if False:", "notes with the wrong checkpoint are accepted"),
    ("A19-drops-ignored", "analyze", "    if b[\"drop_frames\"]:", "    if False:", "drop frames are accepted"),
    ("A20-ladder-error-ignored", "analyze", "        elif lad[\"err\"] != 0:", "        elif False:", "a stopped ladder is accepted"),
    ("A21-unread-bytes-ignored", "analyze", "    elif end[\"unread_bytes\"]:", "    elif False:", "unread engine bytes are accepted"),
    ("A22-banner-any", "analyze", "    if not banner.startswith(\"NAT047 %s deadline_s=\" % IMAGE) or not banner.endswith(\" fault=0\"):", "    if False:", "another image's banner is accepted"),
    ("A23-monitor-identity-any", "analyze", "    if usb.get(\"vid\") != 0x1209 or usb.get(\"pid\") != 1:", "    if False:", "another USB identity is accepted"),
    ("A24-manifest-ignored", "analyze", "        elif m.get(\"outcome\") != \"complete-received-stream\" or m.get(\"errors\"):", "        elif False:", "an incomplete stream is accepted"),
    ("A25-no-boot-no-enumeration-pass", "analyze", "    return done(\"FAIL\", \"no enumeration of 1209:0001 although the loader ran (%s)\" % ev)", "    return done(\"PASS\", \"no enumeration of 1209:0001 although the loader ran (%s)\" % ev)", "a missing enumeration is a PASS"),
    ("A26-loader-evidence-not-needed", "analyze", "    if ev is None:\n        return done(\"undetermined\"", "    if False:\n        return done(\"undetermined\"", "an absence is a FAIL without evidence that the loader ran"),
    ("A27-short-watcher-accepted", "analyze", "    if not view[\"covers_window\"]:\n        return done(\"undetermined\", \"no boot in the archive, and", "    if False:\n        return done(\"undetermined\", \"no boot in the archive, and", "a watcher that stopped early supports an absence"),
    ("A28-preexisting-monitor-accepted", "analyze", "    if view[\"monitor_preexisting\"]:", "    if False:", "a monitor already on the bus counts as this run's"),
]

# Mutants with no observable difference for any input the program is given (reasons recorded in evidence.json, not counted as survivors):
EQUIVALENT = {}


def run_one(mutant, outdir):
    mid, target, old, new, what = mutant
    src = (DRIVER if target == "driver" else ANALYZE).read_text()
    if src.count(old) != 1:
        return dict(id=mid, target=target, what=what, killed=False, error="old text occurs %d times (needs exactly 1)" % src.count(old))
    d = Path(tempfile.mkdtemp(prefix="mut-%s-" % mid, dir=outdir))
    path = d / ("session_nat052.py" if target == "driver" else "analyze_nat052.py")
    path.write_text(src.replace(old, new))
    env = dict(os.environ)
    env["NAT057_DRIVER" if target == "driver" else "NAT057_ANALYZE"] = str(path)
    env["NAT057_BEHAVIOUR_ONLY"] = "1"
    classes = ["OpenGateFlow"] if target == "driver" else ["Verdicts"]
    t = time.time()
    r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(TESTS), *classes], env=env, capture_output=True, text=True, timeout=900)
    tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
    return dict(id=mid, target=target, what=what, killed=r.returncode != 0, seconds=round(time.time() - t, 1), exit_code=r.returncode, tail=tail,
                killed_by=sorted({l.split()[1] for l in (r.stderr or "").splitlines() if l.startswith(("FAIL: ", "ERROR: "))})[:4])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only")
    a = ap.parse_args()
    # the unmutated suite must pass first, otherwise every mutant would count as killed
    base_env = dict(os.environ, NAT057_BEHAVIOUR_ONLY="1")
    for classes in (["OpenGateFlow"], ["Verdicts"]):
        r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(TESTS), *classes], env=base_env, capture_output=True, text=True, timeout=900)
        if r.returncode:
            print("the unmutated %s tests fail: no mutation result is meaningful\n%s" % (classes, r.stderr[-2000:]))
            return 2
    chosen = [m for m in MUTANTS if not a.only or m[0] in a.only.split(",")]
    scratch = ROOT / "artifacts/nat-057/tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    outdir = Path(tempfile.mkdtemp(prefix="mutants-", dir=scratch))
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        results = list(ex.map(lambda m: run_one(m, outdir), chosen))
    killed = [r for r in results if r["killed"]]
    survived = [r["id"] for r in results if not r["killed"] and r["id"] not in EQUIVALENT]
    for r in results:
        print("%-38s %-8s %s%s" % (r["id"], "killed" if r["killed"] else "SURVIVED", r["what"], "  [%s]" % r["error"] if r.get("error") else ""))
    print("mutants: %d, killed: %d, equivalent: %d, survived: %d" % (len(results), len(killed), len(EQUIVALENT), len(survived)))
    if a.json:
        Path(a.json).write_text(json.dumps(dict(results=results, equivalent=EQUIVALENT, survived=survived), indent=1) + "\n")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
