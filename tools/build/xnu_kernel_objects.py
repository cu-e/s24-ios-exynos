#!/usr/bin/env python3
"""Trace and build actual selected XNU objects; no phone, SDK installer or stubs."""
from __future__ import annotations
import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys

from xnu_kernel_config import Build, ROOT, KERNEL, HOST, COMPILER, dump
from xnu_compiler_hardening import registered, sha
from xnu_macho_tools import macho

COMPONENTS = ["osfmk", "bsd", "libkern", "iokit", "pexpert", "libsa", "security", "san"]


class Objects(Build):
    def __init__(self, args):
        self.args = args
        self.out = ROOT / "artifacts/xnu-kernel-objects" / args.run
        if self.out.resolve() != self.out: raise ValueError("Canonical fresh run required")
        self.out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(__file__, self.out / "builder.py")
        self.report = dict(kind="host-test", origin="local-host", outcome="inconclusive",
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), commands=[], checks=[],
            configurations={}, inventory=[], exports=[], device_executed=False,
            sdk_used=False, full_kernel_qualified=False, native_qualified=False)

    def inputs(self):
        super().inputs()
        ledger = json.loads((ROOT / "state/lab.json").read_text())
        for name in ["KCONFIG-005", "KCONFIG-006"]:
            registered(name, ledger)
            e = next(e for e in ledger["experiments"] if e["id"] == name)
            self.report["parents"][name] = dict(evidence=e["evidence"], sha256=e["evidence_sha256"])
        manifest = json.loads((ROOT / "fixtures/public/xnu-kernel-config/qualified-component.json").read_text())
        self.generator = ROOT / manifest["host_generator"]["path"]
        if sha(self.generator) != manifest["host_generator"]["sha256"]: raise ValueError("Generator changed")
        donor = ROOT / "references/hakios-e1s-tools"
        pin = "d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c"
        if self.must(["git", "-C", donor, "rev-parse", "HEAD"], "donor-pin").strip() != pin:
            raise ValueError("Donor pin changed")
        original = self.must(["git", "-C", donor, "show", pin + ":xnu-build.sh"], "donor-profile")
        if original != (donor / "xnu-build.sh").read_text(): raise ValueError("Donor profile source differs")
        for flag in ["ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64", "BUILD_WERROR=0", "BUILD_LTO=0"]:
            if flag not in original: raise ValueError("Donor build profile changed")
        self.report["donor_profile"] = dict(revision=pin, source="references/hakios-e1s-tools/xnu-build.sh",
            source_sha256=sha(donor / "xnu-build.sh"), selected_kernel="RELEASE", inherited_werror=0, inherited_lto=0,
            compatibility_wrapper_executed=False, constant_fallback=False)
        self.shim = self.out / "host-commands.mk"
        self.shim.write_text("""# Explicit standalone Linux query inputs; no SDK contents.
TR = tr
BASH = bash
ECHO = echo
PRINTF = printf
SUPPORTED_EMBEDDED_PLATFORMS = iPhoneOS AppleTVOS WatchOS tvOS BridgeOS
_v =
""")

    def configurations(self):
        hostroot = self.generator.parents[2]
        for component in COMPONENTS:
            output = self.out / "configuration" / component / "RELEASE"
            output.mkdir(parents=True)
            code, stdout, stderr = self.run([HOST / "tcsh", "-f", KERNEL / "SETUP/config/doconf", "-c",
                "-cpu", "arm64", "-soc", "e1s", "-platform", "iPhoneOS", "-d", output,
                "-s", KERNEL / component / "conf", "-m", KERNEL / "config", "-verbose", "RELEASE"],
                "configure-" + component, extra_env=dict(SRCROOT=str(KERNEL), OBJROOT=str(hostroot),
                    SOURCE=str(KERNEL / component / "conf") + "/"))
            valid = code == 0 and (output / "Makefile").is_file()
            self.check("configure-" + component, valid, exit_code=code, diagnostic=stderr[-2000:])
            self.report["configurations"][component] = dict(root=str(output.relative_to(ROOT)),
                exit_code=code, makefile_sha256=sha(output / "Makefile") if valid else None,
                meta_features_sha256=sha(output / "meta_features.h") if (output / "meta_features.h").is_file() else None)
        self.report["configuration_files"] = {str(p.relative_to(self.out)): sha(p)
            for p in (self.out / "configuration").rglob("*") if p.is_file()}

    def make_args(self, directory, component):
        # These explicit CLI assignments replace macOS discovery only. All
        # actual global/component/rule variables are read from selected source.
        return ["SRCROOT=" + str(KERNEL), "OBJROOT=" + str(self.out),
            "OBJPATH=" + str(self.out / "build"), "TARGET=" + str(self.out / "build" / component),
            "SOURCE=" + str(directory) + "/", "RELATIVE_SOURCE_PATH=" + component,
            "CURRENT_ARCH_CONFIG=ARM64", "CURRENT_ARCH_CONFIG_LC=arm64", "CURRENT_KERNEL_CONFIG=RELEASE",
            "CURRENT_KERNEL_CONFIG_LC=release", "CURRENT_MACHINE_CONFIG=E1S", "CURRENT_MACHINE_CONFIG_LC=e1s",
            "PLATFORM=iPhoneOS", "SDKROOT=" + str(self.out / "unavailable-sdk"),
            "CC=" + str(COMPILER), "CXX=" + str(COMPILER), "MakeInc_cmd=" + str(self.shim),
            "ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64", "BUILD_WERROR=0", "BUILD_LTO=0",
            "DEPLOYMENT_TARGET_FLAGS=-target arm64-apple-ios16.5 -DXNU_TARGET_OS_IOS",
            "SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0", "SHELL=/bin/bash", "LOGCOLORS=n"]

    def query(self, source_makefile, component, label, extra=""):
        query = self.out / (label + ".mk")
        query.write_text("include " + str(source_makefile) + "\n" + extra + "\n.PHONY: s24_query\ns24_query: ;\n")
        source_directory = KERNEL / component if source_makefile.is_relative_to(self.out / "configuration") else source_makefile.parent
        text = self.must(["make", "--no-print-directory", "-rR", "-f", query,
            *self.make_args(source_directory, component), "s24_query"], label, cwd=source_makefile.parent)
        return text

    def inventories(self):
        for component, config in self.report["configurations"].items():
            if config["exit_code"]: continue
            directory = ROOT / config["root"]
            makefile = directory / "Makefile"
            text = makefile.read_text()
            recipe_by_object = {}
            target = None
            for line in text.splitlines():
                match = re.match(r"^([^\s:]+\.(?:o|cpo|co)):.*", line)
                if match: target = match[1]
                if target and re.match(r"^\s*\$[({][CPS]_RULE_1A", line):
                    recipe_by_object[target] = line.strip()
            keys = ["OBJS", "LIBOBJS", "CFILES", "COBJS", "CXXFILES", "CXXOBJS", "SFILES", "SOBJS",
                    "GENASSYM_LOCATION", "CFLAGS", "CXXFLAGS", "SFLAGS", "CWARNFLAGS", "CXXWARNFLAGS", "INCFLAGS"]
            extra = "\n".join("$(info S24_VAR|" + k + "|$(" + k + "))" for k in keys)
            # The original generated compile command is expanded by real GNU
            # Make, including its original per-file additions/removals/extras.
            source_by_object = {}
            flat = text.replace("\\\n", " ")
            variables = {k: re.findall(r"(?m)^" + k + r"[ \t]*=(.*)$", flat) for k in ["CFILES", "CXXFILES", "SFILES"]}
            for language, key in [("c", "CFILES"), ("c++", "CXXFILES"), ("asm", "SFILES")]:
                if len(variables[key]) != 1: raise ValueError("Unexpected generated source list " + key)
                for value in variables[key][0].split():
                    name = value.replace("$(SOURCE_DIR)", str(KERNEL))
                    target = Path(name).name[:-1] + "o"
                    if target in source_by_object: raise ValueError("Duplicate selected object basename: " + target)
                    source_by_object[target] = (language, name)
            for target, (language, source) in source_by_object.items():
                if target not in recipe_by_object: continue
                extra += "\n$(eval @ := " + target + ")\n$(eval <F := " + Path(source).name + ")\n"
                # <F is an automatic prerequisite value only inside a real
                # recipe. Substitute that independently inventoried basename
                # explicitly while Make expands the actual rule/flag variables.
                recipe = re.sub(r"\$[({][CPS]_RULE_1B(?:_[A-Z]+)?[)}]", Path(source).name, recipe_by_object[target])
                extra += "$(info S24_CMD|" + target + "|" + recipe + ")\n"
            expanded = self.query(makefile, component, "inventory-" + component, extra)
            values, commands = {}, {}
            for line in expanded.splitlines():
                if line.startswith("S24_VAR|"):
                    _, key, value = line.split("|", 2); values[key] = value
                if line.startswith("S24_CMD|"):
                    _, key, value = line.split("|", 2); commands[key] = value
            selected = values["OBJS"].split()
            if len(selected) != len(set(selected)): raise ValueError("Duplicate linked object name")
            config["expanded_variables"] = values
            config["object_count"] = len(selected)
            for target in selected:
                language, name = source_by_object.get(target, ("unknown", ""))
                source = (directory / name).resolve() if name else None
                if source and not source.is_relative_to(ROOT): raise ValueError("Source path escapes workspace")
                row = dict(id=component + "/" + target, component=component, target=target, language=language,
                    source=str(source.relative_to(ROOT)) if source else None,
                    source_sha256=sha(source) if source and source.is_file() else None,
                    generated_input=bool(source and not source.is_relative_to(KERNEL)),
                    status="pending" if target in commands and source and source.is_file() else "missing_source_or_recipe",
                    original_expanded_recipe=commands.get(target), exit_code=None)
                self.report["inventory"].append(row)
            config["sources_not_in_link_selection"] = sorted(set(source_by_object) - set(selected))
        dump(self.out / "inventory.json", self.report["inventory"])

    def top_level_requirements(self):
        makefile = KERNEL / "makedefs/MakeInc.kernel"
        text = makefile.read_text()
        matches = re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_]*\.o):[ \t]*(\$\((?:SRCROOT|OBJPATH)\)/[^\s]+\.c)[ \t]*$", text)
        expected = {"nonlto.o", "version.o", "lastkerneldataconst.o", "lastkernelconstructor.o"}
        if {name for name, source in matches} != expected:
            raise ValueError("Actual top-level direct-object prerequisites changed")
        prerequisite = re.findall(r"(?m)^\$\(TARGET\)/\$\(KERNEL_FILE_NAME\)\.unstripped:(.*)$", text)
        if len(prerequisite) != 1 or not all(name in prerequisite[0] for name in expected - {"version.o"}):
            raise ValueError("Actual final-kernel prerequisites changed")
        if "version.o" not in text[text.index(prerequisite[0]):text.index(prerequisite[0]) + 4000]:
            raise ValueError("Final kernel no longer links version.o explicitly")
        rows = []
        for target, source in matches:
            generated = source.startswith("$(OBJPATH)")
            path = source.replace("$(SRCROOT)", str(KERNEL)).replace("$(OBJPATH)", str(self.out / "build"))
            rows.append(dict(id="kernel/" + target, target=target, source=path,
                generated_input=generated, source_sha256=sha(path) if Path(path).is_file() else None,
                status="not_attempted_top_level", original_source_expression=source))
        definitions = (KERNEL / "makedefs/MakeInc.def").read_text()
        libraries = {name: re.findall(r"(?m)^" + name + r"[ \t]*=[ \t]*(.*)$", definitions)
                     for name in ["LD_KERNEL_LIBS", "LD_KERNEL_ARCHIVES", "LDFILES_KERNEL_ONLY"]}
        self.report["top_level_requirements"] = dict(direct_objects=rows,
            source="makedefs/MakeInc.kernel", source_sha256=sha(makefile),
            link_definitions_sha256=sha(KERNEL / "makedefs/MakeInc.def"), external_link_expressions=libraries,
            optional_redwood_objects="Not supplied by this standalone selected profile; no external driver object is inferred",
            archives_and_link_metadata_qualified=False,
            scope="Component OBJS inventory excludes these four direct link objects and external archive members")
        dump(self.out / "top-level-requirements.json", self.report["top_level_requirements"])

    def exports(self):
        queue = deque((c, KERNEL / c) for c in COMPONENTS)
        seen = set()
        while queue:
            component, directory = queue.popleft()
            if directory in seen: continue
            seen.add(directory)
            makefile = directory / "Makefile"
            if not makefile.is_file():
                self.report["exports"].append(dict(source=str(directory.relative_to(KERNEL)), status="missing_makefile")); continue
            keys = ["EXPINC_SUBDIRS", "EXPINC_SUBDIRS_ARM64", "EXPORT_MI_LIST", "EXPORT_MI_DIR", "EXPORT_MD_LIST", "EXPORT_MD_DIR",
                    "EXPORT_MI_GEN_LIST", "EXPORT_MD_GEN_LIST"]
            extra = "\n".join("$(info S24_EXPORT|" + k + "|$(" + k + "))" for k in keys)
            label = "export-" + str(directory.relative_to(KERNEL)).replace("/", "-")
            try: expanded = self.query(makefile, component, label, extra)
            except RuntimeError as error:
                self.report["exports"].append(dict(source=str(makefile.relative_to(KERNEL)), status="query_failed", error=str(error))); continue
            values = {line.split("|", 2)[1]: line.split("|", 2)[2] for line in expanded.splitlines() if line.startswith("S24_EXPORT|")}
            for child in sorted(set((values["EXPINC_SUBDIRS"] + " " + values["EXPINC_SUBDIRS_ARM64"]).split())):
                path = (directory / child).resolve()
                if not path.is_relative_to(KERNEL / component): raise ValueError("Export traversal escapes component")
                queue.append((component, path))
            for kind in ["MI", "MD"]:
                dest_dir = values["EXPORT_" + kind + "_DIR"]
                for name in values["EXPORT_" + kind + "_LIST"].split():
                    source = (directory / name).resolve()
                    destination = (self.out / "EXPORT_HDRS" / component / dest_dir / name).resolve()
                    if not source.is_relative_to(KERNEL) or not destination.is_relative_to(self.out / "EXPORT_HDRS"):
                        raise ValueError("Export path escapes source/output")
                    row = dict(source=str(source.relative_to(KERNEL)), destination=str(destination.relative_to(self.out)),
                        declaration=str(makefile.relative_to(KERNEL)), declaration_sha256=sha(makefile), status="missing_source")
                    if source.is_file():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if destination.exists() and sha(destination) != sha(source): raise ValueError("Conflicting genuine exports")
                        shutil.copyfile(source, destination)
                        if sha(destination) != sha(source): raise ValueError("Export bytes changed")
                        row.update(status="copied", sha256=sha(destination))
                    self.report["exports"].append(row)
                for name in values["EXPORT_" + kind + "_GEN_LIST"].split():
                    self.report["exports"].append(dict(source=str(directory.relative_to(KERNEL)), name=name, component=component,
                        destination=str(Path("EXPORT_HDRS") / component / dest_dir / name), status="generated_input_required"))
        dump(self.out / "exports.json", self.report["exports"])

    def extra_includes(self):
        reusable = json.loads((ROOT / "fixtures/public/open-kernel-inputs/reusable-components.json").read_text())["pthread"]
        target = ROOT / "artifacts/open-kernel-inputs/typed-pthread-session1/header-tree/src/Libraries/AvailabilityVersions/include"
        if sha(target / "TargetConditionals.h") != reusable["target_header_sha256"]: raise ValueError("Target header changed")
        for n, h in reusable["mach_generated_headers"].items():
            if sha(ROOT / reusable["mach_generated_root"] / "mach" / (n + ".h")) != h: raise ValueError("MIG client header changed")
        iig = ROOT / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1"
        return [target, iig / "setup-headers", iig / "generated", iig / "mach-server-headers",
                ROOT / reusable["mach_generated_root"], *[KERNEL / c for c in COMPONENTS], KERNEL / "osfmk/libsa"]

    def compile(self):
        includes = self.extra_includes()
        self.report["additional_witnessed_include_roots"] = list(map(str, includes))
        rows = [r for r in self.report["inventory"] if r["status"] == "pending"]

        def one(row):
            objdir = self.out / "objects" / row["component"]
            objdir.mkdir(parents=True, exist_ok=True)
            output = objdir / row["target"]
            argv = shlex.split(row["original_expanded_recipe"])
            if not argv or Path(argv[0]) != COMPILER or any(t in ["&&", "||", ";", "|", ">"] for t in argv):
                row["status"] = "unsupported_recipe"; return row
            cwd = ROOT / self.report["configurations"][row["component"]]["root"]
            if (cwd / argv[-1]).resolve() != (ROOT / row["source"]).resolve():
                row.update(status="invalid_recipe_source", diagnostic="Expanded recipe does not name its independently inventoried source")
                return row
            if "-o" in argv: argv[argv.index("-o") + 1] = str(output)
            else: argv += ["-o", str(output)]
            if "-MF" in argv: argv[argv.index("-MF") + 1] = str(output.with_suffix(".d"))
            argv += [a for p in includes for a in ["-I", str(p)]]
            code, stdout, stderr = self.run(argv, "compile-" + row["id"].replace("/", "-"),
                cwd=cwd, timeout=120)
            row.update(exit_code=code, status="compile_failed", diagnostic=stderr[-6000:],
                       missing_headers=re.findall(r"fatal error: '([^']+)' file not found", stderr))
            if code == 0 and not output.is_file():
                row["status"] = "zero_exit_without_object"
            elif code == 0:
                header = macho(output)
                if header["filetype"] != 1: raise ValueError("Expected actual thin arm64 object")
                row.update(status="compiled_arm64", output=str(output.relative_to(ROOT)), output_sha256=sha(output))
            return row

        if self.args.preflight:
            controls = {"osfmk/kalloc.o", "libkern/OSData.cpo", "pexpert/pe_identify_machine.o"}
            selected = [r for r in rows if r["id"] in controls]
            if len(selected) != len(controls): raise ValueError("Missing actual preflight source units")
            for row in selected: one(row)
            good = all(r["status"] == "compiled_arm64" for r in selected)
            self.check("actual-full-recipe-preflight", good, statuses={r["id"]: r["status"] for r in selected})
            if not good:
                dump(self.out / "inventory.json", self.report["inventory"])
                return
            rows = [r for r in rows if r["status"] == "pending"]
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            futures = {pool.submit(one, row): row for row in rows}
            for index, future in enumerate(as_completed(futures), 1):
                future.result()
                if index % 20 == 0:
                    dump(self.out / "progress.json", dict(completed=index, total=len(rows), statuses=dict(Counter(r["status"] for r in self.report["inventory"]))))
                    print(json.dumps(dict(completed=index, total=len(rows))), flush=True)
        dump(self.out / "inventory.json", self.report["inventory"])

    def finish(self):
        inventory = self.report["inventory"]
        self.report["status_counts"] = dict(Counter(r["status"] for r in inventory))
        self.report["export_status_counts"] = dict(Counter(r["status"] for r in self.report["exports"]))
        component_complete = bool(inventory) and all(r["status"] == "compiled_arm64" for r in inventory)
        top = self.report.get("top_level_requirements", {}).get("direct_objects", [])
        top_complete = bool(top) and all(r["status"] == "compiled_arm64" for r in top)
        self.report.update(component_object_set_complete=component_complete, top_level_object_set_complete=top_complete)
        self.report["outcome"] = "pass" if component_complete and top_complete and "error" not in self.report else "inconclusive"
        self.report["summary"] = "Actual full selected component/object/export/recipe observations; incomplete objects remain explicit and no native/full-kernel claim"
        dump(self.out / "report.json", self.report)
        files = [p for p in self.out.rglob("*") if p.is_file() and p.name != "evidence.json"]
        doc = {k: self.report[k] for k in ["kind", "origin", "outcome", "recorded_at", "summary"]}
        # Keep all actual argv/exits in the hashed local report; publishing the
        # whole repeated kernel command database would dwarf the task ledger.
        examples, seen = [], set()
        for command in self.report["commands"]:
            label = Path(command["stdout"]).name
            if not label.startswith("compile-"):
                if len(examples) < 16: examples.append(command)
            else:
                key = (label.split("-")[1], command["exit_code"])
                if key not in seen: examples.append(command); seen.add(key)
        doc["commands"] = examples
        doc["commands_scope"] = "Representative exact commands; complete actual ordered argv/exits/diagnostics remain in hashed report.json"
        doc["actual_command_count"] = len(self.report["commands"])
        doc.update(commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in sorted(files)],
            sha256={str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}, device_executed=False, full_kernel_qualified=False)
        dump(self.out / "evidence.json", doc)
        print(json.dumps({k: self.report.get(k) for k in ["outcome", "error", "status_counts", "export_status_counts"]}))
        return 0 if self.report["outcome"] == "pass" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--compile", action="store_true")
    p.add_argument("--preflight", action="store_true", help="Require three actual complete-recipe controls before broad compilation")
    p.add_argument("--top-only", action="store_true", help="Inventory genuine top-level link objects/archive requirements without compiling")
    p.add_argument("--jobs", type=int, default=2)
    args = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run) or not 1 <= args.jobs <= 3:
        p.error("Use a fresh canonical run and1..3 host jobs")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    build = Objects(args)
    try:
        build.inputs()
        build.top_level_requirements()
        if not args.top_only:
            build.configurations()
            build.inventories()
            build.exports()
            if args.compile: build.compile()
    except Exception as error:
        build.report["error"] = str(error)
    return build.finish()


if __name__ == "__main__":
    sys.exit(main())
