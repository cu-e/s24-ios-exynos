#!/usr/bin/env python3
"""Offline IPSW inspector (IOS-002).

Reads an Apple restore archive without extracting it: zipfile for the container, plistlib for BuildManifest.plist,
a small DER reader for the kernelcache's IM4P wrapper and tools/ios/lzfse_py.py to reach the kernel's own version
banner. Nothing is written to disk and no Apple data is embedded in this file.

The verdict is about the archive only:

  accepted        the archive is a zip with a parseable BuildManifest.plist, its ProductBuildVersion equals the
                  expected build, its SupportedProductTypes and a BuildIdentity name the expected device, and every
                  OS/Cryptex/kernel/device-tree path the matching identities list is a member of the archive;
  wrong-build     a valid manifest for another ProductBuildVersion;
  wrong-device    the expected product type or device class is not listed;
  missing-member  the manifest lists a path the archive does not contain (or lists no OS / KernelCache / DeviceTree);
  not-an-ipsw     absent file, not a zip, no/unparseable BuildManifest.plist, unsafe member names.

"accepted" does not say the contents run on the S24. File names, build numbers and a Darwin banner are metadata; the
report carries `compatibility: "not-assessed"` so that no consumer mistakes one for the other.
"""
import argparse
import hashlib
import importlib.util
import json
import plistlib
import re
import struct
import sys
import zipfile
from pathlib import PurePosixPath, Path

EXPECTED_BUILD = "20F66"
EXPECTED_PRODUCT = "iPhone10,3"
EXPECTED_DEVICE_CLASS = "d22ap"

VERDICTS = ("accepted", "wrong-build", "wrong-device", "missing-member", "not-an-ipsw")

# Manifest component names whose paths the report lists and whose members must exist when listed.
OS_COMPONENTS = ("OS", "Cryptex1,SystemOS", "Cryptex1,AppOS")
KERNEL_COMPONENTS = ("KernelCache", "RestoreKernelCache")
TREE_COMPONENTS = ("DeviceTree", "RestoreDeviceTree")
EXTRA_COMPONENTS = ("RestoreRamDisk", "StaticTrustCache", "Cryptex1,SystemTrustCache", "Cryptex1,AppTrustCache")
REPORTED = OS_COMPONENTS + KERNEL_COMPONENTS + TREE_COMPONENTS + EXTRA_COMPONENTS
REQUIRED = ("OS", "KernelCache", "DeviceTree")

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_KERNELCACHE_BYTES = 256 * 1024 * 1024
DARWIN_RE = re.compile(rb"Darwin Kernel Version [^\x00\r\n]{8,300}")


class InspectError(Exception):
    pass


