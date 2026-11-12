#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074: build loader-diag-xnu-bigwin-md1 on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source [--root-bytes 2475712512] [--deadline-s 150] [--pet-s 30]
  build.py --check-only --loader-source COPY_OF_... [same options]

This is NAT-065's build (docs/procedures/nat-065/build.py, itself NAT-062/059/052's chain, which built the loader that ran in NAT-068) with
four differences, three applied after NAT-065's own tree preparation and one before it:

  * make_variant.patch_tree(): the window rule (4096 MiB cap, touching /memory nodes merged), the reduced clear around a reserve, the
    layout check, the bounded watchdog pet and the final pet (see make_variant.py);
  * the payload comes from mkpayload74.py (patch_mkpayload.py applied to the pinned mkpayload.py) with the same probe init as md0 plus
    --ramdisk1-reserve (the root image's size rounded up to 16 KiB; no bytes in the payload) and --mem-size 4 GiB;
  * the command line is NAT-067's (tag NAT075-md1; `e1stouch=0 e1sbattery=0` appended, because NAT-066 died in the touch driver before PID 1);
  * the NAT-047 rule "deadline <= watchdog - 20 s" cannot hold for a cap that the pet outlives. It is replaced here by explicit rules: the
    watchdog period read from guard.c is 83 s, pet period + 20 s <= 83 s, and the cap is in (pet period, MAX_CAP_S]. The NAT-047 rule is
    switched off only for the duration of this build and restored afterwards.

The root image itself is not an input of this task: only its size is (the strategy document's 2,475,712,512 B APFS volume image). The
builder rejects a size that is not a multiple of 4 KiB (the kernel's md device counts 4 KiB blocks and would drop the tail), pads to
16 KiB, and checks that the rest of the window (after the ADT and boot_args) keeps at least MIN_FREE_MIB for the kernel.

Output: DIR/loader-diag-xnu-bigwin-md1/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json (extended with nat074_*)."""
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
NAME = "loader-diag-xnu-bigwin-md1"
NEW_TAG = "nat_attempt=NAT075-md1"          # same length as NAT-067's tag; the run this image is for is NAT-075
MAX_CAP_S = 600
WDT_S = 83
GUARD_MARGIN_S = 20          # pet period + this <= watchdog period
MIN_FREE_MIB = 1024          # kernel-managed RAM that must remain above topOfKernelData in the 4096 MiB window
WINDOW_MIB = 4096
PAGE = 0x4000
DEFAULT_ROOT_BYTES = 2475712512
DEFAULT_CAP_S = 150
DEFAULT_PET_S = 30


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b65 = _load("nat074_nat065_build", PROC / "nat-065" / "build.py")
b67 = _load("nat074_nat067_build", PROC / "nat-067" / "build.py")
mv = _load("nat074_make_variant", HERE / "make_variant.py")
pm = _load("nat074_patch_mkpayload", HERE / "patch_mkpayload.py")
fp22 = _load("nat074_fix_payload", PROC / "nat-022" / "fix_payload.py")
b62, b59, b52 = b65.b62, b65.b59, b65.b52
b47 = b52.b47
B3 = b65.B3
sha = b65.sha
STATE = {}


def reserve_for(root_bytes):
    """Root image size -> the 16 KiB-padded size of the reserve-only RAMDisk1. Rejects what the md device could not map whole."""
    if root_bytes <= 0:
        raise SystemExit("the root image size must be positive")
    if root_bytes % 4096:
        raise SystemExit(f"root image size {root_bytes} is not a multiple of 4 KiB: mdevadd counts 4 KiB blocks and would drop the tail")
    return (root_bytes + PAGE - 1) & ~(PAGE - 1)


def check_rules(wdt_s, cap_s, pet_s):
    if wdt_s != WDT_S:
        raise SystemExit(f"guard.c arms a {wdt_s} s watchdog; this build's pet rules are written for {WDT_S} s")
    if not 0 < pet_s or pet_s + GUARD_MARGIN_S > wdt_s:
        raise SystemExit(f"pet period {pet_s} s: pet + {GUARD_MARGIN_S} s must not exceed the {wdt_s} s watchdog")
    if not pet_s < cap_s <= MAX_CAP_S:
        raise SystemExit(f"cap {cap_s} s must be in ({pet_s}, {MAX_CAP_S}]")


def check_layout(payload, reserve):
    """Layout facts of the built payload that the loader relies on (the host-side twin of the loader's own layout check)."""
    virt_base, _entry, adt_off, adt_size, kernel_end, phys_base, mem_size = struct.unpack_from("<7Q", payload, 0x10)
    kernel_off = kernel_end - virt_base          # offset of kernel_end from the window base; the ADT is placed here
    after_adt = (kernel_off + adt_size + PAGE - 1) & ~(PAGE - 1)
    free_mib = (WINDOW_MIB * 1024 * 1024 - after_adt - PAGE) // (1024 * 1024)
    if mem_size != WINDOW_MIB * 1024 * 1024:
        raise SystemExit(f"payload mem_size {mem_size:#x} is not the {WINDOW_MIB} MiB window")
    if kernel_off < reserve:
        raise SystemExit("the reserve does not lie inside the payload's kernel_end")
    if kernel_off & (PAGE - 1):
        raise SystemExit("kernel_end is not 16 KiB aligned")
    if free_mib < MIN_FREE_MIB:
        raise SystemExit(f"only {free_mib} MiB stay free above boot_args (need {MIN_FREE_MIB})")
    return {"kernel_end_offset": kernel_off, "reserve_offset": kernel_off - reserve, "reserve_bytes": reserve, "adt_size": adt_size,
            "boot_args_offset": after_adt, "free_above_boot_args_mib": free_mib, "mem_size": mem_size, "phys_base": phys_base}


def build_payload74(data):
    """Like nat-065's build_payload65, with mkpayload74.py, the reserve and the 4 GiB mem_size. `data` is the NAT-020 payload (pinned)."""
    for rel, want in b65.PIN.items():
        have = sha((B3 / rel).read_bytes())
        if have != want:
            raise SystemExit("input %s is not the pinned one (%s)" % (rel, have))
    if sha(data) != b65.PIN["payload.bin"]:
        raise SystemExit("the NAT-020 payload is not the pinned one")
    reserve = STATE["reserve"]
    cmd = b65.make_cmdline(data[b65.CMDLINE_OFF:b65.CMDLINE_OFF + b65.CMDLINE_LEN])
    tools = B3 / "source/tools/e1s/xnu"
    with tempfile.TemporaryDirectory(prefix="nat074-") as w:
        work = Path(w)
        script = work / "mkpayload74.py"
        out74, mrec = pm.derive(tools / "mkpayload.py")
        script.write_bytes(out74)
        (work / "adt.py").write_bytes((tools / "adt.py").read_bytes())      # mkpayload imports it from its own directory
        probe = b65.build_probe(work)
        (work / "probe-init").write_bytes(probe)
        out = work / "payload.bin"
        b65.run([sys.executable, "-I", script, B3 / "kernel.no-storage", B3 / "e1s.adt", out, "--cmdline", cmd,
                 "--ramdisk", work / "probe-init", "--ramdisk1-reserve", str(reserve), "--mem-size", str(WINDOW_MIB << 20)])
        payload = out.read_bytes()
    if payload[:8] != b"SWEETXNU":
        raise SystemExit("mkpayload74.py did not produce a SWEETXNU payload")
    adt_off, adt_size = struct.unpack_from("<QQ", payload, 32)
    adt_fix = None
    if adt_size & 7 and not adt_off & 7:
        # Two added RAMDisk properties are 104 bytes; the ADT is then 4 bytes off a multiple of 8. NAT-022's checked fix (the padding after the
        # ADT must exist and be zero, no segment may overlap it) rounds the header field up, as it did for the NAT-020 payload.
        payload, adt_fix = fp22.fix(payload)
        adt_off, adt_size = struct.unpack_from("<QQ", payload, 32)
    if adt_size & 7 or adt_off & 7:
        raise SystemExit("adt_off/adt_size of the payload are not multiples of 8 (the loader would refuse it)")
    layout = check_layout(payload, reserve)
    b65.LAST.update(probe=probe, payload=payload, cmdline=cmd)
    STATE["payload"] = {"adt_size_fix": adt_fix, "layout": layout, "mkpayload74": mrec, "sha256": sha(payload), "bytes": len(payload)}
    return payload, {"field": "payload rebuilt by mkpayload74.py with --ramdisk and --ramdisk1-reserve", "cmdline": cmd, "adt_off": adt_off,
                     "adt_size": adt_size, "ramdisk_bytes": len(probe), "ramdisk_sha256": sha(probe), "ramdisk1_reserve": reserve,
                     "nat022_adt_size_fix": adt_fix or "not needed",
                     "base_payload_sha256": sha(data), "fixed_sha256": sha(payload)}


def main():
    argv = sys.argv
    opts = {"--root-bytes": DEFAULT_ROOT_BYTES, "--pet-s": DEFAULT_PET_S}
    rest = [argv[0]]
    i = 1
    while i < len(argv):
        if argv[i] in opts and i + 1 < len(argv):
            opts[argv[i]] = int(argv[i + 1])
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    cap = DEFAULT_CAP_S
    if "--deadline-s" in rest:
        cap = int(rest[rest.index("--deadline-s") + 1])
    else:
        rest += ["--deadline-s", str(cap)]
    sys.argv[:] = rest
    reserve = reserve_for(opts["--root-bytes"])
    pet_s = opts["--pet-s"]
    check_rules(WDT_S, cap, pet_s)       # guard.c is also read back below, from the prepared tree
    STATE.update(reserve=reserve, root_bytes=opts["--root-bytes"], cap=cap, pet_s=pet_s)

    orig_prepare = b62.prepare_tree
    saved_margin = b47.MIN_MARGIN_S

    def prepare74(src, deadline_s, final=True):
        b47.MIN_MARGIN_S = min(saved_margin, WDT_S - deadline_s)     # NAT-074 rules replace this one (see the module docstring)
        try:
            wdt = orig_prepare(src, deadline_s, final)
        finally:
            b47.MIN_MARGIN_S = saved_margin
        check_rules(wdt, deadline_s, pet_s)
        if final:
            rec = mv.patch_tree(Path(src) / "shim/e1s-xnu", {"reserve_bytes": reserve, "pet_s": pet_s})
            STATE["variant"] = rec
        return wdt

    b62.prepare_tree = prepare74
    b65.NAME = NAME
    b65.NEW_TAG = NEW_TAG                # the command line is NAT-067's (e1stouch=0 e1sbattery=0: NAT-066 died in the touch driver) with this tag
    b65.APPEND = b67.APPEND
    b65.build_payload65 = build_payload74
    try:
        b65.main()
    finally:
        b62.prepare_tree = orig_prepare
    if "--out" in argv and "--check-only" not in argv:
        out = Path(argv[argv.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            d["nat074_sources"] = {f: sha((HERE / f).read_bytes()) for f in ("build.py", "make_variant.py", "patch_mkpayload.py")}
            d["nat074_params"] = {"root_bytes": STATE["root_bytes"], "reserve_bytes": STATE["reserve"], "cap_s": STATE["cap"],
                                  "pet_s": STATE["pet_s"], "wdt_s": WDT_S}
            d["nat074_variant"] = STATE.get("variant")
            d["nat074_payload"] = STATE.get("payload")
            d["nat074_cmdline"] = {"tag": NEW_TAG, "append": b67.APPEND, "cmdline": b65.LAST.get("cmdline")}
            d["nat074_note"] = ("NAT-065's chain with the NAT-074 hunks applied after its tree preparation; the NAT-047 deadline-margin rule is "
                                "replaced by the pet/cap rules in build.py; the root image is not an input, only its size")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
