#!/usr/bin/env python3
"""Build/check the pinned generic ARM64 QEMU host tool in local artifact paths."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / "fixtures/public/qemu-host/source.json"
GIB = 1024 ** 3


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sample(session=None):
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("MemAvailable", "SwapTotal", "SwapFree", "SwapCached"):
            memory[key + "_bytes"] = int(value.split()[0]) * 1024
    pressure = {}
    for line in Path("/proc/pressure/memory").read_text().splitlines():
        kind, *fields = line.split()
        pressure[kind] = {k: float(v) for k, v in (field.split("=") for field in fields)}
    rss, states = 0, []
    if session is not None:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
                if int(fields[3]) == session:
                    rss += int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
                    states.append({"pid": int(entry.name), "state": fields[0], "pgrp": int(fields[2])})
            except (OSError, IndexError, ValueError):
                pass
    return {"recorded_at": now(), **memory, "pressure": pressure,
            "owned_tree_rss_bytes": rss, "owned_processes": states}


def pressured(snapshot):
    return (snapshot["pressure"]["full"]["avg10"] >= 2 or
            snapshot["pressure"]["some"]["avg10"] >= 10)


def recovered(snapshot):
    return (snapshot["MemAvailable_bytes"] >= int(4.5 * GIB) and
            snapshot["pressure"]["full"]["avg10"] < 1 and
            snapshot["pressure"]["some"]["avg10"] < 5)


def group_signal(session, sig):
    # Ninja creates a new process group for each compiler command. All remain
    # in the new session we created, so signal every group in that session.
    groups = {session} | {p["pgrp"] for p in sample(session)["owned_processes"]}
    for group in [session, *sorted(groups - {session})]:
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            pass


def terminate(proc):
    # A stopped build must be continued so SIGTERM can be delivered.
    group_signal(proc.pid, signal.SIGCONT)
    group_signal(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # Also remove owned descendants if the leader exited before its children.
    group_signal(proc.pid, signal.SIGKILL)
    return proc.wait(timeout=2)


def run(argv, cwd, out, name, seconds, build_limit=False):
    """Finite stage; pause/stop only the new process group, with live samples."""
    start = time.monotonic()
    record = {"argv": [str(arg) for arg in argv], "cwd": str(cwd),
              "started_at": now(), "timeout_seconds": seconds, "events": []}
    before = sample()
    record["before"] = before
    if build_limit and (before["MemAvailable_bytes"] < 4 * GIB or pressured(before)):
        ready = 0
        with (out / (name + ".resource-wait.jsonl")).open("x") as waiting:
            while ready < 3:
                current = sample()
                waiting.write(json.dumps(current) + "\n")
                waiting.flush()
                ready = ready + 1 if recovered(current) else 0
                if time.monotonic() - start > min(seconds, 600):
                    record.update(exit_code=None, outcome="resource-deferred", after=current)
                    (out / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
                    raise RuntimeError("No build spawned: bounded resource recovery wait expired")
                time.sleep(2)
        record["events"].append({"event": "resource-ready-before-spawn", "recorded_at": now()})
        record["resource_wait_seconds"] = round(time.monotonic() - start, 3)
        start = time.monotonic()

    def limits():
        if build_limit:
            # Two compiler jobs have <=1 GiB virtual address space each.
            resource.setrlimit(resource.RLIMIT_AS, (GIB, GIB))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with (out / (name + ".log")).open("xb") as log, (out / (name + ".samples.jsonl")).open("x") as samples:
        proc = subprocess.Popen(record["argv"], cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=limits)
        record["owned_session"] = proc.pid
        paused, high_samples = False, 0
        record["peak_owned_tree_rss_bytes"] = 0
        try:
            while proc.poll() is None:
                current = sample(proc.pid)
                samples.write(json.dumps(current) + "\n")
                samples.flush()
                record["peak_owned_tree_rss_bytes"] = max(
                    record["peak_owned_tree_rss_bytes"], current["owned_tree_rss_bytes"])
                high_samples = high_samples + 1 if pressured(current) else 0
                if time.monotonic() - start > seconds:
                    record["events"].append({"event": "deadline", "recorded_at": now()})
                    terminate(proc)
                    record["outcome"] = "timeout"
                    break
                if build_limit and current["owned_tree_rss_bytes"] > 2 * GIB:
                    record["events"].append({"event": "aggregate-rss-limit", "recorded_at": now()})
                    terminate(proc)
                    record["outcome"] = "resource-stopped"
                    break
                if build_limit and not paused and (current["MemAvailable_bytes"] < 4 * GIB or high_samples >= 3):
                    group_signal(proc.pid, signal.SIGSTOP)
                    paused = True
                    record["events"].append({"event": "pause", "recorded_at": now(), "sample": current})
                elif build_limit and paused and recovered(current):
                    group_signal(proc.pid, signal.SIGCONT)
                    paused, high_samples = False, 0
                    record["events"].append({"event": "resume", "recorded_at": now(), "sample": current})
                elif build_limit and paused:
                    group_signal(proc.pid, signal.SIGSTOP)
                time.sleep(0.5)
            record["exit_code"] = proc.wait(timeout=2)
            record.setdefault("outcome", "pass" if record["exit_code"] == 0 else "fail")
        except BaseException:
            terminate(proc)
            raise
        finally:
            remaining = sample(proc.pid)
            if any(p["state"] != "Z" for p in remaining["owned_processes"]):
                terminate(proc)
            until = time.monotonic() + 2
            remaining = sample(proc.pid)
            while any(p["state"] != "Z" for p in remaining["owned_processes"]) and time.monotonic() < until:
                time.sleep(0.02)
                remaining = sample(proc.pid)
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            record["after"] = remaining
            (out / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
            if any(p["state"] != "Z" for p in remaining["owned_processes"]):
                raise RuntimeError("Owned child session still has a live process after bounded cleanup")
    return record


def inspect(source, out):
    files = ["VERSION", "LICENSE", "COPYING", "COPYING.LIB", "configure", "meson.build",
             "pythondeps.toml", "scripts/meson-buildoptions.sh", "hw/arm/Kconfig",
             "configs/devices/aarch64-softmmu/minimal.mak", "subprojects/dtc.wrap",
             "python/wheels/meson-1.9.0-py3-none-any.whl", "python/wheels/pycotap-1.3.1-py3-none-any.whl"]
    report = {"recorded_at": now(), "source": str(source), "files": {}, "tools": {}, "dependencies": []}
    for file in files:
        path = source / file
        report["files"][file] = digest(path)
    for name in ("cc", "c++", "python3", "meson", "ninja", "pkg-config", "ld", "ar"):
        path = Path(shutil.which(name)).resolve()
        proc = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
        report["tools"][name] = {"path": str(path), "sha256": digest(path), "exit_code": proc.returncode,
                                  "version": proc.stdout.splitlines()[0] if proc.stdout else proc.stderr.splitlines()[0]}
    for names in (("glib-2.0", "gthread-2.0"), ("pixman-1",), ("zlib",)):
        argv = ["pkg-config", "--modversion", *names]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        report["dependencies"].append({"argv": argv, "exit_code": proc.returncode, "output": proc.stdout})
    (out / "provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def build(args):
    pin = json.loads(PIN.read_text())
    if digest(args.archive) != pin["archive_sha256"]:
        raise ValueError("Source archive differs from pinned SHA256")
    if (args.source / "VERSION").read_text().strip() != pin["version"]:
        raise ValueError("Source VERSION differs from pinned release")
    args.out.mkdir(parents=True, exist_ok=False)
    inspect(args.source, args.out)
    profile = ROOT / "fixtures/public/qemu-host/vm002.mak"
    profile_name = "vm002_" + digest(profile)[:12]
    destination = args.source / "configs/devices/aarch64-softmmu" / (profile_name + ".mak")
    if destination.exists() and destination.read_bytes() != profile.read_bytes():
        raise ValueError("Existing vm002 source profile differs from reviewed owned fixture")
    destination.write_bytes(profile.read_bytes())
    (args.out / "profile.json").write_text(json.dumps({"source": str(profile),
        "sha256": digest(profile), "added_source_file": str(destination),
        "base_commit": pin["commit"], "existing_upstream_files_changed": False}, indent=2) + "\n")
    build_dir = args.out / "build"
    build_dir.mkdir()
    configure = [args.source / "configure", "--target-list=aarch64-softmmu",
                 "--with-devices-aarch64=" + profile_name, "--without-default-devices",
                 "--without-default-features", "--disable-download", "--enable-system", "--enable-tcg",
                 "--enable-fdt=internal", "--disable-rust", "--disable-kvm", "--disable-docs",
                 "--disable-tools", "--disable-guest-agent", "--disable-user", "--disable-werror",
                 "--disable-debug-info", "--disable-strip", "--extra-cflags=-O1 -g0", "--disable-lto"]
    record = run(configure, build_dir, args.out, "configure", 180, build_limit=True)
    if record["outcome"] != "pass":
        raise RuntimeError("QEMU configure failed; see configure.log")
    record = run(["ninja", "-j2", "qemu-system-aarch64"], build_dir, args.out,
                 "compile", args.seconds, build_limit=True)
    if record["outcome"] != "pass":
        raise RuntimeError("QEMU build did not pass; see compile.json/log/samples")
    binary = build_dir / "qemu-system-aarch64"
    report = {"outcome": "pass", "recorded_at": now(), "pin": pin,
              "binary": str(binary), "binary_sha256": digest(binary), "binary_size": binary.stat().st_size,
              "guest_os_executed": False, "limitation": "Source build alone does not qualify XNU guest execution."}
    (args.out / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def check(args):
    args.out.mkdir(parents=True, exist_ok=False)
    checks = []
    for name, options, required in (("version", ["--version"], "QEMU emulator version 10.2.0"),
                                     ("machines", ["-machine", "help"], "virt"),
                                     ("accelerators", ["-accel", "help"], "tcg"),
                                     ("cpu", ["-cpu", "help"], "cortex-a76"),
                                     ("options", ["-help"], "-serial")):
        record = run([args.binary, *options], ROOT, args.out, name, 10)
        output = (args.out / (name + ".log")).read_text()
        if record["exit_code"] != 0 or required not in output:
            raise RuntimeError(f"Actual QEMU {name} capability missing")
        checks.append(name)
    # Paused empty machine: validates the real CLI and host stopping, no guest OS.
    argv = [args.binary, "-machine", "virt,gic-version=3", "-accel", "tcg", "-cpu", "cortex-a76",
            "-smp", "1", "-m", "128", "-S", "-nodefaults", "-nic", "none", "-display", "none",
            "-serial", "stdio", "-monitor", "none", "-no-reboot"]
    stopped = run(argv, ROOT, args.out, "stopped-empty-machine", 2)
    if stopped["outcome"] != "timeout" or stopped["elapsed_seconds"] > 7:
        raise RuntimeError("Stopped real QEMU did not survive to the deadline or stop within its bound")
    checks.append("bounded-stopped-empty-machine")
    report = {"outcome": "pass", "recorded_at": now(), "binary": str(args.binary),
              "binary_sha256": digest(args.binary), "checks": checks,
              "guest_os_executed": False, "xnu_executed": False,
              "limitation": "No kernel loaded; these checks qualify only the host tool and stopping interface."}
    (args.out / "check-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def controls(args):
    args.out.mkdir(parents=True, exist_ok=False)
    child = ROOT / "fixtures/public/qemu-host/ignore-term.py"
    record = run([sys.executable, child], ROOT, args.out, "ignore-term-control", 1)
    assert record["outcome"] == "timeout" and record["exit_code"] == -signal.SIGKILL
    assert record["elapsed_seconds"] < 6
    assert not any(p["state"] != "Z" for p in record["after"]["owned_processes"])
    recorded = [json.loads(line) for line in (args.out / "ignore-term-control.samples.jsonl").read_text().splitlines()]
    assert any(len({p["pgrp"] for p in row["owned_processes"]}) >= 2 for row in recorded)
    with (args.out / "pause-control.log").open("xb") as log:
        proc = subprocess.Popen([sys.executable, "-c",
            "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],process_group=0);time.sleep(30)"],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            until = time.monotonic() + 1
            while len({p["pgrp"] for p in sample(proc.pid)["owned_processes"]}) < 2:
                if time.monotonic() > until:
                    raise AssertionError("Owned independent child group did not start")
                time.sleep(0.02)
            group_signal(proc.pid, signal.SIGSTOP)
            stopped = sample(proc.pid)
            until = time.monotonic() + 1
            while (not stopped["owned_processes"] or
                   any(p["state"] != "T" for p in stopped["owned_processes"])):
                if time.monotonic() > until:
                    raise AssertionError("Owned group did not stop")
                time.sleep(0.02)
                stopped = sample(proc.pid)
            group_signal(proc.pid, signal.SIGCONT)
            time.sleep(0.1)
            resumed = sample(proc.pid)
            assert resumed["owned_processes"] and all(p["state"] != "T" for p in resumed["owned_processes"])
        finally:
            terminate(proc)
        after = sample(proc.pid)
        assert not any(p["state"] != "Z" for p in after["owned_processes"])
    report = {"outcome": "pass", "recorded_at": now(), "ignored_sigterm": record,
              "real_owned_group_pause_resume": {"stopped": stopped, "resumed": resumed, "after": after},
              "guest_os_executed": False}
    (args.out / "controls-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": "pass", "report": str(args.out / "controls-report.json")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=2400, choices=range(60, 3601))
    p = sub.add_parser("check")
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("controls")
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for name in ("archive", "source", "out", "binary"):
        if hasattr(args, name):
            setattr(args, name, getattr(args, name).resolve())
    {"build": build, "check": check, "controls": controls}[args.command](args)


if __name__ == "__main__":
    main()
