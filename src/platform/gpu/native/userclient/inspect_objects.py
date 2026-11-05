#!/usr/bin/env python3
"""Inspect future real GPU-012 objects; never compile, link or supply stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(path):
    if path.stat().st_size > 32 * 1024 * 1024: raise ValueError("Object exceeds bounded inspection limit")
    data = path.read_bytes()
    if len(data) < 32: raise ValueError("Truncated object")
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from("<8I", data)
    if magic != 0xfeedfacf or cpu != 0x100000c or kind != 1 or size > len(data) - 32 or count > size // 8:
        raise ValueError("Expected bounded thin ARM64 MH_OBJECT")
    at = 32
    sections, defined, undefined = [], [], []
    for _ in range(count):
        cmd, length = struct.unpack_from("<II", data, at)
        if length < 8 or at + length > 32 + size: raise ValueError("Invalid command extent")
        if cmd == 25:
            if length < 72: raise ValueError("Invalid segment")
            nsects = struct.unpack_from("<I", data, at + 64)[0]
            if nsects > (length - 72) // 80: raise ValueError("Invalid section count")
            for index in range(nsects):
                name, segment, address, amount, offset = struct.unpack_from("<16s16sQQI", data, at + 72 + 80 * index)
                name, segment = name.split(b"\0")[0].decode(), segment.split(b"\0")[0].decode()
                if name.startswith("__kalloc"):
                    if offset > len(data) or amount > len(data) - offset: raise ValueError("Invalid allocator section extent")
                    sections.append({"segment": segment, "section": name, "bytes": amount,
                                     "sha256": hashlib.sha256(data[offset:offset + amount]).hexdigest()})
        if cmd == 2:
            if length != 24: raise ValueError("Invalid symbol command")
            symoff, nsyms, stroff, strsize = struct.unpack_from("<4I", data, at + 8)
            if symoff > len(data) or nsyms > (len(data) - symoff) // 16 or stroff > len(data) or strsize > len(data) - stroff:
                raise ValueError("Invalid symbol table extent")
            strings = data[stroff:stroff + strsize]
            for index in range(nsyms):
                nameoff, symtype, sect, desc, value = struct.unpack_from("<IBBHQ", data, symoff + 16 * index)
                if symtype & 0xe0: continue
                if nameoff >= len(strings): raise ValueError("Invalid symbol name")
                end = strings.find(b"\0", nameoff)
                if end < 0: raise ValueError("Unterminated symbol name")
                name = strings[nameoff:end].decode()
                if not name: continue
                (undefined if symtype & 0xe == 0 and sect == 0 else defined).append(name)
        at += length
    if at != 32 + size: raise ValueError("Command count/size mismatch")
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "defined": sorted(set(defined)),
            "undefined": sorted(set(undefined)), "allocator_metadata": sections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError("Refusing inspection overwrite")
    reports = {name: inspect(args.directory / (name + ".o")) for name in ["adapter", "policy", "dispatcher"]}
    adapter = reports["adapter"]
    for method in ["externalMethod", "initWithTask", "clientClose", "clientDied", "newUserClient"]:
        if not any(method in symbol for symbol in adapter["defined"]): raise ValueError("Missing typed adapter method: " + method)
    if not any(section["bytes"] for section in adapter["allocator_metadata"]): raise ValueError("No actual typed allocator metadata")
    if "_sgpu_dispatch" not in reports["dispatcher"]["defined"]: raise ValueError("Missing C dispatcher symbol")
    defined = {symbol for row in reports.values() for symbol in row["defined"]}
    unresolved = sorted({symbol for row in reports.values() for symbol in row["undefined"]} - defined)
    result = {"outcome": "pass", "kind": "host-test", "objects": reports, "unresolved_imports": unresolved,
              "linked": False, "executed": False, "native_gpu_qualified": False}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"outcome": "pass", "unresolved_import_count": len(unresolved)}))


if __name__ == "__main__": main()
