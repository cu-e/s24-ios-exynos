#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-031 mutation check: copies src/ to a temporary directory, applies ONE textual mutation to ckpt.c or
ckpt_stub.S, runs the ckpt/marker/chain test classes of test_nat031.py against that copy (NAT031_SRC) and
reports whether any test failed (KILLED) or none did (SURVIVED). Run it with a Python that has capstone and
unicorn so the KernelChain tests are not skipped (a skipped test cannot kill a mutation):

    <venv>/bin/python docs/procedures/nat-022/test_support/mutate_nat031.py [index ...]

Exit status 1 if any mutation survives. Nothing here touches the phone."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
PY = sys.executable
M = [
 ("resume lands one instruction early", "ckpt.c", "NAT031_SITE_WORDS * 4 + st->pa_minus_va", "(NAT031_SITE_WORDS - 1) * 4 + st->pa_minus_va"),
 ("accepts any later checkpoint", "ckpt.c", "x3 == st->expect && x3 >= 1", "x3 >= st->expect && x3 >= 1"),
 ("resumes at five", "ckpt.c", "if (x3 < NAT031_NSITES) {", "if (x3 <= NAT031_NSITES) {"),
 ("site number not compared", "ckpt.c", "w[3] == (0xf100015fu | (n << 10))", "(w[3] & 0xffc003ffu) == 0xf100015fu"),
 ("slot word 3 not checked", "ckpt.c", " ||\n\t    rd64(slot + 8) || rd64(slot + 16) || rd64(slot + 24))", " ||\n\t    rd64(slot + 8) || rd64(slot + 16))"),
 ("next number off by one", "ckpt.c", "st64(st->slot_pa + 16, next);", "st64(st->slot_pa + 16, next + 1);"),
 ("first checkpoint is 2", "ckpt.c", "st64(slot + 16, 1);", "st64(slot + 16, 2);"),
 ("mask bit shifted", "ckpt.c", "st->mask |= 1u << x3;", "st->mask |= 1u << (x3 + 1);"),
 ("expectation does not advance", "ckpt.c", "st->expect = (uint32_t)x3 + 1;", "st->expect = (uint32_t)x3;"),
 ("slot address of the site not checked", "ckpt.c", "if (page + ((w[1] >> 10) & 0xfffu) != NAT031_SLOT_VA)\n\t\treturn 0;", ""),
 ("pa_minus_va wrong sign", "ckpt.c", "st->pa_minus_va = (uint64_t)win_base - virt_base;", "st->pa_minus_va = virt_base - (uint64_t)win_base;"),
 ("exception treated as orderly", "ckpt.c", "x2 == 1 ? NAT031_MASK_EXC : x2 == 0 ? NAT031_MASK_ORDERLY", "x2 == 1 ? NAT031_MASK_ORDERLY : x2 == 0 ? NAT031_MASK_EXC"),
 ("esr taken from x4", "ckpt.c", "r.esr = f->x[3];", "r.esr = f->x[4];"),
 ("stub keeps x9 as kernel sp", "ckpt_stub.S", "mov\tx9, x0\t\t\t/* continuation */", "mov\tx9, x9\t\t\t/* continuation */"),
 ("site slot address ignored (compiles)", "ckpt.c", "if (page + ((w[1] >> 10) & 0xfffu) != NAT031_SLOT_VA)", "if (0 && page + ((w[1] >> 10) & 0xfffu) != NAT031_SLOT_VA)"),
 ("stub frame 0x80 bytes", "ckpt_stub.S", "sub\tx10, x10, #0x100", "sub\tx10, x10, #0xf0"),
]
only = sys.argv[1:]
survived = 0
for i, (name, f, a, b) in enumerate(M):
    if only and str(i) not in only: continue
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / 'src'; shutil.copytree(HERE / 'src', d)
        txt = (d / f).read_text()
        assert txt.count(a) == 1, (name, txt.count(a))
        (d / f).write_text(txt.replace(a, b))
        r = subprocess.run([PY, '-W', 'ignore', '-m', 'unittest', 'test_nat031.CkptHost', 'test_nat031.CkptMarker', 'test_nat031.KernelChain'],
                           cwd=HERE, env={**os.environ, 'NAT031_SRC': str(d)}, capture_output=True, text=True)
        fails = [l.split()[1] for l in r.stderr.splitlines() if l.startswith(('FAIL:', 'ERROR:'))]
        survived += not r.returncode
        print(i, 'KILLED' if r.returncode else 'SURVIVED', name, fails[:6], flush=True)
print('done', len(M) if not only else len(only), 'mutations,', survived, 'survived')
sys.exit(1 if survived else 0)
