#!/usr/bin/env python3
"""Copy allowlisted vendor RIL code via existing shell access; never execute it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
EXPECTED = {"ro.product.model": "SM-S921B", "ro.product.device": "e1s",
            "ro.build.version.incremental": "S921BXXS9BYH3"}
NAMES = ("libsec-ril.so", "libsec-ril-dsds.so", "libsitril.so", "libsecril-client.so", "libsitril-client.so")
REMOTE = tuple("/vendor/lib64/" + name for name in NAMES)
PRIMARY = set(NAMES[:3])
MAX_BYTES = 64 * 1024 * 1024
SCRIPTS = {"id -u", *("getprop " + key for key in EXPECTED),
           *("stat -c '%F|%s' " + path for path in REMOTE),
           *("sha256sum " + path for path in REMOTE)}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def elf_identity(path):
    with path.open("rb") as stream:
        header = stream.read(64)
    if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("Expected a little-endian ELF64 header")
    kind, machine, version = struct.unpack_from("<HHI", header, 16)
    if (kind, machine, version) != (3, 183, 1) or struct.unpack_from("<H", header, 52)[0] != 64:
        raise ValueError("Expected an AArch64 ELF shared-library header")
    return {"class": "ELF64", "endian": "little", "type": "ET_DYN", "machine": "AArch64",
            "scope": "Header identity only, not full ELF/ABI validation or code execution"}


def remote_digest(text):
    match = re.fullmatch(r"([0-9a-f]{64})[ \t]+[^\r\n]+", text.strip())
    if not match:
        raise ValueError("Invalid remote SHA256 response")
    return match.group(1)


class Bridge:
    def __init__(self, executable, out, report, endpoint=None, runner=subprocess.run, select_reference=False, sync_verify=False):
        self.executable, self.out, self.report = str(executable), out, report
        self.endpoint, self.runner = endpoint, runner
        self.select_reference = select_reference
        self.sync_verify = sync_verify
        self.deadline = time.monotonic() + 240

    def run(self, tail, selected=True):
        if selected and not self.endpoint:
            raise ValueError("An authorized endpoint must be selected first")
        argv = [self.executable, *(["-s", self.endpoint] if selected else []), *tail]
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Passive acquisition deadline exhausted")
        safe = ["<selected-device>" if self.endpoint and a == self.endpoint else a for a in argv]
        item = {"argv": safe, "exit_code": None}
        self.report["commands"].append(item)
        try:
            result = self.runner(argv, capture_output=True, text=True, timeout=min(45, remaining))
        except subprocess.TimeoutExpired:
            item["error"] = "timeout"
            raise RuntimeError("Passive ADB command timed out") from None
        item["exit_code"] = result.returncode
        # Device enumeration contains serials. Retain counts/state through select,
        # never the raw stdout. Other commands are strictly allowlisted below.
        if not selected:
            return result
        stdout, stderr = result.stdout, result.stderr
        if self.endpoint:
            stdout, stderr = stdout.replace(self.endpoint, "<selected-device>"), stderr.replace(self.endpoint, "<selected-device>")
        log = self.out / ("command-%03d.txt" % (len(self.report["commands"]) - 1))
        log.write_text(stdout + stderr)
        log.chmod(0o600)
        item.update(log=str(log.relative_to(ROOT)) if log.is_relative_to(ROOT) else log.name, log_sha256=digest(log))
        return result

    def select(self):
        result = self.run(["devices", "-l"] if self.select_reference else ["devices"], selected=False)
        if result.returncode:
            raise RuntimeError("ADB endpoint enumeration failed")
        rows = [line.split() for line in result.stdout.splitlines()[1:] if line.strip()]
        if self.select_reference:
            rows = [row for row in rows if len(row) > 1 and row[1] == "device"
                    and "model:SM_S921B" in row and "device:e1s" in row]
            self.report["selection_strategy"] = "unique authorized model/device metadata; transport type not inferred"
        if self.endpoint:
            rows = [row for row in rows if row[0] == self.endpoint]
        self.report["matching_endpoint_count"] = len(rows)
        if len(rows) != 1 or len(rows[0]) < 2 or rows[0][1] != "device":
            raise RuntimeError("Need one already-authorized endpoint; no pairing or connection change attempted")
        self.endpoint = rows[0][0]

    def shell(self, script):
        if script not in SCRIPTS:
            raise ValueError("Remote operation is outside the literal passive allowlist")
        return self.run(["shell", script])

    def pull(self, remote, destination):
        allowed = (self.out / Path(remote).name, self.out / "verification" / Path(remote).name)
        if remote not in REMOTE or destination not in allowed or destination.exists():
            raise ValueError("Only fresh private copies of allowlisted vendor libraries are accepted")
        return self.run(["pull", remote, str(destination)])


def identity(bridge):
    actual = {}
    for key in EXPECTED:
        result = bridge.shell("getprop " + key)
        if result.returncode:
            raise RuntimeError("Required target identity property unavailable")
        actual[key] = result.stdout.strip()
    if actual != EXPECTED:
        raise ValueError("Selected device/build does not match the exact measured BYH3 target")
    return actual


def collect(bridge, report, out):
    bridge.select()
    report["identity_before"] = identity(bridge)
    inventory = out / "device-inventory.json"
    inventory.write_text(json.dumps({"schema_version": 1, "origin": "local-device",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "properties": report["identity_before"], "matches_reference_target": True,
        "scope": "Fresh exact model/device/build properties only; no native/unlock/recovery proof"}, indent=2) + "\n")
    inventory.chmod(0o600)
    report["device_inventory"] = str(inventory.relative_to(ROOT)) if inventory.is_relative_to(ROOT) else inventory.name
    report["device_inventory_sha256"] = digest(inventory)
    uid = bridge.shell("id -u")
    if uid.returncode or uid.stdout.strip() != "2000":
        raise ValueError("Use the existing unprivileged Android shell; no root context is adopted")
    report["shell_uid"] = 2000
    for remote in REMOTE:
        record = {"remote": remote, "status": "unavailable"}
        report["files"].append(record)
        stat = bridge.shell("stat -c '%F|%s' " + remote)
        if stat.returncode:
            record["reason"] = "not readable through current shell"
            continue
        match = re.fullmatch(r"regular file\|([0-9]+)", stat.stdout.strip())
        if not match or not 64 <= int(match.group(1)) <= MAX_BYTES:
            record["reason"] = "not an allowed bounded regular library file; no symlink is followed"
            continue
        size = int(match.group(1))
        record["stat_bytes"] = size
        before = bridge.shell("sha256sum " + remote)
        if before.returncode and not bridge.sync_verify:
            record["reason"] = "remote digest unavailable"
            continue
        expected = remote_digest(before.stdout) if before.returncode == 0 else None
        destination = out / Path(remote).name
        pulled = bridge.pull(remote, destination)
        if destination.is_file():
            destination.chmod(0o600)
        if pulled.returncode:
            record["reason"] = "copy failed; no root or retry escalation"
            continue
        if not destination.is_file() or destination.is_symlink() or destination.stat().st_size != size:
            raise ValueError("Copied library extent/type differs")
        actual = digest(destination)
        if expected is not None:
            after = bridge.shell("sha256sum " + remote)
            if after.returncode or actual != expected or remote_digest(after.stdout) != expected:
                raise ValueError("Remote/local library bytes changed during passive acquisition")
            method = "remote SHA256 before/local bytes/remote SHA256 after"
        else:
            # Normal ADB sync service only, at existing permissions. No shell
            # bypass, root, helper installation or access-control change.
            verification = out / "verification"
            verification.mkdir(mode=0o700, exist_ok=True)
            repeated = verification / destination.name
            copied = bridge.pull(remote, repeated)
            if repeated.is_file():
                repeated.chmod(0o600)
            if (copied.returncode or not repeated.is_file() or repeated.is_symlink()
                    or repeated.stat().st_size != size or digest(repeated) != actual):
                raise ValueError("Independent authorized sync reads differ or verification copy unavailable")
            method = "two independent authorized ADB sync reads with matching local SHA256 and size"
        record.update(status="captured", bytes=size, sha256=actual, remote_sha256_before=expected,
                      remote_sha256_after=expected, elf=elf_identity(destination),
                      verification_method=method,
                      local=str(destination.relative_to(ROOT)) if destination.is_relative_to(ROOT) else destination.name)
    report["identity_after"] = identity(bridge)
    primary = [f for f in report["files"] if f["status"] == "captured" and Path(f["remote"]).name in PRIMARY]
    report.update(outcome="pass" if primary else "inconclusive",
                  summary="Matching vendor code copied and hashed through ordinary shell; no code/modem operation executed" if primary else "No primary library acquired from the narrow allowlist; no global absence or root requirement inferred")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--device", help="Optional explicit authorized endpoint, never saved")
    selection.add_argument("--select-reference", action="store_true", help="Require one authorized endpoint with exact model/device metadata, then independently recheck actual properties")
    parser.add_argument("--verify-sync-reads", action="store_true", help="When shell checksum is unavailable, try ordinary authorized ADB pull twice and require equal actual bytes; never claim a remote shell hash")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Use a new canonical run name")
    executable = shutil.which("adb")
    if not executable:
        raise RuntimeError("Installed adb is unavailable")
    out = ROOT / "artifacts/ril-capture" / args.run
    if out.resolve() != out:
        raise ValueError("Capture output cannot use symlink aliases")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {"kind": "android-userland", "origin": "local-device", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commands": [], "files": [],
              "collector_sha256": digest(Path(__file__)), "adb_sha256": digest(Path(executable)),
              "authorization_basis": "Existing user request to collect required technical device data and project android-readonly scope; passive vendor code copies only",
              "phone_writes": False, "root_requested": False, "binary_executed": False, "modem_command_sent": False,
              "limits": ["Exact source device/build and byte identity only; no vendor command schema or native/iOS compatibility established",
                         "No personal files, identifiers, radio state, calibration/NV, logs, subscriptions or firmware partitions collected",
                         "Regular files in a five-name vendor allowlist only; missing/symlink/unreadable candidates remain unavailable",
                         "If two ordinary sync reads are used, remote shell SHA256 remains unavailable; local digest/stability is not a signed stock-file attestation"]}
    (out / "collector.py").write_bytes(Path(__file__).read_bytes())
    (out / "collector.py").chmod(0o600)
    bridge = Bridge(executable, out, report, args.device, select_reference=args.select_reference, sync_verify=args.verify_sync_reads)
    try:
        collect(bridge, report, out)
    except (OSError, ValueError, RuntimeError) as error:
        # Do not include exception/argv text that could carry an endpoint ID.
        report.update(outcome="inconclusive" if isinstance(error, RuntimeError) else "fail",
                      error_type=type(error).__name__, error=str(error).replace(bridge.endpoint or "\0", "<selected-device>"))
    path = out / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    path.chmod(0o600)
    print(json.dumps({"outcome": report["outcome"], "captured": len([f for f in report["files"] if f["status"] == "captured"]),
                      "report": str(path.relative_to(ROOT))}))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
