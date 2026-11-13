#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-115 host build: `loader-diag-xnu-sc4-md1` = NAT-113's image with a rebuilt kernel and a 150 s kernel window.

Drives NAT-113's build.py (which drives NAT-110/106/...) without modifying it:
  1. kernel: the pinned NAT-020 `kernel.no-storage` (7ceda59b...) is replaced, in the one mkpayload command that takes it, by
     KRN-044's rebuild with `docs/procedures/nat-115/kernel-combined.patch` on osfmk/arm64/loader_return.c:
       * NAT-071's S5E9945 watchdog feed (boot-arg e1s_wdt_pet=1; fail-safe: if the feed is not proven the kernel itself cuts
         loader_return_after back to 63 s);
       * the wait-state dump of named processes before the timed return (boot-arg wait_dump=1);
     the substitution is counted (exactly one) the way NAT-085 swapped the ADT;
  2. command line (NAT-113's minus three tokens nothing reads -- `sweethw=0 ufsrw=0 e1s.hold=0`: no reader in the kernel binary,
     the loader strips e1s.hold itself and 0 is its default -- plus `e1s_wdt_pet=1 wait_dump=1`), `loader_return_after=150`,
     `rec_secs=150 rec_mb=64` (the recording covers the whole window after the first swap); checked < 256 B;
  3. loader deadline 475 s (receive cap 240 + 150 + 60 work + 25 pixel report); NAT-079's host rule `loader_return_after <= 63`
     is lifted for this build only, because the kernel enforces 63 s itself whenever the feed is not proven.
The loader (glue113.h PX/PR report) is NAT-113's unchanged.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = PROC.parent.parent

