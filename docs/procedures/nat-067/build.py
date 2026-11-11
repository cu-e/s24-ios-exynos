#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-067: build loader-diag-xnu-ne1-usb on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source [--deadline-s 60] [--service-tenths 3]
  build.py --check-only --loader-source COPY_OF_...

This is NAT-065's build (docs/procedures/nat-065/build.py, itself NAT-062's: the loader, the stub, the dump of the kernel's log, the run on after C
checkpoint 21, the probe init as ramdisk, the rebuilt XNU payload) loaded as a module and called with three values replaced:

  * the image name `loader-diag-xnu-ne1-usb` (ne1 = md0 root, no e1s touch/battery drivers; it is hashed into the loader's boot id and printed in the banner;
    it has the same length as NAT-065's name on purpose, so that the loader differs from the one that ran in NAT-066 only in the boot-id/name words);
  * the command-line tag `nat_attempt=NAT067-md0` (instead of NAT065-md0);
  * the appended boot-args ` loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0`: the NAT-065 ones plus two that
    switch off the e1s drivers that touch SoC registers from inside bsd_init. NAT-066 (native) died in `_e1s_touch_init` on a physical-address GPIO read;
    `e1stouch=0` makes it return before touching anything, and `e1sbattery=0` does the same for the battery driver, which maps the same GPIO block and
    bit-bangs two pins from a kernel thread (the e1s patches parse both with PE_parse_boot_argn; test_nat067.py checks that on the patch sources).

Nothing else differs: the ramdisk, the kernel, the ADT, the loader code and the NAT-022 adt_size decision (not applied) are NAT-065's.

Output: DIR/loader-diag-xnu-ne1-usb/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-ne1-usb"
NEW_TAG = "nat_attempt=NAT067-md0"
APPEND = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b65 = _load("nat067_nat065_build", PROC / "nat-065" / "build.py")


def sha(b):
    return b65.sha(b)


def configure():
    """Replace the three NAT-065 values the build reads from its module globals (the functions look them up at call time)."""
    b65.NAME = NAME
    b65.NEW_TAG = NEW_TAG
    b65.APPEND = APPEND


def main():
    configure()
    b65.main()
    argv = sys.argv
    if "--out" in argv and "--check-only" not in argv:
        out = Path(argv[argv.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            d["nat067_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
            d["nat067_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "cmdline_append": APPEND, "cmdline": b65.LAST["cmdline"]}
            d["nat067_note"] = ("NAT-065's build with a new image name, the NAT067 tag and e1stouch=0 e1sbattery=0 appended to the command line; "
                                "the nat065_* keys above are that build's own record and describe this image")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
