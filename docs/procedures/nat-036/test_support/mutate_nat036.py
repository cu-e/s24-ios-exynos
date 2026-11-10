#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-036 mutation check: copies src/ to a temporary directory, applies ONE textual mutation to ckpt3.h, ckpt3.c,
ckpt3_stub.S, marker3.h or markerlib3.c, runs the Words / Ckpt3Host / Ckpt3Marker / C3Chain classes of test_nat036.py against
that copy (NAT036_SRC) and reports whether any test failed (KILLED) or none did (SURVIVED). Run it with a Python that has
capstone and unicorn (the NAT-033/035 scratch virtualenv) so the C3Chain tests are not skipped (a skipped test cannot kill a mutation):

    <venv>/bin/python docs/procedures/nat-036/test_support/mutate_nat036.py [index ...]

Exit status 1 if any mutation survives. What the model cannot see (caches, barriers, the TLB) is not mutated; for it the text of
the unmodified source is asserted at the end instead (the documented instruction order). Checks that are redundant by an invariant
of the code around them (for example the upper bound on the list length, which the 18-entry order table already enforces) are not
mutated either.
Nothing here touches the phone."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
PY = sys.executable

# (name, file, old, new)
M = [
 # --- the list
 ("list: duplicates and reordering allowed", "ckpt3.c", "\t\tpos++;\n\t}\n\treturn 1;", "\t}\n\treturn 1;"),
 ("list: NULL accepted", "ckpt3.c", "if (!stops || n < 1 || n > NAT036_MAX_STOPS)", "if (n < 1 || n > NAT036_MAX_STOPS)"),
 ("list: empty accepted", "ckpt3.c", "if (!stops || n < 1 || n > NAT036_MAX_STOPS)", "if (!stops || n > NAT036_MAX_STOPS)"),
 ("list: checkpoint 17 and later accepted", "ckpt3.h", "#define NAT036_ORDER_LEN\t18u", "#define NAT036_ORDER_LEN\t19u"),
 ("order table: 12 before 35", "ckpt3.c", "10, 11, 30, 31, 32, 33, 34, 35, 12, 40,", "10, 11, 30, 31, 32, 33, 34, 12, 35, 40,"),
 # --- install checks
 ("check: 4 MiB blocks instead of 2", "ckpt3.c", "(stub_pa >> 21) != ((stub_end_pa - 1) >> 21)", "(stub_pa >> 22) != ((stub_end_pa - 1) >> 22)"),
 ("check: loader_jump words not compared", "ckpt3.c", "if (!words_ok(win_base + (uintptr_t)(NAT036_JUMP_VA - virt_base), nat036_jump_words, NAT036_JUMP_WORDS))", "if (0)"),
 ("check: loader_jump last word not compared", "ckpt3.c", "rd32(pa + 4 * i) != w[i]", "(rd32(pa + 4 * i) != w[i] && i + 1 < n)"),
 ("check: _set_mmu_ttb not compared", "ckpt3.c", "if (!words_ok(win_base + (uintptr_t)(NAT036_SETTTB_VA - virt_base), nat036_setttb_words, NAT036_SETTTB_WORDS))", "if (0)"),
 ("check: flag byte not read", "ckpt3.c", "rd8(win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base)) != 0", "0"),
 ("check: the NAT-031 checks skipped", "ckpt3.c", "int rc = nat031_check(win_base, virt_base, bad);", "int rc = 0;"),
 ("prepare: flag PA off by one", "ckpt3.c", "st->flag_pa = win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base);", "st->flag_pa = win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base) + 1;"),
 ("prepare: slot filled when a check failed", "ckpt3.c", "\tif (rc)\n\t\treturn rc;\n\tst->stops = stops;", "\tst->stops = stops;"),
 ("words: loader_jump table changed", "ckpt3.c", "0xd10103ff, 0xa9037bfd,", "0xd10103fe, 0xa9037bfd,"),
 ("header: epilogue offset", "ckpt3.h", "#define NAT036_JUMP_EPILOGUE\t0x4cu", "#define NAT036_JUMP_EPILOGUE\t0x48u"),
 ("header: _set_mmu_ttb address", "ckpt3.h", "0xfffffff0074428bcULL", "0xfffffff0074428b8ULL"),
 ("header: flag address", "ckpt3.h", "0xfffffff007d77009ULL", "0xfffffff007d77008ULL"),
 # --- the decisions
 ("cp5: accepted with the MMU on", "ckpt3.c", "st->s.expect == 5 && !(sctlr & 1)) {", "st->s.expect == 5) {"),
 ("cp5: TTBR0 not validated", "ckpt3.c", "if (!ttbr0_ok(ttbr0)) {", "if (0) {"),
 ("cp5: TTBR0 zero accepted", "ckpt3.c", "return (t & 0x0000fffffffff000ULL) != 0 && (t & 0xffeULL) == 0;", "return (t & 0xffeULL) == 0;"),
 ("cp5: stray low bits accepted", "ckpt3.c", "return (t & 0x0000fffffffff000ULL) != 0 && (t & 0xffeULL) == 0;", "return (t & 0x0000fffffffff000ULL) != 0;"),
 ("cp5: TTBR0 not kept", "ckpt3.c", "\t\tst->kernel_ttbr0 = ttbr0;\n", ""),
 ("cp5: first C stop not stored", "ckpt3.c", "d->next = st->stops[0];\n\t\td->resume_pa", "d->next = 11;\n\t\td->resume_pa"),
 ("cp5: expectation not advanced", "ckpt3.c", "\t\tst->idx = 0;\n\t\tst->s.expect = st->stops[0];\n", "\t\tst->idx = 0;\n"),
 ("cp5: resume 4 bytes early", "ckpt2.h", "#define NAT034_RESUME_BACK\t28u", "#define NAT034_RESUME_BACK\t24u"),
 ("C stop: accepted with the MMU off", "ckpt3.c", "if (!(sctlr & 1)) {\t\t\t/* a C stop always arrives", "if (0) {\t\t\t/* a C stop always arrives"),
 ("C stop: bad state not flagged", "ckpt3.c", "\t\t\tst->s.mask |= NAT036_MASK_BAD_STATE;\n\t\t\treturn;", "\t\t\treturn;"),
 ("C stop: last stop resumed", "ckpt3.c", "if (st->idx + 1 < st->nstops) {", "if (st->idx < st->nstops) {"),
 ("C stop: index not advanced", "ckpt3.c", "\t\t\tst->idx++;\n", ""),
 ("C stop: next not stored", "ckpt3.c", "d->next = st->stops[st->idx];", "d->next = st->stops[0];"),
 ("C stop: last checkpoint not recorded", "ckpt3.c", "\t\tst->last = (uint32_t)x3;\n\t\tif (!(sctlr & 1))", "\t\tif (!(sctlr & 1))"),
 ("C stop: final not flagged", "ckpt3.c", "\t\tst->s.mask |= NAT036_MASK_FINAL;\n", ""),
 ("C stop: final bit is bit 12", "ckpt3.h", "#define NAT036_MASK_FINAL\t(1u << 13)", "#define NAT036_MASK_FINAL\t(1u << 12)"),
 ("C stop: counts no arrival", "ckpt3.c", "\t\t/* the C stop the kernel was set up to reach */\n\t\tst->s.arrivals++;\n", "\t\t/* the C stop the kernel was set up to reach */\n"),
 ("assembly stop: last not recorded", "ckpt3.c", "\t\tst->last = (uint32_t)x3;\n\t\td->action = NAT036_RESUME_ASM;", "\t\td->action = NAT036_RESUME_ASM;"),
 ("assembly stop: next off by one", "ckpt3.c", "\t\td->next = d31.next;", "\t\td->next = d31.next + 1;"),
 # --- the stores
 ("set_next: slot value off by one", "ckpt3.c", "st64(st->slot_pa + 16, next);", "st64(st->slot_pa + 16, next + 1);"),
 ("set_next: wrong word", "ckpt3.c", "st64(st->slot_pa + 16, next);", "st64(st->slot_pa + 8, next);"),
 ("clear_flag: sets the flag", "ckpt3.c", "*(volatile uint8_t *)(uintptr_t)flag_pa = 0;", "*(volatile uint8_t *)(uintptr_t)flag_pa = 1;"),
 ("clear_flag: wrong byte", "ckpt3.c", "*(volatile uint8_t *)(uintptr_t)flag_pa = 0;", "*(volatile uint8_t *)(uintptr_t)(flag_pa + 1) = 0;"),
 # --- the C entry
 ("C entry: flag not cleared", "ckpt3.c", "\tif (d.action == NAT036_RESUME_C)\n\t\tnat036_clear_flag(nat036_st.flag_pa);\n", ""),
 ("C entry: slot not stored for a C resume", "ckpt3.c", "\t\tnat036_set_next(&nat036_st.s, d.next);\t\t/* from checkpoint 5 on", "\t\t(void)0;\t\t/* from checkpoint 5 on"),
 ("C entry: TTBR0 not passed to the stub", "ckpt3.c", "nat036_cres.ttbr0 = nat036_st.kernel_ttbr0;", "nat036_cres.ttbr0 = 0;"),
 ("C entry: assembly mode for a C resume", "ckpt3.c", "\t\tret.mode = 1;", "\t\tret.mode = 0;"),
 ("C entry: pass skipped", "ckpt3.c", "\tmk_ckpt3_pass(&r);\n", ""),
 ("C entry: hold skipped", "ckpt3.c", "\tif (d.action == NAT036_HOLD)\n\t\tmk_ckpt3_hold(&r);\n", ""),
 ("C entry: SCTLR from the x10 slot", "ckpt3.c", "r->sctlr = f->x[11];", "r->sctlr = f->x[10];"),
 ("C entry: TTBR0 read after the stub's table change is not the kernel's", "ckpt3.c", "nat036_decide(&nat036_st, f->x[2], f->x[3], f->x[11], ttbr0, &d);", "nat036_decide(&nat036_st, f->x[2], f->x[3], f->x[11], ttbr1, &d);"),
 ("report: SP taken from x9", "ckpt3.c", "r->sp = f->sp;", "r->sp = f->x[9];"),
 ("report: x0 taken from x1", "ckpt3.c", "r->x0 = f->x[0];", "r->x0 = f->x[1];"),
 ("report: kernel TTBR0 not shown", "ckpt3.c", "r->kttbr0 = st->kernel_ttbr0;", "r->kttbr0 = 0;"),
 ("report: arrivals not shown", "ckpt3.c", "r->arrivals = st->s.arrivals;", "r->arrivals = 0;"),
 ("report: last not shown", "ckpt3.c", "r->last = st->last;", "r->last = 0;"),
 ("report: list length not shown", "ckpt3.c", "r->nstops = st->nstops;", "r->nstops = 0;"),
 ("report: ESR from x4", "ckpt3.c", "r->esr = f->x[3];", "r->esr = f->x[4];"),
 # --- the stub
 ("stub: prologue polarity", "ckpt3_stub.S", "tbz\tw11, #0, 1f", "tbnz\tw11, #0, 1f"),
 ("stub: prologue keeps C set", "ckpt3_stub.S", "mov\tx10, #5", "mov\tx10, #1"),
 ("stub: frame smaller", "ckpt3_stub.S", "sub\tx10, x10, #0x100", "sub\tx10, x10, #0xf0"),
 ("stub: mode test inverted", "ckpt3_stub.S", "cbnz\tx1, 2f", "cbz\tx1, 2f"),
 ("stub C tail: block pointer from x1", "ckpt3_stub.S", "2:\n\t/* C resume. All loads from the frame and from the cres block are done here, MMU off. */\n\tmov\tx9, x0", "2:\n\t/* C resume. All loads from the frame and from the cres block are done here, MMU off. */\n\tmov\tx9, x1"),
 ("stub C tail: x18/x19 from the x16 slot", "ckpt3_stub.S", "\tldp\tx18, x19, [sp, #144]\n\tldp\tx20, x21, [sp, #160]\n\tldp\tx22, x23, [sp, #176]\n\tldp\tx24, x25, [sp, #192]\n\tldp\tx26, x27, [sp, #208]\n\tldr\tx28, [sp, #224]\n\tldr\tx11", "\tldp\tx18, x19, [sp, #128]\n\tldp\tx20, x21, [sp, #160]\n\tldp\tx22, x23, [sp, #176]\n\tldp\tx24, x25, [sp, #192]\n\tldp\tx26, x27, [sp, #208]\n\tldr\tx28, [sp, #224]\n\tldr\tx11"),
 ("stub C tail: x28 from the x27 slot", "ckpt3_stub.S", "ldr\tx28, [sp, #224]", "ldr\tx28, [sp, #216]"),
 ("stub C tail: SCTLR from the x10 slot", "ckpt3_stub.S", "ldr\tx11, [sp, #88]", "ldr\tx11, [sp, #80]"),
 ("stub C tail: SP from x9's slot", "ckpt3_stub.S", "ldr\tx10, [sp, #248]\t\t\t/* the kernel's SP */", "ldr\tx10, [sp, #64]\t\t\t/* the kernel's SP */"),
 ("stub C tail: x30 and x0 swapped", "ckpt3_stub.S", "ldp\tx0, x30, [x9]", "ldp\tx30, x0, [x9]"),
 ("stub C tail: gadget from the x30 word", "ckpt3_stub.S", "ldr\tx12, [x9, #16]", "ldr\tx12, [x9, #8]"),
 ("stub C tail: SCTLR written from x10", "ckpt3_stub.S", "msr\tsctlr_el1, x11\n\tisb\n\tbr\tx12", "msr\tsctlr_el1, x10\n\tisb\n\tbr\tx12"),
 ("stub C tail: branch to x30", "ckpt3_stub.S", "br\tx12", "br\tx30"),
 # --- the report frames
 ("frames: pass shows last only", "markerlib3.c", "return (r->arrivals & 0xffu) << 8 | (r->last & 0xffu);", "return (r->last & 0xffu);"),
 ("frames: pass shows arrivals only", "markerlib3.c", "return (r->arrivals & 0xffu) << 8 | (r->last & 0xffu);", "return (r->arrivals & 0xffu) << 8;"),
 ("frames: SP high half shows x0", "markerlib3.c", "MK_C3_SP_2, c3_x(r->sp, 32)", "MK_C3_SP_2, c3_x(r->x0, 32)"),
 ("frames: SP low half shifted", "markerlib3.c", "MK_C3_SP_0, c3_x(r->sp, 0)", "MK_C3_SP_0, c3_x(r->sp, 4)"),
 ("frames: kernel TTBR0 shows TTBR1", "markerlib3.c", "MK_C3_KTTBR0_1, c3_x(r->kttbr0, 16)", "MK_C3_KTTBR0_1, c3_x(r->ttbr1, 16)"),
 ("frames: x1 high half shows low half", "markerlib3.c", "MK_C3_X1_HI, c3_x(r->x1, 16)", "MK_C3_X1_HI, c3_x(r->x1, 0)"),
 ("frames: x0 middle shows low", "markerlib3.c", "MK_C3_X0_1, c3_x(r->x0, 16)", "MK_C3_X0_1, c3_x(r->x0, 0)"),
 ("frames: list length not shown", "markerlib3.c", "MK_C3_LIST, r->nstops", "MK_C3_LIST, 0"),
 ("frames: the exception report shows the register block", "markerlib3.c", "if ((r->x2 & 0xff) == 1) {", "if (0) {"),
 ("frames: the pass does not redraw in full", "markerlib3.c", "mk_draw(f, 0, 1);\t\t/* full redraw", "mk_draw(f, 0, 0);\t\t/* full redraw"),
 ("frames: the pass shows no dwell", "markerlib3.c", "\tmk_draw(f, 0, 1);\t\t/* full redraw: whatever was on the bands before is not trusted */\n\tld_after_draw();\n", "\tmk_draw(f, 0, 1);\t\t/* full redraw: whatever was on the bands before is not trusted */\n"),
 ("frames: the kind is 12", "marker3.h", "#define MK_CKPT3 13", "#define MK_CKPT3 12"),
 ("frames: PASS idx moved", "marker3.h", "MK_C3_PASS = 0,", "MK_C3_PASS = 14,"),
]

