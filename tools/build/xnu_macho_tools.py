#!/usr/bin/env python3
"""Build pinned host ld64/TAPI/runtime and check actual Mach-O semantics; no SDK/device."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sources

PINS = {"xnu-cctools": "904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb",
        "xnu-tapi": "fa9443738c1a18accef4244732ec6d6ee97a8133",
        "xnu-host-dispatch": "137b6cf3060eae87d9b367c263619c2eca5d3aac"}
RUNTIME_PATCH = ROOT / "patches/build-tools/0002-libdispatch-atomic-header-linkage.patch"
ATOMIC_PATCH = ROOT / "patches/build-tools/0003-host-clang-c11-atomic-header.patch"


def tree_hashes(directory):
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() and not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Prefix/source symlink escapes its directory")
        if path.is_file():
            hashes[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def macho(path):
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError("Truncated Mach-O header")
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from("<IiiIIIII", data)
    if magic != 0xFEEDFACF or cpu != 0x100000C or size > len(data) - 32 or count > size // 8:
        raise ValueError("Expected bounded thin arm64 Mach-O commands")
    at = 32
    result = {"filetype": kind, "flags": flags, "segments": [], "dylibs": [], "commands": []}
    for _ in range(count):
        if at + 8 > 32 + size:
            raise ValueError("Truncated load command")
        cmd, length = struct.unpack_from("<II", data, at)
        if length < 8 or at + length > 32 + size:
            raise ValueError("Invalid Mach-O command extent")
        result["commands"].append(cmd)
        if cmd == 0x19:
            if length < 72:
                raise ValueError("Truncated segment command")
            name, addr, vmsize, offset, filesize, maxprot, initprot, sections, segflags = struct.unpack_from("<16sQQQQiiII", data, at + 8)
            if sections > (length - 72) // 80 or filesize > len(data) or offset > len(data) - filesize:
                raise ValueError("Invalid segment/section extent")
            result["segments"].append({"name": name.split(b"\0")[0].decode("ascii"), "vmaddr": addr,
                                       "vmsize": vmsize, "fileoff": offset, "filesize": filesize,
                                       "maxprot": maxprot, "initprot": initprot})
        elif cmd in (0xC, 0x18 | 0x80000000, 0x1F | 0x80000000):
            if length < 24:
                raise ValueError("Truncated dylib command")
            string_at = struct.unpack_from("<I", data, at + 8)[0]
            if not 24 <= string_at < length:
                raise ValueError("Invalid dylib name offset")
            result["dylibs"].append(data[at + string_at:at + length].split(b"\0")[0].decode("utf-8"))
        at += length
    if at != 32 + size:
        raise ValueError("Load-command count/size disagree")
    return result


def require_kernel_layout(actual):
    if actual["filetype"] != 2 or actual["flags"] & 4 or 0xE in actual["commands"]:
        raise ValueError("Static executable semantics missing; dynamic Mach-O is not a kernel layout pass")
    if not actual["flags"] & 0x200000:
        raise ValueError("Selected kernel PIE flag is missing")
    segments = actual["segments"]
    names = [s["name"] for s in segments]
    # ld64 adds generated LINKEDIT after sorting the input sections. XNU's
    # arm_vm_init documents this tail layout; it is not a literal input order.
    wanted = ["__TEXT", "__DATA_CONST", "__TEXT_EXEC", "__DATA", "__LINKEDIT"]
    if names != wanted:
        raise ValueError("Requested segment ordering was not honored")
    for left, right in zip(segments, segments[1:]):
        if left["vmaddr"] + left["vmsize"] > right["vmaddr"]:
            raise ValueError("Fixture segments overlap or VM order differs")
    by_name = {s["name"]: s for s in segments}
    if by_name["__TEXT"]["vmaddr"] != 0xFFFFFFF007004000 or by_name["__TEXT"]["fileoff"] != 0:
        raise ValueError("Requested high kernel image base was not honored")
    for name, protection in [("__TEXT", 1), ("__DATA_CONST", 1), ("__TEXT_EXEC", 5)]:
        if (by_name[name]["maxprot"], by_name[name]["initprot"]) != (protection, protection):
            raise ValueError("Requested segment protection was not honored: " + name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--clang-bin", type=Path, required=True)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--reuse-dependencies", type=Path, help="Explicit prior successful, hash-verified dependency run; never modified")
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        raise ValueError("Invalid unique run name")
    if not 1 <= args.jobs <= 4:
        raise ValueError("Use1..4 build jobs")
    clangdir = args.clang_bin.resolve()
    if not args.clang_bin.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./+-]+", str(clangdir)):
        raise ValueError("Use an explicit installed LLVM bin path")
    for name in ["clang", "clang++", "llvm-readobj"]:
        if not (clangdir / name).is_file() or not os.access(clangdir / name, os.X_OK):
            raise ValueError("Missing installed LLVM executable: " + name)
    entries = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    provenance = []
    for identifier, pin in PINS.items():
        entry = next(e for e in entries if e["id"] == identifier)
        if entry["revision"] != pin:
            raise ValueError("Recipe requires its reviewed exact source pin")
        provenance.append(sources.verify(ROOT, entry))
    dependency_prefix = None
    if args.reuse_dependencies:
        previous = args.reuse_dependencies.resolve()
        if not previous.is_relative_to(ROOT / "artifacts/xnu-macho-tools"):
            raise ValueError("Reuse only an explicit project dependency run")
        old = json.loads((previous / "report.json").read_text())
        if (old.get("dependency_outcome") != "pass" or old.get("source_pins") != PINS or
                old.get("runtime_patch_sha256") != hashlib.sha256(RUNTIME_PATCH.read_bytes()).hexdigest()):
            raise ValueError("Previous dependency result or source pins do not match")
        if old.get("atomic_patch_sha256") != hashlib.sha256(ATOMIC_PATCH.read_bytes()).hexdigest():
            raise ValueError("Previous dependency atomic-header profile differs")
        dependency_prefix = (ROOT / old["dependency_prefix"]).resolve()
        if not dependency_prefix.is_relative_to(ROOT / "artifacts/xnu-macho-tools") or dependency_prefix.name != "dependencies":
            raise ValueError("Recorded dependency prefix escapes the project build namespace")
        if tree_hashes(dependency_prefix) != old.get("dependency_files_sha256"):
            raise ValueError("Dependency prefix changed since the recorded build")
    out = ROOT / "artifacts/xnu-macho-tools" / args.run
    if out.resolve() != out:
        raise ValueError("Run directory cannot use symlinks")
    out.mkdir(parents=True, exist_ok=False)
    (out / "builder.py").write_bytes(Path(__file__).read_bytes())
    prefix = out / "prefix"
    prefix.mkdir()
    if dependency_prefix is None:
        dependency_prefix = out / "dependencies"
        dependency_prefix.mkdir()
    logs = out / "logs"
    logs.mkdir()
    report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commands": [],
              "source_pins": PINS, "provenance": provenance, "sdk_used": False, "device_executed": False,
              "global_install": False, "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "runtime_patch_sha256": hashlib.sha256(RUNTIME_PATCH.read_bytes()).hexdigest(),
              "atomic_patch_sha256": hashlib.sha256(ATOMIC_PATCH.read_bytes()).hexdigest(),
              "prefix": str(prefix.relative_to(ROOT)), "dependency_prefix": str(dependency_prefix.relative_to(ROOT)),
              "coverage": {}, "limits": ["Owned Mach-O/runtime/text-stub fixtures only; no full XNU link or selected SDK ABI",
                                          "LTO/XAR disabled to match selected BUILD_LTO=0 kernel profile; bitcode packaging unqualified",
                                          "No kernel execution, generated RPC execution or native-device support"]}
    env = {**os.environ, "CC": str(clangdir / "clang"), "CXX": str(clangdir / "clang++"),
           "CFLAGS": "-O2 -g0 -std=gnu11", "CXXFLAGS": "-O2 -g0", "SDKROOT": "", "CONFIG_SITE": "/dev/null",
           "MAKEFLAGS": "", "LD_LIBRARY_PATH": str(dependency_prefix / "lib")}
    deadline = time.monotonic() + 1800

    def run(argv, cwd=out, expected=(0,), timeout=1200, semantic_link=False):
        index = len(report["commands"])
        record = {"argv": list(map(str, argv)), "cwd": str(cwd), "expected_exit_codes": list(expected)}
        report["commands"].append(record)
        stdout, stderr = logs / f"{index:02d}.stdout.txt", logs / f"{index:02d}.stderr.txt"
        print(json.dumps({"command": index, "program": record["argv"][0]}), flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Host build command budget exhausted")
        with stdout.open("w") as so, stderr.open("w") as se:
            child = subprocess.Popen(record["argv"], cwd=cwd, env=env, stdout=so, stderr=se, start_new_session=True)
            try:
                child.wait(timeout=min(timeout, remaining))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
                record.update(exit_code=child.returncode, timeout=True)
                raise RuntimeError("Owned host build exceeded its bounded command budget")
        record.update(exit_code=child.returncode, stdout=str(stdout.relative_to(ROOT)), stderr=str(stderr.relative_to(ROOT)))
        if child.returncode not in expected:
            raise RuntimeError(f"Command{index} exited{child.returncode}; see {stderr.relative_to(ROOT)}")
        text = stdout.read_text(errors="replace")
        errors = stderr.read_text(errors="replace")
        if semantic_link and any(s in errors.lower() for s in ["not yet implemented", "unimplemented", "ignored", "unknown option"]):
            raise RuntimeError("Linker ignored or did not implement requested behavior")
        return text, errors

    try:
        report["compiler"] = run([clangdir / "clang", "--version"])[0].splitlines()[0]
        source_roots = {}
        for identifier in PINS:
            source = ROOT / "references" / identifier
            if identifier != "xnu-cctools" and args.reuse_dependencies:
                continue
            destination = out / identifier
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"), symlinks=True)
            source_roots[identifier] = destination
        common = ["-GNinja", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=" + env["CC"],
                  "-DCMAKE_CXX_COMPILER=" + env["CXX"], "-DCMAKE_INSTALL_PREFIX=" + str(dependency_prefix),
                  "-DCMAKE_INSTALL_LIBDIR=lib", "-DFETCHCONTENT_FULLY_DISCONNECTED=ON"]
        fixture = out / "fixtures"
        fixture.mkdir()
        if not args.reuse_dependencies:
            # Use the pinned LLVM compiler's genuine C11 intrinsic header for
            # this host runtime only, rather than hosted C++ std::atomic APIs.
            atomic_include = out / "clang-c11"
            atomic_include.mkdir()
            atomic_source = source_roots["xnu-tapi"] / "src/clang/lib/Headers/stdatomic.h"
            report["atomic_header_source_sha256"] = hashlib.sha256(atomic_source.read_bytes()).hexdigest()
            shutil.copyfile(atomic_source, atomic_include / "stdatomic.h")
            run(["git", "-c", "core.hooksPath=/dev/null", "init", "--quiet"], cwd=atomic_include)
            run(["git", "-c", "core.hooksPath=/dev/null", "apply", "--check", ATOMIC_PATCH], cwd=atomic_include)
            run(["git", "-c", "core.hooksPath=/dev/null", "apply", ATOMIC_PATCH], cwd=atomic_include)
            atomic_args = ["-I" + str(atomic_include), "-DS24_HOST_C11_ATOMICS=1"]
            (fixture / "atomic-shared.h").write_text('#include <stdatomic.h>\n#include <stddef.h>\nstruct shared_atomic { atomic_long count; atomic_bool ready; atomic_uintptr_t token; };\n#ifdef __cplusplus\nextern "C" {\n#endif\nsize_t cpp_atomic_size(void);\nsize_t cpp_atomic_align(void);\nvoid cpp_atomic_update(struct shared_atomic *);\n#ifdef __cplusplus\n}\n#endif\n')
            (fixture / "atomic-cpp.cpp").write_text('#include "atomic-shared.h"\nsize_t cpp_atomic_size(void) { return sizeof(shared_atomic); }\nsize_t cpp_atomic_align(void) { return alignof(shared_atomic); }\nvoid cpp_atomic_update(shared_atomic *p) { atomic_fetch_add_explicit(&p->count,1,memory_order_acq_rel); atomic_store_explicit(&p->token,2400,memory_order_release); atomic_store_explicit(&p->ready,true,memory_order_release); }\n')
            (fixture / "atomic-c.c").write_text('#include "atomic-shared.h"\n#include <stdio.h>\nint main(void) { struct shared_atomic p; atomic_init(&p.count,0); atomic_init(&p.ready,0); atomic_init(&p.token,0); if(sizeof(p)!=cpp_atomic_size() || _Alignof(struct shared_atomic)!=cpp_atomic_align()) return 7; for(int i=0;i<32;i++) cpp_atomic_update(&p); if(atomic_load_explicit(&p.count,memory_order_acquire)!=32 || !atomic_load_explicit(&p.ready,memory_order_acquire) || atomic_load_explicit(&p.token,memory_order_acquire)!=2400) return 8; puts("s24-c-cpp-atomics-32"); return 0; }\n')
            run([clangdir / "clang++", "-std=c++20", *atomic_args, "-c", fixture / "atomic-cpp.cpp", "-o", fixture / "atomic-cpp.o"])
            run([clangdir / "clang", "-std=gnu11", *atomic_args, "-c", fixture / "atomic-c.c", "-o", fixture / "atomic-c.o"])
            run([clangdir / "clang++", fixture / "atomic-c.o", fixture / "atomic-cpp.o", "-o", fixture / "atomic-cross"])
            if run([fixture / "atomic-cross"], timeout=20)[0].strip() != "s24-c-cpp-atomics-32":
                raise RuntimeError("Actual C/C++ C11 atomic type/operation interoperability differs")
            report["coverage"]["host_atomic_interop"] = "actual C/C++ size/alignment,32 C++ updates observed by C with C11 intrinsic long/bool/pointer-width atomics"
            runtime_source = source_roots["xnu-host-dispatch"]
            run(["git", "-c", "core.hooksPath=/dev/null", "init", "--quiet"], cwd=runtime_source)
            run(["git", "-c", "core.hooksPath=/dev/null", "apply", "--check", RUNTIME_PATCH], cwd=runtime_source)
            run(["git", "-c", "core.hooksPath=/dev/null", "apply", RUNTIME_PATCH], cwd=runtime_source)
            runtime = out / "dispatch-build"
            run(["cmake", "-S", source_roots["xnu-host-dispatch"], "-B", runtime, *common,
                 "-DCMAKE_C_FLAGS=" + " ".join([env["CFLAGS"], *atomic_args]),
                 "-DCMAKE_CXX_FLAGS=" + " ".join([env["CXXFLAGS"], *atomic_args]),
                 "-DENABLE_SWIFT=OFF", "-DBUILD_TESTING=OFF"])
            run(["cmake", "--build", runtime, "--parallel", str(args.jobs)])
            run(["cmake", "--install", runtime])
            (fixture / "runtime.c").write_text('#include <dispatch/dispatch.h>\n#include <stdatomic.h>\n#include <stdio.h>\nstatic _Atomic int total;\nint main(void) { dispatch_once_t once=0; __block int calls=0; for(int i=0;i<8;i++) dispatch_once(&once, ^{ calls++; }); dispatch_apply(32, dispatch_get_global_queue(0,0), ^(size_t i){ atomic_fetch_add(&total,1); }); if(calls!=1 || total!=32) return 7; puts("s24-runtime-1-32"); return 0; }\n')
            run([clangdir / "clang", "-std=gnu11", "-fblocks", "-pthread", *atomic_args, "-I" + str(dependency_prefix / "include"),
                 fixture / "runtime.c", "-L" + str(dependency_prefix / "lib"), "-Wl,-rpath," + str(dependency_prefix / "lib"),
                 "-ldispatch", "-lBlocksRuntime", "-o", fixture / "runtime"])
            if run([fixture / "runtime"], timeout=20)[0].strip() != "s24-runtime-1-32":
                raise RuntimeError("Actual dispatch/BlocksRuntime behavior differs")
            report["coverage"]["host_runtime"] = "real dispatch_once and32 parallel callbacks with BlocksRuntime"
            tapi_build = out / "tapi-build"
            run(["cmake", "-S", source_roots["xnu-tapi"] / "src/llvm", "-B", tapi_build, *common,
                 "-DLLVM_ENABLE_PROJECTS=tapi;clang", "-DLLVM_INCLUDE_TESTS=OFF", "-DLLVM_INCLUDE_BENCHMARKS=OFF",
                 "-DLLVM_TARGETS_TO_BUILD=", "-DLLVM_ENABLE_TERMINFO=OFF", "-DTAPI_REPOSITORY_STRING=1600.0.11.8",
                 "-DTAPI_FULL_VERSION=1600.0.11.8"])
            run(["cmake", "--build", tapi_build, "--target", "clangBasic", "vt_gen", "--parallel", str(args.jobs)])
            run(["cmake", "--build", tapi_build, "--target", "libtapi", "--parallel", str(args.jobs)])
            run(["cmake", "--build", tapi_build, "--target", "install-libtapi", "install-tapi-headers", "--parallel", str(args.jobs)])
            notices = dependency_prefix / "share/licenses"
            notices.mkdir(parents=True, exist_ok=True)
            for identifier, names in {"xnu-host-dispatch": ["LICENSE"], "xnu-tapi": ["LICENSE.APPLE-LIBTAPI.txt", "LICENSE.LLVM.txt", "src/LICENSE.txt"]}.items():
                location = notices / identifier
                location.mkdir()
                for i, name in enumerate(names):
                    shutil.copyfile(source_roots[identifier] / name, location / (str(i) + "-" + Path(name).name))
            shutil.copyfile(atomic_include / "stdatomic.h", notices / "xnu-tapi/host-stdatomic.h")
            report["dependency_outcome"] = "pass"
            report["dependency_files_sha256"] = tree_hashes(dependency_prefix)
        else:
            report.update(dependency_outcome="pass", dependency_files_sha256=old["dependency_files_sha256"],
                          reused_dependency_report_sha256=hashlib.sha256((previous / "report.json").read_bytes()).hexdigest())
        source = source_roots["xnu-cctools"] / "cctools"
        build = out / "cctools-build"
        build.mkdir()
        run(["sh", source / "configure", "--prefix=" + str(prefix), "--target=aarch64-apple-darwin",
             "--disable-maintainer-mode", "--disable-lto-support", "--disable-xar-support",
             "--with-libdispatch=" + str(dependency_prefix), "--with-libblocksruntime=" + str(dependency_prefix),
             "--with-libtapi=" + str(dependency_prefix)], cwd=build)
        run(["make", "-j" + str(args.jobs)], cwd=build)
        run(["make", "install"], cwd=build)
        bindir = prefix / "bin"
        tool = lambda name: bindir / ("aarch64-apple-darwin-" + name)
        report["ld_version"] = run([tool("ld"), "-v"], expected=(0, 1))[1]
        code = fixture / "kernel-layout.c"
        code.write_text('__attribute__((section("__DATA_CONST,__const"))) const int s24_const = 2400;\nvolatile int s24_data=16;\nint s24_host_fixture(void) { return s24_const+s24_data; }\n')
        obj = fixture / "kernel-layout.o"
        run([clangdir / "clang", "-target", "arm64-apple-ios16.5", "-ffreestanding", "-fno-stack-protector", "-fno-pic",
             "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-c", code, "-o", obj])
        kernel = fixture / "kernel-layout"
        run([tool("ld"), "-arch", "arm64", "-platform_version", "ios", "16.5", "16.5", "-static", "-pie",
             "-image_base", "0xfffffff007004000", "-pagezero_size", "0", "-e", "_s24_host_fixture", "-rename_section", "__TEXT", "__text", "__TEXT_EXEC", "__text",
             "-segment_order", "__TEXT:__DATA_CONST:__LINKEDIT:__TEXT_EXEC:__DATA", "-segprot", "__TEXT", "r--", "r--",
             "-segprot", "__DATA_CONST", "r--", "r--", "-segprot", "__TEXT_EXEC", "r-x", "r-x", "-o", kernel, obj], semantic_link=True)
        actual = macho(kernel)
        require_kernel_layout(actual)
        report["kernel_layout"] = actual
        report["coverage"]["static_layout"] = "actual static arm64 Mach-O high base, segment order/renaming/protections; no kernel execution"
        run([tool("otool"), "-hv", kernel])
        symbols = run([tool("nm"), "-gj", obj])[0].splitlines()
        if "_s24_host_fixture" not in symbols or "_s24_data" not in symbols:
            raise RuntimeError("Real nm globals missing")
        (fixture / "members.txt").write_text(str(obj) + "\n")
        archive = fixture / "libfixture.a"
        run([tool("libtool"), "-static", "-csD", "-filelist", fixture / "members.txt", "-o", archive])
        if "_s24_host_fixture" not in run([tool("nm"), "-gj", archive])[0]:
            raise RuntimeError("Actual archive symbol table missing")
        edited = fixture / "edited.o"
        shutil.copyfile(obj, edited)
        (fixture / "keep.txt").write_text("_s24_host_fixture\n")
        run([tool("nmedit"), "-s", fixture / "keep.txt", edited])
        if run([tool("nm"), "-gj", edited])[0].strip() != "_s24_host_fixture":
            raise RuntimeError("Real nmedit export selection differs")
        report["coverage"]["macho_tools"] = "real nm globals/archive, libtool filelist archive, otool header, nmedit export selection"
        client = fixture / "stub-client.c"
        client.write_text("extern void s24_peer(void);\nvoid (*s24_peer_pointer)(void) = s24_peer;\n")
        run([clangdir / "clang", "-target", "arm64-apple-ios16.5", "-ffreestanding", "-c", client, "-o", fixture / "stub-client.o"])
        stub = "--- !tapi-tbd-v3\narchs: [ arm64 ]\nplatform: ios\ninstall-name: /lab/libpeer.dylib\ncurrent-version: 1.0\ncompatibility-version: 1.0\nexports:\n  - archs: [ arm64 ]\n    symbols: [ _s24_peer ]\n...\n"
        (fixture / "libpeer.tbd").write_text(stub)
        stub_link = [tool("ld"), "-arch", "arm64", "-platform_version", "ios", "16.5", "16.5", "-dylib", "-install_name", "/lab/client.dylib",
                     "-o", fixture / "stub-client.dylib", fixture / "stub-client.o", fixture / "libpeer.tbd"]
        run(stub_link, semantic_link=True)
        if "/lab/libpeer.dylib" not in macho(fixture / "stub-client.dylib")["dylibs"]:
            raise RuntimeError("Real text-stub dependency command missing")
        (fixture / "libmissing.tbd").write_text(stub.replace("_s24_peer", "_s24_unrelated"))
        negative = list(stub_link)
        negative[-1] = fixture / "libmissing.tbd"
        negative[negative.index("-o") + 1] = fixture / "missing.dylib"
        if "_s24_peer" not in run(negative, expected=(1,))[1]:
            raise RuntimeError("Text-stub negative case failed for an unrelated reason")
        report["coverage"]["tapi"] = "actual owned arm64 text-stub dependency link and missing-symbol rejection; no SDK stub consumed"
        notices = prefix / "share/licenses/cctools"
        notices.mkdir(parents=True)
        shutil.copyfile(source / "APPLE_LICENSE", notices / "APPLE_LICENSE")
        report["prefix_files_sha256"] = tree_hashes(prefix)
        report.update(outcome="pass", summary="Pinned real ld64/cctools and host dependencies build; actual static-layout, symbols, archives and owned text-stub fixtures pass")
    except Exception as error:
        report.update(outcome="fail", error=str(error), summary="Mach-O tool build/check retained its actual partial/failure result")
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["outcome", "summary", "coverage"]}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sources.SourceError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
