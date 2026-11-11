#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-048 host tests: the host USB event logger (usb_watch.py), the reset-run analyzer (analyze_reset.py) and the gated session
driver of the NAT-044 reset canaries (session_reset_canary.py). Evidence kind: host-test. Nothing here talks to a phone: `adb` is
a fake that records its calls, and the USB bus is a directory tree of fake sysfs attributes.

Layers:
  * UsbWatch: the logger against a fake sysfs tree (appear / disappear / re-enumeration / string change / filter / partial
    enumeration / no serial number / no device-node access / fsync per line), and the CLI as a real process (SIGTERM is a clean stop).
  * Analyzer: table-driven scenarios of the verdict rules fixed in nat-044/decision-template.md (boundaries included), the
    refusal to judge without a covering log, and the tie of the baseline constants to the nat-022 README.
  * RealTreeGate: in the real tree, without the agent-written decision file, the driver stops before the first adb call in
    every mode and for both images; its pinned hashes are those of NAT-044 package-002; its safety lines are those of the
    NAT-037 driver; it never creates the decision file.
  * OpenGateFlow: the driver in a scratch tree with a fake decision file, a fake adb that models the RECOVERY block in a file,
    and the real watcher pointed at a fake sysfs: the read-only preflight writes nothing; --execute writes, reads back in
    full, starts the watcher BEFORE the single reboot (the fake adb checks the log at the moment of the reboot), leaves a
    detached watcher that outlives the driver, and a one-shot marker per image; a readback mismatch, a watcher that cannot
    start, or a decision file that does not name the hashes never reboots.
