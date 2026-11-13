#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-117: the NAT-085 ADT (pinned e1s.adt + /chosen ephemeral-storage) plus the real D22AP /product node (host only).

    make_adt117.py --out e1s-product.adt     reads the pinned e1s.adt and the IPSW's DeviceTree.d22ap.im4p, writes the derived ADT, prints JSON

Why (NAT-116): SpringBoard aborts in -[_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:] with "Failed to load bounding
path bitmap data from the asset manager for asset name: BoundingPathBitmap-1125x2436-375x812-3.00x". The asset is in
UIKitCore.framework/BoundingPathData.bundle/Assets.car; CoreUI picks renditions by the device traits UIKit takes from MobileGestalt, and
MobileGestalt takes them from the device tree's /product node (artwork-device-subtype, artwork-scale-factor, artwork-device-idiom, ...).
The project ADT has no /product node: the donor's tools/e1s/xnu/mkadt.py adds it from research/ipsw-x/d22ap.adt only when that file
exists, and it was absent when NAT-020 built e1s.adt. That the missing node is the cause of the abort is a hypothesis; NAT-118 tests it.

The /product node is built exactly as mkadt.py's d22ap_product() + build() do: every property of the real D22AP /product whose flag
bit is clear (iBoot fills the flagged syscfg placeholders on a real phone), without `name` and `AAPL,phandle`; artwork-display-gamut
replaced by "sRGB" (mkadt's rule: the panel path here is plain sRGB); a fresh phandle above every phandle in the tree. Child nodes of
the real /product (camera, haptics, ...) are not copied (mkadt copies none either). The node is appended after the existing children
of the root, the place mkadt gives it (before sweet-ufs there; order of root children carries no meaning for IORegistry lookups by path).
"""
import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IM4P = ROOT / "artifacts/ios-root/recipe/sysimage/DeviceTree.d22ap.im4p"
IM4P_SHA = "51e7e42b74fb5e4cf5c7c1eed30b3d79ec829edfe8c0884c2e7839ddf62a4853"
D22AP_SHA = None  # filled in by derive() from the decoded bytes; recorded, not pinned in advance
GAMUT = b"sRGB\0"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


m85 = _load("nat117_make_adt85", ROOT / "docs/procedures/nat-085/make_adt85.py")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def d22ap_adt(im4p_bytes):
    """-> the raw D22AP device tree from the IM4P (DER: SEQUENCE{IA5 'IM4P', IA5 'dtre', IA5 desc, OCTET STRING payload}), LZFSE-decoded."""
    if sha(im4p_bytes) != IM4P_SHA:
        raise ValueError("DeviceTree.d22ap.im4p is not the pinned file (sha256 %s)" % sha(im4p_bytes))
    b = im4p_bytes
    pos = 0

    def tlv():
        nonlocal pos
        tag = b[pos]
        ln = b[pos + 1]
        pos += 2
        if ln & 0x80:
            n = ln & 0x7f
            ln = int.from_bytes(b[pos:pos + n], "big")
            pos += n
        return tag, ln

    tag, _ = tlv()
    if tag != 0x30:
        raise ValueError("IM4P is not a DER SEQUENCE")
    fields = []
    for _ in range(4):
        tag, ln = tlv()
        fields.append((tag, b[pos:pos + ln]))
        pos += ln
    if [t for t, _ in fields] != [0x16, 0x16, 0x16, 0x04] or fields[0][1] != b"IM4P" or fields[1][1] != b"dtre":
        raise ValueError("unexpected IM4P layout: %r" % [(t, v[:8]) for t, v in fields])
    payload = fields[3][1]
    if payload[:4] not in (b"bvx2", b"bvx1", b"bvxn", b"bvx-"):
        raise ValueError("payload is not LZFSE")
    sys.path.insert(0, str(ROOT / "tools/ios"))
    try:
        import lzfse_py
    finally:
        sys.path.pop(0)
    return lzfse_py.decode(payload)


def product_props(adt, d22ap_bytes):
    """-> [(name, value)] of the D22AP /product kept by mkadt's rule (flag clear, no name/phandle), gamut -> sRGB."""
    root, end = adt.parse(d22ap_bytes)
    if end != len(d22ap_bytes):
        raise ValueError("trailing bytes after the D22AP tree")
    nodes = [c for c in root.children if c.name == "product"]
    if len(nodes) != 1:
        raise ValueError("expected one /product in the D22AP tree, found %d" % len(nodes))
    kept = [(k, v) for k, f, v in nodes[0].props if not f and k not in ("name", "AAPL,phandle")]
    return [(k, GAMUT if k == "artwork-display-gamut" else v) for k, v in kept]


def max_phandle(node):
    v = node.prop("AAPL,phandle")
    m = struct.unpack("<I", v)[0] if v is not None and len(v) == 4 else 0
    return max([m] + [max_phandle(c) for c in node.children])


def derive(pinned_blob, im4p_bytes, adt=None):
    """-> (new blob, record). `pinned_blob` is the pinned e1s.adt; NAT-085's derivation is applied first, unchanged."""
    adt = adt or m85._adt()
    eph, eph_rec = m85.derive(pinned_blob, adt)
    d22 = d22ap_adt(im4p_bytes)
    props = product_props(adt, d22)
    root, end = adt.parse(eph)
    if end != len(eph) or adt.serialize(root) != eph:
        raise ValueError("NAT-085's ADT does not round-trip")
    if any(c.name == "product" for c in root.children):
        raise ValueError("the ADT already has /product")
    ph = max_phandle(root) + 1
    node = adt.Node()
    node.props = [("name", 0, b"product\0"), ("AAPL,phandle", 0, struct.pack("<I", ph))] + [(k, 0, v) for k, v in props]
    root.children.append(node)
    out = adt.serialize(root)
    key = {k: v for k, v in props}
    return out, {"input_sha256": sha(pinned_blob), "nat085_sha256": sha(eph), "nat085": eph_rec, "d22ap_im4p_sha256": IM4P_SHA,
                 "d22ap_adt_sha256": sha(d22), "d22ap_adt_bytes": len(d22), "output_sha256": sha(out), "output_bytes": len(out),
                 "product": {"properties": len(props), "phandle": ph, "bytes_added": len(out) - len(eph),
                             "artwork-device-subtype": struct.unpack("<I", key["artwork-device-subtype"])[0],
                             "artwork-scale-factor": struct.unpack("<I", key["artwork-scale-factor"])[0],
                             "artwork-device-idiom": key["artwork-device-idiom"].rstrip(b"\0").decode(),
                             "artwork-display-gamut": key["artwork-display-gamut"].rstrip(b"\0").decode(),
                             "product-name": key["product-name"].rstrip(b"\0").decode()}}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.out.exists():
        print("refused: %s exists" % a.out, file=sys.stderr)
        return 2
    try:
        out, rec = derive((m85.B3 / "e1s.adt").read_bytes(), IM4P.read_bytes())
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    a.out.write_bytes(out)
    print(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
