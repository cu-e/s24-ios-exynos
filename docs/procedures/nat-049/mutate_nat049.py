#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-049 mutation check: each mutant changes one thing in host_access.py, collector_launch.py, analyze_usblog.py or
session_usblog.py; the host test file must fail on it. A mutant whose source does not compile, or whose old text does not occur
exactly once, is INVALID (not killed). Survivors are listed; the expected equivalents are named in README.md.

    python3 -I docs/procedures/nat-049/mutate_nat049.py --out artifacts/nat-049/mutation-001 [--jobs 4] [--only NAME]

Each mutant runs only the test classes of its own module (the other layers cannot see it): host_access -> HostAccess,
collector_launch -> Launcher, analyze_usblog -> Verdicts + RealTreeGate, session_usblog -> RealTreeGate + OpenGateFlow.
Driver mutants run twice: first with the source-text pins switched off (NAT049_BEHAVIOUR_ONLY=1), so that a kill means a flow test
saw the changed behaviour; a mutant that survives that pass is run again with the pins on and reported as `killed-by-pin` if only a
pin sees it (these are lines whose exact text is the safety argument, e.g. the ones inherited unchanged from the NAT-048 driver).

The mutated driver runs in a tree that mirrors the project root: symlinks to every other docs/procedures directory, to the real
artifacts/nat-047, devices/, docs/decisions and state/ (so the real-tree gate tests see the same decision files as the unmutated run)
and private artifacts/nat-022 and artifacts/nat-049 (the driver takes a non-blocking flock on artifacts/nat-022/recovery-write.lock
and writes its one-shot markers under artifacts/nat-049: neither may be shared between parallel mutants or with the real tree). The
fake `adb` on PATH keeps a mutated driver from reaching any phone."""
import argparse, concurrent.futures, json, os, py_compile, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = {"access": "host_access.py", "launch": "collector_launch.py", "analyze": "analyze_usblog.py", "driver": "session_usblog.py"}
ENVS = {"access": "NAT049_ACCESS", "launch": "NAT049_LAUNCH", "analyze": "NAT049_ANALYZE", "driver": "NAT049_DRIVER"}
CLASSES = {"access": ["HostAccess"], "launch": ["Launcher"], "analyze": ["Verdicts", "RealTreeGate"], "driver": ["RealTreeGate", "OpenGateFlow"]}

M = []


def mut(name, which, old, new):
    M.append((name, which, old, new))


# --- host_access.py
mut("H01-comments-are-rules", "access", 'if line and not line.startswith("#"):', "if line:")
mut("H02-continuations-not-joined", "access", 'if line.endswith("\\\\"):', "if False:")
mut("H03-either-identity-is-enough", "access", 'if not (_matches(line, "idVendor", VID) and _matches(line, "idProduct", PID)):', 'if not (_matches(line, "idVendor", VID) or _matches(line, "idProduct", PID)):')
mut("H04-uaccess-ignored", "access", "if re.search(r'TAG\\+=\"uaccess\"', line):", "if False:")
mut("H05-other-read-is-write", "access", "if mode & 0o002:", "if mode & 0o004:")
mut("H06-group-write-bit-not-needed", "access", "if group and group.group(1) in groups and mode & 0o020:", "if group and group.group(1) in groups:")
mut("H07-any-group-will-do", "access", "if group and group.group(1) in groups and mode & 0o020:", "if group and mode & 0o020:")
mut("H08-any-owner-will-do", "access", "if owner and owner.group(1) == user and mode & 0o200:", "if owner and mode & 0o200:")
mut("H09-owner-read-is-write", "access", "if owner and owner.group(1) == user and mode & 0o200:", "if owner and owner.group(1) == user and mode & 0o400:")
mut("H10-status-always-zero", "access", "return 0 if found else 2", "return 0")
mut("H11-run-udev-dir-lost", "access", 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")', 'RULE_DIRS = ("/etc/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")')
mut("H12-usr-lib-dir-lost", "access", 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")', 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/lib/udev/rules.d")')
mut("H13-unreadable-file-aborts", "access", "            except OSError:\n                continue\n            for line", "            except OSError:\n                raise\n            for line")
mut("H14-primary-group-lost", "access", "gids = set(os.getgroups()) | {pwd.getpwuid(uid).pw_gid}", "gids = set(os.getgroups())")
mut("H15-non-rules-files-read", "access", 'sorted(Path(d).glob("*.rules"))', 'sorted(Path(d).glob("*"))')
mut("H16-rule-files-in-reverse-order", "access", 'sorted(Path(d).glob("*.rules"))', 'sorted(Path(d).glob("*.rules"), reverse=True)')
mut("H21-usr-local-lib-dir-lost", "access", 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")', 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")')
mut("H22-legacy-lib-dir-lost", "access", 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")', 'RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d")')
mut("H17-vendor-case-sensitive", "access", "(?i)\\b(?:ATTRS?|ENV)", "\\b(?:ATTRS?|ENV)")
mut("H18-not-equal-accepted", "access", '\\s*==\\s*"%s"', '\\s*[=!]=\\s*"%s"')
mut("H19-rules-dir-option-ignored", "access", "found = find_rule(tuple(a.rules_dir) if a.rules_dir else RULE_DIRS, user, groups)", "found = find_rule(RULE_DIRS, user, groups)")
mut("H20-first-rule-not-returned", "access", '                    return dict(file=str(f), line=line, grant=g)', '                    continue')
# --- collector_launch.py
mut("L01-heartbeat-too-slow", "launch", "HEARTBEAT_S = 2.0", "HEARTBEAT_S = 60.0")
mut("L02-log-overwritten", "launch", 'self.f = open(path, "x")', 'self.f = open(path, "w")')
mut("L03-no-fsync", "launch", "        os.fsync(self.f.fileno())\n", "        pass\n")
mut("L04-no-flush", "launch", "        self.f.flush()\n", "")
mut("L05-no-first-poll", "launch", "if self.last_beat is None or now - self.last_beat >= HEARTBEAT_S:", "if self.last_beat is not None and now - self.last_beat >= HEARTBEAT_S:")
mut("L06-heartbeat-boundary", "launch", "now - self.last_beat >= HEARTBEAT_S", "now - self.last_beat > HEARTBEAT_S")
mut("L07-error-swallowed", "launch", "detail=str(e))\n            raise\n", "detail=str(e))\n            devs = []\n")
mut("L08-no-found-record", "launch", "if len(devs) != self.last_found:", "if False:")
mut("L09-polls-not-counted", "launch", "self.polls += 1", "self.polls = 1")
mut("L10-poll-without-count", "launch", 'self.emit("poll", polls=self.polls, found=len(devs))', 'self.emit("poll", polls=self.polls, found=0)')
mut("L11-selftest-needs-either", "launch", 'res["ok"] = bool(res["libusb_backend"] and res["find_returns_list"])', 'res["ok"] = bool(res["libusb_backend"] or res["find_returns_list"])')
mut("L12-selftest-backend-assumed", "launch", 'res["libusb_backend"] = usb.backend.libusb1.get_backend() is not None', 'res["libusb_backend"] = True')
mut("L13-selftest-monitor-count-zero", "launch", 'res["monitor_devices_now"] = len(found)', 'res["monitor_devices_now"] = 0')
mut("L14-selftest-status-zero", "launch", 'return 0 if res["ok"] else 2', "return 0")
mut("L15-provenance-synthetic", "launch", '"--provenance", "unqualified-live"', '"--provenance", "synthetic"')
mut("L16-seconds-fixed", "launch", '"--seconds", str(a.seconds)]', '"--seconds", "180"]')
mut("L17-no-heartbeat-wrapper", "launch", "logd.PyUsbBackend = lambda *args, **kw: HeartbeatBackend(orig(*args, **kw), a.heartbeat)", "logd.PyUsbBackend = orig")
mut("L18-heartbeat-path-optional", "launch", "if not a.out or not a.heartbeat:", "if not a.out:")
mut("L19-value-errors-escape", "launch", "except (OSError, ValueError) as e:", "except OSError as e:")
mut("L20-failure-status-zero", "launch", '        print("collector_launch: %s" % e, file=sys.stderr)\n        return 2', '        print("collector_launch: %s" % e, file=sys.stderr)\n        return 0')
mut("L21-wall-clock-is-monotonic", "launch", "t_unix=round(self.clock(), 6)", "t_unix=round(self.mono(), 6)")
mut("L22-no-start-record", "launch", '        self.emit("start", pid=os.getpid())\n', "        pass\n")
mut("L23-first-found-silent", "launch", "self.last_found = None", "self.last_found = 0")
mut("L24-found-record-names-other-ids", "launch", 'vid="%04x" % vid, pid="%04x" % pid)', 'vid="%04x" % pid, pid="%04x" % vid)')
mut("L25-selftest-needs-no-list", "launch", 'res["find_returns_list"] = isinstance(found, list)', 'res["find_returns_list"] = True')
# --- analyze_usblog.py
mut("A01-synthetic-gets-a-verdict", "analyze", "if verdict in VERDICTS and out.get(\"provenance\") != LIVE:", "if False:")
mut("A02-simulated-not-labelled", "analyze", '                verdict = "simulated-" + verdict', "                pass")
mut("A03-unknown-image-accepted", "analyze", "    if image not in IMAGES:\n        return done", "    if False:\n        return done")
mut("A04-unsent-reboot-accepted", "analyze", 'report.get("reboot_requested_at") if report.get("reboot_sent") else None', 'report.get("reboot_requested_at")')
mut("A05-damaged-archive-judged", "analyze", '    if arch["problems"]:\n        return done', '    if False:\n        return done')
mut("A06-late-collector-tolerated", "analyze", "    if started > t0:", "    if started > t0 + 5:")
mut("A07-boot-id-head-compared", "analyze", '(b["device_id"] or "")[16:] == out["expected_boot_id_tail"]', '(b["device_id"] or "")[:16] == out["expected_boot_id_tail"]')
mut("A08-any-boot-is-mine", "analyze", 'mine = [b for b in arch["boots"] if (b["device_id"] or "")[16:] == out["expected_boot_id_tail"]]', 'mine = list(arch["boots"])')
mut("A09-early-boot-accepted", "analyze", '        if b["first_received_unix"] < t0:', "        if False:")
mut("A10-window-too-wide", "analyze", "RECEIVE_WINDOW_S = 300.0", "RECEIVE_WINDOW_S = 600.0")
mut("A11-disagreement-ignored", "analyze", 'if view["covers_window"] and view["monitor_appear_dt"] is None:', "if False:")
mut("A12-second-boot-ignored", "analyze", "        if len(mine) > 1:", "        if len(mine) > 2:")
mut("A13-foreign-boot-ignored", "analyze", "        if foreign:\n            why.append(", "        if False:\n            why.append(")
mut("A14-missing-manifest-ignored", "analyze", '            why.append("no manifest.json: the collector did not finish (killed?)")', "            pass")
mut("A15-manifest-outcome-ignored", "analyze", 'if m.get("outcome") != "complete-received-stream" or m.get("errors"):', 'if m.get("errors"):')
mut("A16-manifest-errors-ignored", "analyze", 'if m.get("outcome") != "complete-received-stream" or m.get("errors"):', 'if m.get("outcome") != "complete-received-stream":')
mut("A17-collector-drops-ignored", "analyze", 'if out["collector"] and out["collector"].get("drops"):', "if False:")
mut("A18-partial-is-fail", "analyze", 'return done("PARTIAL", ', 'return done("FAIL", ')
mut("A19-foreign-only-not-refused", "analyze", "    if foreign:\n        return done", "    if False:\n        return done")
mut("A20-no-usb-log-not-refused", "analyze", '    if not view["start_ok"]:', "    if False:")
mut("A21-short-usb-log-not-refused", "analyze", '    if not view["covers_window"]:\n        return done', "    if False:\n        return done")
mut("A22-enumeration-without-record-not-a-fail", "analyze", '    if view["monitor_appear_dt"] is not None:\n        cause', "    if False:\n        cause")
mut("A23-access-cause-lost", "analyze", 'cause = "host-access-denied" if "device-access-denied" in arch["capture_errors"] else None', "cause = None")
mut("A24-preexisting-monitor-ignored", "analyze", '    if view["monitor_preexisting"]:', "    if False:")
mut("A25-absence-without-evidence-is-a-fail", "analyze", "    if ev is None:\n        return done", "    if False:\n        return done")
mut("A26-late-watcher-tolerated", "analyze", 'if starts[0]["t_unix"] > t0:', 'if starts[0]["t_unix"] > t0 + 5:')
mut("A27-coverage-boundary", "analyze", "v[\"covers_window\"] = end >= COVERAGE_S", 'v["covers_window"] = end > COVERAGE_S')
mut("A28-coverage-too-short", "analyze", "COVERAGE_S = 120.0", "COVERAGE_S = 60.0")
mut("A29-early-monitor-counts", "analyze", 'is_mon(e) and e["t_unix"] >= t0), None)', "is_mon(e)), None)")
mut("A30-preexisting-not-read", "analyze", 'v["monitor_preexisting"] = any(is_mon(d) for d in (starts[0].get("initial") or []))', 'v["monitor_preexisting"] = False')
mut("A31-other-vendors-count", "analyze", 'e.get("vid") == AR.SAMSUNG and e["t_unix"] >= t0]', 'e["t_unix"] >= t0]')
mut("A32-return-before-leaving", "analyze", 'e["event"] == "appear" and e["t_unix"] > leave["t_unix"]), None)', 'e["event"] == "appear"), None)')
mut("A33-early-return-is-the-loader", "analyze", 'if deadline <= r["dt"] <= ceiling:', 'if r["dt"] <= ceiling:')
mut("A34-late-return-is-the-loader", "analyze", 'if deadline <= r["dt"] <= ceiling:', 'if deadline <= r["dt"]:')
mut("A35-ceiling-formula", "analyze", "ceiling = AR.BASELINE_UPLOAD_S - (wdt - deadline) / 2.0", "ceiling = AR.BASELINE_UPLOAD_S - (wdt - deadline)")
mut("A36-download-is-the-watchdog", "analyze", 'if r["klass"] == "upload" and abs(r["dt"]', 'if r["klass"] == "download" and abs(r["dt"]')
mut("A37-android-return-is-the-loader", "analyze", 'r["klass"] not in ("download", "upload")', "False")
mut("A38-boot-frames-not-checked", "analyze", 'if b["kinds"]["boot"] != 1 or not b["frame_seq_contiguous"]:', "if False:")
mut("A39-monitor-identity-not-checked", "analyze", 'if usb.get("vid") != 0x1209 or usb.get("pid") != 1:', "if False:")
mut("A40-banner-prefix-not-checked", "analyze", 'if not (b["banner"] or "").startswith(want_banner) or not', 'if not True or not')
mut("A41-banner-fault-flag-not-checked", "analyze", 'or not (b["banner"] or "").endswith(" fault=%d" % fault):', "or False:")
mut("A42-dev-seq-start-not-checked", "analyze", 'if not b["dev_seq_contiguous"] or b["first_dev_seq"] != 0:', 'if not b["dev_seq_contiguous"]:')
mut("A43-dev-seq-gaps-allowed", "analyze", 'if not b["dev_seq_contiguous"] or b["first_dev_seq"] != 0:', 'if b["first_dev_seq"] != 0:')
mut("A44-drop-frames-ignored", "analyze", '    if b["drop_frames"]:', "    if False:")
mut("A45-first-stage-not-checked", "analyze", "    if body[0] != STAGE_ORDER[0]:", "    if False:")
mut("A46-stage-order-not-checked", "analyze", "    if any(b < a for a, b in zip(body, body[1:])):", "    if False:")
mut("A47-exception-stage-anywhere", "analyze", "    if fault and STAGE_EXC in nums and [i for i, n in enumerate(nums) if n == STAGE_EXC] != [len(nums) - 1]:", "    if False:")
mut("A48-missing-ladder-ignored", "analyze", "        if lad is None:\n            why.append", "        if False:\n            why.append")
mut("A49-ladder-stop-ignored", "analyze", '        elif lad["err"] != 0:', "        elif False:")
mut("A50-ladder-lines-not-counted", "analyze", '        elif b["ladder_op_lines"][tag] != lad["nrec"]:', "        elif False:")
mut("A51-missing-end-ignored", "analyze", "    if end is None:\n        why.append", "    if False:\n        why.append")
mut("A52-unread-bytes-ignored", "analyze", '    elif end["unread_bytes"]:', "    elif False:")
mut("A53-plain-image-expects-a-fault", "analyze", "    if fault:\n        if len(efr) != 1:", "    if not fault:\n        if len(efr) != 1:")
mut("A54-several-exceptions-accepted", "analyze", "        if len(efr) != 1:", "        if len(efr) < 1:")
mut("A55-wrong-esr-accepted", "analyze", '        elif efr[0]["esr"] != FAULT_ESR:', "        elif False:")
mut("A56-exception-text-not-required", "analyze", '        if not b["exception_texts"]:', "        if False:")
mut("A57-exception-page-validity-ignored", "analyze", 'if not pg["valid"] or (len(efr) == 1 and', 'if (len(efr) == 1 and')
mut("A58-exception-page-disagreement-ignored", "analyze", 'if not pg["valid"] or (len(efr) == 1 and (pg["esr"], pg["elr"], pg["far"]) != (efr[0]["esr"], efr[0]["elr"], efr[0]["far"])):', 'if not pg["valid"]:')
mut("A59-plain-exception-record-ignored", "analyze", "    elif efr or b[\"exception_texts\"] or b[\"exception_page\"] or STAGE_EXC in", "    elif b[\"exception_texts\"] or b[\"exception_page\"] or STAGE_EXC in")
mut("A60-plain-exception-text-ignored", "analyze", "    elif efr or b[\"exception_texts\"] or b[\"exception_page\"] or STAGE_EXC in", "    elif efr or b[\"exception_page\"] or STAGE_EXC in")
mut("A61-plain-exception-page-ignored", "analyze", "    elif efr or b[\"exception_texts\"] or b[\"exception_page\"] or STAGE_EXC in", "    elif efr or b[\"exception_texts\"] or STAGE_EXC in")
mut("A62-plain-exception-stage-ignored", "analyze", "    elif efr or b[\"exception_texts\"] or b[\"exception_page\"] or STAGE_EXC in [n for n, _ in b[\"stages\"]]:", "    elif efr or b[\"exception_texts\"] or b[\"exception_page\"]:")
mut("A63-fault-esr-changed", "analyze", "FAULT_ESR = 0xF2001234 ", "FAULT_ESR = 0xF2001235 ")
mut("A64-fault-flags-swapped", "analyze", 'IMAGES = {"loader-diag-usbmon": 0, "loader-diag-usbmon-fault": 1}', 'IMAGES = {"loader-diag-usbmon": 1, "loader-diag-usbmon-fault": 0}')
mut("A65-fnv-offset", "analyze", "h = 0xCBF29CE484222325", "h = 0xCBF29CE484222326")
mut("A66-fnv-prime", "analyze", "* 0x100000001B3)", "* 0x100000001B5)")
mut("A67-tail-big-endian", "analyze", 'fnv1a64(image).to_bytes(8, "little").hex()', 'fnv1a64(image).to_bytes(8, "big").hex()')
mut("A68-manifest-hash-ignored", "analyze", "            elif sha256_file(p) != h:", "            elif False:")
mut("A69-unlisted-file-ignored", "analyze", '            if rel not in listed and rel != "manifest.json":', "            if False:")
mut("A70-missing-listed-file-ignored", "analyze", "            if p is None:\n                problems.append", "            if False:\n                problems.append")
mut("A71-chunk-offsets-ignored", "analyze", '        if c["offset"] != pos:', "        if False:")
mut("A72-chunk-hash-ignored", "analyze", 'if len(piece) != c["length"] or hashlib.sha256(piece).hexdigest() != c["sha256"]:', 'if len(piece) != c["length"]:')
mut("A73-chunk-length-ignored", "analyze", 'if len(piece) != c["length"] or hashlib.sha256(piece).hexdigest() != c["sha256"]:', 'if hashlib.sha256(piece).hexdigest() != c["sha256"]:')
mut("A74-trailing-bytes-ignored", "analyze", "    if pos != len(data):", "    if False:")
mut("A75-payload-not-compared", "analyze", "    if joined != payload:", "    if False:")
mut("A76-base64-not-validated", "analyze", 'base64.b64decode(r["frame"].get("data_b64", ""), validate=True)', 'base64.b64decode(r["frame"].get("data_b64", ""))')
mut("A77-schema-not-checked", "analyze", 'or attempt.get("schema") != "early-log-archive-v1":', "or False:")
mut("A78-analysis-not-written", "analyze", "    if a.out:\n", "    if False:\n")
mut("A79-allow-synthetic-ignored", "analyze", "res = analyze(a.archive, events, report, a.image, a.allow_synthetic)", "res = analyze(a.archive, events, report, a.image)")
mut("A80-ring-records-include-the-exception-page", "analyze", ' if f["kind"] in ("log", "stage", "fault") and "dev_seq" in f]', ' if f["kind"] in ("log", "stage", "fault")]')
mut("A81-frame-seq-not-checked", "analyze", 's["frame_seq_contiguous"] = [f["seq"] for f in frames] == list(range(len(frames)))', 's["frame_seq_contiguous"] = True')
mut("A82-empty-ring-is-contiguous", "analyze", 's["dev_seq_contiguous"] = bool(seqs) and seqs ==', 's["dev_seq_contiguous"] = seqs ==')
mut("A83-capture-errors-lost", "analyze", 'a["capture_errors"] = [e.get("reason") for e in events if e.get("kind") == "capture-error"]', 'a["capture_errors"] = []')
mut("A84-unreadable-events-ignored", "analyze", '(["events.jsonl has %d unreadable lines" % bad] if bad else [])', "[]")
# --- session_usblog.py
mut("D01-ambiguous-gate-accepted", "driver", "assert len(found)==1,", "assert len(found)>=1,")
mut("D02-hashes-not-required-in-the-decision", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in ('decision 0019',):")
mut("D03-decision-0019-not-required", "driver", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA']):")
mut("D04-glob-matches-the-other-image", "driver", "glob('*-nat043-%s-single-run-*.md'%image)", "glob('*-nat043-%s*.md'%image)")
mut("D05-marker-overwritable", "driver", "with marker.open('x') as f:", "with marker.open('w') as f:")
mut("D06-marker-shared-by-images", "driver", "('artifacts/nat-049/native-attempt-%s-used.json'%a.image)", "('artifacts/nat-049/native-attempt-used.json')")
mut("D07-no-watcher", "driver", "            watcher_start()\n            collector_start()\n", "            collector_start()\n")
mut("D08-no-collector", "driver", "            watcher_start()\n            collector_start()\n", "            watcher_start()\n")
mut("D09-collector-before-watcher", "driver", "            watcher_start()\n            collector_start()\n", "            collector_start()\n            watcher_start()\n")
mut("D10-starts-after-the-reboot", "driver",
    "            watcher_start()\n            collector_start()\n            # The sole native reboot in this session. No later reboot or retry.\n            report['reboot_sent']=True;report['reboot_requested_at']=now();save()\n            run(['adb','reboot','recovery'])\n",
    "            # The sole native reboot in this session. No later reboot or retry.\n            report['reboot_sent']=True;report['reboot_requested_at']=now();save()\n            run(['adb','reboot','recovery'])\n            watcher_start()\n            collector_start()\n")
mut("D11-watcher-start-not-awaited", "driver", "if any(e['event']=='start' for e in read_events(log)):", "if True:")
mut("D12-collector-poll-not-awaited", "driver", "            if 'poll' in ev:\n", "            if True:\n")
mut("D13-collector-error-not-final", "driver", "            if 'error' in ev:break\n", "            if False:break\n")
mut("D14-watcher-exit-not-noticed", "driver", "            if proc.poll() is not None:break\n            time.sleep(0.1)\n        if proc.poll() is None:proc.terminate()\n        raise RuntimeError('the USB watcher", "            time.sleep(0.1)\n        if proc.poll() is None:proc.terminate()\n        raise RuntimeError('the USB watcher")
mut("D15-collector-exit-not-noticed", "driver", "            if proc.poll() is not None:break\n            time.sleep(0.1)\n        if proc.poll() is None:proc.terminate()\n        raise RuntimeError('the collector", "            time.sleep(0.1)\n        if proc.poll() is None:proc.terminate()\n        raise RuntimeError('the collector")
mut("D16-slow-watcher-left-running", "driver", "        if proc.poll() is None:proc.terminate()\n        raise RuntimeError('the USB watcher", "        raise RuntimeError('the USB watcher")
mut("D17-silent-collector-left-running", "driver", "        if proc.poll() is None:proc.terminate()\n        raise RuntimeError('the collector", "        raise RuntimeError('the collector")
mut("D18-started-processes-left-after-abort", "driver", "                for proc in started:\n                    if proc.poll() is None:proc.terminate()", "                for proc in started:\n                    pass")
mut("D19-started-processes-stopped-after-the-request", "driver", "            if not report['reboot_sent']:\n                for proc in started:", "            if True:\n                for proc in started:")
mut("D20-watcher-too-short", "driver", "WATCH_S=360 ", "WATCH_S=20 ")
mut("D21-collector-too-short", "driver", "COLLECT_S=360\n", "COLLECT_S=20\n")
mut("D22-watcher-not-detached", "driver", "stderr=err,start_new_session=True)\n        started.append(proc)\n        report['watcher']", "stderr=err,start_new_session=False)\n        started.append(proc)\n        report['watcher']")
mut("D23-collector-not-detached", "driver", "stderr=err,start_new_session=True)\n        started.append(proc)\n        report['collector']", "stderr=err,start_new_session=False)\n        started.append(proc)\n        report['collector']")
mut("D24-udev-exit-status-ignored", "driver", "assert r.returncode==0 and info.get('found'),", "assert info.get('found'),")
mut("D25-udev-finding-ignored", "driver", "assert r.returncode==0 and info.get('found'),", "assert r.returncode==0,")
mut("D26-no-udev-check", "driver", "host_access();collector_selftest()", "collector_selftest()")
mut("D27-no-collector-selftest", "driver", "host_access();collector_selftest()", "host_access()")
mut("D28-selftest-exit-status-ignored", "driver", "assert r.returncode==0 and res.get('ok') is True,", "assert res.get('ok') is True,")
mut("D29-selftest-ok-ignored", "driver", "assert r.returncode==0 and res.get('ok') is True,", "assert r.returncode==0,")
mut("D30-monitor-already-there-ignored", "driver", "assert res.get('monitor_devices_now')==0,", "assert True,")
mut("D31-missing-venv-ignored", "driver", "assert VENV_PY.exists(),", "assert True,")
mut("D32-collector-runs-without-the-venv", "driver", "argv=[str(VENV_PY),'-I',str(LAUNCHER),'--out'", "argv=[sys.executable,'-I',str(LAUNCHER),'--out'")
mut("D33-preflight-fails-on-a-closed-registry", "driver", "assert not (a.execute and blocker),blocker", "assert not blocker,blocker")
mut("D34-execute-ignores-the-registry", "driver", "assert not (a.execute and blocker),blocker", "assert True,blocker")
mut("D35-native-flag-ignored", "driver", "if state['project']['permissions'].get('native') is not True:return", "if False:return")
mut("D36-native-decision-not-required", "driver", "if not native or native[-1].get('value') is not True or", "if native[-1].get('value') is not True or")
mut("D37-decision-value-ignored", "driver", "or native[-1].get('value') is not True or native[-1].get('decision')", "or native[-1].get('decision')")
mut("D38-decision-citation-ignored", "driver", "native[-1].get('decision')!='docs/decisions/'+decision.name:", "False:")
mut("D39-first-native-decision-counts", "driver", "native[-1].get('value') is not True or native[-1].get('decision')", "native[0].get('value') is not True or native[0].get('decision')")
mut("D40-other-scopes-count", "driver", "if d.get('scope')=='native']", "if True]")
mut("D41-preconditions-ignored", "driver", "    if missing:return", "    if False:return")
mut("D42-one-precondition-only", "driver", "REQUIRED_DONE=('NAT-039','NAT-046')", "REQUIRED_DONE=('NAT-039',)")
mut("D43-done-status-loosened", "driver", "tasks.get(t,{}).get('status')!='done']", "tasks.get(t,{}).get('status') not in ('done','in_progress')]")
mut("D44-restore-needs-the-registry", "driver", "            if not a.restore:\n                blocker=registry_blocker(decision)", "            if True:\n                blocker=registry_blocker(decision)")
mut("D45-registry-closed-not-reported", "driver", "'ready-read-only' if not blocker else 'ready-read-only-registry-closed'", "'ready-read-only'")
mut("D46-decision-file-not-recorded", "driver", "report['decision_file']=decision.name;save()", "save()")
mut("D47-report-dir-reusable", "driver", "a.out.mkdir(parents=True,exist_ok=False)", "a.out.mkdir(parents=True,exist_ok=True)")
mut("D48-restore-runs-the-watcher-selftest", "driver", "if not a.restore:watcher_selftest()", "watcher_selftest()")
mut("D49-no-watcher-selftest", "driver", "if not a.restore:watcher_selftest()", "pass")
mut("D50-pins-swapped", "driver", "NEW_SHA='c6802dea4682a4bc993885bf525e2907e42e4eeebb964310da82ed79fef7212d'", "NEW_SHA='f1a193dcac776dde004a3d1a379c26a4a365a150318bbc0a6501506ad7dfa103'")
mut("D51-package-not-checked", "driver", "assert img['recovery_sha256']==NEW_SHA and img['payload_sha256']==CANARY_SHA and img['payload_bytes']==CANARY_LEN and img['payload_offset']==PAYLOAD_OFFSET", "pass")
mut("D52-flashed-flag-ignored", "driver", "assert pkg['stock_sha256']==STOCK_SHA and pkg['flashed'] is False", "assert pkg['stock_sha256']==STOCK_SHA")
mut("D53-stock-pin-of-package-ignored", "driver", "assert pkg['stock_sha256']==STOCK_SHA and pkg['flashed'] is False", "assert pkg['flashed'] is False")
mut("D54-restore-after-abort-lost", "driver", "write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()", "pass")
mut("D55-readback-not-compared", "driver", "assert measured==expected,'full RECOVERY readback mismatch'", "pass")
mut("D56-low-battery-accepted", "driver", "assert int(values['level'])>=50", "assert int(values['level'])>=0")
mut("D57-busy-dd-ignored", "driver", "return result=='idle'", "return True")
mut("D58-stock-not-required-for-launch", "driver", "if not a.restore: assert initial==STOCK_SHA, 'launch requires unchanged stock RECOVERY'", "pass")
mut("D59-reboot-reported-before-start", "driver", "report['reboot_sent']=True;report['reboot_requested_at']=now();save()\n            run(['adb','reboot','recovery'])", "run(['adb','reboot','recovery']);report['reboot_sent']=True;report['reboot_requested_at']=now();save()")
mut("D60-log-paths-not-printed", "driver", "usb_log=report['watcher']['log'],archive=report['collector']['archive']", "usb_log=report['watcher']['log']")
mut("D61-collector-seconds-fixed", "driver", "'--seconds',str(COLLECT_S)]", "'--seconds','180']")
mut("D62-collector-archive-elsewhere", "driver", "log=a.out/'collector-heartbeat.jsonl';archive=a.out/'archive'", "log=a.out/'collector-heartbeat.jsonl';archive=a.out/'collected'")
mut("D63-flock-not-taken", "driver", "fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)", "pass")
mut("D64-reboot-request-time-lost", "driver", "report['reboot_sent']=True;report['reboot_requested_at']=now();save()", "report['reboot_sent']=True;save()")


def build_tree(base, which, old, new):
    tree = base / "tree"
    d = tree / "docs/procedures/nat-049"
    d.mkdir(parents=True)
    for e in (ROOT / "docs/procedures").iterdir():
        if e.name != "nat-049":
            os.symlink(e, tree / "docs/procedures" / e.name)
    # private artifacts/nat-022 and artifacts/nat-049 (the driver's flock and one-shot markers must not be shared between parallel
    # mutants or with the real tree); the pinned package and the stock image are read through symlinks
    (tree / "artifacts/nat-022").mkdir(parents=True)
    (tree / "artifacts/nat-049").mkdir()
    os.symlink(ROOT / "artifacts/nat-047", tree / "artifacts/nat-047")
    os.symlink(ROOT / "devices", tree / "devices")
    os.symlink(ROOT / "docs/decisions", tree / "docs/decisions")
    os.symlink(ROOT / "state", tree / "state")
    for fn in FILES.values():
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


def run_tests(env, classes, timeout=1200):
    return subprocess.run([sys.executable, "-I", str(HERE / "test_nat049.py"), "-f", *classes], capture_output=True, text=True, env=env, timeout=timeout)


def run_one(item, out):
    name, which, old, new = item
    with tempfile.TemporaryDirectory(prefix="mut049-") as t:
        base = Path(t)
        d, err = build_tree(base, which, old, new)
        if d is None:
            return dict(name=name, outcome="INVALID", detail=err)
        env = dict(os.environ, **{ENVS[w]: str(d / fn) for w, fn in FILES.items()})
        passes = [("behaviour", dict(env, NAT049_BEHAVIOUR_ONLY="1"))] + ([("with-pins", env)] if which == "driver" else [])
        for label, e in passes:
            try:
                r = run_tests(e, CLASSES[which])
            except subprocess.TimeoutExpired:
                return dict(name=name, outcome="killed", detail="timeout (a hang is a failure)")
            (out / ("%s.%s.log" % (name, label))).write_text(r.stdout + r.stderr)
            tail = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
            if r.returncode != 0:
                return dict(name=name, outcome="killed" if label == "behaviour" else "killed-by-pin", detail=tail[0] if tail else "exit %d" % r.returncode)
        return dict(name=name, outcome="SURVIVED", detail="")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", action="append")
    ap.add_argument("--prefix", action="append", help="run only mutants whose name starts with this (H, L, A, D)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    base = subprocess.run([sys.executable, "-I", str(HERE / "test_nat049.py")], capture_output=True, text=True)
    (a.out / "baseline.log").write_text(base.stdout + base.stderr)
    if base.returncode != 0:
        print("the unmutated tests fail; nothing to compare against")
        return 2
    items = [m for m in M if (not a.only or m[0] in a.only) and (not a.prefix or any(m[0].startswith(p) for p in a.prefix))]
    results = []
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(lambda m: run_one(m, a.out), items):
            results.append(res)
            print("%-14s %-48s %s" % (res["outcome"], res["name"], res["detail"][:110]), flush=True)
    summary = dict(mutants=len(items), killed=sum(r["outcome"] == "killed" for r in results), killed_by_pin=[r["name"] for r in results if r["outcome"] == "killed-by-pin"],
                   survived=[r["name"] for r in results if r["outcome"] == "SURVIVED"], invalid=[r["name"] for r in results if r["outcome"] == "INVALID"], results=results)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print("killed %d/%d (+%d only by a source pin); survived %s; invalid %s" % (summary["killed"], len(items), len(summary["killed_by_pin"]), summary["survived"], summary["invalid"]))
    return 0 if not summary["survived"] and not summary["invalid"] else 1


if __name__ == "__main__":
    sys.exit(main())
