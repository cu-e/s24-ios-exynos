#!/usr/bin/env python3
"""Larger fuzz runs of the NAT-030 interpreter against Unicorn (needs capstone and unicorn).

Usage: fuzz_seeds.py SEED COUNT   (4 trials per word; the Differ seed is SEED + 1)

Prints the status counts, any mismatch, the mnemonics the interpreter does not implement (counted, not
compared) and any Unicorn fault. The test suite runs one small fixed seed; this script exists so the larger
runs quoted in README.md can be repeated. Exit code 1 if there is a mismatch or a Unicorn fault.
"""
import collections
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_kstart_sim as T  # noqa: E402


def main(argv):
    seed, count = int(argv[1]), int(argv[2])
    case = T.SemanticsVsUnicorn("test_fuzz_agrees_with_unicorn")
    rng = random.Random(seed)
    differ = T.Differ(seed + 1)
    res = collections.defaultdict(list)
    for w in case.fuzz_words(rng, count):
        status, detail = differ.compare(w, trials=4)
        res[status].append(detail)
    print({k: len(v) for k, v in res.items()})
    for m in res["mismatch"][:30]:
        print("MISMATCH", m[:240])
    print("UNSUPPORTED", dict(collections.Counter(x.split()[0] for x in res["unsupported"])))
    print("UC-FAULT", dict(collections.Counter(x.split()[0] for x in res["unicorn-fault"])))
    return 1 if res["mismatch"] or res["unicorn-fault"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
