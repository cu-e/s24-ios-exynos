#!/usr/bin/env python3
"""IOS-004 mutation pass over tools/ios/udif.py (host-test).

Each mutant is one textual change to a copy of the reader (inside a temporary tree that also holds the tests, the
LZFSE decoder and its fixture); the test file must fail for the mutant to count as killed.  The repository is never
modified.  Usage: python3 -I docs/procedures/ios-004/mutants.py [--json OUT]
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

MUTANTS = [
    ("trailer: accept any header size", "if version != 4 or hdr != TRAILER_SIZE:", "if version != 4:"),
    ("trailer: accept any version", "if version != 4 or hdr != TRAILER_SIZE:", "if hdr != TRAILER_SIZE:"),
    ("trailer: allow an empty property list", "if xml_len == 0 or xml_len > MAX_PLIST_BYTES or", "if xml_len > MAX_PLIST_BYTES or"),
    ("trailer: no upper bound on the property list", "xml_len > MAX_PLIST_BYTES or xml_off > body", "xml_off > body"),
    ("trailer: property list may run past the trailer", "or xml_len > body - xml_off:", ":"),
    ("trailer: data fork may run past the file", "or self.data_fork_length > body - self.data_fork_offset:", ":"),
    ("trailer: segmented images accepted", "if self.segment_count > 1:", "if False:"),
    ("trailer: zero data-fork length uses length 0", "fork_hi = fork_lo + self.data_fork_length if self.data_fork_length else min(xml_off, body)",
     "fork_hi = fork_lo + self.data_fork_length"),
    ("mish: no signature check", 'if blob[:4] != b"mish":', "if False:"),
    ("mish: no version check", "if version != 1:", "if False:"),
    ("mish: header length unchecked", "if len(blob) < MISH_HEADER:", "if False:"),
    ("mish: chunk count unchecked against table size", "or MISH_HEADER + n_chunks * CHUNK_SIZE > len(blob):", ":"),
    ("mish: partition outside the image unchecked (count)", "if first > image_sectors or count > image_sectors - first:", "if first > image_sectors:"),
    ("mish: partition outside the image unchecked (first)", "if first > image_sectors or count > image_sectors - first:", "if count > image_sectors - first:"),
    ("chunk: comment chunk with sectors accepted", "if nsec:\n                raise UdifError(\"blkx %d chunk %d: comment chunk", "if False:\n                raise UdifError(\"blkx %d chunk %d: comment chunk"),
    ("chunk: ADC accepted at parse time", "if t == CHUNK_ADC:", "if False:"),
    ("chunk: unknown types accepted", "if t not in CHUNK_NAMES or t in (CHUNK_END, CHUNK_COMMENT):", "if False:"),
    ("chunk: gaps between chunks accepted", "if sec != expect:", "if False:"),
    ("chunk: chunk may run past the partition", "if nsec > count - sec:", "if False:"),
    ("chunk: size limit applies to nothing", "if t not in _NO_DATA and t != CHUNK_RAW and nsec * SECTOR > MAX_CHUNK_BYTES:", "if False:"),
    ("chunk: size limit applies to raw as well", "if t not in _NO_DATA and t != CHUNK_RAW and nsec * SECTOR > MAX_CHUNK_BYTES:", "if t not in _NO_DATA and nsec * SECTOR > MAX_CHUNK_BYTES:"),
    ("chunk: zero chunk may carry data", "if t in _NO_DATA:\n            if length:", "if t in _NO_DATA:\n            if False:"),
    ("chunk: data before the data fork accepted", "if absolute < fork_lo or length > fork_hi - fork_lo or absolute > fork_hi - length:",
     "if length > fork_hi - fork_lo or absolute > fork_hi - length:"),
    ("chunk: data longer than the fork accepted", "if absolute < fork_lo or length > fork_hi - fork_lo or absolute > fork_hi - length:",
     "if absolute < fork_lo or absolute > fork_hi - length:"),
    ("chunk: data past the fork end accepted", "if absolute < fork_lo or length > fork_hi - fork_lo or absolute > fork_hi - length:",
     "if absolute < fork_lo or length > fork_hi - fork_lo:"),
    ("chunk: raw length unchecked", "if t == CHUNK_RAW and length != nsec * SECTOR:", "if False:"),
    ("chunk: coverage unchecked", "if expect != count:", "if False:"),
    ("partition: overlap accepted", "if first < prev_end:", "if False:"),
    ("decode: output length unchecked", "if len(out) != want:", "if False:"),
    ("decode: zlib unbounded", "out = d.decompress(data, want + 1)\n        elif kind == CHUNK_BZIP2:", "out = d.decompress(data)\n        elif kind == CHUNK_BZIP2:"),
    ("decode: bzip2 unbounded", "out = d.decompress(data, want + 1)\n        elif kind == CHUNK_LZMA:", "out = d.decompress(data)\n        elif kind == CHUNK_LZMA:"),
    ("decode: lzma unbounded", "out = d.decompress(data, want + 1)\n        elif kind == CHUNK_LZFSE:", "out = d.decompress(data)\n        elif kind == CHUNK_LZFSE:"),
    ("decode: lzfse decoded as zlib", "elif kind == CHUNK_LZFSE:\n            global _lzfse", "elif False:\n            global _lzfse"),
    ("cache: never evicts", "if len(self._cache) > self._cache_max:", "if False:"),
    ("cache: key ignores the chunk offset", "key = (chunk.sector, chunk.offset)", "key = (chunk.offset,)"),
    ("read: zero runs materialised from the chunk start", "take = min(end - pos, c.out_bytes - within)\n                out += bytes(take)", "take = min(end - pos, c.out_bytes)\n                out += bytes(take)"),
    ("read: stored slice ignores the in-chunk offset", "out += self._pread(c.offset + within, take)", "out += self._pread(c.offset, take)"),
    ("read: end not clipped to the partition", "end = min(offset + length, p.byte_size)", "end = offset + length"),
    ("read: negative offsets accepted", "if offset < 0 or length < 0:", "if False:"),
    ("find_chunk: off-by-one on the upper bound", "elif sector >= c.sector + c.sectors:", "elif sector > c.sector + c.sectors:"),
    ("find_chunk: bisect moves the wrong way", "lo = mid + 1\n            else:\n                return mid", "lo = mid\n            else:\n                return mid"),
    ("part: any index accepted", "if not isinstance(index, int) or not 0 <= index < len(self.partitions):", "if False:"),
    ("reader: negative seek accepted", "if base + off < 0:\n            raise ValueError(\"negative seek\")\n        self.pos = base + off", "if False:\n            raise ValueError(\"negative seek\")\n        self.pos = base + off"),
    ("window: read not clipped", "if n is None or n < 0 or n > remaining:\n            n = remaining", "if n is None or n < 0:\n            n = remaining"),
    ("zip: compressed members accepted", "if info.compress_type != zipfile.ZIP_STORED:", "if False:"),
    ("zip: local header extra field ignored", "return Window(raw, info.header_offset + 30 + name_len + extra_len, info.file_size), raw",
     "return Window(raw, info.header_offset + 30 + name_len, info.file_size), raw"),
]


def run(tree, timeout=90):
    """Run the tests in the mutant tree; a hang (unbounded decompression, endless loop) counts as a failure."""
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_udif.py"],
                           cwd=tree, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, "timeout after %d s" % timeout
    return r.returncode, (r.stderr or "")[-300:]


def main():
    out_path = None
    if "--json" in sys.argv:
        out_path = sys.argv[sys.argv.index("--json") + 1]
    src = (ROOT / "tools/ios/udif.py").read_text()
    results = []
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        (tree / "tools/ios").mkdir(parents=True)
        (tree / "tests/fixtures").mkdir(parents=True)
        shutil.copy(ROOT / "tools/ios/lzfse_py.py", tree / "tools/ios/lzfse_py.py")
        shutil.copy(ROOT / "tests/test_udif.py", tree / "tests/test_udif.py")
        shutil.copy(ROOT / "tests/fixtures/lzfse_vectors.json", tree / "tests/fixtures/lzfse_vectors.json")
        (tree / "tools/ios/udif.py").write_text(src)
        code, tail = run(tree)
        if code != 0:
            print("baseline fails:", tail)
            return 2
        for name, old, new in MUTANTS:
            if src.count(old) != 1:
                results.append({"mutant": name, "status": "invalid", "occurrences": src.count(old)})
                continue
            (tree / "tools/ios/udif.py").write_text(src.replace(old, new))
            code, tail = run(tree)
            row = {"mutant": name, "status": "survived" if code == 0 else "killed"}
            if code == -1:
                row["by"] = "timeout"
            results.append(row)
            print("%-8s %s" % (row["status"], name), flush=True)
    killed = sum(r["status"] == "killed" for r in results)
    survived = [r["mutant"] for r in results if r["status"] == "survived"]
    invalid = [r["mutant"] for r in results if r["status"] == "invalid"]
    print("mutants %d killed %d survived %d invalid %d" % (len(results), killed, len(survived), len(invalid)))
    for n in survived:
        print("  SURVIVED:", n)
    for n in invalid:
        print("  INVALID (pattern not unique):", n)
    if out_path:
        Path(out_path).write_text(json.dumps({"mutants": results, "killed": killed, "survived": survived,
                                              "invalid": invalid}, indent=1) + "\n")
    return 0 if not survived and not invalid else 1


if __name__ == "__main__":
    sys.exit(main())
