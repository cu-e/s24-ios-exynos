#!/usr/bin/env python3
"""IOS-004 smoke check of tools/ios/udif.py on a real IPSW root image (host-test).

usage: python3 -I docs/procedures/ios-004/smoke.py DMG [MIB=256]
Prints JSON: partitions, chunk-type histogram, the APFS container magic, the sum of partition sizes (to compare with the
unpack-size 7-Zip prints for the same file), and time and peak memory for decompressing MIB mebibytes from the start of
the largest partition.  Only counts, sizes and one SHA-256 are printed; no Apple bytes are written anywhere.
"""
import hashlib
import importlib.util
import json
import resource
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("udif", root / "tools/ios/udif.py")
udif = importlib.util.module_from_spec(spec)
spec.loader.exec_module(udif)

path = sys.argv[1]
mib = int(sys.argv[2]) if len(sys.argv) > 2 else 256
out = {"file": Path(path).name}
with open(path, "rb") as f:
    img = udif.Udif(f)
    parts = img.partitions
    big = max(range(len(parts)), key=lambda i: parts[i].sectors)
    hist = {}
    for p in parts:
        for c in p.chunks:
            name = udif.CHUNK_NAMES.get(c.type, hex(c.type))
            hist[name] = hist.get(name, 0) + 1
    out["partitions"] = [{"name": p.name, "first_sector": p.first_sector, "bytes": p.sectors * 512} for p in parts]
    out["partition_bytes_sum"] = sum(p.sectors * 512 for p in parts)
    out["chunk_histogram"] = hist
    out["apfs_magic_at_32"] = img.read(big, 0, 4096)[32:36].decode("ascii", "replace")
    h = hashlib.sha256()
    done = 0
    t0 = time.perf_counter()
    for block in img.iter_partition(big):
        h.update(block)
        done += len(block)
        if done >= mib * 1048576:
            break
    dt = time.perf_counter() - t0
    out["decompressed_bytes"] = done
    out["sha256_of_that_range"] = h.hexdigest()
    out["seconds"] = round(dt, 2)
    out["seconds_per_mib"] = round(dt / (done / 1048576), 4)
    out["peak_rss_mib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
print(json.dumps(out, indent=1))
