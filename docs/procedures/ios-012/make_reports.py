#!/usr/bin/env python3
"""IOS-012: run tools/ios/macho_audit.py on the unpacked iOS 16.5 userland and write the sanitized, committable report.

Inputs stay under artifacts/ (gitignored).  The report holds counts, hashes, library paths that are *missing*, system-call numbers
with the names of the project's open kernel tables, and the names of the sysctls / environment variables the programs read.  It
holds no Apple code and no file contents.  Static analysis only: nothing here ran on the phone or in any emulator.

usage: python3 -I docs/procedures/ios-012/make_reports.py OUT.json [--unpack DIR] [--kernel DIR]
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/ios/macho_audit.py"
PROGRAMS = ["usr/lib/dyld", "sbin/launchd", "usr/libexec/xpcproxy", "usr/libexec/amfid", "usr/libexec/backboardd",
            "System/Library/CoreServices/SpringBoard.app/SpringBoard"]
KERNEL_FILES = ["bsd/kern/syscalls.master", "osfmk/kern/syscall_sw.c", "config/MASTER", "config/MASTER.arm64", "config/MASTER.arm64.e1s"]
# (sysctl, file in the kernel tree, regex that must occur in it).  Guards were read by hand: see CONDITIONAL.
SYSCTLS = [
    ("kern.bootargs", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*bootargs"),
    ("kern.bootobjectspath", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*bootobjectspath"),
    ("kern.dyld_flags", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*dyld_flags"),
    ("kern.initproc_spawned", "bsd/kern/kern_exit.c", r"OID_AUTO,\s*initproc_spawned"),
    ("kern.minimalboot", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*minimalboot"),
    ("kern.osproductversion", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*osproductversion"),
    ("kern.osreleasetype", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*osreleasetype"),
    ("kern.roots_installed", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*roots_installed"),
    ("kern.syscall_rejection_masks", "bsd/kern/kern_debug.c", r"OID_AUTO,\s*syscall_rejection_masks"),
    ("kern.willshutdown", "iokit/Kernel/IOPMrootDomain.cpp", r"OID_AUTO,\s*willshutdown"),
    ("kern.willuserspacereboot", "libkern/c++/OSKext.cpp", r"OID_AUTO,\s*willuserspacereboot"),
    ("kern.workload_config", "bsd/kern/kern_sysctl.c", r"OID_AUTO,\s*workload_config"),
    ("hw.osenvironment", "bsd/kern/kern_mib.c", r"osenvironment"),
    ("hw.target", "bsd/kern/kern_mib.c", r"HW_TARGET, target"),
    ("hw.targettype", "iokit/Kernel/IOPMrootDomain.cpp", r"OID_AUTO,\s*targettype"),
    ("vm.footprint_suspend", "bsd/vm/vm_unix.c", r"footprint_suspend"),
    ("vm.shared_region_pivot", "bsd/vm/vm_unix.c", r"OID_AUTO,\s*shared_region_pivot"),
]
CONDITIONAL = {
    "kern.syscall_rejection_masks": "declared under #if CONFIG_DEBUG_SYSCALL_REJECTION; that option is OFF in DEVELOPMENT of MASTER.arm64.e1s, "
                                    "so this sysctl does not exist in the project's kernel configuration",
    "vm.footprint_suspend": "declared under #if __arm64__ && (DEVELOPMENT || DEBUG); present in the DEVELOPMENT configuration",
    "vm.shared_region_pivot": "declared without a guard; its handler returns EPERM unless the caller is initproc (launchd)",
}
SYSCTL_RE = r"^(kern|hw|vm|machdep|security)\.[a-z_]+$"
CACHE_IMAGES = ["/usr/lib/system/libsystem_kernel.dylib", "/usr/lib/system/libsystem_platform.dylib", "/usr/lib/system/libsystem_c.dylib",
                "/usr/lib/system/libdyld.dylib", "/usr/lib/system/libsystem_pthread.dylib", "/usr/lib/system/libdispatch.dylib",
                "/usr/lib/libobjc.A.dylib", "/usr/lib/system/libsystem_malloc.dylib", "/usr/lib/system/libxpc.dylib",
                "/usr/lib/libsandbox.1.dylib", "/usr/lib/libc++.1.dylib", "/usr/lib/libSystem.B.dylib",
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
                "/System/Library/Frameworks/Foundation.framework/Foundation"]
# Read by hand from a disassembly of the extracted dyld (Android NDK llvm-objdump 19.0.1, used only as a viewer; the file is
# local, under artifacts/).  Addresses are dyld __text virtual addresses.  The counts quoted come from the tool's own scans.
DYLD_HAND_READ = [
    {"where": "dyld4::APIs::dlopen_from, vm 0x7980-0x7a1c and 0x7bb0 onwards (symbol-table label; the cold-path calls at 0x7d30-0x7d38 belong to it)",
     "reads": "a byte at offset 0x21 of an allocator object reached through offset 0x60 of the function's receiver; when it is non-zero "
              "dyld reads the commpage byte at +0x10c, jumps to a `brk #1` (0x7d3c) if it is 0, or if (byte & 0xfe) != 2; then "
              "`mrs x8, S3_6_C15_C1_5`, loads the commpage u64 at +0xd0, `msr S3_6_C15_C1_5` with it, `isb`, loads +0xd0 again, "
              "`mrs` again and `brk`s if the two differ.  The twin sequence at 0x7bb0 uses +0xd8.",
     "when_the_byte_is_zero": "the same function takes the branch at 0x7980 to 0x7a20 and uses lsl::MemoryManager::lockGuard and "
                              "mprotect-style write protection (MemoryManager::writeProtect issues ___mprotect with PROT_READ=1 and "
                              "PROT_READ|PROT_WRITE=3)",
     "not_established": "where the allocator byte at +0x21 is set to non-zero (no strb of a non-zero constant to a +0x21 field was "
                        "found in the allocator code; the origin may be a wider store); nothing here says which path an S24 run takes"},
    {"where": "dyld4::SyscallDelegate::dyldCommPageFlags / setDyldCommPageFlags, vm 0x30260-0x302a4",
     "reads": "the commpage u64 at +0x160 (dyld_system_flags) and writes it through sysctlbyname(\"kern.dyld_flags\", ..., 8)",
     "ties_to": "the project kernel declares _COMM_PAGE_DYLD_FLAGS at +0x160 and the sysctl kern.dyld_flags (see sysctl_source_review)"},
]
KERNEL_SIDE = [
    {"item": "commpage +0x090 USER_TIMEBASE selects how libsystem_kernel and dyld read the clock",
     "file": "osfmk/arm64/machine_routines.c", "regex": r"return USER_TIMEBASE_NOSPEC_APPLE;",
     "finding": "user_timebase_type() returns USER_TIMEBASE_NOSPEC_APPLE (3) only when HAS_ACNTVCT is defined; userland reads the "
                "Apple register S3_4_C15_C10_6 (2 mrs in libsystem_kernel, 2 in dyld) for that value"},
]
DYLD_FILES = [r"^DYLD_[A-Z_]+$", r"^XPC_USERSPACE_[A-Z]+$", r"^/System/(Volumes/Preboot/)?Cryptexes[/A-Za-z]*$", r"^/System/Library/Caches/com\.apple\.dyld/?",
              r"trustcache$", r"^cryptex1(/current)?$", r"^ignition_[a-z_]+$", r"dylib cache directory present; not overriding",
              r"^No service cache", r"unsecure_cache", r"(?i)handshake"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def tool(*argv):
    r = subprocess.run([sys.executable, "-I", str(TOOL), *map(str, argv)], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        sys.exit("macho_audit failed (%d): %s" % (r.returncode, r.stderr[-800:]))
    return json.loads(r.stdout)


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    out_path = Path(argv[0])
    unpack = Path(argv[argv.index("--unpack") + 1]) if "--unpack" in argv else ROOT / "artifacts/ios-root/recipe/sysimage"
    kernel = Path(argv[argv.index("--kernel") + 1]) if "--kernel" in argv else ROOT / "artifacts/xnu-prepare/patch-session2/xnu"
    rootfs = unpack / "rootfs"
    cache_dir = next(unpack.glob("*/dyld_shared_cache_arm64")).parent
    cache = cache_dir / "dyld_shared_cache_arm64"
    progs = [rootfs / p for p in PROGRAMS]

    closure = tool("closure", *progs, "--cache", cache)
    kcmp = tool("syscalls", "--cache", cache, "--master", kernel / KERNEL_FILES[0], "--traps", kernel / KERNEL_FILES[1],
                "--config-dir", kernel / "config")
    pcmp = tool("program-syscalls", *progs, "--master", kernel / KERNEL_FILES[0], "--traps", kernel / KERNEL_FILES[1],
                "--config-dir", kernel / "config")
    match_args = [a for pat in [SYSCTL_RE, *DYLD_FILES] for a in ("--match", pat)]
    strings = {name: tool("cstrings", rootfs / path, *match_args) for name, path in (("dyld", PROGRAMS[0]), ("launchd", PROGRAMS[1]))}
    img_args = [a for i in CACHE_IMAGES for a in ("--image", i)]
    prog_args = [a for q in progs for a in ("--program", q)]
    commpage = tool("commpage", "--cache", cache, *img_args, *prog_args, "--header", kernel / "osfmk/arm/cpu_capabilities.h")
    sysregs = tool("sysregs", "--cache", cache, *img_args, *prog_args)
    acntvct_defs = sorted(str(f.relative_to(kernel)) for f in kernel.rglob("*.h")
                          if re.search(r"^#\s*define\s+HAS_ACNTVCT\b", f.read_text(errors="replace"), re.M))

    report = {
        "scope": "static analysis of files on the host (source-review / host-test); nothing here ran on the S24 or in any emulator",
        "inputs": {
            "programs": {p: {"bytes": (rootfs / p).stat().st_size, "sha256": sha256(rootfs / p)} for p in PROGRAMS},
            "dyld_shared_cache": {"main_file_sha256": sha256(cache), "files": {f.name: f.stat().st_size for f in sorted(cache_dir.iterdir())
                                                                              if f.name.startswith("dyld_shared_cache_arm64")}},
            "kernel_tree_files_sha256": {f: sha256(kernel / f) for f in KERNEL_FILES},
            "tool_sha256": sha256(TOOL), "tests_sha256": sha256(ROOT / "tests/test_macho_audit.py"),
        },
        "cache": closure["cache"],
        "programs": {},
        "libsystem_kernel_vs_project_kernel": {
            "kernel_tables": kcmp["kernel_tables"],
            "svc_total": kcmp["svc_80_total"], "svc_with_x16_immediate": kcmp["svc_with_x16_immediate"],
            "distinct_bsd_numbers": kcmp["distinct_bsd_numbers"], "distinct_mach_traps": kcmp["distinct_mach_traps"],
            "name_match": kcmp["comparison"]["name_match"],
            "number_absent_in_kernel_table": kcmp["comparison"]["number_absent_in_kernel_table"],
            "name_differs": kcmp["comparison"]["name_differs"],
            "kernel_entry_depends_on_unresolved_option": kcmp["comparison"]["kernel_entry_depends_on_unresolved_option"],
            "kernel_entry_is_nosys": [{"number": r["number"], "stub": (r["stub_names"] or ["(no export)"])[0], "kernel": r["kernel"],
                                      "guard_state": r["kernel_status"]} for r in sorted(kcmp["comparison"]["kernel_entry_is_nosys"], key=lambda r: r["number"])],
            "stubs_without_export_name": [{"number": r["number"], "kernel": r["kernel"]} for r in kcmp["comparison"]["no_export_name_at_stub"]],
        },
        "dyld_direct_system_calls": {},
        "sysctl_source_review": [],
        "interface_strings": {},
        "commpage_references": {
            "method": "heuristic scan of __TEXT,__text for constants that form addresses inside the 64-bit commpage (rw page "
                      "0xfffffc000, ro page 0xfffff4000); a miss proves nothing, a hit shows an access shape, not its semantics",
            "kernel_header": "osfmk/arm/cpu_capabilities.h", "named_fields_in_header": commpage["header_fields"],
            "images": {k.split("rootfs/")[-1]: v for k, v in commpage["images"].items()},
        },
        "system_registers": {
            "method": "every mrs/msr (register form) in __TEXT,__text; 'implementation_defined' = op0 3 with CRn 11 or 15 (ARM ARM "
                      "reserves these for the implementer).  Whether an access executes is not decided here.",
            "images_with_implementation_defined_accesses": {
                k.split("rootfs/")[-1]: [r for r in v["registers"] if r["implementation_defined"]]
                for k, v in sysregs["images"].items() if any(r["implementation_defined"] for r in v["registers"])},
            "images_without": sorted(k.split("rootfs/")[-1] for k, v in sysregs["images"].items()
                                     if not any(r["implementation_defined"] for r in v["registers"])),
        },
        "dyld_hand_read_observations": DYLD_HAND_READ,
        "kernel_side_checks": [dict(k, regex_found_in_file=re.search(k["regex"], (kernel / k["file"]).read_text(errors="replace")) is not None,
                                    HAS_ACNTVCT_defined_in=acntvct_defs) for k in KERNEL_SIDE],
    }
    for label, info in closure["programs"].items():
        short = label.split("rootfs/")[-1]
        cl = info.get("closure", {})
        report["programs"][short] = {
            "cputype": info["cputype"], "cpusubtype": info["cpusubtype"], "filetype": info["filetype"], "build_version": info["build_version"],
            "dyld_fixups": info["dyld_fixups"], "entry": info["entry"], "dyld_linker": info["dyld_linker"],
            "direct_libraries": len(info["libraries"]), "direct_libraries_not_in_cache": info["libraries_not_in_cache"],
            "closure_images": cl.get("images"), "closure_missing": {n: {"required": v["required"], "first_referrer": v["first_referrer"]}
                                                                     for n, v in cl.get("missing", {}).items()},
            "closure_missing_required": cl.get("missing_required"),
        }
    for label, info in pcmp["programs"].items():
        short = label.split("rootfs/")[-1]
        nums = info["numbers"]
        bad = [n for n in nums if n["kernel"] in ("(no entry)", "nosys", "enosys") and n["number"] != 0
               or n["status"].startswith(("unresolved", "absent"))]
        report["dyld_direct_system_calls"][short] = {
            "svc_80_total": info["svc_80_total"], "distinct_numbers": len(nums), "config": pcmp["config"],
            "numbers_not_enabled_in_project_kernel": bad,
            "bsd": [{"number": n["number"], "kernel": n["kernel"]} for n in nums if n["number"] >= 0],
            "mach_traps": [{"trap": -n["number"], "kernel": n["kernel"]} for n in nums if n["number"] < 0],
        } if info["svc_80_total"] else {"svc_80_total": 0}
    for name, rel, rx in SYSCTLS:
        text = (kernel / rel).read_text(errors="replace")
        report["sysctl_source_review"].append({"sysctl": name, "file": rel, "declaration_found": re.search(rx, text) is not None,
                                               "condition": CONDITIONAL.get(name, "none found when read by hand")})
    for name, res in strings.items():
        report["interface_strings"][name] = {"cstring_count": res["cstring_count"],
                                             "matches": {pat: lst for pat, lst in res["matches"].items() if lst},
                                             "patterns_without_a_match": [pat for pat, lst in res["matches"].items() if not lst]}
        if name == "dyld":
            ign = tool("cstrings", rootfs / PROGRAMS[0], "--match", r"libignition")
            report["interface_strings"][name]["libignition_strings"] = len(next(iter(ign["matches"].values())))
    out_path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