def _load_lzfse():
    path = Path(__file__).resolve().parent / "lzfse_py.py"
    spec = importlib.util.spec_from_file_location("lzfse_py", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("lzfse_py", module)
    spec.loader.exec_module(module)
    return module


def unsafe_member(name):
    """Reason a zip member name is refused, or None. Members are never extracted, but a hostile name must not
    reach a report or a later extraction step."""
    if not name or "\x00" in name or "\\" in name:
        return "empty, NUL or backslash in the name"
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return "absolute path"
    parts = PurePosixPath(name).parts
    if any(part == ".." for part in parts):
        return "parent-directory component"
    return None


# ---- IM4P / DER ------------------------------------------------------------------------------------------------

def der_element(buf, pos, end=None):
    """Return (tag, content_start, content_end) of the DER element at pos. Definite lengths only."""
    end = len(buf) if end is None else end
    if pos + 2 > end:
        raise InspectError("DER element truncated at %d" % pos)
    tag = buf[pos]
    if tag & 0x1F == 0x1F:
        raise InspectError("DER multi-byte tag at %d is not used by IM4P" % pos)
    length = buf[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or count > 4 or pos + count > end:
            raise InspectError("DER length form at %d is not supported" % (pos - 1))
        length = int.from_bytes(buf[pos:pos + count], "big")
        pos += count
    if pos + length > end:
        raise InspectError("DER element at %d runs past its parent (%d > %d)" % (pos, pos + length, end))
    return tag, pos, pos + length


def parse_im4p(buf):
    """Parse an IM4P and return {kind, description, payload (memoryview slice bounds), compression}. No decryption:
    an IM4P with a key bag is reported as encrypted."""
    tag, start, end = der_element(buf, 0)
    if tag != 0x30:
        raise InspectError("IM4P does not start with a DER SEQUENCE")
    items = []
    pos = start
    while pos < end:
        t, cs, ce = der_element(buf, pos, end)
        items.append((t, cs, ce))
        pos = ce
    if len(items) < 4 or any(t != 0x16 for t, _, _ in items[:3]) or buf[items[0][1]:items[0][2]] != b"IM4P":
        raise InspectError("not an IM4P: expected IA5String 'IM4P', type, description, then the payload")
    if items[3][0] != 0x04:
        raise InspectError("IM4P payload is not an OCTET STRING")
    result = {
        "kind": bytes(buf[items[1][1]:items[1][2]]).decode("ascii", "replace"),
        "description": bytes(buf[items[2][1]:items[2][2]]).decode("ascii", "replace"),
        "payload": (items[3][1], items[3][2]),
        "key_bag": False,
        "compression": None,
    }
    for t, cs, ce in items[4:]:
        if t == 0x04:
            result["key_bag"] = True
        elif t == 0x30:
            inner = []
            p = cs
            while p < ce:
                it, ics, ice = der_element(buf, p, ce)
                inner.append(int.from_bytes(buf[ics:ice], "big") if it == 0x02 else None)
                p = ice
            if len(inner) == 2 and None not in inner:
                result["compression"] = {"algorithm_id": inner[0], "uncompressed_size": inner[1]}
    return result


def macho_container(data):
    """Describe the first bytes of a decoded kernelcache: fat wrapper and thin Mach-O header fields."""
    info = {"container": "unknown"}
    if len(data) >= 8 and data[:4] == b"\xca\xfe\xba\xbe":
        count = struct.unpack_from(">I", data, 4)[0]
        if not 1 <= count <= 8 or len(data) < 8 + 20 * count:
            return {"container": "fat-malformed"}
        arches = []
        for i in range(count):
            cputype, cpusub, off, size, align = struct.unpack_from(">iiIII", data, 8 + 20 * i)
            arches.append({"cputype": "0x%x" % (cputype & 0xFFFFFFFF), "cpusubtype": "0x%x" % (cpusub & 0xFFFFFFFF),
                           "offset": off, "size": size})
        info = {"container": "fat", "slices": arches}
        off = arches[0]["offset"]
        thin = data[off:off + 32]
    else:
        thin = data[:32]
    if len(thin) >= 32 and thin[:4] == b"\xcf\xfa\xed\xfe":
        cputype, cpusub, filetype, ncmds, sizeofcmds, flags = struct.unpack_from("<iiIIII", thin, 4)
        info["macho"] = {"magic": "MH_MAGIC_64", "cputype": "0x%x" % (cputype & 0xFFFFFFFF),
                         "cpusubtype": "0x%x" % (cpusub & 0xFFFFFFFF), "filetype": filetype, "ncmds": ncmds,
                         "sizeofcmds": sizeofcmds, "flags": "0x%x" % flags}
        if info["container"] == "unknown":
            info["container"] = "thin"
    return info


def kernelcache_banner(raw):
    """From the kernelcache member bytes: IM4P fields, the decoded Mach-O container and the Darwin banner. The
    decoder stops once a NUL-terminated banner is in the output, so the 50 MB image is not decoded in full."""
    im4p = parse_im4p(raw)
    out = {"im4p_kind": im4p["kind"], "im4p_description": im4p["description"], "key_bag": im4p["key_bag"],
           "compression": im4p["compression"]}
    if im4p["key_bag"]:
        out["banner"] = None
        out["note"] = "payload has a key bag; not decrypted here"
        return out
    start, end = im4p["payload"]
    payload = bytes(raw[start:end])
    if payload[:4] == b"\xca\xfe\xba\xbe" or payload[:4] == b"\xcf\xfa\xed\xfe":
        decoded, complete = bytearray(payload), True
    elif payload[:4] in (b"bvx2", b"bvxn", b"bvx-", b"bvx1"):
        lz = _load_lzfse()
        decoded = bytearray()
        complete = False
        scanned = 0
        try:
            for _kind, buf in lz.iter_blocks(payload):
                decoded = buf
                m = DARWIN_RE.search(buf, max(0, scanned - 400))
                scanned = len(buf)
                if m and m.end() < len(buf):
                    break
            else:
                complete = True
        except lz.LzfseError as exc:
            raise InspectError("LZFSE payload does not decode: %s" % exc)
    else:
        raise InspectError("payload starts with %r: neither a Mach-O nor an LZFSE stream" % payload[:4])
    out["decoded_prefix_bytes"] = len(decoded)
    out["decoded_complete"] = complete
    out["container"] = macho_container(bytes(decoded[:64]))
    m = DARWIN_RE.search(decoded)
    banner = m.group(0).decode("ascii", "replace") if m else None
    out["banner"] = banner
    if banner:
        x = re.search(r"root:(xnu-[0-9A-Za-z.~_-]+)/([A-Z0-9_]+)", banner)
        out["xnu"] = x.group(1) if x else None
        out["kernel_config"] = x.group(2) if x else None
    return out


# ---- archive ---------------------------------------------------------------------------------------------------

def _verdict(verdict, detail, report):
    report["verdict"] = verdict
    report["detail"] = detail
    return report


def inspect(path, expect_build=EXPECTED_BUILD, expect_product=EXPECTED_PRODUCT,
            expect_device_class=EXPECTED_DEVICE_CLASS, with_sha256=False, with_kernel=False):
    path = Path(path)
    report = {"path": str(path), "expected": {"build": expect_build, "product_type": expect_product,
                                              "device_class": expect_device_class},
              "compatibility": "not-assessed", "verdict": None, "detail": None}
    if not path.is_file():
        return _verdict("not-an-ipsw", "no such file: %s" % path, report)
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        return _verdict("not-an-ipsw", "not a readable zip archive: %s" % exc, report)
    with archive:
        infos = archive.infolist()
        for info in infos:
            why = unsafe_member(info.filename)
            if why:
                return _verdict("not-an-ipsw", "unsafe member name %r: %s" % (info.filename, why), report)
        members = {i.filename: i for i in infos}
        report["member_count"] = len(infos)
        manifest_info = members.get("BuildManifest.plist")
        if manifest_info is None:
            return _verdict("not-an-ipsw", "member BuildManifest.plist is absent", report)
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            return _verdict("not-an-ipsw", "BuildManifest.plist is larger than %d bytes" % MAX_MANIFEST_BYTES, report)
        try:
            manifest = plistlib.loads(archive.read(manifest_info))
            build = manifest["ProductBuildVersion"]
            version = manifest.get("ProductVersion")
            products = list(manifest["SupportedProductTypes"])
            identities = list(manifest["BuildIdentities"])
        except (plistlib.InvalidFileException, KeyError, TypeError, ValueError, zipfile.BadZipFile, OSError) as exc:
            return _verdict("not-an-ipsw", "BuildManifest.plist is not a usable manifest: %s: %s"
                            % (type(exc).__name__, exc), report)
        report.update({"product_build_version": build, "product_version": version, "supported_product_types": products})

        classes = []
        matching = []
        for identity in identities:
            if not isinstance(identity, dict) or not isinstance(identity.get("Info"), dict):
                continue
            cls = str(identity["Info"].get("DeviceClass", "")).lower()
            classes.append(cls)
            if cls == expect_device_class.lower():
                matching.append(identity)
        report["device_classes"] = sorted(set(classes))
        if build != expect_build:
            return _verdict("wrong-build", "ProductBuildVersion is %r, expected %r" % (build, expect_build), report)
        if expect_product not in products:
            return _verdict("wrong-device", "SupportedProductTypes %s does not list %s" % (products, expect_product),
                            report)
        if not matching:
            return _verdict("wrong-device", "no BuildIdentity has DeviceClass %s (found %s)"
                            % (expect_device_class, sorted(set(classes))), report)

        components = {}
        missing = []
        for identity in matching:
            behavior = identity["Info"].get("RestoreBehavior", "")
            manifest_entries = identity.get("Manifest") or {}
            for name in REPORTED:
                entry = manifest_entries.get(name)
                info = entry.get("Info") if isinstance(entry, dict) else None
                member = info.get("Path") if isinstance(info, dict) else None
                if not isinstance(member, str):
                    if name in REQUIRED:
                        missing.append("%s (%s identity lists no path)" % (name, behavior or "?"))
                    continue
                why = unsafe_member(member)
                if why:
                    return _verdict("not-an-ipsw", "manifest path %r for %s is unsafe: %s" % (member, name, why), report)
                # Identities of one device may name different files for one component (the Erase and Update
                # identities of D22AP use different RestoreRamDisk images), so a component maps to every distinct path.
                slots = components.setdefault(name, [])
                slot = next((x for x in slots if x["path"] == member), None)
                if slot is None:
                    slot = {"path": member, "identities": []}
                    slots.append(slot)
                slot["identities"].append(behavior)
                if member not in members and member not in missing:
                    missing.append(member)
        for slots in components.values():
            for slot in slots:
                info = members.get(slot["path"])
                if info is not None:
                    slot["size"] = info.file_size
                    slot["stored"] = info.compress_type == zipfile.ZIP_STORED
        report["components"] = components
        report["identity_behaviors"] = sorted({i["Info"].get("RestoreBehavior", "") for i in matching})
        if missing:
            return _verdict("missing-member", "listed but absent or unlisted: %s" % ", ".join(sorted(set(missing))),
                            report)

        if with_sha256:
            hashes = {}
            for name in ["BuildManifest.plist"] + sorted({x["path"] for slots in components.values() for x in slots}):
                digest = hashlib.sha256()
                try:
                    with archive.open(members[name]) as handle:
                        for chunk in iter(lambda: handle.read(1 << 20), b""):
                            digest.update(chunk)
                except (zipfile.BadZipFile, OSError) as exc:
                    return _verdict("not-an-ipsw", "member %s does not read back cleanly: %s" % (name, exc), report)
                hashes[name] = digest.hexdigest()
            report["member_sha256"] = hashes
        if with_kernel:
            info = members[components["KernelCache"][0]["path"]]
            if info.file_size > MAX_KERNELCACHE_BYTES:
                report["kernelcache"] = {"error": "kernelcache member is larger than %d bytes" % MAX_KERNELCACHE_BYTES}
            else:
                try:
                    report["kernelcache"] = kernelcache_banner(archive.read(info))
                except (InspectError, zipfile.BadZipFile) as exc:
                    report["kernelcache"] = {"error": str(exc)}
    return _verdict("accepted", "manifest names build %s for %s; every path listed for %d components is a member"
                    % (expect_build, expect_product, len(components)), report)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ipsw")
    ap.add_argument("--build", default=EXPECTED_BUILD)
    ap.add_argument("--product-type", default=EXPECTED_PRODUCT)
    ap.add_argument("--device-class", default=EXPECTED_DEVICE_CLASS)
    ap.add_argument("--sha256", action="store_true", help="stream-hash the archive and each listed member")
    ap.add_argument("--kernel", action="store_true", help="decode the kernelcache far enough to read its Darwin banner")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    report = inspect(args.ipsw, args.build, args.product_type, args.device_class, args.sha256, args.kernel)
    if args.sha256 and Path(args.ipsw).is_file():
        report["archive_sha256"] = file_sha256(args.ipsw)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("verdict: %s\n%s" % (report["verdict"], report["detail"]))
        if report.get("product_build_version"):
            print("build %s version %s products %s" % (report["product_build_version"], report.get("product_version"),
                                                      report.get("supported_product_types")))
        for name, slots in sorted(report.get("components", {}).items()):
            for slot in slots:
                print("  %-26s %s (%d B) %s" % (name, slot["path"], slot.get("size", -1), ",".join(slot["identities"])))
        kc = report.get("kernelcache")
        if kc:
            print("kernelcache:", kc.get("banner") or kc.get("error") or kc.get("note"))
        print("compatibility: not-assessed (metadata only)")
    if report["verdict"] != "accepted":
        return 2
    return 3 if args.kernel and "error" in report.get("kernelcache", {}) else 0


if __name__ == "__main__":
    sys.exit(main())
