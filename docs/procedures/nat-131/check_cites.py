#!/usr/bin/env python3
"""NAT-131: check that every file:line citation in cites.tsv holds at the pinned vendor revision.

cites.tsv rows: <path in references/s24-linux> TAB <1-based line> TAB <literal text that must occur on that line>.
The file is read with `git show <pin>:<path>` (the checkout is sparse, so the working tree is not used).
Exit 0 when every row matches, 1 when any row does not, 2 when the checkout or the pin is missing.
This proves only that the cited text is at the cited line; it does not prove the README's reading of it.
"""
import os
import subprocess
import sys

PIN = "417484173abc2c4fa93e738ea82ad9f2e84911b1"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REPO = os.path.join(ROOT, "references", "s24-linux")


def main():
    tsv = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cites.tsv")
    have = subprocess.run(["git", "-C", REPO, "cat-file", "-e", PIN + "^{commit}"], capture_output=True)
    if have.returncode != 0:
        print("pinned revision %s not available in %s" % (PIN, REPO))
        return 2
    cache = {}
    total = bad = 0
    with open(tsv, encoding="utf-8") as fh:
        for row in fh:
            row = row.rstrip("\n")
            if not row:
                continue
            path, line, text = row.split("\t", 2)
            line = int(line)
            total += 1
            if path not in cache:
                out = subprocess.run(["git", "-C", REPO, "show", PIN + ":" + path], capture_output=True)
                if out.returncode != 0:
                    print("MISSING %s" % path)
                    cache[path] = []
                else:
                    cache[path] = out.stdout.decode("latin-1").split("\n")
            lines = cache[path]
            got = lines[line - 1] if 0 < line <= len(lines) else ""
            if text not in got:
                bad += 1
                print("MISMATCH %s:%d want %r got %r" % (path, line, text, got.strip()))
    print("%d citations, %d mismatches (pin %s)" % (total, bad, PIN))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
