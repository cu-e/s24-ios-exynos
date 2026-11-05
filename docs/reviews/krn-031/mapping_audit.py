#!/usr/bin/env python3
"""Independently classify an immutable shifted-mapping guest failure; no VM."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = Path("/home/egor/dev/pet/s24-ios-exynos")
spec = importlib.util.spec_from_file_location("independent_reader", BASE / "mapping-reader-snapshot.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
report = dict(kind="source-review", origin="local-host", outcome="fail", recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), task="REV-017", checks=[], inputs={}, commands=[], final_acceptance=False, guest_reruns=0)


def check(name, condition, **details):
    report["checks"].append(dict(name=name, passed=bool(condition), **details))
    if not condition:
        raise AssertionError(name)


def bind(path, digest=None):
    path = Path(path)
    value = reader.sha(path)
    report["inputs"][str(path)] = value
    check("input-" + str(path), digest is None or digest == value)
    return path


try:
    parent_path = ROOT / "worktrees/krn-031-20261105/artifacts/kernel-xts/final-guest1/evidence.json"
    parent = json.loads(bind(parent_path).read_text())
    check("original-failure-preserved", parent["outcome"] == "fail" and parent["error"] == "ValueError('Actual caller/control case failed bad-mapping')")
    check("exact-prefix-only", [r["case"] for r in parent["guest_cases"]] == ["positive", "wrong-cookie", "bad-mapping"] and [r["accepted"] for r in parent["guest_cases"]] == [True, True, False])
    for name, digest in parent["sha256"].items():
        bind(ROOT / name, digest)
    native_path = ROOT / "worktrees/krn-031-20261105/artifacts/kernel-xts/frozen-native2/evidence.json"
    native = json.loads(bind(native_path).read_text())
    source_row = next(r for r in native["components"] if r["id"] == "fixture/bad-mapping")
    source = bind(ROOT / source_row["source"], source_row["source_sha256"]).read_text()
    check("actual-shifted-source", "#ifdef KXTS_BAD_MAPPING\n#define HIGH_L2_FIRST 33\n#else\n#define HIGH_L2_FIRST 32" in source)
    command = next(c for c in native["commands"] if source_row["source"] in " ".join(c["argv"]) and "-DKXTS_BAD_MAPPING" in c["argv"])
    check("actual-shifted-compilation", command["exit_code"] == 0 and command["outcome"] == "pass")
    row = parent["guest_cases"][2]
    image_path = bind(ROOT / row["image"], row["image_sha256"])
    image = reader.MachO(image_path)
    entry = image.names["_mapped_entry"]["va"]
    delta = 0xffffffefc4000000
    normal_pa = (entry - delta) % 2 ** 64
    shifted_pa = normal_pa - 2 ** 21
    segments = []
    position = 32
    for _ in range(struct.unpack_from("<I", image.data, 16)[0]):
        kind, size = struct.unpack_from("<II", image.data, position)
        if kind == 0x19:
            name, va, count = struct.unpack_from("<16sQQ", image.data, position + 8)
            segments.append((va - delta, va - delta + count))
        position += size
    check("normal-entry-in-loaded-image", any(start <= normal_pa < end for start, end in segments))
    check("shifted-entry-outside-loaded-image", not any(start <= shifted_pa < end for start, end in segments))
    console = bind(parent_path.parent / "bad-mapping.log", row["console_sha256"]).read_text()
    run = parent["commands"][2]
    exception = re.search(r"avfboot: exception slot=(0x[0-9a-f]+) during xnu\s+esr=(0x[0-9a-f]+) elr=(0x[0-9a-f]+) far=(0x[0-9a-f]+)", console)
    check("exact-actual-exception", exception and tuple(int(exception[n], 16) for n in range(1, 5)) == (4, 0x02000000, entry, 0))
    check("no-mapped-caller-pass", "KXTS MAPPING START" in console and "KXTS MAPPED" not in console and "KXTS CALLER PASS" not in console)
    check("natural-shutdown-and-cleanup", run["outcome"] == "pass" and run["exit_code"] == 0 and run["elapsed_seconds"] < 3 and not run["after"]["owned_processes"] and "avfboot: FATAL: unexpected exception" in console and "avfboot: powering off" in console)
    argv = ["git", "-C", str(ROOT / "references/scion-avf"), "show", "a6f4bc38aa244359cd365c976244a88c9d6b3304:avf/shim/avfboot.c"]
    result = subprocess.run(argv, capture_output=True, timeout=15, env=dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0"))
    digest = hashlib.sha256(result.stdout).hexdigest()
    report["commands"].append(dict(argv=argv, exit_code=result.returncode, stdout_sha256=digest, stderr_sha256=hashlib.sha256(result.stderr).hexdigest(), environment_overrides={"GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}))
    shim_report = json.loads(bind(ROOT / "worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/report.json").read_text())
    source_hash = next(r["sha256"] for r in shim_report["sources"] if r["path"] == "avf/shim/avfboot.c")
    text = result.stdout.decode()
    check("pinned-actual-shim-handler", result.returncode == 0 and digest == source_hash and "void avfboot_exception(" in text and 'die("unexpected exception");' in text and "psci_call(PSCI_SYSTEM_OFF, 0, 0, 0);" in text)
    bind(parent["qualified_inputs"]["shim"], parent["qualified_inputs"]["pins"]["shim_sha256"])
    report["diagnosis"] = dict(linked_entry=entry, normal_physical_entry=normal_pa, shifted_physical_entry=shifted_pa, outside_loaded_image=True, slot=4, ESR=0x02000000, FAR=0, natural_exit_code=0, timeout_required=False)
    report["outcome"] = "pass"
    report["summary"] = "Independent exact translation/exception/shim-source review accepts retained bad mapping as a natural-shutdown negative; original aggregate failure preserved, no guest rerun"
except Exception as error:
    report["error"] = repr(error)
report["auditor_sha256"] = reader.sha(__file__)
report["independent_reader_sha256"] = reader.sha(BASE / "mapping-reader-snapshot.py")
(BASE / "mapping-audit.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: report.get(k) for k in ["outcome", "error", "diagnosis"]}, indent=2))
raise SystemExit(0 if report["outcome"] == "pass" else 1)
