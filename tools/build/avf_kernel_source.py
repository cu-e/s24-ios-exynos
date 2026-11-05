#!/usr/bin/env python3
"""Own exact public source caches and compose the genuine AVF guest source only."""
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
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
GUARDS = {"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
          "PYTHONDONTWRITEBYTECODE": "1"}
PINS = {
    "scion": ("a6f4bc38aa244359cd365c976244a88c9d6b3304", "https://github.com/Scion-Project/hackios-xnu-kernel.git", "scion-avf"),
    "xnu": ("c54f35ca767986246321eb901baf8f5ff7923f6a", "https://github.com/apple-oss-distributions/xnu.git", "apple-xnu"),
    "hfs": ("31d5ec238dfab485e78a9a30b8b92d13e8914f03", "https://github.com/apple-oss-distributions/hfs.git", "apple-hfs"),
}
PROFILE = {"arch": "ARM64", "kernel_config": "DEVELOPMENT", "machine": "BCM2837",
           "board_macro": "ARM64_BOARD_CONFIG_BCM2837", "config": "defconfig",
           "BUILD_LTO": 0, "DO_CTFMERGE": 0, "native_outputs_reused": False}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def tree_rows(data):
    rows = []
    for entry in data.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = name.decode()
        if Path(path).is_absolute() or ".." in Path(path).parts or kind != "blob":
            raise ValueError("Unsupported canonical source member: " + path)
        rows.append({"path": path, "mode": mode, "kind": kind, "oid": oid})
    return rows


def snapshot(root):
    result = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Unexpected nonregular source member")
            size = path.stat().st_size
            blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
            with path.open("rb") as stream:
                for data in iter(lambda: stream.read(65536), b""):
                    blob.update(data)
            result.append({"path": str(path.relative_to(root)), "size": size, "sha256": sha(path),
                           "oid": blob.hexdigest(), "mode": "100755" if path.stat().st_mode & 0o111 else "100644"})
    return sorted(result, key=lambda row: row["path"])


def validate_member(root, row):
    path = root / row["path"]
    if not path.is_file() or path.stat().st_size != row["size"] or sha(path) != row["sha256"]:
        raise ValueError("Missing/changed source/config member: " + row["path"])


def validate_profile(profile, config="defconfig"):
    if config not in ["defconfig", "qemu"] or profile != PROFILE | {"config": config}:
        raise ValueError("Explicit source profile changed or native output reuse requested")


def canonical_tree_oid(rows):
    root = {}
    for row in rows:
        node = root
        components = row["path"].split("/")
        for part in components[:-1]:
            node = node.setdefault(part, {})
        node[components[-1]] = (row["mode"], row["oid"])
    def digest(node):
        entries = []
        for name, value in node.items():
            mode, oid = ("40000", digest(value)) if isinstance(value, dict) else value
            entries.append((name.encode() + (b"/" if mode == "40000" else b""),
                            mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(oid)))
        data = b"".join(payload for _, payload in sorted(entries))
        return hashlib.sha1(b"tree " + str(len(data)).encode() + b"\0" + data).hexdigest()
    return digest(root)


def validate_patch_inputs(directory, fixed):
    patches = sorted(directory.glob("*.patch"))
    if [p.name for p in patches] != fixed["ordered_numbered_patches"] or len(patches) != 34:
        raise ValueError("Missing or reordered actual numbered patch input")
    return patches


