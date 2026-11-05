#!/usr/bin/env python3
"""Witness-preserving Clang17 AST hardening; host compilation only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from xnu_macho_tools import macho

BASE = ROOT / "artifacts/xnu-compiler-types/frontend-session1"
PROFILE = ROOT / "artifacts/xnu-compiler-types/gnu-void-session1"
PATCHES = ROOT / "patches/compiler-hardening"
FIXTURES = ROOT / "fixtures/public/xnu-compiler-hardening"
NDK = Path("/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin")


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def registered(identifier, ledger):
    exp = next(e for e in ledger["experiments"] if e["id"] == identifier)
    path = ROOT / exp["evidence"]
    if sha(path) != exp["evidence_sha256"]:
        raise ValueError("Recorded evidence changed: " + identifier)
    doc = json.loads(path.read_text())
    for n, h in doc["sha256"].items():
        if sha(ROOT / n) != h:
            raise ValueError("Recorded artifact changed: " + n)
    return doc


class Audit:
    def __init__(self, args):
        self.args = args
        self.out = ROOT / "artifacts/xnu-compiler-hardening" / args.run
        if self.out.resolve() != self.out:
            raise ValueError("Run path must not traverse symlinks")
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / "builder.py")
        self.report = dict(kind="host-test", origin="local-host", outcome="fail",
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            summary="Incomplete actual compiler hardening audit", commands=[],
            checks=[], device_executed=False, full_kernel_qualified=False,
            apple_private_abi_qualified=False, mode=args.mode)
        self.ledger = json.loads((ROOT / "state/lab.json").read_text())

    def run(self, argv, label, cwd=ROOT, timeout=90):
        argv = list(map(str, argv))
        executable = shutil.which(argv[0])
        if executable:
            self.report.setdefault("tools_sha256", {})[str(Path(executable).resolve())] = sha(executable)
        so, se = self.out / (label + ".stdout.txt"), self.out / (label + ".stderr.txt")
        print(label, flush=True)
        # Preserve binary archive extraction exactly; decode only diagnostic reads.
        with so.open("wb") as stdout, se.open("wb") as stderr:
            try:
                proc = subprocess.Popen(argv, stdout=stdout, stderr=stderr, cwd=cwd,
                    env=dict(os.environ, LC_ALL="C"), start_new_session=True)
                code, timed_out = proc.wait(timeout=timeout), False
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                code, timed_out = None, True
        self.report["commands"].append(dict(argv=argv, cwd=str(cwd), exit_code=code,
            timed_out=timed_out, stdout=str(so.relative_to(ROOT)), stderr=str(se.relative_to(ROOT))))
        return code, so.read_bytes().decode("utf-8", errors="replace"), se.read_bytes().decode("utf-8", errors="replace")

    def must(self, argv, label, **kwargs):
        code, stdout, stderr = self.run(argv, label, **kwargs)
        if code != 0:
            raise RuntimeError(label + " failed; see retained diagnostics")
        return stdout

    def check(self, name, ok, **data):
        self.report["checks"].append(dict(name=name, pass_check=bool(ok), **data))

    def inputs(self):
        registered("TYPECOMP-008", self.ledger)
        base_doc = registered("TYPECOMP-002", self.ledger)
        registered("TYPECOMP-007", self.ledger)
        self.private, self.build = BASE / "compiler-source", BASE / "compiler-build"
        counts = []
        for witness, root in [(BASE / "compiler-source-files.json", self.private),
                              (BASE / "reuse-files.json", self.build)]:
            if sha(witness) != base_doc["sha256"][str(witness.relative_to(ROOT))]:
                raise ValueError("Witness differs from recorded parent")
            files = json.loads(witness.read_text())
            counts.append(len(files))
            if witness.name == "compiler-source-files.json":
                actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts}
                if actual != set(files):
                    raise ValueError("Compiler source file set differs")
            for n, h in files.items():
                if sha(root / n) != h:
                    raise ValueError("Compiler reuse input changed: " + n)
        old = json.loads((BASE / "report.json").read_text())
        self.host_sha = old["host_cxx_sha256"]
        self.report["parent_witnesses"] = {str(p.relative_to(ROOT)): sha(p) for p in [
            BASE / "compiler-source-files.json", BASE / "reuse-files.json",
            ROOT / "state/evidence/TYPECOMP-008.json", ROOT / "state/evidence/TYPECOMP-002.json",
            ROOT / "state/evidence/TYPECOMP-007.json"]}
        self.compiler = PROFILE / "clang"
        self.check("input-witnesses", True, source_files=counts[0], build_inputs=counts[1],
                   compiler_sha256=sha(self.compiler))
        text = self.must([shutil.which("ninja"), "-C", self.build, "-t", "commands", "bin/clang-17"], "link-recipe")
        command = shlex.split(text.splitlines()[-1])
        if command[:2] == [":", "&&"]: command = command[2:]
        if command[-2:] == ["&&", ":"]: command = command[:-2]
        if any(t in command for t in ["&&", ";", "|", "||"]) or sha(command[0]) != self.host_sha:
            raise ValueError("Unexpected original link argv")
        self.link = command
        for lib in ["libclangParse.a", "libclangSema.a"]:
            self.link[self.link.index("lib/" + lib)] = str(PROFILE / lib)
        self.report["link_inputs_sha256"] = {str((self.build / p).resolve()): sha(self.build / p)
            for p in self.link if p.endswith((".a", ".o")) and (self.build / p).is_file()}

    def build_harness(self, ast_archive=None):
        source = self.out / "raw-evaluator.cpp"
        shutil.copyfile(PATCHES / source.name, source)
        obj = self.out / "raw-evaluator.o"
        flags = ["-std=c++17", "-fno-rtti", "-D_GNU_SOURCE", "-D__STDC_CONSTANT_MACROS",
                 "-D__STDC_FORMAT_MACROS", "-D__STDC_LIMIT_MACROS"]
        includes = [self.private / "src/clang/include", self.build / "tools/clang/include",
                    self.private / "src/llvm/include", self.build / "include"]
        self.must([NDK / "clang++", *flags, *[x for p in includes for x in ["-I", p]],
            "-c", source, "-o", obj], "harness-compile", timeout=180)
        link = [t for t in self.link if not t.endswith(".o")]
        link.insert(1, str(obj))
        if ast_archive:
            link[link.index("lib/libclangAST.a")] = str(ast_archive)
        exe = self.out / "raw-evaluator"
        link[link.index("-o") + 1] = str(exe)
        self.must(link, "harness-link", cwd=self.build, timeout=180)
        self.report["harness_sha256"] = sha(exe)
        for mode in ["summary-pointer", "summary-data", "signature-pointer", "signature-data", "summary-reference", "signature-reference"]:
            code, stdout, stderr = self.run([exe, mode], "raw-" + mode)
            self.check("raw-" + mode, code == 0, exit_code=code, observed=stdout.strip())

    def templates(self):
        for builtin in ["summary", "signature", "compatible"]:
            operand = "T,T" if builtin == "compatible" else "T"
            spelling = "__builtin_xnu_types_compatible" if builtin == "compatible" else "__builtin_xnu_type_" + builtin
            source = self.out / ("mangle-" + builtin + ".cpp")
            source.write_text("struct Word { unsigned long long x; };\n"
                f"template<class T> auto s24_{builtin}(T*) -> decltype(({spelling}({operand}),0)) {{ return 7; }}\n"
                f"template int s24_{builtin}<Word>(Word*);\n")
            obj = source.with_suffix(".o")
            code, _, stderr = self.run([*self.flags(), "-c", source, "-o", obj], "mangle-" + builtin)
            defined = []
            demangled = []
            if code == 0:
                self.check("arm64-" + builtin, macho(obj)["filetype"] == 1)
                text = self.must([NDK / "llvm-nm", "--defined-only", "--just-symbol-name", obj], "symbols-" + builtin)
                defined = [n for n in text.splitlines() if n.startswith("__Z")]
                for index, name in enumerate(defined):
                    dm = self.must([NDK / "llvm-cxxfilt", name[1:]], "demangle-" + builtin + "-" + str(index)).strip()
                    demangled.append(dm)
            valid = len(defined) == 1 and len(demangled) == 1 and spelling in demangled[0] and "Word" in demangled[0]
            self.check("dependent-mangle-" + builtin, valid, exit_code=code,
                symbols=defined, demangled=demangled, diagnostic=stderr[-1500:])

    def flags(self, language="c++"):
        return [self.compiler, "-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc",
                "-std=gnu++17" if language == "c++" else "-std=gnu11"]

    def qualify(self):
        self.report["serialization_limits"] = [
            "Same experimental AST schema only; foreign compiler serialization is not qualified",
            "ASTReader validates major version and full repository version before imports",
            "No -fno-validate-pch or disabled validation is used"]
        for language, extension in [("c", "c"), ("c++", "cpp")]:
            header = self.out / ("metadata-" + extension + ".h")
            assertion = "_Static_assert" if language == "c" else "static_assert"
            text = '''typedef unsigned long long Address __attribute__((xnu_usage_semantics("pointer")));
struct Mixed { Address pointer; unsigned long long data; };
struct Data { unsigned long long one, two; };
struct Pointers { void *one, *two; };
'''
            for expression in ["sizeof(struct Mixed)==16", "__builtin_xnu_type_summary(struct Mixed)==6",
                               "__builtin_xnu_type_summary(struct Data)==4", "__builtin_xnu_type_summary(struct Pointers)==2",
                               "__builtin_xnu_types_compatible(struct Data,struct Data)",
                               "!__builtin_xnu_types_compatible(struct Data,struct Pointers)"]:
                text += f'{assertion}({expression}, "independent layout/type expectation");\n'
            if language == "c++":
                text += '''template<class T> struct Metadata {
  static constexpr unsigned summary = __builtin_xnu_type_summary(T);
  static constexpr const char *signature = __builtin_xnu_type_signature(T);
};
template<class T> auto pch_summary(T*) -> decltype((__builtin_xnu_type_summary(T),0)) { return 1; }
template<class T> auto pch_signature(T*) -> decltype((__builtin_xnu_type_signature(T),0)) { return 2; }
template<class T> auto pch_compatible(T*) -> decltype((__builtin_xnu_types_compatible(T,T),0)) { return 3; }
template<bool B> struct Enabled {};
template<> struct Enabled<true> { using type = int; };
template<class T, typename Enabled<__builtin_xnu_type_summary(T)==4>::type = 0>
constexpr int data_only(T*) { return 41; }
constexpr int data_only(...) { return 17; }
template<class T, typename Enabled<__builtin_xnu_types_compatible(T,Pointers)>::type = 0>
constexpr int pointer_only(T*) { return 23; }
constexpr int pointer_only(...) { return 19; }
'''
            header.write_text(text)
            source = self.out / ("metadata-consumer." + extension)
            extra = '''const char *s24_signature = __builtin_xnu_type_signature(struct Mixed);
unsigned s24_summary = __builtin_xnu_type_summary(struct Mixed);
'''
            if language == "c++":
                extra += '''static_assert(Metadata<Mixed>::summary==6);
static_assert(Metadata<Mixed>::signature[0]=='1' && Metadata<Mixed>::signature[1]=='2' && Metadata<Mixed>::signature[2]=='\\0');
static_assert(Metadata<Data>::summary==4 && Metadata<Pointers>::summary==2);
static_assert(data_only((Data*)0)==41 && data_only((Pointers*)0)==17);
static_assert(pointer_only((Pointers*)0)==23 && pointer_only((Data*)0)==19);
template int pch_summary<Mixed>(Mixed*);
template int pch_signature<Mixed>(Mixed*);
template int pch_compatible<Mixed>(Mixed*);
'''
            source.write_text(extra)
            pch = header.with_suffix(".pch")
            flags = self.flags(language)
            code, _, stderr = self.run([*flags, "-Werror=unknown-attributes", "-x", language + "-header",
                header, "-o", pch], "pch-create-" + extension)
            self.check("pch-create-" + extension, code == 0, exit_code=code, diagnostic=stderr[-1000:])
            if code != 0: continue
            objects = []
            for kind, include in [("textual", ["-include", header]), ("pch", ["-include-pch", pch])]:
                obj = self.out / (kind + "-" + extension + ".o")
                code, _, stderr = self.run([*flags, *include, "-c", source, "-o", obj], kind + "-consume-" + extension)
                self.check(kind + "-consume-" + extension, code == 0 and macho(obj)["filetype"] == 1,
                           exit_code=code, diagnostic=stderr[-1000:])
                if code == 0: objects.append(obj)
            if len(objects) == 2:
                # Binary equality proves persisted annotations/templates produce
                # the same actual metadata/object as textual inclusion.
                self.check("pch-textual-object-equality-" + extension, objects[0].read_bytes() == objects[1].read_bytes(),
                    object_sha256=[sha(p) for p in objects])
                if language == "c++": self.symbol_agreement(header, objects[1])
            wrong_flags = flags.copy()
            wrong_flags[wrong_flags.index("arm64-apple-ios16.5")] = "arm64e-apple-ios16.5"
            code, _, stderr = self.run([*wrong_flags, "-include-pch", pch, "-fsyntax-only", source], "pch-wrong-target-" + extension)
            self.check("pch-wrong-target-" + extension, code == 1 and "error:" in stderr and "target" in stderr,
                       exit_code=code, diagnostic=stderr[-1500:])
            broken = self.out / (extension + "-truncated.pch")
            broken.write_bytes(pch.read_bytes()[:128])
            code, _, stderr = self.run([*flags, "-include-pch", broken, "-fsyntax-only", source], "pch-truncated-" + extension)
            self.check("pch-truncated-" + extension, code == 1 and "error:" in stderr,
                       exit_code=code, diagnostic=stderr[-1500:])
        self.negative_layouts()
        self.foreign_pch()
        self.kernel_units()

    def foreign_pch(self):
        source = self.out / "foreign-header.h"
        source.write_text("struct Foreign { unsigned long long word; };\n")
        pch = source.with_suffix(".pch")
        self.must([NDK / "clang", "-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc",
                   "-std=gnu++17", "-x", "c++-header", source, "-o", pch], "foreign-pch-create")
        consumer = self.out / "foreign-consumer.cpp"
        consumer.write_text("static_assert(sizeof(Foreign)==8);\n")
        code, _, stderr = self.run([*self.flags(), "-include-pch", pch, "-fsyntax-only", consumer], "foreign-pch-load")
        self.check("foreign-pch-rejected", code == 1 and
                   "error: PCH file uses an older PCH format that is no longer supported" in stderr,
                   exit_code=code, diagnostic=stderr[-1500:])

    def symbol_agreement(self, header, definition):
        source = self.out / "template-caller.cpp"
        source.write_text('''extern template int pch_summary<Mixed>(Mixed*);
extern template int pch_signature<Mixed>(Mixed*);
extern template int pch_compatible<Mixed>(Mixed*);
int caller(Mixed *p) { return pch_summary(p) + pch_signature(p) + pch_compatible(p); }
''')
        obj = source.with_suffix(".o")
        self.must([*self.flags(), "-include", header, "-c", source, "-o", obj], "template-caller")
        used = self.must([NDK / "llvm-nm", "--undefined-only", "--just-symbol-name", obj], "template-undefined")
        provided = self.must([NDK / "llvm-nm", "--defined-only", "--just-symbol-name", definition], "template-defined")
        required = set(n for n in used.splitlines() if n.startswith("__Z"))
        self.check("separate-tu-template-symbol-agreement", len(required) == 3 and required <= set(provided.splitlines()),
                   required=sorted(required))

    def negative_layouts(self):
        cases = {
            "reference": "constexpr auto x=__builtin_xnu_type_summary(int&);",
            "virtual-base": "struct B { int x; }; struct D:virtual B {}; constexpr auto x=__builtin_xnu_type_summary(D);",
            "member-pointer": "struct X{}; constexpr auto x=__builtin_xnu_type_summary(int X::*);",
            "arm64e": "constexpr auto x=__builtin_xnu_type_summary(void*);",
            "vla": "void f(int n) { int a[n]; (void)__builtin_xnu_type_summary(__typeof__(a)); }",
        }
        for name, text in cases.items():
            source = self.out / ("negative-" + name + ".cpp")
            source.write_text(text + "\n")
            flags = self.flags()
            if name == "arm64e": flags[flags.index("arm64-apple-ios16.5")] = "arm64e-apple-ios16.5"
            code, _, stderr = self.run([*flags, "-fsyntax-only", source], "negative-" + name)
            self.check("negative-" + name, code == 1 and "experimental XNU metadata does not support" in stderr,
                       exit_code=code, diagnostic=stderr[-1500:])

    def kernel_units(self):
        registered("IIGABI-013", self.ledger)
        previous = json.loads((ROOT / "fixtures/public/xnu-dependencies/firehose-session1.json").read_text())
        witness = ROOT / "artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json"
        kernel = ROOT / "artifacts/xnu-prepare/e1s-dependency-source-session1/xnu"
        if sha(witness) != previous["kernel_tree_manifest_sha256"]:
            raise ValueError("Prepared kernel source witness changed")
        files = json.loads(witness.read_text())
        actual = {str(p.relative_to(kernel)) for p in kernel.rglob("*") if p.is_file() and ".git" not in p.relative_to(kernel).parts}
        if actual != set(files) or any(sha(kernel / n) != h for n, h in files.items()):
            raise ValueError("Prepared source file set/bytes changed")
        reuse = json.loads((ROOT / "fixtures/public/open-kernel-inputs/reusable-components.json").read_text())["pthread"]
        target = ROOT / "artifacts/open-kernel-inputs/typed-pthread-session1/header-tree/src/Libraries/AvailabilityVersions/include"
        if sha(target / "TargetConditionals.h") != reuse["target_header_sha256"]:
            raise ValueError("Target header changed")
        for n, h in reuse["mach_generated_headers"].items():
            if sha(ROOT / reuse["mach_generated_root"] / "mach" / (n + ".h")) != h:
                raise ValueError("Recorded MIG client header changed: " + n)
        iig = ROOT / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1"
        dirs = [target, iig / "setup-headers", iig / "generated", iig / "mach-server-headers",
                ROOT / reuse["mach_generated_root"], *[kernel / n for n in ["osfmk", "bsd", "iokit", "libkern", "pexpert", "EXTERNAL_HEADERS", "osfmk/libsa"]]]
        definitions = ["APPLE=1", "KERNEL=1", "KERNEL_PRIVATE=1", "PRIVATE=1", "DRIVERKIT_PRIVATE=1",
            "__MACHO__=1", "XNU_KERNEL_PRIVATE=1", "XNU_KERN_EVENT_DATA_IS_VLA=1",
            "ARM64_BOARD_CONFIG_E1S=1", "XNU_NO_TYPE_BUILTINS=0", "volatile=__volatile"]
        observations = []
        for name in ["osfmk/kern/kalloc.c", "libkern/c++/OSData.cpp", "pexpert/arm/pe_identify_machine.c"]:
            source = kernel / name
            label = "unit-" + source.stem
            obj = self.out / (label + ".o")
            code, _, stderr = self.run([*self.flags("c++" if source.suffix == ".cpp" else "c"), "-mkernel",
                *["-D" + d for d in definitions], *[x for d in dirs for x in ["-I", d]],
                "-ferror-limit=4", "-c", source, "-o", obj], label)
            observations.append(dict(source=name, source_sha256=sha(source), exit_code=code,
                actual_arm64_object=code == 0 and macho(obj)["filetype"] == 1,
                missing_headers=re.findall(r"fatal error: '([^']+)' file not found", stderr),
                diagnostic=stderr[-6000:]))
        templates = ["osfmk/conf/Makefile.template", "pexpert/conf/Makefile.template", "libkern/conf/Makefile.template",
                     "SETUP/config/mkheaders.c", "makedefs/MakeInc.def", "osfmk/vm/vm_map.h", "osfmk/arm/machine_routines.h"]
        self.report["kernel_configuration_sources_sha256"] = {n: sha(kernel / n) for n in templates}
        self.report["whole_kernel_units"] = observations
        self.report["whole_kernel_profile"] = dict(complete=False, definitions=definitions,
            include_roots=[str(d.relative_to(ROOT)) for d in dirs], source_witness_sha256=sha(witness),
            missing_configuration="Complete generated RELEASE/ARM64/E1S config/export tree, CURRENT_MACHINE_CONFIG_LC and CONFIG_DEFINES/SEED_DEFINES are not qualified by this partial profile")
        self.report["whole_kernel_profile"]["per_component_requirements"] = {
            "osfmk": "osfmk/conf/Makefile.template:19 requires -include meta_features.h -DMACH_KERNEL_PRIVATE -DMACH_KERNEL",
            "pexpert": "pexpert/conf/Makefile.template:19 requires -include meta_features.h -DPEXPERT_KERNEL_PRIVATE",
            "libkern": "libkern/conf/Makefile.template:19 requires -include meta_features.h -DLIBKERN_KERNEL_PRIVATE -DOSALLOCDEBUG=1",
            "generator": "SETUP/config/mkheaders.c generates meta_features.h from the selected component configuration; no fabricated header supplied",
            "observed_errors": "vm_map_entry_t is guarded by MACH_KERNEL_PRIVATE in osfmk/vm/vm_map.h; ml_io_map by PEXPERT_KERNEL_PRIVATE/MACH_KERNEL_PRIVATE in osfmk/arm/machine_routines.h"}
        self.check("actual-kernel-unit-observations", len(observations) == 3 and all(x["exit_code"] in [0, 1] for x in observations))

    def rebuild(self):
        source = self.out / "ast-source"
        for name in ["ExprConstant.cpp", "ItaniumMangle.cpp"]:
            rel = Path("src/clang/lib/AST") / name
            dest = source / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.private / rel, dest)
        patch = PATCHES / "0001-evaluate-and-mangle-xnu-traits.patch"
        self.must(["git", "-C", source, "apply", "--check", patch], "patch-check")
        self.must(["git", "-C", source, "apply", patch], "patch-apply")
        archive = self.out / "libclangAST.a"
        shutil.copyfile(self.build / "lib/libclangAST.a", archive)
        for name in ["ExprConstant.cpp", "ItaniumMangle.cpp"]:
            rel = Path("src/clang/lib/AST") / name
            recipe = self.must([shutil.which("ninja"), "-C", self.build, "-t", "commands",
                "tools/clang/lib/AST/CMakeFiles/obj.clangAST.dir/" + name + ".o"], name + "-recipe")
            argv = shlex.split(recipe.splitlines()[-1])
            if sha(argv[0]) != self.host_sha or str(self.private / rel) not in argv:
                raise ValueError("Unexpected AST compile argv")
            argv[argv.index(str(self.private / rel))] = str(source / rel)
            obj = self.out / (name + ".o")
            for flag, value in [("-o", obj), ("-MF", obj.with_suffix(".d")), ("-MT", obj)]:
                if flag in argv: argv[argv.index(flag) + 1] = str(value)
            self.must(argv, name + "-compile", cwd=self.build, timeout=180)
            self.must([NDK / "llvm-ar", "r", archive, obj], name + "-archive")
            self.must([NDK / "llvm-ar", "p", archive, obj.name], name + "-extract")
            if sha(self.out / (name + "-extract.stdout.txt")) != sha(obj):
                raise ValueError("Archive member does not match actual new object")
        argv = self.link.copy()
        argv[argv.index("lib/libclangAST.a")] = str(archive)
        self.compiler = self.out / "clang"
        argv[argv.index("-o") + 1] = str(self.compiler)
        self.must(argv, "compiler-link", cwd=self.build, timeout=180)
        self.report["patch_sha256"] = sha(patch)
        return archive

    def finish(self):
        checks = self.report["checks"]
        self.report["outcome"] = "pass" if checks and all(c["pass_check"] for c in checks) and "error" not in self.report else "fail"
        self.report["summary"] = "Actual experimental source compiler controls; bounded host result with full kernel/Apple ABI/native qualification false"
        if self.compiler.is_file(): self.report["compiler_sha256"] = sha(self.compiler)
        dump(self.out / "report.json", self.report)
        files = [p for p in self.out.rglob("*") if p.is_file() and p.name != "evidence.json"]
        # Include the reused compiler in the capsule even for a baseline run.
        files = sorted(set(files + [self.compiler]))
        evidence = {k: self.report[k] for k in ["kind", "origin", "outcome", "recorded_at", "summary", "commands"]}
        evidence.update(commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files],
            sha256={str(p.relative_to(ROOT)): sha(p) for p in files}, device_executed=False,
            full_kernel_qualified=False, apple_private_abi_qualified=False)
        dump(self.out / "evidence.json", evidence)
        print(json.dumps({"outcome": self.report["outcome"], "checks": checks, "error": self.report.get("error")}))
        return 0 if self.report["outcome"] == "pass" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--mode", choices=["baseline", "harden", "qualify", "foreign"], required=True)
    p.add_argument("--compiler", type=Path)
    p.add_argument("--compiler-evidence", help="Registered experiment ID binding the actual compiler")
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        p.error("Use a fresh canonical run name")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    audit = Audit(args)
    try:
        audit.inputs()
        if args.mode in ["qualify", "foreign"]:
            if not args.compiler or not args.compiler.is_absolute() or not args.compiler_evidence:
                raise ValueError("Qualification requires explicit compiler and recorded experiment ID")
            doc = registered(args.compiler_evidence, audit.ledger)
            if sha(args.compiler) != doc["sha256"][str(args.compiler.relative_to(ROOT))]:
                raise ValueError("Compiler differs from recorded evidence")
            audit.compiler = args.compiler
            if args.mode == "qualify": audit.qualify()
            else: audit.foreign_pch()
        else:
            archive = audit.rebuild() if args.mode == "harden" else None
            audit.templates()
            audit.build_harness(archive)
    except Exception as error:
        audit.report["error"] = str(error)
        # inputs() may have rejected a parent before setting the compiler.
        if not hasattr(audit, "compiler"): audit.compiler = PROFILE / "clang"
    return audit.finish()


if __name__ == "__main__":
    sys.exit(main())
