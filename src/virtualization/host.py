#!/usr/bin/env python3
"""Prepare or run a bounded, host-only ARM64 XNU guest. No downloads or ADB."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import time

DONOR = "a6f4bc38aa244359cd365c976244a88c9d6b3304"
MARKER = b"VM002: pid=1 ostype=Darwin owned-entry=v1"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def macho(path, kernel=False):
    """Structural check only: never a complete-kernel qualification."""
    with path.open("rb") as stream:
        head = stream.read(32)
        if len(head) != 32:
            raise ValueError(f"{path}: truncated Mach-O header")
        magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack("<8I", head)
        if magic != 0xFEEDFACF or cpu != 0x0100000C or kind != 2:
            raise ValueError(f"{path}: expected executable arm64 Mach-O")
        if not 0 < count <= 4096 or size > 16 * 1024 * 1024:
            raise ValueError(f"{path}: invalid Mach-O command bounds")
        data = stream.read(size)
        if len(data) != size:
            raise ValueError(f"{path}: truncated load commands")
    offset, entry, dynamic = 0, None, False
    for _ in range(count):
        if offset + 8 > size:
            raise ValueError(f"{path}: truncated load command")
        cmd, length = struct.unpack_from("<II", data, offset)
        if length < 8 or length % 8 or offset + length > size:
            raise ValueError(f"{path}: invalid load command length")
        if cmd == 5:
            if length != 288 or struct.unpack_from("<II", data, offset + 8) != (6, 68):
                raise ValueError(f"{path}: expected ARM_THREAD_STATE64")
            entry = struct.unpack_from("<Q", data, offset + 272)[0]
        if cmd == 0x19:
            if length < 72:
                raise ValueError(f"{path}: truncated segment command")
            fileoff, filesize = struct.unpack_from("<QQ", data, offset + 40)
            if fileoff + filesize > path.stat().st_size:
                raise ValueError(f"{path}: segment exceeds file bounds")
        dynamic |= cmd in (0xC, 0xE, 0x18, 0x20, 0x80000018, 0x8000001F, 0x80000023)
        offset += length
    if offset != size or entry is None or dynamic:
        raise ValueError(f"{path}: need static LC_UNIXTHREAD executable")
    if kernel and entry < 0xFFFFFFF004000000:
        raise ValueError(f"{path}: not a kernel-space XNU entry; user executable rejected")
    return {"cpu": "arm64", "subtype": subtype, "filetype": kind,
            "commands": count, "entry": hex(entry)}


def payload(destination, kernel, pid1):
    # XNUP format reviewed at DONOR:xnuloader/mkpayload.py, MIT.
    entries = [(b"kernel", kernel.read_bytes()), (b"ramdisk", pid1.read_bytes()),
               (b"cmdline", b"cpus=1 -v console_quiet=0 avf_exit=1\0")]
    total = 24 + sum(24 + len(data) + (-len(data) % 16) for _, data in entries)
    if total > 0xFFFFFFFF:
        raise ValueError("XNUP payload exceeds 32-bit size")
    with destination.open("xb") as stream:
        stream.write(struct.pack("<II", 0x50554E58, total))
        for name, data in entries:
            stream.write(struct.pack("<16sII", name, len(data), 0))
            stream.write(data)
            stream.write(b"\0" * (-len(data) % 16))
        stream.write(b"\0" * 24)


def bounded(argv, console, seconds):
    """Only signal the process group created by this invocation."""
    start = time.monotonic()
    timed_out = False
    with console.open("xb") as output:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = proc.wait(timeout=2)
    return {"exit_code": code, "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - start, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--shim", type=Path)
    parser.add_argument("--pid1", type=Path)
    for name in ("kernel", "shim", "pid1"):
        parser.add_argument(f"--{name}-sha256")
    parser.add_argument("--qemu", default=shutil.which("qemu-system-aarch64"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=60, choices=range(1, 181))
    parser.add_argument("--memory-mib", type=int, default=512, choices=range(256, 769))
    parser.add_argument("--run", action="store_true", help="launch only after the coordinator grants a resource lease")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"donor_commit": DONOR, "origin": "local-host", "outcome": "blocked",
              "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "guest_started": False, "pid1_observed": False, "missing": [], "inputs": {},
              "limitations": ["Structural checks do not qualify a complete XNU kernel.",
                              "Host guest evidence establishes no S24 hardware support."]}
    for name in ("kernel", "shim", "pid1"):
        path, expected = getattr(args, name), getattr(args, name + "_sha256")
        if path is None or not path.is_file():
            report["missing"].append(f"Explicit existing {name} file and reviewed build provenance")
            continue
        if path.stat().st_size > 256 * 1024 * 1024:
            report["missing"].append(f"{name}: exceeds the preparation limit of 256 MiB")
            continue
        actual = sha256(path)
        report["inputs"][name] = {"path": str(path.resolve()), "sha256": actual}
        if not expected or actual != expected:
            report["missing"].append(f"{name}: explicit matching reviewed SHA256 required")
    if not args.qemu or not Path(args.qemu).is_file() or not os.access(args.qemu, os.X_OK):
        report["missing"].append("Explicit executable qemu-system-aarch64 path")
    else:
        report["inputs"]["qemu"] = {"path": str(Path(args.qemu).resolve()), "sha256": sha256(Path(args.qemu))}
        report["qemu_probes"] = []
        for option, required in (("-machine", "virt"), ("-accel", "tcg")):
            try:
                proc = subprocess.run([args.qemu, option, "help"], stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                output = proc.stdout.decode(errors="replace")
                report["qemu_probes"].append({"argv": [args.qemu, option, "help"],
                                             "exit_code": proc.returncode, "output": output})
                if proc.returncode or not any(line.split() and line.split()[0] == required
                                              for line in output.splitlines()):
                    report["missing"].append(f"QEMU {option} help must expose {required}")
            except (OSError, subprocess.SubprocessError) as error:
                report["missing"].append(f"QEMU {option} capability probe failed: {error}")
    if not report["missing"]:
        try:
            for name in ("kernel", "pid1"):
                report["inputs"][name]["structure"] = macho(getattr(args, name), kernel=name == "kernel")
            with args.shim.open("rb") as stream:
                image = stream.read(64)
            if len(image) != 64 or image[56:60] != b"ARM\x64":
                raise ValueError("shim: missing arm64 Image header")
            payload_path = args.out / "payload.bin"
            payload(payload_path, args.kernel, args.pid1)
            report["inputs"]["payload"] = {"path": str(payload_path.resolve()), "sha256": sha256(payload_path)}
            argv = [args.qemu, "-machine", "virt,gic-version=3", "-accel", "tcg",
                    "-cpu", "cortex-a76", "-smp", "1", "-m", str(args.memory_mib),
                    "-kernel", str(args.shim.resolve()), "-initrd", str(payload_path.resolve()),
                    "-nodefaults", "-nic", "none", "-display", "none", "-serial", "stdio",
                    "-monitor", "none", "-no-reboot"]
            report["argv"] = argv
            report["outcome"] = "prepared"
            if args.run:
                report["termination"] = bounded(argv, args.out / "console.txt", args.seconds)
                report["guest_started"] = True
                console = (args.out / "console.txt").read_bytes()
                report["pid1_observed"] = MARKER in console and b"Darwin Kernel Version" in console
                report["outcome"] = "observed" if report["pid1_observed"] else "fail"
                if report["termination"]["timed_out"]:
                    report["limitations"].append("Guest exceeded its deadline; owned process group was stopped.")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            report["outcome"] = "fail"
            report["error"] = str(error)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 2 if report["outcome"] in ("blocked", "fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