class Session:
    def __init__(self, main, out):
        self.main, self.out = main, out
        self.env = dict(os.environ) | GUARDS
        supervisor_path = main / "tools/build/qemu_host.py"
        expected = json.loads((main / "fixtures/public/avf-kernel-profile/inputs.json").read_text())["accepted_readonly_inputs"]["tools/build/qemu_host.py"]["sha256"]
        if sha(supervisor_path) != expected:
            raise ValueError("Accepted source-only process supervisor changed")
        spec = importlib.util.spec_from_file_location("avf_source_supervisor", supervisor_path)
        self.supervisor = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.supervisor)
        self.report = {"kind": "source-review", "origin": "local-host", "outcome": "fail",
                       "recorded_at": stamp(), "commands": [], "supervisor_sha256": expected,
                       "compiler_executed": False, "full_build_executed": False, "link_executed": False,
                       "guest_executed": False, "device_executed": False, "sdk_acquired": False,
                       "full_header_route_qualified": False, "kernel_image_qualified": False}
        self.report["builder_sha256"] = sha(Path(__file__))

    def monitored(self, argv, label, cwd=None, seconds=120, exchange=None):
        log_path = self.out / (label + ".log")
        record = {"argv": [str(a) for a in argv], "cwd": str(cwd or ROOT), "started_at": stamp(),
                  "environment_overrides": GUARDS | {k: self.env[k] for k in ["HAKIOS_VERSION_SUFFIX", "GIT_CEILING_DIRECTORIES"] if k in self.env},
                  "timeout_seconds": seconds}
        self.report["commands"].append(record)
        stop = threading.Event(); peak = [0]; reason = [None]
        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
        with log_path.open("xb") as log:
            proc = subprocess.Popen(record["argv"], cwd=cwd or ROOT, env=self.env, start_new_session=True,
                                    stdin=subprocess.PIPE if exchange else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE if exchange else log, stderr=log, preexec_fn=limits)
            record["owned_session"] = proc.pid
            start = time.monotonic()
            def watch():
                while not stop.is_set():
                    sample = self.supervisor.sample(proc.pid)
                    own = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
                    peak[0] = max(peak[0], own + sample["owned_tree_rss_bytes"])
                    if peak[0] > 256 * 1024**2 or time.monotonic() - start > seconds:
                        reason[0] = "rss-budget" if peak[0] > 256 * 1024**2 else "deadline"
                        self.supervisor.terminate(proc)
                        return
                    stop.wait(0.1)
            watcher = threading.Thread(target=watch, daemon=True); watcher.start()
            try:
                result = exchange(proc) if exchange else None
                if exchange:
                    proc.stdin.close()
                code = proc.wait(timeout=seconds + 3)
            finally:
                stop.set(); watcher.join(timeout=3)
                if any(p["state"] != "Z" for p in self.supervisor.sample(proc.pid)["owned_processes"]):
                    self.supervisor.terminate(proc)
                after = self.supervisor.sample(proc.pid)
                record.update(exit_code=proc.poll(), elapsed_seconds=round(time.monotonic() - start, 3),
                              peak_total_owned_rss_bytes=peak[0], stop_reason=reason[0], after=after,
                              log_sha256=sha(log_path))
                write(self.out / "progress.json", self.report)
            if any(p["state"] != "Z" for p in after["owned_processes"]):
                raise RuntimeError("Owned child survived source operation")
            if code or reason[0]:
                raise ValueError("Actual source command failed: " + label)
        return result if exchange else log_path.read_bytes()

    def git(self, repo, args, label, seconds=120, exchange=None):
        return self.monitored(["git", "-c", "core.hooksPath=/dev/null", "-c", "pack.threads=1",
                               "-c", "core.packedGitWindowSize=1m", "-c", "core.packedGitLimit=16m",
                               "-c", "core.deltaBaseCacheLimit=4m",
                               "-C", repo, *args], label, seconds=seconds, exchange=exchange)

    def mirror(self, cache, name):
        path = cache / "mirrors" / name
        if not (path / ".git").is_dir():
            path.mkdir(parents=True, exist_ok=True)
            self.git(path, ["init", "-q"], name + "-init")
            self.git(path, ["remote", "add", "origin", PINS[name][1]], name + "-remote")
            self.git(path, ["config", "remote.origin.promisor", "true"], name + "-promisor")
            self.git(path, ["config", "remote.origin.partialclonefilter", "blob:none"], name + "-filter")
        probe = subprocess.run(["git", "-C", str(path), "cat-file", "-e", PINS[name][0] + "^{commit}"],
                               env=self.env, capture_output=True, timeout=10)
        self.report["commands"].append({"argv": ["git", "-C", str(path), "cat-file", "-e", PINS[name][0] + "^{commit}"],
                                        "exit_code": probe.returncode, "environment_overrides": GUARDS,
                                        "stderr": probe.stderr.decode(errors="replace")})
        if probe.returncode:
            self.git(path, ["-c", "protocol.version=2", "fetch", "--no-tags", "--depth=1", "--filter=blob:none",
                            "origin", PINS[name][0]], name + "-metadata-fetch", seconds=180)
        return path

    def acquire(self, cache):
        cache.mkdir(parents=True, exist_ok=True)
        manifests = {}
        for name in PINS:
            pin, _, shared_name = PINS[name]
            shared = self.main / "references" / shared_name
            repo = shared if name != "hfs" else self.mirror(cache, name)
            canonical = self.git(repo, ["ls-tree", "-r", "-z", "--full-tree", pin], name + "-canonical-tree")
            (self.out / (name + "-canonical-tree.nul")).write_bytes(canonical)
            rows = tree_rows(canonical)
            selected, excluded = [], []
            required_hfs = None
            if name == "hfs":
                source_root = cache / "originals/scion/xnu/hfs"
                required_hfs = {"core/" + p.strip() for p in (source_root / "core.list").read_text().splitlines() if p.strip()}
                required_hfs |= {"hfs_encodings/" + p.strip() for p in (source_root / "encodings.list").read_text().splitlines() if p.strip()}
                if not required_hfs <= {r["path"] for r in rows}:
                    raise ValueError("Required HFS source list differs from canonical tree")
            for row in rows:
                # Build outputs are forbidden acquisitions, not omitted source inputs.
                if name == "scion" and row["path"].startswith("prebuilt/") and row["path"] not in ["prebuilt/NOTICES.md", "prebuilt/SHA256SUMS"]:
                    excluded.append(row)
                elif required_hfs is not None and row["path"] not in required_hfs and not ("/" not in row["path"] and any(s in row["path"].lower() for s in ["license", "copying", "readme"])):
                    excluded.append(row)
                else:
                    selected.append(row)
            write(self.out / (name + "-canonical-tree.json"), rows)
            objects = {r["oid"] for r in selected}
            missing = self.read_blobs(repo, cache, sorted(objects), name + "-shared-blobs")
            if missing:
                owned = self.mirror(cache, name)
                for start in range(0, len(missing), 256):
                    self.git(owned, ["fetch", "--no-tags", "--no-write-fetch-head", "origin", *missing[start:start+256]],
                             name + "-explicit-source-blobs-" + str(start // 256), seconds=180)
                missing = self.read_blobs(owned, cache, missing, name + "-owned-blobs")
                if missing:
                    raise ValueError("Explicit source blobs unavailable: " + name)
            entries = []
            original = cache / "originals" / name
            for row in manifest["files"]:
                validate_member(original, row)
            original.mkdir(parents=True, exist_ok=True)
            for row in selected:
                blob = cache / "blobs" / row["oid"]
                data_size = blob.stat().st_size
                # Object hashes were checked during streaming; fixed manifest binds content as well.
                target = original / row["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if row["mode"] == "120000":
                    raise ValueError("Review symlink source input before materializing: " + row["path"])
                if not target.exists():
                    shutil.copyfile(blob, target)
                    target.chmod(0o755 if row["mode"] == "100755" else 0o644)
                elif sha(target) != sha(blob):
                    raise ValueError("Existing owned original source changed")
                entries.append(row | {"size": data_size, "sha256": sha(blob)})
            manifests[name] = {"commit": pin, "primary_url": PINS[name][1], "canonical_tree_sha256": hashlib.sha256(canonical).hexdigest(),
                               "files": entries, "excluded_members": excluded,
                               "exclusion_reason": "20 prebuilt binaries" if name == "scion" else "HFS members outside genuine required source lists/root licenses" if name == "hfs" else "none",
                               "materialized_source_files": len(entries)}
            write(cache / "source-manifest.json", manifests)
            print(json.dumps({"source": name, "materialized": len(entries), "excluded_members": len(excluded)}), flush=True)
        return manifests

    def read_blobs(self, repo, cache, objects, label):
        store = cache / "blobs"; store.mkdir(exist_ok=True)
        def transfer(proc):
            missing = []
            for number, oid in enumerate(objects):
                target = store / oid
                if target.is_file():
                    size = target.stat().st_size
                    h = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
                    with target.open("rb") as f:
                        for block in iter(lambda: f.read(65536), b""):
                            h.update(block)
                    if h.hexdigest() != oid:
                        raise ValueError("Changed owned CAS blob")
                    continue
                proc.stdin.write((oid + "\n").encode()); proc.stdin.flush()
                header = proc.stdout.readline(512).decode().strip().split()
                if header == [oid, "missing"]:
                    missing.append(oid); continue
                if len(header) != 3 or header[0] != oid or header[1] != "blob":
                    raise ValueError("Invalid actual Git object response")
                size = int(header[2])
                if size > 32 * 1024**2:
                    raise ValueError("Review oversized source member before acquisition")
                h = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
                temporary = store / (oid + ".partial")
                with temporary.open("wb") as f:
                    left = size
                    while left:
                        block = proc.stdout.read(min(left, 65536))
                        if not block:
                            raise ValueError("Truncated Git blob stream")
                        left -= len(block); h.update(block); f.write(block)
                if proc.stdout.read(1) != b"\n" or h.hexdigest() != oid:
                    raise ValueError("Actual Git blob identity mismatch")
                temporary.rename(target)
                if number and number % 500 == 0:
                    print(json.dumps({"blob_source": label, "processed": number, "missing": len(missing)}), flush=True)
            return missing
        return self.git(repo, ["cat-file", "--batch"], label, seconds=240, exchange=transfer)

    def validate_cache(self, cache):
        manifest_path = cache / "source-manifest.json"
        fixed = json.loads((ROOT / "fixtures/public/avf-kernel-source/inputs.json").read_text())
        if sha(manifest_path) != fixed["source_manifest_sha256"]:
            raise ValueError("Immutable source acquisition manifest changed")
        manifests = json.loads(manifest_path.read_text())
        for name, manifest in manifests.items():
            if manifest["commit"] != PINS[name][0] or manifest["canonical_tree_sha256"] != fixed["sources"][name]["canonical_tree_sha256"]:
                raise ValueError("Wrong actual pinned public source")
            if canonical_tree_oid(manifest["files"] + manifest["excluded_members"]) != fixed["sources"][name]["canonical_root_tree_oid"]:
                raise ValueError("Complete canonical source tree identity differs from actual pinned Git tree")
            original = cache / "originals" / name
            expected = [{k: row[k] for k in ["path", "mode", "oid", "size", "sha256"]} for row in manifest["files"]]
            if snapshot(original) != sorted(expected, key=lambda r: r["path"]):
                raise ValueError("Owned original source was modified: " + name)
        return manifests

    def excluded_binary_check(self, cache, manifests):
        excluded = manifests["scion"]["excluded_members"]
        if len(excluded) != 20 or any((cache / "blobs" / r["oid"]).exists() for r in excluded):
            raise ValueError("Excluded prebuilt binary appeared in owned source CAS")
        mirror = cache / "mirrors/scion"
        if (mirror / ".git").is_dir():
            def probe(proc):
                result = []
                for row in excluded:
                    proc.stdin.write((row["oid"] + "\n").encode()); proc.stdin.flush()
                    line = proc.stdout.readline(512).decode().strip()
                    if line != row["oid"] + " missing":
                        raise ValueError("Excluded prebuilt object was acquired into owned Git cache")
                    result.append({"path": row["path"], "oid": row["oid"], "actual_git_result": line})
                return result
            self.report["excluded_binary_object_checks"] = self.git(mirror, ["cat-file", "--batch-check"], "actual-excluded-binary-object-check", exchange=probe)

    def canonical_output(self, tree, label):
        self.git(tree, ["init", "-q"], label + "-init")
        self.git(tree, ["-c", "core.autocrlf=false", "-c", "core.attributesFile=/dev/null", "add", "-f", "--", "."], label + "-index")
        oid = self.git(tree, ["write-tree"], label + "-write-tree").decode().strip()
        raw = self.git(tree, ["ls-tree", "-r", "-z", oid], label + "-tree-members")
        actual = tree_rows(raw)
        expected = [{k: row[k] for k in ["path", "mode", "oid"]} for row in snapshot(tree)]
        if [{k: row[k] for k in ["path", "mode", "oid"]} for row in actual] != expected:
            raise ValueError("Canonical output tree differs from actual source bytes/modes")
        return oid

    def compose(self, cache):
        manifests = self.validate_cache(cache)
        self.report["commit"] = self.git(ROOT, ["rev-parse", "HEAD"], "implementation-revision").decode().strip()
        parents_before = self.parents(cache, "before")
        self.excluded_binary_check(cache, manifests)
        original = cache / "originals"
        scion = original / "scion"
        entrypoint = (scion / "xnu-build.sh").read_text()
        if "SDKROOT=iphoneos ARCH_CONFIGS=ARM64 MACHINE_CONFIGS=${MACHINE:-BCM2837} KERNEL_CONFIGS=DEVELOPMENT" not in entrypoint or "BUILD_LTO=0 DO_CTFMERGE=0" not in entrypoint:
            raise ValueError("Explicit actual guest build entrypoint/profile changed")
        xnu = self.out / "common-xnu"
        shutil.copytree(original / "xnu", xnu)
        self.git(xnu, ["init", "-q"], "common-init")
        events = []
        def patch(path, label):
            self.git(xnu, ["apply", "--check", path], label + "-check")
            self.git(xnu, ["apply", path], label + "-apply")
            events.append({"operation": "actual-full-tree-git-apply", "source": str(path), "sha256": sha(path)})
        def install(src, relative, label):
            if not src.is_file() or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Missing/unsafe actual mapped source")
            dst = xnu / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            previous = sha(dst) if dst.exists() else None
            shutil.copy2(src, dst)
            events.append({"operation": label, "source": str(src), "destination": str(relative),
                           "source_sha256": sha(src), "previous_sha256": previous, "output_sha256": sha(dst)})
        patch(scion / "xnu/hakios.patch", "base")
        for file in sorted((scion / "xnu/files").rglob("*")):
            if file.is_file():
                install(file, file.relative_to(scion / "xnu/files"), "complete-overlay")
        for list_name, source_dir, dest_dir in [("core.list", "core", "bsd/hfs"), ("encodings.list", "hfs_encodings", "bsd/hfs_encodings")]:
            for line in (scion / "xnu/hfs" / list_name).read_text().splitlines():
                if line.strip():
                    install(original / "hfs" / source_dir / line.strip(), Path(dest_dir) / line.strip(), "genuine-hfs-list")
        patch(scion / "xnu/hfs/hfs.patch", "hfs")
        for line in (scion / "drivers/map").read_text().splitlines():
            fields = line.split()
            if fields and not fields[0].startswith("#"):
                sub, target = fields[:2]
                install(scion / "drivers" / sub / Path(target).name, Path(target), "genuine-drivers-map")
        # Use the documented source-only version override so genuine helper code
        # never runs its upward Git update-index on a containing shared checkout.
        self.env["HAKIOS_VERSION_SUFFIX"] = "-g" + PINS["scion"][0][:8] + "-source"
        self.env["GIT_CEILING_DIRECTORIES"] = str(self.out)
        external = self.monitored([sys.executable, scion / "tools/hakios-config.py", "external-files", "--root", scion], "actual-external-layer-files").decode()
        for line in external.splitlines():
            src, target = line.split("\t")
            path = Path(src)
            if not path.is_absolute():
                path = scion / path
            if not path.resolve().is_relative_to(scion.resolve()):
                raise ValueError("External layer escapes pinned staged Scion source")
            install(path, Path(target), "genuine-external-layer-map")
        fixed = json.loads((ROOT / "fixtures/public/avf-kernel-source/inputs.json").read_text())
        patches = validate_patch_inputs(scion / "xnu/patches", fixed)
        for number, path in enumerate(patches):
            patch(path, "numbered-" + str(number))
        for name in ["config/Private.exports", "config/Private.arm64.exports"]:
            if sha(xnu / name) != sha(original / "xnu" / name):
                raise ValueError("Guest preparation altered preserved public export declarations")
        common_snapshot = snapshot(xnu)
        common_tree = self.canonical_output(xnu, "common-canonical")
        profiles = {}
        for label, config in [("baseline", "defconfig"), ("qemu", "qemu")]:
            validate_profile(PROFILE | {"config": config}, config)
            location = self.out / "profiles" / label
            donor = location / "scion"
            prepared = location / "xnu"
            location.mkdir(parents=True)
            shutil.copytree(scion, donor)
            shutil.copytree(xnu, prepared, ignore=shutil.ignore_patterns(".git"))
            command = [sys.executable, donor / "tools/hakios-config.py", "--root", donor]
            self.monitored([*command, "defconfig", config], label + "-actual-defconfig", donor)
            self.monitored([*command, "check"], label + "-actual-config-check", donor)
            self.monitored([*command, "kernel", "--tree", prepared], label + "-actual-driver-generation", donor)
            self.monitored([*command, "show"], label + "-actual-profile-show", donor)
            cfg = donor / ".config"
            header = prepared / "bsd/dev/hakios.drivers.h"
            changes = []
            before = {row["path"]: row for row in common_snapshot}
            after = snapshot(prepared)
            for row in after:
                if row != before.get(row["path"]):
                    changes.append(row["path"])
            if set(changes) != {"bsd/conf/files", "iokit/conf/files", "config/MASTER.hakios", "bsd/dev/hakios.drivers.h"}:
                raise ValueError("Genuine driver generation changed unexpected source files")
            baseline_donor = snapshot(donor)
            without_cfg = [row for row in baseline_donor if row["path"] != ".config"]
            expected_donor = [{k: r[k] for k in ["path", "mode", "oid", "size", "sha256"]} for r in manifests["scion"]["files"]]
            if without_cfg != sorted(expected_donor, key=lambda r: r["path"]):
                raise ValueError("Configuration script changed donor source beyond .config")
            profile_tree = self.canonical_output(prepared, label + "-canonical")
            profiles[label] = {"source_config": config, "build_profile": PROFILE | {"config": config},
                               "source_config_sha256": sha(cfg), "donor_root": str(donor), "xnu_root": str(prepared),
                               "canonical_output_tree": profile_tree, "files": after, "donor_files": baseline_donor,
                               "driver_header_sha256": sha(header), "driver_header_text": header.read_text(),
                               "generated_driver_input_files": changes}
        result = {"recorded_at": stamp(), "source_manifest_sha256": sha(cache / "source-manifest.json"),
                  "source_cache": str(cache), "common_tree": common_tree, "common_source_files": common_snapshot,
                  "common_xnu_root": str(xnu), "ordered_composition_events": events,
                  "actual_layer_file_map": external, "profiles": profiles,
                  "shared_parents_modified": False, "sdk_equivalent": False, "full_header_route_qualified": False,
                  "compiler_executed": False, "guest_executed": False}
        result["build_profile_source_binding"] = {"entrypoint": "xnu-build.sh", "sha256": sha(scion / "xnu-build.sh"),
            "source_selected_arch": "ARM64", "source_default_machine": "BCM2837", "source_selected_kernel_config": "DEVELOPMENT",
            "future_explicit_machine_environment": "MACHINE=BCM2837", "make_or_doconf_executed": False,
            "scope": "Actual donor .config/driver-selector generation executed; board/compiler/generated setup/header recipes are VM008."}
        self.controls(cache, result)
        self.validate_cache(cache)
        if self.parents(cache, "after") != parents_before:
            raise ValueError("Shared/native parent source witness changed")
        result["parent_witness"] = parents_before
        write(self.out / "composition-manifest.json", result)
        self.report["composition_manifest_sha256"] = sha(self.out / "composition-manifest.json")
        self.report["source_file_counts"] = {k: len(v["files"]) for k, v in manifests.items()}
        self.report["common_output_file_count"] = len(common_snapshot)
        self.report["profiles"] = {k: {field: v[field] for field in ["source_config", "source_config_sha256", "canonical_output_tree", "driver_header_text"]} for k, v in profiles.items()}
        return result

    def parents(self, cache, label):
        manifests = json.loads((cache / "source-manifest.json").read_text())
        witness = {}
        for name in ["scion", "xnu"]:
            repo = self.main / "references" / PINS[name][2]
            canonical = self.git(repo, ["ls-tree", "-r", "-z", "--full-tree", PINS[name][0]], label + "-parent-" + name)
            present = {}
            for row in manifests[name]["files"]:
                path = repo / row["path"]
                if path.is_file():
                    present[row["path"]] = sha(path)
            index = repo / ".git/index"
            witness[name] = {"canonical_tree_sha256": hashlib.sha256(canonical).hexdigest(),
                             "present_source_files": present, "index_sha256": sha(index) if index.is_file() else None}
        # Revalidate bounded accepted native/component parents without using their
        # objects, generated headers or archives as guest source/build inputs.
        accepted = json.loads((self.main / "fixtures/public/avf-kernel-profile/inputs.json").read_text())["accepted_readonly_inputs"]
        witness["accepted_native_component_parents"] = {}
        for path, expected in accepted.items():
            actual = sha(self.main / path)
            if actual != expected["sha256"]:
                raise ValueError("Accepted native/component parent changed: " + path)
            witness["accepted_native_component_parents"][path] = actual
        return witness

    def controls(self, cache, composition):
        folder = self.out / "negative-inputs"; folder.mkdir()
        controls = []
        def reject(name, action):
            try:
                action()
            except (ValueError, FileNotFoundError) as error:
                controls.append({"name": name, "outcome": "pass", "rejected": str(error)})
            else:
                raise ValueError("Negative source/config input admitted: " + name)
        bad = PROFILE | {"machine": "E1S", "board_macro": "ARM64_BOARD_CONFIG_E1S"}
        reject("mixed-native-board", lambda: validate_profile(bad))
        reject("native-generated-output-reuse", lambda: validate_profile(PROFILE | {"native_outputs_reused": True}))
        reject("false-release-profile", lambda: validate_profile(PROFILE | {"kernel_config": "RELEASE"}))
        bad_manifest = json.loads((cache / "source-manifest.json").read_text())
        bad_manifest["xnu"]["commit"] = "0" * 40
        wrong_cache = folder / "wrong-source"; wrong_cache.mkdir()
        write(wrong_cache / "source-manifest.json", bad_manifest)
        fixed = json.loads((ROOT / "fixtures/public/avf-kernel-source/inputs.json").read_text())
        reject("wrong-xnu-source-pin", lambda: self.validate_cache(wrong_cache))
        incomplete = folder / "missing-patch"; incomplete.mkdir()
        scion = cache / "originals/scion"
        for name in fixed["ordered_numbered_patches"][:-1]:
            shutil.copyfile(scion / "xnu/patches" / name, incomplete / name)
        reject("actual-missing-numbered-patch", lambda: validate_patch_inputs(incomplete, fixed))
        original_manifest = json.loads((cache / "source-manifest.json").read_text())
        driver = next(r for r in original_manifest["scion"]["files"] if r["path"] == "drivers/core/hakios.platform.c")
        reject("actual-missing-mapped-driver", lambda: validate_member(folder / "missing-driver", driver))
        wrong_driver = folder / "wrong-driver" / driver["path"]; wrong_driver.parent.mkdir(parents=True)
        wrong_driver.write_bytes((scion / driver["path"]).read_bytes() + b"\n/* deliberate changed input */\n")
        reject("actual-changed-mapped-driver", lambda: validate_member(folder / "wrong-driver", driver))
        cfg_row = next(r for r in composition["profiles"]["baseline"]["donor_files"] if r["path"] == ".config")
        wrong_config = folder / "wrong-config"; wrong_config.mkdir()
        (wrong_config / ".config").write_bytes((Path(composition["profiles"]["baseline"]["donor_root"]) / ".config").read_bytes() + b"\nCONFIG_CPUS=2\n")
        reject("actual-stale-changed-config", lambda: validate_member(wrong_config, cfg_row))
        self.report["negative_controls"] = controls

    def verify(self, cache, stage):
        manifests = self.validate_cache(cache)
        self.excluded_binary_check(cache, manifests)
        self.report["commit"] = self.git(ROOT, ["rev-parse", "HEAD"], "verification-revision").decode().strip()
        fixed = json.loads((ROOT / "fixtures/public/avf-kernel-source/qualified-source.json").read_text())
        manifest = stage / "composition-manifest.json"
        if sha(manifest) != fixed["composition_manifest_sha256"]:
            raise ValueError("Immutable composition manifest changed")
        composition = json.loads(manifest.read_text())
        parents_before = self.parents(cache, "verify-before")
        if sha(cache / "source-manifest.json") != composition["source_manifest_sha256"]:
            raise ValueError("Source manifest no longer matches composed stage")
        if snapshot(Path(composition["common_xnu_root"])) != composition["common_source_files"]:
            raise ValueError("Full common source tree changed")
        for label, profile in composition["profiles"].items():
            validate_profile(profile["build_profile"], profile["source_config"])
            validate_member(Path(profile["donor_root"]), next(r for r in profile["donor_files"] if r["path"] == ".config"))
            if snapshot(Path(profile["xnu_root"])) != profile["files"] or snapshot(Path(profile["donor_root"])) != profile["donor_files"]:
                raise ValueError("Complete composed source/config profile changed: " + label)
            tree = self.git(Path(profile["xnu_root"]), ["ls-tree", "-r", "-z", profile["canonical_output_tree"]], "verify-canonical-" + label)
            if [{k: r[k] for k in ["path", "mode", "oid"]} for r in tree_rows(tree)] != [{k: r[k] for k in ["path", "mode", "oid"]} for r in profile["files"]]:
                raise ValueError("Canonical composed source IDs changed")
        self.controls(cache, composition)
        if parents_before != self.parents(cache, "verify-after") or parents_before != composition["parent_witness"]:
            raise ValueError("Shared/native source parent changed")
        self.report["verified_composition_manifest_sha256"] = sha(manifest)
        self.report["profiles"] = fixed["profiles"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["acquire", "compose", "verify"])
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    session = Session(args.main.resolve(), out)
    session.report["argv"] = [sys.executable, *sys.argv]
    try:
        if args.mode == "acquire":
            session.report["sources"] = session.acquire(args.cache.resolve())
        elif args.mode == "compose":
            session.compose(args.cache.resolve())
        else:
            if args.stage is None:
                raise ValueError("verify needs explicit immutable --stage")
            session.verify(args.cache.resolve(), args.stage.resolve())
        session.report["outcome"] = "pass"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        session.report["error"] = repr(error)
    write(out / "report.json", session.report)
    print(json.dumps({k: session.report.get(k) for k in ["outcome", "error"]}, indent=2))
    return 0 if session.report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
