#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-085: build loader-diag-xnu-ep-md1 on the host: NAT-083's image (the delivered APFS as the kernel's root, rd=md1) with two changes. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-020_build-003_source --ramdisk SMALL_ROOT.apfs
           [--root-bytes 2475720704] [--deadline-s 360] [--pet-s 30] [--rx-cap-s 240] [--return-after-s 60] [--rx-direct 1] [--report-s 10]

The two changes against NAT-083 (applied from outside, so docs/procedures/nat-083/build.py and the NAT-079 chain below it stay as they were reviewed and tested):

  * the device tree in the payload is the pinned e1s.adt plus ONE /chosen property, `ephemeral-storage` = u32 1 (docs/procedures/nat-085/make_adt85.py): the XNU in the payload
    publishes it as sysctl hw.ephemeral_storage, which Apple's os_variant_uses_ephemeral_storage() reads, and keybagd then skips its initialisation (see make_adt85.py);
  * the small root (md0) is NAT-085's: the same three programs, rc and files as NAT-083's, plus one launchd job (com.nat085.ps.plist). That is the --ramdisk file; it must be
    an APFS container as NAT-083's build requires.

The image name (`loader-diag-xnu-ep-md1`) and the command-line tag (`nat_attempt=NAT085-ep1`) are new and have the lengths of NAT-083's. Everything else (the receive phase, the
4096 MiB window, the md1 reserve, the pet, the time rules, `rd=md1`, `loader_return_after=60`) is NAT-083's.

The ADT swap is a counted replacement inside NAT-074's mkpayload call: exactly one argument of exactly one subprocess call must be the pinned ADT path, and it is replaced by the
derived file; the pins of the NAT-065 chain (which check the original) run before. Output: DIR/loader-diag-xnu-ep-md1/{Image,Image.payload,loader.elf,probe-init,source/} and
DIR/build.json (extended with nat083_* by NAT-083's build and nat085_* here)."""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-ep-md1"
NEW_TAG = "nat_attempt=NAT085-ep1"          # same length as NAT-083's tag


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b83 = _load("nat085_nat083_build", PROC / "nat-083" / "build.py")
m85 = _load("nat085_make_adt", HERE / "make_adt85.py")
b79 = b83.b79
b65 = b83.b65
sha = b83.sha
STATE = {"swaps": 0}


def swap_adt(argv, derived):
    """-> argv with the pinned ADT path replaced by `derived`; (argv, number of replacements)."""
    pinned = Path(b65.B3 / "e1s.adt")
    out, n = [], 0
    for a in argv:
        if isinstance(a, Path) and Path(a) == pinned:
            out.append(derived)
            n += 1
        else:
            out.append(a)
    return out, n


def main():
    argv_saved = list(sys.argv)
    pinned_bytes = (b65.B3 / "e1s.adt").read_bytes()
    derived_bytes, adt_rec = m85.derive(pinned_bytes)
    orig_run = b65.run
    saved = (b83.NAME, b83.NEW_TAG, b65.run)
    with tempfile.TemporaryDirectory(prefix="nat085-adt-") as w:
        derived = Path(w) / "e1s-eph.adt"
        derived.write_bytes(derived_bytes)

        def run85(argv):
            new, n = swap_adt(argv, derived)
            if n > 1:
                raise SystemExit("more than one pinned-ADT argument in one command: " + str(argv))
            STATE["swaps"] += n
            return orig_run(new)

        b83.NAME, b83.NEW_TAG = NAME, NEW_TAG
        b65.run = run85
        try:
            b83.main()
        finally:
            b83.NAME, b83.NEW_TAG, b65.run = saved
    if "--check-only" in argv_saved:
        return
    if STATE["swaps"] != 1:
        raise SystemExit("the ADT swap happened %d times, expected exactly 1: the payload was NOT built with the derived ADT" % STATE["swaps"])
    if "--out" in argv_saved:
        out = Path(argv_saved[argv_saved.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            d["nat085_sources"] = {"build.py": sha((HERE / "build.py").read_bytes()), "make_adt85.py": sha((HERE / "make_adt85.py").read_bytes())}
            d["nat085_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "adt": adt_rec, "adt_swaps": STATE["swaps"]}
            d["nat085_note"] = ("NAT-083's build with the pinned ADT replaced by the same ADT plus /chosen ephemeral-storage = 1, and md0 = NAT-085's small root (one launchd job); "
                                "nothing here ran on a phone")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
