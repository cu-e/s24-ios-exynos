#!/usr/bin/env python3
"""Read-only selected AVF PID1 admission; never compile, execute or launch a guest."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import struct
import sys
import time


LIMIT = 1024 * 1024


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def bounded_bytes(path):
    require(path.is_file() and path.stat().st_size <= LIMIT, "Input exceeds 1MiB limit or is not a file")
    with path.open("rb") as source:
        data = source.read(LIMIT + 1)
    require(len(data) <= LIMIT, "Input grew beyond 1MiB limit")
    return data


def macho(data):
    """Deliberately narrow static arm64 LC_UNIXTHREAD contract, not XNU emulation."""
    require(len(data) >= 32, "Truncated Mach-O header")
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from("<8I", data)
    require((magic, cpu, subtype, kind, reserved) == (0xFEEDFACF, 0x100000C, 0, 2, 0),
            "Expected thin little-endian arm64-all MH_EXECUTE")
    require(flags == 1, "Expected original static MH_NOUNDEFS contract; no DYLDLINK/PIE")
    require(0 < count <= 64 and size <= len(data) - 32, "Unbounded Mach-O commands")
    offset, end = 32, 32 + size
    segments, sections, threads = [], [], []
    allowed = {0x19, 2, 0xB, 0x1B, 0x24, 0x25, 0x2A, 0x32, 5}
    for _ in range(count):
        require(offset + 8 <= end, "Truncated load command")
        command, length = struct.unpack_from("<II", data, offset)
        require(length >= 8 and length % 8 == 0 and length <= end - offset, "Invalid command extent")
        require(command in allowed, "Unsupported or dynamic load command")
        if command == 0x19:
            require(length >= 72, "Truncated segment")
            name = data[offset + 8:offset + 24].rstrip(b"\0").decode("ascii")
            va, vm, fileoff, filesz, maximum, initial, nsects, segflags = struct.unpack_from("<4Q4I", data, offset + 24)
            require(length == 72 + nsects * 80, "Segment section count mismatch")
            require(vm > 0 and va + vm < 2**64 and fileoff + filesz <= len(data) and filesz <= vm,
                    "Segment extent outside input or address space")
            require(va % 16384 == 0 and vm % 16384 == 0 and fileoff % 16384 == 0,
                    "Segment violates selected 16KiB mapping contract")
            require(maximum & ~7 == 0 and initial & ~maximum == 0 and initial & 6 != 6,
                    "Invalid segment permissions or writable executable segment")
            segment = dict(name=name, va=va, vmsize=vm, fileoff=fileoff, filesize=filesz,
                           maxprot=maximum, initprot=initial, command_offset=offset)
            segments.append(segment)
            for index in range(nsects):
                start = offset + 72 + index * 80
                address, section_size, section_file = struct.unpack_from("<QQI", data, start + 32)
                section_flags = struct.unpack_from("<I", data, start + 64)[0]
                require(va <= address and address + section_size <= va + vm, "Section outside VM segment")
                if section_flags & 0xFF not in {1, 0xC, 0x12}:  # zero-fill variants
                    require(fileoff <= section_file and section_file + section_size <= fileoff + filesz,
                            "Section outside file-backed segment")
                sections.append(dict(name=data[start:start + 16].rstrip(b"\0").decode("ascii"),
                                     address=address, size=section_size, offset=section_file))
        elif command == 5:
            require(length == 288, "Expected one complete ARM_THREAD_STATE64 command")
            flavor, words = struct.unpack_from("<II", data, offset + 8)
            require((flavor, words) == (6, 68), "Wrong ARM64 thread state flavor/count")
            registers = struct.unpack_from("<33QII", data, offset + 16)
            require(all(value == 0 for index, value in enumerate(registers) if index != 32),
                    "Expected kernel-created default stack and zero initial registers/CPSR")
            threads.append(dict(pc=registers[32], sp=registers[31], command_offset=offset))
        offset += length
    require(offset == end and len(threads) == 1, "Load command table or entry count mismatch")
    require(len({item["name"] for item in segments}) == len(segments), "Duplicate segment name")
    for left, right in zip(sorted(segments, key=lambda row: row["va"]),
                           sorted(segments, key=lambda row: row["va"])[1:]):
        require(left["va"] + left["vmsize"] <= right["va"], "Overlapping VM segments")
    pagezero = [row for row in segments if row["name"] == "__PAGEZERO"]
    require(len(pagezero) == 1 and all(pagezero[0][key] == value for key, value in
            {"va": 0, "vmsize": 0x100000000, "filesize": 0, "initprot": 0, "maxprot": 0}.items()),
            "Missing hard 4GiB pagezero")
    pc = threads[0]["pc"]
    executable = [row for row in segments if row["initprot"] & 4 and
                  row["va"] <= pc < row["va"] + row["filesize"]]
    require(pc % 4 == 0 and len(executable) == 1, "Entry is not aligned file-backed executable memory")
    require(any(row["name"] == "__text" and row["address"] <= pc < row["address"] + row["size"]
                for row in sections), "Entry outside __text")
    return dict(entry=pc, stack="kernel default (LC_UNIXTHREAD SP=0)",
                segments=segments, sections=sections, thread=threads[0], flags=flags)


def path_under(root, relative):
    require(isinstance(relative, str) and not Path(relative).is_absolute(), "Expected relative input path")
    resolved = (root / relative).resolve()
    require(resolved.is_relative_to(root), "Input escapes MAIN")
    return resolved


def verify_inputs(main, fixture):
    records = []
    for row in fixture["inputs"]:
        path = path_under(main, row["path"])
        actual = sha(path)
        require(actual == row["sha256"], "Pinned input changed: " + row["path"])
        records.append(dict(path=row["path"], sha256=actual, size=path.stat().st_size, role=row["role"]))
    compiler = fixture["historical_compiler"]
    compiler_path = Path(compiler["path"])
    require(sha(compiler_path) == compiler["sha256"], "Historical compiler bytes changed")
    records.append(dict(path=str(compiler_path), sha256=compiler["sha256"],
                        size=compiler_path.stat().st_size, role=compiler["origin"]))
    prepared_row = next(row for row in fixture["inputs"] if row["path"].endswith("/prepared-component.json"))
    prepared = json.loads(bounded_bytes(path_under(main, prepared_row["path"])))
    for row in fixture["inputs"]:
        prefix = "worktrees/vm-008-20261105/artifacts/avf-kernel-headers/prepare-2/source/xnu/"
        if row["path"].startswith(prefix):
            require(prepared["prepared_source_files"][row["path"][len(prefix):]] == row["sha256"],
                    "Source is not bound by frozen prepared component")
    return records


def candidate_review(main, fixture, candidate, descriptor_path):
    """Bind reviewed compiled evidence; this never qualifies kernel execution."""
    endorsement = next((row for row in fixture.get("candidate_reviews", [])
                        if row["candidate"] == candidate), None)
    require(endorsement is not None, "Candidate has no exact compiled-review endorsement")
    require(descriptor_path is not None and sha(descriptor_path) ==
            endorsement["candidate_descriptor"]["sha256"], "Reviewed candidate descriptor bytes changed")
    pinned = {row["path"]: row["sha256"] for row in fixture["inputs"]}
    for key in ("candidate_descriptor", "compiled_admission", "review_evidence", "raw_build_evidence"):
        binding = endorsement[key]
        require(pinned.get(binding["path"]) == binding["sha256"], "Unpinned review binding: " + key)
    admission = json.loads(bounded_bytes(path_under(main, endorsement["compiled_admission"]["path"])))
    review = json.loads(bounded_bytes(path_under(main, endorsement["review_evidence"]["path"])))
    build = json.loads(bounded_bytes(path_under(main, endorsement["raw_build_evidence"]["path"])))
    require(admission["outcome"] == "pass" and admission["compiled_ABI_review_pass"] is True and
            admission["candidate"] == candidate and admission["candidate_descriptor"] ==
            endorsement["candidate_descriptor"], "Compiled admission does not bind the exact candidate")
    require(review["outcome"] == "pass" and review["task"] == "REV-026" and
            review["compiled_admission"] == endorsement["compiled_admission"] and
            review["reviewed_candidate"] == endorsement["candidate_descriptor"], "Independent review chain changed")
    require(build["outcome"] == "pass" and build["candidate"] == candidate and
            admission["raw_build_evidence"] == endorsement["raw_build_evidence"], "Raw build chain changed")
    baseline = fixture["historical_vm025"]
    require(build["bindings"]["VM025_fixture"] == baseline["fixture"], "Historical fixture binding changed")
    tool = build["tools"]["preflight"]
    require(Path(tool["path"]).resolve() == path_under(main, baseline["implementation"]["path"]) and
            tool["sha256"] == baseline["implementation"]["sha256"], "Historical tool binding changed")
    for key in ("fixture", "implementation", "inconclusive_evidence"):
        binding = baseline[key]
        require(pinned.get(binding["path"]) == binding["sha256"], "Unpinned historical baseline: " + key)
    original = json.loads(bounded_bytes(path_under(main, baseline["fixture"]["path"])))
    require(fixture["inputs"][:len(original["inputs"])] == original["inputs"] and
            fixture["legacy"] == original["legacy"] and original["qualified_candidates"] == [],
            "Historical nineteen-input baseline was not retained")
    for path, digest in review["sha256"].items():
        require(pinned.get(path) == digest, "Independent reviewed input not pinned: " + path)
    return dict(**endorsement, historical_vm025=baseline)


def controls(data):
    parsed = macho(data)
    text = next(row for row in parsed["segments"] if row["name"] == "__TEXT")
    thread = parsed["thread"]["command_offset"]
    variants = {"truncated-header": data[:31], "truncated-file-backed-segment": data[:-512]}
    mutations = [("wrong-cpu", 4, "I", 0x1000007), ("kernel-not-pid1", 12, "I", 0xC),
                 ("dynamic-flags", 24, "I", 5), ("unbounded-command-count", 16, "I", 0xFFFFFFFF),
                 ("zero-command-size", 36, "I", 0), ("wrong-thread-flavor", thread + 8, "I", 1),
                 ("wrong-thread-count", thread + 12, "I", 67),
                 ("nonzero-custom-stack", thread + 16 + 31 * 8, "Q", 0x100000000),
                 ("unaligned-entry", thread + 16 + 32 * 8, "Q", parsed["entry"] + 1),
                 ("entry-in-pagezero", thread + 16 + 32 * 8, "Q", 4),
                 ("entry-in-linkedit", thread + 16 + 32 * 8, "Q", 0x100004000),
                 ("write-execute", text["command_offset"] + 60, "I", 7),
                 ("segment-file-overrun", text["command_offset"] + 48, "Q", 2**63),
                 ("vm-overlap", text["command_offset"] + 24, "Q", 0),
                 ("dynamic-load-command", thread, "I", 0x80000028)]
    for name, offset, fmt, value in mutations:
        changed = bytearray(data)
        struct.pack_into("<" + fmt, changed, offset, value)
        variants[name] = changed
    results = []
    for name, changed in variants.items():
        try:
            macho(changed)
        except (ValueError, UnicodeError, struct.error) as error:
            results.append(dict(case=name, outcome="rejected", reason=str(error),
                                sha256=hashlib.sha256(changed).hexdigest()))
        else:
            raise ValueError("Corrupt input was accepted: " + name)
    return results


def hwm():
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, amount, unit = line.split()
            fields[key.rstrip(":") + "_bytes"] = int(amount) * 1024
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=Path(__file__).resolve().parents[2] /
                        "fixtures/public/avf-guest-pid1/inputs.json")
    parser.add_argument("--candidate", type=Path, help="Explicit reviewed candidate path/hash descriptor")
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    report = dict(schema_version=1, task="VM-025", evidence_kind="host-test",
                  started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  argv=sys.argv, guest_executed=False, compiler_executed=False,
                  pid1_observed=False, native_device_qualified=False,
                  runtime_syscalls_qualified=False, stack_signing_console_qualified=False,
                  qualification_scope="Compiled source/IR/ARM64/static Mach-O admission only")
    args.out.mkdir(parents=True, exist_ok=False)
    code = 1
    try:
        fixture = json.loads(bounded_bytes(args.fixture))
        report["fixture_sha256"] = sha(args.fixture)
        report["inputs"] = verify_inputs(args.main.resolve(), fixture)
        candidate = fixture["legacy"] if args.candidate is None else json.loads(bounded_bytes(args.candidate))
        candidate_path = path_under(args.main.resolve(), candidate["path"])
        data = bounded_bytes(candidate_path)
        require(hashlib.sha256(data).hexdigest() == candidate["sha256"], "Explicit PID1 hash mismatch")
        source_path = path_under(args.main.resolve(), candidate["source_path"])
        require(sha(source_path) == candidate["source_sha256"], "Explicit PID1 source hash mismatch")
        report["candidate"] = candidate
        report["macho"] = macho(data)
        if args.controls:
            report["controls"] = controls(data)
        legacy = candidate["sha256"] == fixture["legacy"]["sha256"]
        approved = not legacy and any(candidate == row for row in fixture["qualified_candidates"])
        if approved:
            report["compiled_review"] = candidate_review(args.main.resolve(), fixture, candidate, args.candidate)
        report["compiled_abi_admitted"] = approved
        report["abi_admission"] = "rejected" if legacy else "compiled-only" if approved else "unqualified"
        report["reason"] = fixture["legacy_rejection"] if legacy else (
            "Exact independently reviewed candidate descriptor matched" if approved else
            "Candidate is structurally eligible but lacks an exact independently reviewed fixture entry")
        report["outcome"] = "pass" if approved else "inconclusive"
        report["runtime_prerequisites"] = fixture["runtime_prerequisites"]
        code = 0 if approved else 2
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, struct.error) as error:
        report.update(outcome="fail", error=str(error))
    report.update(elapsed_seconds=round(time.monotonic() - started, 6), exit_code=code,
                  memory=hwm(), implementation_sha256=sha(Path(__file__)))
    if report["memory"].get("VmHWM_bytes", LIMIT) > 256 * 1024 * 1024:
        report.update(outcome="fail", error="Controller current-image VmHWM exceeded 256MiB", exit_code=1)
        code = 1
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report.get(key) for key in ("outcome", "abi_admission", "reason", "error", "exit_code", "memory")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
