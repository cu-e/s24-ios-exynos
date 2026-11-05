#!/usr/bin/env python3
"""Qualify named AVF XNU source/profile inputs without building or booting XNU."""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

import source

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUTS = ROOT / "fixtures/public/avf-kernel-profile/inputs.json"
NATIVE_REPORT = "worktrees/krn-030-20261105/artifacts/kernel-runtime-link/native-session1/report.json"
NATIVE_GAPS = "worktrees/krn-024-20261105/artifacts/kernel-provider-link/acceptance-session1/remaining-export-inputs.json"
SELECTED = ["makedefs/MakeInc.def", "config/MASTER.arm64.bcm2837",
            "pexpert/pexpert/arm64/BCM2837.h", "pexpert/pexpert/arm64/board_config.h",
            "osfmk/arm/arm_init.c", "pexpert/arm/pe_init.c", "pexpert/arm/pe_serial.c",
            "bsd/miscfs/mockfs/mockfs_fsnode.c", "bsd/miscfs/mockfs/mockfs_vfsops.c",
            "bsd/miscfs/mockfs/mockfs_vnops.c", "osfmk/arm64/loader_return.c",
            "osfmk/arm64/psci_smp.c", "osfmk/arm64/psci_smp.h", "osfmk/arm64/gic_v3_irq.c"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2) + "\n")


