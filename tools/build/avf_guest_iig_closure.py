#!/usr/bin/env python3
"""Audit the frozen public guest IIG graph without invoking a compiler or IIG.

This is a lexical source inventory and provenance check, not a C++ parser,
layout oracle, implementation compile, selected Apple ABI qualification or boot.
"""

import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time


MANIFEST = "afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd"
COMPONENT = "dce352be7c6bbe5a92937685328b45588afef08d7495c2ae3d705dc79348abee"
HISTORICAL = "7ab9382d3392e34485bd21c5a42b22ae07d1c8aecf47ec586aec0052c575487b"
HISTORICAL_EVIDENCE = "1a568caf5c1ae17c9ed44a9f342bdb88886d9b4bdb81efa5f4408096b8b7d9fe"
COMPILER = "7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82"
CONTROLS = ("source-hash", "generated-hash", "missing-recipe", "wrong-target", "missing-builtin-contract")


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def digest(path):
    """Stream inputs, including the large LLVM shared library."""
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def witness(path, expected=None):
    path = Path(path)
    actual = digest(path)
    require(expected is None or actual == expected, "Hash mismatch: " + str(path))
    return {"path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def load_pinned(path, expected, report):
    report["inputs"].append(witness(path, expected))
    return json.loads(Path(path).read_text())


def lines_matching(path, pattern):
    return [{"line": i, "text": line} for i, line in enumerate(Path(path).read_text().splitlines(), 1)
            if re.search(pattern, line)]


def macros(text):
    """Collect exact multiline macro bodies; do not interpret conditionals."""
    result = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"#define\s+(\w+)\s+\\$", line)
        if match:
            body = [line]
            for following in lines[i + 1:]:
                body.append(following)
                if not following.endswith("\\"):
                    break
            result[match[1]] = {"line": i + 1, "text": "\n".join(body)}
    return result


def records(text):
    """Inventory flat emitted RPC records, keeping fields and packing context."""
    result = []
    for match in re.finditer(r"^struct (\w+)\s*\n\{\n(.*?)^\};", text, re.M | re.S):
        name, body = match.groups()
        if "_Msg" not in name and "_Rpl" not in name:
            continue
        preceding = text[:match.start()]
        packs = re.findall(r"^#pragma pack\(([^)]*)\)", preceding, re.M)
        result.append({"name": name, "line": preceding.count("\n") + 1,
                       "lexical_pack": packs[-1] if packs else "default",
                       "fields": body.splitlines(),
                       "record_text_sha256": hashlib.sha256(match.group().encode()).hexdigest(),
                       "size_and_offsets": "unmeasured"})
    return result


def source_witness(path, source_root, source_pins):
    relative = str(Path(path).relative_to(source_root))
    require(relative in source_pins, "Public source lacks composition pin: " + relative)
    pin = source_pins[relative]
    return {**witness(path, pin["sha256"]), "canonical_git_blob_sha1": pin["oid"]}


def provider_index(source_root, recipe_rows, source_pins):
    """Follow public source includes to retain definitions supplied by headers.

    In particular IODataQueueDispatchSource implementations live in a shared
    header included by IOUserServer.cpp. Looking only at .cpp files incorrectly
    diagnoses nine missing methods. Include traversal is lexical and preserves
    conditional candidates; it does not assert that a C++ frontend accepts them.
    """
    roots = [source_root / name for name in ["iokit", "libkern", "osfmk", "bsd", "pexpert", "libsa", "EXTERNAL_HEADERS"]]
    providers, visited = {}, set()
    queue = [(Path(row["bound_source"]), row["id"], []) for row in recipe_rows if not row["generated_input"]]
    while queue:
        path, recipe_id, chain = queue.pop()
        if path in visited:
            continue
        visited.add(path)
        pinned = source_witness(path, source_root, source_pins)
        body = path.read_text()
        for match in re.finditer(r"^(\w+)::(\w+_Impl)\s*\(", body, re.M):
            key = "::".join(match.groups())
            providers.setdefault(key, []).append({"source": pinned, "line": body[:match.start()].count("\n") + 1,
                "including_recipe": recipe_id, "include_chain": chain,
                "conditional_and_type_acceptance": "unmeasured"})
        for include in re.findall(r'^\s*#\s*include\s*[<"]([^>"]+)', body, re.M):
            for candidate in [path.parent / include, *[root / include for root in roots]]:
                candidate = candidate.resolve()
                if candidate.is_relative_to(source_root) and candidate.is_file():
                    queue.append((candidate, recipe_id, [*chain, {"from": str(path), "include": include, "resolved": str(candidate)}]))
                    break
    return providers, len(visited)


