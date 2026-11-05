#!/usr/bin/env python3
"""Plan or execute one explicitly leased, finite read-only virtual RAM capture."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OWNER = "codex-guest-exec-20261106-di"
RAM_LO, RAM_HI = 0x40000000, 0x50000000
MAX_DUMP = 1024 * 1024
RSS_LIMIT = 512 * 1024 * 1024
DEADLINE = 55  # Includes admission; finite owned cleanup leaves the whole under60s.


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def owned_output(path):
    path = Path(path)
    canonical = path.resolve()
    base = (ROOT / "artifacts/avf-guest-device-tree").resolve()
    if path.absolute() != canonical or not canonical.is_relative_to(base) or canonical == base:
        raise ValueError("Output must be canonical and below this worktree's owned artifact directory")
    return canonical


def bounds(address, length):
    if not RAM_LO <= address < RAM_HI or not 0 < length <= MAX_DUMP or length > RAM_HI - address:
        raise ValueError("Dynamic Apple DT extent is outside admitted virtual RAM/dump limits")
    return address, length


def check_lease(queue, lease_id):
    grant = json.loads(Path(queue).read_text()).get("qemu")
    if not isinstance(grant, dict) or grant.get("id") != lease_id or grant.get("owner") != OWNER or grant.get("task") != "VM-027":
        raise ValueError("No matching explicit root single-QEMU lease")


def console_extent(data):
    matches = re.findall(rb"avfboot: device tree (0x[0-9a-f]+)\+(0x[0-9a-f]+) boot_args (0x[0-9a-f]+)", data)
    if len(matches) != 1:
        raise ValueError("Expected exactly one real shim Apple device-tree console extent")
    address, length, ba = (int(value, 16) for value in matches[0])
    bounds(address, length)
    bounds(ba, 1)
    # It must be the emitted tree; the separate FDT input message is never parsed.
    return {"address": address, "length": length, "boot_args_address": ba}


def make_plan(main, out):
    main, out = Path(main).resolve(), owned_output(out)
    if out.exists():
        raise ValueError("Capture output must be fresh")
    paths = {
        "qemu": "worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build/qemu-system-aarch64",
        "shim": "worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/Image",
        "payload": "worktrees/vm-005-20261105/artifacts/avf-handoff/run-final-221923b/spin-timeout.xnup",
        "macho": "worktrees/vm-005-20261105/artifacts/avf-handoff/run-final-221923b/spin.macho",
        "historical_artifact_index": "worktrees/vm-005-20261105/artifacts/avf-handoff/artifact-sha256.json",
        "historical_guest_record": "worktrees/vm-005-20261105/artifacts/avf-handoff/run-final-221923b/spin-timeout.json",
        "shim_build_record": "worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/report.json",
        "qemu_build_record": "worktrees/vm-004-20261105/artifacts/qemu-host/build-6/build-report.json",
    }
    expected = {"qemu": "bca8564182c786eb00e9f43c3153328f68e2edf50bfabe28236dbaac438acc11",
                "shim": "283f6740424011959ebe03e71ce910a81bbfa3b7ba31c6395ab6f8aab77eaf87",
                "payload": "f9028141a8fd1bb95edf47017937a621912bdd089733d0ed1379a04b15db0c04",
                "macho": "a4e93770fb95342c49dc6ac2b2975f0501e7f970ae5e8e3f1315036dc7a6899a"}
    pins = {name: {"path": str(main / rel), "sha256": digest(main / rel),
                   "size": (main / rel).stat().st_size} for name, rel in paths.items()}
    for name, value in expected.items():
        if pins[name]["sha256"] != value:
            raise ValueError("Qualified input changed: " + name)
    index = json.loads((main / paths["historical_artifact_index"]).read_text())
    for name in ("payload", "macho"):
        if index[paths[name]] != expected[name]:
            raise ValueError("Historical artifact index disagrees: " + name)
    argv = [pins["qemu"]["path"], "-machine", "virt,gic-version=3", "-accel", "tcg",
            "-cpu", "cortex-a76", "-smp", "1", "-m", "256", "-kernel", pins["shim"]["path"],
            "-nodefaults", "-nic", "none", "-display", "none", "-serial", "stdio",
            "-monitor", "none", "-no-reboot", "-initrd", pins["payload"]["path"],
            "-qmp", "unix:qmp.sock,server=on,wait=off"]
    return {"schema_version": 1, "task": "VM-027", "owner": OWNER, "main": str(main),
            "output": str(out), "pins": pins, "argv": argv, "cwd": str(out),
            "capture_script_sha256": digest(__file__),
            "accepted_supervisor": {"path": str(ROOT / "tools/build/qemu_host.py"),
                                    "sha256": digest(ROOT / "tools/build/qemu_host.py")},
            "parser_sha256": digest(ROOT / "tools/build/avf_guest_device_tree.py"),
            "qmp_sequence": ["greeting", "qmp_capabilities", "wait for real shim DT extent and VM005 SYNTHETIC SPIN-CONTROL",
                             "stop", "query-status: running=false,status=paused", "pmemsave: dynamic address,length to canonical apple-tree.adt", "quit"],
            "bounds": {"guest_ram_low": RAM_LO, "guest_ram_high_exclusive": RAM_HI,
                       "maximum_dump_bytes": MAX_DUMP, "guest_ram_mib": 256,
                       "owned_rss_limit_bytes": RSS_LIMIT, "minimum_MemAvailable_bytes": 4 * 1024**3,
                       "admission_samples": 3, "sample_interval_seconds": 1,
                       "capture_deadline_seconds": DEADLINE, "whole_limit_seconds": 60},
            "environment": {"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C",
                            "PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1"},
            "scope": "One unchanged source-built shim to existing owned synthetic spin payload; virtual RAM read only; no kernel or PID1 claim"}


class QMP:
    def __init__(self, sock, guard, transcript):
        self.sock, self.guard, self.transcript = sock, guard, transcript
        self.buffer, self.sequence = b"", 0
        self.sock.settimeout(0.05)

    def receive(self):
        while b"\n" not in self.buffer:
            self.guard()
            try:
                value = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not value:
                raise ValueError("QMP closed before its reply")
            self.buffer += value
            if len(self.buffer) > MAX_DUMP:
                raise ValueError("QMP reply exceeds finite bound")
        line, self.buffer = self.buffer.split(b"\n", 1)
        message = json.loads(line)
        self.transcript.append({"received": message})
        return message

    def command(self, command, arguments=None):
        self.sequence += 1
        request = {"execute": command, "id": self.sequence}
        if arguments is not None:
            request["arguments"] = arguments
        self.transcript.append({"sent": request})
        self.sock.sendall(json.dumps(request).encode() + b"\n")
        while True:
            reply = self.receive()
            if reply.get("id") == self.sequence:
                if "error" in reply or "return" not in reply:
                    raise ValueError("QMP rejected request: " + str(reply))
                return reply["return"]


def execute(plan, lease_id):
    # Revalidate all pins and exact command/output construction immediately before admission.
    if plan != make_plan(plan["main"], plan["output"]):
        raise ValueError("Plan no longer matches exact source/tool/input/output bindings")
    queue = Path(plan["main"]) / "artifacts/team-coordination/20261106-team/resource-queue.json"

    def lease():
        check_lease(queue, lease_id)

    lease()
    out = owned_output(plan["output"])
    out.mkdir(parents=True, exist_ok=False)
    record = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "started_at": datetime.now(timezone.utc).isoformat(), "plan": plan, "lease_id": lease_id,
              "admission": [], "qmp": [], "compiler_executed": False, "xnu_executed": False,
              "pid1_executed": False, "phone_operations": False}
    supervisor_spec = importlib.util.spec_from_file_location("accepted_qemu_supervisor", plan["accepted_supervisor"]["path"])
    supervisor = importlib.util.module_from_spec(supervisor_spec)
    supervisor_spec.loader.exec_module(supervisor)
    start = time.monotonic()
    process, connection = None, None
    peak = 0
    old_cwd = Path.cwd()
    with (out / "samples.jsonl").open("x") as samples, (out / "console.log").open("xb") as console:
        def guard():
            nonlocal peak
            if time.monotonic() - start > DEADLINE:
                raise TimeoutError("Whole capture deadline exceeded")
            lease()
            snapshot = supervisor.sample(process.pid if process else None)
            own_rss = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
            snapshot["controller_rss_bytes"] = own_rss
            snapshot["total_owned_rss_bytes"] = own_rss + snapshot["owned_tree_rss_bytes"]
            peak = max(peak, snapshot["total_owned_rss_bytes"])
            samples.write(json.dumps(snapshot) + "\n"); samples.flush()
            if peak > RSS_LIMIT:
                raise MemoryError("Owned aggregate RSS exceeds512MiB")
            return snapshot

        try:
            for _ in range(3):
                snapshot = guard()
                record["admission"].append(snapshot)
                if snapshot["MemAvailable_bytes"] < 4 * 1024**3:
                    raise MemoryError("Admission below4GiB MemAvailable")
                time.sleep(1)
            lease()
            os.chdir(out)  # Relative Unix socket avoids sockaddr_un length overflow.
            process = subprocess.Popen(plan["argv"], cwd=out, stdin=subprocess.DEVNULL,
                                       stdout=console, stderr=subprocess.STDOUT, start_new_session=True,
                                       env=dict(os.environ) | plan["environment"],
                                       preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            record["owned_session"] = process.pid
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            while True:
                guard()
                try:
                    connection.connect("qmp.sock")
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if process.poll() is not None:
                        raise ValueError("QEMU exited before QMP connection")
                    time.sleep(0.05)
            qmp = QMP(connection, guard, record["qmp"])
            if "QMP" not in qmp.receive():
                raise ValueError("Missing QMP greeting")
            qmp.command("qmp_capabilities")
            while True:
                guard()
                with (out / "console.log").open("rb") as stream:
                    data = stream.read(MAX_DUMP + 1)
                if len(data) > MAX_DUMP:
                    raise ValueError("Console exceeds finite bound")
                if b"VM005 SYNTHETIC SPIN-CONTROL" in data:
                    extent = console_extent(data)
                    break
                if process.poll() is not None:
                    raise ValueError("Existing spin payload did not reach its marker")
                time.sleep(0.05)
            record["dynamic_extent"] = extent
            qmp.command("stop")
            status = qmp.command("query-status")
            if status.get("running") is not False or status.get("status") != "paused":
                raise ValueError("QMP did not confirm a paused guest")
            destination = owned_output(out / "apple-tree.adt")
            if destination.exists():
                raise ValueError("Refuse to overwrite existing capture")
            qmp.command("pmemsave", {"val": extent["address"], "size": extent["length"], "filename": str(destination)})
            if destination.is_symlink() or not destination.is_file() or destination.stat().st_size != extent["length"]:
                raise ValueError("Captured size differs from real shim console length")
            qmp.command("quit")
            while process.poll() is None:
                guard(); time.sleep(0.05)
            record["exit_code"] = process.wait(timeout=1)
            if record["exit_code"] != 0:
                raise ValueError("QEMU quit returned nonzero")
            record.update(outcome="pass", capture_sha256=digest(destination), capture_size=destination.stat().st_size)
        except Exception as error:
            record["error"] = repr(error)
        finally:
            if connection is not None:
                connection.close()
            if process is not None:
                if any(p["state"] != "Z" for p in supervisor.sample(process.pid)["owned_processes"]):
                    supervisor.terminate(process)
                record["exit_code"] = process.wait(timeout=2)
                record["after"] = supervisor.sample(process.pid)
                if any(p["state"] != "Z" for p in record["after"]["owned_processes"]):
                    record["outcome"] = "fail"
                    record["cleanup_error"] = "Owned process survived accepted cleanup"
            os.chdir(old_cwd)
            record.update(elapsed_seconds=time.monotonic() - start, peak_total_owned_rss_bytes=peak,
                          console_sha256=digest(out / "console.log"))
            with open("/proc/self/status", encoding="ascii") as stream:
                record["controller_current_image_VmHWM_bytes"] = next(int(line.split()[1]) * 1024 for line in stream if line.startswith("VmHWM:"))
            (out / "report.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({key: record.get(key) for key in ("outcome", "error", "elapsed_seconds", "peak_total_owned_rss_bytes", "dynamic_extent")}))
    return 0 if record["outcome"] == "pass" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--lease-id")
    args = parser.parse_args()
    if args.execute:
        if not args.lease_id:
            parser.error("--execute requires --lease-id")
        return execute(json.loads(args.plan.read_text()), args.lease_id)
    if not args.main or not args.out:
        parser.error("planning requires --main and --out")
    plan = make_plan(args.main, args.out)
    with args.plan.open("x") as stream:
        stream.write(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"plan": str(args.plan), "sha256": digest(args.plan), "guest_executed": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
