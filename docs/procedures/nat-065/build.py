#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-065: build loader-diag-xnu-md0-usb on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source [--deadline-s 60] [--service-tenths 3]
  build.py --check-only --loader-source COPY_OF_...

This is NAT-062's build (docs/procedures/nat-062/build.py: the loader, the stub, the dump of the kernel's log and the run on after C checkpoint 21,
all unchanged and re-derived from NAT-052 + NAT-059 + patch_run62.py) with two differences:
the image name `loader-diag-xnu-md0-usb`, and the XNU payload. The payload is not the NAT-020 build-003 `payload.bin` with a patched command line any more:
it is rebuilt from the same `kernel.no-storage` and `e1s.adt` by the pinned `mkpayload.py` (byte-equal to the NAT-020 payload when run without
a ramdisk, NAT-064) with

  * `--ramdisk` the NAT-065 probe init (src/probe-init.S through clang -target arm64-apple-ios16.0 and the pinned mkinit.py): one more segment and the
    `/chosen/memory-map` `RAMDisk` property, which the kernel's `rd=md0` needs and the loader rebases (adt_rebase_ramdisk);
  * `--cmdline` the NAT-062 command line (the one in the NAT-020 payload with `nat_attempt=NAT065-md0` and ` loader_return_after=8`) plus
    ` launchdsuffix=release cs_enforcement_disable=1`, the boot-args the pinned upstream test line uses for the ad-hoc-signed test /sbin/launchd.

NAT-022's adt_size fix (13956 -> 13960) is NOT applied: with the property the ADT is 14008 bytes, already a multiple of 8 (fix_payload.py would refuse).

