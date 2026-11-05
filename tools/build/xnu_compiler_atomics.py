#!/usr/bin/env python3
"""Build and measure source-backed XNU atomic type metadata, entirely on host."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import struct
import subprocess
import sys

from xnu_compiler_hardening import Audit, ROOT, BASE, PROFILE, NDK, registered, sha, dump
from xnu_compiler_types import allocator_metadata
from xnu_macho_tools import macho

FIXTURES = ROOT / "fixtures/public/xnu-compiler-atomics"
PATCHES = ROOT / "patches/compiler-atomics"
HARDEN = ROOT / "artifacts/xnu-compiler-hardening/ast-patch-session1"
KERNEL = ROOT / "artifacts/xnu-prepare/e1s-dependency-source-session1/xnu"
KOBJECT = ROOT / "artifacts/xnu-kernel-objects/compile-session2"


class Atomics(Audit):
    def __init__(self, args):
        self.args = args
        self.out = ROOT / "artifacts/xnu-compiler-atomics" / args.run
        if self.out.resolve() != self.out: raise ValueError("Canonical fresh run required")
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / "builder.py")
        self.report = dict(kind="host-test", origin="local-host", outcome="fail",
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), mode=args.mode,
            commands=[], checks=[], device_executed=False, full_kernel_qualified=False,
            apple_private_abi_qualified=False, kernel_cases=[])
        self.ledger = json.loads((ROOT / "state/lab.json").read_text())

    def inputs(self):
        super().inputs()
        self.report["parents"] = {}
        for identifier in ["HARDEN-002", "HARDEN-005", "KCONFIG-005", "KCONFIG-006", "KOBJECT-003", "KOBJECT-004"]:
            registered(identifier, self.ledger)
            e = next(e for e in self.ledger["experiments"] if e["id"] == identifier)
            self.report["parents"][identifier] = dict(evidence=e["evidence"], sha256=e["evidence_sha256"])
        witness = ROOT / "artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json"
        parent = json.loads((ROOT / "fixtures/public/xnu-dependencies/firehose-session1.json").read_text())
        if sha(witness) != parent["kernel_tree_manifest_sha256"]: raise ValueError("Prepared source witness changed")
        files = json.loads(witness.read_text())
        actual = {str(p.relative_to(KERNEL)) for p in KERNEL.rglob("*") if p.is_file() and ".git" not in p.relative_to(KERNEL).parts}
        if actual != set(files) or any(sha(KERNEL / p) != h for p, h in files.items()):
            raise ValueError("Prepared source bytes/file set changed")
        self.report["prepared_source_witness_sha256"] = sha(witness)
        self.compiler = HARDEN / "clang"
        self.link[self.link.index("lib/libclangAST.a")] = str(HARDEN / "libclangAST.a")
        self.object_report = json.loads((KOBJECT / "report.json").read_text())
        self.processes = {Path(c["stdout"]).name.removeprefix("compile-").removesuffix(".stdout.txt"): c
            for c in self.object_report["commands"] if Path(c["stdout"]).name.startswith("compile-")}
        fixtures = self.out / "fixture-inputs"
        fixtures.mkdir()
        for source in [*FIXTURES.glob("*.c"), *FIXTURES.glob("*.cpp"),
                       ROOT / "fixtures/public/xnu-kernel-objects/atomic-metadata.c"]:
            shutil.copyfile(source, fixtures / source.name)
        self.report["fixture_files_sha256"] = {p.name: sha(p) for p in fixtures.iterdir()}

    def rebuild_atomics(self):
        helper = self.out / "helper-source"
        rel = Path("src/clang/include/clang/AST/XnuTypeMetadata.h")
        (helper / rel).parent.mkdir(parents=True)
        shutil.copyfile(self.private / rel, helper / rel)
        patch = PATCHES / "0001-target-atomic-value-storage.patch"
        self.must(["git", "-C", helper, "apply", "--check", patch], "atomic-patch-check")
        self.must(["git", "-C", helper, "apply", patch], "atomic-patch-apply")
        if self.args.array_semantics:
            array_patch = PATCHES / "0003-scalar-array-usage-semantics.patch"
            self.must(["git", "-C", helper, "apply", "--check", array_patch], "array-patch-check")
            self.must(["git", "-C", helper, "apply", array_patch], "array-patch-apply")
            self.report["array_patch_sha256"] = sha(array_patch)
        include = helper / "src/clang/include"
        # Preserve all previous Parser, Sema, constant-evaluator and mangling
        # corrections. The new header has three actual compiled consumers.
        archives = {"Sema": self.out / "libclangSema.a", "AST": self.out / "libclangAST.a"}
        shutil.copyfile(PROFILE / "libclangSema.a", archives["Sema"])
        shutil.copyfile(HARDEN / "libclangAST.a", archives["AST"])
        sources = [("Sema", "SemaExpr.cpp", PROFILE / "parser-source/src/clang/lib/Sema/SemaExpr.cpp"),
                   ("Sema", "SemaExprCXX.cpp", self.private / "src/clang/lib/Sema/SemaExprCXX.cpp"),
                   ("AST", "ExprConstant.cpp", HARDEN / "ast-source/src/clang/lib/AST/ExprConstant.cpp")]
        self.report["compiled_consumers"] = []
        for library, name, previous in sources:
            relative = Path("src/clang/lib") / library / name
            source = self.out / "consumer-source" / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(previous, source)
            recipe = self.must([shutil.which("ninja"), "-C", self.build, "-t", "commands",
                "tools/clang/lib/" + library + "/CMakeFiles/obj.clang" + library + ".dir/" + name + ".o"], name + "-recipe")
            argv = shlex.split(recipe.splitlines()[-1])
            if sha(argv[0]) != self.host_sha or str(self.private / relative) not in argv:
                raise ValueError("Unexpected real compiler TU recipe")
            argv[argv.index(str(self.private / relative))] = str(source)
            argv[1:1] = ["-I", str(include)]
            obj = self.out / (name + ".o")
            for flag, value in [("-o", obj), ("-MF", obj.with_suffix(".d")), ("-MT", obj)]:
                if flag in argv: argv[argv.index(flag) + 1] = str(value)
            self.must(argv, name + "-compile", cwd=self.build, timeout=180)
            self.must([NDK / "llvm-ar", "r", archives[library], obj], name + "-archive")
            self.must([NDK / "llvm-ar", "p", archives[library], obj.name], name + "-extract")
            if sha(self.out / (name + "-extract.stdout.txt")) != sha(obj): raise ValueError("Archive member mismatch")
            self.report["compiled_consumers"].append(dict(source=str(source.relative_to(ROOT)), source_sha256=sha(source),
                retained_parent=str(previous.relative_to(ROOT)), retained_parent_sha256=sha(previous), object_sha256=sha(obj)))
        argv = self.link.copy()
        argv[argv.index(str(PROFILE / "libclangSema.a"))] = str(archives["Sema"])
        argv[argv.index(str(HARDEN / "libclangAST.a"))] = str(archives["AST"])
        self.compiler = self.out / ("clang-before-postfix" if self.args.postfix else "clang")
        argv[argv.index("-o") + 1] = str(self.compiler)
        self.must(argv, "atomic-compiler-link", cwd=self.build, timeout=180)
        self.report.update(atomic_patch_sha256=sha(patch), atomic_helper_sha256=sha(helper / rel),
            relink_inputs_sha256={str((self.build / p).resolve()): sha(self.build / p)
                for p in argv if p.endswith((".a", ".o")) and (self.build / p).is_file()})
        self.link = argv
        return archives

    def reuse_atomics(self):
        doc = registered(self.args.reuse_evidence, self.ledger)
        previous = self.args.reuse_run.resolve()
        if not previous.is_relative_to(ROOT / "artifacts/xnu-compiler-atomics"):
            raise ValueError("Reuse only recorded isolated atomic source builds")
        path = previous / "report.json"
        if sha(path) != doc["sha256"][str(path.relative_to(ROOT))]: raise ValueError("Atomic parent report changed")
        report = json.loads(path.read_text())
        required = {"SemaExpr.cpp", "SemaExprCXX.cpp", "ExprConstant.cpp"}
        if {Path(c["source"]).name for c in report.get("compiled_consumers", [])} != required:
            raise ValueError("Atomic compiler did not rebuild every actual consumer")
        if sha(previous / "helper-source/src/clang/include/clang/AST/XnuTypeMetadata.h") != report["atomic_helper_sha256"]:
            raise ValueError("Recorded atomic helper changed")
        self.link[self.link.index(str(PROFILE / "libclangSema.a"))] = str(previous / "libclangSema.a")
        self.link[self.link.index(str(HARDEN / "libclangAST.a"))] = str(previous / "libclangAST.a")
        self.report.update(reused_atomic_parent=self.args.reuse_evidence, atomic_helper_sha256=report["atomic_helper_sha256"],
            atomic_patch_sha256=report["atomic_patch_sha256"], compiled_consumers=report["compiled_consumers"])

    def rebuild_parser(self):
        relative = Path("src/clang/lib/Parse/ParseExpr.cpp")
        root = self.out / "parser-source"
        source = root / relative
        source.parent.mkdir(parents=True)
        shutil.copyfile(PROFILE / "parser-source" / relative, source)
        patch = PATCHES / "0002-builtin-postfix-expression.patch"
        self.must(["git", "-C", root, "apply", "--check", patch], "postfix-patch-check")
        self.must(["git", "-C", root, "apply", patch], "postfix-patch-apply")
        text = self.must([shutil.which("ninja"), "-C", self.build, "-t", "commands",
            "tools/clang/lib/Parse/CMakeFiles/obj.clangParse.dir/ParseExpr.cpp.o"], "postfix-recipe")
        argv = shlex.split(text.splitlines()[-1])
        if sha(argv[0]) != self.host_sha or str(self.private / relative) not in argv:
            raise ValueError("Unexpected real parser compile recipe")
        argv[argv.index(str(self.private / relative))] = str(source)
        obj = self.out / "ParseExpr.cpp.o"
        for flag, value in [("-o", obj), ("-MF", obj.with_suffix(".d")), ("-MT", obj)]:
            if flag in argv: argv[argv.index(flag) + 1] = str(value)
        self.must(argv, "postfix-compile", cwd=self.build, timeout=180)
        archive = self.out / "libclangParse.a"
        shutil.copyfile(PROFILE / "libclangParse.a", archive)
        self.must([NDK / "llvm-ar", "r", archive, obj], "postfix-archive")
        self.must([NDK / "llvm-ar", "p", archive, obj.name], "postfix-member")
        if sha(self.out / "postfix-member.stdout.txt") != sha(obj): raise ValueError("Parser archive member mismatch")
        link = self.link.copy();link[link.index(str(PROFILE / "libclangParse.a"))] = str(archive)
        self.compiler = self.out / "clang";link[link.index("-o") + 1] = str(self.compiler)
        self.must(link, "postfix-compiler-link", cwd=self.build, timeout=180)
        self.link = link
        self.report.update(postfix_patch_sha256=sha(patch), parser_source_sha256=sha(source))

    def controls(self):
        layout = self.out / "fixture-inputs/layout-only.c"
        for name, compiler in [("independent19", NDK / "clang"), ("source17", self.compiler)]:
            obj = self.out / (name + "-layout.o")
            code, _, stderr = self.run([compiler, "-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc",
                "-std=gnu11", "-c", layout, "-o", obj], "layout-" + name)
            self.check("layout-" + name, code == 0 and macho(obj)["filetype"] == 1,
                       exit_code=code, source_sha256=sha(layout), diagnostic=stderr[-2500:])
        cases = [("atomic-c", self.out / "fixture-inputs/atomic-metadata.c", self.flags("c") + ["-DS24_ATOMIC=1"]),
                 ("atomic-cxx", self.out / "fixture-inputs/atomic-contract.cpp", self.flags() + ["-Werror=unknown-attributes"])]
        for name, source, flags in cases:
            obj = self.out / (name + ".o")
            code, _, stderr = self.run([*flags, "-c", source, "-o", obj], name)
            self.check(name, code == 0 and macho(obj)["filetype"] == 1, exit_code=code,
                source_sha256=sha(source), diagnostic=stderr[-4500:])

    def recompiled_argv(self, row, output):
        process = self.processes[row["id"].replace("/", "-")]
        argv = process["argv"].copy()
        if Path(argv[0]) != HARDEN / "clang" or sha(ROOT / row["source"]) != row["source_sha256"]:
            raise ValueError("Genuine source/compiler provenance changed")
        if "-DXNU_NO_TYPE_BUILTINS=0" not in argv or any("xnu_clang_compat.h" in a for a in argv):
            raise ValueError("Actual type-check profile was not preserved")
        argv[0] = str(self.compiler)
        argv[argv.index("-o") + 1] = str(output)
        argv[argv.index("-MF") + 1] = str(output.parent / (output.name[:-1] + "d"))
        return argv, Path(process["cwd"])

    def allocator(self):
        row = next(r for r in self.object_report["inventory"] if r["id"] == "libkern/OSData.cpo")
        obj = self.out / "atomic-allocator.o"
        argv, cwd = self.recompiled_argv(row, obj)
        argv[argv.index(str(ROOT / row["source"]))] = str(self.out / "fixture-inputs/allocator-metadata.cpp")
        code, _, stderr = self.run(argv, "atomic-selected-allocator", cwd=cwd)
        value = allocator_metadata(obj) if code == 0 else None
        self.check("atomic-selected-allocator", code == 0 and bool(value), exit_code=code, diagnostic=stderr[-3500:])
        self.report["atomic_allocator_metadata"] = value

    def kernel_cases(self):
        rows = []
        for row in self.object_report["inventory"]:
            if self.args.all_existing:
                if row["status"] in ["compiled_arm64", "compile_failed"]: rows.append(row)
                continue
            if row["status"] != "compile_failed": continue
            process = self.processes[row["id"].replace("/", "-")]
            text = (ROOT / process["stderr"]).read_text(errors="replace")
            if "error: experimental XNU metadata does not support" in text: rows.append(row)
        self.report["kernel_case_selection"] = ("Every original existing-source compile recipe, including previous successes and failures" if self.args.all_existing else
            "Every actual source whose original full diagnostics contains unsupported XNU metadata (not an inferred cause grouping)")

        def one(row):
            directory = self.out / "kernel-objects" / row["component"]
            directory.mkdir(parents=True, exist_ok=True)
            output = directory / row["target"]
            argv, cwd = self.recompiled_argv(row, output)
            code, _, stderr = self.run(argv, "kernel-" + row["id"].replace("/", "-"), cwd=cwd, timeout=120)
            return dict(id=row["id"], source=row["source"], source_sha256=row["source_sha256"],
                parent_status=row["status"], exit_code=code, actual_arm64_object=code == 0 and output.is_file() and macho(output)["filetype"] == 1,
                output=str(output.relative_to(ROOT)) if output.is_file() else None, output_sha256=sha(output) if output.is_file() else None,
                still_unsupported_metadata="error: experimental XNU metadata does not support" in stderr,
                missing_headers=re.findall(r"fatal error: '([^']+)' file not found", stderr), diagnostic=stderr[-4500:])
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for index, result in enumerate(pool.map(one, rows), 1):
                self.report["kernel_cases"].append(result)
                if index % 40 == 0:
                    dump(self.out / "progress.json", dict(completed=index, total=len(rows),
                        actual_arm64=sum(r["actual_arm64_object"] for r in self.report["kernel_cases"])))
        self.report["kernel_case_counts"] = dict(selected=len(rows), actual_arm64=sum(r["actual_arm64_object"] for r in self.report["kernel_cases"]),
            still_unsupported=sum(r["still_unsupported_metadata"] for r in self.report["kernel_cases"]))
        expected = {"osfmk/core_analytics.o", "osfmk/restartable.o", "osfmk/smr.o"}
        selected = [r for r in self.report["kernel_cases"] if r["id"] in expected]
        self.check("genuine-kernel-representatives", len(selected)==len(expected) and all(r["actual_arm64_object"] for r in selected))
        if self.args.all_existing:
            expected_ids = {r["id"] for r in self.object_report["inventory"]
                if r["status"] in ["compiled_arm64", "compile_failed"]}
            results = self.report["kernel_cases"]
            regressions = [r["id"] for r in results
                if r["parent_status"] == "compiled_arm64" and not r["actual_arm64_object"]]
            self.check("complete-existing-source-selection", len(results)==len(expected_ids) and
                {r["id"] for r in results}==expected_ids)
            self.check("prior-object-regressions", not regressions, regressions=regressions)

    def diagnose_remaining(self):
        """Read actual selected AST types without weakening metadata rejection."""
        cases = [
            ("osfmk/status.o", "arm_neon_saved_state64", ["uint64x2_t", "uint32x4_t"],
             "arm_act_context.ns -> arm_neon_saved_state.uns.ns_64.v -> fixed ext_vector_type arrays; fixed vectors are not supported by this metadata helper"),
            ("iokit/MiniIOSurface.cpo", "IOExternalTrap", ["IOTrap", "IOService::*"],
             "IOSurfaceRootUserClient.fTraps -> IOExternalTrap.func -> IOTrap, a C++ member function pointer; member pointers remain rejected"),
            ("iokit/IONVRAM.cpo", "IONVRAMCHRPHandler", ["_varDict", "OSSharedPtr<OSDictionary> &"],
             "IONVRAMCHRPHandler._varDict and IONVRAMV3Handler._varDict are reference fields; reference storage metadata remains rejected"),
        ]
        observations = []
        for identifier, name, expected, explanation in cases:
            row = next(r for r in self.object_report["inventory"] if r["id"]==identifier)
            argv, cwd = self.recompiled_argv(row, self.out / "unused.o")
            # Preserve every target/define/include/source option, but request
            # read-only syntax/AST output and no object or dependency writes.
            for flag in ["-o", "-MF", "-MT", "-MQ"]:
                while flag in argv:
                    at = argv.index(flag);del argv[at:at+2]
            argv = [a for a in argv if a not in ["-c", "-MD", "-MMD", "-MP"]]
            argv += ["-fsyntax-only", "-Xclang", "-ast-dump", "-Xclang", "-ast-dump-filter", "-Xclang", name]
            code, stdout, stderr = self.run(argv, "diagnose-" + name, cwd=cwd, timeout=120)
            self.check("selected-ast-" + name, code==1 and "experimental XNU metadata does not support" in stderr
                and all(word in stdout for word in expected), exit_code=code, required_type_fragments=expected)
            observations.append(dict(id=identifier, filtered_ast=name, explanation=explanation,
                source=row["source"], source_sha256=row["source_sha256"]))
        source = self.out / "remaining-limits.cpp"
        source.write_text('''typedef unsigned long long Vector __attribute__((ext_vector_type(2)));
struct VectorRecord { Vector words[2]; };
struct Service { int call(void*); };
typedef int (Service::*Trap)(void*);
struct TrapRecord { void *object; Trap func; };
struct RefRecord { void *&reference; };
constexpr auto vector_summary=__builtin_xnu_type_summary(VectorRecord);
constexpr auto trap_summary=__builtin_xnu_type_summary(TrapRecord);
constexpr auto reference_summary=__builtin_xnu_type_summary(RefRecord);
''')
        code, _, stderr = self.run([*self.flags(), "-fsyntax-only", source], "remaining-limits")
        self.check("remaining-limits-rejected", code==1 and stderr.count("error: experimental XNU metadata does not support")==3,
            exit_code=code, diagnostic=stderr[-3500:])
        self.report["remaining_metadata_causes"] = observations

    def coverage(self):
        """Audit recorded objects/recipes/dependencies; do not infer new coverage."""
        doc = registered(self.args.coverage_evidence, self.ledger)
        paths = [ROOT / p for p in doc["artifacts"] if p.endswith("/report.json")]
        if len(paths)!=1: raise ValueError("Expected one recorded full-profile report")
        previous = json.loads(paths[0].read_text())
        if previous.get("compiler_sha256")!=sha(self.compiler): raise ValueError("Coverage compiler changed")
        cases = {r["id"]:r for r in previous["kernel_cases"]}
        expected = {r["id"]:r for r in self.object_report["inventory"]
            if r["status"] in ["compiled_arm64", "compile_failed"]}
        if len(cases)!=len(previous["kernel_cases"]) or set(cases)!=set(expected):
            raise ValueError("Coverage must contain every original existing-source recipe exactly once")
        processes = {Path(c["stdout"]).name.removeprefix("kernel-").removesuffix(".stdout.txt"):c
            for c in previous["commands"] if Path(c["stdout"]).name.startswith("kernel-")}
        if len(processes)!=len(cases): raise ValueError("Actual compile process inventory incomplete")
        objects, compiled, unresolved, dependencies, inputs = [], [], [], {}, {}
        categories, headers, regressions = Counter(), Counter(), []
        for identifier, row in expected.items():
            result = cases[identifier]
            process = processes[identifier.replace("/", "-")]
            argv, cwd = self.recompiled_argv(row, Path(process["argv"][process["argv"].index("-o")+1]))
            if argv!=process["argv"] or str(cwd)!=process["cwd"] or process["exit_code"]!=result["exit_code"]:
                raise ValueError("Actual full compile recipe/result mismatch: " + identifier)
            if process["timed_out"] or process["exit_code"] not in [0,1]:
                raise ValueError("Unexpected compiler failure/crash: " + identifier)
            if not result["actual_arm64_object"]:
                if row["status"]=="compiled_arm64": regressions.append(identifier)
                text = (ROOT / process["stderr"]).read_text(errors="replace")
                missing = re.findall(r"fatal error: '([^']+)' file not found", text)
                category = "missing_header" if missing else "unsupported_metadata" if "error: experimental XNU metadata does not support" in text else "other_compile_error"
                categories[category]+=1;headers.update(missing)
                unresolved.append(dict(id=identifier, category=category, missing_headers=missing,
                    errors=re.findall(r"(?m)^.*(?:fatal error:|error:).*$",text)[:4]))
                continue
            obj = ROOT / result["output"]
            if process["exit_code"]!=0 or sha(obj)!=result["output_sha256"] or macho(obj)["filetype"]!=1:
                raise ValueError("Actual ARM64 object changed: " + identifier)
            objects.append(obj)
            compiled.append({k:result[k] for k in ["id","source","source_sha256","output","output_sha256","parent_status"]})
            dep = Path(argv[argv.index("-MF")+1])
            line = dep.read_text().replace("\\\n", " ").splitlines()[0]
            files = [(cwd / p).resolve() for p in shlex.split(line.split(":",1)[1])]
            if (ROOT / row["source"]).resolve() not in files: raise ValueError("Actual dependency source mismatch")
            names = []
            for path in files:
                name = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
                if name not in inputs: inputs[name]=sha(path)
                names.append(name)
            dependencies[identifier]=dict(depfile=str(dep.relative_to(ROOT)), depfile_sha256=sha(dep), inputs=sorted(set(names)))
        for row in self.object_report["inventory"]:
            if row["status"]=="missing_source_or_recipe":
                unresolved.append(dict(id=row["id"], category="missing_source_or_recipe",source=row["source"]))
        text = self.must([NDK / "llvm-readobj", "--file-headers", *objects], "coverage-llvm-headers", timeout=120)
        self.check("independent-arm64-headers", text.count("Format: Mach-O arm64")==len(objects), object_count=len(objects))
        text = self.must([NDK / "llvm-nm", "--defined-only", "--format=posix", *objects], "coverage-llvm-symbols", timeout=120)
        counts = Counter(re.findall(r"(?m)^\S+ ([A-Za-z]) [0-9a-f]+", text))
        self.check("actual-code-symbols", counts["T"]+counts["t"]>0, defined_symbol_types=dict(counts))
        self.check("complete-recipe-selection", len(cases)==len(expected), actual_recipes=len(cases))
        self.check("prior-object-regressions", not regressions, regressions=regressions)
        self.check("coverage-observation-agreement", previous["kernel_case_counts"]["actual_arm64"]==len(objects))
        self.report["coverage"] = dict(parent_evidence=self.args.coverage_evidence, parent_report_sha256=sha(paths[0]),
            selected=len(self.object_report["inventory"]), attempted=len(cases), actual_arm64=len(objects),
            additional_objects=sum(r["parent_status"]!="compiled_arm64" for r in compiled), unresolved=len(unresolved),
            failure_categories=dict(categories), missing_headers=dict(headers), unique_dependency_files=len(inputs),
            defined_symbol_types=dict(counts), prior_object_regressions=regressions)
        for name, value in [("compiled-objects",compiled),("unresolved-objects",unresolved),("dependency-files",inputs),("object-dependencies",dependencies)]:
            dump(self.out / (name+".json"), value)

    def negatives(self):
        sources = {
            "atomic-aggregate-annotation": 'struct X { int data; }; struct Y { _Atomic(X) x __attribute__((xnu_usage_semantics("data"))); }; constexpr auto n=__builtin_xnu_type_summary(Y);',
            "atomic-member-pointer": 'struct X {}; typedef int X::* MP; struct Y { _Atomic(MP) x __attribute__((xnu_usage_semantics("pointer"))); }; constexpr auto n=__builtin_xnu_type_summary(Y);',
            "atomic-arm64e": 'constexpr auto n=__builtin_xnu_type_summary(_Atomic(void*));',
            "summary-subscript": 'constexpr auto n=__builtin_xnu_type_summary(void*)[0];',
        }
        for name, text in sources.items():
            source = self.out / (name + ".cpp");source.write_text(text + "\n")
            flags = self.flags()
            if name.endswith("arm64e"): flags[flags.index("arm64-apple-ios16.5")] = "arm64e-apple-ios16.5"
            code, _, stderr = self.run([*flags, "-fsyntax-only", source], name)
            expected = "subscripted value is not an array, pointer, or vector" if name == "summary-subscript" else "experimental XNU metadata does not support"
            self.check(name, code == 1 and expected in stderr,
                       exit_code=code, diagnostic=stderr[-2500:])

    def pch(self):
        header = self.out / "atomic-header.h"
        header.write_bytes((self.out / "fixture-inputs/atomic-contract.cpp").read_bytes())
        source = self.out / "atomic-consumer.cpp"
        source.write_text('''static_assert(AtomicMetadata<void*>::summary==2);
static_assert(AtomicMetadata<ThreeWords>::summary==4 && AtomicMetadata<ThreeWords>::signature[0]=='2');
static_assert(__builtin_xnu_type_summary(Annotated)==2 && __builtin_xnu_type_summary(DataOverride)==4);
struct Reloaded { _Atomic(Address) pointer; _Atomic(ThreeWords) words; };
static_assert(sizeof(Reloaded)==32 && __builtin_offsetof(Reloaded,words)==16);
static_assert(__builtin_xnu_type_summary(Reloaded)==7);
static_assert(__builtin_xnu_type_signature(Reloaded)[0]=='1' && __builtin_xnu_type_signature(Reloaded)[1]=='0');
static_assert(__builtin_xnu_type_signature(Reloaded)[2]=='2' && __builtin_xnu_type_signature(Reloaded)[3]=='2');
unsigned use_atomic(void **p) { return atomic_contract()+atomic_symbol(p); }
''')
        pch = self.out / "atomic.pch"
        code, _, stderr = self.run([*self.flags(), "-x", "c++-header", header, "-o", pch], "atomic-pch-create")
        self.check("atomic-pch-create", code == 0, exit_code=code, diagnostic=stderr[-2500:])
        if code: return
        objects = []
        for name, include in [("textual", ["-include", header]), ("serialized", ["-include-pch", pch])]:
            obj = self.out / ("atomic-pch-" + name + ".o")
            code, _, stderr = self.run([*self.flags(), *include, "-c", source, "-o", obj], "atomic-pch-" + name)
            self.check("atomic-pch-" + name, code == 0 and macho(obj)["filetype"] == 1,
                       exit_code=code, diagnostic=stderr[-2500:])
            if code == 0: objects.append(obj)
        if len(objects) == 2:
            self.report["atomic_pch_whole_object_equal"] = objects[0].read_bytes() == objects[1].read_bytes()
            self.pch_code_equivalence(objects[0], objects[1])
            names = self.must([NDK / "llvm-nm", "--defined-only", "--just-symbol-name", objects[1]], "atomic-pch-symbols")
            symbols = [n for n in names.splitlines() if n.startswith("__Z") and "atomic_symbol" in n]
            if len(symbols) != 1: raise ValueError("Expected one actual atomic dependent template symbol")
            text = self.must([NDK / "llvm-cxxfilt", symbols[0][1:]], "atomic-pch-demangle")
            self.check("atomic-dependent-vendor-expression", "__builtin_xnu_type_summary" in text and "Atomic" in text,
                       symbol=symbols[0], demangled=text.strip())

    def pch_code_equivalence(self, left, right):
        def text_section(path):
            macho(path)
            data = path.read_bytes();at = 32;sections = []
            for _ in range(struct.unpack_from("<I", data, 16)[0]):
                cmd, length = struct.unpack_from("<II", data, at)
                if cmd == 0x19:
                    count = struct.unpack_from("<I", data, at + 64)[0]
                    for i in range(count):
                        name, segment, address, size, offset, align, reloc, nr, flags, _, _, _ = struct.unpack_from("<16s16sQQ8I", data, at + 72 + i * 80)
                        if size:
                            if offset > len(data) or size > len(data)-offset or reloc > len(data) or nr > (len(data)-reloc)//8:
                                raise ValueError("PCH fixture section/relocation extent invalid")
                            sections.append((name.split(b"\0")[0], segment.split(b"\0")[0], address, size, offset, reloc, nr))
                at += length
            if len(sections) != 1 or sections[0][:2] != (b"__text", b"__TEXT"):
                raise ValueError("PCH fixture requires exactly one actual nonempty text section")
            return data, sections[0]

        def canonical(path, label):
            data, section = text_section(path)
            _, _, base, size, offset, reloc, nr = section
            names = self.must([NDK / "llvm-nm", "--defined-only", "--format=posix", path], label + "-symbols")
            functions = {a[0]: int(a[2],16) for line in names.splitlines() if len(a:=line.split())>=3 and a[1]=="T"}
            ordered = sorted(functions.items(), key=lambda p:p[1])
            if len(ordered) != 3: raise ValueError("Expected three actual PCH fixture code definitions")
            code = {}
            for i, (name, begin) in enumerate(ordered):
                end = ordered[i+1][1] if i+1<len(ordered) else base+size
                if begin < base or end <= begin or end > base+size: raise ValueError("Invalid PCH function extent")
                code[name] = data[offset+begin-base:offset+end-base].hex()
            decoded = self.must([NDK / "llvm-objdump", "-r", path], label + "-relocations")
            entries = []
            for position, kind, value in re.findall(r"(?m)^\s*([0-9a-fA-F]+)\s+(ARM64_RELOC_\w+)\s+(.+)$", decoded):
                address = base+int(position,16)
                owner = next((name for name, begin in reversed(ordered) if begin<=address), None)
                if owner is None: raise ValueError("Relocation outside actual functions")
                entries.append((owner, address-functions[owner], kind, value.strip()))
            if not entries: raise ValueError("PCH caller fixture has no checked external relocations")
            return dict(code=code, relocations=sorted(entries)), section

        a, _ = canonical(left, "pch-left")
        b, section = canonical(right, "pch-right")
        self.check("atomic-pch-function-code-and-relocations", a==b,
                   functions=sorted(a["code"]), relocations=a["relocations"], whole_object_equal=self.report["atomic_pch_whole_object_equal"])
        data = bytearray(right.read_bytes());_, _, base, size, offset, reloc, nr = section
        # A genuine code-byte change must fail even though addresses/order are
        # intentionally normalized. The bytes still form an actual Mach-O.
        data[offset] ^= 0x20
        changed = self.out / "atomic-pch-changed-code.o";changed.write_bytes(data)
        c, _ = canonical(changed, "pch-code-mutation")
        self.check("atomic-pch-code-mutation-rejected", c!=b)
        if nr < 2: raise ValueError("Expected two actual function call relocations")
        data = bytearray(right.read_bytes())
        first = struct.unpack_from("<I", data, reloc+4)[0]
        second = struct.unpack_from("<I", data, reloc+12)[0]
        if first & 0xffffff == second & 0xffffff: raise ValueError("Expected distinct actual call targets")
        struct.pack_into("<I", data, reloc+4, (first & 0xff000000) | (second & 0xffffff))
        changed = self.out / "atomic-pch-changed-call.o";changed.write_bytes(data)
        c, _ = canonical(changed, "pch-call-mutation")
        self.check("atomic-pch-call-mutation-rejected", c["code"]==b["code"] and c["relocations"]!=b["relocations"])

    def harness(self):
        text = (ROOT / "patches/compiler-hardening/raw-evaluator.cpp").read_text()
        anchor = '  if (Unsupported) T = C.getLValueReferenceType(T);'
        if text.count(anchor) != 1: raise ValueError("Actual raw harness source changed")
        text = text.replace(anchor, '  if (Mode.find("atomic") != std::string::npos) T = C.getAtomicType(T);\n' + anchor)
        source = self.out / "atomic-raw-evaluator.cpp";source.write_text(text)
        obj = self.out / "atomic-raw-evaluator.o"
        includes = [self.private / "src/clang/include", self.build / "tools/clang/include", self.private / "src/llvm/include", self.build / "include"]
        self.must([NDK / "clang++", "-std=c++17", "-fno-rtti", "-D_GNU_SOURCE", "-D__STDC_CONSTANT_MACROS",
            "-D__STDC_FORMAT_MACROS", "-D__STDC_LIMIT_MACROS", *[x for p in includes for x in ["-I", p]], "-c", source, "-o", obj], "atomic-harness-compile", timeout=180)
        link = [t for t in self.link if not t.endswith(".o")];link.insert(1, str(obj))
        exe = self.out / "atomic-raw-evaluator";link[link.index("-o") + 1] = str(exe)
        self.must(link, "atomic-harness-link", cwd=self.build, timeout=180)
        for mode in ["summary-atomic-pointer", "summary-atomic-data", "signature-atomic-pointer", "signature-atomic-data", "summary-reference", "signature-reference"]:
            code, stdout, stderr = self.run([exe, mode], "raw-" + mode)
            self.check("raw-" + mode, code == 0, exit_code=code, observed=stdout.strip(), diagnostic=stderr[-1000:])

    def finish(self):
        checks = self.report["checks"]
        self.report["outcome"] = "pass" if checks and all(c["pass_check"] for c in checks) and "error" not in self.report else "fail"
        self.report["summary"] = "Actual source atomic metadata/storage/archive/raw/PCH/kernel controls; bounded component only, remaining object/kernel/native qualification is separate"
        if hasattr(self, "compiler") and self.compiler.is_file(): self.report["compiler_sha256"] = sha(self.compiler)
        dump(self.out / "report.json", self.report)
        files = [p for p in self.out.rglob("*") if p.is_file() and p.name != "evidence.json"]
        if hasattr(self, "compiler"): files.append(self.compiler)
        evidence = {k: self.report[k] for k in ["kind", "origin", "outcome", "recorded_at", "summary"]}
        evidence.update(commands=self.report["commands"][:24], commands_scope="Representative exact commands; complete actual argv/exits retained in hashed report.json",
            actual_command_count=len(self.report["commands"]), commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in sorted(set(files))], sha256={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(files))},
            device_executed=False, full_kernel_qualified=False, apple_private_abi_qualified=False)
        dump(self.out / "evidence.json", evidence)
        print(json.dumps({k: self.report.get(k) for k in ["outcome", "error", "kernel_case_counts"]}))
        print(json.dumps([c for c in checks if not c["pass_check"]]))
        return 0 if self.report["outcome"] == "pass" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--mode", choices=["baseline", "build", "parser", "audit", "diagnose", "coverage"], required=True)
    p.add_argument("--kernel-cases", action="store_true")
    p.add_argument("--reuse-run", type=Path)
    p.add_argument("--reuse-evidence", help="Recorded atomic source build experiment ID")
    p.add_argument("--array-semantics", action="store_true")
    p.add_argument("--postfix", action="store_true")
    p.add_argument("--compiler", type=Path)
    p.add_argument("--compiler-evidence", help="Recorded actual compiler experiment ID")
    p.add_argument("--coverage-evidence", help="Recorded full existing-source recompile experiment ID")
    p.add_argument("--all-existing", action="store_true", help="Recompile every original existing-source recipe, including previous successes")
    p.add_argument("--jobs", type=int, default=2)
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run): p.error("Use a fresh canonical run name")
    if args.array_semantics and args.mode != "build": p.error("Array semantics requires rebuilding all three helper consumers")
    if not 1 <= args.jobs <= 3: p.error("Use1..3 bounded host jobs")
    if args.all_existing and not args.kernel_cases: p.error("Full existing-source selection requires --kernel-cases")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    audit = Atomics(args)
    try:
        audit.inputs()
        if args.mode == "build":
            audit.rebuild_atomics()
            if args.postfix: audit.rebuild_parser()
        if args.mode == "parser":
            if not args.reuse_run or not args.reuse_evidence: raise ValueError("Parser continuation requires a recorded atomic source build")
            audit.reuse_atomics();audit.rebuild_parser()
        if args.mode in ["audit", "diagnose", "coverage"]:
            if not args.compiler or not args.compiler.is_absolute() or not args.compiler_evidence:
                raise ValueError("Direct audit requires explicit compiler and recorded provenance")
            doc = registered(args.compiler_evidence, audit.ledger)
            if sha(args.compiler) != doc["sha256"][str(args.compiler.relative_to(ROOT))]: raise ValueError("Recorded compiler changed")
            audit.compiler = args.compiler
            entry = next(e for e in audit.ledger["experiments"] if e["id"]==args.compiler_evidence)
            audit.report["candidate_provenance"] = dict(experiment=args.compiler_evidence,
                evidence=entry["evidence"], evidence_sha256=entry["evidence_sha256"])
        if args.mode == "coverage":
            if not args.coverage_evidence: raise ValueError("Coverage audit requires a recorded full recompile")
            audit.coverage()
        elif args.mode == "diagnose": audit.diagnose_remaining()
        else: audit.controls()
        if args.mode in ["build", "parser"]:
            audit.allocator();audit.negatives();audit.pch();audit.harness()
        if args.kernel_cases: audit.kernel_cases()
    except Exception as error: audit.report["error"] = str(error)
    return audit.finish()


if __name__ == "__main__":
    sys.exit(main())
