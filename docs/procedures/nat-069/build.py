#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-069: build loader-diag-xnu-ne2-usb on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source [--deadline-s 60] [--service-tenths 3]
  build.py --check-only --loader-source COPY_OF_...

This is NAT-065's build (docs/procedures/nat-065/build.py, itself NAT-062's) loaded as a module and called with three values replaced, exactly as NAT-067 does
(docs/procedures/nat-067/build.py): the image name, the command-line tag and the appended boot-args.

  * the image name `loader-diag-xnu-ne2-usb` (ne2 = NAT-067's ne1 image + the display pipeline dump; same length as the ne1 name, so the loader differs from the
    one that ran in NAT-068 only in the six boot-id/name immediate words);
  * the command-line tag `nat_attempt=NAT069-md0`;
  * the appended boot-args are NAT-067's plus ` e1sdisp=2`. The pinned e1s display patch (0010-e1s-display.patch) reads the boot-arg `e1sdisp` (default 1 = print the
    framebuffer the console uses; 2 = additionally read the DECON0/RDMA/DSIM0/DSIM1/DCPHY0 registers and print them). The reads happen in e1s_display_probe(), called from
    bsd_init after devfs_kernel_mount: the kernel maps seven display register windows with ml_io_map and only reads them (test_nat069.py checks that on the patch source).

Nothing else differs: the ramdisk, the kernel, the ADT, the loader code are NAT-065's (and NAT-067's).

Output: DIR/loader-diag-xnu-ne2-usb/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-ne2-usb"
NEW_TAG = "nat_attempt=NAT069-md0"
APPEND_NAT067 = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0"
APPEND = APPEND_NAT067 + " e1sdisp=2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b65 = _load("nat069_nat065_build", PROC / "nat-065" / "build.py")


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
            d["nat069_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
            d["nat069_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "cmdline_append": APPEND, "cmdline": b65.LAST["cmdline"]}
            d["nat069_note"] = ("NAT-065's build with a new image name, the NAT069 tag and NAT-067's boot-args plus e1sdisp=2 appended to the command line; "
                                "the nat065_* keys above are that build's own record and describe this image")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
