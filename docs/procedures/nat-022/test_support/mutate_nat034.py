#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-034 mutation check: copies src/ to a temporary directory, applies ONE textual mutation to ckpt2.h, ckpt2.c,
ckpt2_stub.S or markerlib.c, runs the Ckpt2Host/Ckpt2Marker/C11Chain classes of test_nat034.py against that copy
(NAT034_SRC) and reports whether any test failed (KILLED) or none did (SURVIVED). Run it with a Python that has capstone
and unicorn so the C11Chain tests are not skipped (a skipped test cannot kill a mutation):

    <venv>/bin/python docs/procedures/nat-022/test_support/mutate_nat034.py [index ...]

Exit status 1 if any mutation survives. The one mutation that cannot be killed on the host is listed separately: the order
of the cache-maintenance instructions in nat034_set_next is not observable in a model without caches (NAT-032 states
this); the check that it is still the documented order is a text assertion at the end. Nothing here touches the phone."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
PY = sys.executable
M = [
 ("resume lands 4 bytes early", "ckpt2.h", "#define NAT034_RESUME_BACK\t28u", "#define NAT034_RESUME_BACK\t24u"),
 ("resume lands at the macro itself", "ckpt2.h", "#define NAT034_RESUME_BACK\t28u", "#define NAT034_RESUME_BACK\t0u"),
 ("slot[2] after 5 stays 5", "ckpt2.c", "d->action = NAT031_RESUME;\n\t\td->next = NAT034_C11;", "d->action = NAT031_RESUME;\n\t\td->next = 5;"),
 ("the C stop is resumed", "ckpt2.c", "d->action = NAT031_HOLD;\n\t\td->next = NAT034_C11;", "d->action = NAT031_RESUME;\n\t\td->next = NAT034_C11;"),
 ("C stop mask bit is bit 10", "ckpt2.c", "st->mask |= NAT034_MASK_C11;", "st->mask |= 1u << 10;"),
 ("expectation stays 5 after the resume", "ckpt2.c", "st->expect = NAT034_C11;\n\t\td->action", "st->expect = 5;\n\t\td->action"),
 ("the C stop accepted before 5", "ckpt2.c", "x3 == NAT034_C11 && st->expect == NAT034_C11", "x3 == NAT034_C11"),
 ("5 accepted when not expected", "ckpt2.c", "x2 == 2 && x3 == 5 && st->expect == 5", "x2 == 2 && x3 == 5"),
 ("x2 not compared at 5", "ckpt2.c", "x2 == 2 && x3 == 5 && st->expect == 5", "x3 == 5 && st->expect == 5"),
 ("slot[2] value off by one", "ckpt2.c", "st64(st->slot_pa + 16, next);", "st64(st->slot_pa + 16, next + 1);"),
 ("SCTLR taken from x10", "ckpt2.c", "r.sctlr = f->x[11];", "r.sctlr = f->x[10];"),
 ("TTBR0 not read", "ckpt2.c", "__asm__ volatile(\"mrs %0, ttbr0_el1\" : \"=r\"(c.ttbr0));", "c.ttbr0 = 0;"),
 ("x5 taken from x4", "ckpt2.c", "c.x5 = f->x[5];", "c.x5 = f->x[4];"),
 ("x1 taken from x2", "ckpt2.c", "c.x1 = f->x[1];", "c.x1 = f->x[2];"),
 ("the C stop uses the plain hold", "ckpt2.c", "if (d.next == NAT034_C11)\n\t\tmk_ckpt2_hold(&r, &c);", "if (0)\n\t\tmk_ckpt2_hold(&r, &c);"),
 ("checkpoints 1..4 resume at the wrong word", "ckpt2.c", "nat031_set_next(&nat034_st, d.next);\t/* checkpoints 1..4: exactly as run 008 */", "nat031_set_next(&nat034_st, d.next + 1);"),
 ("prologue tests the wrong polarity", "ckpt2_stub.S", "tbz\tw11, #0, 1f", "tbnz\tw11, #0, 1f"),
 ("prologue keeps C set", "ckpt2_stub.S", "mov\tx10, #5", "mov\tx10, #1"),
 ("prologue writes nothing", "ckpt2_stub.S", "msr\tsctlr_el1, x10\n\tisb\n1:", "nop\n\tisb\n1:"),
 ("prologue does not keep the arrival SCTLR", "ckpt2_stub.S", "mrs\tx11, sctlr_el1", "mrs\tx11, ttbr0_el1"),
 ("stub keeps x9 as kernel sp", "ckpt2_stub.S", "mov\tx9, x0\t\t\t/* continuation */", "mov\tx9, x9\t\t\t/* continuation */"),
 ("stub frame smaller", "ckpt2_stub.S", "sub\tx10, x10, #0x100", "sub\tx10, x10, #0xf0"),
 ("x0 frames show x1", "markerlib.c", "mk_frame(MK_CKPT2, MK_C2_X0_0, c2_x(c->x0, 0))", "mk_frame(MK_CKPT2, MK_C2_X0_0, c2_x(c->x1, 0))"),
 ("TTBR0 frames show x5", "markerlib.c", "mk_frame(MK_CKPT2, MK_C2_TTBR0_1, c2_x(c->ttbr0, 16))", "mk_frame(MK_CKPT2, MK_C2_TTBR0_1, c2_x(c->x5, 16))"),
 ("x1 high half shows low half", "markerlib.c", "mk_frame(MK_CKPT2, MK_C2_X1_HI, c2_x(c->x1, 16))", "mk_frame(MK_CKPT2, MK_C2_X1_HI, c2_x(c->x1, 0))"),
 ("the arrival SCTLR low half shows TTBR1", "markerlib.c", "c2_x(c->ttbr0, 0)), &ld_k);\n\t\tshow(&prev, mk_frame(MK_CKPT, MK_CK_SCTLR_LO, (uint32_t)r->sctlr), &ld_k);", "c2_x(c->ttbr0, 0)), &ld_k);\n\t\tshow(&prev, mk_frame(MK_CKPT, MK_CK_SCTLR_LO, (uint32_t)r->ttbr1), &ld_k);"),
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
        r = subprocess.run([PY, '-W', 'ignore', '-m', 'unittest', 'test_nat034.Ckpt2Host', 'test_nat034.Ckpt2Marker', 'test_nat034.C11Chain'],
                           cwd=HERE, env={**os.environ, 'NAT034_SRC': str(d)}, capture_output=True, text=True)
        fails = [l.split()[1] for l in r.stderr.splitlines() if l.startswith(('FAIL:', 'ERROR:'))]
        survived += not r.returncode
        print(i, 'KILLED' if r.returncode else 'SURVIVED', name, fails[:6], flush=True)
src = (HERE / 'src/ckpt2.c').read_text()
want = '"dc civac, %0\\n\\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");\n#endif\n\tst64(st->slot_pa + 16, next);\n#ifndef NAT031_HOST\n\t__asm__ volatile("dsb sy\\n\\tdc civac, %0\\n\\tdsb sy"'
ok = want in src
print('cache-maintenance order in nat034_set_next (text check, not observable in the model):', 'ok' if ok else 'CHANGED')
survived += not ok
print('done', len(M) if not only else len(only), 'mutations,', survived, 'survived')
sys.exit(1 if survived else 0)
