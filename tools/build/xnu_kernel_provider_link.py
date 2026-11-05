#!/usr/bin/env python3
"""Measure an intact native kernel link with the accepted current providers."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import resource
import shlex
import shutil
import signal
import subprocess
import struct
import sys
import time

sys.dont_write_bytecode = True
os.environ.update(GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0", PYTHONDONTWRITEBYTECODE="1")
OWNER = "codex-team-kernel-link-20261105-ax"
REPLACEMENTS = {"osfmk/caches_asm.o", "osfmk/start.o", "osfmk/model_dep.o", "pexpert/pe_init.o"}
PTHREAD_SHA = "d5f047488be1806e7e30af166312173b08f56bbbcff85340c1c5f3d28514b0d1"
RSS_LIMIT = 1024 * 1024


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def mem_available():
    text = Path("/proc/meminfo").read_text()
    return int(re.search(r"^MemAvailable:\s+(\d+) kB$", text, re.M)[1])


def rss(pid):
    try:
        match = re.search(r"^VmRSS:\s+(\d+) kB$", Path(f"/proc/{pid}/status").read_text(), re.M)
        return int(match[1]) if match else 0
    except (OSError, ProcessLookupError):
        return 0


def group_rss(group):
    total = rss(os.getpid())
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group:
                total += rss(path.name)
        except (OSError, ValueError, ProcessLookupError):
            pass
    return total


class ProviderLink:
    def __init__(self, args, native, symbol_reader):
        self.args, self.native, self.external_symbols = args, native, symbol_reader
        self.root = args.root.resolve()
        self.worktree = Path(__file__).resolve().parents[2]
        if self.worktree == self.root or not self.worktree.is_relative_to(self.root / "worktrees"):
            raise ValueError("Execution requires a separate worktree below the primary checkout")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run):
            raise ValueError("One plain fresh run name required")
        self.out = self.worktree / "artifacts/kernel-provider-link" / args.run
        self.out.mkdir(parents=True, exist_ok=False)
        self.stage = self.out / "stage"
        self.stage.mkdir()
        self.ledger = json.loads((self.root / "state/lab.json").read_text())
        self.report = dict(kind="host-test", origin="local-host", outcome="fail", recorded_at=stamp(),
                           commands=[], checks=[], parents={}, source_inputs={}, tools_sha256={},
                           device_executed=False, sdk_used=False, global_install=False,
                           full_kernel_qualified=False, full_archive_link_qualified=False,
                           full_crypto_qualified=False, apple_private_abi_qualified=False,
                           apple_interoperability_qualified=False, runtime_qualified=False,
                           native_device_qualified=False, experimental_generator=True)
        shutil.copyfile(__file__, self.out / "builder.py")

    def check(self, name, ok, **data):
        self.report["checks"].append(dict(name=name, pass_check=bool(ok), **data))
        if not ok:
            raise ValueError("Failed invariant: " + name)

    def read(self, path):
        return json.loads((self.root / path).read_text())

    def capsule(self, identifier):
        entry = next(e for e in self.ledger["experiments"] if e["id"] == identifier)
        path = self.root / entry["evidence"]
        if sha(path) != entry["evidence_sha256"]:
            raise ValueError("Changed registered capsule: " + identifier)
        doc = json.loads(path.read_text())
        if doc["outcome"] != "pass":
            raise ValueError("Passing capsule required: " + identifier)
        hashes = doc.get("sha256", doc.get("hashes", {}))
        if not hashes:
            raise ValueError("Artifact hashes required: " + identifier)
        for name, digest in hashes.items():
            if sha(self.root / name) != digest:
                raise ValueError("Changed capsule artifact: " + name)
        self.report["parents"][identifier] = dict(path=entry["evidence"], sha256=sha(path),
                                                  artifacts_verified=len(hashes))
        return doc

    def run(self, argv, label, cwd=None, timeout=120):
        argv = list(map(str, argv))
        cwd = Path(cwd or self.out)
        if timeout <= 0:
            raise ValueError("Positive subprocess deadline required")
        timeout = min(timeout, 120)  # Tighten inherited helper deadlines to this task budget.
        available = mem_available()
        if available < 4 * 1024 * 1024:
            raise RuntimeError("Deferred: MemAvailable below 4 GiB")
        executable = shutil.which(argv[0])
        if executable:
            self.report["tools_sha256"][str(Path(executable).resolve())] = sha(executable)
        so, se = self.out / (label + ".stdout.txt"), self.out / (label + ".stderr.txt")
        started, start = stamp(), time.monotonic()
        peak, reason = rss(os.getpid()), None
        print(label, flush=True)
        with so.open("wb") as stdout, se.open("wb") as stderr:
            proc = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr,
                                    env=dict(os.environ, LC_ALL="C", MAKEFLAGS="-j1"), start_new_session=True)
            while proc.poll() is None:
                peak = max(peak, group_rss(proc.pid))
                if peak > RSS_LIMIT:
                    reason = "aggregate_rss_limit"
                elif time.monotonic() - start > timeout:
                    reason = "wall_timeout"
                if reason:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    break
                time.sleep(0.02)
            code = proc.wait()
        command = dict(argv=argv, cwd=str(cwd), started_at=started, ended_at=stamp(), exit_code=code,
                       stop_reason=reason, timeout_seconds=timeout, mem_available_kib=available,
                       peak_owned_group_plus_harness_rss_kib=peak, stdout=str(so.relative_to(self.root)),
                       stderr=str(se.relative_to(self.root)), stdout_sha256=sha(so), stderr_sha256=sha(se))
        command["argv_sha256"] = hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()
        self.report["commands"].append(command)
        if reason:
            raise RuntimeError("Owned command terminated: " + reason)
        return code, so.read_text(errors="replace"), se.read_text(errors="replace")

    def must(self, argv, label, **kwargs):
        code, stdout, _ = self.run(argv, label, **kwargs)
        if code:
            raise RuntimeError("Command failed; retained diagnostics: " + label)
        return stdout

    def make_args(self, component, script):
        return self.native.LinkInputs.make_args(self, component, script)

    def query_link(self):
        return self.native.LinkInputs.query_link(self)

    def validate_graph(self, rows):
        original = {r["id"]: r for r in self.read("artifacts/xnu-kernel-iig-objects/audit-session1/compiled-objects.json")}
        if len(rows) != 982 or len({r["id"] for r in rows}) != 982 or set(original) != {r["id"] for r in rows}:
            raise ValueError("Exact 982-object identity set required")
        replaced = {r["id"] for r in rows if r["output"] != original[r["id"]]["output"]}
        if replaced != REPLACEMENTS:
            raise ValueError("Exactly four SGAP replacements required; stale graph rejected")
        for row in rows:
            for field in ("source", "output"):
                if sha(self.root / row[field]) != row[field + "_sha256"]:
                    raise ValueError("Changed current source/object: " + row["id"])
            with (self.root / row["output"]).open("rb") as stream:
                header = stream.read(32)
            if len(header) != 32 or struct.unpack_from("<I", header)[0] != 0xfeedfacf or struct.unpack_from("<I", header, 4)[0] != 0x100000c or struct.unpack_from("<I", header, 12)[0] != 1:
                raise ValueError("Actual ARM64 object required")
        return replaced

    def inputs(self):
        tasks = {t["id"]: t for t in self.ledger["tasks"]}
        task = tasks["KRN-024"]
        self.check("owned-task-and-accepted-dependencies", task["owner"] == OWNER and task["status"] == "in_progress"
                   and all(tasks[n]["status"] == "done" for n in ["KRN-020", "KRN-021", "KRN-022", "REV-006"]))
        plan = next(e for e in self.ledger["experiments"] if e["id"] == self.args.experiment)
        self.check("registered-owned-experiment", plan["owner"] == OWNER and plan["task"] == "KRN-024"
                   and plan["status"] == "planned")
        for identifier in ["KLINK-007", "KLINK-009", "KLINK-011", "KLINK-012", "SGAP-001", "SGAP-006",
                           "FHDR-006", "PTHP-007", "PTHP-012", "PTHPREV-001"]:
            self.capsule(identifier)
        self.sgap = self.read("fixtures/public/xnu-kernel-symbol-gaps/qualified-component.json")
        for item in self.sgap["coherent_graph"].values():
            if sha(self.root / item["path"]) != item["sha256"]:
                raise ValueError("Changed SGAP graph witness")
        self.compiled = self.read(self.sgap["coherent_graph"]["compiled-objects"]["path"])
        replaced = self.validate_graph(self.compiled)
        self.by_id = {row["id"]: row for row in self.compiled}
        self.dependencies = self.read(self.sgap["coherent_graph"]["dependency-files"]["path"])
        for path, digest in self.dependencies.items():
            if sha(self.root / path) != digest:
                raise ValueError("Changed dependency: " + path)
        replacement_deps = self.read(self.sgap["coherent_graph"]["replacement-object-dependencies"]["path"])
        for item in replacement_deps.values():
            if sha(self.root / item["depfile"]) != item["sha256"] or not set(item["inputs"]) <= self.dependencies.keys():
                raise ValueError("Replacement depfile/dependency mismatch")
        self.check("current-982-objects-four-replacements-and-3156-dependencies", len(self.dependencies) == 3156
                   and set(replacement_deps) == REPLACEMENTS, replacements=sorted(replaced), dependencies=len(self.dependencies))
        self.baseline = self.read("artifacts/xnu-kernel-link-inputs/baseline-session5/report.json")
        self.object_report = self.read("artifacts/xnu-kernel-objects/compile-session2/report.json")
        pthread = self.read("artifacts/xnu-kernel-pthread-profile/compile-session2/report.json")
        self.pthread = self.read("fixtures/public/xnu-kernel-pthread-profile/qualified-component.json")
        self.firehose = self.read("fixtures/public/xnu-kernel-firehose-headers/qualified-component.json")["provider"]
        command = next(c for c in pthread["commands"] if c["argv"] and "clang" in c["argv"][0] and "-c" in c["argv"])
        self.compiler = Path(command["argv"][0])
        production = self.read("artifacts/xnu-kernel-symbol-gaps/production-session1/report.json")
        self.check("same-current-compiler-and-non-LTO-native-pthread-profile", sha(self.compiler) == pthread["compiler_sha256"]
                   == production["compiler_sha256"] and "-DXNU_NO_TYPE_BUILTINS=0" in pthread["pthread_compile_profile"]["flags"]
                   and all(x in pthread["pthread_compile_profile"]["flags"] for x in
                           ["-Dpthread_kern=pthread_kext_kern", "-Dcurrent_uthread=pthread_kext_current_uthread"]))
        self.report["pthread_compile_profile"] = pthread["pthread_compile_profile"]
        self.report["compiler"] = dict(path=str(self.compiler.relative_to(self.root)), sha256=sha(self.compiler))
        self.ld = self.root / self.baseline["tools"]["linker"]
        self.libtool = self.root / self.baseline["tools"]["libtool"]
        self.segtool = self.root / self.baseline["tools"]["setsegname"]
        for name, path in [("linker", self.ld), ("libtool", self.libtool), ("setsegname", self.segtool)]:
            if sha(path) != self.baseline["tools"][name + "_sha256"]:
                raise ValueError("Changed genuine native tool: " + name)
            self.report["tools_sha256"][str(path)] = sha(path)
        self.kernel = self.native.KERNEL
        self.report["graph"] = self.sgap["coherent_graph"]
        self.report["dependencies"] = dict(count=len(self.dependencies), manifest=self.sgap["coherent_graph"]["dependency-files"])
        for path, digest in self.baseline["link_source_inputs"].items():
            if sha(self.root / path) != digest:
                raise ValueError("Changed original native link source: " + path)
            self.report["source_inputs"][path] = digest
        for path in [self.root / "tools/build/xnu_kernel_link_inputs.py", self.root / "tools/build/xnu_kernel_direct_tail.py",
                     self.root / "tools/build/xnu_kernel_symbol_gaps.py", self.worktree / "tools/build/xnu_kernel_provider_link.py"]:
            self.report["source_inputs"][str(path.relative_to(self.root))] = sha(path)
        dump(self.out / "current-compiled-objects.json", self.compiled)
        dump(self.out / "current-dependency-files.json", self.dependencies)
        revision = "fa9443738c1a18accef4244732ec6d6ee97a8133"
        driver_sources = {}
        for index, name in enumerate(["src/clang/lib/Driver/Driver.cpp", "src/clang/lib/Driver/ToolChains/Darwin.cpp",
                                      "src/clang/lib/Driver/ToolChain.cpp"]):
            self.must(["git", "-C", self.root / "references/xnu-tapi", "show", revision + ":" + name], "pinned-driver-source-" + str(index))
            blob = self.out / ("pinned-driver-source-" + str(index) + ".stdout.txt")
            actual = self.root / "artifacts/xnu-compiler-types/frontend-session1/compiler-source" / name
            self.check("unchanged-pinned-driver-source-" + str(index), sha(blob) == sha(actual))
            driver_sources[name] = dict(revision=revision, sha256=sha(blob), compiler_source=str(actual.relative_to(self.root)))
        driver = (self.out / "pinned-driver-source-0.stdout.txt").read_text()
        darwin = (self.out / "pinned-driver-source-1.stdout.txt").read_text()
        self.check("source-explains-reserved-cc-kext-rewrite-and-optional-runtime", 'Value == "cc_kext"' in driver
                   and "OPT_Z_reserved_lib_cckext" in driver and "libclang_rt.cc_kext_ios.a" in darwin and "if (getVFS().exists(P))" in darwin)
        directory = Path(self.must([self.compiler, "-print-resource-dir"], "actual-compiler-resource-directory").strip())
        runtime = directory / "lib/darwin/libclang_rt.cc_kext_ios.a"
        self.report["compiler_runtime_policy"] = dict(primary_sources=driver_sources, resource_directory=str(directory),
            expected_runtime=str(runtime), runtime_exists=runtime.is_file(),
            scope="Clang reserved compiler-support library policy; does not identify this library with corecrypto or qualify a runtime archive")

    def metadata(self):
        # Adapted from KRN-020 LinkInputs.full_link_attempt's metadata stage.
        # Only fresh native generators execute; its old full-link object inputs are never used.
        query = self.out / "query-exports.mk"
        components = ["BSDKernel", "IOKit", "Libkern", "Mach", "MACFramework", "Unsupported", "Private"]
        keys = ["EXPORTS_FILES", "SYMBOL_COMPONENT_LIST", "SYMBOL_SET_PLIST_COMPONENT_LIST", "Kasan_EXPORTS", "Kcov_EXPORTS"] + [c + "_EXPORTS" for c in components]
        query.write_text("include " + str(self.kernel / "config/Makefile") + "\n" + "".join("$(info S24_EXPORT|" + k + "|$(" + k + "))\n" for k in keys) + "\n.PHONY: s24_query\ns24_query: ;\n")
        args = self.report["link_query_argv"].copy()
        args[args.index("-f") + 1] = str(query)
        replacements = {"OBJPATH": str(self.stage), "TARGET": str(self.stage), "SOURCE": str(self.kernel / "config") + "/", "RELATIVE_SOURCE_PATH": "./config"}
        args = [next((k + "=" + v for k, v in replacements.items() if a.startswith(k + "=")), a) for a in args]
        text = self.must(args, "genuine-config-export-query")
        values = {a[1]: a[2].split() for line in text.splitlines() if line.startswith("S24_EXPORT|") and len(a := line.split("|", 2)) == 3}
        self.check("exact-native-export-selection", set(values) == set(keys) and values["SYMBOL_COMPONENT_LIST"] == components)
        exports = [self.kernel / "config" / n for n in values["EXPORTS_FILES"]] + [Path(n) for k in ["Kasan_EXPORTS", "Kcov_EXPORTS"] for n in values[k]]
        for name, script in [("all-kpi.exp", "generate_linker_exports.sh"), ("all-alias.exp", "generate_linker_aliases.sh")]:
            self.must(["sh", self.kernel / "config" / script, self.stage / name, *exports], "genuine-" + name, cwd=self.kernel / "config")
        generated = []
        for component in values["SYMBOL_SET_PLIST_COMPONENT_LIST"]:
            original = self.kernel / "config/System.kext/PlugIns" / (component + ".kext") / "Info.plist"
            info = self.out / (component + "-Info.plist")
            shutil.copyfile(original, info)
            self.report["source_inputs"][str(original.relative_to(self.root))] = sha(original)
            self.must(["env", "SRCROOT=" + str(self.kernel), "OBJROOT=" + str(self.out), "TARGET=" + str(self.stage),
                       "CURRENT_KERNEL_CONFIG_LC=release", "perl", self.kernel / "config/newvers.pl", info], "genuine-newvers-" + component)
            output = self.out / (component + ".symbolset.plist")
            self.must(["sh", self.kernel / "config/generate_symbolset_plist.sh", output, info, *map(Path, values[component + "_EXPORTS"])],
                      "genuine-symbolset-" + component, cwd=self.kernel / "config")
            plistlib.loads(output.read_bytes())
            generated.append(output)
        xml = self.out / "symbolsets.xml.plist"
        self.must(["sh", self.kernel / "config/generate_combined_symbolsets_plist.sh", xml, *generated], "genuine-combined-symbolsets")
        value = plistlib.loads(xml.read_bytes())
        binary = self.stage / "symbolsets.plist"
        binary.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_BINARY, sort_keys=False))
        self.check("nine-native-symbolsets-and-fallback", len(value["SymbolsSets"]) == 9 and value["WeakRefFallbackSymbol"] == {"SymbolName": "_gOSKextUnresolved"})
        self.check("host-plist-semantic-roundtrip", plistlib.loads(binary.read_bytes()) == value)
        self.alias_path = self.stage / "all-alias.exp"
        self.aliases = {parts[1]: parts[0] for line in self.alias_path.read_text().splitlines() if len(parts := line.split()) == 2}
        accepted = self.read("artifacts/xnu-kernel-pthread-profile/compile-session2/report.json")
        self.check("exact-accepted-native-alias-bytes", sha(self.alias_path) == accepted["alias_list"]["sha256"])
        for name, row in self.pthread["native_vm_aliases"].items():
            self.check("native-alias-" + name, self.aliases.get(name) == row["target"])
        self.report["metadata"] = dict(query_values=values, aliases=len(self.aliases), native_plutil_oracle_qualified=False,
            serialization="Python stdlib plistlib binary1, semantic roundtrip only",
            outputs={str(p.relative_to(self.root)): sha(p) for p in [self.stage / "all-kpi.exp", self.alias_path, xml, binary]})
        self.report["source_inputs"].update({str(p.relative_to(self.root)): sha(p) for p in exports})

    def providers(self):
        native_providers, native_consumers = defaultdict(list), defaultdict(list)
        for row in self.compiled:
            for symbol in self.external_symbols(self.root / row["output"]):
                (native_providers if symbol["defined"] else native_consumers)[symbol["name"]].append(
                    dict(object=row["id"], weak=symbol["weak"], common=symbol["common"], alias=symbol["alias"]))
        expected = self.read(self.sgap["coherent_graph"]["symbol-providers"]["path"])
        consumers = self.read(self.sgap["coherent_graph"]["symbol-consumers"]["path"])
        self.check("all982-actual-current-nlists-match-recorded-graph", native_providers == expected and native_consumers == consumers)
        self.library = self.out / "available-libraries"
        self.library.mkdir()
        manifests = {"firehose_kernel": (self.firehose["archive"], self.firehose["archive_sha256"]),
                     "pthread_kext": (self.pthread["archive"], self.pthread["archive_sha256"])}
        self.check("accepted-current-pthread-archive-identity", manifests["pthread_kext"][1] == PTHREAD_SHA)
        inventories = {}
        all_defs = set(native_providers)
        all_required = {n for n, uses in native_consumers.items() if any(not u["weak"] for u in uses)}
        for name, (path, digest) in manifests.items():
            original = self.root / path
            if sha(original) != digest:
                raise ValueError("Changed genuine provider archive: " + name)
            copy = self.library / ("lib" + name + ".a")
            shutil.copyfile(original, copy)
            members = self.native.archive_members(copy.read_bytes())
            text = self.must([self.native.NDK / "llvm-nm", "--extern-only", "--defined-only", "--just-symbol-name", copy], name + "-definitions")
            defs = {line for line in text.splitlines() if line and not line.endswith(":")}
            text = self.must([self.native.NDK / "llvm-nm", "--undefined-only", "--just-symbol-name", copy], name + "-imports")
            imports = {line for line in text.splitlines() if line and not line.endswith(":")} - defs
            missing = sorted(n for n in imports if self.aliases.get(n, n) not in native_providers)
            overlap = sorted(defs & all_defs)
            self.check("real-provider-import-closure-" + name, not missing and not overlap, definitions=len(defs), imports=len(imports))
            inventories[name] = dict(original=path, archive=str(copy.relative_to(self.root)), sha256=sha(copy),
                members=[dict(ordinal=i, name=n, sha256=hashlib.sha256(data).hexdigest()) for i, (n, data) in enumerate(members)],
                definitions=sorted(defs), external_imports=sorted(imports), missing_from_current_kernel_after_native_aliases=missing,
                overlap=overlap)
            all_defs |= defs
            all_required |= imports
        remaining = sorted(n for n in all_required if self.aliases.get(n, n) not in all_defs)
        old_missing = self.read(self.sgap["coherent_graph"]["unresolved-symbols"]["path"])
        self.check("only13-previously-measured-linker-boundaries-remain-in-object-provider-subset",
                   len(remaining) == 13 and set(remaining) <= old_missing.keys()
                   and all(n.startswith(("section$", "segment$")) or n in {"___dso_handle", "__mh_execute_header"} for n in remaining))
        self.check("only-two-genuine-provider-archives-supplied", sorted(p.name for p in self.library.iterdir()) == ["libfirehose_kernel.a", "libpthread_kext.a"])
        self.report["providers"] = inventories
        self.report["remaining_object_provider_names"] = remaining
        dump(self.out / "provider-inventories.json", inventories)

    def validate_link(self, argv, rows=None, aliases=None):
        rows = rows if rows is not None else self.compiled
        self.validate_graph(rows)
        expected = [str(self.stage / c / "RELEASE" / name) for c in self.report["link_variables"]["COMPONENT_LIST"].split()
                    for name in self.report["component_filelists"][c]["objects"]]
        filelist = Path(argv[argv.index("-filelist") + 1])
        if filelist.read_text().splitlines() != expected or len(expected) != 978:
            raise ValueError("Exact current native filelist/order required")
        for lib in ["cc_kext", "firehose_kernel", "pthread_kext"]:
            if argv.count("-l" + lib) != 1:
                raise ValueError("Required native library absent or repeated: " + lib)
        for bad in ["-undefined", "dynamic_lookup", "-flat_namespace", "-r"]:
            if bad in argv or any(a.startswith("-Wl,") and bad in a[4:].split(",") for a in argv):
                raise ValueError("No downgraded link semantics")
        mapping = aliases if aliases is not None else self.aliases
        for name, row in self.pthread["native_vm_aliases"].items():
            if mapping.get(name) != row["target"]:
                raise ValueError("Wrong native VM provider alias")
        if sha(self.library / "libpthread_kext.a") != PTHREAD_SHA:
            raise ValueError("Wrong pthread provider archive")
        for row in rows:
            stage = self.report["staged_objects"][row["id"]]
            if stage["original"] != row["output"] or stage["original_sha256"] != row["output_sha256"] or sha(self.root / stage["output"]) != stage["output_sha256"]:
                raise ValueError("Staged object does not bind the current graph")

    def controls_and_link(self):
        variables = self.report["link_variables"]
        self.check("native-selected-BUILD_LTO-zero", variables["USE_LTO"] == "0" and variables["LD_KERNEL_LIBS"] == "-lcc_kext")
        flags = shlex.split(variables["LDFLAGS_KERNEL"]) + shlex.split(variables["LDFLAGS_KERNEL_ONLY"])
        output = self.out / "mach.release.e1s.unstripped"
        argv = [str(self.compiler), "-L" + str(self.library), "--ld-path=" + str(self.ld), "-nostdlib", *flags,
                "-filelist", self.report["archive"]["filelist"], str(self.stage / "version.o"),
                str(self.stage / "lastkerneldataconst.o"), str(self.stage / "lastkernelconstructor.o"),
                str(self.stage / "nonlto.o"), "-o", str(output), *shlex.split(variables["LD_KERNEL_LIBS"]),
                *shlex.split(variables["LD_KERNEL_ARCHIVES"])]
        # Helpers report paths relative to the primary root; Clang needs absolute paths.
        argv[argv.index("-filelist") + 1] = str(self.root / self.report["archive"]["filelist"])
        self.validate_link(argv)
        controls = []
        def reject(name, function):
            try:
                function()
            except (ValueError, FileNotFoundError) as error:
                controls.append(dict(name=name, rejected=True, reason=str(error)))
            else:
                raise ValueError("Wrong-input control accepted: " + name)
        stale = self.read("artifacts/xnu-kernel-iig-objects/audit-session1/compiled-objects.json")
        reject("old-pre-SGAP-graph", lambda: self.validate_link(argv, rows=stale))
        reject("missing-required-cc_kext", lambda: self.validate_link([a for a in argv if a != "-lcc_kext"]))
        wrong = dict(self.aliases, _mach_vm_map="_mach_vm_allocate_external")
        reject("wrong-real-VM-provider", lambda: self.validate_link(argv, aliases=wrong))
        fake = self.out / "negative-reordered.filelist"
        lines = Path(argv[argv.index("-filelist") + 1]).read_text().splitlines()
        fake.write_text("\n".join(list(reversed(lines))) + "\n")
        altered = argv.copy()
        altered[altered.index("-filelist") + 1] = str(fake)
        reject("wrong-real-object-order", lambda: self.validate_link(altered))
        archive = self.library / "libpthread_kext.a"
        historical = self.read("fixtures/public/open-kernel-inputs/reusable-components.json")["pthread"]["archive"]
        shutil.copyfile(self.root / historical["path"], archive)
        try:
            reject("wrong-historical-pthread-archive", lambda: self.validate_link(argv))
        finally:
            shutil.copyfile(self.root / self.pthread["archive"], archive)
        self.report["negative_controls"] = controls
        self.validate_link(argv)
        self.must([*argv, "-###"], "genuine-native-link-driver-expansion")
        expansion = (self.out / "genuine-native-link-driver-expansion.stderr.txt").read_text().splitlines()
        candidates = [shlex.split(line) for line in expansion if line.strip().startswith('"' + str(self.ld) + '"')]
        self.check("one-actual-native-linker-expansion", len(candidates) == 1)
        expanded = candidates[0]
        libraries = [a for a in expanded if a.startswith("-l")]
        self.check("measured-driver-library-policy", libraries in [["-lfirehose_kernel", "-lpthread_kext"],
                   ["-lcc_kext", "-lfirehose_kernel", "-lpthread_kext"]])
        direct = expanded.copy()
        restored = []
        if "-lcc_kext" not in direct:
            insertion = direct.index("-lfirehose_kernel")
            direct[insertion:insertion] = ["-lcc_kext"]
            restored = ["-lcc_kext"]
            reject("actual-backend-missing-cc_kext", lambda: self.validate_link(expanded))
        self.validate_link(direct)
        self.check("all3-libraries-present-in-actual-backend-command",
                   [a for a in direct if a.startswith("-l")] == ["-lcc_kext", "-lfirehose_kernel", "-lpthread_kext"])
        self.report["driver_expansion"] = dict(compiler_argv=argv, expanded_linker_argv=expanded,
            observed_library_arguments=libraries, source_justified_restored_native_arguments=restored,
            actual_linker_argv=direct, no_other_backend_argument_changed=True)
        code, _, diagnostic = self.run(direct, "genuine-current-provider-full-link", timeout=120)
        produced = output.is_file()
        self.report["actual_link"] = dict(argv=direct, exit_code=code, image_exists=produced,
            output=str(output.relative_to(self.root)), output_sha256=sha(output) if produced else None,
            missing_cc_kext="library not found for -lcc_kext" in diagnostic,
            required_libraries_preserved=["cc_kext", "firehose_kernel", "pthread_kext"],
            empty_or_stub_library_supplied=False, historical_pthread_supplied=False, diagnostic=diagnostic)
        if produced:
            if code:
                self.report["actual_link"]["partial_output"] = True
            else:
                view = self.native.thin(output)
                self.check("produced-real-ARM64-image", view["filetype"] == 2)
                self.must([self.native.NDK / "llvm-readobj", "--file-headers", "--sections", "--symbols", output], "genuine-produced-image-inspection")
                self.report["actual_link"]["genuine_image_inspected"] = True
        if code:
            self.check("bounded-real-link-failure-retained", not produced, exit_code=code)
        else:
            self.check("real-link-produced-an-image", produced)
        self.check("all-real-wrong-input-controls-rejected", len(controls) == 5 + len(restored) and all(c["rejected"] for c in controls))

    def finish(self, error=None):
        self.report["recorded_at"] = stamp()
        self.report["outcome"] = "fail" if error or not self.report["checks"] or not all(c["pass_check"] for c in self.report["checks"]) else "pass"
        if error:
            self.report["error"] = str(error)
        self.report["summary"] = "Actual coherent provider link measurement; full kernel, crypto, SDK, Apple private ABI, runtime and native qualification remain false"
        self.report["max_child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self.report["max_harness_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.report["commit"] = subprocess.check_output(["git", "-C", str(self.worktree), "rev-parse", "HEAD"], text=True).strip()
        dump(self.out / "report.json", self.report)
        artifacts = [p for p in self.out.rglob("*") if p.is_file() and p.name != "evidence.json"]
        evidence = dict(kind="host-test", origin="local-host", outcome=self.report["outcome"], recorded_at=stamp(),
            summary=self.report["summary"], commit=self.report["commit"], commands=self.report["commands"],
            device_executed=False, full_kernel_qualified=False, artifacts=[str(p.relative_to(self.root)) for p in artifacts],
            sha256={str(p.relative_to(self.root)): sha(p) for p in artifacts})
        dump(self.out / "evidence.json", evidence)
        print(json.dumps(dict(outcome=evidence["outcome"], evidence=str((self.out / "evidence.json").relative_to(self.root)), error=str(error) if error else None)), flush=True)
        return 0 if evidence["outcome"] == "pass" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Primary checkout, read-only except external registry CLI")
    parser.add_argument("--run", required=True)
    parser.add_argument("--experiment", default="KPROV-001")
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve() / "tools/build"))
    import xnu_kernel_link_inputs as native
    from xnu_kernel_symbol_gaps import SymbolGaps
    if native.ROOT.resolve() != args.root.resolve():
        raise ValueError("Helper primary root mismatch")
    build = ProviderLink(args, native, SymbolGaps.external_symbols)
    try:
        build.inputs()
        native.LinkInputs.stage_filelists(build)
        native.LinkInputs.archive(build)
        build.metadata()
        build.providers()
        build.controls_and_link()
    except Exception as error:
        return build.finish(error)
    return build.finish()


if __name__ == "__main__":
    raise SystemExit(main())
