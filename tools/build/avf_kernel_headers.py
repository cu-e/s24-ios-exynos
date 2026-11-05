#!/usr/bin/env python3
"""Regenerate coherent public AVF guest header inputs; never build/boot a kernel."""
import argparse
from collections import deque
import datetime
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request

sys.dont_write_bytecode = True
from avf_kernel_source import snapshot, write

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ["osfmk", "bsd", "libkern", "iokit", "pexpert", "libsa", "security", "san"]
GUARDS = {"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "PYTHONDONTWRITEBYTECODE": "1"}
QEMU_TREE = "6a955269a8f4e17d21239f75cef9fbe66cffc56c"
QEMU_CONFIG = "1571c785ae12ed79858fb9c81ebfce4ecd5414e4ce6af906820f6b9d61f68394"


def sha(path):
    """Hash even multi-GiB host libraries without materializing their bytes."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def controller_usage():
    # Linux ru_maxrss can retain a pre-exec ancestor high-water value. VmHWM
    # measures this executable image; preserve both instead of misclassifying
    # inherited history as a current controller allocation.
    status = Path("/proc/self/status").read_text().splitlines()
    values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in status if line.startswith(("VmHWM:", "VmRSS:"))}
    return {"current_image_peak_rss_bytes": values["VmHWM"], "current_rss_bytes": values["VmRSS"],
            "raw_rusage_maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}


def available():
    return int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))) * 1024


class Headers:
    def __init__(self, args):
        self.args, self.main, self.out = args, args.main.resolve(), args.out.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / "builder.py")
        self.env = dict(os.environ) | GUARDS
        self.env["HAKIOS_VERSION_SUFFIX"] = "-ga6f4bc38-source"
        self.env["GIT_CEILING_DIRECTORIES"] = str(self.out)
        for key in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "MAKEFLAGS", "MFLAGS", "MAKEFILES"]:
            self.env.pop(key, None)
        path = self.main / "tools/build/qemu_host.py"
        pinned = json.loads((self.main / "fixtures/public/avf-kernel-profile/inputs.json").read_text())["accepted_readonly_inputs"]["tools/build/qemu_host.py"]["sha256"]
        if sha(path) != pinned:
            raise ValueError("Accepted process supervisor changed")
        spec = importlib.util.spec_from_file_location("avf_headers_supervisor", path)
        self.supervisor = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.supervisor)
        self.report = {"kind": "host-test", "origin": "local-host", "outcome": "inconclusive", "recorded_at": stamp(),
                       "argv": [sys.executable, *sys.argv], "builder_sha256": sha(Path(__file__)), "commands": [], "checks": [],
                       "selected_guest": {"arch": "ARM64", "machine": "BCM2837", "kernel": "DEVELOPMENT", "driver_profile": "qemu", "tree": QEMU_TREE},
                       "native_generated_products_used": False, "sdk_used": False, "fake_sdk_supplied": False,
                       "constant_allocator_fallback": False, "empty_iig_implementation_supplied": False,
                       "full_kernel_build_or_link": False, "guest_executed": False, "device_executed": False,
                       "full_sdk_qualified": False, "private_apple_abi_qualified": False, "controller_start_usage": controller_usage()}
        ledger = json.loads((self.main / "state/lab.json").read_text())
        plans = [entry for entry in ledger["experiments"] if entry["id"] == args.experiment]
        if len(plans) != 1 or plans[0]["task"] != "VM-008" or plans[0]["kind"] != "host-test" or (args.mode != "verify" and plans[0]["status"] != "planned"):
            raise ValueError("A real pre-registered MAIN VM-008 host experiment is required before execution")
        procedure = self.main / plans[0]["procedure"]
        if not procedure.is_file():
            raise ValueError("Registered actual MAIN experiment procedure unavailable")
        self.report["registered_main_experiment"] = dict(plans[0], procedure_sha256=sha(procedure))

    def run(self, argv, label, cwd=None, env=None, timeout=90, admitted=True, expect=(0,)):
        record = {"argv": [str(a) for a in argv], "cwd": str(cwd or ROOT), "started_at": stamp(), "timeout_seconds": timeout,
                  "admission_MemAvailable_bytes": available(), "environment_overrides": GUARDS | {"HAKIOS_VERSION_SUFFIX": self.env["HAKIOS_VERSION_SUFFIX"], "GIT_CEILING_DIRECTORIES": self.env["GIT_CEILING_DIRECTORIES"]} | (env or {})}
        record["environment_overrides"]["PATH"] = self.env.get("PATH", "")
        self.report["commands"].append(record)
        if admitted and record["admission_MemAvailable_bytes"] < 4 * 1024**3:
            record.update(exit_code=None, not_started="MemAvailable below 4GiB")
            raise RuntimeError("Resource admission below 4GiB; no generator/compiler started")
        settings = self.env | (env or {})
        started = time.monotonic(); peak = 0
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            # RSS is the physical-memory constraint. Large Clang shared mappings
            # are not misclassified as a missing input by a 256MiB virtual cap.
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        stdout = self.out / (label + ".stdout.txt"); stderr = self.out / (label + ".stderr.txt")
        with stdout.open("xb") as out, stderr.open("xb") as err, (self.out / (label + ".samples.jsonl")).open("x") as samples:
            proc = subprocess.Popen(record["argv"], cwd=cwd or ROOT, env=settings, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, start_new_session=True, preexec_fn=limits)
            record["owned_session"] = proc.pid
            try:
                while proc.poll() is None:
                    sample = self.supervisor.sample(proc.pid)
                    own = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
                    sample["total_owned_rss_bytes"] = own + sample["owned_tree_rss_bytes"]
                    peak = max(peak, sample["total_owned_rss_bytes"])
                    samples.write(json.dumps(sample) + "\n"); samples.flush()
                    if peak > 256 * 1024**2 or time.monotonic() - started > timeout or (admitted and sample["MemAvailable_bytes"] < 4 * 1024**3):
                        record["stop_reason"] = "rss-budget" if peak > 256 * 1024**2 else "deadline" if time.monotonic() - started > timeout else "MemAvailable-floor"
                        self.supervisor.terminate(proc); break
                    time.sleep(0.025)
                record["exit_code"] = proc.wait(timeout=3)
            finally:
                if any(p["state"] != "Z" for p in self.supervisor.sample(proc.pid)["owned_processes"]):
                    self.supervisor.terminate(proc)
                after = self.supervisor.sample(proc.pid)
                record.update(after=after, elapsed_seconds=round(time.monotonic() - started, 3), peak_total_owned_rss_bytes=peak,
                              stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
                write(self.out / "progress.json", self.report)
            if any(p["state"] != "Z" for p in after["owned_processes"]):
                raise RuntimeError("Owned child survived cleanup")
        if record.get("stop_reason"):
            raise RuntimeError("Owned command stopped by resource/deadline guard: " + label + ": " + record["stop_reason"])
        if record["exit_code"] not in expect:
            raise ValueError("Actual command failed: " + label)
        return stdout.read_text()

    def tools(self):
        generators = json.loads((self.main / "fixtures/public/xnu-host-tools/generators-session2.json").read_text())
        self.host = self.main / generators["prefix"] / "bin"
        self.env["PATH"] = str(self.host) + os.pathsep + "/usr/bin:/bin"
        self.report["public_host_tools"] = {}
        for name in ["tcsh", "mig", "migcom", "unifdef"]:
            path = self.host / name
            if sha(path) != generators["binary_sha256"][name]:
                raise ValueError("Qualified public host tool changed: " + name)
            self.report["public_host_tools"][name] = {"path": str(path), "sha256": sha(path)}
        config = json.loads((self.main / "fixtures/public/xnu-kernel-config/qualified-component.json").read_text())
        self.generator = self.main / config["host_generator"]["path"]
        if sha(self.generator) != config["host_generator"]["sha256"]:
            raise ValueError("Qualified board-neutral config tool changed")
        witness = json.loads((self.main / config["host_generator"]["source_witness"]).read_text())
        for name, expected in witness.items():
            if name == "doconf":
                continue
            if sha(self.kernel / "SETUP/config" / name) != expected:
                raise ValueError("Guest config producer differs from accepted host binary: " + name)
        hostroot = self.out / "host"
        dest = hostroot / "SETUP/config/config"; dest.parent.mkdir(parents=True)
        shutil.copy2(self.generator, dest)
        self.hostroot = hostroot
        self.report["public_host_tools"]["config"] = {"source": str(self.generator), "sha256": sha(dest),
            "guest_source_match": "All accepted C/header/lexer/parser/Makefile producer sources match; actual new Scion doconf runs separately."}
        self.compiler = self.main / "artifacts/xnu-compiler-cxx-storage/source-build-session2/clang"
        if sha(self.compiler) != "7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82":
            raise ValueError("Real-builtin compiler changed")
        self.report["compiler"] = {"path": str(self.compiler), "sha256": sha(self.compiler)}

    def prepare(self):
        descriptor_path = self.main / "fixtures/public/avf-kernel-source/qualified-source.json"
        descriptor = json.loads(descriptor_path.read_text())
        manifest = self.main / descriptor["composition_manifest"]
        if sha(manifest) != descriptor["composition_manifest_sha256"]:
            raise ValueError("Accepted complete source manifest changed")
        composition = json.loads(manifest.read_text()); qemu = composition["profiles"]["qemu"]
        if qemu["canonical_output_tree"] != QEMU_TREE or qemu["source_config_sha256"] != QEMU_CONFIG:
            raise ValueError("Explicit frozen QEMU source/config profile changed")
        original_kernel, original_donor = Path(qemu["xnu_root"]), Path(qemu["donor_root"])
        parent_kernel_files, parent_donor_files = qemu["files"], qemu["donor_files"]
        if snapshot(original_kernel) != qemu["files"] or snapshot(original_donor) != qemu["donor_files"]:
            raise ValueError("Frozen guest source/config content or modes changed")
        self.report["parent_source"] = {"descriptor": str(descriptor_path), "descriptor_sha256": sha(descriptor_path),
            "composition_manifest": str(manifest), "composition_manifest_sha256": sha(manifest), "config_sha256": QEMU_CONFIG,
            "source_tree": QEMU_TREE, "original_kernel": str(original_kernel), "original_donor": str(original_donor)}
        self.kernel = self.out / "source/xnu"; self.donor = self.out / "source/scion"
        self.kernel.parent.mkdir()
        shutil.copytree(original_kernel, self.kernel, ignore=shutil.ignore_patterns(".git"))
        shutil.copytree(original_donor, self.donor, ignore=shutil.ignore_patterns(".git"))
        if snapshot(self.kernel) != qemu["files"] or sha(self.donor / ".config") != QEMU_CONFIG:
            raise ValueError("Copied guest source/config does not match frozen profile")
        del qemu, composition; gc.collect()
        self.tools()
        self.report["configurations"] = {}
        for component in COMPONENTS:
            target = self.out / "configuration" / component / "DEVELOPMENT"; target.mkdir(parents=True)
            self.run([self.host / "tcsh", "-f", self.kernel / "SETUP/config/doconf", "-c", "-cpu", "arm64", "-soc", "bcm2837",
                      "-platform", "iPhoneOS", "-d", target, "-s", self.kernel / component / "conf", "-m", self.kernel / "config", "-verbose", "DEVELOPMENT"],
                     "actual-configure-" + component, env={"SRCROOT": str(self.kernel), "OBJROOT": str(self.hostroot), "SOURCE": str(self.kernel / component / "conf") + "/"})
            if not (target / "Makefile").is_file() or not (target / "meta_features.h").is_file():
                raise ValueError("Actual doconf omitted configuration products")
            self.report["configurations"][component] = {"root": str(target), "makefile_sha256": sha(target / "Makefile"),
                                                        "meta_features_sha256": sha(target / "meta_features.h")}
        self.report["prepared_source_files"] = {str(p.relative_to(self.kernel)): sha(p) for p in self.kernel.rglob("*") if p.is_file()}
        self.report["kernel_root"] = str(self.kernel)
        self.report["donor_root"] = str(self.donor)
        if snapshot(original_kernel) != parent_kernel_files or snapshot(original_donor) != parent_donor_files:
            raise ValueError("Frozen parent guest source/config changed")
        self.report["parent_guest_source_unchanged"] = True
        write(self.out / "prepared-component.json", {k: self.report[k] for k in ["parent_source", "configurations", "compiler", "public_host_tools", "kernel_root", "donor_root", "prepared_source_files"]})

    def reuse(self):
        if self.args.prepared is None:
            raise ValueError("Supply explicit owned guest --prepared input")
        path = self.args.prepared.resolve() / "prepared-component.json"
        prepared = json.loads(path.read_text())
        selected = prepared["parent_source"]
        if selected["source_tree"] != QEMU_TREE or selected["config_sha256"] != QEMU_CONFIG:
            raise ValueError("Prepared source profile is not the explicitly frozen QEMU guest")
        descriptor_path = self.main / "fixtures/public/avf-kernel-source/qualified-source.json"
        if sha(descriptor_path) != "6eb1afcc895ecbb852ecea5331c3818e398302ca1bd5701b8609a35ba8a62ec4":
            raise ValueError("Accepted complete-source descriptor changed")
        descriptor = json.loads(descriptor_path.read_text())
        manifest_path = self.main / descriptor["composition_manifest"]
        if sha(manifest_path) != descriptor["composition_manifest_sha256"]:
            raise ValueError("Accepted complete-source manifest changed")
        accepted = json.loads(manifest_path.read_text())["profiles"]["qemu"]
        self.kernel, self.donor = Path(prepared["kernel_root"]), Path(prepared["donor_root"])
        if snapshot(self.kernel) != accepted["files"] or snapshot(self.donor) != accepted["donor_files"]:
            raise ValueError("Prepared complete guest source/config modes or blobs differ from frozen composition")
        del accepted; gc.collect()
        if sha(self.donor / ".config") != QEMU_CONFIG:
            raise ValueError("Prepared guest .config changed")
        actual = {r["path"]: r["sha256"] for r in snapshot(self.kernel)}
        if actual != prepared["prepared_source_files"]:
            raise ValueError("Owned guest prepared source changed")
        self.prepared = prepared
        self.tools()
        self.configs = prepared["configurations"]
        for component, row in self.configs.items():
            cfg = Path(row["root"])
            if sha(cfg / "Makefile") != row["makefile_sha256"] or sha(cfg / "meta_features.h") != row["meta_features_sha256"]:
                raise ValueError("Actual guest doconf products changed")
        self.report["prepared_parent"] = {"path": str(path), "sha256": sha(path), "selected": prepared["parent_source"]}
        self.shim = self.out / "host-commands.mk"
        lines = (self.kernel / "makedefs/MakeInc.cmd").read_text().splitlines()
        platform = "\n".join(next(line for line in lines if line.startswith(key + " :=")) for key in ["SUPPORTED_EMBEDDED_PLATFORMS", "SUPPORTED_SIMULATOR_PLATFORMS", "SUPPORTED_PLATFORMS"])
        logging = "\n".join(next(line for line in lines if re.match(r"^" + re.escape(key) + r"\s*=", line)) for key in ["LOG_PFX_LEN", "LOG_PFX_LEN_ADJ", "LOG", "_LOG_HOST", "_LOG_HOST_LINK", "LOG_INSTALLHDR", "LOG_GENERATE", "LOG_IIG"])
        self.shim.write_text("TR = tr\nBASH = bash\nECHO = echo\nPRINTF = printf\nCAT = cat\nMKDIR = mkdir -p\nRM = rm -f\nCP = cp\nINSTALL = /usr/bin/install\n_v =\n" + platform + "\n" + logging + "\n")
        self.context = self.out / "public-source-context"
        self.context.mkdir()
        self.report["source_context_scope"] = "Upstream SDKROOT variable points only to a recorded source-built include context; no SDK identity/settings/archive, invented header or SDK equivalence."
        self.report["host_query_shim"] = {"sha256": sha(self.shim), "source_platform_logging": str(self.kernel / "makedefs/MakeInc.cmd")}

    def make_args(self, directory, component, cwd):
        return ["SRCROOT=" + str(self.kernel), "OBJROOT=" + str(self.out), "OBJPATH=" + str(self.out / "build"),
                "TARGET=" + str(cwd), "SOURCE=" + str(directory) + "/", "RELATIVE_SOURCE_PATH=./" + str(directory.relative_to(self.kernel)),
                "CURRENT_ARCH_CONFIG=ARM64", "CURRENT_ARCH_CONFIG_LC=arm64", "CURRENT_KERNEL_CONFIG=DEVELOPMENT", "CURRENT_KERNEL_CONFIG_LC=development",
                "CURRENT_MACHINE_CONFIG=BCM2837", "CURRENT_MACHINE_CONFIG_LC=bcm2837", "PLATFORM=iPhoneOS", "SDKROOT=" + str(self.context),
                "CC=" + str(self.compiler), "CXX=" + str(self.compiler), "MIG=" + str(self.host / "mig"), "MIGCOM=" + str(self.host / "migcom"),
                "MIGCC=" + str(self.compiler), "UNIFDEF=" + str(self.host / "unifdef"), "MakeInc_cmd=" + str(self.shim), "ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64",
                "BUILD_WERROR=0", "BUILD_LTO=0", "DO_CTFMERGE=0", "DSTROOT=" + str(self.out / "installtree"), "DEPLOYMENT_TARGET_FLAGS=-target arm64-apple-ios16.5 -DXNU_TARGET_OS_IOS",
                "SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0", "SHELL=/bin/bash", "LOGCOLORS=n"]

    def query(self, makefile, directory, component, label, keys, extra="", definitions=False):
        cwd = self.out / "build" / directory.relative_to(self.kernel); cwd.mkdir(parents=True, exist_ok=True)
        query = self.out / ("query-" + label + ".mk")
        query.write_text("include " + str(makefile) + "\n" + "".join("$(info AVF|" + key + "|$(" + key + "))\n" for key in keys) + extra + "\n.PHONY: avf_query\navf_query: ;\n")
        argv = ["make", "--no-print-directory", "-rR", "-f", str(query), *self.make_args(directory, component, cwd)]
        if definitions:
            content = (Path(self.configs[component]["root"]) / "Makefile").read_text()
            found = re.findall(r"^export CONFIG_DEFINES = (.*)$", content, re.M)
            if len(found) != 1:
                raise ValueError("Actual guest component CONFIG_DEFINES missing")
            argv.append("CONFIG_DEFINES=" + found[0])
        text = self.run([*argv, "avf_query"], "query-" + label, cwd=cwd, admitted=False)
        values = {a[1]: a[2] for line in text.splitlines() if line.startswith("AVF|") and len(a := line.split("|", 2)) == 3}
        if set(values) != set(keys):
            raise ValueError("Incomplete actual Make variable query: " + label)
        return values, argv, cwd, text

    def exports(self):
        keys = ["EXPINC_SUBDIRS", "EXPINC_SUBDIRS_ARM64", "EXPORT_MI_LIST", "EXPORT_MI_DIR", "EXPORT_MD_LIST", "EXPORT_MD_DIR", "EXPORT_MI_GEN_LIST", "EXPORT_MD_GEN_LIST"]
        queue = deque((component, self.kernel / component) for component in COMPONENTS); seen = set(); rows = []
        while queue:
            component, directory = queue.popleft()
            if directory in seen:
                continue
            seen.add(directory)
            if not (directory / "Makefile").is_file():
                rows.append({"directory": str(directory), "status": "missing_genuine_makefile"}); continue
            relative = str(directory.relative_to(self.kernel))
            values, _, _, _ = self.query(directory / "Makefile", directory, component, "export-" + relative.replace("/", "-"), keys)
            for child in sorted(set((values["EXPINC_SUBDIRS"] + " " + values["EXPINC_SUBDIRS_ARM64"]).split())):
                path = (directory / child).resolve()
                if not path.is_relative_to(self.kernel / component):
                    raise ValueError("Genuine export traversal escaped source component")
                queue.append((component, path))
            for kind in ["MI", "MD"]:
                dest = self.out / "EXPORT_HDRS" / component / values["EXPORT_" + kind + "_DIR"]
                for name in values["EXPORT_" + kind + "_LIST"].split():
                    original, output = directory / name, dest / name
                    if not original.resolve().is_relative_to(self.kernel) or not output.resolve().is_relative_to(self.out / "EXPORT_HDRS"):
                        raise ValueError("Genuine source export escaped owned namespace")
                    row = {"source": str(original), "output": str(output), "declaration": str(directory / "Makefile"), "status": "missing_source"}
                    if original.is_file():
                        output.parent.mkdir(parents=True, exist_ok=True)
                        if output.exists() and sha(output) != sha(original):
                            raise ValueError("Conflicting genuine source exports")
                        shutil.copyfile(original, output)
                        row.update(status="source_exported", sha256=sha(output))
                    rows.append(row)
                for name in values["EXPORT_" + kind + "_GEN_LIST"].split():
                    rows.append({"source_directory": str(directory), "component": component, "name": name, "output": str(dest / name), "status": "requires_genuine_generation"})
        self.report["source_exports"] = {"directories": len(seen), "available": sum(r["status"] == "source_exported" for r in rows), "generated_required": sum(r["status"] == "requires_genuine_generation" for r in rows)}
        write(self.out / "source-export-manifest.json", rows)

    def generate(self):
        self.reuse()
        self.exports()
        write(self.out / "generated-component.json", {"kernel_root": str(self.kernel), "donor_root": str(self.donor), "prepared": self.report["prepared_parent"],
            "exports": str(self.out / "EXPORT_HDRS"), "source_context": str(self.context), "host_shim": str(self.shim), "compiler": self.report["compiler"],
            "source_exports": self.report["source_exports"], "coherent_header_route_complete": False})

    def pinned_file(self, repo, pin, relative, upstream, label):
        metadata = self.run(["git", "-C", self.main / "references" / repo, "ls-tree", pin, "--", relative], label + "-tree", admitted=False)
        if not metadata.strip() or metadata.split()[1] != "blob":
            raise ValueError("Exact public source blob metadata unavailable: " + label)
        oid = metadata.split()[2]
        self.run(["git", "-C", self.main / "references" / repo, "show", pin + ":" + relative], label + "-source", admitted=False, expect=(0, 128))
        data = (self.out / (label + "-source.stdout.txt")).read_bytes()
        if self.report["commands"][-1]["exit_code"]:
            url = "https://raw.githubusercontent.com/" + upstream + "/" + pin + "/" + relative
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read(2 * 1024**2 + 1)
            self.report.setdefault("explicit_primary_source_fetches", []).append({"url": url, "size": len(data)})
        if len(data) > 2 * 1024**2 or hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != oid:
            raise ValueError("Exact public source blob/extent mismatch: " + label)
        return data, {"repo": repo, "commit": pin, "path": relative, "git_blob": oid, "sha256": hashlib.sha256(data).hexdigest()}

    def foundation(self):
        self.reuse()
        if self.args.generated is None:
            raise ValueError("Supply explicit fresh guest source-export --generated parent")
        generated = self.args.generated.resolve() / "generated-component.json"
        previous = json.loads(generated.read_text())
        if previous["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("Guest export/config parent mismatch")
        self.exports_root = Path(previous["exports"])
        raw = json.loads((generated.parent / "source-export-manifest.json").read_text())
        for row in raw:
            if row["status"] == "source_exported" and sha(Path(row["output"])) != row["sha256"]:
                raise ValueError("Fresh guest exported source changed")
        self.report["guest_exports_parent"] = {"path": str(generated), "sha256": sha(generated), "root": str(self.exports_root)}
        rawroot = self.out / "public-source/PureDarwin"; rawroot.mkdir(parents=True)
        relative = "src/Libraries/AvailabilityVersions/include/TargetConditionals.h"
        data, binding = self.pinned_file("puredarwin-build-inputs", "6982ddbfca1047c86680ec7c66da152789746efd", relative,
                                         "PureDarwin/PureDarwin", "public-target-base")
        target = rawroot / relative; target.parent.mkdir(parents=True); target.write_bytes(data)
        for name in ["APPLE_LICENSE.txt", "PUREDARWIN_LICENSE.txt"]:
            license_data, _ = self.pinned_file("puredarwin-build-inputs", "6982ddbfca1047c86680ec7c66da152789746efd", name,
                                              "PureDarwin/PureDarwin", "public-license-" + name.replace(".", "-"))
            (rawroot / name).write_bytes(license_data)
        patch = self.main / "patches/open-kernel-inputs/0001-open-header-native-ios-target.patch"
        if sha(patch) != "de3faeb4e5a5661be57ab76ecbaf9dcc7b46e09e44c3acf2140915419e0a4b66":
            raise ValueError("Accepted public target-header source port changed")
        self.run(["git", "-c", "core.hooksPath=/dev/null", "init", "-q"], "public-target-own-init", cwd=rawroot, admitted=False)
        self.run(["git", "apply", "--check", patch], "public-target-port-check", cwd=rawroot, admitted=False)
        self.run(["git", "apply", patch], "public-target-port-apply", cwd=rawroot, admitted=False)
        if sha(target) != "17dc82833b1eb8ec946e660fe371d9a64bee669cdfa9226cffc1026d13ee2d9d":
            raise ValueError("Fresh source-ported public target header differs")
        include = self.context / "usr/include"; include.mkdir(parents=True)
        shutil.copyfile(target, include / "TargetConditionals.h")
        for name in ["Availability.h", "AvailabilityInternal.h", "AvailabilityMacros.h"]:
            shutil.copyfile(self.kernel / "EXTERNAL_HEADERS" / name, include / name)
        self.report["public_target_header"] = binding | {"source_port_sha256": sha(patch), "output_sha256": sha(target),
                                                       "scope": "Fresh public source port, not SDK material or a native generated header"}
        availability, origin = self.pinned_file("xnu-availability", "5d9baee345b3bc72b26c71adc65f94f2d5e9ced2", "availability.pl",
                                               "apple-oss-distributions/AvailabilityVersions", "public-availability-generator")
        tool = self.context / "usr/local/libexec/availability.pl"; tool.parent.mkdir(parents=True); tool.write_bytes(availability); tool.chmod(0o755)
        headers = self.out / "setup/include/sys"; headers.mkdir(parents=True)
        self.run(["/bin/bash", self.kernel / "bsd/sys/make_symbol_aliasing.sh", self.context, headers / "_symbol_aliasing.h"], "genuine-symbol-aliasing")
        self.run(["/bin/sh", self.kernel / "bsd/sys/make_posix_availability.sh", headers / "_posix_availability.h"], "genuine-posix-availability")
        self.report["source_setup_headers"] = {str(path): sha(path) for path in headers.iterdir() if path.is_file()}
        self.report["availability_generator"] = origin
        write(self.out / "foundation-component.json", {"prepared": self.report["prepared_parent"], "exports": self.report["guest_exports_parent"],
            "context": str(self.context), "setup_include": str(headers.parent), "public_target_header": self.report["public_target_header"],
            "setup_headers": self.report["source_setup_headers"], "full_header_route_qualified": False})


    def use_foundation(self):
        self.reuse()
        if self.args.foundation is None:
            raise ValueError("Supply explicit fresh guest --foundation input")
        path = self.args.foundation.resolve() / "foundation-component.json"
        parent = json.loads(path.read_text())
        if parent["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("Foundation/config profile mismatch")
        for name, expected in parent["setup_headers"].items():
            if sha(Path(name)) != expected:
                raise ValueError("Guest foundation setup header changed")
        context = Path(parent["context"])
        if sha(context / "usr/include/TargetConditionals.h") != parent["public_target_header"]["output_sha256"]:
            raise ValueError("Source-ported public target header changed")
        if parent["public_target_header"]["output_sha256"] != "17dc82833b1eb8ec946e660fe371d9a64bee669cdfa9226cffc1026d13ee2d9d":
            raise ValueError("Public target port differs from selected source witness")
        for name in ["Availability.h", "AvailabilityInternal.h", "AvailabilityMacros.h"]:
            if sha(context / "usr/include" / name) != sha(self.kernel / "EXTERNAL_HEADERS" / name):
                raise ValueError("Unchanged public availability source header differs")
        if sha(context / "usr/local/libexec/availability.pl") != "26842f02be5cb75ab02baa6654153ed0b848ff35122a32fea3a02b8472095234":
            raise ValueError("Pinned public AvailabilityVersions producer changed")
        shutil.copytree(context, self.context, dirs_exist_ok=True)
        self.setup_include = Path(parent["setup_include"])
        exports_parent = Path(parent["exports"]["path"])
        if sha(exports_parent) != parent["exports"]["sha256"]:
            raise ValueError("Guest export parent changed")
        rows = json.loads((exports_parent.parent / "source-export-manifest.json").read_text())
        for row in rows:
            if row["status"] == "source_exported" and sha(Path(row["output"])) != row["sha256"]:
                raise ValueError("Guest raw export changed")
        shutil.copytree(Path(parent["exports"]["root"]), self.out / "EXPORT_HDRS")
        self.report["foundation_parent"] = {"path": str(path), "sha256": sha(path)}

    def mig(self):
        self.use_foundation()
        keys = ["COMP_SUBDIRS", "COMP_FILES", "MIGFLAGS", "MIGKUFLAGS", "MIGKSFLAGS", "MIG_UUHDRS", "MIG_USHDRS", "MIG_KUHDRS", "MIG_KSHDRS", "MIG_KUSRC", "MIG_KSSRC", "DEVICE_FILES"]
        top, _, _, _ = self.query(Path(self.configs["osfmk"]["root"]) / "Makefile", self.kernel / "osfmk", "osfmk", "mig-top", keys, definitions=True)
        recipes, inventories = [], []
        for child in top["COMP_SUBDIRS"].split():
            directory = self.kernel / "osfmk" / child
            if not directory.resolve().is_relative_to(self.kernel / "osfmk"):
                raise ValueError("MIG subdirectory escaped guest source")
            values, argv, cwd, _ = self.query(directory / "Makefile", directory, "osfmk", "mig-" + child, keys, definitions=True)
            inventories.append({"directory": child, "makefile_sha256": sha(directory / "Makefile"), "variables": values})
            goals = sorted(set((values["COMP_FILES"] + " " + values["MIG_UUHDRS"] + " " + values["MIG_USHDRS"]).split()))
            for goal in goals:
                text = self.run([*argv, "-n", goal], "recipe-mig-" + child + "-" + goal, cwd=cwd)
                commands = [shlex.split(line) for line in text.replace("\\\n", " ").splitlines() if line.startswith(str(self.host / "mig") + " ")]
                if len(commands) != 1:
                    raise ValueError("Expected one genuine MIG command: " + child + "/" + goal)
                command = commands[0]; source = Path(command[-1]).resolve()
                if not source.is_relative_to(self.kernel) or source.suffix != ".defs" or not source.is_file():
                    raise ValueError("Actual MIG source is outside frozen guest source")
                outputs = {flag: command[command.index(flag) + 1] for flag in ["-user", "-header", "-server", "-sheader"] if flag in command}
                if any(value != "/dev/null" and (Path(value).is_absolute() or ".." in Path(value).parts) for value in outputs.values()):
                    raise ValueError("MIG output escaped owned namespace")
                recipes.append({"directory": child, "goal": goal, "argv": command, "source": str(source), "source_sha256": sha(source), "outputs": outputs})
        unique = list({tuple(row["argv"]): row for row in recipes}.values())
        self.report["mig_inventory"] = inventories
        self.report["mig_recipes"] = recipes
        self.report["unique_mig_commands"] = len(unique)
        write(self.out / "mig-inventory.json", {"directories": top["COMP_SUBDIRS"].split(), "inventories": inventories, "recipes": recipes})
        wrapper_source = ROOT / "fixtures/public/avf-kernel-headers/preprocess.py"
        wrapper = self.out / "preprocess.py"; shutil.copyfile(wrapper_source, wrapper); wrapper.chmod(0o755)
        self.report["mig_preprocessor_sha256"] = sha(wrapper)
        temporary = self.out / "tmp"; temporary.mkdir()
        outputs, dependencies, generation = {}, {}, []
        for index, row in enumerate(unique):
            mode = "internal" if any(value.endswith(".c") for value in row["outputs"].values() if value != "/dev/null") else "export"
            cwd = self.out / mode / "osfmk" / row["directory"]; cwd.mkdir(parents=True, exist_ok=True)
            trace = self.out / "preprocessing" / str(index); trace.mkdir(parents=True)
            env = {"MIGCC": str(wrapper), "MIGCOM": str(self.host / "migcom"), "SDKROOT": "", "TMPDIR": str(temporary),
                   "S24_MIG_COMPILER": str(self.compiler), "S24_MIG_TRACE": str(trace), "S24_MIG_SOURCE": row["source"]}
            command = [*row["argv"][:-1], "-I" + str(self.context / "usr/include"), row["argv"][-1]]
            self.run(command, "generate-mig-" + str(index), cwd=cwd, env=env)
            record = json.loads((trace / "provenance.json").read_text())
            for name, expected in record["inputs"].items():
                if name in dependencies and dependencies[name] != expected:
                    raise ValueError("Actual MIG dependency changed between commands")
                dependencies[name] = expected
            made = {}
            for name in row["outputs"].values():
                if name == "/dev/null":
                    continue
                path = cwd / name
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError("Genuine MIG output absent/empty")
                relative, digest = str(path.relative_to(self.out)), sha(path)
                if relative in outputs and outputs[relative] != digest:
                    raise ValueError("Conflicting same-mode MIG output")
                outputs[relative] = digest; made[name] = digest
            generation.append({"recipe": index, "mode": mode, "directory": str(cwd), "outputs": made})
            self.report["mig_generation"] = generation
        if not outputs or any(sha(self.out / name) != expected for name, expected in outputs.items()):
            raise ValueError("Mode-separated MIG outputs changed")
        write(self.out / "preprocessor-inputs.json", dependencies)
        write(self.out / "mig-component.json", {"prepared": self.report["prepared_parent"], "foundation": self.report["foundation_parent"], "outputs": outputs,
            "dependencies": dependencies, "internal": str(self.out / "internal/osfmk"), "export": str(self.out / "export/osfmk"), "private_apple_abi_qualified": False})
        self.report["mig_generated_files"] = len(outputs)
        self.report["mig_dependency_count"] = len(dependencies)


    def syscalls(self):
        self.use_foundation()
        directory = self.kernel / "bsd"
        keys = ["MAKESYSCALLS", "SEED_DEFINES", "UNIFDEF", "TARGET", "CONFIG_DEFINES", "EXPORT_MI_GEN_LIST"]
        values, argv, cwd, _ = self.query(Path(self.configs["bsd"]["root"]) / "Makefile", directory, "bsd", "syscalls-master", keys, definitions=True)
        master = cwd / "bsd.syscalls.master"
        self.run([*argv, "-n", str(master)], "recipe-syscalls-master", cwd=cwd)
        source = self.kernel / "bsd/kern/syscalls.master"
        script = self.kernel / "bsd/kern/makesyscalls.sh"
        if Path(values["MAKESYSCALLS"]) != script or Path(values["UNIFDEF"]) != self.host / "unifdef":
            raise ValueError("Unexpected genuine syscall producer")
        self.run([self.host / "unifdef", *shlex.split(values["SEED_DEFINES"]), source], "syscalls-select-master", expect=(0, 1))
        shutil.copyfile(self.out / "syscalls-select-master.stdout.txt", master)
        headers_dir = self.kernel / "bsd/sys"
        _, header_argv, header_cwd, _ = self.query(headers_dir / "Makefile", headers_dir, "bsd", "syscalls-headers", keys, definitions=True)
        outputs, rules = {}, {}
        for output, kind, work, args in [("init_sysent.c", "table", cwd, argv), ("syscalls.c", "names", cwd, argv), ("systrace_args.c", "systrace", cwd, argv),
                                         ("syscall.h", "header", header_cwd, header_argv), ("sysproto.h", "proto", header_cwd, header_argv)]:
            text = self.run([*args, "TARGET=" + str(cwd), "-n", output], "recipe-syscalls-" + output, cwd=work)
            commands = [shlex.split(line) for line in text.replace("\\\n", " ").splitlines() if line.startswith(str(script) + " ")]
            if commands != [[str(script), str(master), kind, ">", "/dev/null"]]:
                raise ValueError("Actual syscall recipe differs from selected output: " + output)
            self.run(["/bin/sh", script, master, kind], "generate-syscalls-" + output, cwd=work, env={"TARGET": str(cwd)})
            path = work / output
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError("Genuine syscall output absent/empty")
            outputs[str(path)] = sha(path); rules[output] = commands[0]
        self.report["syscalls"] = {"selected_master": str(master), "selected_master_sha256": sha(master), "source_sha256": sha(source),
            "script_sha256": sha(script), "seed_defines": values["SEED_DEFINES"], "outputs": outputs, "genuine_rules": rules}
        write(self.out / "syscalls-component.json", {"prepared": self.report["prepared_parent"], "foundation": self.report["foundation_parent"],
            "outputs": outputs, "include": str(cwd), "selected_master": str(master), "selected_master_sha256": sha(master)})


    def use_mig_syscalls(self, sanitizer=True):
        self.use_foundation()
        if self.args.mig is None or self.args.syscalls is None:
            raise ValueError("Supply explicit fresh guest --mig and --syscalls components")
        path = self.args.mig.resolve() / "mig-component.json"
        mig = json.loads(path.read_text())
        if mig["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("MIG/config profile mismatch")
        for name, expected in mig["outputs"].items():
            if sha(path.parent / name) != expected:
                raise ValueError("Fresh guest MIG output changed")
        for name, expected in mig["dependencies"].items():
            if sha(Path(name)) != expected:
                raise ValueError("Fresh guest MIG source dependency changed")
        self.mig_internal, self.mig_export = Path(mig["internal"]), Path(mig["export"])
        self.report["mig_parent"] = {"path": str(path), "sha256": sha(path)}
        path = self.args.syscalls.resolve() / "syscalls-component.json"
        syscalls = json.loads(path.read_text())
        if syscalls["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("Syscall/config profile mismatch")
        for name, expected in syscalls["outputs"].items():
            if sha(Path(name)) != expected:
                raise ValueError("Fresh guest syscall output changed")
        self.syscalls_include = Path(syscalls["include"])
        self.report["syscalls_parent"] = {"path": str(path), "sha256": sha(path)}
        # DEVELOPMENT genuinely enables minimal UBSan and requires this generated
        # three-input ignorelist even when KASAN itself is disabled.
        if not sanitizer:
            return
        directory = self.kernel / "san/memory"
        _, argv, cwd, _ = self.query(directory / "Makefile", directory, "san", "san-setup", [])
        target = self.out / "san/kasan-blacklist-arm64"; target.parent.mkdir()
        self.run([*argv, "-n", str(target)], "recipe-sanitizer-ignorelist", cwd=cwd)
        self.run([*argv, "-j1", str(target)], "generate-sanitizer-ignorelist", cwd=cwd)
        self.report["sanitizer_ignorelist"] = {"path": str(target), "sha256": sha(target),
            "source_sha256": {name: sha(directory / name) for name in ["kasan-blacklist", "ubsan-blacklist", "kasan-blacklist-arm64"]},
            "validator_sha256": sha(self.kernel / "san/tools/validate_blacklist.sh")}

    def include_flags(self, component):
        modes = [self.mig_internal, self.mig_export] if component == "osfmk" else [self.mig_export, self.mig_internal]
        roots = [self.setup_include, self.syscalls_include, *modes, Path(self.configs[component]["root"]), self.context / "usr/include"]
        return [value for root in roots for value in ["-I", str(root)]]

    def setup(self):
        self.use_mig_syscalls()
        config = Path(self.configs["osfmk"]["root"]) / "Makefile"
        lines = config.read_text().splitlines()
        compile_line = next(line.strip() for line in lines if "${GENASSYM_KCC}" in line)
        sed_line = next(line.strip() for line in lines if line.strip().startswith("$(_v)sed ") and "DEFINITION__define__" in line)
        extra = "$(eval @ := genassym.o)\n$(eval < := $(SOURCE_DIR)/$(COMPONENT)/$(GENASSYM_LOCATION)/genassym.c)\n$(info AVF|GENASSYM|" + compile_line + ")\n$(eval @ := assym.s)\n$(info AVF|EXTRACT|" + sed_line + ")\n"
        keys = ["GENASSYM_LOCATION", "CFLAGS", "INCFLAGS", "CFLAGS_NOLTO_FLAG", "GENASSYM_KCC", "GENASSYM", "EXTRACT"]
        values, _, cwd, _ = self.query(config, self.kernel / "osfmk", "osfmk", "setup-osfmk", keys, extra=extra, definitions=True)
        # Stamp genuine public templates independently of target compilation.
        include = self.out / "setup/include/libkern"; include.mkdir(parents=True)
        header = include / "version.h"; shutil.copyfile(self.kernel / "libkern/libkern/version.h.template", header)
        version = self.out / "setup/version.c"; shutil.copyfile(self.kernel / "config/version.c", version)
        env = {"SRCROOT": str(self.kernel), "OBJROOT": str(self.out / "setup"), "TARGET": str(cwd), "CURRENT_KERNEL_CONFIG_LC": "development",
               "KERNEL_BUILD_DATE": self.report["recorded_at"], "KERNEL_BUILD_OBJROOT": "local-public-avf/DEVELOPMENT_ARM64_BCM2837"}
        self.run(["env", "-u", "RC_XBS", "perl", self.kernel / "config/newvers.pl", header, version], "stamp-local-version", env=env)
        if any("###KERNEL_" in path.read_text() for path in [header, version]):
            raise ValueError("Public local version template unresolved")
        self.report["local_version"] = {"header": str(header), "header_sha256": sha(header), "source": str(version), "source_sha256": sha(version), "origin": "local public DEVELOPMENT guest, not Apple release"}
        command = shlex.split(values["GENASSYM"])
        source = self.kernel / "osfmk/arm64/genassym.c"
        if Path(command[0]) != self.compiler or Path(command[-1]) != source or "-S" not in command or "-fno-integrated-as" not in command:
            raise ValueError("Genuine guest genassym command changed")
        assembly = cwd / "genassym.o"
        command[command.index("-o") + 1] = str(assembly)
        command = [command[0], *self.include_flags("osfmk"), *command[1:], "-MF", str(cwd / "genassym.d")]
        self.report["setup_rules"] = values
        self.run(command, "actual-guest-genassym", cwd=cwd, timeout=120)
        extract = shlex.split(values["EXTRACT"])
        if extract[0] != "sed" or extract[-2:] != [">", "assym.s"]:
            raise ValueError("Genuine assembly extraction command changed")
        self.run(extract[:-2], "extract-guest-assym", cwd=cwd)
        assym = cwd / "assym.s"; shutil.copyfile(self.out / "extract-guest-assym.stdout.txt", assym)
        definitions = re.findall(r"^#define\s+([A-Za-z0-9_]+)\s+([^\n]+)$", assym.read_text(), re.M)
        if not definitions or len(definitions) != len(set(name for name, value in definitions)):
            raise ValueError("Actual assembly definitions absent/duplicate")
        self.report["assym"] = {"source": str(source), "source_sha256": sha(source), "assembly": str(assembly), "assembly_sha256": sha(assembly),
            "header": str(assym), "header_sha256": sha(assym), "definitions": dict(definitions)}
        write(self.out / "setup-component.json", {"prepared": self.report["prepared_parent"], "foundation": self.report["foundation_parent"],
            "mig": self.report["mig_parent"], "syscalls": self.report["syscalls_parent"], "version": self.report["local_version"], "assym": self.report["assym"], "include": str(include.parent)})


    def iig(self):
        self.use_mig_syscalls()
        parent_path = self.main / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/report.json"
        parent = json.loads(parent_path.read_text())
        accepted = json.loads((self.main / "fixtures/public/xnu-iig-abi/components.json").read_text())
        evidence_path = self.main / accepted["evidence"]
        if sha(evidence_path) != accepted["evidence_sha256"]:
            raise ValueError("Accepted experimental IIG evidence capsule changed")
        evidence = json.loads(evidence_path.read_text())
        report_name = str(parent_path.relative_to(self.main))
        if sha(parent_path) != evidence["sha256"][report_name]:
            raise ValueError("Accepted experimental IIG report changed")
        tool = parent_path.parent / "iig"
        if sha(tool) != parent["candidate_binary_sha256"]:
            raise ValueError("Experimental public IIG tool changed")
        library = parent["libclang"]
        for path, expected in [(Path(library["path"]), library["sha256"]), (Path(library["llvm_dependency"]), library["llvm_sha256"])]:
            if sha(path) != expected:
                raise ValueError("IIG libclang/LLVM host dependency changed")
        resource_root = Path("/usr/lib64/rocm/llvm/lib/clang/19/include")
        for name, expected in parent["compiler_resource_headers_sha256"].items():
            if sha(resource_root / name) != expected:
                raise ValueError("Matched IIG libclang resource header changed")
        self.report["public_iig_producer"] = {"path": str(tool), "sha256": sha(tool), "upstream": "Nyktis/iig-port", "commit": "ea6d147d668ca15d490da638012243fcd705f30d",
            "qualification_report": str(parent_path), "report_sha256": sha(parent_path), "libclang": library,
            "experimental_public_candidate": True, "selected_private_apple_abi_qualified": False,
            "source_ports": {key: parent[key] for key in ["target_patch_sha256", "legacy_patch_sha256", "invoke_guard_patch_sha256"]}}
        directory = self.kernel / "iokit/DriverKit"
        values, argv, cwd, _ = self.query(directory / "Makefile", directory, "iokit", "iig-driverkit", ["ALL_DEFS", "OTHER_IIG_CFLAGS", "GENERATED_HEADERS"])
        produced = {}
        for name in values["GENERATED_HEADERS"].split():
            text = self.run([*argv, "IIG=" + str(tool), "-n", name], "recipe-iig-" + name, cwd=cwd)
            commands = [shlex.split(line) for line in text.replace("\\\n", " ").splitlines() if line.startswith(str(tool) + " ")]
            if len(commands) != 1:
                raise ValueError("One genuine IIG source recipe required")
            command = commands[0]
            source = Path(command[command.index("--def") + 1]).resolve()
            if not source.is_relative_to(directory) or source.suffix != ".iig" or not source.is_file():
                raise ValueError("Guest IIG IDL escaped source")
            # The genuine SDK-driven rule lacks an explicit public cross-target.
            # Keep its declarations/defines, binding only the accepted guest
            # target and coherent public include/resource namespaces.
            command += ["-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc", *self.include_flags("iokit"),
                "-I", str(self.kernel / "libkern"), "-I", str(self.kernel / "pexpert"), "-isystem", str(resource_root)]
            self.run(command, "generate-iig-" + name, cwd=cwd, timeout=90)
            pair = [cwd / name, cwd / (Path(name).stem + ".iig.cpp")]
            if any(not path.is_file() or path.stat().st_size == 0 for path in pair):
                raise ValueError("Public IIG output absent/empty")
            produced[source.name] = {"source": str(source), "source_sha256": sha(source), "outputs": {str(path): sha(path) for path in pair}}
        self.report["iig_generation"] = produced
        write(self.out / "iig-component.json", {"prepared": self.report["prepared_parent"], "producer": self.report["public_iig_producer"], "root": str(cwd),
            "pairs": produced, "selected_private_apple_abi_qualified": False, "full_header_route_qualified": False})


    def header_inventory(self):
        self.use_mig_syscalls(sanitizer=False)
        queue = deque((component, self.kernel / component) for component in [*COMPONENTS, "EXTERNAL_HEADERS"])
        lists = ["INSTALL_KF_" + arch + suffix for arch in ["MI", "MD"] for suffix in ["_LIST", "_LCL_LIST", "_GEN_LIST", "_LCL_GEN_LIST"]]
        keys = ["INSTINC_SUBDIRS", "INSTINC_SUBDIRS_ARM64", "KINCFRAME_UNIFDEF", "KPINCFRAME_UNIFDEF", "KINCDIR", "KPINCDIR", "VPATH", *lists]
        keys += [key.removesuffix("_LIST") + "_FILES" for key in lists]
        seen, rows, queries, missing = set(), [], [], []
        while queue:
            component, directory = queue.popleft()
            directory = directory.resolve()
            if directory in seen:
                continue
            if not directory.is_relative_to(self.kernel):
                raise ValueError("Installed-header recursion escaped frozen guest source")
            seen.add(directory)
            if not (directory / "Makefile").is_file():
                missing.append(str(directory)); continue
            relative = str(directory.relative_to(self.kernel))
            values, argv, cwd, _ = self.query(directory / "Makefile", directory, component, "installed-" + relative.replace("/", "-"), keys)
            for child in sorted(set((values["INSTINC_SUBDIRS"] + " " + values["INSTINC_SUBDIRS_ARM64"]).split())):
                queue.append((component, directory / child))
            selection = []
            for key in lists:
                names, outputs = values[key].split(), values[key.removesuffix("_LIST") + "_FILES"].split()
                if len(names) != len(outputs):
                    raise ValueError("Genuine header list/output count differs")
                for name, destination in zip(names, outputs):
                    target = Path(destination).resolve()
                    if not target.is_relative_to(self.out / "installtree"):
                        raise ValueError("Installed-header output escaped owned prefix")
                    generated = "_GEN_LIST" in key or "_LCL_GEN_LIST" in key
                    source = (cwd if generated else directory) / name
                    flags = shlex.split(values["KPINCFRAME_UNIFDEF" if "_LCL" in key else "KINCFRAME_UNIFDEF"])
                    if any(flag not in flags for flag in ["-UXNU_KERNEL_PRIVATE", "-UMACH_KERNEL_PRIVATE", "-UBSD_KERNEL_PRIVATE"]):
                        raise ValueError("Installed kernel namespace must remove private XNU bodies")
                    row = {"declaration": str(directory / "Makefile"), "declaration_sha256": sha(directory / "Makefile"), "kind": key, "name": name,
                        "source": str(source), "source_exists": source.is_file(), "source_sha256": sha(source) if source.is_file() else None,
                        "output": str(target), "make_target": destination, "generated_input": generated, "private": "_LCL" in key, "unifdef_flags": flags, "vpath": values["VPATH"]}
                    rows.append(row); selection.append(len(rows) - 1)
            queries.append({"source_directory": str(directory), "component": component, "argv": argv, "cwd": str(cwd), "values": values, "rows": selection})
        if not rows:
            raise ValueError("Genuine guest installed-header selection is empty")
        self.report["header_inventory"] = {"directories": len(queries), "selected": len(rows), "generated_inputs": sum(row["generated_input"] for row in rows), "missing_makefiles": missing, "sdk_complete": False}
        self.report["header_queries"] = queries
        write(self.out / "header-inventory.json", rows)
        write(self.out / "header-selection-component.json", {"prepared": self.report["prepared_parent"], "rows": str(self.out / "header-inventory.json"),
            "rows_sha256": sha(self.out / "header-inventory.json"), "queries": queries, "full_header_route_qualified": False})


    def use_setup(self):
        if self.args.setup is None:
            raise ValueError("Supply explicit successful fresh guest --setup component")
        path = self.args.setup.resolve() / "setup-component.json"
        parent = json.loads(path.read_text())
        if parent["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("Setup/config profile mismatch")
        for section, names in [("version", ["header", "source"]), ("assym", ["header", "assembly"])]:
            for name in names:
                if sha(Path(parent[section][name])) != parent[section][name + "_sha256"]:
                    raise ValueError("Fresh guest setup output changed")
        self.guest_setup = parent
        self.report["setup_parent"] = {"path": str(path), "sha256": sha(path)}

    def headers(self):
        self.header_inventory()
        self.use_setup()
        iig = None
        if self.args.iig is not None:
            path = self.args.iig.resolve() / "iig-component.json"
            iig = json.loads(path.read_text())
            if iig["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
                raise ValueError("IIG/config profile mismatch")
            for pair in iig["pairs"].values():
                if sha(Path(pair["source"])) != pair["source_sha256"] or any(sha(Path(name)) != expected for name, expected in pair["outputs"].items()):
                    raise ValueError("Fresh public IIG pair/source changed")
            self.report["iig_parent"] = {"path": str(path), "sha256": sha(path)}
        producer = json.loads((self.main / "artifacts/xnu-kernel-pthread-profile/headers-session4/report.json").read_text())["header_install_tools"]
        decomment = self.main / "artifacts/xnu-kernel-pthread-profile/headers-session4/decomment"
        replace = self.main / producer["replacecontents"]
        if sha(self.kernel / "SETUP/decomment/decomment.c") != producer["decomment_source_sha256"] or sha(decomment) != producer["decomment_sha256"] or sha(replace) != producer["replacecontents_sha256"]:
            raise ValueError("Qualified board-neutral header host producer/source changed")
        self.report["header_host_tools"] = {"decomment": str(decomment), "decomment_sha256": sha(decomment), "source_sha256": producer["decomment_source_sha256"],
            "replacecontents": str(replace), "replacecontents_sha256": sha(replace), "install_flags": "GNU -c -m 0444; BSD-only -S omitted, genuine header filtering unchanged"}
        rows = json.loads((self.out / "header-inventory.json").read_text())
        available, seeded = set(), {}
        for index, row in enumerate(rows):
            source = Path(row["source"])
            if row["generated_input"]:
                relative = source.relative_to(self.out / "build")
                original = self.kernel / relative
                candidate, origin = None, None
                if original.is_file():
                    candidate, origin = original, "genuine source-backed declared generation input"
                else:
                    # Some genuine GEN_LIST entries (mach/*/asm.h) are found
                    # unchanged through the source Makefile's explicit VPATH.
                    # They are source inputs, not missing generated interfaces.
                    for entry in row["vpath"].split(":"):
                        if not entry:
                            continue
                        path = (source.parent / entry / row["name"]).resolve()
                        if path.is_file() and path.is_relative_to(self.kernel):
                            candidate, origin = path, "genuine source Make VPATH input"; break
                if candidate is None and relative.parts[0] == "osfmk":
                    for root in [self.mig_export, self.mig_internal]:
                        if (root / Path(*relative.parts[1:])).is_file():
                            candidate, origin = root / Path(*relative.parts[1:]), "fresh mode-separated guest MIG"; break
                elif candidate is None and str(relative) in ["bsd/sys/syscall.h", "bsd/sys/sysproto.h"]:
                    candidate, origin = self.syscalls_include / Path(*relative.parts[1:]), "fresh guest syscall generator"
                elif candidate is None and str(relative) in ["bsd/sys/_symbol_aliasing.h", "bsd/sys/_posix_availability.h"]:
                    candidate, origin = self.setup_include / Path(*relative.parts[1:]), "fresh source availability generator"
                elif candidate is None and str(relative) == "libkern/libkern/version.h":
                    candidate, origin = Path(self.guest_setup["version"]["header"]), "fresh public guest version stamp"
                elif candidate is None and relative.parts[:2] == ("iokit", "DriverKit") and iig:
                    candidate, origin = Path(iig["root"]) / relative.name, "fresh experimental public IIG; private ABI unqualified"
                if candidate is None or not candidate.is_file():
                    row["status"] = "unavailable_genuine_generated_input"; continue
                if source in seeded and seeded[source] != sha(candidate):
                    raise ValueError("Conflicting guest generated input")
                source.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(candidate, source); seeded[source] = sha(source)
                row.update(source_exists=True, source_sha256=sha(source), generated_origin=str(candidate), origin_scope=origin)
            if not source.is_file():
                row["status"] = "missing_genuine_source"; continue
            if sha(source) != row["source_sha256"]:
                raise ValueError("Guest header input changed before installation")
            available.add(index)
        for index, query in enumerate(self.report["header_queries"]):
            selected = [rows[i] for i in query["rows"] if i in available]
            if not selected:
                continue
            goals = list(dict.fromkeys(row["make_target"] for row in selected))
            argv = [*query["argv"], "-j1", *goals, "DECOMMENT=" + str(decomment), "REPLACECONTENTS=" + str(replace), "INSTALL_FLAGS=-c -m 0444"]
            for name in sorted({row["source"] for row in selected if row["generated_input"]}):
                argv += ["-o", name, "-o", str(Path(name).relative_to(query["cwd"]))]
            self.run(argv, "actual-install-" + str(index), cwd=Path(query["cwd"]), timeout=120)
            for row in selected:
                path = Path(row["output"])
                if path.is_file():
                    row.update(status="installed", output_sha256=sha(path), output_mode=oct(path.stat().st_mode & 0o777))
                    if path.stat().st_mode & 0o777 != 0o444:
                        raise ValueError("Genuine read-only installed header mode differs")
                else:
                    row["status"] = "genuine_filter_removed_empty_body"
        counts = {status: sum(row.get("status") == status for row in rows) for status in sorted({row.get("status", "not_run") for row in rows})}
        first = self.report["header_queries"][0]["values"]
        roots = {name: str(self.out / "installtree" / first[key].lstrip("/")) for name, key in [("public", "KINCDIR"), ("private", "KPINCDIR")]}
        thread = Path(roots["private"]) / "kern/thread.h"
        if not thread.is_file() or re.search(r"\bstruct\s+thread\s*\{", thread.read_text()):
            raise ValueError("Genuine installed namespace must remove XNU thread implementation")
        if any(Path(row["output"]).exists() for row in rows if row.get("status") == "unavailable_genuine_generated_input"):
            raise ValueError("Missing generation input received fabricated installed output")
        write(self.out / "installed-header-manifest.json", rows)
        self.report["header_install_counts"], self.report["header_roots"] = counts, roots
        write(self.out / "headers-component.json", {"prepared": self.report["prepared_parent"], "roots": roots, "counts": counts,
            "manifest": str(self.out / "installed-header-manifest.json"), "manifest_sha256": sha(self.out / "installed-header-manifest.json"),
            "full_header_route_qualified": False, "sdk_qualified": False, "private_apple_abi_qualified": False})


    def objects(self):
        self.use_foundation()
        self.object_inventory()

    def object_inventory(self):
        rows = []
        keys = ["OBJS", "LIBOBJS", "CFILES", "CXXFILES", "SFILES", "CFLAGS", "CXXFLAGS", "SFLAGS", "INCFLAGS"]
        for component in COMPONENTS:
            makefile = Path(self.configs[component]["root"]) / "Makefile"
            text = makefile.read_text(); recipes = {}; target = None
            for line in text.splitlines():
                match = re.match(r"^([^\s:]+\.(?:o|cpo|co)):.*", line)
                if match:
                    target = match[1]
                if target and re.match(r"^\s*\$[({][CPS]_RULE_1A", line):
                    recipes[target] = line.strip()
            sources, extra = {}, ""
            flat = text.replace("\\\n", " ")
            for language, key in [("c", "CFILES"), ("c++", "CXXFILES"), ("asm", "SFILES")]:
                found = re.findall(r"(?m)^" + key + r"[ \t]*=(.*)$", flat)
                if len(found) != 1:
                    raise ValueError("Genuine guest source-list declaration missing: " + component + "/" + key)
                for name in found[0].split():
                    name = name.replace("$(SOURCE_DIR)", str(self.kernel))
                    target = Path(name).name[:-1] + "o"
                    if target in sources:
                        raise ValueError("Duplicate guest selected object basename")
                    sources[target] = (language, name)
            for target, (language, source) in sources.items():
                if target not in recipes:
                    continue
                recipe = re.sub(r"\$[({][CPS]_RULE_1B(?:_[A-Z]+)?[)}]", Path(source).name, recipes[target])
                extra += "$(eval @ := " + target + ")\n$(eval <F := " + Path(source).name + ")\n$(info AVFCMD|" + target + "|" + recipe + ")\n"
            values, _, cwd, expanded = self.query(makefile, self.kernel / component, component, "objects-" + component, keys, extra=extra, definitions=True)
            commands = {parts[1]: parts[2] for line in expanded.splitlines() if line.startswith("AVFCMD|") and len(parts := line.split("|", 2)) == 3}
            selected = values["OBJS"].split()
            if len(selected) != len(set(selected)):
                raise ValueError("Duplicate linked guest object")
            for target in selected:
                language, name = sources.get(target, ("unknown", ""))
                source = (cwd / name).resolve() if name else None
                generated = source is not None and not source.is_relative_to(self.kernel)
                if source and not (source.is_relative_to(self.kernel) or source.is_relative_to(self.out)):
                    raise ValueError("Guest compile input escaped own source/generation roots")
                rows.append({"id": component + "/" + target, "component": component, "target": target, "language": language, "source": str(source) if source else None,
                    "source_sha256": sha(source) if source and source.is_file() else None, "generated_input": generated, "genuine_expanded_recipe": commands.get(target),
                    "cwd": str(cwd), "configuration": str(makefile), "configuration_sha256": sha(makefile), "status": "source_and_recipe_available" if source and source.is_file() and target in commands else "requires_genuine_generation_or_rule"})
        self.report["guest_object_inventory"] = {"selected": len(rows), "source_and_recipe_available": sum(row["status"] == "source_and_recipe_available" for row in rows),
            "requires_genuine_generation_or_rule": sum(row["status"] != "source_and_recipe_available" for row in rows), "compiled": 0, "no_native_objects_reused": True}
        write(self.out / "guest-object-manifest.json", rows)
        write(self.out / "objects-component.json", {"prepared": self.report["prepared_parent"], "foundation": self.report["foundation_parent"],
            "manifest": str(self.out / "guest-object-manifest.json"), "manifest_sha256": sha(self.out / "guest-object-manifest.json"), "summary": self.report["guest_object_inventory"]})


    def representatives(self):
        self.use_mig_syscalls()
        self.use_setup()
        if self.args.iig is None:
            raise ValueError("Fresh experimental public --iig component required")
        path = self.args.iig.resolve() / "iig-component.json"
        iig = json.loads(path.read_text())
        if iig["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("Public IIG/config profile mismatch")
        for pair in iig["pairs"].values():
            if sha(Path(pair["source"])) != pair["source_sha256"] or any(sha(Path(name)) != expected for name, expected in pair["outputs"].items()):
                raise ValueError("Fresh public IIG source/pair changed")
        self.report["iig_parent"] = {"path": str(path), "sha256": sha(path)}
        self.object_inventory()
        rows = json.loads((self.out / "guest-object-manifest.json").read_text())
        selected = {"pexpert/pe_init.o", "osfmk/gic_v3_irq.o", "osfmk/arm_init.o", "bsd/mockfs_vfsops.o", "osfmk/startup.o", "libkern/OSObject.cpo", "iokit/OSObject.iig.cpo", "osfmk/start.o", "osfmk/kalloc.o", "libkern/OSData.cpo"}
        if self.args.only:
            requested = set(self.args.only)
            if not requested <= selected:
                raise ValueError("--only must select from the bounded genuine representative set")
            selected = requested
        cases = [row for row in rows if row["id"] in selected]
        if {row["id"] for row in cases} != selected:
            raise ValueError("Actual guest profile does not select required bounded representatives")
        self.report["representative_compiles"] = []
        for index, row in enumerate(cases):
            source = Path(row["source"])
            if row["generated_input"]:
                if row["id"] != "iokit/OSObject.iig.cpo":
                    raise ValueError("Unexpected representative generation source")
                source = Path(iig["root"]) / "OSObject.iig.cpp"
            command = shlex.split(row["genuine_expanded_recipe"])
            if Path(command[0]) != self.compiler or (Path(row["cwd"]) / command[-1]).resolve() != Path(row["source"]).resolve():
                raise ValueError("Real guest representative recipe/source binding differs")
            output = self.out / "representatives" / row["id"]; output.parent.mkdir(parents=True, exist_ok=True)
            command[-1] = str(source)
            for flag, value in [("-o", output), ("-MF", output.with_suffix(".d"))]:
                if flag in command:
                    command[command.index(flag) + 1] = str(value)
                else:
                    command += [flag, str(value)]
            roots = [Path(self.guest_setup["version"]["header"]).parents[1], Path(self.guest_setup["assym"]["header"]).parent, Path(iig["root"]).parent]
            command = [command[0], *[value for root in roots for value in ["-I", str(root)]], *self.include_flags(row["component"]), *command[1:]]
            self.run(command, "compile-guest-" + str(index), cwd=Path(row["cwd"]), timeout=120, expect=(0, 1))
            result = self.report["commands"][-1]
            diagnostics = (self.out / ("compile-guest-" + str(index) + ".stderr.txt")).read_text()
            actual = False
            if result["exit_code"] == 0 and output.is_file():
                import struct
                magic, cpu, subtype, kind = struct.unpack("<4I", output.read_bytes()[:16])
                actual = magic == 0xfeedfacf and cpu == 0x100000c and kind == 1
                if not actual:
                    raise ValueError("Successful representative did not emit an ARM64 Mach-O object")
            dependencies = {}
            dep = output.with_suffix(".d")
            if dep.is_file():
                first = dep.read_text().replace("\\\n", " ").splitlines()[0]
                for name in shlex.split(first.split(":", 1)[1]):
                    dependency = (Path(row["cwd"]) / name).resolve()
                    dependencies[str(dependency)] = sha(dependency)
            sections = []
            if actual:
                data = output.read_bytes(); count = struct.unpack_from("<I", data, 16)[0]; at = 32
                for unused in range(count):
                    command_id, extent = struct.unpack_from("<II", data, at)
                    if extent < 8 or at + extent > len(data):
                        raise ValueError("Invalid real object load command")
                    if command_id == 25:
                        section_count = struct.unpack_from("<I", data, at + 64)[0]
                        if extent < 72 + 80 * section_count:
                            raise ValueError("Invalid real object section extent")
                        for number in range(section_count):
                            name, segment, address, size, offset = struct.unpack_from("<16s16sQQI", data, at + 72 + 80 * number)
                            name, segment = name.split(b"\0")[0].decode(), segment.split(b"\0")[0].decode()
                            if "kalloc" in name:
                                if offset + size > len(data) or not size:
                                    raise ValueError("Truncated/empty actual allocator metadata")
                                sections.append({"segment": segment, "section": name, "size": size, "sha256": hashlib.sha256(data[offset:offset + size]).hexdigest()})
                    at += extent
            if actual and row["id"] == "libkern/OSData.cpo" and not sections:
                raise ValueError("Real C++ allocator must emit genuine nonempty allocator metadata")
            item = {"id": row["id"], "source": str(source), "source_sha256": sha(source), "exit_code": result["exit_code"], "actual_arm64_object": actual,
                "object": str(output) if actual else None, "object_sha256": sha(output) if actual else None, "allocator_metadata_sections": sections, "dependencies": dependencies,
                "missing_headers": re.findall(r"fatal error: '([^']+)' file not found", diagnostics), "errors": re.findall(r"(?m)^.*(?:fatal error:|error:).*$", diagnostics)[:20]}
            self.report["representative_compiles"].append(item)
            write(self.out / "compile-progress.json", self.report["representative_compiles"])
        self.report["representative_summary"] = {"attempted": len(cases), "actual_arm64": sum(row["actual_arm64_object"] for row in self.report["representative_compiles"]),
            "actual_guest_execution": False, "selected_private_apple_abi_qualified": False}
        write(self.out / "representatives-component.json", {"prepared": self.report["prepared_parent"], "summary": self.report["representative_summary"], "results": self.report["representative_compiles"], "full_header_route_qualified": False})
        if self.report["representative_summary"]["actual_arm64"] != len(cases):
            raise RuntimeError("Real guest representative input/profile remains incomplete; retain exact diagnostics")


    def controls(self):
        self.use_foundation()
        prepared_path = self.args.prepared.resolve() / "prepared-component.json"
        prepared = json.loads(prepared_path.read_text())
        self.report["negative_controls"] = []
        for label in ["wrong-profile", "wrong-config"]:
            directory = self.out / label; directory.mkdir()
            changed = json.loads(json.dumps(prepared))
            if label == "wrong-profile":
                changed["parent_source"]["source_tree"] = "0" * 40
                expected = "not the explicitly frozen QEMU guest"
            else:
                donor = directory / "donor"; donor.mkdir()
                (donor / ".config").write_bytes((self.donor / ".config").read_bytes() + b"\nCONFIG_NEGATIVE_INPUT=y\n")
                changed["donor_root"] = str(donor)
                expected = "differ from frozen composition"
            write(directory / "prepared-component.json", changed)
            argv = [sys.executable, Path(__file__).resolve(), "--mode", "objects", "--main", self.main, "--prepared", directory,
                    "--foundation", self.args.foundation.resolve(), "--out", directory / "result", "--experiment", self.args.experiment]
            self.run(argv, "control-" + label, admitted=False, expect=(2,))
            result = json.loads((directory / "result/report.json").read_text())
            good = result["outcome"] == "fail" and expected in result.get("error", "") and not result["commands"]
            if not good:
                raise ValueError("Wrong guest profile/config input was not rejected before commands")
            self.report["negative_controls"].append({"name": label, "pass": good, "actual_exit_code": 2, "compiler_or_generator_started": False, "diagnostic": result["error"]})
        if self.args.mig is None:
            raise ValueError("Supply real --mig recipe for the actual preprocessor-error control")
        parent_path = self.args.mig.resolve() / "report.json"
        parent = json.loads(parent_path.read_text())
        recipe = parent["mig_recipes"][0]
        source = Path(recipe["source"])
        if sha(source) != recipe["source_sha256"]:
            raise ValueError("Actual negative MIG recipe source changed")
        wrapper = self.out / "preprocess.py"; shutil.copyfile(ROOT / "fixtures/public/avf-kernel-headers/preprocess.py", wrapper); wrapper.chmod(0o755)
        trace = self.out / "negative-cpp-trace"; trace.mkdir()
        temporary = self.out / "tmp"; temporary.mkdir()
        work = self.out / "negative-cpp"; work.mkdir()
        command = [str(value).replace(str(parent_path.parent / "EXPORT_HDRS"), str(self.out / "EXPORT_HDRS")) for value in recipe["argv"]]
        command = [*command[:-1], "-include" + str(self.out / "deliberately-absent-input.h"), command[-1]]
        env = {"MIGCC": str(wrapper), "MIGCOM": str(self.host / "migcom"), "SDKROOT": "", "TMPDIR": str(temporary),
               "S24_MIG_COMPILER": str(self.compiler), "S24_MIG_TRACE": str(trace), "S24_MIG_SOURCE": str(source)}
        production_rejected = False
        try:
            self.run(command, "control-mig-preprocessor-error", cwd=work, env=env)
        except ValueError:
            if self.report["commands"][-1].get("exit_code") not in [1, 2]:
                raise
            production_rejected = True
        provenance = json.loads((trace / "provenance.json").read_text())
        rejected = {str(work / name): sha(work / name) for name in recipe["outputs"].values() if name != "/dev/null" and (work / name).is_file()}
        good = provenance["exit_code"] != 0 and production_rejected and not (self.out / "mig-component.json").exists()
        if not good:
            raise ValueError("Real MIG preprocessor error was not rejected by the production exit gate")
        self.report["negative_controls"].append({"name": "actual-mig-preprocessor-error", "pass": good, "actual_exit_code": self.report["commands"][-1]["exit_code"],
            "preprocessor_exit_code": provenance["exit_code"], "production_gate_rejected": True, "quarantined_partial_outputs": rejected,
            "no_positive_component_published": True, "provenance_sha256": sha(trace / "provenance.json")})
        if self.args.metadata is None:
            raise ValueError("Supply passing real guest --metadata emission witness")
        metadata_path = self.args.metadata.resolve() / "report.json"
        metadata = json.loads(metadata_path.read_text())
        row = next(item for item in metadata["representative_compiles"] if item["id"] == "libkern/OSData.cpo")
        if not row["actual_arm64_object"] or not row["allocator_metadata_sections"] or sha(Path(row["source"])) != row["source_sha256"] or sha(Path(row["object"])) != row["object_sha256"]:
            raise ValueError("Actual C++ metadata witness changed or absent")
        stock = Path("/usr/lib64/rocm/llvm/bin/clang")
        if not stock.is_file() or sha(stock) == sha(self.compiler):
            raise ValueError("Distinct installed stock compiler control unavailable")
        original = next(item for item in metadata["commands"] if item["argv"][0] == str(self.compiler) and row["source"] in item["argv"])
        command = original["argv"].copy(); command[0] = str(stock)
        # Clang19 removed this transitional acknowledgement flag. Keep the
        # actual -ftrivial-auto-var-init=zero behavior and every type/target
        # define; remove only this obsolete driver spelling for the control.
        retired_flag = "-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang"
        if retired_flag in command:
            command.remove(retired_flag)
        output = self.out / "stock-compiler-negative.o"
        command[command.index("-o") + 1] = str(output)
        command[command.index("-MF") + 1] = str(output.with_suffix(".d"))
        self.run(command, "control-stock-compiler-metadata", cwd=Path(original["cwd"]), expect=(1,))
        diagnostic = (self.out / "control-stock-compiler-metadata.stderr.txt").read_text()
        good = not output.exists() and "__builtin_xnu_type" in diagnostic and "error:" in diagnostic
        if not good:
            raise ValueError("Stock compiler did not reject the genuine XNU metadata dependency")
        self.report["negative_controls"].append({"name": "stock-compiler-real-metadata", "pass": good, "actual_exit_code": 1, "compiler": str(stock), "compiler_sha256": sha(stock),
            "source": row["source"], "source_sha256": row["source_sha256"], "removed_obsolete_control_driver_flag": retired_flag, "auto_var_init_zero_retained": "-ftrivial-auto-var-init=zero" in command, "actual_metadata_witness": str(metadata_path), "actual_metadata_report_sha256": sha(metadata_path), "no_output_or_fallback": True})
        write(self.out / "controls-component.json", {"prepared": self.report["prepared_parent"], "controls": self.report["negative_controls"]})


    def header_residual(self):
        self.use_foundation()
        if self.args.headers is None:
            raise ValueError("Supply prior passing --headers component")
        parent_path = self.args.headers.resolve() / "headers-component.json"
        parent = json.loads(parent_path.read_text())
        if parent["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"]:
            raise ValueError("Installed-header/config parent differs")
        manifest_path = Path(parent["manifest"])
        if sha(manifest_path) != parent["manifest_sha256"]:
            raise ValueError("Passing header manifest changed")
        rows = json.loads(manifest_path.read_text())
        old_prefix, prefix = parent_path.parent / "installtree", self.out / "installtree"
        for row in rows:
            if row["status"] == "installed" and sha(Path(row["output"])) != row["output_sha256"]:
                raise ValueError("Passing installed header changed")
            if row.get("source_exists") and sha(Path(row["source"])) != row["source_sha256"]:
                raise ValueError("Passing header source/generation input changed")
        shutil.copytree(old_prefix, prefix)
        for row in rows:
            relative = Path(row["output"]).relative_to(old_prefix)
            row["output"] = str(prefix / relative)
            row["make_target"] = row["make_target"].replace(str(old_prefix), str(prefix), 1)
        unresolved = [row for row in rows if row["status"] == "unavailable_genuine_generated_input"]
        if not unresolved or any(row["name"] != "asm.h" for row in unresolved):
            raise ValueError("This bounded continuation handles only the measured genuine VPATH asm.h inputs")
        producer = json.loads((self.main / "artifacts/xnu-kernel-pthread-profile/headers-session4/report.json").read_text())["header_install_tools"]
        decomment = self.main / "artifacts/xnu-kernel-pthread-profile/headers-session4/decomment"
        replace = self.main / producer["replacecontents"]
        if sha(decomment) != producer["decomment_sha256"] or sha(replace) != producer["replacecontents_sha256"] or sha(self.kernel / "SETUP/decomment/decomment.c") != producer["decomment_source_sha256"]:
            raise ValueError("Board-neutral install producer/source changed")
        lists = ["INSTALL_KF_" + arch + suffix for arch in ["MI", "MD"] for suffix in ["_LIST", "_LCL_LIST", "_GEN_LIST", "_LCL_GEN_LIST"]]
        keys = ["VPATH", *lists, *[key.removesuffix("_LIST") + "_FILES" for key in lists]]
        for index, declaration in enumerate(sorted({row["declaration"] for row in unresolved})):
            directory = Path(declaration).parent
            values, argv, cwd, _ = self.query(Path(declaration), directory, "osfmk", "vpath-" + str(index), keys)
            selected = [row for row in unresolved if row["declaration"] == declaration]
            for row in selected:
                names = values[row["kind"]].split(); outputs = values[row["kind"].removesuffix("_LIST") + "_FILES"].split()
                if len(names) != len(outputs) or row["name"] not in names:
                    raise ValueError("Actual residual header declaration changed")
                target = outputs[names.index(row["name"])]
                if Path(target).resolve() != Path(row["output"]):
                    raise ValueError("Actual residual header destination differs")
                candidates = [(cwd / entry / row["name"]).resolve() for entry in values["VPATH"].split(":") if entry]
                candidate = next((path for path in candidates if path.is_file() and path.is_relative_to(self.kernel)), None)
                if candidate is None:
                    raise ValueError("Genuine VPATH source cannot be resolved")
                source = cwd / row["name"]; shutil.copyfile(candidate, source)
                row.update(source=str(source), source_exists=True, source_sha256=sha(source), generated_origin=str(candidate),
                    origin_scope="unchanged genuine source resolved by actual Make VPATH", make_target=target, vpath=values["VPATH"])
            goals = list(dict.fromkeys(row["make_target"] for row in selected))
            command = [*argv, "-j1", *goals, "DECOMMENT=" + str(decomment), "REPLACECONTENTS=" + str(replace), "INSTALL_FLAGS=-c -m 0444", "-o", "asm.h", "-o", str(cwd / "asm.h")]
            self.run(command, "actual-vpath-install-" + str(index), cwd=cwd)
            for row in selected:
                path = Path(row["output"])
                if not path.is_file() or path.stat().st_mode & 0o777 != 0o444:
                    raise ValueError("Actual source-backed asm header was not installed read-only")
                row.update(status="installed", output_sha256=sha(path), output_mode="0o444")
        for row in rows:
            if row["status"] == "installed" and sha(Path(row["output"])) != row["output_sha256"]:
                raise ValueError("Composed installed namespace changed")
            if row["status"] not in ["installed", "genuine_filter_removed_empty_body"]:
                raise ValueError("Selected public installed-header entry remains unavailable")
        roots = {name: str(prefix / Path(path).relative_to(old_prefix)) for name, path in parent["roots"].items()}
        counts = {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})}
        write(self.out / "installed-header-manifest.json", rows)
        self.report["header_install_counts"], self.report["header_roots"] = counts, roots
        self.report["composed_from_passing_guest_headers"] = {"component": str(parent_path), "sha256": sha(parent_path), "prior_inputs_rehashed": True, "original_unchanged": True}
        write(self.out / "headers-component.json", {"prepared": self.report["prepared_parent"], "roots": roots, "counts": counts, "manifest": str(self.out / "installed-header-manifest.json"),
            "manifest_sha256": sha(self.out / "installed-header-manifest.json"), "selected_entries_materialized_or_genuinely_filtered": True,
            "full_header_route_qualified": False, "sdk_qualified": False, "private_apple_abi_qualified": False})


    def handoff(self):
        self.use_mig_syscalls(sanitizer=False)
        self.use_setup()
        if self.args.iig is None or self.args.headers is None:
            raise ValueError("Explicit passing fresh guest IIG/header components required")
        iig_path = self.args.iig.resolve() / "iig-component.json"
        iig = json.loads(iig_path.read_text())
        header_path = self.args.headers.resolve() / "headers-component.json"
        headers = json.loads(header_path.read_text())
        if any(component["prepared"]["sha256"] != self.report["prepared_parent"]["sha256"] for component in [iig, headers]):
            raise ValueError("Handoff source/config components differ")
        for pair in iig["pairs"].values():
            if sha(Path(pair["source"])) != pair["source_sha256"] or any(sha(Path(path)) != expected for path, expected in pair["outputs"].items()):
                raise ValueError("Fresh public IIG source/product changed")
        header_manifest = Path(headers["manifest"])
        if sha(header_manifest) != headers["manifest_sha256"]:
            raise ValueError("Selected guest installed-header manifest changed")
        installed = json.loads(header_manifest.read_text())
        generated_headers = {}
        for row in installed:
            if row["status"] == "installed" and sha(Path(row["output"])) != row["output_sha256"]:
                raise ValueError("Installed guest header changed")
            if row["status"] not in ["installed", "genuine_filter_removed_empty_body"]:
                raise ValueError("Actual selected header entry is incomplete")
            if row.get("generated_input"):
                source = Path(row["generated_origin"])
                if sha(source) != row["source_sha256"]:
                    raise ValueError("Actual unfiltered guest generation input changed")
                relative = Path(row["declaration"]).parent.relative_to(self.kernel) / row["name"]
                if str(relative) in generated_headers and sha(Path(generated_headers[str(relative)])) != sha(source):
                    raise ValueError("Conflicting unfiltered guest header producer")
                generated_headers[str(relative)] = str(source)
        foundation = json.loads((self.args.foundation.resolve() / "foundation-component.json").read_text())
        declarations = json.loads((Path(foundation["exports"]["path"]).parent / "source-export-manifest.json").read_text())
        exported = []
        for row in declarations:
            if row["status"] != "requires_genuine_generation":
                continue
            relative = Path(row["source_directory"]).relative_to(self.kernel) / row["name"]
            source = Path(generated_headers[str(relative)]) if str(relative) in generated_headers else None
            if source is None or not source.is_file():
                raise ValueError("Unfiltered source-export producer remains unavailable: " + str(relative))
            target = self.out / "EXPORT_HDRS" / Path(row["output"]).relative_to(Path(foundation["exports"]["root"]))
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
            exported.append({"declaration": row, "source": str(source), "output": str(target), "sha256": sha(target)})
        # Reuse only this guest's real generated sanitizer setup product.
        setup_report = json.loads((self.args.setup.resolve() / "report.json").read_text())
        original = Path(setup_report["sanitizer_ignorelist"]["path"])
        if sha(original) != setup_report["sanitizer_ignorelist"]["sha256"]:
            raise ValueError("Fresh guest generated ignorelist changed")
        ignorelist = self.out / "san/kasan-blacklist-arm64"; ignorelist.parent.mkdir(); shutil.copyfile(original, ignorelist)
        self.object_inventory()
        manifest = json.loads((self.out / "guest-object-manifest.json").read_text())
        config_products = {}
        for component, config in self.configs.items():
            root = Path(config["root"])
            config_products[component] = {str(path): sha(path) for path in root.iterdir() if path.is_file()}
        for row in manifest:
            source = Path(row["source"])
            if row["generated_input"]:
                relative = source.relative_to(self.out / "build")
                if relative.parts[0] == "osfmk":
                    source = self.mig_internal / Path(*relative.parts[1:])
                elif relative.parts[0] == "bsd":
                    source = Path(self.configs["bsd"]["root"]) / "ioconf.c" if relative.name == "ioconf.c" else self.syscalls_include / relative.name
                elif relative.parts[:2] == ("iokit", "DriverKit"):
                    source = Path(iig["root"]) / relative.name
                else:
                    raise ValueError("Unmapped actual generated guest object input")
            if not source.is_file() or not row["genuine_expanded_recipe"]:
                raise ValueError("Next guest object lacks actual source or genuine recipe: " + row["id"])
            row.update(bound_source=str(source), bound_source_sha256=sha(source), status="genuine_source_and_recipe_bound_not_compiled")
            command = shlex.split(row["genuine_expanded_recipe"])
            command[-1] = str(source)
            for flag, value in [("-o", "@NEXT_OBJECT_DIR@/" + row["id"]), ("-MF", "@NEXT_DEPENDENCY_DIR@/" + row["id"] + ".d")]:
                if flag in command:
                    command[command.index(flag) + 1] = value
                else:
                    command += [flag, value]
            roots = [Path(self.guest_setup["version"]["header"]).parents[1], Path(self.guest_setup["assym"]["header"]).parent, Path(iig["root"]).parent]
            row["next_owned_compile_argv_template"] = [command[0], *[item for root in roots for item in ["-I", str(root)]], *self.include_flags(row["component"]), *command[1:]]
            row["execution_requires_new_plan_and_resource_lease"] = True
        write(self.out / "next-full-object-manifest.json", manifest)
        write(self.out / "generated-export-manifest.json", exported)
        write(self.out / "guest-configuration-products.json", config_products)
        self.report["next_full_object_inputs"] = {"selected": len(manifest), "generated_sources_bound": sum(row["generated_input"] for row in manifest), "generated_raw_exports": len(exported),
            "compiled_by_this_handoff": 0, "native_objects_or_board_products_reused": False, "explicit_sdk_identity": False}
        self.report["handoff_parents"] = {"iig": {"path": str(iig_path), "sha256": sha(iig_path)}, "headers": {"path": str(header_path), "sha256": sha(header_path)}}
        write(self.out / "handoff-component.json", {"prepared": self.report["prepared_parent"], "parents": self.report["handoff_parents"], "summary": self.report["next_full_object_inputs"],
            "object_manifest": str(self.out / "next-full-object-manifest.json"), "object_manifest_sha256": sha(self.out / "next-full-object-manifest.json"),
            "raw_exports": str(self.out / "EXPORT_HDRS"), "installed_headers": headers["roots"], "configuration_products": str(self.out / "guest-configuration-products.json"),
            "sdk_qualified": False, "private_apple_abi_qualified": False, "full_kernel_build_or_link": False, "guest_executed": False})


    def verify(self):
        if self.args.qualification is None:
            raise ValueError("Supply explicit --qualification descriptor for read-only verification")
        descriptor_path = self.args.qualification.resolve()
        qualified = json.loads(descriptor_path.read_text())
        if qualified["implementation"]["sha256"] != sha(Path(__file__)):
            raise ValueError("Scoped implementation differs from qualified evidence")
        index_path = self.main / qualified["artifact_index"]
        if sha(index_path) != qualified["artifact_index_sha256"]:
            raise ValueError("Qualified artifact index changed")
        index = json.loads(index_path.read_text())
        for name, expected in index["files"].items():
            if sha(self.main / name) != expected:
                raise ValueError("Qualified actual artifact/input changed: " + name)
        prepared = json.loads((self.main / qualified["prepared_component"]).read_text())
        source_descriptor = self.main / "fixtures/public/avf-kernel-source/qualified-source.json"
        if sha(source_descriptor) != "6eb1afcc895ecbb852ecea5331c3818e398302ca1bd5701b8609a35ba8a62ec4":
            raise ValueError("Accepted source-composition descriptor changed")
        source_component = json.loads(source_descriptor.read_text())
        composition_path = self.main / source_component["composition_manifest"]
        if sha(composition_path) != source_component["composition_manifest_sha256"]:
            raise ValueError("Accepted source-composition manifest changed")
        qemu = json.loads(composition_path.read_text())["profiles"]["qemu"]
        if qemu["canonical_output_tree"] != QEMU_TREE or qemu["source_config_sha256"] != QEMU_CONFIG:
            raise ValueError("Explicit accepted QEMU source/config profile changed")
        for path, files in [(Path(prepared["kernel_root"]), qemu["files"]), (Path(prepared["donor_root"]), qemu["donor_files"]),
                            (Path(qemu["xnu_root"]), qemu["files"]), (Path(qemu["donor_root"]), qemu["donor_files"])]:
            if snapshot(path) != files:
                raise ValueError("Prepared or immutable parent guest source/config changed")
        for name, report in qualified["accepted_phase_reports"].items():
            phase = json.loads((self.main / report).read_text())
            if phase["outcome"] != "pass":
                raise ValueError("Bounded phase is not an actual pass: " + name)
            if name == "public-iig" and (phase.get("controller_rss_budget_bytes") != 256 * 1024**2 or
                                          not 0 < phase.get("host_controller_peak_rss_bytes", 0) <= 256 * 1024**2):
                raise ValueError("IIG library hashing/generation lacks corrected bounded-controller evidence")
        objects = {}
        for name in qualified["accepted_object_records"]:
            data = json.loads((self.main / name).read_text())
            rows = data["representative_compiles"] if isinstance(data, dict) else data
            for row in rows:
                if not row["actual_arm64_object"] or sha(Path(row["object"])) != row["object_sha256"] or sha(Path(row["source"])) != row["source_sha256"]:
                    raise ValueError("Actual guest object/source witness is incomplete or changed")
                import struct
                magic, cpu, subtype, kind = struct.unpack("<4I", Path(row["object"]).read_bytes()[:16])
                if (magic, cpu, kind) != (0xfeedfacf, 0x100000c, 1):
                    raise ValueError("Actual object witness is not ARM64 Mach-O")
                for path, expected in row["dependencies"].items():
                    if sha(Path(path)) != expected:
                        raise ValueError("Actual representative dependency changed")
                objects[row["id"]] = row
        if len(objects) != 10 or not objects["libkern/OSData.cpo"]["allocator_metadata_sections"]:
            raise ValueError("Bounded real guest/allocator metadata coverage is incomplete")
        controls = json.loads((self.main / qualified["accepted_phase_reports"]["controls"]).read_text())["negative_controls"]
        if len(controls) != 4 or not all(row["pass"] for row in controls):
            raise ValueError("Actual changed-input/metadata controls are incomplete")
        manifest = json.loads((self.main / qualified["next_object_manifest"]).read_text())
        if len(manifest) != 1080 or sum(row["generated_input"] for row in manifest) != 55:
            raise ValueError("Actual coherent guest object source selection changed")
        for row in manifest:
            if sha(Path(row["bound_source"])) != row["bound_source_sha256"] or not row["execution_requires_new_plan_and_resource_lease"]:
                raise ValueError("Next guest source binding changed or lacks execution boundary")
        boundaries = ["sdk_qualified", "private_apple_abi_qualified", "full_kernel_build_or_link", "guest_executed", "device_executed", "native_device_qualified"]
        if any(qualified[name] is not False for name in boundaries):
            raise ValueError("Bounded header/source result was promoted to an unqualified SDK/ABI/kernel/device claim")
        self.report["read_only_verification"] = {"qualified_descriptor": str(descriptor_path), "descriptor_sha256": sha(descriptor_path), "artifacts_rehashed": len(index["files"]),
            "actual_guest_representative_objects": len(objects), "actual_next_guest_sources": len(manifest), "compiler_or_generator_started": False,
            "prepared_and_parent_guest_source_unchanged": True, "selected_private_apple_abi_qualified": False, "sdk_qualified": False, "kernel_or_guest_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="AVFHEAD-001")
    parser.add_argument("--mode", choices=["prepare", "generate", "foundation", "mig", "syscalls", "setup", "iig", "header-inventory", "headers", "objects", "representatives", "controls", "header-residual", "handoff", "verify"], required=True)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--generated", type=Path)
    parser.add_argument("--foundation", type=Path)
    parser.add_argument("--mig", type=Path)
    parser.add_argument("--syscalls", type=Path)
    parser.add_argument("--setup", type=Path)
    parser.add_argument("--iig", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--headers", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--only", action="append", help="Explicit subset of the bounded genuine representative set")
    args = parser.parse_args()
    job = Headers(args)
    try:
        if args.mode == "prepare":
            job.prepare()
        elif args.mode == "generate":
            job.generate()
        elif args.mode == "foundation":
            job.foundation()
        elif args.mode == "mig":
            job.mig()
        elif args.mode == "syscalls":
            job.syscalls()
        elif args.mode == "setup":
            job.setup()
        elif args.mode == "iig":
            job.iig()
        elif args.mode == "header-inventory":
            job.header_inventory()
        elif args.mode == "headers":
            job.headers()
        elif args.mode == "objects":
            job.objects()
        elif args.mode == "representatives":
            job.representatives()
        elif args.mode == "controls":
            job.controls()
        elif args.mode == "header-residual":
            job.header_residual()
        elif args.mode == "handoff":
            job.handoff()
        else:
            job.verify()
        job.report["outcome"] = "pass"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        job.report["error"] = repr(error)
        job.report["outcome"] = "inconclusive" if isinstance(error, RuntimeError) else "fail"
    usage = controller_usage()
    peak = usage["current_image_peak_rss_bytes"]
    job.report["controller_finish_usage"] = usage
    job.report["controller_peak_source"] = "/proc/self/status VmHWM for the current executable image; raw pre-exec rusage retained separately"
    job.report["host_controller_peak_rss_bytes"] = peak
    job.report["controller_rss_budget_bytes"] = 256 * 1024**2
    if peak > 256 * 1024**2:
        job.report["outcome"] = "inconclusive"
        job.report["controller_resource_error"] = "Controller RSS exceeded 256MiB; integrity alone is not a resource-qualified pass"
    job.report["finished_at"] = stamp()
    write(job.out / "report.json", job.report)
    print(json.dumps({k: job.report.get(k) for k in ["outcome", "error", "kernel_root"]}, indent=2))
    return 0 if job.report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