The fakes are not the phone: what these tests establish is the control flow and the log/verdict rules, not device behaviour."""
import datetime, difflib, hashlib, importlib.util, json, os, re, shutil, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DRIVER = Path(os.environ.get("NAT048_DRIVER") or HERE / "session_reset_canary.py")     # mutated copies for the mutation checks
WATCH = Path(os.environ.get("NAT048_WATCH") or HERE / "usb_watch.py")
ANALYZE = Path(os.environ.get("NAT048_ANALYZE") or HERE / "analyze_reset.py")
NAT037_DRIVER = ROOT / "docs/procedures/nat-037/session_xnu_ckpt3.py"
PACKAGE = ROOT / "artifacts/nat-044/package-002"
BUILD = ROOT / "artifacts/nat-044/build-002"
STOCK = ROOT / "devices/recovery/backups/2026-11-10/recovery.img"
STOCK_SHA = "96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67"
IMAGES = ("loader-diag-reset", "loader-diag-reset-bl")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def add_dev(root, name, vid="04e8", pid="685d", product="SAMSUNG USB", devnum="7", serial="SERIALSENTINEL0123", manufacturer="SAMSUNG", complete=True):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    files = dict(idVendor=vid, idProduct=pid, product=product, manufacturer=manufacturer, busnum="5", devnum=devnum, serial=serial)
    for k, v in files.items():
        if complete or k == "idVendor":
            (d / k).write_text(v + "\n")


def rm_dev(root, name):
    shutil.rmtree(Path(root) / name)


class Clock:
    def __init__(self, base=1000.0):
        self.t = base

    def __call__(self):
        self.t += 0.25
        return self.t


class UsbWatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load(WATCH, "usb_watch_under_test")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nat048-watch-"))
        self.sys = self.tmp / "sys"
        self.sys.mkdir()
        self.log = self.tmp / "events.jsonl"
        self.opened = []

    def tearDown(self):
        for w in self.opened:
            if w.f and not w.f.closed:
                w.f.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def watcher(self, **kw):
        kw.setdefault("vids", self.mod.DEFAULT_VIDS)
        w = self.mod.Watcher(self.sys, self.log, clock=Clock(1000.0), mono=Clock(5.0), **kw)
        self.opened.append(w)
        return w

    def lines(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()]

    def test_start_lists_the_devices_already_present(self):
        add_dev(self.sys, "1-2", pid="6860", product="SM-S921B")
        w = self.watcher()
        (rec,) = w.start()
        self.assertEqual(rec["event"], "start")
        self.assertEqual([(d["path"], d["vid"], d["pid"], d["product"]) for d in rec["initial"]], [("1-2", "04e8", "6860", "SM-S921B")])

    def test_appear_disappear_and_the_numbering(self):
        w = self.watcher()
        w.start()
        self.assertEqual(w.poll(), [])
        add_dev(self.sys, "1-2", product="SAMSUNG USB", devnum="7")
        (a,) = w.poll()
        self.assertEqual((a["event"], a["path"], a["vid"], a["pid"], a["product"], a["devnum"]), ("appear", "1-2", "04e8", "685d", "SAMSUNG USB", "7"))
        self.assertEqual(w.poll(), [], "no event while nothing changes")
        rm_dev(self.sys, "1-2")
        (d,) = w.poll()
        self.assertEqual((d["event"], d["path"], d["product"]), ("disappear", "1-2", "SAMSUNG USB"))
        w.stop()
        rows = self.lines()
        self.assertEqual([r["event"] for r in rows], ["start", "appear", "disappear", "stop"])
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3, 4])
        self.assertTrue(all(rows[i]["t_unix"] < rows[i + 1]["t_unix"] and rows[i]["t_mono"] < rows[i + 1]["t_mono"] for i in range(3)))
        self.assertTrue(all(r["t_unix"] > 1000 and r["t_mono"] < 100 for r in rows), "t_unix is the wall clock, t_mono the monotonic one")

    def test_a_reenumeration_between_two_polls_is_a_disappear_and_an_appear(self):
        add_dev(self.sys, "1-2", product="SEC_UPLOAD", devnum="7")
        w = self.watcher()
        w.start()
        add_dev(self.sys, "1-2", product="SAMSUNG USB", devnum="8")      # same bus path, new device number
        got = w.poll()
        self.assertEqual([(e["event"], e["devnum"], e["product"]) for e in got], [("disappear", "7", "SEC_UPLOAD"), ("appear", "8", "SAMSUNG USB")])

    def test_a_string_change_on_the_same_device_is_a_change_event(self):
        add_dev(self.sys, "1-2", product="SEC_UPLOAD", devnum="7")
        w = self.watcher()
        w.start()
        add_dev(self.sys, "1-2", product="SAMSUNG USB", devnum="7")
        (e,) = w.poll()
        self.assertEqual((e["event"], e["product"]), ("change", "SAMSUNG USB"))
        add_dev(self.sys, "1-2", pid="6860", product="SAMSUNG USB", devnum="7")
        (e,) = w.poll()
        self.assertEqual((e["event"], e["pid"]), ("change", "6860"))

    def test_vendor_and_product_ids_are_recorded_in_lower_case_whatever_sysfs_says(self):
        # The analyzer compares vid == "04e8"; a record that kept the sysfs spelling would be ignored there.
        add_dev(self.sys, "1-2", vid="04E8", pid="685D", product="SAMSUNG USB")
        w = self.watcher()
        (rec,) = w.start()
        self.assertEqual([(d["vid"], d["pid"]) for d in rec["initial"]], [("04e8", "685d")])
        add_dev(self.sys, "2-1", vid="18D1", pid="4EE0", product="Fastboot")
        (e,) = w.poll()
        self.assertEqual((e["event"], e["vid"], e["pid"]), ("appear", "18d1", "4ee0"))

    def test_the_default_filter_keeps_the_phone_and_hides_other_peripherals(self):
        add_dev(self.sys, "1-2", vid="8087", pid="0033", product="Bluetooth")
        add_dev(self.sys, "1-3", vid="046d", pid="c52b", product="Receiver")
        w = self.watcher()
        (rec,) = w.start()
        self.assertEqual(rec["initial"], [])
        for vid in ("04e8", "18d1", "1209"):
            add_dev(self.sys, "2-1", vid=vid, pid="0001", product="x" + vid)
            (e,) = w.poll()
            self.assertEqual((e["event"], e["vid"]), ("appear", vid))
            rm_dev(self.sys, "2-1")
            self.assertEqual(w.poll()[0]["event"], "disappear")
        self.assertNotIn("Bluetooth", self.log.read_text())
        self.assertNotIn("Receiver", self.log.read_text())

    def test_without_a_filter_every_device_is_logged(self):
        add_dev(self.sys, "1-2", vid="8087", pid="0033", product="Bluetooth")
        w = self.watcher(vids=None)
        (rec,) = w.start()
        self.assertEqual([d["product"] for d in rec["initial"]], ["Bluetooth"])

    def test_root_hubs_and_interfaces_are_not_devices(self):
        add_dev(self.sys, "usb1", vid="04e8")
        add_dev(self.sys, "1-2:1.0", vid="04e8")
        add_dev(self.sys, "1-0:1.0", vid="04e8")
        w = self.watcher()
        (rec,) = w.start()
        self.assertEqual(rec["initial"], [])
        add_dev(self.sys, "1-4.2.1", vid="04e8")      # a device behind two hubs is a device
        (e,) = w.poll()
        self.assertEqual(e["path"], "1-4.2.1")

    def test_a_device_that_is_still_being_enumerated_is_reported_once_complete(self):
        w = self.watcher()
        w.start()
        add_dev(self.sys, "1-2", complete=False)           # only idVendor yet
        self.assertEqual(w.poll(), [])
        add_dev(self.sys, "1-2")
        (e,) = w.poll()
        self.assertEqual(e["event"], "appear")

    def test_the_serial_number_never_reaches_the_log(self):
        add_dev(self.sys, "1-2", serial="SERIALSENTINEL0123")
        w = self.watcher()
        w.start()
        add_dev(self.sys, "1-3", serial="SERIALSENTINEL0123")
        w.poll()
        rm_dev(self.sys, "1-2")
        w.poll()
        w.stop()
        self.assertNotIn("SERIALSENTINEL", self.log.read_text())
        self.assertNotIn("serial", self.log.read_text().lower())

    def test_it_reads_only_sysfs_attributes_and_never_opens_a_device(self):
        src = WATCH.read_text()
        for bad in ("/dev/bus/usb", "import usb", "pyusb", "libusb", "fcntl", "ioctl", "os.open(", "adb", "subprocess"):
            self.assertNotIn(bad, src, bad)
        self.assertEqual(sorted(self.mod.ATTRS), ["busnum", "devnum", "idProduct", "idVendor", "manufacturer", "product"])
        opened = []
        real_open = Path.read_text

        def spy(self_, *a, **k):
            opened.append(self_.name)
            return real_open(self_, *a, **k)
        add_dev(self.sys, "1-2")
        with mock.patch.object(Path, "read_text", spy):
            self.watcher().start()
        self.assertEqual(sorted(set(opened)), sorted(self.mod.ATTRS))

    def test_every_event_line_is_synced_to_disk_as_it_is_written(self):
        with mock.patch.object(self.mod.os, "fsync") as fs:
            w = self.watcher()
            w.start()
            self.assertEqual(fs.call_count, 1)
            self.assertEqual(len(self.lines()), 1, "the line is readable by another process before stop()")
            add_dev(self.sys, "1-2")
            w.poll()
            self.assertEqual(fs.call_count, 2)
            w.stop()
            self.assertEqual(fs.call_count, 3)

    def test_an_existing_log_is_never_overwritten(self):
        self.log.write_text("earlier run\n")
        with self.assertRaises(FileExistsError):
            self.mod.Watcher(self.sys, self.log)
        self.assertEqual(self.log.read_text(), "earlier run\n")

    def cli(self, *extra, seconds="30"):
        return subprocess.Popen([sys.executable, "-I", str(WATCH), "--out", str(self.log), "--seconds", seconds, "--sysfs", str(self.sys), "--poll", "0.05", *extra],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait_for(self, pred, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if self.log.exists():
                rows = [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]
                if pred(rows):
                    return rows
            time.sleep(0.05)
        self.fail("timed out; log: %s" % (self.log.read_text() if self.log.exists() else "<none>"))

    def test_the_process_logs_events_and_stops_cleanly_on_sigterm(self):
        p = self.cli()
        try:
            self.wait_for(lambda r: any(x["event"] == "start" for x in r))
            add_dev(self.sys, "1-2", product="SEC_UPLOAD")
            self.wait_for(lambda r: any(x["event"] == "appear" for x in r))
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=10), 0)
        finally:
            if p.poll() is None:
                p.kill()
        rows = self.wait_for(lambda r: True)
        self.assertEqual([r["event"] for r in rows], ["start", "appear", "stop"])

    def test_the_process_ends_by_itself_after_its_seconds(self):
        p = self.cli(seconds="0.5")
        try:
            self.assertEqual(p.wait(timeout=15), 0)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
        self.assertEqual([r["event"] for r in self.wait_for(lambda r: True)], ["start", "stop"])

    def test_the_command_line_filter_options(self):
        add_dev(self.sys, "1-2", vid="8087", pid="0033", product="Bluetooth")
        add_dev(self.sys, "1-3", vid="04e8", pid="6860", product="SM-S921B")
        for i, (extra, expect) in enumerate([((), ["SM-S921B"]), (("--vid", "8087"), ["Bluetooth"]), (("--vid", "8087", "--vid", "04E8"), ["Bluetooth", "SM-S921B"]), (("--all",), ["Bluetooth", "SM-S921B"])]):
            self.log = self.tmp / ("opt%d.jsonl" % i)
            p = self.cli(*extra, seconds="0.4")
            try:
                self.assertEqual(p.wait(timeout=15), 0)
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
            rows = self.wait_for(lambda r: any(x["event"] == "stop" for x in r))
            self.assertEqual(sorted(d["product"] for d in rows[0]["initial"]), expect, extra)

    def test_a_killed_process_leaves_a_usable_log(self):
        p = self.cli()
        try:
            self.wait_for(lambda r: any(x["event"] == "start" for x in r))
            add_dev(self.sys, "1-2")
            self.wait_for(lambda r: any(x["event"] == "appear" for x in r))
        finally:
            p.kill()
            p.wait()
        rows = [json.loads(l) for l in self.log.read_text().splitlines()]       # every line is a whole JSON record
        self.assertEqual([r["event"] for r in rows], ["start", "appear"])

    def test_invalid_arguments_are_refused(self):
        for bad in (["--seconds", "0"], ["--seconds", "5", "--poll", "0"]):
            r = subprocess.run([sys.executable, "-I", str(WATCH), "--out", str(self.tmp / "x.jsonl"), "--sysfs", str(self.sys), *bad], capture_output=True)
            self.assertNotEqual(r.returncode, 0, bad)


# ---------------------------------------------------------------------------------------------------------------- analyzer

T0 = 1_800_000_000.0
META = dict(reason="0x12345601", deadline_s=45, wdt_s=83)
MARK_BASELINE = "USB vanish at +4 s and `SEC_UPLOAD` at +95 s"


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


def rec(dt, event, vid="04e8", pid="685d", product="SAMSUNG USB", path="5-1"):
    return dict(seq=0, event=event, t_unix=T0 + dt, t_mono=0.0, path=path, vid=vid, pid=pid, product=product, manufacturer="SAMSUNG", busnum="5", devnum="1")


def log(*events, start=-3.0, stop=240.0):
    out = []
    if start is not None:
        out.append(dict(seq=1, event="start", t_unix=T0 + start, t_mono=0.0, initial=[]))
    out += list(events)
    if stop is not None:
        out.append(dict(seq=99, event="stop", t_unix=T0 + stop, t_mono=0.0))
    return out


def leave(dt=4.0):
    return rec(dt, "disappear", pid="6860", product="SM-S921B")


def REPORT(sent=True, when=None):
    return dict(reboot_sent=sent, reboot_requested_at=iso(T0) if when is None else when)


class Analyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load(ANALYZE, "analyze_reset_under_test")

    def run_case(self, events, report=None, meta=META, image="loader-diag-reset"):
        return self.mod.analyze(events, REPORT() if report is None else report, meta, image)

    def verdicts(self, events, **kw):
        r = self.run_case(events, **kw)
        return r["U1_U2"]["verdict"], r["U3_U4"]["verdict"]

    def appear_at(self, dt, product, **kw):
        return log(leave(), rec(dt, "appear", product=product, **kw))

    def test_the_baseline_of_runs_001_to_009_refutes_an_early_reset(self):
        self.assertEqual(self.verdicts(self.appear_at(95.0, "SEC_UPLOAD")), ("refuted", "undetermined"))
        r = self.run_case(self.appear_at(95.0, "SEC_UPLOAD"))
        self.assertEqual(r["vanish_dt_s"], 4.0)
        self.assertEqual(r["first_appearance"]["klass"], "upload")

    def test_an_early_download_mode_supports_both_questions(self):
        self.assertEqual(self.verdicts(self.appear_at(50.0, "SAMSUNG USB")), ("supported", "supported"))

    def test_an_early_upload_supports_the_reset_and_refutes_the_word(self):
        self.assertEqual(self.verdicts(self.appear_at(50.0, "SEC_UPLOAD")), ("supported", "refuted"))

    def test_the_window_boundaries(self):
        ceiling = BASELINE = None
        r = self.run_case(self.appear_at(50.0, "SAMSUNG USB"))
        self.assertEqual(r["early_ceiling_s"], 76.0)
        for dt, product, expect in [
            (44.9, "SAMSUNG USB", "undetermined"), (45.0, "SAMSUNG USB", "supported"), (76.0, "SAMSUNG USB", "supported"), (76.1, "SAMSUNG USB", "undetermined"),
            (44.9, "SEC_UPLOAD", "undetermined"), (45.0, "SEC_UPLOAD", "supported"), (76.0, "SEC_UPLOAD", "supported"), (76.1, "SEC_UPLOAD", "undetermined"),
            (84.9, "SEC_UPLOAD", "undetermined"), (85.0, "SEC_UPLOAD", "refuted"), (105.0, "SEC_UPLOAD", "refuted"), (105.1, "SEC_UPLOAD", "undetermined"),
            (95.0, "SAMSUNG USB", "undetermined"),         # Download Mode at the baseline time is not the baseline (SEC_UPLOAD): not judged
            (10.0, "SAMSUNG USB", "undetermined"),
        ]:
            self.assertEqual(self.verdicts(self.appear_at(dt, product))[0], expect, (dt, product))

    def test_u3_u4_is_judged_only_when_the_reset_was_seen_early(self):
        for dt, product in [(20.0, "SAMSUNG USB"), (95.0, "SEC_UPLOAD"), (90.0, "SAMSUNG USB"), (84.0, "SEC_UPLOAD")]:
            self.assertEqual(self.verdicts(self.appear_at(dt, product))[1], "undetermined", (dt, product))

    def test_the_question_text_names_the_reason_word(self):
        self.assertIn("U3", self.run_case(self.appear_at(50, "SAMSUNG USB"))["U3_U4"]["question"])
        r = self.run_case(self.appear_at(50, "SAMSUNG USB"), meta=dict(reason="0x1234560d", deadline_s=45, wdt_s=83), image="loader-diag-reset-bl")
        self.assertIn("U4", r["U3_U4"]["question"])
        self.assertIn("0x1234560d", r["U3_U4"]["question"])

    def test_android_coming_back_by_itself_is_recorded_and_refutes_download_mode(self):
        r = self.run_case(log(leave(), rec(60.0, "appear", pid="6860", product="SM-S921B")))
        self.assertEqual((r["U1_U2"]["verdict"], r["U3_U4"]["verdict"]), ("undetermined", "refuted"))
        self.assertTrue(any("Android came back" in n for n in r["notes"]))

    def test_an_appearance_before_the_phone_left_is_not_its_return(self):
        events = log(rec(1.0, "appear", pid="6862", product="Gadget"), leave(), rec(95.0, "appear", product="SEC_UPLOAD"))
        self.assertEqual(self.verdicts(events), ("refuted", "undetermined"))

    def test_a_reenumeration_before_the_deadline_is_not_the_loaders_reset(self):
        r = self.run_case(self.appear_at(20.0, "SAMSUNG USB"))
        self.assertEqual(r["U1_U2"]["verdict"], "undetermined")
        self.assertIn("before the 45 s deadline", r["U1_U2"]["why"])

    def test_nothing_returning_is_a_finding_only_with_enough_coverage(self):
        r = self.run_case(log(leave(), stop=200.0))
        self.assertEqual((r["U1_U2"]["verdict"], r["U3_U4"]["verdict"]), ("undetermined", "undetermined"))
        self.assertIn("covered window", r["U1_U2"]["why"])
        self.assertNotIn("covered only", r["U1_U2"]["why"])
        short = self.run_case(log(leave(), stop=60.0))
        self.assertIn("covered only 60 s", short["U1_U2"]["why"])
        self.assertIn("covered window", self.run_case(log(leave(), stop=120.0))["U1_U2"]["why"])
        self.assertIn("covered only", self.run_case(log(leave(), stop=119.9))["U1_U2"]["why"])

    def test_a_log_without_a_stop_record_notes_it_and_covers_up_to_its_last_record(self):
        r = self.run_case(log(leave(), stop=None))
        self.assertEqual(r["watcher_covers_s_after_t0"], 4.0)
        self.assertTrue(any("no stop record" in n for n in r["notes"]))

    def test_no_judgement_without_t0_or_a_covering_log(self):
        cases = {
            "reboot never sent": (self.appear_at(50, "SAMSUNG USB"), REPORT(sent=False)),
            "no timestamp": (self.appear_at(50, "SAMSUNG USB"), dict(reboot_sent=True)),
            "empty log": ([], REPORT()),
            "no start record": (log(leave(), rec(50, "appear"), start=None), REPORT()),
            "watcher started after the request": (log(leave(), rec(50, "appear"), start=0.5), REPORT()),
            "the device never left": (log(rec(50, "appear")), REPORT()),
            "left before the request": (log(rec(-2.0, "disappear", pid="6860", product="x"), rec(50, "appear")), REPORT()),
        }
        for name, (events, report) in cases.items():
            r = self.run_case(events, report=report)
            self.assertEqual((r["U1_U2"]["verdict"], r["U3_U4"]["verdict"]), ("undetermined", "undetermined"), name)

    def test_other_vendors_do_not_count(self):
        events = log(leave(), rec(50, "appear", vid="1209", pid="0001", product="SAMSUNG USB"))
        self.assertEqual(self.verdicts(events), ("undetermined", "undetermined"))

    def test_the_deadline_and_the_watchdog_of_the_image_move_the_window(self):
        self.assertEqual(self.verdicts(self.appear_at(40.0, "SAMSUNG USB")), ("undetermined", "undetermined"))
        self.assertEqual(self.verdicts(self.appear_at(40.0, "SAMSUNG USB"), meta=dict(reason="0x12345601", deadline_s=30, wdt_s=83)), ("supported", "supported"))
        r = self.run_case(self.appear_at(80.0, "SEC_UPLOAD"), meta=dict(reason="0x12345601", deadline_s=45, wdt_s=63))
        self.assertEqual((r["early_ceiling_s"], r["U1_U2"]["verdict"]), (86.0, "supported"))
        self.assertEqual(self.verdicts(self.appear_at(80.0, "SEC_UPLOAD"))[0], "undetermined")

    def test_the_product_string_decides_the_class(self):
        c = self.mod.classify
        self.assertEqual(c(dict(vid="04e8", pid="685d", product="SAMSUNG USB")), "download")
        self.assertEqual(c(dict(vid="04e8", pid="685d", product="SAMSUNG USB ")), "download")
        self.assertEqual(c(dict(vid="04e8", pid="685d", product="SEC_UPLOAD")), "upload")
        self.assertEqual(c(dict(vid="04e8", pid="6860", product="SM-S921B")), "android")
        self.assertEqual(c(dict(vid="04e8", pid="685d", product=None)), "other")
        self.assertEqual(c(dict(vid="04e8", pid="1234", product="Gadget")), "other")

    def test_the_verdict_words_are_the_three_of_the_template(self):
        for events in (self.appear_at(50, "SAMSUNG USB"), self.appear_at(95, "SEC_UPLOAD"), log(leave()), []):
            r = self.run_case(events)
            for q in ("U1_U2", "U3_U4"):
                self.assertIn(r[q]["verdict"], ("supported", "refuted", "undetermined"))
                self.assertTrue(r[q]["why"])

    def test_the_baseline_constants_are_the_ones_the_nat022_readme_records(self):
        readme = (ROOT / "docs/procedures/nat-022/README.md").read_text()
        self.assertIn(MARK_BASELINE, readme)
        self.assertEqual((self.mod.BASELINE_VANISH_S, self.mod.BASELINE_UPLOAD_S), (4.0, 95.0))

    def test_the_window_follows_the_decision_template(self):
        t = (ROOT / "docs/procedures/nat-044/decision-template.md").read_text()
        for phrase in ("U1+U2 supported", "U3/U4 supported", "U3/U4 refuted", "U1/U2 refuted", "undetermined", "SEC_UPLOAD", "SAMSUNG USB"):
            self.assertIn(phrase, t)

    def test_the_command_line_reads_the_build_record_and_writes_the_analysis(self):
        if not (BUILD / "build.json").exists():
            self.skipTest("build-002 not present")
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in self.appear_at(50.0, "SAMSUNG USB")))
            (t / "report.json").write_text(json.dumps(REPORT()))
            rc = self.mod.main(["--events", str(t / "events.jsonl"), "--report", str(t / "report.json"), "--build", str(BUILD), "--image", "loader-diag-reset-bl", "--out", str(t / "analysis.json")])
            self.assertEqual(rc, 0)
            a = json.loads((t / "analysis.json").read_text())
            meta = json.loads((BUILD / "build.json").read_text())["image_meta"]["loader-diag-reset-bl"]
            self.assertEqual((a["reason"], a["deadline_s"], a["wdt_s"], a["image"]), (meta["reason"], meta["deadline_s"], meta["wdt_s"], "loader-diag-reset-bl"))
            self.assertEqual((a["U1_U2"]["verdict"], a["U3_U4"]["verdict"]), ("supported", "supported"))

    def test_a_missing_log_file_is_undetermined_not_a_crash(self):
        if not (BUILD / "build.json").exists():
            self.skipTest("build-002 not present")
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "report.json").write_text(json.dumps(REPORT()))
            self.assertEqual(self.mod.main(["--events", str(t / "none.jsonl"), "--report", str(t / "report.json"), "--build", str(BUILD), "--image", "loader-diag-reset"]), 0)


# ---------------------------------------------------------------------------------------------------------------- driver

FAKE_ADB = r'''#!{python}
import hashlib, os, sys
from pathlib import Path
base = Path(os.environ["FAKE_DEVICE_DIR"])
dev = base / "recovery.bin"
with (base / "adb-calls").open("a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args == ["get-state"]:
    print("device")
elif args == ["reboot", "recovery"]:
    log = os.environ.get("FAKE_WATCH_LOG")
    saw = bool(log) and os.path.exists(log) and any('"event": "start"' in l for l in open(log))
    (base / "reboot-saw-watcher").write_text("yes" if saw else "no")
elif args[:2] == ["shell", "-T"]:
    cmd = args[2]
    props = {"ro.product.model": "SM-S921B", "ro.product.device": "e1s", "ro.build.PDA": "S921BXXS9BYH3", "sys.boot_completed": "1"}
    if cmd.startswith("getprop "):
        print(props[cmd.split()[1]])
    elif "readlink -f" in cmd:
        print("/dev/block/sda18\n100663296\nblock_device")
    elif "pidof dd" in cmd:
        print("busy" if (base / "dd-busy").exists() else "idle")
    elif "sha256sum /dev/block/sda18" in cmd:
        print(hashlib.sha256(dev.read_bytes()).hexdigest() + "  /dev/block/sda18")
    elif cmd.startswith("dumpsys battery"):
        print("level=%s\ntemperature=300" % (base / "battery").read_text().strip() if (base / "battery").exists() else "level=80\ntemperature=300")
    elif "dd of=/dev/block/sda18" in cmd:
        data = sys.stdin.buffer.read()
        n = (base / "writes").read_text().count("\n") if (base / "writes").exists() else 0
        with (base / "writes").open("a") as w:
            w.write("%d\n" % len(data))
        if (base / "corrupt-first-write").exists() and n == 0:
            data = bytes([data[0] ^ 1]) + data[1:]
        dev.write_bytes(data)
    else:
        sys.stderr.write("fake adb: unexpected shell command: %s\n" % cmd)
        sys.exit(1)
else:
    sys.stderr.write("fake adb: unexpected arguments: %s\n" % args)
    sys.exit(1)
'''

WRAPPER = r'''import os, runpy, sys
real = os.environ["REAL_WATCHER"]
secs = sys.argv[sys.argv.index("--seconds") + 1]
if os.environ.get("FAKE_WATCHER_FAIL_SELFTEST") and secs == "1":
    sys.exit(1)
if os.environ.get("FAKE_WATCHER_FAIL_RUN") and secs != "1":
    sys.exit(1)
if os.environ.get("FAKE_WATCHER_DELAY") and secs != "1":
    import time
    time.sleep(float(os.environ["FAKE_WATCHER_DELAY"]))
sys.argv += ["--sysfs", os.environ["FAKE_SYSFS"]]
sys.argv[0] = real
runpy.run_path(real, run_name="__main__")
'''


def pinned(image):
    return json.loads((PACKAGE / "package.json").read_text())["images"][image]


def decision_text(image, with_recovery=True, with_payload=True, with_0019=True):
    p = pinned(image)
    parts = ["scratch-tree decision for %s\n" % image]
    if with_recovery:
        parts.append("RECOVERY SHA-256 %s\n" % p["recovery_sha256"])
    if with_payload:
        parts.append("Image.payload SHA-256 %s\n" % p["payload_sha256"])
    if with_0019:
        parts.append("recorded under decision 0019\n")
    return "".join(parts)


class RealTreeGate(unittest.TestCase):
    """The gated driver in the real tree: with no agent-written decision file it stops before any adb call, in every mode."""

    def decisions(self, image):
        return sorted((ROOT / "docs/decisions").glob("*-nat046-%s-single-run-*.md" % image))

    def run_driver(self, image, *mode):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "bin").mkdir()
            fake = t / "bin/adb"
            fake.write_text("#!/bin/sh\necho \"$@\" >> %s\nexit 1\n" % (t / "adb-calls"))
            fake.chmod(0o755)
            env = {"PATH": f"{t / 'bin'}:/usr/bin:/bin", "HOME": str(t)}
            r = subprocess.run([sys.executable, "-I", str(DRIVER), "--image", image, "--out", str(t / "out"), *mode], capture_output=True, text=True, env=env)
            calls = (t / "adb-calls").read_text() if (t / "adb-calls").exists() else ""
            return r, calls, json.loads((t / "out/report.json").read_text())

    def test_no_decision_no_adb_in_any_mode_for_either_image(self):
        for image in IMAGES:
            if self.decisions(image):
                self.skipTest("a decision file for %s exists: its gate is open" % image)
            marker = ROOT / ("artifacts/nat-048/native-attempt-%s-used.json" % image)
            before = marker.exists()
            for mode in ((), ("--execute",), ("--restore",)):
                r, calls, rep = self.run_driver(image, *mode)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(calls, "", (image, mode))
                self.assertEqual(rep["outcome"], "stopped")
                self.assertIn("decision file for %s is missing or ambiguous (0 found)" % image, rep["error"])
                self.assertEqual((rep["device_write_started"], rep["reboot_sent"], rep["commands"]), (False, False, []))
                self.assertNotIn("watcher", rep)
            self.assertEqual(marker.exists(), before, "a refused run must not leave the one-shot marker")

    def test_one_images_decision_does_not_open_the_other(self):
        # the glob of `loader-diag-reset` must not match `loader-diag-reset-bl` files and vice versa
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "0021-nat046-loader-diag-reset-bl-single-run-2026-11-12.md").write_text("x")
            self.assertEqual(sorted(d.glob("*-nat046-loader-diag-reset-single-run-*.md")), [])
            self.assertEqual(len(sorted(d.glob("*-nat046-loader-diag-reset-bl-single-run-*.md"))), 1)

    def test_pinned_hashes_are_those_of_package_002_and_the_build_record(self):
        if not (PACKAGE / "package.json").exists():
            self.skipTest("package-002 is not present")
        src = DRIVER.read_text()
        pkg = json.loads((PACKAGE / "package.json").read_text())
        build = json.loads((BUILD / "build.json").read_text())
        self.assertRegex(src, r"(?m)^PACKAGE=ROOT/'artifacts/nat-044/package-002'")
        self.assertRegex(src, r"(?m)^STOCK_SHA='%s'" % pkg["stock_sha256"])
        self.assertTrue(pkg["flashed"] is False and pkg["build"] == "artifacts/nat-044/build-002")
        for image in IMAGES:
            p = pkg["images"][image]
            for value in (p["recovery_sha256"], p["payload_sha256"]):
                self.assertEqual(src.count(value), 1, (image, value))
            self.assertIn("CANARY_LEN=%d" % p["payload_bytes"], src)
            self.assertEqual(p["payload_offset"], 2048)
            self.assertIn("PAYLOAD_OFFSET=2048", src)
            self.assertEqual(build["image_payloads"][image]["sha256"], p["payload_sha256"])
            self.assertEqual(build["image_payloads"][image]["bytes"], p["payload_bytes"])
            self.assertNotEqual(p["payload_sha256"], p["loader_image_sha256"], "the payload, not the loader-only Image, is pinned")
            self.assertNotIn(p["loader_image_sha256"], src)
            rec = PACKAGE / image / "recovery.img"
            if rec.exists():
                self.assertEqual(sha256(rec), p["recovery_sha256"])
        # the two images are told apart by their pinned names, nothing else
        m = load(DRIVER, "driver_pins")
        self.assertEqual(sorted(m.IMAGES), sorted(IMAGES))
        for image in IMAGES:
            self.assertEqual((m.IMAGES[image]["NEW_SHA"], m.IMAGES[image]["CANARY_SHA"], m.IMAGES[image]["CANARY_LEN"]),
                             (pkg["images"][image]["recovery_sha256"], pkg["images"][image]["payload_sha256"], pkg["images"][image]["payload_bytes"]))
        self.assertEqual(m.STOCK_SHA, STOCK_SHA)

    def test_reboot_and_flash_surface(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("reboot','recovery'"), 1)
        self.assertEqual(len(re.findall(r"'reboot'", src)), 1, "no other reboot form (reboot bootloader/download, a plain reboot)")
        self.assertNotIn("fastboot", src.lower())
        self.assertEqual(len(re.findall(r"odin|heimdall", src)), 2)
        self.assertIn("['odin4','heimdall']", src)
        self.assertEqual(sorted(set(re.findall(r"/dev/block/[\w/.-]+", src))), ["/dev/block/by-name/recovery", "/dev/block/sda18"])
        self.assertEqual(len(re.findall(r"dd of=", src)), 1)

    def test_the_driver_never_creates_the_decision_file(self):
        src = DRIVER.read_text()
        self.assertEqual(src.count("ROOT/'docs/decisions'"), 1)
        self.assertRegex(src, r"glob\('\*-nat046-%s-single-run-\*\.md'%image\)")
        self.assertNotRegex(src, r"decisions[^\n]*(write_text|write_bytes|open\()")
        self.assertIn("marker.open('x')", src)
        self.assertIn("exist_ok=False", src)

    def test_the_gate_is_checked_before_the_first_adb_call(self):
        src = DRIVER.read_text()
        gate_at = src.index("gate(a.image,cfg)")
        self.assertLess(gate_at, src.index("run(['adb','get-state'])"))
        self.assertLess(gate_at, src.index("if not a.restore:watcher_selftest()"))
        self.assertLess(gate_at, src.index("watcher_start()\n"))
        self.assertEqual(src.count("gate(a.image,cfg)"), 1)

    def test_the_safety_lines_are_those_of_the_nat037_driver(self):
        old = {l.strip() for l in NAT037_DRIVER.read_text().splitlines()}
        new = {l.strip() for l in DRIVER.read_text().splitlines()}
        keep = [
            "SIZE=100663296", "TARGET='/dev/block/sda18'",
            "WRITE=\"su -c 'test -b /dev/block/sda18 && dd of=/dev/block/sda18 bs=1048576 count=100663296 iflag=count_bytes conv=notrunc,fsync'\"",
            "assert len(data)==SIZE and digest(data)==expected", "assert dd_idle(), 'a remote dd process is still running'",
            "assert measured==expected,'full RECOVERY readback mismatch'", "assert identity.splitlines()==[TARGET,str(SIZE),'block_device'],identity",
            "assert int(values['level'])>=50 and int(values['temperature'])<420",
            "assert not any(s.strip().lower() in ['odin4','heimdall'] for s in processes),'another flasher is active'",
            "if not a.restore: assert initial==STOCK_SHA, 'launch requires unchanged stock RECOVERY'",
            "assert len(stock)==len(candidate)==SIZE and digest(stock)==STOCK_SHA and digest(candidate)==NEW_SHA",
            "run(['adb','reboot','recovery'])", "report['reboot_sent']=True;report['reboot_requested_at']=now();save()",
            "if report['device_write_started'] and not report['reboot_sent'] and not a.restore:",
            "write(stock,STOCK_SHA);report['outcome']='launch-aborted-stock-restored';save()",
            "assert shell('getprop ro.product.model')=='SM-S921B'", "assert shell('getprop ro.build.PDA')=='S921BXXS9BYH3'",
            "fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)", "write(stock,STOCK_SHA);report['outcome']='stock-written-readback-confirmed';save();print(report['outcome']);return 0",
        ]
        for line in keep:
            self.assertIn(line, old, "not in the NAT-037 driver: " + line)
            self.assertIn(line, new, "missing from the NAT-048 driver: " + line)

    def test_the_driver_differs_from_the_nat037_driver_only_where_the_task_says(self):
        def code(path):
            text = path.read_text()
            m = re.search(r'"""(.*?)"""', text, re.S)
            return [l.strip() for l in (text[:m.start()] + text[m.end():]).splitlines() if l.strip()]
        removed = [l[2:] for l in difflib.ndiff(code(NAT037_DRIVER), code(DRIVER)) if l.startswith("- ")]
        self.assertEqual(removed, [
            "CANDIDATE=ROOT/'artifacts/nat-036/package-001/recovery.img'",
            "NEW_SHA='c61165cb0264388098705deea0421e12d77f612791c3b2d579e46bf40abd4f0b'",
            "CANARY_SHA='0e556d94b9921ba4cdc426d89e613dbd4e0c694391c220c9429958aae631911a'  # loader-diag-xnu-ckpt3 Image.payload (stops 11,30,35,12,44,13,14,15,16)",
            "CANARY_LEN=21784160",
            "p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)",
            "report=dict(at=now(),mode='restore' if a.restore else 'launch' if a.execute else 'preflight',",
            "pkg=json.loads((CANDIDATE.parent/'package.json').read_text())",
            "assert pkg['recovery_sha256']==NEW_SHA and pkg['source_image_sha256']==CANARY_SHA and pkg['flashed'] is False",
            "assert (ROOT/'docs/decisions/0018-nat036-loader-diag-xnu-ckpt3-single-run-2026-11-11.md').exists(), 'owner decision 0018 is missing: no device access'",
            "assert digest(candidate[2048:2048+CANARY_LEN])==CANARY_SHA,'loader Image.payload not at its expected offset'",
            "marker=ROOT/'artifacts/nat-022/native-attempt-xnuckpt3-used.json'",
            "json.dump(dict(at=now(),image_sha256=NEW_SHA,attempt=str(a.out)),f);f.write('\\n');f.flush();os.fsync(f.fileno())",
            "report['outcome']='native-attempt-started';save();print(json.dumps(dict(outcome=report['outcome'],image_sha256=NEW_SHA,reboot_requested_at=report['reboot_requested_at'])));return 0",
        ])


class OpenGateFlow(unittest.TestCase):
    """The driver in a scratch tree with fake decision files, a fake adb that models the RECOVERY block in a file, and the real
    watcher pointed at a fake sysfs through a one-file wrapper (the production driver has no test hook)."""

    @classmethod
    def setUpClass(cls):
        needed = [STOCK, PACKAGE / "package.json"] + [PACKAGE / i / "recovery.img" for i in IMAGES]
        for p in needed:
            if not p.exists():
                raise unittest.SkipTest("missing %s" % p)
        cls.tmp = Path(tempfile.mkdtemp(prefix="nat048-"))
        t = cls.tmp
        drv = t / "docs/procedures/nat-048"
        drv.mkdir(parents=True)
        shutil.copy(DRIVER, drv / "session_reset_canary.py")
        (drv / "usb_watch.py").write_text(WRAPPER)
        (t / "docs/decisions").mkdir(parents=True)
        for rel in ("package.json",) + tuple("%s/recovery.img" % i for i in IMAGES):
            dst = t / "artifacts/nat-044/package-002" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(PACKAGE / rel, dst)
        (t / "devices/recovery/backups/2026-11-10").mkdir(parents=True)
        os.symlink(STOCK, t / "devices/recovery/backups/2026-11-10/recovery.img")
        (t / "bin").mkdir()
        adb = t / "bin/adb"
        adb.write_text(FAKE_ADB.replace("{python}", sys.executable))
        adb.chmod(0o755)
        cls.driver = drv / "session_reset_canary.py"
        cls.pids = []

    @classmethod
    def tearDownClass(cls):
        for pid in cls.pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="dev-", dir=self.tmp))
        self.sysfs = self.base / "sys"
        self.sysfs.mkdir()
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        for p in (self.tmp / "docs/decisions").glob("*"):
            p.unlink()
        for p in (self.tmp / "artifacts/nat-048").glob("native-attempt-*") if (self.tmp / "artifacts/nat-048").exists() else []:
            p.unlink()
        self.n = 0
        self.decide("loader-diag-reset")

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        shutil.rmtree(self.base, ignore_errors=True)

    def decide(self, image, **kw):
        (self.tmp / "docs/decisions" / ("0099-nat046-%s-single-run-2026-11-12.md" % image)).write_text(decision_text(image, **kw))

    def run_driver(self, *mode, image="loader-diag-reset", env_extra=None):
        self.n += 1
        out = self.base / ("out%d" % self.n)
        env = {"PATH": f"{self.tmp / 'bin'}:/usr/bin:/bin", "HOME": str(self.tmp), "FAKE_DEVICE_DIR": str(self.base), "FAKE_SYSFS": str(self.sysfs),
               "FAKE_WATCH_LOG": str(out / "usb-events.jsonl"), "REAL_WATCHER": str(WATCH)}
        env.update(env_extra or {})
        r = subprocess.run([sys.executable, str(self.driver), "--image", image, "--out", str(out), *mode], capture_output=True, text=True, env=env, timeout=300)
        rep = json.loads((out / "report.json").read_text())
        if "watcher" in rep:
            self.pids.append(rep["watcher"]["pid"])
        return r, rep, out

    def calls(self):
        p = self.base / "adb-calls"
        return p.read_text().splitlines() if p.exists() else []

    def reboots(self):
        return [c for c in self.calls() if c.startswith("reboot")]

    def device_sha(self):
        return sha256(self.base / "recovery.bin")

    def marker(self, image="loader-diag-reset"):
        return self.tmp / ("artifacts/nat-048/native-attempt-%s-used.json" % image)

    def test_preflight_is_read_only_and_proves_the_watcher_first(self):
        r, rep, out = self.run_driver()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "ready-read-only")
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["device_write_started"] or rep["reboot_sent"])
        self.assertFalse(self.marker().exists())
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertEqual(rep["watcher_selftest"]["events"], ["start", "stop"])
        self.assertNotIn("watcher", rep, "the preflight leaves no detached watcher")
        self.assertTrue((out / "usb-selftest.jsonl").exists())

    def test_execute_writes_reads_back_starts_the_watcher_then_reboots_once(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "native-attempt-started")
        new_sha = pinned("loader-diag-reset")["recovery_sha256"]
        self.assertEqual(self.device_sha(), new_sha)
        self.assertEqual(rep["readback_sha256"], new_sha)
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296"])
        self.assertEqual(self.reboots(), ["reboot recovery"])
        calls = self.calls()
        write = next(i for i, c in enumerate(calls) if c.startswith("shell -T") and "dd of=" in c)
        readback = max(i for i, c in enumerate(calls) if "sha256sum /dev/block/sda18" in c)
        self.assertLess(write, readback)
        self.assertLess(readback, calls.index("reboot recovery"))
        self.assertEqual(calls[-1], "reboot recovery")
        self.assertEqual((self.base / "reboot-saw-watcher").read_text(), "yes", "the watcher had logged its start record before the reboot was sent")
        self.assertTrue(rep["watcher"]["start_record_seen"])
        self.assertEqual(rep["decision_file"], "0099-nat046-loader-diag-reset-single-run-2026-11-12.md")
        self.assertLess(rep["watcher"]["started_at"], rep["reboot_requested_at"])
        self.assertEqual(json.loads(self.marker().read_text())["image_sha256"], new_sha)
        self.assertIn("reboot_requested_at", r.stdout)
        self.assertIn("usb-events.jsonl", r.stdout)

    def test_the_watcher_outlives_the_driver_and_sees_the_device_leave_and_return(self):
        r, rep, out = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pid = rep["watcher"]["pid"]
        os.kill(pid, 0)                                                  # still alive after the driver exited
        self.assertEqual(rep["watcher"]["seconds"], 240)
        self.assertIn(b"\x00240\x00", Path("/proc/%d/cmdline" % pid).read_bytes() + b"\x00", "the watcher runs for 240 s, long enough to cover +95 s and +118 s of runs 001-009")
        add_dev(self.sysfs, "1-2", pid="6860", product="SM-S921B")
        self.wait_events(out, lambda e: any(x["event"] == "appear" for x in e))
        rm_dev(self.sysfs, "1-2")
        add_dev(self.sysfs, "1-2", pid="685d", product="SEC_UPLOAD", devnum="9")
        rows = self.wait_events(out, lambda e: any(x["event"] == "appear" and x.get("product") == "SEC_UPLOAD" for x in e))
        self.assertEqual([x["event"] for x in rows][:1], ["start"])
        # the session is a new process group: not the driver's, so the driver's exit did not end it
        self.assertNotEqual(os.getpgid(pid), os.getpgid(os.getpid()))
        os.kill(pid, signal.SIGTERM)
        self.wait_events(out, lambda e: e[-1]["event"] == "stop")

    def wait_events(self, out, pred, timeout=15):
        end = time.time() + timeout
        log = out / "usb-events.jsonl"
        while time.time() < end:
            rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []
            if rows and pred(rows):
                return rows
            time.sleep(0.05)
        self.fail("timed out waiting for the watcher log: %s" % (log.read_text() if log.exists() else "<none>"))

    def test_the_reboot_waits_for_the_watchers_start_record(self):
        r, rep, out = self.run_driver("--execute", env_extra={"FAKE_WATCHER_DELAY": "1.5"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.base / "reboot-saw-watcher").read_text(), "yes", "a slow watcher delays the reboot instead of missing its window")
        self.assertTrue(rep["watcher"]["start_record_seen"])

    def test_the_report_and_the_log_make_the_analyzer_usable(self):
        r, rep, out = self.run_driver("--execute")
        t0 = datetime.datetime.fromisoformat(rep["reboot_requested_at"]).timestamp()
        events = self.wait_events(out, lambda e: any(x["event"] == "start" for x in e))
        self.assertLessEqual(events[0]["t_unix"], t0, "the start record precedes the reboot request: the log covers T0")
        self.assertGreaterEqual(t0, datetime.datetime.fromisoformat(rep["watcher"]["started_at"]).timestamp())

    def test_the_second_image_uses_its_own_pins_decision_and_marker(self):
        self.decide("loader-diag-reset-bl")
        r, rep, out = self.run_driver("--execute", image="loader-diag-reset-bl")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.device_sha(), pinned("loader-diag-reset-bl")["recovery_sha256"])
        self.assertTrue(self.marker("loader-diag-reset-bl").exists())
        self.assertFalse(self.marker("loader-diag-reset").exists())
        self.assertEqual(self.reboots(), ["reboot recovery"])

    def test_a_second_execute_is_refused_by_the_marker_before_any_write(self):
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        shutil.copyfile(STOCK, self.base / "recovery.bin")
        (self.base / "writes").unlink()
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stopped")
        self.assertFalse(rep["device_write_started"] or rep["reboot_sent"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), ["reboot recovery"], "exactly one reboot over both sessions")

    def test_the_marker_of_one_image_does_not_block_the_other(self):
        self.decide("loader-diag-reset-bl")
        self.marker("loader-diag-reset-bl").parent.mkdir(parents=True, exist_ok=True)
        self.marker("loader-diag-reset-bl").write_text("{}")
        r, rep, _ = self.run_driver("--execute", image="loader-diag-reset")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_readback_mismatch_restores_stock_and_never_reboots_or_starts_a_watcher(self):
        (self.base / "corrupt-first-write").write_text("")
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("readback mismatch", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["reboot_sent"])
        self.assertNotIn("watcher", rep)
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertEqual((self.base / "writes").read_text().split(), ["100663296", "100663296"])

    def test_a_watcher_that_cannot_start_after_the_write_restores_stock_and_never_reboots(self):
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_WATCHER_FAIL_RUN": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "launch-aborted-stock-restored")
        self.assertIn("watcher did not log its start record", rep["error"])
        self.assertEqual(self.reboots(), [])
        self.assertFalse(rep["reboot_sent"])
        self.assertFalse(rep["watcher"]["start_record_seen"])
        self.assertEqual(self.device_sha(), STOCK_SHA)

    def test_a_failing_watcher_selftest_stops_before_any_write(self):
        r, rep, _ = self.run_driver("--execute", env_extra={"FAKE_WATCHER_FAIL_SELFTEST": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("self-test failed", rep["error"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())
        r, rep, _ = self.run_driver(env_extra={"FAKE_WATCHER_FAIL_SELFTEST": "1"})
        self.assertEqual(r.returncode, 2, "the read-only preflight reports a broken watcher too")

    def test_a_decision_that_does_not_name_the_hashes_or_decision_0019_opens_nothing(self):
        for kw in (dict(with_recovery=False), dict(with_payload=False), dict(with_0019=False)):
            self.decide("loader-diag-reset", **kw)
            before = len(self.calls())
            for mode in ((), ("--execute",), ("--restore",)):
                r, rep, _ = self.run_driver(*mode)
                self.assertEqual(r.returncode, 2, (kw, mode, r.stdout))
                self.assertIn("does not name", rep["error"])
            self.assertEqual(len(self.calls()), before, "no adb call: %r" % (kw,))
        self.assertFalse((self.base / "writes").exists())

    def test_two_decision_files_for_one_image_are_ambiguous(self):
        (self.tmp / "docs/decisions" / "0098-nat046-loader-diag-reset-single-run-2026-11-12.md").write_text(decision_text("loader-diag-reset"))
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ambiguous (2 found)", rep["error"])
        self.assertEqual(self.calls(), [])

    def test_a_decision_of_the_other_image_does_not_open_this_one(self):
        for p in (self.tmp / "docs/decisions").glob("*"):
            p.unlink()
        self.decide("loader-diag-reset-bl")
        r, rep, _ = self.run_driver("--execute", image="loader-diag-reset")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_a_busy_remote_dd_blocks_every_write(self):
        (self.base / "dd-busy").write_text("")
        for mode in ((), ("--execute",), ("--restore",)):
            r, rep, _ = self.run_driver(*mode)
            self.assertEqual(r.returncode, 2, (mode, r.stdout, r.stderr))
            self.assertFalse((self.base / "writes").exists(), mode)
            self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_restore_writes_stock_without_a_reboot_or_a_watcher(self):
        r, _, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.device_sha(), STOCK_SHA)
        r, rep, out = self.run_driver("--restore")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["outcome"], "stock-written-readback-confirmed")
        self.assertEqual(self.device_sha(), STOCK_SHA)
        self.assertEqual(self.reboots(), ["reboot recovery"], "only the launch rebooted")
        self.assertFalse(rep["reboot_sent"])
        self.assertNotIn("watcher", rep)
        self.assertNotIn("watcher_selftest", rep)

    def test_launch_refuses_a_recovery_that_is_not_stock(self):
        data = bytearray(STOCK.read_bytes())
        data[100] ^= 0xFF
        (self.base / "recovery.bin").write_bytes(bytes(data))
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unchanged stock RECOVERY", rep["error"])
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_launch_refuses_a_low_battery(self):
        (self.base / "battery").write_text("49")
        r, rep, _ = self.run_driver("--execute")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.base / "writes").exists())
        self.assertEqual(self.reboots(), [])
        self.assertFalse(self.marker().exists())

    def test_the_candidate_packages_the_payload_not_the_loader_only_image(self):
        for image in IMAGES:
            p = pinned(image)
            img = (PACKAGE / image / "recovery.img").read_bytes()
            payload = (BUILD / image / "Image.payload")
            if not payload.exists():
                self.skipTest("build-002 not present")
            self.assertEqual(hashlib.sha256(img[2048:2048 + p["payload_bytes"]]).hexdigest(), p["payload_sha256"])
            self.assertEqual(sha256(payload), p["payload_sha256"])


if __name__ == "__main__":
    unittest.main()
