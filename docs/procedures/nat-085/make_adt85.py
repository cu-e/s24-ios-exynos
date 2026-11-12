#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-085: the project's ADT plus one /chosen property, `ephemeral-storage` = u32 1 (host only).

    make_adt85.py --out e1s-eph.adt        reads the pinned artifacts/nat-020/build-003/e1s.adt, writes the derived ADT, prints a JSON record

Why: Apple's keybagd (`/usr/libexec/keybagd --init`, the launchd boot task `keybag`) calls os_variant_uses_ephemeral_storage("com.apple.mobile.keybagd")
before MKB_INIT and exits 0 with "DEVICE HAS EPHEMERAL DATA VOLUME, SKIP INIT" when it is true. libsystem_darwin's os_variant initialiser (read from the
shared cache of the IPSW, 1d0d5be60..) takes it from sysctl `hw.ephemeral_storage` (state 3 = yes when the value is non-zero, 2 = no when the sysctl fails
or is 0). XNU (bsd/kern/kern_mib.c, sysctl_load_devicetree_entries) creates that value only from /chosen `ephemeral-storage` when the property is exactly
4 bytes. Our /private/var is a RAM file system at every boot, so "ephemeral data volume" is what is true here. The kernel in the payload carries the
strings `ephemeral-storage` and `ephemeral_storage`.

The derivation parses the pinned ADT with the project's adt.py, appends the property to /chosen and serialises; it refuses an ADT that already has the
property, that is not the pinned file, or whose re-serialisation differs from the input (so the only change is the added property)."""
import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
B3 = ROOT / "artifacts/nat-020/build-003"
ADT_PY = B3 / "source/tools/e1s/xnu/adt.py"
PIN_ADT = "1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e"
PROP = "ephemeral-storage"
VALUE = 1


def _adt():
    spec = importlib.util.spec_from_file_location("nat085_adt", ADT_PY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha(b):
    return hashlib.sha256(b).hexdigest()


def derive(blob, adt=None, check_pin=True):
    """-> (new blob, record). `blob` is the pinned ADT."""
    adt = adt or _adt()
    if check_pin and sha(blob) != PIN_ADT:
        raise ValueError("the input is not the pinned e1s.adt (sha256 %s)" % sha(blob))
    root, end = adt.parse(blob)
    if end != len(blob):
        raise ValueError("trailing bytes after the ADT root (%d of %d parsed)" % (end, len(blob)))
    if adt.serialize(root) != blob:
        raise ValueError("re-serialising the input does not reproduce it; refusing to derive from a lossy parse")
    chosen = [c for c in root.children if c.name == "chosen"]
    if len(chosen) != 1:
        raise ValueError("expected exactly one /chosen node, found %d" % len(chosen))
    chosen = chosen[0]
    if chosen.prop(PROP) is not None:
        raise ValueError("/chosen already has %s" % PROP)
    chosen.props.append((PROP, 0, struct.pack("<I", VALUE)))
    out = adt.serialize(root)
    return out, {"input_sha256": sha(blob), "output_sha256": sha(out), "input_bytes": len(blob), "output_bytes": len(out),
                 "added": {"node": "/chosen", "property": PROP, "value_u32": VALUE, "bytes_added": len(out) - len(blob)}}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        print("refused: %s exists" % a.out, file=sys.stderr)
        return 2
    try:
        out, rec = derive((B3 / "e1s.adt").read_bytes())
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    a.out.write_bytes(out)
    print(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
