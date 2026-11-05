#!/usr/bin/env python3
"""Execute a real pinned AVF shim with an explicitly synthetic owned CPU fixture."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/public/avf-handoff"
PIN = json.loads((FIXTURES / "inputs.json").read_text())
GIT_GUARDS = {"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}
CHILD_ENV = dict(os.environ) | GIT_GUARDS
spec = importlib.util.spec_from_file_location("qualified_qemu_supervisor", ROOT / "tools/build/qemu_host.py")
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, out, name, seconds=5, limit_mib=512):
    start = time.monotonic()
    record = {"argv": [str(x) for x in argv], "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "timeout_seconds": seconds, "rss_budget_mib": limit_mib, "outcome": "fail",
              "environment_overrides": GIT_GUARDS}

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if limit_mib == 256:
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))

    with (out / (name + ".log")).open("xb") as log, (out / (name + ".samples.jsonl")).open("x") as samples:
        proc = subprocess.Popen(record["argv"], cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=limits, env=CHILD_ENV)
        record["owned_session"] = proc.pid
        peak = 0
        try:
            while proc.poll() is None:
                snap = supervisor.sample(proc.pid)
                own_rss = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
                snap["supervisor_rss_bytes"] = own_rss
                snap["total_owned_rss_bytes"] = own_rss + snap["owned_tree_rss_bytes"]
                peak = max(peak, snap["total_owned_rss_bytes"])
                samples.write(json.dumps(snap) + "\n"); samples.flush()
                if peak > limit_mib * 1024**2:
                    record["outcome"] = "rss-limit"
                    supervisor.terminate(proc)
                    break
                if time.monotonic() - start >= seconds:
                    record["outcome"] = "timeout"
                    supervisor.terminate(proc)
                    break
                time.sleep(0.05)
            record["exit_code"] = proc.wait(timeout=2)
            if record["outcome"] == "fail" and record["exit_code"] == 0:
                record["outcome"] = "pass"
        finally:
            if any(p["state"] != "Z" for p in supervisor.sample(proc.pid)["owned_processes"]):
                supervisor.terminate(proc)
            until = time.monotonic() + 2
            after = supervisor.sample(proc.pid)
            while any(p["state"] != "Z" for p in after["owned_processes"]) and time.monotonic() < until:
                time.sleep(0.02); after = supervisor.sample(proc.pid)
            record.update(elapsed_seconds=round(time.monotonic() - start, 3),
                          peak_total_owned_rss_bytes=peak, after=after)
            (out / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
            if any(p["state"] != "Z" for p in after["owned_processes"]):
                raise RuntimeError("Live owned fixture child survived cleanup")
    return record


def macho(path):
    data = path.read_bytes()
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from("<8I", data)
    if (magic, cpu, kind) != (0xFEEDFACF, 0x0100000C, 2) or size > len(data) - 32:
        raise ValueError("Owned fixture must be a real arm64 executable Mach-O")
    segments, entry, offset = [], None, 32
    for _ in range(count):
        cmd, length = struct.unpack_from("<II", data, offset)
        if length < 8 or length % 8 or offset + length > 32 + size:
            raise ValueError("Invalid fixture load commands")
        if cmd == 0x19:
            name, va, vm, fileoff, filesize = struct.unpack_from("<16s4Q", data, offset + 8)
            if fileoff + filesize > len(data):
                raise ValueError("Fixture segment file bounds")
            if vm:
                segments.append({"name": name.rstrip(b"\0").decode(), "vmaddr": va,
                                 "vmsize": vm, "fileoff": fileoff, "filesize": filesize})
        if cmd == 5:
            if length != 288 or struct.unpack_from("<II", data, offset + 8) != (6, 68):
                raise ValueError("Expected genuine ARM_THREAD_STATE64")
            entry = struct.unpack_from("<Q", data, offset + 272)[0]
        if cmd in (0xC, 0xE, 0x80000018, 0x8000001F):
            raise ValueError("Synthetic fixture must not load libraries or dyld")
        offset += length
    if offset != 32 + size or not segments or entry is None:
        raise ValueError("Incomplete synthetic Mach-O")
    low = min(s["vmaddr"] for s in segments)
    high = max(s["vmaddr"] + s["vmsize"] for s in segments)
    if low != 0xFFFFFFF007000000 or not low <= entry < high:
        raise ValueError("Synthetic fixture does not meet the pinned shim layout")
    slide = 0x40000000 - 0xFFFFFFF004000000
    dt = (high + slide + 16383) & ~16383
    return {"entry_va": entry, "entry_pa": entry + slide, "dt_pa": dt,
            "bootargs_pa": dt + 65536, "segments": segments, "sha256": digest(path)}


def xnup(destination, kernel, command):
    body = bytearray()
    for name, data in ((b"kernel", kernel), (b"cmdline", command.encode() + b"\0")):
        body += struct.pack("<16sII", name, len(data), 0) + data + b"\0" * (-len(data) % 16)
    body += b"\0" * 24
    destination.write_bytes(struct.pack("<II", 0x50554E58, len(body)) + body)


def fdt(path):
    """Independently decode actual QEMU DTB, with bounds and string checks."""
    data = path.read_bytes()
    header = struct.unpack_from(">10I", data)
    magic, total, start, strings_start, reserve, version, compatible, cpuid, strings_size, structure_size = header
    if magic != 0xD00DFEED or total != len(data) or start + structure_size > total or strings_start + strings_size > total:
        raise ValueError("Malformed actual QEMU DTB")
    strings = data[strings_start:strings_start + strings_size]
    offset, stack, props = start, [], {}
    while offset < start + structure_size:
        token = struct.unpack_from(">I", data, offset)[0]; offset += 4
        if token == 1:
            end = data.index(0, offset, start + structure_size)
            stack.append(data[offset:end].decode()); offset = (end + 4) & ~3
        elif token == 2:
            if not stack: raise ValueError("DTB stack underflow")
            stack.pop()
        elif token == 3:
            length, name_offset = struct.unpack_from(">II", data, offset); offset += 8
            if offset + length > start + structure_size or name_offset >= len(strings):
                raise ValueError("DTB property out of bounds")
            name_end = strings.index(0, name_offset)
            name = strings[name_offset:name_end].decode()
            props[("/" + "/".join(stack[1:]), name)] = data[offset:offset + length]
            offset += (length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            break
        else:
            raise ValueError("Unknown DTB token")
    memory = next(value for (node, name), value in props.items() if node.startswith("/memory@") and name == "reg")
    ram_base, ram_size = struct.unpack(">QQ", memory)
    uart = props[("/pl011@9000000", "reg")]
    gic = props[("/intc@8000000", "reg")]
    psci = props[("/psci", "method")]
    assert (ram_base, ram_size) == (0x40000000, 0x10000000)
    assert struct.unpack(">QQ", uart)[0] == 0x09000000 and psci == b"hvc\0"
    assert struct.unpack(">4Q", gic)[::2] == (0x08000000, 0x080A0000)
    return {"sha256": digest(path), "ram_base": ram_base, "ram_size": ram_size,
            "psci_method": "hvc", "uart_reg_hex": uart.hex(), "gic_reg_hex": gic.hex(),
            "initrd_start": int.from_bytes(props[("/chosen", "linux,initrd-start")], "big"),
            "initrd_end": int.from_bytes(props[("/chosen", "linux,initrd-end")], "big")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("out", "qemu", "shim", "scion", "qemu-source", "clang", "ld",
                 "shim-build-report", "qemu-build-report", "qemu-source-manifest"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name in vars(args): setattr(args, name, getattr(args, name).resolve())
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"task": "VM-005", "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "kind": "host-test", "origin": "local-host", "outcome": "fail", "owned_synthetic": True,
              "xnu_executed": False, "pid1_executed": False, "ios_executed": False, "cases": [],
              "argv": [sys.executable, *sys.argv], "environment_overrides": GIT_GUARDS, "source_reads": []}
    try:
        revision = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True,
                                  timeout=10, env=CHILD_ENV, check=True)
        report["commit"] = revision.stdout.strip()
        if digest(args.qemu) != PIN["qemu_sha256"] or digest(args.shim) != PIN["shim_sha256"]:
            raise ValueError("Qualified QEMU or genuine shim hash mismatch")
        shim_build = json.loads(args.shim_build_report.read_text())
        qemu_build = json.loads(args.qemu_build_report.read_text())
        qemu_manifest = json.loads(args.qemu_source_manifest.read_text())
        if shim_build["donor_commit"] != PIN["scion_commit"] or not any(
                entry["sha256"] == PIN["shim_sha256"] for entry in shim_build["artifacts"]):
            raise ValueError("Pinned image is not bound to the genuine shim build report")
        if qemu_build["pin"]["commit"] != PIN["qemu_commit"] or qemu_build["binary_sha256"] != PIN["qemu_sha256"]:
            raise ValueError("Qualified binary is not bound to the genuine QEMU build report")
        built_shim_sources = {entry["path"]: entry["sha256"] for entry in shim_build["sources"]}
        source_hashes = {}
        for file in (*built_shim_sources, "xnuloader/mkpayload.py"):
            argv = ["git", "-C", str(args.scion), "show", PIN["scion_commit"] + ":" + file]
            proc = subprocess.run(argv, capture_output=True, timeout=10, env=CHILD_ENV)
            report["source_reads"].append({"argv": argv, "exit_code": proc.returncode,
                "environment_overrides": GIT_GUARDS, "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
                "stderr": proc.stderr.decode(errors="replace")})
            if proc.returncode: raise ValueError("Pinned AVF source unavailable without lazy fetch: " + file)
            source_hashes[file] = hashlib.sha256(proc.stdout).hexdigest()
            if file in built_shim_sources and built_shim_sources[file] != source_hashes[file]:
                raise ValueError("Actual shim build source differs from pinned donor: " + file)
        for file in ("hw/arm/virt.c", "hw/arm/boot.c", "target/arm/tcg/psci.c"):
            source_hashes["qemu/" + file] = digest(args.qemu_source / file)
            if source_hashes["qemu/" + file] != qemu_manifest[file]["sha256"]:
                raise ValueError("QEMU board/boot/PSCI source differs from qualified source manifest")
        report["inputs"] = {"pin": PIN, "qemu": str(args.qemu), "shim": str(args.shim),
                            "source_sha256": source_hashes, "clang_sha256": digest(args.clang),
                            "ld_sha256": digest(args.ld), "supervisor_sha256": digest(ROOT / "tools/build/qemu_host.py"),
                            "fixture_source_sha256": digest(FIXTURES / "synthetic.c"),
                            "build_reports_and_source_manifest": {
                                str(p): digest(p) for p in (args.shim_build_report, args.qemu_build_report, args.qemu_source_manifest)},
                            "compiled_shim_source_bindings_verified": 5,
                            "shim_source_header_linker_license_bindings_verified": len(built_shim_sources),
                            "qemu_board_boot_psci_source_bindings_verified": 3}
        for name, options in (("clang-version", [args.clang, "--version"]), ("ld-version", [args.ld, "-v"])):
            if run(options, args.out, name, limit_mib=256)["exit_code"]: raise RuntimeError(name)
        images = {}
        for mode in ("normal", "spin"):
            obj, image = args.out / (mode + ".o"), args.out / (mode + ".macho")
            flags = ["--target=arm64-apple-macos12", "-O1", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie",
                     "-nostdlib", "-fno-stack-protector", "-fno-jump-tables", "-mstrict-align", "-mgeneral-regs-only", "-Wall", "-Wextra", "-Werror"]
            if mode == "spin": flags.append("-DVM005_SPIN=1")
            r = run([args.clang, *flags, "-c", FIXTURES / "synthetic.c", "-o", obj], args.out, mode + "-compile", limit_mib=256)
            if r["exit_code"]: raise RuntimeError(mode + " compile failed")
            r = run([args.ld, "-arch", "arm64", "-static", "-e", "_synthetic_entry", "-macosx_version_min", "12.0",
                     "-pagezero_size", "0", "-seg1addr", "0xfffffff007000000", "-no_uuid", obj, "-o", image],
                    args.out, mode + "-link", limit_mib=256)
            if r["exit_code"]: raise RuntimeError(mode + " link failed")
            images[mode] = macho(image)
        report["synthetic_macho"] = images
        base_args = [args.qemu, "-machine", "virt,gic-version=3", "-accel", "tcg", "-cpu", "cortex-a76",
                     "-smp", "1", "-m", "256", "-kernel", args.shim, "-nodefaults", "-nic", "none",
                     "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot"]
        for name, mode, cookie in (("positive", "normal", PIN["command_cookie"]),
                                   ("wrong-cookie", "normal", "vm005_cookie=wrong-synthetic"),
                                   ("bad-magic", "normal", PIN["command_cookie"]),
                                   ("spin-timeout", "spin", PIN["command_cookie"])):
            payload = args.out / (name + ".xnup")
            kernel = bytearray((args.out / (mode + ".macho")).read_bytes())
            if name == "bad-magic": kernel[0] ^= 1
            xnup(payload, kernel, "cpus=1 console_quiet=0 " + cookie)
            command = [*base_args, "-initrd", payload]
            if name == "positive":
                dtb = args.out / "qemu.dtb"
                dump_command = list(command); dump_command[2] += ",dumpdtb=" + str(dtb)
                if run(dump_command, args.out, "dtb-dump")["exit_code"]: raise RuntimeError("QEMU DTB dump failed")
                report["actual_qemu_dtb"] = fdt(dtb)
            r = run(command, args.out, name, seconds=3 if mode == "spin" else 5)
            console = (args.out / (name + ".log")).read_text(errors="replace")
            entered = "VM005 SYNTHETIC ENTER" in console
            passed = "VM005 SYNTHETIC PASS" in console
            if name == "positive":
                marker = re.search(r"VM005 SYNTHETIC PASS entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+) dt=(0x[0-9a-f]+) mem=(0x[0-9a-f]+) psci=(0x[0-9a-f]+)", console)
                expected = images[mode]
                ok = bool(marker) and (int(marker[1], 16), int(marker[2], 16), int(marker[3], 16), int(marker[4], 16)) == (
                    expected["entry_pa"], expected["bootargs_pa"], expected["dt_pa"], 0x0E000000)
                ok = ok and entered and r["outcome"] == "pass" and "VM005 SYNTHETIC PSCI_SYSTEM_OFF" in console
            elif name == "wrong-cookie":
                ok = entered and not passed and "VM005 SYNTHETIC REJECT command-cookie" in console and r["outcome"] == "pass"
            elif name == "bad-magic":
                ok = not entered and not passed and "avfboot: FATAL: the kernel entry is not a 64-bit Mach-O" in console and r["outcome"] == "pass"
            else:
                ok = entered and not passed and "VM005 SYNTHETIC SPIN-CONTROL" in console and r["outcome"] == "timeout"
            report["cases"].append({"name": name, "outcome": "pass" if ok else "fail", "run": r,
                                    "payload_sha256": digest(payload), "console_sha256": digest(args.out / (name + ".log"))})
            if not ok: raise RuntimeError("Real shim/fixture case failed: " + name)
        if digest(args.qemu) != PIN["qemu_sha256"] or digest(args.shim) != PIN["shim_sha256"]:
            raise ValueError("Read-only input changed during fixture checks")
        report["outcome"] = "pass"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, AssertionError) as error:
        report["error"] = str(error)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("outcome", "owned_synthetic", "xnu_executed")} |
                     {"cases": [{"name": c["name"], "outcome": c["outcome"],
                                 "elapsed_seconds": c["run"]["elapsed_seconds"]} for c in report["cases"]],
                      "error": report.get("error"), "report": str(args.out / "report.json")}, indent=2))
    return 0 if report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
