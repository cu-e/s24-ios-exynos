#!/usr/bin/env python3
"""Measure native selected kernel linking with accepted compiler-resource lookup."""
from __future__ import annotations
import argparse
import copy
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

sys.dont_write_bytecode = True
os.environ.update(GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0", PYTHONDONTWRITEBYTECODE="1")
OWNER = "codex-team-kernel-runtime-link-20261105-bk"
RUNTIME_SHA = "67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5"
DESCRIPTOR = "worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/qualified-component.json"
PREVIOUS = "worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3"
ACCEPTANCE = "worktrees/krn-024-20261105/artifacts/kernel-provider-link/acceptance-session1"
REPLACEMENTS = {"osfmk/caches_asm.o", "osfmk/start.o", "osfmk/model_dep.o", "pexpert/pe_init.o"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def build_class(parent):
    class RuntimeLink(parent.ProviderLink):
        def __init__(self, args, native):
            self.args, self.native = args, native
            self.root = args.root.resolve()
            self.worktree = Path(__file__).resolve().parents[2]
            if self.worktree == self.root or not self.worktree.is_relative_to(self.root / "worktrees"):
                raise ValueError("Separate task worktree below primary checkout required")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run):
                raise ValueError("Plain fresh run name required")
            self.out = self.worktree / "artifacts/kernel-runtime-link" / args.run
            self.out.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(__file__, self.out / "builder.py")
            self.ledger = self.read("state/lab.json")
            self.report = dict(kind="host-test", origin="local-host", outcome="fail", recorded_at=stamp(),
                commands=[], checks=[], parents={}, tools_sha256={}, source_inputs={}, device_executed=False,
                sdk_used=False, global_install=False, full_kernel_qualified=False, full_crypto_qualified=False,
                apple_private_abi_qualified=False, apple_interoperability_qualified=False,
                full_runtime_behavior_qualified=False, native_device_qualified=False)

        def validate_descriptor(self, desc):
            resource = self.root / desc["resource_dir"]
            archive = self.root / desc["archive"]
            if (desc["archive_sha256"] != RUNTIME_SHA or sha(archive) != RUNTIME_SHA
                    or archive != resource / "lib/darwin/libclang_rt.cc_kext_ios.a"
                    or desc["compiler_sha256"] != self.previous["compiler"]["sha256"]
                    or desc["target"] != "arm64-apple-ios16.5" or desc["archive_members"] != 287
                    or desc["corecrypto_provider"] is not False or desc["exact_upstream_source"] is not False
                    or "Link-only" not in desc["resource_scope"]):
                raise ValueError("Require exact accepted link-only corrected runtime descriptor/archive")
            return resource, archive

        def inputs(self):
            tasks = {t["id"]: t for t in self.ledger["tasks"]}
            task = tasks["KRN-030"]
            self.check("owned-task-and-accepted-parent-tasks", task["status"] == "in_progress" and task["owner"] == OWNER
                       and all(tasks[n]["status"] == "done" for n in ["KRN-024", "KRN-025", "KRN-022"]))
            plan = next(e for e in self.ledger["experiments"] if e["id"] == self.args.experiment)
            self.check("owned-registered-plan", plan["owner"] == OWNER and plan["task"] == "KRN-030" and plan["status"] == "planned")
            for identifier in ["KPROV-003", "KPROV-004", "CCKEXT-015", "CCKEXT-017", "CCREV-002"]:
                self.capsule(identifier)
            self.previous = self.read(PREVIOUS + "/report.json")
            self.compiled = self.read(PREVIOUS + "/current-compiled-objects.json")
            dependencies = self.read(PREVIOUS + "/current-dependency-files.json")
            original = {r["id"]: r for r in self.read("artifacts/xnu-kernel-iig-objects/audit-session1/compiled-objects.json")}
            changed = {r["id"] for r in self.compiled if r["output"] != original[r["id"]]["output"]}
            self.check("exact-current-982-identities-four-replacements", len(self.compiled) == len({r["id"] for r in self.compiled}) == 982
                       and set(original) == {r["id"] for r in self.compiled} and changed == REPLACEMENTS)
            for row in self.compiled:
                for field in ["source", "output"]:
                    if sha(self.root / row[field]) != row[field + "_sha256"]:
                        raise ValueError("Changed current source/object: " + row["id"])
                stage = self.previous["staged_objects"][row["id"]]
                if stage["original"] != row["output"] or stage["original_sha256"] != row["output_sha256"] or sha(self.root / stage["output"]) != stage["output_sha256"]:
                    raise ValueError("Staging no longer binds current graph")
                with (self.root / row["output"]).open("rb") as stream:
                    header = stream.read(16)
                if len(header) != 16 or struct.unpack_from("<I", header)[0] != 0xfeedfacf or struct.unpack_from("<I", header, 4)[0] != 0x100000c or struct.unpack_from("<I", header, 12)[0] != 1:
                    raise ValueError("Actual thin ARM64 object required")
            for path, digest in dependencies.items():
                if sha(self.root / path) != digest:
                    raise ValueError("Changed current dependency: " + path)
            self.check("all3156-current-dependencies", len(dependencies) == 3156)
            for path, digest in self.previous["metadata"]["outputs"].items():
                if sha(self.root / path) != digest:
                    raise ValueError("Changed native metadata")
            archive = self.previous["archive"]
            if sha(self.root / archive["path"]) != archive["sha256"] or sha(self.root / archive["filelist"]) != archive["filelist_sha256"]:
                raise ValueError("Changed native archive/filelist")
            self.check("native-transform-and-archive-context", len(self.previous["HIB_processing"]) == 14
                       and len(self.previous["KLD_processing"]) == 1 and archive["expected_objects"] == 981
                       and len((self.root / archive["filelist"]).read_text().splitlines()) == 978
                       and self.previous["metadata"]["aliases"] == 83 and self.previous["link_variables"]["USE_LTO"] == "0")
            for provider in self.previous["providers"].values():
                if sha(self.root / provider["archive"]) != provider["sha256"] or provider["missing_from_current_kernel_after_native_aliases"] or provider["overlap"]:
                    raise ValueError("Changed genuine FHDR/PTHP provider")
            self.descriptor = self.read(DESCRIPTOR)
            self.resource, self.runtime = self.validate_descriptor(self.descriptor)
            self.compiler = self.root / self.descriptor["compiler"]
            self.frontend_original = self.previous["driver_expansion"]["compiler_argv"]
            self.ld = Path(self.previous["driver_expansion"]["expanded_linker_argv"][0])
            if str(self.compiler) != self.frontend_original[0] or sha(self.compiler) != self.descriptor["compiler_sha256"]:
                raise ValueError("Changed selected compiler")
            if sha(self.ld) != self.previous["tools_sha256"][str(self.ld)]:
                raise ValueError("Changed native linker")
            correction = self.descriptor["source_correction"]
            patch = self.root / correction["patch_path"]
            corrected = patch.parent.parent / "patched-source/lib/builtins/ashrti3.c"
            corrected_report = self.read("worktrees/krn-025-20261105/artifacts/xnu-cc-kext/corrected-session1/report.json")
            sources = [self.root / p for p in corrected_report["selection"]["sources"] if p.endswith("/lib/builtins/ashrti3.c")]
            self.check("qualified-runtime-arithmetic-patch-provenance", len(sources) == 1
                       and sha(sources[0]) == correction["base_sha256"] and sha(patch) == correction["patch_sha256"]
                       and sha(corrected) == correction["patched_sha256"] and correction == corrected_report["source_correction"]
                       and correction["revision"] == "6009708b4367171ccdbf4b5905cb6a803753fe18")
            members = self.native.archive_members(self.runtime.read_bytes())
            self.check("287-real-runtime-members-and-corrected-native-byte-identity", len(members) == 287
                       and sum(hashlib.sha256(data).hexdigest() == correction["corrected_object_sha256"] for _, data in members) == 1)
            self.report["runtime"] = dict(descriptor=DESCRIPTOR, descriptor_sha256=sha(self.root / DESCRIPTOR),
                resource_dir=str(self.resource.relative_to(self.root)), archive=str(self.runtime.relative_to(self.root)), archive_sha256=sha(self.runtime),
                members=[dict(ordinal=i, name=n, sha256=hashlib.sha256(data).hexdigest()) for i, (n, data) in enumerate(members)],
                source_revision=self.descriptor["source_revision"], source_correction=correction, link_only=True)
            self.report["reused_native_inputs"] = dict(graph=self.previous["graph"], dependency_count=len(dependencies),
                archive=archive, metadata=self.previous["metadata"], providers=self.previous["providers"],
                link_variables=self.previous["link_variables"], staged_objects=self.previous["staged_objects"])
            for path, digest in self.previous["source_inputs"].items():
                if sha(self.root / path) != digest:
                    raise ValueError("Changed witnessed native source/helper")
            for path in [Path(parent.__file__), Path(self.native.__file__), Path(__file__)]:
                self.report["source_inputs"][str(path.relative_to(self.root))] = sha(path)
            self.report["source_inputs"].update({str(p.relative_to(self.root)): sha(p) for p in [patch, corrected, sources[0]]})
            self.report["compiler"] = dict(path=str(self.compiler.relative_to(self.root)), sha256=sha(self.compiler))
            self.report["tools_sha256"][str(self.ld)] = sha(self.ld)

        def command(self):
            self.output = self.out / "mach.release.e1s.unstripped"
            self.journal = self.out / "actual-backend.json"
            self.wrapper = self.out / "journal-ld64"
            source = ('#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\n'
                      + 'argv=' + repr([str(self.ld)]) + '+sys.argv[1:]\n'
                      + 'if "-o" in argv:\n    Path(' + repr(str(self.journal)) + ').write_text(json.dumps({"argv":argv},indent=2)+"\\n")\n'
                      + 'os.execv(argv[0],argv)\n')
            self.wrapper.write_text(source)
            self.wrapper.chmod(0o755)
            argv = self.frontend_original.copy()
            argv[argv.index("-o") + 1] = str(self.output)
            ld_flags = [i for i, arg in enumerate(argv) if arg.startswith("--ld-path=")]
            if len(ld_flags) != 1:
                raise ValueError("One original native linker selection required")
            argv[ld_flags[0]] = "--ld-path=" + str(self.wrapper)
            argv += ["-resource-dir", str(self.resource)]
            self.validate_frontend(argv)
            self.report["frontend_binding"] = dict(original_argv=self.frontend_original, actual_argv=argv,
                changed_inputs=["fresh output path", "transparent execv journal for same ld64", "explicit qualified link-only resource directory"],
                wrapper_sha256=sha(self.wrapper), literal_backend_library_restored=False)
            return argv

        def validate_frontend(self, argv):
            if argv.count("-resource-dir") != 1 or argv.count("-lcc_kext") != 1 or "-Wl,-lcc_kext" in argv:
                raise ValueError("Keep outer native reserved cc library and exactly one resource input")
            index = argv.index("-resource-dir")
            if argv[index + 1] != str(self.resource):
                raise ValueError("Wrong link-only resource root")
            normalized = argv[:index] + argv[index + 2:]
            normalized[normalized.index("-o") + 1] = self.frontend_original[self.frontend_original.index("-o") + 1]
            normalized = ["--ld-path=" + str(self.ld) if a.startswith("--ld-path=") else a for a in normalized]
            if normalized != self.frontend_original:
                raise ValueError("Original native frontend inputs/flags/order must be unchanged")

        def expansion(self, argv, label):
            self.must([*argv, "-###"], label)
            lines = (self.out / (label + ".stderr.txt")).read_text().splitlines()
            commands = [shlex.split(line) for line in lines if line.strip().startswith('"' + str(self.wrapper) + '"')]
            if len(commands) != 1:
                raise ValueError("One actual backend expansion required")
            return [str(self.ld), *commands[0][1:]]

        def validate_backend(self, argv):
            if argv.count(str(self.runtime)) != 1 or "-lcc_kext" in argv:
                raise ValueError("Native reserved-option expansion must name only the genuine absolute runtime")
            if any(x in argv for x in ["-all_load", "-force_load", "-undefined", "dynamic_lookup", "-r"]):
                raise ValueError("No forced members or downgraded link/export behavior")
            for name in ["-lfirehose_kernel", "-lpthread_kext"]:
                if argv.count(name) != 1:
                    raise ValueError("Missing or repeated native library")
            normalized = argv.copy()
            normalized.remove(str(self.runtime))
            normalized[normalized.index("-o") + 1] = self.previous["driver_expansion"]["expanded_linker_argv"][self.previous["driver_expansion"]["expanded_linker_argv"].index("-o") + 1]
            if normalized != self.previous["driver_expansion"]["expanded_linker_argv"]:
                raise ValueError("Native backend differs beyond runtime insertion and fresh output")

        def controls(self, frontend, backend):
            result = []
            def reject(name, function):
                try:
                    function()
                except (ValueError, FileNotFoundError) as error:
                    result.append(dict(name=name, rejected=True, reason=str(error)))
                else:
                    raise ValueError("Negative input accepted: " + name)
            altered = copy.deepcopy(self.descriptor)
            altered["archive_sha256"] = "0" * 64
            reject("wrong-accepted-archive-digest", lambda: self.validate_descriptor(altered))
            altered_argv = frontend.copy()
            altered_argv[altered_argv.index("-filelist") + 1] = str(self.root / "artifacts/xnu-kernel-link-inputs/baseline-session5/stage/link.filelist")
            reject("stale-pre-SGAP-filelist", lambda: self.validate_frontend(altered_argv))
            reject("literal-backend-library-restoration", lambda: self.validate_backend([*backend, "-lcc_kext"]))
            weakened = backend.copy()
            index = weakened.index("-exported_symbols_list")
            del weakened[index:index + 2]
            reject("skipped-native-export-list", lambda: self.validate_backend(weakened))
            reject("forced-all-runtime-members", lambda: self.validate_backend([*backend, "-all_load"]))
            missing = self.out / "missing-resource"
            missing.mkdir()
            dry = frontend.copy()
            dry[dry.index("-resource-dir") + 1] = str(missing)
            wrong_backend = self.expansion(dry, "negative-missing-resource-driver-expansion")
            self.check("missing-resource-reproduces-actual-native-driver-omission", str(self.runtime) not in wrong_backend
                       and "-lcc_kext" not in wrong_backend)
            reject("actual-missing-resource-driver-output", lambda: self.validate_backend(wrong_backend))
            self.report["negative_controls"] = result
            self.check("six-wrong-input-controls-rejected", len(result) == 6 and all(c["rejected"] for c in result))

        def link(self):
            frontend = self.command()
            backend = self.expansion(frontend, "qualified-runtime-driver-expansion")
            self.validate_backend(backend)
            self.controls(frontend, backend)
            code, _, diagnostic = self.run(frontend, "actual-native-full-kernel-link", timeout=120)
            if not self.journal.is_file():
                raise ValueError("No actual backend execution journal")
            observed = json.loads(self.journal.read_text())["argv"]
            self.check("executed-backend-matches-native-driver-expansion", observed == backend)
            self.validate_backend(observed)
            produced = self.output.is_file()
            self.report["actual_link"] = dict(frontend_argv=frontend, expanded_backend=backend, observed_backend=observed,
                exit_code=code, image_exists=produced, output=str(self.output.relative_to(self.root)),
                output_sha256=sha(self.output) if produced else None, diagnostic=diagnostic,
                kernel_link_succeeded=(code == 0 and produced), absolute_runtime_inserted=True,
                literal_backend_library_restored=False, forced_archive_members=False)
            missing = re.findall(r'^  "([^"]+)", referenced from:', diagnostic, re.M)
            earlier = self.read(ACCEPTANCE + "/remaining-export-inputs.json")
            self.report["diagnosed_missing_names"] = missing
            self.report["remaining_prior_export_names"] = {name: earlier[name] for name in missing if name in earlier}
            self.report["new_diagnosed_names"] = sorted(set(missing) - earlier.keys())
            if code == 0:
                self.check("real-image-required-on-link-success", produced)
                view = self.native.thin(self.output)
                self.check("produced-real-ARM64-MachO-image", view["filetype"] == 2)
                self.must([self.native.NDK / "llvm-readobj", "--file-headers", "--sections", "--symbols", self.output], "real-image-structural-inspection")
            else:
                self.check("actual-failed-link-retained-with-no-image", not produced, actual_exit=code)
            inventory = self.read("worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/report.json")["runtime_symbols"]
            self.report["runtime_archive_inventory"] = dict(definitions=inventory["defined"], external_imports=inventory["external_imports"],
                scope="Whole-archive inventory only;not all-member selection or import closure for this lazy failed link",
                selected_members_observed=None, selection_scope="Original native command has no force_load/all_load;no trace-only linker option was added",
                diagnosed_runtime_import_names=sorted(set(missing) & set(inventory["external_imports"])))
            self.check("native-resource-resolves-former-missing-runtime-gate", str(self.runtime) in observed
                       and "library not found for -lcc_kext" not in diagnostic)
            self.report["runtime_inventory_inputs"] = dict(whole_archive_import_count=len(inventory["external_imports"]),
                prior_object_provider_subset=self.previous["remaining_object_provider_names"],
                potential_object_provider_subset_runtime_requests=sorted(set(inventory["defined"]) & set(self.previous["remaining_object_provider_names"])),
                all47_imports_required_by_this_link=False)

        def finish(self, error=None):
            self.report["outcome"] = "fail" if error or not self.report["checks"] or not all(c["pass_check"] for c in self.report["checks"]) else "pass"
            self.report["recorded_at"] = stamp()
            self.report["error"] = str(error) if error else None
            self.report["summary"] = "Native driver/compiler-runtime full-link measurement; full kernel, crypto, private ABI, runtime behavior and native qualification remain false"
            self.report["commit"] = subprocess.check_output(["git", "-C", str(self.worktree), "rev-parse", "HEAD"], text=True).strip()
            dump(self.out / "report.json", self.report)
            files = [p for p in self.out.rglob("*") if p.is_file() and p.name != "evidence.json"]
            evidence = dict(kind="host-test", origin="local-host", outcome=self.report["outcome"], recorded_at=self.report["recorded_at"],
                commit=self.report["commit"], summary=self.report["summary"], commands=self.report["commands"],
                device_executed=False, full_kernel_qualified=False, artifacts=[str(p.relative_to(self.root)) for p in files],
                sha256={str(p.relative_to(self.root)): sha(p) for p in files})
            dump(self.out / "evidence.json", evidence)
            print(json.dumps(dict(outcome=evidence["outcome"], error=self.report["error"], evidence=str((self.out / "evidence.json").relative_to(self.root)))), flush=True)
            return 0 if evidence["outcome"] == "pass" else 1
    return RuntimeLink


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--experiment", default="KRUNLINK-001")
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve() / "tools/build"))
    import xnu_kernel_provider_link as parent
    import xnu_kernel_link_inputs as native
    if native.ROOT.resolve() != args.root.resolve():
        raise ValueError("Primary helper root mismatch")
    build = build_class(parent)(args, native)
    try:
        build.inputs()
        build.link()
    except Exception as error:
        return build.finish(error)
    return build.finish()


if __name__ == "__main__":
    raise SystemExit(main())
