#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-114 mutation pass over src/glue113.h: each mutant must make test_nat113.py fail. Restores the file whatever happens.

    python3 -B -I docs/procedures/nat-113/mutate_nat113.py      -> JSON {total, killed, survived: [...]}, exit 1 on a survivor
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src" / "glue113.h"
TEST = HERE / "test_nat113.py"
MUTANTS = [
    ("(v & 0xffffffu) != 0", "v != 0"),
    ("rlen > NAT113_REC_MAX", "rlen > NAT113_REC_MAX * 2"),
    ("rpa < NAT113_RAM_LO", "rpa < 0"),
    ("rpa > NAT113_RAM_HI - rlen", "0"),
    ("(rpa & 3u) ||", ""),
    ("rlen < 32u ||", ""),
    ("32u + (uint64_t)frames * fsize > rlen", "0"),
    ("i < NAT113_FRAMES_MAX", "1"),
    ("y += NAT113_STEP", "y += NAT113_STEP + 1"),
    ("x += NAT113_STEP", "x += NAT113_STEP + 1"),
    ("h = (h ^ v) * 16777619u;\n\t\t}\n\t}", "h = (h + v) * 16777619u;\n\t\t}\n\t}"),
    ("(r & 0xe0u) | ((g & 0xe0u) >> 3) | (bl >> 6)", "(r & 0xe0u) | ((g & 0xe0u) >> 2) | (bl >> 6)"),
    ("q->sent >= NAT062_BURST", "0"),
    ("N62_WAIT();\n}\n#endif", "}\n#endif"),
    ("nzb += ((v & 0xffu) != 0)", "nzb += ((v & 0xfeu) != 0)"),
    ("N113_R32(rpa) != NAT113_MAGIC0 ||", ""),
    ("N113_R32(rpa + 4u) != NAT113_MAGIC1 ||", ""),
    ("(pix & 3u) ||", ""),
    ("hgt > 4096u ||", ""),
    ("if ((y & 63u) == 0)\n\t\t\tN113_TICK();", ""),
    ("if (rpa == 0 && rlen == 0) {", "if (rpa == 0 || rlen == 0) {"),
    ("n113_recording(pa_minus_va, &q);", ""),
]


def main():
    orig = SRC.read_text()
    killed, survived = 0, []
    base = subprocess.run([sys.executable, "-B", "-I", str(TEST)], capture_output=True, text=True, timeout=600)
    if base.returncode != 0:
        print("baseline tests fail", file=sys.stderr)
        return 2
    try:
        for old, new in MUTANTS:
            if orig.count(old) != 1:
                raise SystemExit("mutant anchor not found exactly once: %r" % old)
            SRC.write_text(orig.replace(old, new))
            r = subprocess.run([sys.executable, "-B", "-I", str(TEST)], capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                killed += 1
            else:
                survived.append(old)
    finally:
        SRC.write_text(orig)
    print(json.dumps({"total": len(MUTANTS), "killed": killed, "survived": survived}))
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
