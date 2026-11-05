#!/usr/bin/env python3
"""Measure real XNU allocator compiler APIs without constant builtin replacements."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from xnu_macho_tools import macho
import sources


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_reuse_witness(build, destination):
    paths = list((build / "lib").glob("*.a")) + [build / "build.ninja"]
    for base in [build / "include", build / "tools/clang/include"]:
        paths += [p for p in base.rglob("*") if p.is_file() and p.suffix in [".h", ".inc"]]
    destination.write_text(json.dumps({str(p.relative_to(build)): sha(p) for p in sorted(set(paths))}, indent=2) + "\n")


def write_evidence_capsule(out, report):
    """Serialize existing actual command results; never rerun or invent a pass."""
    paths = [p for p in sorted(out.iterdir()) if p.is_file() and p.name != "evidence.json"]
    for key in ["compiler_source_inventory"]:
        if report.get(key): paths.append(Path(report[key]))
    if report.get("candidate_binary_sha256"):
        candidates = [out / "clang", out / "compiler-build/bin/clang"]
        if report.get("compiler_build_root"):
            candidates.append(Path(report["compiler_build_root"]) / "bin/clang")
        paths += [p for p in candidates if p.is_file() and sha(p) == report["candidate_binary_sha256"]]
    # The saved report carries complete source/build witnesses and transitive
    # parent-evidence hashes. Large source/build trees stay local.
    paths = sorted(set(paths))
    doc = {k: report[k] for k in ["kind", "origin", "outcome", "recorded_at", "summary", "commands"]}
    doc.update(commit=subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
               artifacts=[str(p.relative_to(ROOT)) for p in paths],
               sha256={str(p.relative_to(ROOT)): sha(p) for p in paths},
               evidence_writer_sha256=sha(Path(__file__)),
               real_allocator_compiler_qualified=report["real_allocator_compiler_qualified"],
               full_apple_compiler_equivalence=False, device_executed=False)
    (out / "evidence.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def allocator_metadata(path):
    """Resolve actual arm64 object symbols/relocations to selected metadata."""
    if macho(path)["filetype"] != 1:
        raise ValueError("Allocator input is not an arm64 object")
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 16)[0]
    at, sections, symtab = 32, [], None
    for _ in range(count):
        cmd, length = struct.unpack_from("<II", data, at)
        if cmd == 0x19:
            n = struct.unpack_from("<I", data, at + 64)[0]
            for i in range(n):
                name, segment, addr, size, offset, align, reloc, nr, flags, _, _, _ = struct.unpack_from("<16s16sQQ8I", data, at + 72 + i * 80)
                if offset > len(data) or size > len(data) - offset or reloc > len(data) or nr > (len(data) - reloc) // 8:
                    raise ValueError("Allocator section/relocation file extent is invalid")
                sections.append({"name": name.split(b"\0")[0].decode("ascii"), "segment": segment.split(b"\0")[0].decode("ascii"),
                                 "address": addr, "size": size, "offset": offset, "reloc": reloc, "nreloc": nr})
        if cmd == 2:
            if length < 24 or symtab is not None:
                raise ValueError("Invalid allocator symbol table command")
            symtab = struct.unpack_from("<4I", data, at + 8)
        at += length
    if symtab is None:
        raise ValueError("Allocator object has no actual symbol table")
    off, n, strings, size = symtab
    if off > len(data) or n > (len(data) - off) // 16 or strings > len(data) or size > len(data) - strings:
        raise ValueError("Allocator symbol/string table extent is invalid")
    symbols, named = [], {}
    for i in range(n):
        si, kind, sect, desc, value = struct.unpack_from("<IBBHQ", data, off + i * 16)
        if si >= size:
            raise ValueError("Allocator symbol name offset is invalid")
        end = data.find(b"\0", strings + si, strings + size)
        if end < 0:
            raise ValueError("Unterminated allocator symbol name")
        name = data[strings + si:end].decode("ascii")
        symbol = {"name": name, "kind": kind, "section": sect, "value": value}
        symbols.append(symbol)
        if kind & 0x0E == 0x0E:
            if not 1 <= sect <= len(sections):
                raise ValueError("Allocator symbol section is invalid")
            if name in named:
                raise ValueError("Duplicate allocator defined symbol")
            named[name] = symbol

    def location(name, length):
        symbol = named[name]
        section = sections[symbol["section"] - 1]
        delta = symbol["value"] - section["address"]
        if delta < 0 or delta > section["size"] or length > section["size"] - delta:
            raise ValueError("Allocator symbol storage is outside its section")
        return section, delta, section["offset"] + delta

    _, _, layout_at = location("_s24_allocator_layout", 32)
    total, sig_off, flags_off, size_off = struct.unpack_from("<4Q", data, layout_at)
    if not 0 < total <= 256 or sig_off + 8 > total or flags_off + 4 > total or size_off + 4 > total:
        raise ValueError("Actual selected allocator header layout is invalid")
    records = []
    expected = [("_s24_mixed_view", "12", 0x61), ("_s24_data_view", "", 0x69), ("_s24_pointer_view", "11", 0xE1)]
    for name, signature, flags in expected:
        section, delta, record_at = location(name, total)
        if (section["segment"], section["name"]) != ("__DATA_CONST", "__kalloc_type"):
            raise ValueError("Actual allocation view is outside selected metadata section")
        relocations = []
        for i in range(section["nreloc"]):
            address, info = struct.unpack_from("<iI", data, section["reloc"] + i * 8)
            if address == delta + sig_off:
                relocations.append(info)
        if len(relocations) != 1:
            raise ValueError("Allocator signature requires exactly one actual relocation")
        info = relocations[0]
        if (info >> 28) != 0 or (info >> 24) & 1 or (info >> 25) & 3 != 3:
            raise ValueError("Unsupported allocator pointer relocation encoding")
        addend = struct.unpack_from("<Q", data, record_at + sig_off)[0]
        index = info & 0xFFFFFF
        if (info >> 27) & 1:
            if index >= len(symbols) or not 1 <= symbols[index]["section"] <= len(sections):
                raise ValueError("Allocator signature relocation symbol is not defined")
            target_section = sections[symbols[index]["section"] - 1]
            target = symbols[index]["value"] + addend
        else:
            if not 1 <= index <= len(sections):
                raise ValueError("Allocator signature relocation section is invalid")
            target_section, target = sections[index - 1], addend
        relative = target - target_section["address"]
        if target_section["name"] != "__cstring" or relative < 0 or relative >= target_section["size"]:
            raise ValueError("Allocator signature does not resolve inside actual cstring section")
        start = target_section["offset"] + relative
        end = data.find(b"\0", start, target_section["offset"] + target_section["size"])
        if end < 0:
            raise ValueError("Unterminated actual allocator signature")
        actual = data[start:end].decode("ascii")
        actual_flags = struct.unpack_from("<I", data, record_at + flags_off)[0]
        actual_size = struct.unpack_from("<I", data, record_at + size_off)[0]
        if actual != signature or actual_flags != flags or actual_size != 16:
            raise ValueError("Actual type-sensitive allocator record differs from public expectations")
        records.append({"name": name, "signature": actual, "flags": actual_flags, "allocation_size": actual_size,
                        "record_file_offset": record_at, "flags_file_offset": record_at + flags_off})
    return {"header_layout": {"size": total, "signature": sig_off, "flags": flags_off, "allocation_size": size_off}, "records": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--clang", type=Path, action="append", required=True)
    parser.add_argument("--build-frontend", action="store_true")
    parser.add_argument("--host-cxx", type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--reuse-frontend-run", type=Path)
    parser.add_argument("--frontend-evidence", type=Path,
                        help="Recorded parent compiler evidence binding source, archive and generated-header inputs")
    parser.add_argument("--continue-frontend-run", type=Path,
                        help="Continue a terminal failed unchanged source build, keeping prior report/log bytes")
    parser.add_argument("--expanded-controls", action="store_true")
    parser.add_argument("--e1s-profile", action="store_true",
                        help="Probe selected E1S board/private compiler defines; does not configure a full kernel build")
    parser.add_argument("--compile-interfaces", action="store_true",
                        help="Actually compile all17 previously generated selected interfaces")
    parser.add_argument("--qualify-supported-profile", action="store_true",
                        help="Require complete concrete controls before a bounded experimental compiler component pass")
    parser.add_argument("--unevaluated-void-port", action="store_true",
                        help="Rebuild/check selected GNU unevaluated void typeof support without allowing runtime dereference")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        parser.error("Use a fresh canonical run name")
    for compiler in args.clang:
        if not compiler.is_absolute() or not compiler.is_file() or not os.access(compiler, os.X_OK):
            parser.error("Use explicit installed compiler executables")
    if args.build_frontend and (not args.host_cxx or not args.host_cxx.is_absolute() or not args.host_cxx.is_file() or not 1 <= args.jobs <= 4):
        parser.error("A private frontend build requires an explicit installed C++ compiler and 1..4 jobs")
    if not 1 <= args.jobs <= 4:
        parser.error("Use 1..4 build jobs")
    if sum(bool(x) for x in [args.build_frontend, args.reuse_frontend_run, args.continue_frontend_run]) > 1:
        parser.error("Build fresh or explicitly reuse a completed compiler run")
    if args.qualify_supported_profile and not (args.expanded_controls and args.e1s_profile and args.compile_interfaces and args.frontend_evidence):
        parser.error("Profile qualification requires all concrete controls, E1S interfaces and recorded compiler provenance")
    ledger = json.loads((ROOT / "state/lab.json").read_text())
    evidence_path = ROOT / "state/evidence/IIGABI-013.json"
    experiment = next(e for e in ledger["experiments"] if e["id"] == "IIGABI-013")
    if sha(evidence_path) != experiment["evidence_sha256"]:
        raise ValueError("Parent IIG evidence changed")
    evidence = json.loads(evidence_path.read_text())
    for name, value in evidence["sha256"].items():
        if sha(ROOT / name) != value:
            raise ValueError("Parent IIG artifact changed: " + name)
    parent = json.loads((ROOT / "fixtures/public/xnu-dependencies/firehose-session1.json").read_text())
    witness = ROOT / "artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json"
    kernel = ROOT / "artifacts/xnu-prepare/e1s-dependency-source-session1/xnu"
    if sha(witness) != parent["kernel_tree_manifest_sha256"] or sha(kernel.parent / "report.json") != parent["prepared_report_sha256"]:
        raise ValueError("Prepared selected source witness/report changed")
    files = json.loads(witness.read_text())
    actual = {str(p.relative_to(kernel)) for p in kernel.rglob("*") if p.is_file() and ".git" not in p.relative_to(kernel).parts}
    if actual != set(files) or any(sha(kernel / n) != value for n, value in files.items()):
        raise ValueError("Actual selected prepared source differs")
    out = ROOT / "artifacts/xnu-compiler-types" / args.run
    if out.resolve() != out:
        raise ValueError("Run cannot escape via a symlink")
    out.mkdir(parents=True, exist_ok=False)
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    report = {"kind": "host-test", "origin": "local-host", "outcome": "fail", "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "commands": [], "compilers": [], "builder_sha256": sha(Path(__file__)), "selected_tree_sha256": sha(witness),
              "iig_evidence_sha256": sha(evidence_path), "real_allocator_compiler_qualified": False,
              "constant_fallback_used": False, "sdk_used": False, "device_executed": False}
    env = dict(os.environ, LC_ALL="C")

    def run(argv, label, streamed=False, timeout=90, cwd=None):
        argv = list(map(str, argv))
        so, se = out / (label + ".stdout.txt"), out / (label + ".stderr.txt")
        print(json.dumps({"label": label, "started": True}), flush=True)
        if streamed:
            with so.open("w") as stdout, se.open("w") as stderr:
                r = subprocess.run(argv, stdout=stdout, stderr=stderr, text=True, timeout=timeout, env=env, cwd=cwd)
        else:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
            so.write_text(r.stdout); se.write_text(r.stderr)
        report["commands"].append({"argv": argv, "exit_code": r.returncode,
                                  "stdout": str(so.relative_to(ROOT)), "stderr": str(se.relative_to(ROOT)),
                                  "cwd": str(cwd or ROOT)})
        print(json.dumps({"label": label, "exit_code": r.returncode}), flush=True)
        return r

    target_header = ROOT / "artifacts/open-kernel-inputs/typed-pthread-session1/header-tree/src/Libraries/AvailabilityVersions/include"
    reuse = json.loads((ROOT / "fixtures/public/open-kernel-inputs/reusable-components.json").read_text())["pthread"]
    if sha(target_header / "TargetConditionals.h") != reuse["target_header_sha256"]:
        raise ValueError("Genuine corrected target header differs")
    iig = ROOT / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1"
    dirs = [target_header, iig / "setup-headers", iig / "generated", iig / "mach-server-headers",
            ROOT / reuse["mach_generated_root"], *[kernel / n for n in ["osfmk", "bsd", "iokit", "libkern", "pexpert", "EXTERNAL_HEADERS", "osfmk/libsa"]]]
    capability = out / "capabilities.cpp"
    capability.write_text('S24_SIGNATURE = __has_builtin(__builtin_xnu_type_signature);\nS24_SUMMARY = __has_builtin(__builtin_xnu_type_summary);\nS24_COMPATIBLE = __has_builtin(__builtin_xnu_types_compatible);\nS24_SEMANTICS = __has_attribute(xnu_usage_semantics);\n')
    allocator = out / "allocator.cpp"
    allocator.write_text('#include <kern/kalloc.h>\nstruct S24Mixed { void *pointer; unsigned long long word; };\nKALLOC_TYPE_DEFINE(s24_mixed_view, S24Mixed, KT_DEFAULT);\n')
    try:
        if args.frontend_evidence and not args.reuse_frontend_run:
            parent_path = (ROOT / args.frontend_evidence).resolve()
            recorded = next(e for e in ledger["experiments"] if e.get("evidence") == str(parent_path.relative_to(ROOT)))
            if sha(parent_path) != recorded["evidence_sha256"]:
                raise ValueError("Recorded direct compiler provenance differs")
            doc = json.loads(parent_path.read_text())
            for compiler in args.clang:
                if sha(compiler) != doc["sha256"][str(compiler.relative_to(ROOT))]:
                    raise ValueError("Actual direct source compiler differs from recorded bytes")
            report["frontend_parent_evidence_sha256"] = sha(parent_path)
        if args.continue_frontend_run:
            previous = args.continue_frontend_run.resolve()
            if not previous.is_relative_to(ROOT / "artifacts/xnu-compiler-types"):
                raise ValueError("Continue only an explicit private source run")
            old = json.loads((previous / "report.json").read_text())
            if old["outcome"] != "fail" or old.get("candidate_binary_sha256"):
                raise ValueError("Continuation requires a terminal failed build without a completed binary")
            private = Path(old.get("compiler_source_root", str(previous / "compiler-source")))
            build = Path(old.get("compiler_build_root", str(previous / "compiler-build")))
            inventory = Path(old.get("compiler_source_inventory", str(previous / "compiler-source-files.json")))
            if not private.resolve().is_relative_to(ROOT / "artifacts/xnu-compiler-types") or not build.resolve().is_relative_to(ROOT / "artifacts/xnu-compiler-types"):
                raise ValueError("Continued compiler paths escape the private namespace")
            if sha(inventory) != old["patched_source_inventory_sha256"] or any(sha(private / n) != h for n, h in json.loads(inventory.read_text()).items()):
                raise ValueError("Unchanged source continuation witness differs")
            active = []
            for proc in Path("/proc").glob("[0-9]*"):
                if proc.name == str(os.getpid()): continue
                try: command = (proc / "cmdline").read_bytes()
                except (FileNotFoundError, PermissionError, ProcessLookupError): continue
                if str(build).encode() in command: active.append(int(proc.name))
            if active:
                raise ValueError("Prior build/compiler processes are still live: " + str(active))
            report.update(compiler_source=old["compiler_source"], host_cxx_sha256=old["host_cxx_sha256"],
                patched_source_inventory_sha256=sha(inventory), compiler_source_inventory=str(inventory),
                compiler_source_root=str(private), compiler_build_root=str(build), previous_report_sha256=sha(previous / "report.json"))
            ninja = Path(shutil.which("ninja"))
            if run([ninja, "-C", build, "-j", str(args.jobs), "clang"], "frontend-continue", True, 1500).returncode:
                raise RuntimeError("Actual unchanged source compiler continuation failed")
            candidate = build / "bin/clang"
            report["candidate_binary_sha256"] = sha(candidate)
            write_reuse_witness(build, out / "reuse-files.json")
            args.clang.append(candidate)
        if args.reuse_frontend_run:
            previous = args.reuse_frontend_run.resolve()
            if not previous.is_relative_to(ROOT / "artifacts/xnu-compiler-types"):
                raise ValueError("Reuse only an explicit private compiler run")
            old = json.loads((previous / "report.json").read_text())
            if not args.frontend_evidence:
                raise ValueError("Explicit recorded parent compiler evidence is required for reuse")
            parent_path = (ROOT / args.frontend_evidence).resolve()
            relative_evidence = str(parent_path.relative_to(ROOT))
            recorded = next(e for e in ledger["experiments"] if e.get("evidence") == relative_evidence)
            if sha(parent_path) != recorded["evidence_sha256"]:
                raise ValueError("Parent compiler evidence bytes changed")
            parent_doc = json.loads(parent_path.read_text())
            witness = previous / "reuse-files.json"
            for path in [previous / "report.json", witness]:
                if sha(path) != parent_doc["sha256"][str(path.relative_to(ROOT))]:
                    raise ValueError("Recorded parent compiler witness/report differs")
            private = Path(old.get("compiler_source_root", str(previous / "compiler-source")))
            inventory = Path(old.get("compiler_source_inventory", str(previous / "compiler-source-files.json")))
            if sha(inventory) != old["patched_source_inventory_sha256"]:
                raise ValueError("Prior compiler source inventory changed")
            if any(sha(private / n) != h for n, h in json.loads(inventory.read_text()).items()):
                raise ValueError("Prior compiler source bytes changed")
            build = Path(old.get("compiler_build_root", str(previous / "compiler-build")))
            for n, value in json.loads(witness.read_text()).items():
                if sha(build / n) != value:
                    raise ValueError("Prior compiler archive/generated header/recipe changed: " + n)
            report["frontend_parent_evidence_sha256"] = sha(parent_path)
            report["reused_build_witness_sha256"] = sha(witness)
            binary = build / "bin/clang"
            if sha(binary) != old["candidate_binary_sha256"]:
                raise ValueError("Prior actual compiler binary changed")
            # Rebuild only the changed parser TU in a new output directory and
            # relink against unchanged source-built libraries. The old run's
            # source, generated headers, objects, archives and binary stay intact.
            new_source = out / "parser-source"
            relative = Path("src/clang/lib/Parse/ParseExpr.cpp")
            (new_source / relative).parent.mkdir(parents=True)
            shutil.copyfile(private / relative, new_source / relative)
            patch = ROOT / "patches/compiler-types/0002-parse-type-only-xnu-builtins.patch"
            for extra in [["--check"], []]:
                if run(["git", "-c", "core.hooksPath=/dev/null", "-C", new_source, "apply", *extra, patch], "parser-patch" + ("-check" if extra else "")).returncode:
                    raise RuntimeError("Type-only parser patch failed")
            ninja = Path(shutil.which("ninja"))
            query = run([ninja, "-C", build, "-t", "commands", "tools/clang/lib/Parse/CMakeFiles/obj.clangParse.dir/ParseExpr.cpp.o"], "parser-compile-recipe")
            command = shlex.split(query.stdout.splitlines()[-1])
            if sha(Path(command[0])) != old["host_cxx_sha256"] or str(private / relative) not in command:
                raise ValueError("Unexpected actual parser compiler recipe")
            obj = out / "ParseExpr.cpp.o"
            command[command.index(str(private / relative))] = str(new_source / relative)
            for flag, value in [("-o", obj), ("-MF", out / "ParseExpr.cpp.o.d"), ("-MT", obj)]:
                if flag in command:
                    command[command.index(flag) + 1] = str(value)
            if run(command, "parser-compile", True, 180, build).returncode:
                raise RuntimeError("Actual corrected parser compilation failed")
            archive = out / "libclangParse.a"
            shutil.copyfile(build / "lib/libclangParse.a", archive)
            ar = args.clang[0].parent / "llvm-ar"
            report["archive_tool_sha256"] = sha(ar)
            if run([ar, "r", archive, obj], "parser-archive").returncode:
                raise RuntimeError("Actual parser archive replacement failed")
            r = run([ar, "p", archive, obj.name], "parser-member", True)
            if r.returncode or sha(out / "parser-member.stdout.txt") != sha(obj):
                raise ValueError("Actual archive member differs from corrected parser object")
            sema_archive = None
            if args.unevaluated_void_port:
                sema_relative = Path("src/clang/lib/Sema/SemaExpr.cpp")
                (new_source / sema_relative).parent.mkdir(parents=True)
                shutil.copyfile(private / sema_relative, new_source / sema_relative)
                sema_patch = ROOT / "patches/compiler-types/0003-gnu-unevaluated-void-typeof.patch"
                for extra in [["--check"], []]:
                    if run(["git", "-c", "core.hooksPath=/dev/null", "-C", new_source, "apply", *extra, sema_patch], "void-patch" + ("-check" if extra else "")).returncode:
                        raise RuntimeError("GNU unevaluated void patch failed")
                query = run([ninja, "-C", build, "-t", "commands", "tools/clang/lib/Sema/CMakeFiles/obj.clangSema.dir/SemaExpr.cpp.o"], "sema-compile-recipe")
                command = shlex.split(query.stdout.splitlines()[-1])
                if sha(Path(command[0])) != old["host_cxx_sha256"] or str(private / sema_relative) not in command:
                    raise ValueError("Unexpected actual semantic compiler recipe")
                sema_obj = out / "SemaExpr.cpp.o"
                command[command.index(str(private / sema_relative))] = str(new_source / sema_relative)
                for flag, value in [("-o", sema_obj), ("-MF", out / "SemaExpr.cpp.o.d"), ("-MT", sema_obj)]:
                    if flag in command: command[command.index(flag) + 1] = str(value)
                if run(command, "sema-compile", True, 180, build).returncode:
                    raise RuntimeError("Actual GNU semantic module compilation failed")
                sema_archive = out / "libclangSema.a"
                shutil.copyfile(build / "lib/libclangSema.a", sema_archive)
                if run([ar, "r", sema_archive, sema_obj], "sema-archive").returncode:
                    raise RuntimeError("Actual semantic archive replacement failed")
                r = run([ar, "p", sema_archive, sema_obj.name], "sema-member", True)
                if r.returncode or sha(out / "sema-member.stdout.txt") != sha(sema_obj):
                    raise ValueError("Actual semantic archive member differs")
                report["void_semantics_patch_sha256"] = sha(sema_patch)
                report["sema_source_sha256"] = sha(new_source / sema_relative)
            query = run([ninja, "-C", build, "-t", "commands", str(binary.resolve().relative_to(build))], "compiler-link-recipe")
            command = shlex.split(query.stdout.splitlines()[-1])
            if command[:2] == [":", "&&"]: command = command[2:]
            if command[-2:] == ["&&", ":"]: command = command[:-2]
            if any(t in command for t in ["&&", ";", "|", "||"]) or sha(Path(command[0])) != old["host_cxx_sha256"]:
                raise ValueError("Only a single known compiler link argv is allowed")
            if command.count("lib/libclangParse.a") != 1:
                raise ValueError("Unexpected parser library multiplicity in actual link recipe")
            report["reuse_inputs_sha256"] = {str((build / p).resolve()): sha((build / p).resolve())
                for p in command if p.endswith((".a", ".o")) and (build / p).is_file()}
            command[command.index("lib/libclangParse.a")] = str(archive)
            if sema_archive:
                if command.count("lib/libclangSema.a") != 1:
                    raise ValueError("Unexpected semantic library multiplicity in actual link recipe")
                command[command.index("lib/libclangSema.a")] = str(sema_archive)
            candidate = out / "clang"
            command[command.index("-o") + 1] = str(candidate)
            if run(command, "compiler-relink", True, 180, build).returncode:
                raise RuntimeError("Actual compiler relink failed")
            report.update(candidate_binary_sha256=sha(candidate), parser_patch_sha256=sha(patch),
                          parser_source_sha256=sha(new_source / relative), previous_report_sha256=sha(previous / "report.json"))
            args.clang.append(candidate)
        if args.build_frontend:
            catalog = json.loads((ROOT / "research/sources.json").read_text())["sources"]
            source = next(s for s in catalog if s["id"] == "xnu-tapi")
            if source["revision"] != "fa9443738c1a18accef4244732ec6d6ee97a8133":
                raise ValueError("Use the exact reviewed public Clang17 source pin")
            report["compiler_source"] = sources.verify(ROOT, source)
            report["host_cxx_sha256"] = sha(args.host_cxx)
            private = out / "compiler-source"
            shutil.copytree(ROOT / "references/xnu-tapi", private,
                            ignore=shutil.ignore_patterns(".git", "test", "tests", "unittests", "docs", "examples", "benchmarks"))
            patch = ROOT / "patches/compiler-types/0001-experimental-xnu-target-type-metadata.patch"
            for extra in [["--check"], []]:
                if run(["git", "-c", "core.hooksPath=/dev/null", "-C", private, "apply", *extra, patch], "frontend-patch" + ("-check" if extra else "")).returncode:
                    raise RuntimeError("Actual source compiler patch failed")
            header = ROOT / "patches/compiler-types/XnuTypeMetadata.h"
            shutil.copyfile(header, private / "src/clang/include/clang/AST/XnuTypeMetadata.h")
            inventory = {str(p.relative_to(private)): sha(p) for p in sorted(private.rglob("*")) if p.is_file()}
            manifest = out / "compiler-source-files.json"
            manifest.write_text(json.dumps(inventory, indent=2) + "\n")
            report["patched_source_inventory_sha256"] = sha(manifest)
            report["compiler_source_inventory"] = str(manifest)
            report["compiler_source_root"] = str(private)
            report["compiler_patch_sha256"] = sha(patch)
            report["compiler_extension_header_sha256"] = sha(header)
            build = out / "compiler-build"
            report["compiler_build_root"] = str(build)
            cmake, ninja = Path(shutil.which("cmake")), Path(shutil.which("ninja"))
            report["build_tool_sha256"] = {str(p): sha(p) for p in [cmake, ninja]}
            r = run([cmake, "-S", private / "src/llvm", "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_C_COMPILER=" + str(args.clang[0]), "-DCMAKE_CXX_COMPILER=" + str(args.host_cxx),
                "-DCMAKE_C_FLAGS_RELEASE=-O1 -DNDEBUG", "-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG",
                "-DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=" + str(args.clang[0].parent / "ld.lld"),
                "-DLLVM_ENABLE_PROJECTS=clang", "-DLLVM_TARGETS_TO_BUILD=AArch64", "-DLLVM_INCLUDE_TESTS=OFF",
                "-DLLVM_INCLUDE_BENCHMARKS=OFF", "-DLLVM_INCLUDE_EXAMPLES=OFF", "-DLLVM_ENABLE_BINDINGS=OFF",
                "-DCLANG_INCLUDE_TESTS=OFF", "-DCLANG_INCLUDE_DOCS=OFF", "-DCLANG_ENABLE_STATIC_ANALYZER=OFF",
                "-DCLANG_ENABLE_ARCMT=OFF", "-DLLVM_ENABLE_ZLIB=OFF", "-DLLVM_ENABLE_ZSTD=OFF",
                "-DLLVM_ENABLE_LIBXML2=OFF", "-DLLVM_ENABLE_TERMINFO=OFF", "-DLLVM_ENABLE_LIBEDIT=OFF"], "frontend-configure", True, 180)
            if r.returncode:
                raise RuntimeError("Actual public compiler configuration failed")
            r = run([ninja, "-C", build, "-j", str(args.jobs), "clang"], "frontend-build", True, 1500)
            if r.returncode:
                raise RuntimeError("Actual public compiler build failed")
            candidate = build / "bin/clang"
            report["candidate_binary_sha256"] = sha(candidate)
            write_reuse_witness(build, out / "reuse-files.json")
            args.clang.append(candidate)
        for index, compiler in enumerate(args.clang):
            name = "compiler-" + str(index)
            version = run([compiler, "--version"], name + "-version")
            entry = {"path": str(compiler), "resolved": str(compiler.resolve()), "sha256": sha(compiler), "version": version.stdout.splitlines()[0], "cases": []}
            report["compilers"].append(entry)
            base = [compiler, "-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc", "-std=gnu++17"]
            r = run([*base, "-E", "-P", "-x", "c++", capability], name + "-capabilities")
            entry["features"] = dict((k, int(v)) for k, v in re.findall(r"S24_(\w+)\s*=\s*(\d+)", r.stdout))
            flags = [*base, "-mkernel", "-DKERNEL=1", "-DKERNEL_PRIVATE=1", "-DPRIVATE=1", "-DDRIVERKIT_PRIVATE=1",
                     *[a for d in dirs for a in ["-I", d]]]
            if len(entry["features"]) == 4 and all(entry["features"].values()):
                flags += ["-DXNU_NO_TYPE_BUILTINS=0"]
                entry["allocator_type_checks_enabled"] = True
            if args.e1s_profile:
                flags += ["-DAPPLE=1", "-D__MACHO__=1", "-DXNU_KERNEL_PRIVATE=1", "-DXNU_KERN_EVENT_DATA_IS_VLA=1", "-DARM64_BOARD_CONFIG_E1S=1"]
                entry["e1s_profile"] = {"full_kernel_profile_qualified": False, "source_sha256": {
                    n: sha(kernel / n) for n in ["makedefs/MakeInc.def", "pexpert/pexpert/arm64/board_config.h", "pexpert/pexpert/arm64/E1S.h"]}}
            for case in ["public-contract", "annotation-contract", *(["template-layout-contract"] if args.expanded_controls else []),
                         *(["unevaluated-void-contract"] if args.unevaluated_void_port else [])]:
                source = ROOT / "fixtures/public/xnu-compiler-types" / (case + ".cpp")
                obj = out / (name + "-" + case + ".o")
                r = run([*base, "-Werror=unknown-attributes", "-c", source, "-o", obj], name + "-" + case)
                entry["cases"].append({"case": case, "source_sha256": sha(source), "exit_code": r.returncode,
                    "actual_arm64_object": r.returncode == 0 and macho(obj)["filetype"] == 1, "object_sha256": sha(obj) if obj.is_file() else None})
            if args.expanded_controls:
                entry["negative_controls"] = []
                positive = all(x["actual_arm64_object"] for x in entry["cases"])
                negatives = [("negative-data-pointer", "S24_EXPECTED_DATA_REJECTION"),
                    ("negative-incompatible-free", "Pointer type is not compatible with specified type"),
                    ("negative-virtual-base", "experimental XNU metadata does not support"),
                    ("negative-member-pointer", "experimental XNU metadata does not support"),
                    ("negative-unknown-semantics", "unsupported XNU usage semantic")]
                if args.unevaluated_void_port:
                    negatives.append(("negative-evaluated-void", "indirection not permitted on operand"))
                for case, expected in negatives:
                    source = ROOT / "fixtures/public/xnu-compiler-types" / (case + ".cpp")
                    r = run([*flags, "-Werror=unknown-attributes", "-fsyntax-only", source], name + "-" + case)
                    errors = [line for line in r.stderr.splitlines() if "error:" in line]
                    entry["negative_controls"].append({"case": case, "source_sha256": sha(source), "exit_code": r.returncode,
                        "qualified_rejection": positive and r.returncode != 0 and len(errors) == 1 and expected in errors[0]})
            selected_cases = [("selected-allocator", allocator), ("selected-metaclass", iig / "generated/DriverKit/IODispatchQueue.iig.cpp")]
            if args.expanded_controls:
                selected_cases.append(("allocator-metadata", ROOT / "fixtures/public/xnu-compiler-types/allocator-metadata.cpp"))
            for case, source in selected_cases:
                obj = out / (name + "-" + case + ".o")
                r = run([*flags, "-include", "IOKit/IOReturn.h", "-include", "IOKit/IORPC.h", "-include", "DriverKit/IODispatchQueue.h",
                         "-c", source, "-o", obj], name + "-" + case)
                entry["cases"].append({"case": case, "source_sha256": sha(source), "exit_code": r.returncode,
                    "actual_arm64_object": r.returncode == 0 and macho(obj)["filetype"] == 1, "object_sha256": sha(obj) if obj.is_file() else None})
                if case == "allocator-metadata" and r.returncode == 0:
                    try:
                        entry["allocator_metadata"] = allocator_metadata(obj)
                        entry["metadata_mutations"] = []
                        raw = obj.read_bytes()
                        for mutation in ["truncated", "wrong-flags", "escaped-signature"]:
                            bad = bytearray(raw)
                            record = entry["allocator_metadata"]["records"][0]
                            if mutation == "truncated": bad = bad[:16]
                            if mutation == "wrong-flags": bad[record["flags_file_offset"]] ^= 8
                            if mutation == "escaped-signature":
                                offset = record["record_file_offset"] + entry["allocator_metadata"]["header_layout"]["signature"]
                                struct.pack_into("<Q", bad, offset, (1 << 64) - 1)
                            invalid = out / (name + "-" + mutation + ".o")
                            invalid.write_bytes(bad)
                            try:
                                allocator_metadata(invalid)
                                rejected = False
                            except (ValueError, KeyError, UnicodeError, struct.error): rejected = True
                            entry["metadata_mutations"].append({"case": mutation, "rejected": rejected, "object_sha256": sha(invalid)})
                    except (ValueError, KeyError, UnicodeError, struct.error) as error:
                        entry["allocator_metadata_error"] = str(error)
            if args.compile_interfaces:
                interfaces = sorted((iig / "generated/DriverKit").glob("*.iig.cpp"))
                if len(interfaces) != 17:
                    raise ValueError("Actual selected generated interface inventory differs")
                entry["selected_interfaces"] = []
                for source in interfaces:
                    class_name = source.name.removesuffix(".iig.cpp")
                    obj = out / (name + "-" + class_name + ".o")
                    r = run([*flags, "-include", "IOKit/IOReturn.h", "-include", "IOKit/IORPC.h",
                             "-include", "DriverKit/" + class_name + ".h", "-c", source, "-o", obj], name + "-iig-" + class_name)
                    entry["selected_interfaces"].append({"name": class_name, "source_sha256": sha(source), "exit_code": r.returncode,
                        "actual_arm64_object": r.returncode == 0 and macho(obj)["filetype"] == 1, "object_sha256": sha(obj) if obj.is_file() else None})
        report["outcome"] = "inconclusive" if any(all(x["actual_arm64_object"] for x in c["cases"]) and
            (not args.expanded_controls or (all(x["qualified_rejection"] for x in c["negative_controls"]) and c.get("allocator_metadata") and
              all(x["rejected"] for x in c["metadata_mutations"]))) for c in report["compilers"]) else "fail"
        report["summary"] = "Actual installed compiler APIs/public granule controls/selected allocator and metaclass compiles measured; complete allocator/compiler equivalence remains unqualified"
        if args.compile_interfaces and not any(len(c.get("selected_interfaces", [])) == 17 and all(x["actual_arm64_object"] for x in c["selected_interfaces"]) for c in report["compilers"]):
            report["outcome"] = "fail"
        if args.qualify_supported_profile:
            for c in report["compilers"]:
                c["supported_profile_qualified"] = (len(c["cases"]) == (7 if args.unevaluated_void_port else 6) and all(x["actual_arm64_object"] for x in c["cases"]) and
                    len(c.get("negative_controls", [])) == (6 if args.unevaluated_void_port else 5) and all(x["qualified_rejection"] for x in c["negative_controls"]) and
                    bool(c.get("allocator_metadata")) and len(c.get("metadata_mutations", [])) == 3 and all(x["rejected"] for x in c["metadata_mutations"]) and
                    len(c.get("selected_interfaces", [])) == 17 and all(x["actual_arm64_object"] for x in c["selected_interfaces"]))
            qualified = any(c["supported_profile_qualified"] for c in report["compilers"])
            report.update(outcome="pass" if qualified else "fail", real_allocator_compiler_qualified=qualified,
                full_apple_compiler_equivalence=False, supported_profile="Experimental public-source plain arm64 iOS16.5 compiler metadata; actual selected E1S/private defines and17 generated interfaces",
                summary="Bounded real source compiler metadata/profile controls assessed; full kernel/Apple SDK/ABI/native support remain unqualified",
                limits=["No original selected Apple compiler oracle or full private language/allocator equivalence",
                        "No ARM execution, full kernel build or native hardware result",
                        "PAC/arm64e, virtual bases, reference/member-pointer, scalable/VLA and excessive/large layouts are rejected",
                        "Dependent builtin mangling/constant-evaluator fallback paths need separate hardening; explicit positive template controls pass"])
    except Exception as error:
        report["error"] = str(error)
        report["summary"] = "Actual compiler audit stopped; retained diagnostics are not qualification"
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    write_evidence_capsule(out, report)
    print(json.dumps({"outcome": report["outcome"], "compilers": [{"path": c["path"], "features": c.get("features")} for c in report["compilers"]]}))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