NAME = "loader-diag-xnu-sc4-md1"
NEW_TAG = "nat_attempt=NAT115-sc4"
RETURN_AFTER_NEW = 150
DEADLINE_NEW = 475
RX_CAP = 240
KERNEL_DIR = ROOT / "artifacts/nat-115/kernel-001"
KERNEL_PATCH = HERE / "kernel-combined.patch"
DROP_BASE_TOKENS = ("keepsyms=1", "sweethw=0", "ufsrw=0", "e1s.hold=0")
REC_TOKENS = ("rec_secs=150", "rec_mb=64")
NEW_TOKENS = ("e1s_wdt_pet=1", "wait_dump=1")
APPEND_NEW = (" loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 "
              + " ".join(REC_TOKENS + NEW_TOKENS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b113 = _load("nat115_nat113_build", PROC / "nat-113" / "build.py")
b79, b67, b65 = b113.b79, b113.b67, b113.b65
sha = b113.sha
STATE = {"kernel_swaps": 0}


def kernel_record():
    rec = json.loads((KERNEL_DIR / "rebuild.json").read_text())
    k = (KERNEL_DIR / "kernel.no-storage").read_bytes()
    if sha(k) != rec["no_storage_sha256"]:
        raise SystemExit("artifacts/nat-115/kernel-001/kernel.no-storage does not match its rebuild.json")
    if rec["patch_sha256"] != sha(KERNEL_PATCH.read_bytes()):
        raise SystemExit("the kernel was not built from docs/procedures/nat-115/kernel-combined.patch")
    if rec["object"] != "osfmk/loader_return.o" or rec["stub_patches"] != 29:
        raise SystemExit("unexpected kernel rebuild record")
    for s in ("e1s_wdt: fed every 10 s for %u s", "waitdump: %s[%d] t%u tid"):
        if k.count(s.encode()) != 1:
            raise SystemExit("kernel lacks %r" % s)
    return rec, k


def swap_kernel(argv, derived):
    pinned = Path(b65.B3 / "kernel.no-storage")
    out, n = [], 0
    for a in argv:
        if isinstance(a, (str, Path)) and Path(a) == pinned:
            out.append(derived)
            n += 1
        else:
            out.append(a)
    return out, n


def check_cmdline(cmdline):
    tokens = cmdline.split()
    need = [NEW_TAG, "loader_return_after=%d" % RETURN_AFTER_NEW, "cpus=1", "rd=md1", "xrd=md0"] + list(REC_TOKENS + NEW_TOKENS)
    for t in need:
        if tokens.count(t) != 1:
            raise SystemExit("cmdline must contain %s exactly once: %r" % (t, cmdline))
    for t in DROP_BASE_TOKENS + ("fb_diff=1",):
        if t in tokens:
            raise SystemExit("cmdline must not contain %s: %r" % (t, cmdline))
    if len(cmdline.encode()) >= 256:
        raise SystemExit("cmdline exceeds 255 bytes (%d): %r" % (len(cmdline.encode()), cmdline))


def main():
    rec, kbytes = kernel_record()
    derived = KERNEL_DIR / "kernel.no-storage"
    argv_saved = list(sys.argv)
    out = list(argv_saved)
    if "--return-after-s" not in out:
        out += ["--return-after-s", str(RETURN_AFTER_NEW)]
    if "--deadline-s" not in out:
        out += ["--deadline-s", str(DEADLINE_NEW)]
    sys.argv = out
    saved = (b113.NAME, b113.NEW_TAG, b113.APPEND_NEW, b113.DROP_BASE_TOKENS, b113.REC_TOKENS, b113.RETURN_AFTER_NEW,
             b113.DEADLINE_NEW, b113.check_cmdline, b79.RETURN_AFTER_MAX_S, b65.run, b113.VALUES)
    orig_run = b65.run

    def run115(argv):
        new, n = swap_kernel(argv, derived)
        if n > 1:
            raise SystemExit("more than one pinned-kernel argument in one command: " + str(argv))
        STATE["kernel_swaps"] += n
        return orig_run(new)

    b113.NAME, b113.NEW_TAG, b113.APPEND_NEW = NAME, NEW_TAG, APPEND_NEW
    b113.DROP_BASE_TOKENS, b113.REC_TOKENS = DROP_BASE_TOKENS, REC_TOKENS
    b113.RETURN_AFTER_NEW, b113.DEADLINE_NEW = RETURN_AFTER_NEW, DEADLINE_NEW
    b113.check_cmdline = check_cmdline
    # NAT-113 hands NAME/NEW_TAG to NAT-106 through VALUES (computed at import): rebuild it with ours
    b113.VALUES = tuple(NAME if f == "NAME" else NEW_TAG if f == "NEW_TAG" else v for f, v in zip(b113.FIELDS, b113.VALUES))
    b79.RETURN_AFTER_MAX_S = RETURN_AFTER_NEW
    b65.run = run115
    try:
        b113.main()
    finally:
        sys.argv = argv_saved
        (b113.NAME, b113.NEW_TAG, b113.APPEND_NEW, b113.DROP_BASE_TOKENS, b113.REC_TOKENS, b113.RETURN_AFTER_NEW,
         b113.DEADLINE_NEW, b113.check_cmdline, b79.RETURN_AFTER_MAX_S, b65.run, b113.VALUES) = saved

    if "--check-only" in argv_saved:
        return
    o = b113.argv_value(argv_saved, "--out")
    if o is None:
        return
    if STATE["kernel_swaps"] != 1:
        raise SystemExit("the rebuilt kernel replaced the pinned one %d times (need exactly 1)" % STATE["kernel_swaps"])
    path = Path(o) / "build.json"
    d = json.loads(path.read_text())
    c = d.pop("nat113_changes")
    d.pop("nat113_note", None)
    d["nat115_sources"] = {"build.py": sha((HERE / "build.py").read_bytes()), "kernel-combined.patch": rec["patch_sha256"],
                           "nat113": d.pop("nat113_sources", None)}
    d["nat115_changes"] = dict(c, image_name=NAME, cmdline_tag=NEW_TAG, rec_secs=150, return_after_s=RETURN_AFTER_NEW,
                               deadline_s=DEADLINE_NEW, dropped_base_tokens=list(DROP_BASE_TOKENS), added_tokens=list(NEW_TOKENS),
                               kernel_no_storage_sha256=sha(kbytes), kernel_unstripped_sha256=rec["kernel_unstripped_sha256"],
                               kernel_uuid=rec["uuid"], kernel_swaps=STATE["kernel_swaps"])
    d["nat115_note"] = ("NAT-113's image with the KRN-044-rebuilt kernel (NAT-071 watchdog feed + wait dump), loader_return_after=150, "
                        "deadline 475 s, rec_secs=150; nothing ran on a phone")
    path.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
