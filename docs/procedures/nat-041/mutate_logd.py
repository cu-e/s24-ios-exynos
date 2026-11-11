#!/usr/bin/env python3
"""Mutation check for the NAT-041 collector: break one line of s24_logd.py at a time in a scratch copy of the procedure
tree and require test_logd.py to fail. Host-only; it writes under the --out directory and nowhere else.

    python3 -I docs/procedures/nat-041/mutate_logd.py --out artifacts/nat-041/mutation-logd

A mutant that is not killed is reported and makes the exit status non-zero.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# (name, old, new): `old` must occur exactly once in s24_logd.py
MUTANTS = [
    ("reset-detection-disabled", "        return (not (info[\"flags\"] & P.F_NONCE_SET) or info[\"nonce\"] != boot.nonce or info[\"boot_id\"] != boot.dev_boot\n                or info[\"written\"] < boot.next_off)",
     "        return False"),
    ("device-boot-block-not-compared", " or info[\"boot_id\"] != boot.dev_boot\n                or info[\"written\"] < boot.next_off)", "\n                or info[\"written\"] < boot.next_off)"),
    ("stream-regression-not-a-reset", "\n                or info[\"written\"] < boot.next_off)", ")"),
    ("nonce-echo-not-checked", "if not info[\"flags\"] & P.F_NONCE_SET or info[\"nonce\"] != nonce:", "if False:"),
    ("resume-ignores-the-nonce", " and info[\"nonce\"] == live.nonce\n                    and info[\"boot_id\"] == live.dev_boot", "\n                    and info[\"boot_id\"] == live.dev_boot"),
    ("resume-ignores-the-device-boot-block", "\n                    and info[\"boot_id\"] == live.dev_boot and info[\"written\"] >= live.next_off):", " and info[\"written\"] >= live.next_off):"),
    ("resume-gone-marker-not-cleared", "                live.gone_at = None\n", ""),
    ("grace-compare-inverted", "self.clock() - self.live.gone_at > self.grace", "self.clock() - self.live.gone_at < self.grace"),
    ("ring-overrun-not-reported", "        if delta:\n            self._drop(boot, \"ring-overrun\"", "        if False:\n            self._drop(boot, \"ring-overrun\""),
    ("overrun-position-not-advanced", "            boot.next_off += delta\n", ""),
    ("stream-going-backwards-accepted", "        if delta >= 1 << 31:\n            return \"reset\"", "        if False:\n            return \"reset\""),
    ("offset-high-half-wrong", "off >> 16, P.READ_MAX", "off >> 8, P.READ_MAX"),
    ("offset-low-half-wrong", "off & 0xFFFF, off >> 16", "off & 0xFF, off >> 16"),
    ("offset-not-wrapped-to-32-bits", "off = boot.next_off & 0xFFFFFFFF", "off = boot.next_off & 0xFFFFFFFFFF"),
    ("sequence-gap-not-reported", "            if boot.dev_next_seq is not None and seq != boot.dev_next_seq:", "            if False:"),
    ("crc-error-not-reported", "        if err is not None:\n            skipped", "        if False:\n            skipped"),
    ("resync-skips-one-byte-too-many", "                return i - pos\n", "                return i - pos + 1\n"),
    ("resync-never-skips-the-record", "        return max(1, len(payload) - pos - (P.REC_HDR - 1))", "        return 0"),
    ("lost-before-connect-not-reported", "        if info[\"oldest\"] > 0:", "        if False:"),
    ("unread-bytes-not-reported", "        if unread:\n            self.archive.error", "        if False:\n            self.archive.error"),
    ("end-frame-not-written", "        self._emit(boot, \"end\", self._json(dict(reason=reason,", "        return\n        self._emit(boot, \"end\", self._json(dict(reason=reason,"),
    ("exception-fetched-on-every-cycle", " or boot.exc_faults == info[\"faults\"]:", ":"),
    ("exception-never-refetched", "        boot.exc_faults = info[\"faults\"]\n", "        boot.exc_faults = 1\n"),
    ("exception-frame-not-raw", "self._emit(boot, \"fault\", raw, source=\"get_exc\"", "self._emit(boot, \"fault\", b\"\", source=\"get_exc\""),
    ("unresponsive-threshold-inverted", "if self.clock() - last_ok > self.dead_after:", "if self.clock() - last_ok < self.dead_after:"),
    ("repeated-start-failures-all-recorded", "        if reason != self._last_start_failure:", "        if True:"),
    ("boot-id-without-the-host-nonce", "boot_id = \"%s-%s\" % (nonce.hex(), info[\"boot_id\"].hex())", "boot_id = \"%s-%s\" % (info[\"boot_id\"].hex(), info[\"boot_id\"].hex())"),
    ("nonce-reused-between-boots", "nonce = self.rng(P.NONCE_LEN)", "nonce = b\"\\x11\" * P.NONCE_LEN"),
    ("samsung-not-refused", "REFUSED_VIDS = (0x04E8,)", "REFUSED_VIDS = ()"),
    ("drain-skipped-at-stop", "        if stop in (\"deadline\", \"interrupted\"):\n            self._drain()", "        if False:\n            self._drain()"),
    ("size-limit-treated-as-deliberate", "deliberate = stop in (\"deadline\", \"interrupted\")", "deliberate = stop in (\"deadline\", \"interrupted\", \"size-limit\")"),
    ("deadline-recorded-as-error", "return archive.finish(\"eof\" if deliberate else stop)", "return archive.finish(stop)"),
    ("gone-errno-mapped-to-timeout", "        if errno == 19:\n            return UsbGone(str(e))", "        if errno == 19:\n            return UsbTimeout(str(e))"),
    ("access-errno-mapped-to-timeout", "        if errno == 13:\n            return UsbAccess(str(e))", "        if errno == 13:\n            return UsbTimeout(str(e))"),
    ("stall-errno-mapped-to-timeout", "        if errno == 32:\n            return UsbStall(str(e))", "        if errno == 32:\n            return UsbTimeout(str(e))"),
    ("vendor-in-request-type-wrong", "VENDOR_IN = 0xC0", "VENDOR_IN = 0xA0"),
    ("vendor-out-request-type-wrong", "VENDOR_OUT = 0x40", "VENDOR_OUT = 0x20"),
    ("device-reported-drop-not-forwarded", "fkind = {P.K_STAGE: \"stage\", P.K_FAULT: \"fault\", P.K_DROP: \"drop\"}.get(kind, \"log\")", "fkind = {P.K_STAGE: \"stage\", P.K_FAULT: \"fault\"}.get(kind, \"log\")"),
    ("frames-numbered-from-one", "        self.fseq = 0\n", "        self.fseq = 1\n"),
    ("transfers-not-logged", "        self.stats[\"transfers\"] += 1\n        row = ", "        return\n        row = "),
    ("access-denied-recorded-every-time", "            if not self._access_noted:", "            if True:"),
    ("multiple-devices-not-reported", "                if len(devs) > 1 and self.stats[\"sessions\"] == 0:", "                if False:"),
    ("backend-error-swallowed", "                    self.archive.error(\"usb-backend\", detail=str(e))\n                    stop = \"backend-error\"\n                    break", "                    self.sleep(self.wait_interval)\n                    continue"),
]


def run_tests(tree, timeout):
    try:
        r = subprocess.run([sys.executable, "-I", os.path.join(tree, "docs", "procedures", "nat-041", "test_logd.py")],
                           capture_output=True, text=True, timeout=timeout, cwd=tree)
    except subprocess.TimeoutExpired as e:
        return "timeout", (e.stdout or b"")[-400:] if isinstance(e.stdout, bytes) else ""
    return r.returncode, r.stderr[-600:]


def make_tree(dst):
    base = os.path.join(dst, "docs", "procedures")
    os.makedirs(base)
    shutil.copytree(HERE, os.path.join(base, "nat-041"), ignore=shutil.ignore_patterns("__pycache__", "evidence.json"))
    os.makedirs(os.path.join(base, "nat-016"))
    shutil.copy(os.path.join(HERE, "..", "nat-016", "archive.py"), os.path.join(base, "nat-016", "archive.py"))
    return os.path.join(base, "nat-041", "s24_logd.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=False)
    results, survived = [], 0
    with tempfile.TemporaryDirectory(prefix="nat041-mut-") as tmp:
        tree = os.path.join(tmp, "base")
        target = make_tree(tree)
        base_rc, tail = run_tests(tree, a.timeout)
        results.append(dict(name="baseline (unmutated copy)", killed=None, exit=base_rc))
        if base_rc != 0:
            print("baseline fails; refusing to judge mutants:\n" + str(tail))
            return 2
        with open(target) as f:
            original = f.read()
        for i, (name, old, new) in enumerate(MUTANTS):
            n = original.count(old)
            if n != 1:
                results.append(dict(name=name, killed=None, exit=None, error="anchor occurs %d times" % n))
                survived += 1
                print("%-45s ANCHOR MISMATCH (%d)" % (name, n))
                continue
            mt = os.path.join(tmp, "m%02d" % i)
            mtarget = make_tree(mt)
            with open(mtarget, "w") as f:
                f.write(original.replace(old, new))
            rc, tail = run_tests(mt, a.timeout)
            killed = rc != 0
            survived += 0 if killed else 1
            results.append(dict(name=name, killed=killed, exit=rc))
            print("%-45s %s" % (name, "killed (exit %s)" % rc if killed else "SURVIVED"))
            shutil.rmtree(mt)
    summary = dict(total=len(MUTANTS), killed=sum(1 for r in results if r.get("killed")), survived=survived, results=results)
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("killed %d of %d" % (summary["killed"], summary["total"]))
    return 0 if survived == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
