#!/usr/bin/env python3
"""Audit real portable IIG behavior against selected public XNU inputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sources
from xnu_macho_tools import macho

PINS = {"nyktis-iig": "ea6d147d668ca15d490da638012243fcd705f30d",
        "puredarwin-build-inputs": "6982ddbfca1047c86680ec7c66da152789746efd",
        "puredarwin-iig": "28010c688caab7eb5400b9c98faa5b1e538e0108",
        "xnu-availability": "5d9baee345b3bc72b26c71adc65f94f2d5e9ced2",
        "allen-xnu-toolchain": "909990e4ec2c6cda30c20cdb23219946918c7fd6"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--cxx", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--libclang-prefix", type=Path, required=True)
    parser.add_argument("--prepared-run", type=Path, required=True)
    parser.add_argument("--selected-target-port", action="store_true",
                        help="Apply the explicit selected arm64 target guard patch in a private copy")
    parser.add_argument("--compiler-headers", action="store_true",
                        help="Supply matching installed libclang freestanding resource headers explicitly")
    parser.add_argument("--compile-generated", action="store_true",
                        help="Actually compile successful generated implementations against selected headers")
    parser.add_argument("--setup-headers", action="store_true",
                        help="Run reviewed selected XNU symbol/POSIX header generators with public availability source")
    parser.add_argument("--kernel-export-includes", action="store_true",
                        help="Expose genuine osfmk/libsa export-root string.h for implementation compilation")
    parser.add_argument("--legacy-rpc-port", action="store_true",
                        help="Apply the experimental selected24-byte IORPC emitter patch in a private copy")
    parser.add_argument("--server-headers", action="store_true",
                        help="Generate the actual selected MIG_USHDRS list using the qualified real migcom")
    parser.add_argument("--host-clang", type=Path,
                        help="Explicit installed host clang++ for actual generated CopyDispatchQueue sanitizer checks")
    parser.add_argument("--host-linux-port", action="store_true",
                        help="Use the attributed full-header Linux host profile and installed GNU sanitizer link")
    parser.add_argument("--host-guard-pages", action="store_true",
                        help="Use real Linux guard-page extent checks; no unavailable sanitizer runtime is implied")
    parser.add_argument("--guard-invoke", action="store_true",
                        help="Check real generated Invoke extents/nulls before touching message/reply/callback")
    args = parser.parse_args()
    if args.legacy_rpc_port and not args.selected_target_port:
        parser.error("The legacy RPC experiment requires the explicit selected target port")
    if args.guard_invoke and not args.legacy_rpc_port:
        parser.error("The Invoke guard experiment requires the experimental legacy RPC port")
    if args.host_guard_pages and (not args.host_linux_port or not args.host_clang):
        parser.error("Guard pages require the explicit host compiler and Linux header port")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Use a fresh canonical run name")
    for tool in [args.cxx, args.clang, *([args.host_clang] if args.host_clang else [])]:
        if not tool.is_absolute() or not tool.is_file() or not os.access(tool, os.X_OK):
            raise ValueError("Use explicit installed compiler executables")
    prefix = args.libclang_prefix.resolve()
    include = prefix / "include"
    library = (prefix / "lib/libclang.so").resolve()
    llvm_library = (prefix / "lib/libLLVM.so.19.0git").resolve()
    if not prefix.is_absolute() or not (include / "clang-c/Index.h").is_file() or not library.is_file() or not llvm_library.is_file():
        raise ValueError("Use the explicit installed matching ROCm LLVM19 C API prefix")
    prepared = args.prepared_run.resolve()
    if not prepared.is_relative_to(ROOT / "artifacts/xnu-prepare"):
        raise ValueError("Use an actual selected E1S prepared-source run")
    kernel = prepared / "xnu"
    parent = json.loads((ROOT / "fixtures/public/xnu-dependencies/firehose-session1.json").read_text())
    witness = ROOT / "artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json"
    if sha(witness) != parent["kernel_tree_manifest_sha256"] or sha(prepared / "report.json") != parent["prepared_report_sha256"]:
        raise ValueError("Prepared-source witness/report differs")
    tree = json.loads(witness.read_text())
    actual_names = {str(p.relative_to(kernel)) for p in kernel.rglob("*") if p.is_file() and ".git" not in p.relative_to(kernel).parts}
    if actual_names != set(tree) or any(sha(kernel / name) != value for name, value in tree.items()):
        raise ValueError("Selected prepared source bytes/file set changed")
    entries = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    provenance = []
    for identifier, pin in PINS.items():
        entry = next(s for s in entries if s["id"] == identifier)
        if entry["revision"] != pin:
            raise ValueError("Use exact reviewed candidate pins")
        provenance.append(sources.verify(ROOT, entry))
    out = ROOT / "artifacts/xnu-iig-abi" / args.run
    if out.resolve() != out:
        raise ValueError("Run cannot escape through a symlink")
    out.mkdir(parents=True, exist_ok=False)
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commands": [], "provenance": provenance,
              "builder_sha256": sha(Path(__file__)), "selected_kernel_tree_sha256": sha(witness),
              "libclang": {"path": str(library), "sha256": sha(library), "llvm_dependency": str(llvm_library),
                           "llvm_sha256": sha(llvm_library),
                           "c_api_headers_sha256": {str(p.relative_to(include)): sha(p) for p in sorted((include / "clang-c").glob("*.h"))}},
              "conditional_cases": [], "selected_interfaces": [], "hash_observations": [],
              "selected_apple_iig_abi_qualified": False, "sdk_used": False, "sdk_standins_used": False,
              "device_executed": False, "upstream_test_archive_used": False,
              "selected_target_port": args.selected_target_port,
              "compiler_headers": args.compiler_headers,
              "legacy_rpc_port": args.legacy_rpc_port,
              "limits": ["Nyktis implements observed DriverKit440 behavior, not a certified selected8796 oracle",
                         "Published numeric observations identify XNU10063.121.3/DriverKit286 and are not selected-version evidence",
                         "Parser/hash/layout checks remain distinct from full generated-interface compilation, marshalling and native execution"]}
    deadline = time.monotonic() + 300
    env = dict(os.environ)
    env.pop("IIG_TRACE_HEADERS", None)
    env["LC_ALL"] = "C"
    env["DRIVERKITROOT"] = ""

    def run(argv, label, stdin=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("IIG experiment command budget exhausted")
        result = subprocess.run(list(map(str, argv)), input=stdin, capture_output=True, text=True, env=env, timeout=min(60, remaining))
        so, se = out / (label + ".stdout.txt"), out / (label + ".stderr.txt")
        so.write_text(result.stdout)
        se.write_text(result.stderr)
        command = {"argv": list(map(str, argv)), "exit_code": result.returncode,
                   "stdout": str(so.relative_to(ROOT)), "stderr": str(se.relative_to(ROOT))}
        if stdin is not None:
            command["stdin_sha256"] = hashlib.sha256(stdin.encode()).hexdigest()
        report["commands"].append(command)
        print(json.dumps({"label": label, "exit_code": result.returncode}), flush=True)
        return result

    try:
        for name, tool in [("host_cxx", args.cxx), ("target_clang", args.clang)]:
            r = run([tool, "--version"], name + "-version")
            if r.returncode:
                raise RuntimeError("Compiler version check failed")
            report[name] = {"version": r.stdout.splitlines()[0], "sha256": sha(tool)}
        candidate = ROOT / "references/nyktis-iig"
        if args.selected_target_port:
            private = out / "candidate"
            private.mkdir()
            for name in ["iig.cpp", "LICENSE", "NOTICE"]:
                shutil.copyfile(candidate / name, private / name)
            patch = ROOT / "patches/iig-abi/0001-explicit-selected-arm64-target.patch"
            if run(["git", "-C", private, "apply", "--check", patch], "target-patch-check").returncode:
                raise RuntimeError("Explicit selected target patch does not apply")
            if run(["git", "-C", private, "apply", patch], "target-patch").returncode:
                raise RuntimeError("Explicit selected target patch failed")
            candidate = private
            report["target_patch_sha256"] = sha(patch)
            report["patched_candidate_sha256"] = sha(candidate / "iig.cpp")
            if args.legacy_rpc_port:
                patch = ROOT / "patches/iig-abi/0002-selected-legacy24-rpc.patch"
                if run(["git", "-C", private, "apply", "--check", patch], "legacy-patch-check").returncode:
                    raise RuntimeError("Experimental legacy RPC patch does not apply")
                if run(["git", "-C", private, "apply", patch], "legacy-patch").returncode:
                    raise RuntimeError("Experimental legacy RPC patch failed")
                report["legacy_patch_sha256"] = sha(patch)
                report["patched_candidate_sha256"] = sha(candidate / "iig.cpp")
                if args.guard_invoke:
                    patch = ROOT / "patches/iig-abi/0004-invoke-check-extents-before-access.patch"
                    if run(["git", "-C", private, "apply", "--check", patch], "invoke-patch-check").returncode or run(["git", "-C", private, "apply", patch], "invoke-patch").returncode:
                        raise RuntimeError("Invoke bounds/null guard patch failed")
                    report["invoke_guard_patch_sha256"] = sha(patch)
                    report["patched_candidate_sha256"] = sha(candidate / "iig.cpp")
        tool = out / "iig"
        built = run([args.cxx, "-std=c++17", "-O2", "-I", include, candidate / "iig.cpp", library,
                     "-Wl,-rpath," + str(library.parent), "-o", tool], "candidate-build")
        if built.returncode:
            raise RuntimeError("Actual portable IIG compilation failed")
        report["candidate_binary_sha256"] = sha(tool)
        version = run([tool, "--version"], "candidate-version")
        if version.returncode:
            raise RuntimeError("Actual candidate binary cannot run")
        report["candidate_version"] = version.stdout.strip()
        fixture = ROOT / "fixtures/public/xnu-iig-abi/ConditionalProbe.iig"
        for flag in [0, 1]:
            h, impl = out / ("conditional-" + str(flag) + ".h"), out / ("conditional-" + str(flag) + ".cpp")
            r = run([tool, "--def", fixture, "--header", h, "--impl", impl, "--", "-x", "c++", "-std=c++17",
                     "-ffreestanding", "-nostdinc", "-D__IIG=1", "-DENABLE_OPTION=" + str(flag)], "conditional-" + str(flag))
            ids = re.findall(r"#define\s+(ConditionalProbe_\w+_ID)\s+", h.read_text()) if h.is_file() else []
            expected = "ConditionalProbe_Enabled_ID" if flag else "ConditionalProbe_Disabled_ID"
            report["conditional_cases"].append({"flag": flag, "exit_code": r.returncode, "method_ids": ids,
                "selection_correct": r.returncode == 0 and ids == [expected], "header_sha256": sha(h) if h.is_file() else None})

        # Independent algorithm body is extracted verbatim from selected XNU,
        # retaining the local fasthash MIT notice. Composition is the candidate's
        # proposed class->method rule and is checked against published facts.
        original = kernel / "iokit/Kernel/IOKitDebug.cpp"
        text = original.read_text()
        start, end = text.index("/* fasthash\n"), text.index("static uint32_t\nfasthash32")
        body = text[start:end]
        helper = out / "selected-hash.cpp"
        helper.write_text('#include <cstdint>\n#include <cstddef>\n#include <cstring>\n#include <cstdio>\n' + body + '\nint main(int n,char**v){ if(n!=3 || std::strlen(v[1])>=256 || std::strlen(v[2])>=256)return 2; alignas(8) char c[256]={},m[256]={}; std::strcpy(c,v[1]);std::strcpy(m,v[2]); auto id=fasthash64(m,std::strlen(m),fasthash64(c,std::strlen(c),0)) | (1ULL<<63); std::printf("0x%016llx\\n",(unsigned long long)id); }\n')
        helper_binary = out / "selected-hash"
        if run([args.cxx, "-std=gnu++17", "-O2", helper, "-o", helper_binary], "hash-build").returncode:
            raise RuntimeError("Independent selected-source hash body failed compilation")
        report["hash_source_sha256"] = sha(original)
        report["hash_helper_sha256"] = sha(helper)
        observations_path = ROOT / "fixtures/public/xnu-iig-abi/published-id-observations.json"
        observed = json.loads(observations_path.read_text())
        if sha(ROOT / observed["snapshot"]) != observed["snapshot_sha256"] or observed["selected_version_match"]:
            raise ValueError("Published cross-version observation provenance differs")
        report["published_observations_sha256"] = sha(observations_path)
        selected_idl = (kernel / "iokit/DriverKit/IOService.iig").read_text()
        for name, expected in observed["io_service_method_ids"].items():
            r = run([helper_binary, "IOService", name], "hash-" + name)
            report["hash_observations"].append({"class": "IOService", "method": name, "computed": r.stdout.strip(),
                "published_newer_observation": expected, "matches_observed": r.returncode == 0 and r.stdout.strip() == expected,
                "method_name_in_selected_idl": re.search(r"\b" + name + r"\s*\(", selected_idl) is not None,
                "selected_version_oracle": False})

        reuse_path = ROOT / "fixtures/public/open-kernel-inputs/reusable-components.json"
        reuse = json.loads(reuse_path.read_text())["pthread"]
        target_header = ROOT / reuse["header_root"] / "TargetConditionals.h"
        if sha(target_header) != reuse["target_header_sha256"]:
            raise ValueError("Reusable corrected source header bytes changed")
        mach_root = ROOT / reuse["mach_generated_root"]
        for name, value in reuse["mach_generated_headers"].items():
            if sha(mach_root / "mach" / (name + ".h")) != value:
                raise ValueError("Reusable genuine Mach header bytes changed")
        dirs = [target_header.parent, mach_root, *[kernel / n for n in ["osfmk", "bsd", "iokit", "libkern", "pexpert", "EXTERNAL_HEADERS"]]]
        common = [args.clang, "-target", "arm64-apple-ios16.5", "-mkernel", "-ffreestanding", "-nostdinc", "-std=gnu++17",
                  "-DKERNEL=1", "-DKERNEL_PRIVATE=1", "-DPRIVATE=1", "-DDRIVERKIT_PRIVATE=1",
                  *[a for d in dirs for a in ["-I", d]]]
        if args.kernel_export_includes:
            common += ["-I", kernel / "osfmk/libsa"]
            report["kernel_export_string_header_sha256"] = sha(kernel / "osfmk/libsa/string.h")
        if args.server_headers:
            manifest_file = ROOT / "fixtures/public/xnu-host-tools/qualified-inputs.json"
            manifest = json.loads(manifest_file.read_text())
            migcom = (ROOT / manifest["generator_prefix"] / "bin/migcom").resolve()
            if not migcom.is_relative_to(ROOT / "artifacts/xnu-host-tools") or sha(migcom) != manifest["generator_binary_sha256"]["migcom"]:
                raise ValueError("Qualified real MIG compiler provenance differs")
            makefile = kernel / "osfmk/mach/Makefile"
            block = re.search(r"MIG_USHDRS\s*=\s*\\\n(.*?)\n\nMIG_UUHDRS", makefile.read_text(), re.DOTALL)
            if not block:
                raise ValueError("Actual selected Mach server-header recipe not recognized")
            names = re.findall(r"\b([A-Za-z0-9_]+)_server\.h\b", block.group(1))
            if len(names) != 14 or len(set(names)) != 14:
                raise ValueError("Actual selected Mach server-header inventory differs")
            mach_out = out / "mach-server-headers"
            (mach_out / "mach").mkdir(parents=True)
            report["migcom_sha256"] = sha(migcom)
            report["mach_server_headers"] = []
            for name in names:
                source = kernel / "osfmk/mach" / (name + ".defs")
                cpp_common = [v for v in common if v != "-std=gnu++17"]
                cpp = run([*cpp_common, "-D__MACH30__", "-E", "-x", "c", source], "mig-cpp-" + name)
                if cpp.returncode:
                    raise RuntimeError("Actual selected server defs preprocessing failed")
                h = mach_out / "mach" / (name + "_server.h")
                r = run([migcom, "-novouchers", "-server", "/dev/null", "-user", "/dev/null", "-header", "/dev/null", "-sheader", h], "mig-server-" + name, cpp.stdout)
                if r.returncode or not h.is_file():
                    raise RuntimeError("Actual selected server header generation failed")
                report["mach_server_headers"].append({"name": name, "source_sha256": sha(source), "header_sha256": sha(h)})
            common += ["-I", mach_out]
        probe = out / "selected-rpc.cpp"
        probe.write_text('#include <IOKit/IOReturn.h>\n#include <IOKit/IORPC.h>\nstatic_assert(sizeof(IORPC)==24);\nstatic_assert(__builtin_offsetof(IORPC,message)==0);\nstatic_assert(__builtin_offsetof(IORPC,reply)==8);\nstatic_assert(__builtin_offsetof(IORPC,sendSize)==16);\nstatic_assert(__builtin_offsetof(IORPC,replySize)==20);\nextern "C" unsigned s24_rpc_bytes(void){return sizeof(IORPC);}\n')
        obj = out / "selected-rpc.o"
        good = run([*common, "-c", probe, "-o", obj], "selected-rpc-layout")
        if good.returncode == 0 and macho(obj)["filetype"] == 1:
            report["selected_rpc_layout"] = {"actual_arm64_object": True, "size": 24, "field_offsets": [0, 8, 16, 20], "object_sha256": sha(obj)}
        negative = out / "new-rpc-field.cpp"
        negative.write_text('#include <IOKit/IOReturn.h>\n#include <IOKit/IORPC.h>\nunsigned s24_new_field(void){return sizeof(((IORPC*)0)->kernelContent);}\n')
        r = run([*common, "-fsyntax-only", negative], "new-rpc-field")
        report["new_field_absent_in_selected_api"] = good.returncode == 0 and r.returncode != 0 and "kernelContent" in r.stderr

        generated = out / "generated/DriverKit"
        generated.mkdir(parents=True)
        parse_extra = []
        if args.setup_headers:
            setup = out / "setup-headers"
            (setup / "sys").mkdir(parents=True)
            tool_prefix = out / "availability-tool-prefix"
            script = tool_prefix / "usr/local/libexec/availability.pl"
            script.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "references/xnu-availability/availability.pl", script)
            script.chmod(0o755)
            for name, argv in [
                ("symbol_aliasing", ["/bin/bash", kernel / "bsd/sys/make_symbol_aliasing.sh", tool_prefix, setup / "sys/_symbol_aliasing.h"]),
                ("posix_availability", ["/bin/sh", kernel / "bsd/sys/make_posix_availability.sh", setup / "sys/_posix_availability.h"]),
            ]:
                if run(argv, "setup-" + name).returncode:
                    raise RuntimeError("Actual selected source setup-header generator failed")
            report["source_setup_headers_sha256"] = {str(p.relative_to(setup)): sha(p) for p in sorted(setup.rglob("*.h"))}
            report["availability_tool_prefix_is_sdk"] = False
            report["availability_script_sha256"] = sha(script)
            report["host_script_interpreters"] = {n: sha(Path(n)) for n in ["/bin/bash", "/bin/sh", "/usr/bin/perl"]}
            dirs.insert(0, setup)
            common += ["-I", setup]
        if args.compiler_headers:
            compiler_resource = prefix / "lib/clang/19/include"
            if not (compiler_resource / "stdint.h").is_file():
                raise ValueError("Matching installed compiler resource headers are absent")
            report["compiler_resource_headers_sha256"] = {
                str(p.relative_to(compiler_resource)): sha(p) for p in sorted(compiler_resource.rglob("*.h"))}
            parse_extra = ["-ffreestanding", "-isystem", compiler_resource]
        definitions = sorted((kernel / "iokit/DriverKit").glob("*.iig"))
        if len(definitions) != 17:
            raise ValueError("Actual selected interface inventory differs")
        for source in definitions:
            h, impl = generated / (source.stem + ".h"), generated / (source.stem + ".iig.cpp")
            r = run([tool, "--def", source, "--header", h, "--impl", impl, "--framework-name", "DriverKit", "--",
                     "-x", "c++", "-std=gnu++17", "-D__IIG=1", "-DDRIVERKIT_PRIVATE=1", "-DPRIVATE_WIFI_ONLY=1",
                     "-target", "arm64-apple-ios16.5", "-nostdinc", *[a for d in dirs for a in ["-I", d]], *parse_extra], "selected-" + source.stem)
            report["selected_interfaces"].append({"name": source.stem, "source_sha256": sha(source), "exit_code": r.returncode,
                "header_sha256": sha(h) if h.is_file() else None, "implementation_sha256": sha(impl) if impl.is_file() else None})
        if args.compile_generated:
            report["generated_compiles"] = []
            for entry in report["selected_interfaces"]:
                if entry["exit_code"]:
                    continue
                name = entry["name"]
                obj = out / (name + ".o")
                r = run([*common, "-I", generated.parent, "-include", "IOKit/IOReturn.h",
                         "-include", "IOKit/IORPC.h", "-include", "DriverKit/" + name + ".h",
                         "-c", generated / (name + ".iig.cpp"), "-o", obj], "compile-" + name)
                report["generated_compiles"].append({"name": name, "exit_code": r.returncode,
                    "actual_arm64_object": r.returncode == 0 and macho(obj)["filetype"] == 1,
                    "object_sha256": sha(obj) if obj.is_file() else None})
        if (generated / "IOService.h").is_file():
            actual = (generated / "IOService.h").read_text()
            report["generated_id_observations"] = []
            for name, expected in observed["io_service_method_ids"].items():
                match = re.search(r"#define\s+IOService_" + name + r"_ID\s+(0x[0-9a-fA-F]+)ULL", actual)
                value = match.group(1).lower() if match else None
                report["generated_id_observations"].append({"method": name, "generated": value,
                    "matches_cross_version_observation": value == expected, "selected_version_oracle": False})
        if args.legacy_rpc_port and args.compile_generated:
            probe = out / "generated-rpc-layout.cpp"
            probe.write_text('#include <DriverKit/OSObject.iig.cpp>\nstatic_assert(sizeof(OSObject_CopyDispatchQueue_Invocation)==sizeof(IORPC));\nstatic_assert(sizeof(OSObject_SetDispatchQueue_Invocation)==sizeof(IORPC));\nstatic_assert(__builtin_offsetof(OSObject_CopyDispatchQueue_Invocation,sendSize)==__builtin_offsetof(IORPC,sendSize));\nstatic_assert(__builtin_offsetof(OSObject_CopyDispatchQueue_Invocation,replySize)==__builtin_offsetof(IORPC,replySize));\nstatic_assert(__builtin_offsetof(OSObject_CopyDispatchQueue_Msg_With_Content,content)==sizeof(IORPCMessageMach)+sizeof(mach_msg_port_descriptor_t));\n')
            obj = out / "generated-rpc-layout.o"
            r = run([*common, "-I", generated.parent, "-include", "IOKit/IOReturn.h", "-include", "IOKit/IORPC.h",
                     "-include", "DriverKit/OSObject.h", "-c", probe, "-o", obj], "generated-rpc-layout")
            report["generated_layout_probe"] = {"exit_code": r.returncode, "actual_arm64_object": r.returncode == 0 and macho(obj)["filetype"] == 1,
                "object_sha256": sha(obj) if obj.is_file() else None, "selected_apple_abi_qualified": False}
        if args.host_clang:
            fixture = ROOT / ("fixtures/public/xnu-iig-abi/copy-dispatch-guard-runtime.cpp" if args.host_guard_pages else "fixtures/public/xnu-iig-abi/copy-dispatch-runtime.cpp")
            binary = out / "copy-dispatch-runtime"
            report["host_clang"] = {"path": str(args.host_clang), "sha256": sha(args.host_clang)}
            run([args.host_clang, "--version"], "host-runtime-compiler")
            host_dirs = list(dirs)
            host_defines = ["-DTARGET_CPU_X86_64=1", "-DTARGET_OS_UNIX=1", "-DTARGET_OS_MAC=0"]
            if args.host_linux_port:
                full_header = out / "host-target-header"
                full_header.mkdir()
                shutil.copyfile(target_header, full_header / "TargetConditionals.h")
                patch = ROOT / "patches/iig-abi/0003-host-linux-target-header.patch"
                if run(["git", "-C", full_header, "apply", "--check", patch], "host-header-patch-check").returncode or run(["git", "-C", full_header, "apply", patch], "host-header-patch").returncode:
                    raise RuntimeError("Full licensed host target header patch failed")
                host_dirs.insert(0, full_header)
                host_defines = []
                report["host_header_patch_sha256"] = sha(patch)
                report["host_full_target_header_sha256"] = sha(full_header / "TargetConditionals.h")
            host_flags = ["-target", "x86_64-unknown-linux-gnu", "-ffreestanding", "-nostdinc", "-std=gnu++17",
                          "-fblocks", *host_defines,
                          "-DKERNEL=1", "-DKERNEL_PRIVATE=1", "-DPRIVATE=1", "-DDRIVERKIT_PRIVATE=1",
                          "-I", generated.parent, *[a for d in host_dirs for a in ["-I", d]],
                          "-I", kernel / "osfmk/libsa", "-include", "IOKit/IOReturn.h", "-include", "IOKit/IORPC.h",
                          "-include", "DriverKit/OSObject.h", "-ffunction-sections", "-fdata-sections",
                          "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-O1", "-g"]
            if args.host_linux_port:
                profile = out / "host-profile.hpp"
                profile.write_text('#include <TargetConditionals.h>\nstatic_assert(TARGET_CPU_X86_64 && TARGET_OS_UNIX && TARGET_OS_LINUX && TARGET_RT_64_BIT);\nstatic_assert(!TARGET_OS_MAC && !TARGET_OS_IOS && !TARGET_RT_MAC_MACHO);\n')
                obj = out / "host-runtime.o"
                if args.host_guard_pages:
                    host_flags = [v for v in host_flags if v not in ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-ffreestanding"]]
                    host_flags += ["-fhosted"]
                    sanitizer_flags = []
                    helper = ROOT / "fixtures/public/xnu-iig-abi/guard-page-host.cpp"
                    helper_obj = out / "host-guard-page.o"
                    if run([args.cxx, "-std=c++17", "-c", helper, "-o", helper_obj], "host-guard-page-compile").returncode:
                        raise RuntimeError("Real Linux guard-page helper compilation failed")
                    report["host_guard_page_helper_sha256"] = sha(helper)
                    report["host_runtime_sanitizers_used"] = False
                else:
                    sanitizer_flags = ["-fno-sanitize=function"]
                r = run([args.host_clang, *host_flags, *sanitizer_flags, "-include", profile, "-c", fixture, "-o", obj], "host-runtime-compile")
                if r.returncode == 0:
                    link_extra = [helper_obj] if args.host_guard_pages else ["-fsanitize=address,undefined"]
                    r = run([args.cxx, "-Wl,--gc-sections", obj, *link_extra, "-o", binary], "host-runtime-link")
                report["host_sanitizer_function_check"] = False
                report["host_sanitizer_function_check_limit"] = "Clang-specific function sanitizer excluded for explicit GNU runtime link; no Apple ABI equivalence implied"
            else:
                r = run([args.host_clang, *host_flags, "-Wl,--gc-sections", fixture, "-o", binary], "host-runtime-build")
            report["host_runtime"] = {"fixture_sha256": sha(fixture), "build_exit_code": r.returncode,
                                      "architecture": "host-x86_64", "actual_arm64_execution": False, "cases": []}
            if r.returncode == 0:
                report["host_runtime"]["binary_sha256"] = sha(binary)
                for mode in "gsrdonetzuf":
                    r = run([binary, mode], "host-runtime-" + mode)
                    report["host_runtime"]["cases"].append({"mode": mode, "exit_code": r.returncode, "passed": r.returncode == 0})
        checks = [all(x["exit_code"] == 0 for x in report["selected_interfaces"]),
                  all(x["selection_correct"] for x in report["conditional_cases"]),
                  all(x["matches_observed"] for x in report["hash_observations"]),
                  bool(report.get("selected_rpc_layout")), report["new_field_absent_in_selected_api"]]
        if args.compile_generated:
            checks.append(len(report["generated_compiles"]) == 17 and all(x["actual_arm64_object"] for x in report["generated_compiles"]))
        if args.host_clang:
            checks.append(len(report["host_runtime"]["cases"]) == 11 and all(x["passed"] for x in report["host_runtime"]["cases"]))
        if report.get("generated_id_observations"):
            checks.append(len(report["generated_id_observations"]) == 8 and all(x["matches_cross_version_observation"] for x in report["generated_id_observations"]))
        if args.legacy_rpc_port and args.compile_generated:
            checks.append(report["generated_layout_probe"]["actual_arm64_object"])
        report.update(outcome="inconclusive" if all(checks) else "fail",
                      summary="Actual new candidate/hash/parser/selected public RPC layout audit retained; complete selected Apple ABI remains unqualified")
    except Exception as error:
        report.update(outcome="fail", error=str(error))
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "conditional_cases": report["conditional_cases"],
                      "selected_interfaces": len(report["selected_interfaces"]), "selected_apple_iig_abi_qualified": False}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