class Review:
    def __init__(self, main, cache, out):
        self.main, self.cache, self.out = main, cache, out
        self.env = dict(os.environ) | source.GUARDS | {"PYTHONDONTWRITEBYTECODE": "1"}
        expected_supervisor = json.loads(DEFAULT_INPUTS.read_text())["accepted_readonly_inputs"]["tools/build/qemu_host.py"]["sha256"]
        if sha(main / "tools/build/qemu_host.py") != expected_supervisor:
            raise ValueError("Accepted supervisor changed before read-only reuse")
        spec = importlib.util.spec_from_file_location("avf_profile_supervisor", main / "tools/build/qemu_host.py")
        self.supervisor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.supervisor)
        self.report = {"kind": "source-review", "origin": "local-host", "outcome": "fail",
                       "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "commands": [], "facts": [], "negative_controls": [],
                       "full_build_executed": False, "compiler_executed": False,
                       "guest_executed": False, "device_executed": False,
                       "full_kernel_qualified": False, "native_exports_modified": False}

    def run(self, argv, label, cwd=None):
        record = {"argv": [str(x) for x in argv], "cwd": str(cwd or ROOT),
                  "environment_overrides": source.GUARDS | {"PYTHONDONTWRITEBYTECODE": "1"},
                  "timeout_seconds": 20, "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        self.report["commands"].append(record)
        start = time.monotonic()
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
        with (self.out / (label + ".log")).open("xb") as log:
            proc = subprocess.Popen(record["argv"], cwd=cwd or ROOT, env=self.env,
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=limits)
            peak = 0
            record["owned_session"] = proc.pid
            try:
                while proc.poll() is None:
                    sample = self.supervisor.sample(proc.pid)
                    own = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
                    peak = max(peak, own + sample["owned_tree_rss_bytes"])
                    if peak > 256 * 1024**2 or time.monotonic() - start > 20:
                        record["terminated"] = "resource-or-deadline"
                        self.supervisor.terminate(proc)
                        break
                    time.sleep(0.025)
                record["exit_code"] = proc.wait(timeout=2)
            finally:
                if any(p["state"] != "Z" for p in self.supervisor.sample(proc.pid)["owned_processes"]):
                    self.supervisor.terminate(proc)
                after = self.supervisor.sample(proc.pid)
                record.update(elapsed_seconds=round(time.monotonic() - start, 3),
                              peak_total_owned_rss_bytes=peak, after=after)
            if any(p["state"] != "Z" for p in after["owned_processes"]):
                raise RuntimeError("Owned session survived cleanup")
        record["log_sha256"] = sha(self.out / (label + ".log"))
        if record["exit_code"] or record.get("terminated"):
            raise ValueError("Failed bounded command " + label)
        return (self.out / (label + ".log")).read_text()

    def validate(self, manifest, changed=None):
        fixed = json.loads(DEFAULT_INPUTS.read_text())
        if set(manifest["source_files"]) != set(fixed["source_files"]):
            raise ValueError("Named source input set differs from selected profile")
        for name, item in manifest["source_files"].items():
            if item != fixed["source_files"][name]:
                raise ValueError("Selected source pin/blob metadata changed: " + name)
            if item["commit"] != source.REPOS[item["repo"]][0]:
                raise ValueError("Source commit differs from full selected pin")
            data = changed[name] if changed and name in changed else (self.cache / item["repo"] / item["path"]).read_bytes()
            if len(data) != item["size"] or source.digest(data) != item["sha256"]:
                raise ValueError("Source content/extent mismatch: " + name)
            if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != item["blob_id"]:
                raise ValueError("Source Git blob mismatch: " + name)
        if manifest["guest"] != fixed["guest"]:
            raise ValueError("Guest selection or unqualified readiness claim changed")
        if manifest["native"] != fixed["native"]:
            raise ValueError("Preserved native feature/export contract changed")
        if manifest["accepted_readonly_inputs"] != fixed["accepted_readonly_inputs"]:
            raise ValueError("Accepted component binding changed")

    def fact(self, name, path, marker, explanation):
        text = (self.cache / path).read_text()
        if marker not in text:
            raise ValueError("Source fact not established: " + name)
        self.report["facts"].append({"id": name, "input": path,
                                     "line": text[:text.index(marker)].count("\n") + 1,
                                     "marker": marker, "source_sha256": sha(self.cache / path),
                                     "establishes": explanation})

    def qualify(self):
        manifest = json.loads(DEFAULT_INPUTS.read_text())
        self.validate(manifest)
        self.report["manifest_sha256"] = sha(DEFAULT_INPUTS)
        self.report["commit"] = self.run(["git", "rev-parse", "HEAD"], "revision").strip()
        self.report["tools"] = {}
        for name in ["git", "make"]:
            tool = Path(shutil.which(name)).resolve()
            self.report["tools"][name] = {"path": str(tool), "sha256": sha(tool)}
            self.run([tool, "--version"], name + "-version")
        # Recheck the actual Git tree at each selected pin, not just a mutable journal.
        for name in source.REPOS:
            paths = [f["path"] for f in manifest["source_files"].values() if f["repo"] == name]
            tree = self.run(["git", "-C", self.main / "references" / name, "ls-tree",
                             source.REPOS[name][0], "--", *paths], "tree-" + name)
            actual = {line.split("\t")[1]: line.split()[2] for line in tree.splitlines()}
            for item in manifest["source_files"].values():
                if item["repo"] == name and actual.get(item["path"]) != item["blob_id"]:
                    raise ValueError("Actual pinned tree disagrees with source manifest")
        for path, item in manifest["accepted_readonly_inputs"].items():
            current = self.main / path
            if current.stat().st_size != item["size"] or sha(current) != item["sha256"]:
                raise ValueError("Accepted read-only input changed: " + path)
        # A private subset proves selected profile composition, not full-tree patch applicability.
        shadow = self.out / "selected-source-subset"
        shadow.mkdir()
        self.run(["git", "init", "-q", shadow], "subset-init")
        for target in SELECTED:
            original = self.cache / "apple-xnu" / target
            if original.is_file():
                dest = shadow / target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, dest)
        include = ["--include=" + path for path in SELECTED]
        self.run(["git", "apply", "--no-index", "--allow-empty", *include,
                  self.cache / "scion-avf/xnu/hakios.patch"], "subset-base-patch", shadow)
        for target in SELECTED:
            overlay = self.cache / "scion-avf/xnu/files" / target
            if overlay.is_file():
                dest = shadow / target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(overlay, dest)
        patch_tree = self.run(["git", "-C", self.main / "references/scion-avf", "ls-tree",
                               source.REPOS["scion-avf"][0], "xnu/patches/"], "numbered-patches")
        paths = sorted(line.split("\t")[1] for line in patch_tree.splitlines() if line.endswith(".patch"))
        pinned_patches = sorted(f["path"] for f in manifest["source_files"].values()
                                if f["repo"] == "scion-avf" and f["path"].startswith("xnu/patches/") and f["path"].endswith(".patch"))
        if paths != pinned_patches:
            raise ValueError("Actual selected numbered patch sequence is incomplete")
        affected = []
        for number, path in enumerate(paths):
            patch = self.cache / "scion-avf" / path
            targets = [line[6:] for line in patch.read_text().splitlines() if line.startswith("+++ b/")]
            affected.append({"path": path, "sha256": sha(patch), "targets": targets})
            self.run(["git", "apply", "--no-index", "--allow-empty", *include, patch],
                     "subset-patch-" + str(number), shadow)
        self.report["numbered_patches"] = affected
        self.report["composed_selected_sources"] = {p: sha(shadow / p) for p in SELECTED if (shadow / p).is_file()}
        text = (shadow / "makedefs/MakeInc.def").read_text()
        fragment = text[text.index("LDFLAGS_KERNEL_GENARM64 ="):text.index("#\n# Default runtime libraries")]
        (self.out / "unchanged-link-profile.mk").write_text(fragment)
        oracle = self.out / "link-profile-oracle.mk"
        oracle.write_text("include " + str(self.out / "unchanged-link-profile.mk") +
                          "\n$(info ACTUAL_KERNEL_ONLY=$(LDFLAGS_KERNEL_ONLY))\nprofile:;\n")
        expanded = {}
        for config in ["DEVELOPMENT", "RELEASE"]:
            expanded[config] = self.run(["make", "--no-builtin-rules", "--no-builtin-variables", "-n", "-f", oracle,
                                          "CURRENT_ARCH_CONFIG=ARM64", "CURRENT_KERNEL_CONFIG=" + config,
                                          "ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64", "TARGET=OWNED_PROFILE_TARGET", "profile"],
                                         "actual-profile-" + config)
        if "-exported_symbols_list" in expanded["DEVELOPMENT"] or "-exported_symbols_list,OWNED_PROFILE_TARGET/all-kpi.exp" not in expanded["RELEASE"]:
            raise ValueError("Genuine Make expansion contradicts DEVELOPMENT/RELEASE distinction")
        self.report["source_make_oracle"] = {"fragment_sha256": sha(self.out / "unchanged-link-profile.mk"),
                                              "expansion": expanded,
                                              "scope": "Unchanged composed MakeInc ARM64 link-variable fragment only; not full build/dry-run closure"}
        native = json.loads((self.main / NATIVE_REPORT).read_text())
        gaps = json.loads((self.main / NATIVE_GAPS).read_text())
        native_argv = native["actual_link"]["frontend_argv"]
        if not any("-exported_symbols_list" in x for x in native_argv) or len(gaps) != 37:
            raise ValueError("Preserved actual native comparison changed")
        exports = (self.cache / "apple-xnu/config/Private.arm64.exports").read_text().splitlines() + (self.cache / "apple-xnu/config/Private.exports").read_text().splitlines()
        if not set(gaps) <= set(exports):
            raise ValueError("Native remaining names do not match genuine selected exports")
        self.report["native_comparison"] = {"actual_native_report": NATIVE_REPORT,
                                            "export_enforcement_argv": [x for x in native_argv if "-exported_symbols_list" in x],
                                            "preserved_native_missing_names": sorted(gaps),
                                            "guest_same_missing_names_claimed": False,
                                            "guest_actual_reference_closure_qualified": False}
        # Stock SDK paths are explicit observations, not a scan for proprietary inputs.
        stock_paths = {
            "default_theos_sdk_includes": Path.home() / "theos/sdks/iPhoneOS16.5.sdk/usr/include",
            "donor_generated_sdk_includes": self.main / "references/scion-avf/xnu-deps/sdk/iPhoneOS16.5.xnu.sdk/usr/include",
            "donor_driverkit_headers": self.main / "references/scion-avf/xnu-deps/MacOSX13.3.sdk/System/Library/Frameworks/Kernel.framework/Headers/DriverKit",
        }
        self.report["stock_input_path_observations"] = {k: {"path": str(p), "is_directory": p.is_dir()}
                                                        for k, p in stock_paths.items()}
        self.report["reuse_and_rebuild"] = {
            "compiler_candidate": native["compiler"],
            "linker_candidate": {p: h for p, h in native["tools_sha256"].items() if p.endswith("-ld")},
            "link_only_runtime_candidate": {k: native["runtime"][k] for k in ["archive", "archive_sha256", "descriptor", "descriptor_sha256", "resource_dir"]},
            "reuse_scope": "Accepted tools and board-independent cc_kext component bytes/provenance only; guest driver/target/header/link compatibility must be revalidated before use. Runtime resource root is LINK ONLY, never compiler header root.",
            "rebuild_required": ["complete selected Scion source/ordered overlays and HFS", "BCM2837 DEVELOPMENT doconf/config/generated board headers", "guest MIG/setup/export/include/assembly/generated IIG objects", "all guest kernel objects, filelists, layout/version/alias/symbolset products", "firehose and pthread against coherent guest exported headers and BCM2837 profile"],
            "forbidden_reuse": "E1S objects/archives/generated board headers and unqualified IIG ABI outputs are not guest inputs; never edit preserved native exports/features.",
            "exact_residual_gates": ["Stock iPhoneOS16.5 SDK include-tree gate and MacOSX13.3 pre-generated DriverKit headers have no supplied qualified guest paths", "IIG shim can emit empty implementation TUs; open generator/native experiments are not full selected ABI substitutes", "Stock compiler wrapper includes constant allocator-type fallback unless genuine builtins are available; qualified compiler integration requires explicit coherent target/resource headers", "Full source/patch applicability, guest object/reference closure, link/image and mockfs/PSCI execution remain unmeasured"],
        }
        self.report["reuse_and_rebuild"]["public_header_route"] = {
            "qualified_native_recipe_components": ["fixtures/public/xnu-kernel-pthread-profile/qualified-component.json", "fixtures/public/xnu-kernel-resource-headers/qualified-component.json"],
            "established_scope": "Public source-installed kernel subset, unchanged public Availability/TargetConditionals and matched compiler resource generation exist. Their native component recipes/source bytes are candidates for guest preparation; this is not a complete SDK or a qualified AVF header namespace.",
            "next_question": "Regenerate coherent DEVELOPMENT/BCM2837 setup/MIG/installed headers from actual Scion source using these public recipes, then measure any genuinely missing guest compiler/IIG inputs. Do not treat the donor SDK installer as proof that all public-source assembly routes are impossible.",
        }
        facts = [
            ("guest-default", "scion-avf/xnu-build.sh", "MACHINE_CONFIGS=${MACHINE:-BCM2837} KERNEL_CONFIGS=DEVELOPMENT", "Selected wrapper defaults: ARM64 DEVELOPMENT BCM2837; no E1S object reuse."),
            ("base-pin", "scion-avf/xnu/apply.sh", "BASE=c54f35ca767986246321eb901baf8f5ff7923f6a", "Exact public XNU base."),
            ("sdk-gate", "scion-avf/xnu-deps/setup.sh", '[ -d "$DARWIN_SDK/usr/include" ] || die', "Stock setup explicitly requires iPhoneOS16.5 SDK includes; not a universal open-core theorem."),
            ("iig-gate", "scion-avf/xnu-deps/host/bin/iig", 'SDKH="$XNUDEPS/MacOSX13.3.sdk/System/Library/Frameworks/Kernel.framework/Headers"', "Stock IIG shim copies pre-generated SDK headers, not a qualified open generator."),
            ("iig-empty-tu", "scion-avf/xnu-deps/host/bin/iig", "no DriverKit implementation generated", "Fallback empty TU is not implementation/ABI proof."),
            ("runtime-config-separate", "scion-avf/Makefile", "qemu-open: kernel loader-open hello", "qemu-open uses ordinary kernel; ARGS_OPEN does not create compiled .config."),
            ("driver-defaults", "scion-avf/tools/hakios-config.py", 'config.get(d.symbol, d.default) == "y"', "Compiled defaults remain unless actual HAKIOS driver selectors change; firmware-none is not driver exclusion."),
            ("raw-executable", "apple-xnu/bsd/miscfs/mockfs/mockfs_vfsops.c", "we will assume that rootvp is an executable", "mockfs serves a raw executable backend, not a filesystem image; input sanity is a caller responsibility."),
            ("raw-launchd", "apple-xnu/bsd/miscfs/mockfs/mockfs_vnops.c", "launchd", "mockfs executable path is launchd; no Apple launchd binary supplied."),
            ("ramdisk-root", "scion-avf/avf/shim/avfboot.c", 'cmd_append(cl, &n, "rd=md0 ");', "Real AVF shim supplies md0 root argument for nonempty ramdisk unless caller overrides rd=."),
            ("psci-stop", "scion-avf/xnu/patches/1001-avf-psci-system-off.patch", "+#define PSCI_SYSTEM_OFF         0x84000008u", "Kernel patch supports SYSTEM_OFF/RESET with chosen psci-method and no-loader path; actual XNU execution remains unmeasured."),
            ("e1s-board", "s24-port/xnu/e1s/patches/0001-e1s-machine-config.patch", "+MACHINE_FLAGS_ARM64_E1S = -DARM64_BOARD_CONFIG_E1S", "Native E1S board/profile is independent from generic BCM2837 virtual guest."),
            ("hfs-source", "scion-avf/xnu/hfs/hfs.sh", "BASE=31d5ec238dfab485e78a9a30b8b92d13e8914f03", "Stock apply additionally fetches exact HFS source; no HFS source acquired or built by this task."),
            ("allocator-fallback", "scion-avf/xnu-deps/hostinc/xnu_clang_compat.h", '#define __builtin_xnu_type_signature(type)       "12"', "Donor stock compiler fallback is a constant, not genuine allocator type metadata; qualified custom compiler is a separately accepted candidate, not automatic guest closure."),
            ("native-gic-source", "s24-port/shim/e1s-xnu/gic.c", "#define GICD_BASE\t0x10200000UL", "Native loader declares Exynos-specific GIC addresses; no physical MMIO is executed or measured."),
            ("native-dram-dt", "s24-port/shim/e1s-xnu/adt_patch.c", '"dram-base"', "Native loader patches supplied Apple DT memory properties instead of constructing the guest tree from QEMU FDT."),
        ]
        for row in facts:
            self.fact(*row)
        for name, path, marker, meaning in [
            ("guest-board-gic", "pexpert/pexpert/arm64/BCM2837.h", "#define GENERIC_GIC_V3_IRQ", "Actual composed BCM2837 source enables generic GIC rather than E1S board selection."),
            ("guest-board-timer", "pexpert/pexpert/arm64/BCM2837.h", "#define ARM_ARCH_TIMER", "Architected ARM timer is selected by genuine guest board header."),
            ("guest-virtual-timer-irq", "osfmk/arm64/gic_v3_irq.c", "#define GIC_INTID_VTIMER        27", "Virtual timer interrupt 27 is routed by generic GIC source."),
            ("guest-dram-dt", "osfmk/arm/arm_init.c", 'SecureDTGetProperty(chosen, "dram-base"', "Kernel consumes translated chosen DRAM base/size; hardware E1S and guest have distinct DT content."),
            ("guest-console-pl011", "pexpert/arm/pe_serial.c", "PL011_CR_UART_ENABLE", "Composed kernel retains PL011 backend for QEMU; driver access is source-review only."),
            ("guest-console-avf", "pexpert/arm/pe_serial.c", "ns16550_serial_functions", "AVF numbered patch adds byte-wide NS16550 console, independent from native E1S loader/UART facts."),
            ("guest-psci-no-loader", "osfmk/arm64/loader_return.c", "loader_exit_without_loader", "Actual composed kernel has no-loader PSCI exit hook, not measured kernel execution."),
            ("guest-mockfs-config", "config/MASTER.arm64.bcm2837", "bindfs mockfs ramfs apfs hfs", "Guest filesystem selection includes raw executable mockfs and HFS; open bootargs do not remove compiled filesystem dependencies."),
            ("guest-link-address", "makedefs/MakeInc.def", "ARM64_LINK_ADDR    =0xfffffff007004000", "Composed non-KASAN ARM64 image base remains within the real shim window/text placement contract."),
        ]:
            text = (shadow / path).read_text()
            if marker not in text:
                raise ValueError("Composed source fact absent: " + name)
            self.report["facts"].append({"id": name, "composed_input": path,
                                         "line": text[:text.index(marker)].count("\n") + 1,
                                         "marker": marker, "source_sha256": sha(shadow / path), "establishes": meaning})
        trees = self.run(["git", "-C", self.main / "references/scion-avf", "ls-tree", source.REPOS["scion-avf"][0],
                          "--", "xnu/files", "drivers", "xnu/hfs", "xnu-deps/iig-impl"], "source-subtrees")
        tree_nodes = {line.split("\t")[1]: {"commit": source.REPOS["scion-avf"][0], "type": line.split()[1],
                                               "git_tree_id": line.split()[2], "content_reviewed_completely": False}
                      for line in trees.splitlines()}
        self.report["input_graph"] = {"nodes": manifest["source_files"], "source_subtrees": tree_nodes, "edges": [
            {"from": "scion-avf:Makefile", "to": ["scion-avf:xnu/apply.sh", "scion-avf:xnu-deps/setup.sh", "scion-avf:tools/make-kernel.sh"], "reason": "kernel prerequisites"},
            {"from": "scion-avf:xnu/apply.sh", "to": ["apple-xnu@" + source.REPOS['apple-xnu'][0], "scion-avf:xnu/hakios.patch", "scion-avf:xnu/files", "scion-avf:drivers/map", "scion-avf:xnu/hfs/hfs.sh", *["scion-avf:" + p for p in paths]], "reason": "ordered source composition; tree overlay and mapped drivers still require full preparation"},
            {"from": "scion-avf:tools/make-kernel.sh", "to": ["scion-avf:xnu/sync-drivers.sh", "scion-avf:tools/hakios-config.py", "scion-avf:xnu-build.sh"], "reason": "compiled selector regeneration and wrapper build"},
            {"from": "scion-avf:xnu-build.sh", "to": ["scion-avf:xnu-env.sh", "scion-avf:xnu-deps/host/bin/xnu-clang", "scion-avf:xnu-deps/host/bin/xcrun", "apple-xnu:makedefs/MakeInc.def"], "reason": "compiler/SDK/profile/link variables"},
            {"from": "scion-avf:xnu-deps/setup.sh", "to": ["external:iPhoneOS16.5-sdk", "external:MacOSX13.3-DriverKit-headers", "source:AvailabilityVersions@5d9baee345b3bc72b26c71adc65f94f2d5e9ced2", "source:libdispatch@a641558f447659d90ad002ef0ee6f0212273fbfc", "source:libpthread@a6c70ca0e544347a0377babf748f831577ec24f9"], "reason": "explicit setup route gates; SDKs not acquired"},
        ], "not_full_dependency_closure": True}
        controls = []
        bad = copy.deepcopy(manifest); next(iter(bad["source_files"].values()))["commit"] = "0" * 40
        controls.append(("wrong-full-pin", bad, None))
        bad = copy.deepcopy(manifest); bad["source_files"].pop("scion-avf:xnu/patches/1001-avf-psci-system-off.patch")
        controls.append(("missing-actual-psci-input", bad, None))
        name = "scion-avf:xnu-build.sh"; original = (self.cache / "scion-avf/xnu-build.sh").read_bytes()
        altered = original.replace(b"KERNEL_CONFIGS=DEVELOPMENT", b"KERNEL_CONFIGS=RELEASE", 1)
        if altered == original:
            raise ValueError("Changed actual profile control did not alter its source")
        (self.out / "changed-profile-source.sh").write_bytes(altered)
        controls.append(("changed-real-build-selector", manifest, {name: altered}))
        for label, field, value in [("mixed-e1s-board", "machine", "E1S"), ("reuse-e1s-objects", "reuse_e1s_objects", True),
                                    ("false-sdk-free-route", "sdk_setup_route", False), ("false-build-ready", "build_ready", True)]:
            bad = copy.deepcopy(manifest); bad["guest"][field] = value
            controls.append((label, bad, None))
        bad = copy.deepcopy(manifest); bad["native"]["preserve_exports"] = False
        controls.append(("pruned-native-export-contract", bad, None))
        for label, bad, changed in controls:
            try:
                self.validate(bad, changed)
            except ValueError as error:
                self.report["negative_controls"].append({"name": label, "outcome": "pass", "rejected": str(error)})
            else:
                raise ValueError("Negative input/profile control admitted: " + label)
        # Rehash preserved accepted inputs after all own-tree composition and controls.
        for path, item in manifest["accepted_readonly_inputs"].items():
            if sha(self.main / path) != item["sha256"]:
                raise ValueError("Read-only parent input changed during review")
        self.report["summary"] = "Pinned actual AVF DEVELOPMENT/BCM2837 source graph and genuine Make link-profile oracle qualified; source-supported guest has no RELEASE-only forced export list. Stock SDK/DriverKit setup gates and coherent guest rebuild remain; preserved native37 export requirements unchanged. No full build or boot."
        self.report["outcome"] = "pass"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    review = Review(args.main.resolve(), args.cache.resolve(), out)
    review.report["argv"] = [sys.executable, *sys.argv]
    try:
        review.qualify()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        review.report["error"] = repr(error)
    write(out / "report.json", review.report)
    print(json.dumps({k: review.report.get(k) for k in ["outcome", "error", "commit", "summary"]}, indent=2))
    return 0 if review.report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