def run(name, f, a, b, d):
    """Applies the mutation to the copy d. ckpt2.h is NAT-022's: it is copied next to the others first, and the copy wins the include search."""
    target = d / f
    if not target.exists():
        shutil.copy(HERE.parent / "nat-022/src" / f, target)
    txt = target.read_text()
    assert txt.count(a) == 1, (name, txt.count(a))
    target.write_text(txt.replace(a, b))


only = sys.argv[1:]
survived = []
for i, (name, f, a, b) in enumerate(M):
    if only and str(i) not in only:
        continue
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "src"
        shutil.copytree(HERE / "src", d)
        run(name, f, a, b, d)
        env = {**os.environ, "NAT036_SRC": str(d)}
        classes = ["test_nat036.Words", "test_nat036.Ckpt3Host", "test_nat036.Ckpt3Marker", "test_nat036.C3Chain"]
        if f == "ckpt3_stub.S":
            classes.append("test_nat036.C3Controls")                  # the stub's own restore/prologue checks
        r = subprocess.run([PY, "-W", "ignore", "-m", "unittest", *classes],
                           cwd=HERE, env=env, capture_output=True, text=True)
        fails = [l.split()[1] for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
        if not r.returncode:
            survived.append(name)
        print(i, "KILLED" if r.returncode else "SURVIVED", name, fails[:4], flush=True)

src = (HERE / "src/ckpt3.c").read_text()
want = ['"dc civac, %0\\n\\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");\n#endif\n\tst64(st->slot_pa + 16, next);\n#ifndef NAT031_HOST\n\t__asm__ volatile("dsb sy\\n\\tdc civac, %0\\n\\tdsb sy"',
        '"dc civac, %0\\n\\tdsb sy" :: "r"(flag_pa) : "memory");\n#endif\n\t*(volatile uint8_t *)(uintptr_t)flag_pa = 0;\n#ifndef NAT031_HOST\n\t__asm__ volatile("dsb sy\\n\\tdc civac, %0\\n\\tdsb sy"',
        "if (d.action == NAT036_RESUME_ASM && d.next <= 5)\n\t\tnat031_set_next(&nat036_st.s, d.next);"]
stub = (HERE / "src/ckpt3_stub.S").read_text()
want_stub = "\tmov\tsp, x10\n\tdsb\tsy\n\ttlbi\tvmalle1\n\tdsb\tnsh\n\tisb\n\tmsr\tsctlr_el1, x11\n\tisb\n\tbr\tx12"
ok = all(w in src for w in want) and want_stub in stub
print("cache-maintenance order of the two stores, the 1..4 routing and the barrier sequence of the stub (text checks, not observable in the model):", "ok" if ok else "CHANGED")
print("done", len(only) if only else len(M), "mutations,", len(survived), "survived", survived)
sys.exit(1 if survived or not ok else 0)
