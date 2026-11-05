#!/usr/bin/env python3
"""Independent read-only frozen-source and existing-capsule audit; no build/VM."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

ENV = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
CANDIDATE = "1bd64b4265cccf866bd1a3e1e1bcb3dde66d2877"
FOLLOWUP = "b87957bfd89d8ab82162e546d9c9eee3c018078f"
STRICT_FOLLOWUP = "e3b6b7da1217a716b0a2b152207b61ab73c749cf"
COUNT_FOLLOWUP = "0551ab0279adbc7e1f0bae3e698f4857865c4888"
ADMISSION_FOLLOWUP = "376a2f3f639d88ab954d9807220854779e995dc8"
MAPPING_FOLLOWUP = "9dc0c9f92c26373263ed17439eb44d0f2ea2268d"
XNU = "c54f35ca767986246321eb901baf8f5ff7923f6a"
DONOR = "c8860decc62c6d6180e609036d027a2997972420"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def apply_unified(original, patch):
    """Apply only exact unified hunks, without git/producer application code."""
    lines = original.splitlines(keepends=True)
    output, position, active = [], 0, False
    for line in patch.splitlines(keepends=True):
        if line.startswith("@@ "):
            start = int(re.match(r"@@ -(\d+)", line)[1]) - 1
            assert start >= position
            output.extend(lines[position:start])
            position, active = start, True
        elif active and line[0] in " -+":
            if line[0] != "+":
                assert lines[position] == line[1:]
                position += 1
            if line[0] != "-":
                output.append(line[1:])
    output.extend(lines[position:])
    return "".join(output)


def xnup_records(data):
    magic, total = struct.unpack_from("<II", data)
    assert magic == 0x50554e58 and total == len(data) - 8
    position, records = 8, {}
    while position + 24 <= len(data):
        name, count, flags = struct.unpack_from("<16sII", data, position)
        position += 24
        if name == b"\0" * 16:
            assert count == flags == 0 and position == len(data)
            return records
        assert flags == 0 and position + count <= len(data)
        name = name.rstrip(b"\0").decode()
        assert name not in records
        records[name] = data[position:position + count]
        position += (count + 15) // 16 * 16
    raise AssertionError("Missing XNUP terminator")


class MachO:
    """Small independent arm64 Mach-O object/image reader."""
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        magic, cpu, _, self.kind, count = struct.unpack_from("<5I", self.data)
        assert magic == 0xfeedfacf and cpu == 0x100000c
        self.sections, self.symbols, self.names = [], [], {}
        at = 32
        for _ in range(count):
            cmd, size = struct.unpack_from("<II", self.data, at)
            assert size >= 8 and at + size <= len(self.data)
            if cmd == 0x19:
                nsections = struct.unpack_from("<I", self.data, at + 64)[0]
                for index in range(nsections):
                    row = struct.unpack_from("<16s16sQQ8I", self.data, at + 72 + index * 80)
                    self.sections.append(dict(name=row[0].rstrip(b"\0").decode(), segment=row[1].rstrip(b"\0").decode(), va=row[2], size=row[3], offset=row[4], reloc=row[6], nreloc=row[7], flags=row[8]))
            if cmd == 2:
                symbol_table = struct.unpack_from("<4I", self.data, at + 8)
            at += size
        offset, count, strings, stringsize = symbol_table
        for index in range(count):
            start, kind, section, _, value = struct.unpack_from("<IBBHQ", self.data, offset + index * 16)
            end = self.data.index(0, strings + start, strings + stringsize)
            name = self.data[strings + start:end].decode()
            row = dict(name=name, kind=kind, section=section, va=value)
            self.symbols.append(row)
            if kind & 0x0e == 0x0e:
                # Local C function names can repeat across linked TUs. Required
                # public objects are checked separately, all callback addresses
                # are matched against the complete symbol list below.
                self.names.setdefault(name, row)

    def read(self, name, fmt, delta=0):
        symbol = self.names[name]
        section = self.sections[symbol["section"] - 1]
        start = symbol["va"] - section["va"] + delta
        assert 0 <= start and start + struct.calcsize(fmt) <= section["size"]
        return struct.unpack_from(fmt, self.data, section["offset"] + start)

    def relocations(self, name):
        symbol = self.names[name]
        section = self.sections[symbol["section"] - 1]
        result = {}
        for index in range(section["nreloc"]):
            address, bits = struct.unpack_from("<iI", self.data, section["reloc"] + index * 8)
            if bits >> 27 & 1:
                offset = address - (symbol["va"] - section["va"])
                result.setdefault(offset, []).append(dict(target=self.symbols[bits & 0xffffff]["name"], type=bits >> 28, instruction=struct.unpack_from("<I", self.data, section["offset"] + address)[0]))
        return result

    def definitions(self):
        return {s["name"] for s in self.symbols if s["kind"] & 0x0e == 0x0e and s["kind"] & 1}

    def imports(self):
        return {s["name"] for s in self.symbols if s["kind"] & 0x0e == 0 and s["name"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native", type=Path)
    parser.add_argument("--guest", type=Path)
    parser.add_argument("--guest-prefix", type=Path)
    parser.add_argument("--mapping-review", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    report = dict(kind="source-review", origin="local-host", outcome="fail", recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), task="REV-017", candidate=CANDIDATE, followup=FOLLOWUP, commands=[], checks=[], inputs={}, final_acceptance=False, limitations=["Read-only review of existing source/artifacts; no new compiler/guest/device execution.", "Full provider startup/XNU/native device/private Apple ABI/FIPS/full crypto and 37 missing export providers remain unqualified."])

    def check(name, condition, **details):
        report["checks"].append(dict(name=name, passed=bool(condition), **details))
        if not condition:
            raise AssertionError(name)

    def git(repo, *arguments):
        command = ["git", "-C", str(repo), *arguments]
        result = subprocess.run(command, env=ENV, capture_output=True, timeout=15)
        report["commands"].append(dict(argv=command, exit_code=result.returncode, stdout_sha256=hashlib.sha256(result.stdout).hexdigest(), stderr_sha256=hashlib.sha256(result.stderr).hexdigest(), environment_overrides={k: ENV[k] for k in ["GIT_NO_LAZY_FETCH", "GIT_OPTIONAL_LOCKS"]}))
        check("git-command-success", result.returncode == 0)
        return result.stdout

    def bind(path, digest=None):
        path = Path(path)
        value = sha(path)
        report["inputs"][str(path)] = value
        check("input-hash-" + str(path), digest is None or value == digest)
        return path

    def capsule(path):
        data = json.loads(bind(path).read_text())
        check("final-capsule-pass-" + str(path), data["outcome"] == "pass")
        for name, digest in data.get("sha256", {}).items():
            bind(root / name, digest)
        for name, digest in data.get("component_dependency_hashes", {}).items():
            bind(root / name, digest)
        return data

    try:
        files = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", CANDIDATE).decode().splitlines()
        source = {}
        for name in files:
            raw = git(root, "show", CANDIDATE + ":" + name)
            source[name] = raw.decode()
            report["inputs"][CANDIDATE + ":" + name] = hashlib.sha256(raw).hexdigest()
        delta = git(root, "diff", "--name-only", CANDIDATE, FOLLOWUP).decode().splitlines()
        check("followup-only-builder", delta == ["tools/build/xnu_kernel_xts.py"])
        diff = git(root, "diff", CANDIDATE, FOLLOWUP).decode()
        check("followup-two-spin-proof-expressions", diff.count("+   kernel=") == 1 and diff.count("+    report['guest_images']") == 1)
        strict_names = git(root, "diff", "--name-only", FOLLOWUP, STRICT_FOLLOWUP).decode().splitlines()
        check("strict-followup-scope", strict_names == ["docs/procedures/kernel-xts/finish_native.py", "tools/build/xnu_kernel_xts.py"])
        strict_diff = git(root, "diff", FOLLOWUP, STRICT_FOLLOWUP, "--", "tools/build/xnu_kernel_xts.py").decode()
        check("strict-followup-two-builder-lines", strict_diff.count("\n+") == 3 and "-Werror=incompatible-function-pointer-types-strict" in strict_diff and "parent['guest_images']['positive']['path']" in strict_diff)
        for before, after in [(STRICT_FOLLOWUP, COUNT_FOLLOWUP), (COUNT_FOLLOWUP, ADMISSION_FOLLOWUP)]:
            names = git(root, "diff", "--name-only", before, after).decode().splitlines()
            check("followup-scope-" + after, names == ["docs/procedures/kernel-xts/finish_native.py", "tools/build/xnu_kernel_xts.py"])
            for name in names:
                raw = git(root, "show", after + ":" + name)
                report["inputs"][after + ":" + name] = hashlib.sha256(raw).hexdigest()
        mapping_names = git(root, "diff", "--name-only", ADMISSION_FOLLOWUP, MAPPING_FOLLOWUP).decode().splitlines()
        check("mapping-followup-only-qualification", mapping_names == ["docs/procedures/kernel-xts/reinspect_guest.py", "tools/build/xnu_kernel_xts.py"])
        for name in mapping_names:
            raw = git(root, "show", MAPPING_FOLLOWUP + ":" + name)
            report["inputs"][MAPPING_FOLLOWUP + ":" + name] = hashlib.sha256(raw).hexdigest()
        helper = source["src/platform/crypto/xts/kernel_provider.c"]
        check("const-public-static-lifetime", helper.count("const struct ccmode_xts s24_kernel_xts_") == 2 and "static struct ccmode_xts private_encrypt,private_decrypt;" in helper)
        check("private-factory-before-ready", helper.index("s24_xts_descriptor(&private_encrypt,0)") < helper.index("s24_xts_descriptor(&private_decrypt,1)") < helper.index("!metadata(&private_encrypt)") < helper.index("__atomic_store_n(&preparation,2,__ATOMIC_RELEASE)"))
        check("acquire-ready-sticky-failure", "__atomic_load_n(&preparation,__ATOMIC_ACQUIRE)==2" in helper and "__atomic_store_n(&preparation,3,__ATOMIC_RELEASE)" in helper and "expected==2?CCERR_OK:expected==3?CCERR_INTERNAL:CCERR_CALL_SEQUENCE" in helper)
        check("both-descriptor-identity-guards", "m!=&s24_kernel_xts_encrypt" in helper and "m!=&s24_kernel_xts_decrypt" in helper)
        check("metadata-complete", all(text in helper for text in ["m->size==S24_KERNEL_XTS_KEY_BYTES", "m->tweak_size==S24_KERNEL_XTS_TWEAK_BYTES", "m->block_size==16", "m->init && m->key_sched && m->set_tweak && m->xts", "!m->custom && !m->custom1", "m->impl==CC_IMPL_AES_XTS_GENERIC"]))
        caller = git(root / "references/apple-xnu", "show", XNU + ":libkern/crypto/corecrypto_aesxts.c").decode()
        registration = git(root / "references/apple-xnu", "show", XNU + ":libkern/crypto/register_crypto.c").decode()
        xts_header = git(root / "references/apple-xnu", "show", XNU + ":libkern/libkern/crypto/aesxts.h").decode()
        mode_header = git(root / "references/apple-xnu", "show", XNU + ":EXTERNAL_HEADERS/corecrypto/ccmode_impl.h").decode()
        check("actual-registration-one-publication", "if (g_crypto_funcs)" in registration and "g_crypto_funcs = funcs;" in registration and "crypto_init = true;" in registration)
        check("actual-opaque-alignment", "cc_aligned_struct(16) ccxts_ctx;" in mode_header and "cc_aligned_struct(16) ccxts_tweak;" in mode_header)
        report["selected_header_sha256"] = {"libkern/libkern/crypto/aesxts.h": hashlib.sha256(xts_header.encode()).hexdigest(), "EXTERNAL_HEADERS/corecrypto/ccmode_impl.h": hashlib.sha256(mode_header.encode()).hexdigest()}
        donor = git(root / "references/s24-port", "show", DONOR + ":xnu/hackios/files/osfmk/minicrypto/mc_provider.c").decode()
        check("actual-caller-discarded-return", caller.count("->xts(") == 2 and caller.count("return 0;") >= 2)
        patch = source["patches/kernel-xts-provider/0002-propagate-rejected-xts-block-operations.patch"]
        check("both-block-errors-propagated", patch.count("== NULL") == 2 and patch.count("+\t\treturn CCERR_PARAMETER;") == 2)
        check("genuine-provider-startup-boundary", "STARTUP(EARLY_BOOT, STARTUP_RANK_FIRST, minicrypto_init);" in donor)
        parent = json.loads(bind(root / "docs/procedures/crypto-xts/qualified-evidence.json").read_text())
        check("accepted-parent-pass", parent["outcome"] == "pass")
        implementation = root / "worktrees/krn-031-20261105"
        for name, text in source.items():
            if name.startswith(("src/", "fixtures/", "patches/")):
                bind(implementation / name, hashlib.sha256(text.encode()).hexdigest())
        for name, digest in parent["owned_source_hashes"].items():
            if name.startswith("src/platform/crypto/xts/") or name == "fixtures/public/avf-handoff/runtime.h":
                bind(implementation / name, digest)
        if args.native:
            native = capsule(args.native)
            check("frozen-native-followup", native["commit"] in [CANDIDATE, FOLLOWUP, STRICT_FOLLOWUP, COUNT_FOLLOWUP, ADMISSION_FOLLOWUP])
            if "retained-native" in native["parents"]:
                row = native["parents"]["retained-native"]
                retained = json.loads(bind(root / row["path"], row["sha256"]).read_text())
                check("retained-failure-honestly-scoped", retained["outcome"] == "fail" and retained.get("error") == "ValueError('real-genuine-header-callback-rejection')" and [c["name"] for c in retained["checks"] if not c["passed"]] == ["real-genuine-header-callback-rejection"])
                for name, digest in retained["sha256"].items():
                    bind(root / name, digest)
                old_commands = retained["commands"]
                new_commands = native["commands"]
                check("exactly-two-targeted-compiles", len(new_commands) == 2 and all("-c" in c["argv"] and "-Werror=incompatible-function-pointer-types-strict" in c["argv"] for c in new_commands) and new_commands[0]["exit_code"] != 0 and new_commands[1]["exit_code"] == 0)
                original_positive = next(c for c in old_commands if str(implementation / "src/platform/crypto/xts/kernel_provider.c") in c["argv"] and "-c" in c["argv"])
                for label, current, previous in [("negative", new_commands[0], old_commands[-1]), ("positive", new_commands[1], original_positive)]:
                    expected = list(previous["argv"])
                    for flag in ["-o", "-MF"]:
                        expected[expected.index(flag) + 1] = current["argv"][current["argv"].index(flag) + 1]
                    expected.append("-Werror=incompatible-function-pointer-types-strict")
                    check("exact-strengthened-command-" + label, expected == current["argv"])
                for admission in native.get("admission_waits", []):
                    check("stable-memory-admission-" + admission["command"], admission["admitted"] and admission["launch_available_bytes"] >= 4 * 1024 ** 3 and all(s["available_bytes"] >= 4 * 1024 ** 3 for s in admission["samples"][-3:]) and admission["actual_wait_seconds"] <= 46)
                negative_log = args.native.parent / "wrong-signature-strict.log"
                check("strict-negative-is-type-error", "error: incompatible function pointer types" in bind(negative_log).read_text() and "-Wincompatible-function-pointer-types-strict" in negative_log.read_text() and not (args.native.parent / "rejected.o").exists())
                check("retained-warning-previously-exit0", old_commands[-1]["exit_code"] == 0 and "-Wincompatible-function-pointer-types-strict" in (root / row["path"]).parent.joinpath("reject-incompatible-actual-callback.log").read_text())
                merged = dict(retained)
                merged.update(native)
                merged["commands"] = old_commands + new_commands
                merged["parents"] = dict(retained["parents"], **native["parents"])
                native = merged
            components = {c["id"]: c for c in native["components"]}
            for row in components.values():
                bind(root / row["source"], row["source_sha256"])
                bind(root / row["output"], row["output_sha256"])
            expected_caller = apply_unified(caller, source["patches/kernel-xts-provider/0002-propagate-rejected-xts-block-operations.patch"])
            ported_donor = donor.replace("extern int printf(const char *format, ...) __printflike(1, 2);\n", "", 1)
            expected_provider = apply_unified(ported_donor, source["patches/kernel-xts-provider/0001-prepare-real-xts-modes-before-provider-publication.patch"])
            check("exact-patched-caller-from-genuine-pin", (root / components["libkern/corecrypto_aesxts.o"]["source"]).read_text() == expected_caller)
            check("exact-patched-provider-from-genuine-pin", (root / components["osfmk/mc_provider.o"]["source"]).read_text() == expected_provider)
            objects = {name: MachO(root / row["output"]) for name, row in components.items() if not name.startswith("fixture/")}
            provider = objects["osfmk/mc_provider.o"]
            helper_obj = objects["component/kernel_provider"]
            strict_helper_path = args.native.parent / "matched-helper.o"
            if strict_helper_path.exists():
                strict_helper = MachO(bind(strict_helper_path))
                old_text = helper_obj.sections[helper_obj.names["_s24_kernel_xts_prepare"]["section"] - 1]
                new_text = strict_helper.sections[strict_helper.names["_s24_kernel_xts_prepare"]["section"] - 1]
                check("strict-helper-identical-code", helper_obj.data[old_text["offset"]:old_text["offset"] + old_text["size"]] == strict_helper.data[new_text["offset"]:new_text["offset"] + new_text["size"]])
                check("strict-helper-identical-symbols", helper_obj.imports() == strict_helper.imports() and helper_obj.definitions() == strict_helper.definitions())
                check("strict-helper-identical-layout", helper_obj.read("_s24_kernel_xts_layout", "<11Q") == strict_helper.read("_s24_kernel_xts_layout", "<11Q"))
            original = json.loads(bind(root / native["original_graph"]["path"], native["original_graph"]["sha256"]).read_text())
            check("original982-identities", len(original) == len({r["id"] for r in original}) == 982)
            for row in original:
                for field in ["source", "output"]:
                    bind(root / row[field], row[field + "_sha256"])
            dependencies_path = (root / native["original_graph"]["path"]).parent / "current-dependency-files.json"
            dependencies = json.loads(bind(dependencies_path).read_text())
            check("original3156-dependencies", len(dependencies) == 3156)
            for name, digest in dependencies.items():
                bind(root / name, digest)
            baseline = MachO(root / next(r for r in original if r["id"] == "osfmk/mc_provider.o")["output"])
            native_recipes = json.loads(bind(root / native["parents"]["native-recipes"]["path"], native["parents"]["native-recipes"]["sha256"]).read_text())
            for ident in ["osfmk/mc_provider.o", "libkern/corecrypto_aesxts.o", "component/kernel_provider"]:
                row = components[ident]
                oldsource = str(root / next(r for r in original if r["id"] == row["template"])["source"])
                recipe = next(c for c in native_recipes["commands"] if "-c" in c["argv"] and oldsource in c["argv"])
                check("original-recipe-identity-" + ident, hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest() == row["original_recipe_sha256"])
                actual = next(c["argv"] for c in native["commands"] if "-c" in c["argv"] and str(root / row["source"]) in c["argv"])
                expected = list(recipe["argv"])
                expected[expected.index(oldsource)] = str(root / row["source"])
                expected[expected.index("-o") + 1] = str(root / row["output"])
                expected[expected.index("-MF") + 1] = str((root / row["output"]).with_suffix(".d"))
                expected = ["-I" + recipe["cwd"] if flag == "-I." else flag for flag in expected]
                added = actual[len(expected):]
                check("actual-native-profile-" + ident, actual[:len(expected)] == expected and added[:2] == ["-I" + str(implementation / "src/platform/crypto/xts"), "-Werror=incompatible-function-pointer-types"] and all(flag == "-Werror=incompatible-function-pointer-types-strict" for flag in added[2:]))
            bind(root / native["native_compiler"]["path"], native["native_compiler"]["sha256"])
            publication = native["publication_controls"]
            bind(publication["host_compiler"], publication["host_sha256"])
            for name, digest in parent["tools"]["host"]["runtime_hashes"].items():
                bind(name, digest)
            for name, digest in publication["source_hashes"].items():
                bind(root / name, digest)
            native_dir = (root / components["osfmk/mc_provider.o"]["output"]).parent.parent
            adapter_text = (implementation / "src/platform/crypto/xts/xts.c").read_text()
            point = "int s24_xts_descriptor(struct ccmode_xts *mode, int decrypt)\n{"
            expected_gate = adapter_text.replace(point, "extern void kxts_factory_gate(void);\n" + point + "\n    kxts_factory_gate();")
            check("real-factory-gate-only", (native_dir / "gated-factory.c").read_text() == expected_gate)
            point = "m->custom = NULL; m->custom1 = NULL; m->impl = CC_IMPL_AES_XTS_GENERIC;"
            expected_mismatch = adapter_text.replace(point, point + "\n    m->size += 16; /* owned negative metadata control, real algorithm unchanged */")
            check("real-factory-size-only", (native_dir / "mismatch-factory.c").read_text() == expected_mismatch)
            check("actual-host-publication105", "KXTS PUBLICATION PASS checks=105 failure_line=0" in (native_dir / "host-run-publication.log").read_text())
            check("actual-host-mismatch5", "KXTS PUBLICATION PASS checks=5 failure_line=0" in (native_dir / "host-run-mismatch.log").read_text())
            for command in native["commands"]:
                if "after" in command:
                    check("native-command-cleanup", not command["after"]["owned_processes"] and command["peak_total_owned_rss_bytes"] <= command["rss_budget_mib"] * 1024 ** 2 and command["rss_budget_mib"] == 256)
            oldrel = baseline.relocations("_mc_funcs")
            newrel = provider.relocations("_mc_funcs")
            oldslots = {k: v[0]["target"] for k, v in oldrel.items() if 0 <= k < 448}
            newslots = {k: v[0]["target"] for k, v in newrel.items() if 0 <= k < 448}
            check("independent-34-original-slots", len(oldslots) == 34 and all(newslots.get(k) == v for k, v in oldslots.items()))
            check("independent-exact-two-additions", len(newslots) == 36 and {k: v for k, v in newslots.items() if k not in oldslots} == {144: "_s24_kernel_xts_encrypt", 152: "_s24_kernel_xts_decrypt"})
            empty = [k for k in range(0, 448, 8) if k not in newslots]
            check("deferred-sha-and19-unsupported", len(empty) == 20 and 48 in empty and all(provider.read("_mc_funcs", "<Q", k) == (0,) for k in empty))
            targets = ["_s24_kernel_xts_prepare", "_s24_kernel_xts_encrypt_mode", "_s24_kernel_xts_decrypt_mode", "_ccsha256_di", "_register_crypto_functions"]
            init = provider.names["_minicrypto_init"]
            later = [s["va"] for s in provider.symbols if s["kind"] & 0x0e == 0x0e and s["section"] == init["section"] and s["va"] > init["va"] and s["name"].startswith("_")]
            function_size = min(later) - init["va"]
            calls = sorted((k, r) for k, rows in provider.relocations("_minicrypto_init").items() for r in rows if 0 <= k < function_size and r["target"] in targets and r["type"] == 2)
            check("independent-native-BL-order", [r["target"] for _, r in calls] == targets and all(r["instruction"] & 0xfc000000 == 0x94000000 for _, r in calls))
            for label, prefix in [("_s24_kernel_xts_encrypt", "enc"), ("_s24_kernel_xts_decrypt", "dec")]:
                check("independent-descriptor-metadata-" + prefix, helper_obj.read(label, "<3Q") == (608, 48, 16))
                reloc = helper_obj.relocations(label)
                check("independent-typed-callbacks-" + prefix, [reloc[k][0]["target"] for k in [24, 32, 40, 48]] == ["_" + prefix + "_" + suffix for suffix in ["init", "sched", "tweak", "blocks"]])
            check("independent-layout", helper_obj.read("_s24_kernel_xts_layout", "<11Q") == (80, 8, 1072, 1072, 16, 608, 48, 24, 32, 40, 48) and objects["component/xts"].read("_s24_xts_layout", "<4Q") == (608, 16, 48, 16))
            labels = {"osfmk/mc_provider.o": "provider", "libkern/corecrypto_aesxts.o": "caller", "component/kernel_provider": "publication", "component/xts": "adapter", "component/aes": "aes"}
            for name, label in labels.items():
                check("independent-imports-" + label, objects[name].imports() == set(native["component_symbols"][label]["imports"]))
                check("independent-definitions-" + label, objects[name].definitions() == set(native["component_symbols"][label]["definitions"]))
            check("exact-new-provider-imports", objects["osfmk/mc_provider.o"].imports() - baseline.imports() == set(targets[:3] + ["_s24_kernel_xts_encrypt", "_s24_kernel_xts_decrypt"]))
            provided = set().union(*(obj.definitions() for obj in objects.values()))
            imports = set().union(*(obj.imports() for obj in objects.values()))
            check("import-map-covers-actual-imports", set(native["import_provider_map"]) == imports and all(native["import_provider_map"][name] == "new-component" for name in imports & provided))
            original_report = json.loads(bind((root / native["original_graph"]["path"]).parent / "report.json").read_text())
            known_row = original_report["graph"]["symbol-providers"]
            known = json.loads(bind(root / known_row["path"], known_row["sha256"]).read_text())
            check("external-import-routes-preserved", all(native["import_provider_map"][name] == known[name] for name in imports - provided))
            added = set().union(*(objects[name].definitions() for name in ["component/kernel_provider", "component/xts", "component/aes"]))
            check("no-new-duplicate-providers", not added.intersection(known))
            check("remaining37-exports", len(native["remaining_exports"]["entries"]) == 37)
            for row in native["remaining_exports"]["entries"].values():
                bind(root / row["path"], row["sha256"])
            bind(root / native["qualified_link_runtime"]["archive"], native["qualified_link_runtime"]["sha256"])
            check("no-fullkernel-claims", not native["full_kernel_qualified"] and not native["full_crypto_qualified"] and not native["native_device_qualified"])
            report["native_verified"] = str(args.native)
        if args.guest:
            guest = capsule(args.guest)
            guest["guest_cases"] = [dict(c, artifact_directory=str(args.guest.parent)) for c in guest["guest_cases"]]
            if args.guest_prefix:
                prefix = json.loads(bind(args.guest_prefix).read_text())
                check("retained-prefix-precise-failure", prefix["outcome"] == "fail" and prefix["error"] == "ValueError('Actual caller/control case failed bad-mapping')" and [c["case"] for c in prefix["guest_cases"]] == ["positive", "wrong-cookie", "bad-mapping"] and [c["accepted"] for c in prefix["guest_cases"]] == [True, True, False])
                for name, digest in prefix["sha256"].items():
                    bind(root / name, digest)
                mapping = capsule(args.mapping_review)
                check("qualified-mapping-prefix-bound", mapping["retained_parent"]["path"] == str(args.guest_prefix.relative_to(root)) and mapping["retained_parent"]["sha256"] == sha(args.guest_prefix) and mapping["guest_reruns"] == 0 and all(c["accepted"] for c in mapping["guest_cases"]))
                independent_mapping = json.loads(bind(Path(__file__).parent / "mapping-audit.json").read_text())
                check("independent-mapping-qualified", independent_mapping["outcome"] == "pass" and independent_mapping["diagnosis"]["natural_exit_code"] == 0 and independent_mapping["diagnosis"]["outside_loaded_image"])
                check("continuation-five-only", [c["case"] for c in guest["guest_cases"]] == ["corrupt-vector", "original-caller", "factory-mismatch", "panic", "spin"] and guest["requested_cases"] == [c["case"] for c in guest["guest_cases"]] and guest["whole_timeout_seconds"] == 300 and guest["whole_elapsed_seconds"] <= 300)
                check("same-genuine-guest-inputs", guest["qualified_inputs"] == prefix["qualified_inputs"] and guest["component_parent"] == prefix["component_parent"])
                check("frozen-continuation-builder", guest["commit"] == MAPPING_FOLLOWUP and guest["builder_sha256"] == sha(args.guest.parent / "builder.py") and guest["builder_sha256"] == report["inputs"][MAPPING_FOLLOWUP + ":tools/build/xnu_kernel_xts.py"])
                cases = [dict(c, artifact_directory=str(args.guest_prefix.parent), accepted=True) for c in prefix["guest_cases"]] + guest["guest_cases"]
                combined = dict(prefix)
                combined.update(guest)
                combined.update(guest_cases=cases, commands=prefix["commands"] + guest["commands"], genuine_selected_caller_executed=prefix["genuine_selected_caller_executed"], vectors=prefix["vectors"], checks=prefix["checks"], admission_waits=prefix["admission_waits"] + guest["admission_waits"], admission_total_wait_seconds=prefix["admission_total_wait_seconds"] + guest["admission_total_wait_seconds"])
                guest = combined
            check("guest-bound-to-native", args.native is not None and root / guest["component_parent"]["path"] == args.native and sha(args.native) == guest["component_parent"]["sha256"])
            check("actual-genuine-caller", guest["genuine_selected_caller_executed"] and guest["vectors"] == 1220 and guest["checks"] == 7350)
            check("all-eight-guest-cases", {c["case"] for c in guest["guest_cases"]} == {"positive", "wrong-cookie", "bad-mapping", "corrupt-vector", "original-caller", "factory-mismatch", "panic", "spin"} and all(c["accepted"] for c in guest["guest_cases"]))
            tools = guest["qualified_inputs"]
            bind(tools["qemu"], tools["pins"]["qemu_sha256"])
            bind(tools["shim"], tools["pins"]["shim_sha256"])
            for admission in guest.get("admission_waits", []):
                check("guest-stable-memory-" + admission["command"], admission["admitted"] and admission["launch_available_bytes"] >= 4 * 1024 ** 3 and all(s["available_bytes"] >= 4 * 1024 ** 3 for s in admission["samples"][-3:]) and admission["actual_wait_seconds"] <= 46)
            check("guest-total-admission-bounded", guest.get("admission_total_wait_seconds", 0) <= 181)
            for case in guest["guest_cases"]:
                image = MachO(bind(root / case["image"], case["image_sha256"]))
                label = case["case"]
                console = bind(Path(case["artifact_directory"]) / (label + ".log"), case["console_sha256"]).read_text()
                command = guest["commands"][[c["case"] for c in guest["guest_cases"]].index(label)]
                check("guest-resource-and-cleanup-" + label, command["rss_budget_mib"] == 512 and command["peak_total_owned_rss_bytes"] <= 512 * 1024 ** 2 and not command["after"]["owned_processes"] and command["argv"][command["argv"].index("-m") + 1] == "256")
                payload = bind(command["argv"][command["argv"].index("-initrd") + 1], case["payload_sha256"])
                records = xnup_records(payload.read_bytes())
                cookie = b"wrong" if label == "wrong-cookie" else b"owned-adapter-v1"
                check("actual-payload-cookie-" + label, set(records) == {"kernel", "cmdline"} and records["cmdline"] == b"cpus=1 xts_cookie=" + cookie + b"\0")
                expected_image = bytearray(image.data)
                if label == "corrupt-vector":
                    control = guest["algorithm_control"]
                    point = control["offset"]
                    expected = bytes.fromhex(control["original_expected"])
                    check("actual-corruption-point", expected_image[point:point + len(expected)] == expected)
                    expected_image[point] ^= 1
                check("actual-payload-image-" + label, records["kernel"] == expected_image)
                check("actual-pinned-guest-command-" + label, command["argv"][0] == tools["qemu"] and command["argv"][command["argv"].index("-kernel") + 1] == tools["shim"] and command["argv"][command["argv"].index("-accel") + 1] == "tcg" and command["argv"][command["argv"].index("-cpu") + 1] == "cortex-a76")
                mapped = re.search(r"KXTS MAPPED pc=(0x[0-9a-f]+) mode=(0x[0-9a-f]+) init=(0x[0-9a-f]+) tt0=(0x[0-9a-f]+) tt1=(0x[0-9a-f]+) tcr=(0x[0-9a-f]+)", console)
                if mapped:
                    delta = 0xffffffefc4000000
                    expected = [image.names["_mapped_entry"]["va"], image.names["_s24_kernel_xts_encrypt"]["va"], image.read("_s24_kernel_xts_encrypt", "<Q", 24)[0], (image.names["_tt0"]["va"] - delta) % 2 ** 64, (image.names["_tt1"]["va"] - delta) % 2 ** 64]
                    check("actual-console-linked-addresses-" + label, [int(mapped[n], 16) for n in range(1, 6)] == expected)
                    expected_tcr = 25 | (1 << 8) | (1 << 10) | (3 << 12) | (25 << 16) | (1 << 24) | (1 << 26) | (3 << 28) | (2 << 30)
                    check("actual-console-TCR-" + label, int(mapped[6], 16) == expected_tcr)
                passed = "KXTS CALLER PASS" in console
                if label == "positive":
                    check("positive-console", mapped and passed and "line=0x0" in console and command["exit_code"] == 0 and "XTS SYNTHETIC PSCI_SYSTEM_OFF" in console)
                elif label in ["corrupt-vector", "original-caller"]:
                    line = 44 if label == "corrupt-vector" else 53
                    check("specific-negative-line-" + label, mapped and not passed and "KXTS CALLER FAIL" in console and "line=" + hex(line) in console and command["exit_code"] == 0)
                elif label == "bad-mapping":
                    fault = re.search(r"avfboot: exception slot=(0x[0-9a-f]+) during xnu\s+esr=(0x[0-9a-f]+) elr=(0x[0-9a-f]+) far=(0x[0-9a-f]+)", console)
                    check("precise-natural-shim-exception", not mapped and not passed and fault and tuple(int(fault[n], 16) for n in range(1, 5)) == (4, 0x02000000, image.names["_mapped_entry"]["va"], 0) and command["exit_code"] == 0 and command["outcome"] == "pass" and "avfboot: FATAL: unexpected exception" in console and "avfboot: powering off" in console)
                elif label == "spin":
                    check("bounded-timeout-" + label, not mapped and not passed and command["outcome"] == "timeout" and command["timeout_seconds"] == 3)
                elif label == "wrong-cookie":
                    check("cookie-admission", not mapped and not passed and "XTS SYNTHETIC REJECT command-cookie" in console and command["exit_code"] == 0)
                elif label == "factory-mismatch":
                    check("factory-rejection-zero-vectors", mapped and not passed and "KXTS FACTORY PASS vectors=0x0 checks=0xb line=0x0" in console and "KXTS FACTORY MISMATCH REJECTED" in console and command["exit_code"] == 0)
                elif label == "panic":
                    check("actual-panic", mapped and not passed and "KXTS SYNTHETIC PANIC" in console and command["exit_code"] == 0)
                if case["case"] == "spin":
                    continue
                modes = [image.names[n]["va"] for n in ["_s24_kernel_xts_encrypt", "_s24_kernel_xts_decrypt"]]
                if case["case"] != "factory-mismatch":
                    check("linked-table-" + case["case"], image.read("_test_table", "<2Q", 144) == tuple(modes))
                for label in ["_s24_kernel_xts_encrypt", "_s24_kernel_xts_decrypt"]:
                    check("linked-metadata-" + case["case"] + label, image.read(label, "<3Q") == (608, 48, 16))
                    callbacks = image.read(label, "<4Q", 24)
                    check("linked-callback-symbols-" + case["case"] + label, all(v in {s["va"] for s in image.symbols if s["kind"] & 0x0e == 0x0e} and 0xfffffff007000000 <= v < 0xfffffff008000000 for v in callbacks))
            report["guest_verified"] = str(args.guest)
        report["outcome"] = "pass"
        report["final_acceptance"] = bool(args.native and args.guest)
        report["summary"] = "Independent frozen source/native/guest artifact audit passed" if report["final_acceptance"] else "Independent source/native artifact audit passed; final qualified guest capsule required" if args.native else "Independent frozen source audit passed; final qualified native/guest capsules still required"
    except Exception as error:
        report["error"] = repr(error)
    report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report["auditor_sha256"] = sha(__file__)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report.get(k) for k in ["outcome", "error", "summary", "final_acceptance"]}, indent=2))
    return 0 if report["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
