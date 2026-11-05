#!/usr/bin/env python3
"""Generate actual selected XNU component configuration in isolated host outputs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from xnu_macho_tools import macho
from xnu_compiler_hardening import registered, sha

KERNEL = ROOT / "artifacts/xnu-prepare/e1s-dependency-source-session1/xnu"
HOST = ROOT / "artifacts/xnu-host-tools/generators-session2/prefix/bin"
COMPILER = ROOT / "artifacts/xnu-compiler-hardening/ast-patch-session1/clang"


def dump(path, doc):
    path.write_text(json.dumps(doc, indent=2) + "\n")


class Build:
    def __init__(self, args):
        self.args = args
        self.out = ROOT / "artifacts/xnu-kernel-config" / args.run
        if self.out.resolve() != self.out:
            raise ValueError("Canonical fresh run directory required")
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / "builder.py")
        self.report = dict(kind="host-test", origin="local-host", outcome="fail",
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            commands=[], checks=[], units=[], device_executed=False,
            sdk_used=False, full_kernel_profile_qualified=False)

    def run(self, argv, label, cwd=None, extra_env=None, timeout=90):
        argv = list(map(str, argv))
        executable = shutil.which(argv[0])
        if executable:
            self.report.setdefault("tools_sha256", {})[str(Path(executable).resolve())] = sha(executable)
        so, se = self.out / (label + ".stdout.txt"), self.out / (label + ".stderr.txt")
        env = dict(os.environ, LC_ALL="C", PATH=str(HOST) + os.pathsep + os.environ.get("PATH", ""))
        env.update(extra_env or {})
        print(label, flush=True)
        with so.open("wb") as stdout, se.open("wb") as stderr:
            proc = subprocess.Popen(argv, cwd=cwd or self.out, env=env,
                stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code, timed_out = proc.wait(timeout=timeout), False
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try: proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                code, timed_out = None, True
        self.report["commands"].append(dict(argv=argv, cwd=str(cwd or self.out),
            environment_overrides=extra_env or {}, exit_code=code, timed_out=timed_out,
            stdout=str(so.relative_to(ROOT)), stderr=str(se.relative_to(ROOT))))
        return code, so.read_text(errors="replace"), se.read_text(errors="replace")

    def must(self, argv, label, **kwargs):
        code, stdout, stderr = self.run(argv, label, **kwargs)
        if code != 0: raise RuntimeError(label + " failed; see retained diagnostics")
        return stdout

    def check(self, name, ok, **data):
        self.report["checks"].append(dict(name=name, passed=bool(ok), **data))

    def inputs(self):
        ledger = json.loads((ROOT / "state/lab.json").read_text())
        self.report["parents"] = {}
        for name in ["HARDEN-002", "HARDEN-005", "IIGABI-013", "HOSTGEN-002"]:
            registered(name, ledger)
            e = next(e for e in ledger["experiments"] if e["id"] == name)
            self.report["parents"][name] = dict(evidence=e["evidence"], sha256=e["evidence_sha256"])
        parent = json.loads((ROOT / "fixtures/public/xnu-dependencies/firehose-session1.json").read_text())
        witness = ROOT / "artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json"
        if sha(witness) != parent["kernel_tree_manifest_sha256"]:
            raise ValueError("Selected source witness changed")
        files = json.loads(witness.read_text())
        actual = {str(p.relative_to(KERNEL)) for p in KERNEL.rglob("*") if p.is_file() and ".git" not in p.relative_to(KERNEL).parts}
        if set(files) != actual or any(sha(KERNEL / p) != h for p, h in files.items()):
            raise ValueError("Selected source set or bytes changed")
        self.report["kernel_source_witness_sha256"] = sha(witness)
        self.report["kernel_source_files"] = len(files)
        self.report["compiler_sha256"] = sha(COMPILER)
        self.check("witnessed-inputs", True)

    def generator(self):
        source = self.out / "generator-source"
        source.mkdir()
        original = KERNEL / "SETUP/config"
        for p in original.iterdir():
            if p.is_file(): shutil.copyfile(p, source / p.name)
        dump(self.out / "generator-source-files.json", {p.name: sha(p) for p in source.iterdir() if p.is_file()})
        self.must(["bison", "-y", "-d", "-d", "-o", "parser.c", "parser.y"], "generator-bison", cwd=source)
        self.must(["flex", "--header-file=lexer.yy.h", "-o", "lexer.yy.c", "lexer.l"], "generator-flex", cwd=source)
        names = ["externs", "main", "mkheaders", "mkioconf", "mkmakefile", "openp", "searchp", "lexer.yy", "parser"]
        for name in names:
            self.must([self.args.host_cc, "-std=gnu11", "-DYY_NO_INPUT", "-Wall", "-g", "-O0",
                "-I", source, "-c", source / (name + ".c"), "-o", source / (name + ".o")], "generator-" + name)
        hostroot = self.out / "host"
        generator = hostroot / "SETUP/config/config"
        generator.parent.mkdir(parents=True)
        self.must([self.args.host_cc, "-o", generator, *[source / (n + ".o") for n in names]], "generator-link")
        self.report["generator_sha256"] = sha(generator)
        self.check("actual-config-generator-built", True, object_count=len(names))
        return hostroot

    def configurations(self, hostroot):
        configs = {}
        for component in ["osfmk", "libkern", "pexpert"]:
            output = self.out / "configuration" / component / "RELEASE"
            output.mkdir(parents=True)
            environment = dict(SRCROOT=str(KERNEL), SOURCE=str(KERNEL / component / "conf") + "/", OBJROOT=str(hostroot))
            code, stdout, stderr = self.run([HOST / "tcsh", "-f", KERNEL / "SETUP/config/doconf",
                "-c", "-cpu", "arm64", "-soc", "e1s", "-platform", "iPhoneOS", "-d", output,
                "-s", KERNEL / component / "conf", "-m", KERNEL / "config", "-verbose", "RELEASE"],
                "configure-" + component, extra_env=environment)
            makefile = output / "Makefile"
            features = output / "meta_features.h"
            valid = code == 0 and makefile.is_file() and features.is_file()
            self.check("configure-" + component, valid, exit_code=code, diagnostic=stderr[-1500:])
            if not valid: continue
            content = makefile.read_text()
            defines = re.findall(r"^export CONFIG_DEFINES =(.*)$", content, re.M)
            if len(defines) != 1: raise ValueError("Unexpected generated CONFIG_DEFINES")
            values = shlex.split(defines[0])
            if any(not d.startswith("-D") for d in values): raise ValueError("Unexpected generated compiler defines")
            configs[component] = dict(root=output, defines=values)
            dump(self.out / (component + "-generated-files.json"), {str(p.relative_to(output)): sha(p) for p in output.iterdir() if p.is_file()})
            self.report.setdefault("configurations", {})[component] = dict(root=str(output.relative_to(ROOT)),
                config_defines=values, meta_features_sha256=sha(features), makefile_sha256=sha(makefile))
        return configs

    def reuse_configurations(self):
        ledger = json.loads((ROOT / "state/lab.json").read_text())
        doc = registered(self.args.config_evidence, ledger)
        previous = self.args.reuse_config_run.resolve()
        if not previous.is_relative_to(ROOT / "artifacts/xnu-kernel-config"):
            raise ValueError("Reuse only a recorded isolated configuration run")
        report_path = previous / "report.json"
        if sha(report_path) != doc["sha256"][str(report_path.relative_to(ROOT))]:
            raise ValueError("Configuration report differs from recorded evidence")
        report = json.loads(report_path.read_text())
        names = {"witnessed-inputs", "actual-config-generator-built", "configure-osfmk", "configure-libkern", "configure-pexpert"}
        if not names <= {c["name"] for c in report["checks"] if c["passed"]}:
            raise ValueError("Prior generator/configuration checks did not pass")
        result = {}
        for component in ["osfmk", "libkern", "pexpert"]:
            config = report["configurations"][component]
            result[component] = dict(root=ROOT / config["root"], defines=config["config_defines"])
        self.report["reused_config_evidence"] = self.args.config_evidence
        self.report["configurations"] = report["configurations"]
        self.report["generator_sha256"] = report["generator_sha256"]
        self.check("recorded-generator-configurations-reused", True)
        return result

    def configuration_controls(self, configs):
        for component, values in configs.items():
            header = self.out / (component + "-configuration-controls.c")
            text = '''#include <meta_features.h>
#if CONFIG_VNODES != 1024 || !CONFIG_EMBEDDED || !CONFIG_PMAP_PPL || !NOS_ARM_PMAP || !CONFIG_KERNEL_INTEGRITY
#error S24_EXPECTED_SELECTED_E1S_CONFIG
#endif
'''
            if component == "osfmk":
                text += '''#if MACH_ASSERT != 0 || MACH_KDP != 1 || CONFIG_DTRACE != 0
#error S24_EXPECTED_RELEASE_OSFMK_FEATURES
#endif
'''
            if component == "libkern":
                text += '''#if LIBKERNCPP != 1 || IOTRACKING != 0 || CONFIG_DTRACE != 0
#error S24_EXPECTED_RELEASE_LIBKERN_FEATURES
#endif
'''
            if component == "pexpert":
                text += '''#if CONFIG_DTRACE != 0
#error S24_EXPECTED_RELEASE_PEXPERT_FEATURES
#endif
'''
            header.write_text(text)
            flags = [COMPILER, "-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc", "-std=gnu11",
                     *values["defines"], "-I", values["root"], "-fsyntax-only", header]
            code, _, stderr = self.run(flags, "config-control-" + component)
            self.check("config-control-" + component, code == 0, exit_code=code, diagnostic=stderr[-2000:])
            # Wrong board-size metadata must not pass merely because files exist.
            mutated = flags[:]
            at = next(i for i, a in enumerate(mutated) if str(a).startswith("-DCONFIG_VNODES="))
            mutated[at] = "-DCONFIG_VNODES=1025"
            code, _, stderr = self.run(mutated, "config-mutation-" + component)
            self.check("config-mutation-" + component, code == 1 and "S24_EXPECTED_SELECTED_E1S_CONFIG" in stderr,
                       exit_code=code, diagnostic=stderr[-1000:])

    def internal_exports(self):
        roots, declarations = [], []
        for relative in ["security", "san/memory", "san/coverage"]:
            directory = KERNEL / relative
            makefile = directory / "Makefile"
            # Only a small, fail-closed variable subset is needed by these
            # actual source-only export lists. No Makefile execution or eval.
            text = makefile.read_text().replace("\\\n", " ")
            assignments = dict(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)[ \t]*=[ \t]*(.*)$", text))

            def resolve(name, trail=()):
                if name in trail or name not in assignments: raise ValueError("Unknown/cyclic export variable: " + name)
                value = assignments[name]
                value = re.sub(r"\$[({]([A-Z][A-Z0-9_]*)[)}]", lambda m: resolve(m[1], (*trail, name)), value)
                if "$" in value or "#" in value: raise ValueError("Unsupported export expression: " + value)
                return value.strip()

            target_dir = resolve("EXPORT_MI_DIR")
            names = resolve("EXPORT_MI_LIST").split()
            if not names or Path(target_dir).name != target_dir or any(Path(n).name != n or not n.endswith(".h") for n in names):
                raise ValueError("Unexpected internal export paths")
            fragment = self.out / (relative.replace("/", "-") + "-exports.mk")
            fragment.write_text("\n".join(k + " = " + v for k, v in assignments.items()) +
                "\n$(info S24_DIR=$(EXPORT_MI_DIR))\n$(info S24_HEADERS=$(EXPORT_MI_LIST))\nall: ;\n")
            oracle = self.must(["make", "--no-print-directory", "-rR", "-f", fragment, "all"],
                "export-make-oracle-" + relative.replace("/", "-"))
            oracle_dir = re.findall(r"^S24_DIR=(.*)$", oracle, re.M)
            oracle_names = re.findall(r"^S24_HEADERS=(.*)$", oracle, re.M)
            if oracle_dir != [target_dir] or len(oracle_names) != 1 or oracle_names[0].split() != names:
                raise ValueError("Owned export resolver differs from actual GNU Make")
            component = Path(relative).parts[0]
            export_root = self.out / "EXPORT_HDRS" / component
            (export_root / target_dir).mkdir(parents=True, exist_ok=True)
            files = {}
            for name in names:
                original = directory / name
                destination = export_root / target_dir / name
                if destination.exists() and sha(original) != sha(destination): raise ValueError("Conflicting internal header export")
                shutil.copyfile(original, destination)
                if sha(original) != sha(destination): raise ValueError("Internal export copy changed bytes")
                files[str(destination.relative_to(export_root))] = sha(destination)
            declarations.append(dict(source=relative + "/Makefile", source_sha256=sha(makefile), root=str(export_root.relative_to(ROOT)), files=files))
            if export_root not in roots: roots.append(export_root)
        self.report["internal_exports"] = dict(declarations=declarations,
            rule="makedefs/MakeInc.rule:EXPORT_MI_INC_FILES uses byte-preserving install",
            rule_sha256=sha(KERNEL / "makedefs/MakeInc.rule"))
        self.check("declared-internal-exports", all(d["files"] for d in declarations),
                   header_count=sum(len(d["files"]) for d in declarations))
        return roots

    def units(self, configs):
        reuse = json.loads((ROOT / "fixtures/public/open-kernel-inputs/reusable-components.json").read_text())["pthread"]
        target = ROOT / "artifacts/open-kernel-inputs/typed-pthread-session1/header-tree/src/Libraries/AvailabilityVersions/include"
        if sha(target / "TargetConditionals.h") != reuse["target_header_sha256"]:
            raise ValueError("Target header changed")
        for n, h in reuse["mach_generated_headers"].items():
            if sha(ROOT / reuse["mach_generated_root"] / "mach" / (n + ".h")) != h:
                raise ValueError("Recorded MIG client header changed")
        iig = ROOT / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1"
        includes = [target, iig / "setup-headers", iig / "generated", iig / "mach-server-headers",
                    ROOT / reuse["mach_generated_root"], *[KERNEL / n for n in ["osfmk", "bsd", "iokit", "libkern", "pexpert", "EXTERNAL_HEADERS", "osfmk/libsa"]]]
        if self.args.internal_exports: includes = self.internal_exports() + includes
        self.report["include_roots"] = list(map(str, includes))
        cases = [("osfmk", "osfmk/kern/kalloc.c", ["MACH_KERNEL_PRIVATE", "MACH_KERNEL"]),
                 ("libkern", "libkern/c++/OSData.cpp", ["LIBKERN_KERNEL_PRIVATE", "OSALLOCDEBUG=1"]),
                 ("pexpert", "pexpert/arm/pe_identify_machine.c", ["PEXPERT_KERNEL_PRIVATE"])]
        for component, name, private in cases:
            if component not in configs: continue
            config = configs[component]
            source = KERNEL / name
            obj = self.out / (source.stem + ".o")
            flags = ["-target", "arm64-apple-ios16.5", "-ffreestanding", "-nostdinc", "-std=gnu++17" if source.suffix == ".cpp" else "-std=gnu11",
                "-mkernel", "-DAPPLE", "-DKERNEL", "-DKERNEL_PRIVATE", "-DXNU_KERNEL_PRIVATE", "-DPRIVATE", "-D__MACHO__=1",
                "-Dvolatile=__volatile", "-DXNU_KERN_EVENT_DATA_IS_VLA", "-DCURRENT_MACHINE_CONFIG_LC=e1s", "-DARM64_BOARD_CONFIG_E1S",
                "-DXNU_NO_TYPE_BUILTINS=0", *config["defines"], *["-D" + d for d in private],
                "-include", config["root"] / "meta_features.h", "-I", config["root"], *[x for p in includes for x in ["-I", p]]]
            code, stdout, stderr = self.run([COMPILER, *flags, "-ferror-limit=6", "-c", source, "-o", obj], "unit-" + source.stem)
            self.report["units"].append(dict(source=name, source_sha256=sha(source), component=component,
                exit_code=code, actual_arm64_object=code == 0 and macho(obj)["filetype"] == 1,
                object_sha256=sha(obj) if obj.is_file() else None, diagnostic=stderr[-12000:],
                missing_headers=re.findall(r"fatal error: '([^']+)' file not found", stderr)))

    def audit_objects(self):
        ledger = json.loads((ROOT / "state/lab.json").read_text())
        doc = registered(self.args.object_evidence, ledger)
        previous = self.args.audit_run.resolve()
        if not previous.is_relative_to(ROOT / "artifacts/xnu-kernel-config"):
            raise ValueError("Audit only recorded isolated kernel objects")
        report_path = previous / "report.json"
        if sha(report_path) != doc["sha256"][str(report_path.relative_to(ROOT))]:
            raise ValueError("Object report differs from recorded evidence")
        report = json.loads(report_path.read_text())
        if report["outcome"] != "pass": raise ValueError("Object audit requires an actual passing compile run")
        expected = {
            "osfmk/kern/kalloc.c": ["_kalloc_ext", "_kfree_ext", "_kalloc_type_impl_external"],
            "libkern/c++/OSData.cpp": ["__ZN6OSData12withCapacityEj", "__ZN6OSData16initWithCapacityEj"],
            "pexpert/arm/pe_identify_machine.c": ["_pe_identify_machine"],
        }
        if {u["source"] for u in report["units"]} != set(expected): raise ValueError("Unexpected source-unit set")
        tools = Path("/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin")
        for unit in report["units"]:
            name = unit["source"]
            obj = previous / (Path(name).stem + ".o")
            if not unit["actual_arm64_object"] or sha(obj) != unit["object_sha256"] or sha(KERNEL / name) != unit["source_sha256"]:
                raise ValueError("Recorded actual object/source bytes changed")
            header = macho(obj)
            text = self.must([tools / "llvm-nm", "--defined-only", "--format=posix", obj], "symbols-" + obj.stem)
            symbols = {line.split()[0]: line.split()[1] for line in text.splitlines() if len(line.split()) >= 2}
            self.check("actual-code-symbols-" + obj.stem, header["filetype"] == 1 and
                       all(symbols.get(n) == "T" for n in expected[name]), required=expected[name])
            disassembly = self.must([tools / "llvm-objdump", "-d", "--no-show-raw-insn", obj], "disassembly-" + obj.stem)
            instructions = re.findall(r"(?m)^\s+[0-9a-f]+:\s+[a-z]", disassembly)
            self.check("actual-arm64-disassembly-" + obj.stem, len(instructions) > 0, instruction_lines=len(instructions))
        self.report["units"] = report["units"]
        self.report["audited_parent_experiment"] = self.args.object_evidence
        self.report["audited_parent_report_sha256"] = sha(report_path)

    def finish(self):
        checks = self.report["checks"]
        good = checks and all(c["passed"] for c in checks) and len(self.report["units"]) == 3 and all(u["actual_arm64_object"] for u in self.report["units"])
        self.report["outcome"] = "pass" if good and "error" not in self.report else "fail"
        self.report["summary"] = "Actual selected E1S generator/configuration/unit commands; no full kernel/native or external ABI qualification"
        dump(self.out / "report.json", self.report)
        files = [p for p in self.out.rglob("*") if p.is_file() and p.name != "evidence.json"]
        doc = {k: self.report[k] for k in ["kind", "origin", "outcome", "recorded_at", "summary", "commands"]}
        doc.update(commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in sorted(files)],
            sha256={str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}, device_executed=False, full_kernel_qualified=False)
        dump(self.out / "evidence.json", doc)
        print(json.dumps({k: self.report.get(k) for k in ["outcome", "error", "checks", "units"]}))
        return 0 if self.report["outcome"] == "pass" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--host-cc", type=Path, default=Path("/usr/bin/cc"))
    parser.add_argument("--reuse-config-run", type=Path)
    parser.add_argument("--config-evidence", help="Registered parent experiment ID")
    parser.add_argument("--internal-exports", action="store_true")
    parser.add_argument("--audit-run", type=Path)
    parser.add_argument("--object-evidence", help="Registered passing source-unit experiment ID")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run): parser.error("Use a fresh canonical run name")
    if not args.host_cc.is_absolute() or not args.host_cc.is_file(): parser.error("Use an explicit host compiler")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    build = Build(args)
    try:
        build.inputs()
        if args.audit_run:
            if not args.object_evidence or args.reuse_config_run: raise ValueError("Audit requires object evidence and no configuration rebuild/reuse")
            build.audit_objects()
        else:
            if args.reuse_config_run:
                if not args.config_evidence: raise ValueError("Reuse requires recorded parent evidence")
                configs = build.reuse_configurations()
            else:
                hostroot = build.generator()
                configs = build.configurations(hostroot)
            build.configuration_controls(configs)
            build.units(configs)
    except Exception as error:
        build.report["error"] = str(error)
    return build.finish()


if __name__ == "__main__":
    sys.exit(main())