Output: DIR/loader-diag-xnu-md0-usb/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json."""
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-md0-usb"

CMDLINE_OFF = 0x48
CMDLINE_LEN = 608
OLD_TAG = "nat_attempt=NAT020-83s"
NEW_TAG = "nat_attempt=NAT065-md0"
APPEND = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1"
CLANG_TARGET = "arm64-apple-ios16.0"

# pins of the NAT-020 build-003 inputs (artifacts/nat-020/build-003, gitignored; hashes as measured in NAT-064)
PIN = {
    "payload.bin": "071bc632f7af0a6aa9b11a679c1d5a951ee80943be11669326949d0725caf544",
    "kernel.no-storage": "7ceda59bdbedba4d32b80c319e35ec51fe766cf61daa648f80a0c42bbca3e407",
    "e1s.adt": "1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e",
    "source/tools/e1s/xnu/mkpayload.py": "50c043e4033ceea682bd20134b5283c1abec51985d49609a3bce5ea0a4013ed7",
    "source/tools/e1s/mkinit.py": "2200a8b3225ffc42cbec33747d74fc3562012fb5a2882b8ab5795d453a90ce03",
    "source/tools/e1s/sweet-init.S": "06fcf98612dd05579853e5dac96f1ab00c0a1b304ee06c400d3d6f72b3f393aa",
}
LAST = {}       # filled by the payload hook: the probe and the payload bytes, for main()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def sha(b):
    return hashlib.sha256(b).hexdigest()


b62 = _load("nat065_nat062_build", PROC / "nat-062" / "build.py")
b59, b52 = b62.b59, b62.b52
B3 = b52.b22.B3


def run(argv):
    r = subprocess.run([str(a) for a in argv], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("command failed (exit %d): %s\n%s" % (r.returncode, argv, r.stderr[-2000:]))
    return r.stdout


def make_cmdline(field):
    """The NAT-020 command line (bytes of the NUL-padded header field) -> the NAT-065 one (str)."""
    text = field.rstrip(b"\0")
    if b"\0" in text or field[len(text):] != b"\0" * (CMDLINE_LEN - len(text)):
        raise SystemExit("the command-line field is not one NUL-padded string")
    text = text.decode("ascii")
    if text.count(OLD_TAG) != 1 or "loader_return_after" in text or "launchdsuffix" in text or "cs_enforcement_disable" in text:
        raise SystemExit("the command line is not the NAT-020 one this build expects")
    if not text.startswith("rd=md0 "):
        raise SystemExit("the NAT-020 command line no longer starts with rd=md0")
    new = text.replace(OLD_TAG, NEW_TAG) + APPEND
    if len(new) >= 256:
        raise SystemExit("the kernel's BOOT_LINE_LENGTH is 256: the command line would be cut")
    return new


def build_probe(work):
    obj, init = work / "probe-init.o", work / "probe-init"
    run(["clang", "-target", CLANG_TARGET, "-c", HERE / "src" / "probe-init.S", "-o", obj])
    run([sys.executable, "-I", B3 / "source/tools/e1s/mkinit.py", obj, init])
    return init.read_bytes()


def build_payload65(data):
    """-> (payload bytes, info). `data` is the NAT-020 build-003 payload.bin, only used to take its command line and to prove that it is the pinned one."""
    for rel, want in PIN.items():
        have = sha((B3 / rel).read_bytes())
        if have != want:
            raise SystemExit("input %s is not the pinned one (%s)" % (rel, have))
    if sha(data) != PIN["payload.bin"]:
        raise SystemExit("the NAT-020 payload is not the pinned one")
    cmd = make_cmdline(data[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN])
    with tempfile.TemporaryDirectory(prefix="nat065-") as w:
        work = Path(w)
        probe = build_probe(work)
        out = work / "payload.bin"
        run([sys.executable, "-I", B3 / "source/tools/e1s/xnu/mkpayload.py", B3 / "kernel.no-storage", B3 / "e1s.adt", out,
             "--cmdline", cmd, "--ramdisk", work / "probe-init"])
        payload = out.read_bytes()
    if payload[:8] != b"SWEETXNU":
        raise SystemExit("mkpayload.py did not produce a SWEETXNU payload")
    adt_off, adt_size = struct.unpack_from("<QQ", payload, 32)
    if adt_size & 7 or adt_off & 7:
        raise SystemExit("adt_off/adt_size of the ramdisk payload are not multiples of 8 (the loader would refuse it)")
    LAST.update(probe=probe, payload=payload, cmdline=cmd)
    return payload, {"field": "payload rebuilt by mkpayload.py with --ramdisk", "cmdline": cmd, "adt_off": adt_off, "adt_size": adt_size,
                     "ramdisk_bytes": len(probe), "ramdisk_sha256": sha(probe), "base_payload_sha256": sha(data), "fixed_sha256": sha(payload),
                     "nat022_adt_size_fix": "not applied (adt_size is already a multiple of 8)"}


def _fix_payload65():
    def fix65(data):
        return build_payload65(data)
    return fix65


def main():
    b59.NAME = NAME
    b59.prepare_tree = b62.prepare_tree
    b52.b22._fix_payload = _fix_payload65
    b59.main()
    argv = sys.argv
    if "--out" in argv and "--check-only" not in argv:
        out = Path(argv[argv.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            (out / NAME / "probe-init").write_bytes(LAST["probe"])
            d = json.loads(rec.read_text())
            d["nat065_sources"] = {f: sha((HERE / f).read_bytes()) for f in ("build.py", "src/probe-init.S")}
            d["nat065_pins"] = dict(PIN)
            d["nat065_tools"] = {"clang": run(["clang", "--version"]).splitlines()[0], "clang_target": CLANG_TARGET}
            d["nat065_probe_init"] = {"path": "%s/probe-init" % NAME, "sha256": sha(LAST["probe"]), "bytes": len(LAST["probe"])}
            d["nat065_payload"] = {"sha256": sha(LAST["payload"]), "bytes": len(LAST["payload"]), "cmdline": LAST["cmdline"]}
            d["nat065_note"] = ("the loader, stub and run-on chain are NAT-062's (see nat062_sources, nat059_sources, ...); the XNU payload is rebuilt by the pinned mkpayload.py "
                                "with the probe init as ramdisk; the NAT-062 command-line patch and the NAT-022 adt_size fix are not used")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