def historical_results(main, historical, hashes):
    rows = []
    for command in historical["commands"]:
        stderr = command.get("stderr", "")
        if "/compile-" not in stderr:
            continue
        path = main / stderr
        errors = lines_matching(path, r"error:")
        messages = sorted(set(line["text"].split("error:", 1)[1].strip() for line in errors))
        rows.append({"name": path.name.removeprefix("compile-").removesuffix(".stderr.txt"),
                     "command": command, "stderr": witness(path, hashes[stderr]), "errors": errors,
                     "unique_error_messages": messages,
                     "context": "Historical native E1S/NDK compile; not the guest compiler or recipe",
                     "guest_result": "unmeasured"})
    require(len(rows) == 17 and sum(row["command"]["exit_code"] != 0 for row in rows) == 16,
            "Historical implementation result selection changed")
    return rows


def audit(main, report, control=None):
    headers = main / "worktrees/vm-008-20261105/artifacts/avf-kernel-headers"
    manifest = load_pinned(headers / "handoff-1/next-full-object-manifest.json", MANIFEST, report)
    component = load_pinned(headers / "iig-1/iig-component.json", COMPONENT, report)
    historical = load_pinned(main / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/report.json", HISTORICAL, report)
    historical_evidence = load_pinned(main / "state/evidence/IIGABI-013.json", HISTORICAL_EVIDENCE, report)
    require(len(manifest) == 1080, "Expected exactly 1080 genuine object recipes")
    iokit = copy.deepcopy([row for row in manifest if row["component"] == "iokit"])
    component = copy.deepcopy(component)
    if control == "source-hash":
        iokit[0]["bound_source_sha256"] = "0" * 64
    elif control == "generated-hash":
        pair = component["pairs"][sorted(component["pairs"])[0]]
        pair["outputs"][sorted(pair["outputs"])[0]] = "0" * 64
    elif control == "missing-recipe":
        iokit.pop()
    elif control == "wrong-target":
        iokit[0]["next_owned_compile_argv_template"] = [
            value.replace("arm64-apple-ios16.5", "arm64-apple-ios17.0")
            for value in iokit[0]["next_owned_compile_argv_template"]]
    elif control == "missing-builtin-contract":
        iokit[0]["next_owned_compile_argv_template"].remove("-DXNU_NO_TYPE_BUILTINS=0")
    require(len(iokit) == 104, "Expected exactly 104 iokit recipes")
    require(len({row["id"] for row in iokit}) == 104, "Duplicate iokit object recipe")
    generated = {Path(row["bound_source"]).name: row for row in iokit if row["generated_input"]}
    require(len(generated) == 17, "Expected exactly 17 generated IIG recipes")
    report["iokit_recipes"] = []
    compilers = set()
    for row in iokit:
        argv = row["next_owned_compile_argv_template"]
        require(isinstance(argv, list), "Compile template must be an argument vector")
        require("-target" in argv and argv[argv.index("-target") + 1] == "arm64-apple-ios16.5", "Wrong guest target: " + row["id"])
        require("-DXNU_NO_TYPE_BUILTINS=0" in argv, "Missing typed-builtin contract: " + row["id"])
        require(all(flag in argv for flag in ["-DKERNEL", "-DKERNEL_PRIVATE", "-DXNU_KERNEL_PRIVATE", "-DDRIVERKIT_PRIVATE=1"]),
                "Missing selected private-kernel flags: " + row["id"])
        require("@NEXT_OBJECT_DIR@" in " ".join(argv) and "@NEXT_DEPENDENCY_DIR@" in " ".join(argv), "Object output is not owned: " + row["id"])
        require(str(row["bound_source"]) in argv, "Recipe does not select bound source: " + row["id"])
        source = witness(row["bound_source"], row["bound_source_sha256"])
        config = witness(row["configuration"], row["configuration_sha256"])
        compilers.add(argv[0])
        report["iokit_recipes"].append({"id": row["id"], "source": source, "configuration": config,
            "generated_input": row["generated_input"], "argv": argv,
            "genuine_expanded_recipe_sha256": hashlib.sha256(row["genuine_expanded_recipe"].encode()).hexdigest(),
            "guest_compile": "unmeasured"})
    require(len(compilers) == 1, "Iokit recipes disagree on compiler")
    report["compiler"] = witness(next(iter(compilers)), COMPILER)
    producer = component["producer"]
    require(producer["commit"] == "ea6d147d668ca15d490da638012243fcd705f30d", "Unpinned IIG producer")
    report["generator"] = {"upstream": producer["upstream"], "commit": producer["commit"],
        "version_from_pinned_report": historical["candidate_version"], "source_ports": producer["source_ports"],
        "binary": witness(producer["path"], producer["sha256"]),
        "source": witness(main / "artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/candidate/iig.cpp", historical["patched_candidate_sha256"]),
        "libclang": witness(producer["libclang"]["path"], producer["libclang"]["sha256"]),
        "llvm": witness(producer["libclang"]["llvm_dependency"], producer["libclang"]["llvm_sha256"]),
        "executed_this_audit": False, "selected_version_oracle": False}
    resource_root = Path(producer["libclang"]["path"]).parent / "clang/19/include"
    report["generator"]["resource_headers"] = [witness(resource_root / name, expected)
        for name, expected in sorted(historical["compiler_resource_headers_sha256"].items())]
    source_root = headers / "prepare-2/source/xnu"
    selected = component["prepared"]["selected"]
    prepared = load_pinned(component["prepared"]["path"], component["prepared"]["sha256"], report)
    composition = load_pinned(selected["composition_manifest"], selected["composition_manifest_sha256"], report)
    require(composition["profiles"]["qemu"]["canonical_output_tree"] == selected["source_tree"], "Wrong public guest source tree")
    source_pins = {row["path"]: row for row in composition["profiles"]["qemu"]["files"]}
    report["public_source_pin"] = {"canonical_tree": selected["source_tree"],
        "composition_manifest_sha256": selected["composition_manifest_sha256"],
        "profile": "qemu", "source_files": len(source_pins)}
    del composition, prepared
    providers, visited = provider_index(source_root, iokit, source_pins)
    report["provider_scan"] = {"source_and_header_files": visited, "qualified_impl_names": len(providers),
                               "includes_evaluated_by_cpp": False}
    metaclass = source_root / "libkern/libkern/c++/OSMetaClass.h"
    report["dispatch_macro_bridge"] = {**source_witness(metaclass, source_root, source_pins), "lines": lines_matching(metaclass, r"_OS_ADD_METHODS|className ## _(Methods|KernelMethods)")}
    declarations = []
    for path in sorted((source_root / "iokit/IOKit").rglob("*.h")):
        text = path.read_text()
        if "OSDeclare" in text and "WithDispatch" in text:
            declarations.append((path, text))
    declarations.append((source_root / "libkern/libkern/c++/OSObject.h", (source_root / "libkern/libkern/c++/OSObject.h").read_text()))
    report["interfaces"] = []
    require(len(component["pairs"]) == 17, "Expected exactly 17 IIG pairs")
    for name, pair in sorted(component["pairs"].items()):
        klass = name.removesuffix(".iig")
        source = witness(pair["source"], pair["source_sha256"])
        outputs = [witness(path, expected) for path, expected in pair["outputs"].items()]
        header = next(Path(row["path"]) for row in outputs if row["path"].endswith(".h"))
        cpp = next(Path(row["path"]) for row in outputs if row["path"].endswith(".iig.cpp"))
        recipe = generated.get(cpp.name)
        require(recipe is not None and recipe["bound_source_sha256"] == digest(cpp), "Generated recipe source mismatch: " + klass)
        text, implementation = header.read_text(), cpp.read_text()
        all_macros = macros(text)
        own_macros = {key: value for key, value in all_macros.items() if key.startswith(klass + "_")}
        for suffix in ["Methods", "KernelMethods", "VirtualMethods"]:
            require(klass + "_" + suffix in own_macros, "Generated declaration macro missing: " + klass + "_" + suffix)
        ids = [{"method": method, "id": value, "line": text[:match.start()].count("\n") + 1}
               for match in re.finditer(r"^#define\s+" + re.escape(klass) + r"_(\w+)_ID\s+(0x[0-9a-f]+)ULL", text, re.M)
               for method, value in [match.groups()]]
        bindings = []
        for match in re.finditer(r"^" + re.escape(klass) + r"::(\w+)\s*\(", implementation, re.M):
            method = match[1]
            owners = [{"macro": key, "line": value["line"]} for key, value in own_macros.items()
                      if re.search(r"\b" + re.escape(method) + r"\s*\(", value["text"])]
            bindings.append({"method": method, "implementation_line": implementation[:match.start()].count("\n") + 1,
                             "declaration_macro_candidates": owners,
                             "missing_lexical_declaration": not bool(owners)})
        # Classes declared by the public kernel headers receive the generated
        # macros through OSDeclare*WithDispatch. Other KERNEL classes are emitted.
        native = [{**source_witness(path, source_root, source_pins), "macro_lines": lines_matching(path, r"OSDeclare\w*WithDispatch\w*\(\s*" + re.escape(klass) + r"\s*\)")}
                  for path, body in declarations if re.search(r"OSDeclare\w*WithDispatch\w*\(\s*" + re.escape(klass) + r"\s*\)", body)]
        generated_bridge = lines_matching(header, r"OSDeclare\w*WithDispatch\(\s*" + re.escape(klass) + r"\s*\)")
        includes = re.findall(r"^#include [<\"]([^>\"]+)", implementation, re.M)
        impl_refs = []
        for owner, method in sorted(set(re.findall(r"\b(\w+)::(\w+_Impl)\b", implementation))):
            key = owner + "::" + method
            impl_refs.append({"qualified_name": key, "provider_candidates": providers.get(key, []),
                              "missing_lexical_provider": key not in providers})
        all_definitions = [{"qualified_name": match[1], "line": implementation[:match.start()].count("\n") + 1}
                           for match in re.finditer(r"^((?:\w+::)+\w+)\s*\(", implementation, re.M)]
        report["interfaces"].append({"name": klass, "idl": source, "outputs": outputs, "recipe_id": recipe["id"],
            "ids": ids, "method_definitions": bindings, "macros": own_macros,
            "all_qualified_definition_candidates": all_definitions, "implementation_provider_references": impl_refs,
            "emitted_class_names": sorted(key.removesuffix("_Methods") for key in all_macros if key.endswith("_Methods")),
            "native_declaration_bridges": native, "generated_declaration_bridge": generated_bridge,
            "implementation_includes": includes, "rpc_records": records(implementation),
            "historically_unqualified_interface": klass != "OSObject",
            "guest_compile": "unmeasured", "selected_apple_abi": "unqualified"})
    report["historical_compiles"] = historical_results(main, historical, historical_evidence["sha256"])
    rpc = source_root / "iokit/IOKit/IORPC.h"
    report["public_rpc_declarations"] = {**source_witness(rpc, source_root, source_pins), "lines": lines_matching(rpc, r"struct IORPC|typedef struct|IORPCMessage|objectRefs|msgid|flags|sendSize|replySize")}
    report["historical_rpc_layout"] = {"observation": historical["selected_rpc_layout"],
        "new_field_absent_in_selected_api": historical["new_field_absent_in_selected_api"],
        "guest_layout_measured_here": False}
    report["summary"] = {"iokit_recipes": len(iokit), "generated_pairs": len(report["interfaces"]),
        "unqualified_interfaces": 16,
        "rpc_methods_with_ids": sum(len(row["ids"]) for row in report["interfaces"]),
        "implementation_method_definitions": sum(len(row["method_definitions"]) for row in report["interfaces"]),
        "missing_lexical_method_declarations": [{"interface": row["name"], **method} for row in report["interfaces"]
            for method in row["method_definitions"] if method["missing_lexical_declaration"]],
        "rpc_records": sum(len(row["rpc_records"]) for row in report["interfaces"]),
        "interfaces_without_dispatch_bridge": [row["name"] for row in report["interfaces"]
            if not row["native_declaration_bridges"] and not row["generated_declaration_bridge"]],
        "implementation_provider_references": sum(len(row["implementation_provider_references"]) for row in report["interfaces"]),
        "missing_lexical_impl_providers": [ref["qualified_name"] for row in report["interfaces"]
            for ref in row["implementation_provider_references"] if ref["missing_lexical_provider"]],
        "source_patch_justified": False, "new_compiles": 0, "new_guest_runs": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New owned report path")
    parser.add_argument("--control", choices=CONTROLS)
    args = parser.parse_args()
    require(not args.output.exists(), "Refusing to overwrite an existing report")
    started = time.monotonic()
    report = {"schema_version": 1, "task": "VM-032", "kind": "host-test", "origin": "local-host",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "argv": sys.argv,
        "inputs": [], "control": args.control, "compiler_executed": False, "qemu_executed": False,
        "limitations": ["Lexical declaration and packing inventory does not evaluate C++ conditionals, macro expansion, inheritance or types.",
            "Historical failed native compiles are retained evidence, not guest compile results.",
            "All 17 guest implementation compiles, RPC record sizes/offsets, full dispatch/marshalling and selected-version oracle remain unmeasured here.",
            "Source justified patches require a concrete guest diagnostic or semantic mismatch; no fake record or SDK is supplied."]}
    code = 0
    try:
        audit(args.main.resolve(), report, args.control)
        require(args.control is None, "Negative control unexpectedly passed")
        report["outcome"] = "pass"
    except (AuditError, OSError, KeyError, ValueError) as error:
        report["outcome"] = "rejected" if args.control else "fail"
        report["error"] = str(error)
        code = 2 if args.control else 1
    report["exit_code"] = code
    report["elapsed_seconds"] = time.monotonic() - started
    report["proc_status"] = [line for line in Path("/proc/self/status").read_text().splitlines()
                             if line.startswith(("VmHWM:", "VmRSS:", "VmPeak:"))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "output": str(args.output), "exit_code": code,
                      "summary": report.get("summary"), "error": report.get("error")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
