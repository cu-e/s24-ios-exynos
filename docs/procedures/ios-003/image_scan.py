#!/usr/bin/env python3
"""IOS-003 host inspection: count marker strings in the built NAT-069 recovery image.

Evidence class: host inspection of a build artifact. A string in the payload says the text is present; it does not say
the code runs, registers or is correct. Usage: python3 -I image_scan.py IMAGE > scan.json
"""
import hashlib
import json
import re
import sys

data = open(sys.argv[1], "rb").read()


def distinct(pattern):
    return len(set(re.findall(pattern, data)))


out = {
    "image_sha256": hashlib.sha256(data).hexdigest(),
    "image_bytes": len(data),
    "distinct_apfs_symbols": distinct(rb"apfs_[A-Za-z0-9_]{2,}"),
    "distinct_mockfs_symbols": distinct(rb"mockfs_[A-Za-z0-9_]{2,}"),
    "MiniAppleKeyStore_occurrences": len(re.findall(rb"MiniAppleKeyStore", data)),
    "distinct_MiniIOSurface_strings": distinct(rb"MiniIOSurface[A-Za-z0-9_:]*"),
    "distinct_trust_cache_strings": distinct(rb"trust_cache[A-Za-z0-9_]*"),
    "absent_markers": {m: data.count(m.encode()) for m in
                       ("launchd_unsecure_cache", "ignition_level", "purplebuddy", "Apple File System")},
}
print(json.dumps(out, indent=2))
