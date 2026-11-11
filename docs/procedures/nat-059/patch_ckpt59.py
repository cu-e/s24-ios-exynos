#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-059: derive the sources of loader-diag-xnu-ckpt4-usb: the NAT-052 image whose stub also stops and resumes the payload kernel
at C checkpoints 17..21, the five that follow arm_vm_init in arm_init.

  patch_ckpt59.py SOURCE_ROOT        (a tree already prepared by nat-052/build.py prepare_tree(final=True))

Rewrites SOURCE_ROOT/shim/e1s-xnu/ckpt3.c and ckpt3.h in place with exact-match hunks (each anchor must occur exactly once, or the
script fails before it writes anything). The NAT-036 and NAT-052 files are not touched.

Why the stub needs a change. The C resume gives the kernel back its own TTBR0 through the kernel's _set_mmu_ttb. Up to checkpoint 16 that
is the value the stub read at the checkpoint-5 stop (measured on the phone by NAT-058: 0x9e15ae000). arm_vm_init, which runs between
checkpoint 16 and checkpoint 17, ends with `set_mmu_ttb(*_invalid_ttep & 0xffffffffffff)` (payload bytes 0xfffffff007433b64..74, pinned by
this directory's test), so from checkpoint 17 on the kernel's TTBR0 is that table, not the cp5 one. The stub reads _invalid_ttep from the
kernel's data by physical address (MMU off, line cleaned and invalidated first, as the slot is) and uses it for the stops 17..21. Nothing
else about the resume changes: arm_vm_init's other writes (TCR_EL1 |= TBI0, TTBR1_EL1 = cpu_ttep) are not touched by the stub, and
loader_jump's own early-return epilogue is the same code at every stop.

Changes to ckpt3.h: the program-order table has 23 entries (..16, 17..21); NAT036_LAST_STOP is 21; the state gets the PA of _invalid_ttep;
a new check code for a kernel whose arm_vm_init is not the one analysed; the declaration of nat059_resume_ttbr0.
Changes to ckpt3.c: the table and the default list; the words of the arm_vm_init site; the check of those words when the list reaches a
stop after arm_vm_init (a list that stays at or below 16 does not read them); nat036_prepare records the PA of _invalid_ttep;
nat059_resume_ttbr0 (the rule: x3 in 17..21 -> _invalid_ttep, any other stop -> the cp5 value; the ids are not in numeric order); nat036_ckpt_c uses it for the resume and for the
`kttbr0` field of the stop note (so the note says which TTBR0 the stub gave back), and holds instead of resuming when the value is not a
plausible table base."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Pinned facts of the NAT-020 build-003 payload (disassembly of arm_init/arm_vm_init, NAT-059 README).
INVALID_TTEP_VA = 0xfffffff0071ac3e0
VMTTB_VA = 0xfffffff007433b64
VMTTB_WORDS = (0xb0ffebd3, 0x910f8273, 0xf9400268, 0x9240bd00, 0x94003b52)   # adrp x19; add x19,#0x3e0; ldr x8,[x19]; and x0,x8,#0xffffffffffff; bl _set_mmu_ttb
FIRST_POST_VM = 17
LAST_STOP = 21
STOPS = (11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21)

CKPT3_H = [
    ("doc", " * case holds. Stops after the kernel's arm_vm_init (checkpoint 17 on) are refused in the list: the kernel's TTBR0 changes\n"
     " * there and the stub only has the value from checkpoint 5.\n",
     " * case holds. Stops after the kernel's arm_vm_init (checkpoint 17 on) resume with the TTBR0 arm_vm_init installs\n"
     " * (_invalid_ttep, NAT-059); up to checkpoint 16 the value captured at checkpoint 5 is used.\n"),
    ("list-bad", "not in program order, or has a checkpoint after 16 */", "not in program order, or has a checkpoint after 21 */"),
    ("order-len", "#define NAT036_ORDER_LEN\t18u\n", "#define NAT036_ORDER_LEN\t23u\n"),
    ("last-stop", "#define NAT036_LAST_STOP\t16u\t/* the last checkpoint in program order before arm_vm_init */\n",
     "#define NAT036_LAST_STOP\t21u\t/* NAT-059: the last checkpoint of arm_init (machine_startup follows it) */\n"
     "#define NAT059_FIRST_POST_VM\t17u\t/* the first checkpoint after arm_vm_init */\n"
     "#define NAT059_POST_VM(cp)\t((cp) >= NAT059_FIRST_POST_VM && (cp) <= NAT036_LAST_STOP)\t/* the ids are not in numeric order (30..44 sit between 11 and 12): test the range */\n"
     "#define NAT059_TTEP_VA\t\t0x%xULL\t/* _invalid_ttep: arm_vm_init's last TTBR0 */\n"
     "#define NAT059_VMTTB_VA\t\t0x%xULL\t/* arm_vm_init: adrp/add/ldr/and/bl _set_mmu_ttb of _invalid_ttep */\n"
     "#define NAT059_VMTTB_WORDS\t5u\n"
     "#define NAT059_TTBR0_MASK\t0x0000ffffffffffffULL\t/* the kernel's `and x0, x8, #0xffffffffffff` */\n" % (INVALID_TTEP_VA, VMTTB_VA)),
    ("rc", "\tNAT036_FLAG_BAD = 7\t/* loader_return_entered is not zero in the kernel copy */\n",
     "\tNAT036_FLAG_BAD = 7,\t/* loader_return_entered is not zero in the kernel copy */\n"
     "\tNAT059_VMTTB_BAD = 8\t/* arm_vm_init is not the function NAT-059 analysed (only checked when the list has a stop after it) */\n"),
    ("state", "\tuint64_t flag_pa;\t/* PA of loader_return_entered */\n};\n",
     "\tuint64_t flag_pa;\t/* PA of loader_return_entered */\n\tuint64_t ttep_pa;\t/* NAT-059: PA of _invalid_ttep */\n};\n"),
    ("decl", "extern const uint32_t nat036_setttb_words[NAT036_SETTTB_WORDS];\n",
     "extern const uint32_t nat036_setttb_words[NAT036_SETTTB_WORDS];\nextern const uint32_t nat059_vmttb_words[NAT059_VMTTB_WORDS];\n"),
    ("resume-decl", "/* What the stub does for an arrival with (x2, x3), the arrival SCTLR_EL1 and the TTBR0_EL1 read on arrival. Updates st. */\n",
     "/* NAT-059: the TTBR0 the kernel has at C checkpoint `checkpoint`, to be written back when the stub resumes it. For a stop\n"
     " * outside 17..21 (NAT059_POST_VM) it is the value captured at checkpoint 5; for 17..21 it is _invalid_ttep & NAT059_TTBR0_MASK read\n"
     " * from the kernel's data by physical address (the line is cleaned and invalidated first when this runs in the loader).\n"
     " * Stores the value in *ttbr0 and returns 1 when it is a plausible table base, 0 when it is not (the stub then holds). */\n"
     "int nat059_resume_ttbr0(const struct nat036_state *st, uint32_t checkpoint, uint64_t *ttbr0);\n\n"
     "/* NAT-059: the part of nat036_ckpt_c that gives the TTBR0 back, so that the host tests run it. After nat036_decide: sets *rt to the\n"
     " * TTBR0 of this stop (0 when the stop neither resumes nor is the final one), and turns a C resume for which that value is not a\n"
     " * plausible table base into a hold with NAT036_MASK_BAD_TTBR0 set. */\n"
     "void nat059_resume_decision(struct nat036_state *st, struct nat036_decision *d, uint64_t x3, uint64_t *rt);\n\n"
     "/* What the stub does for an arrival with (x2, x3), the arrival SCTLR_EL1 and the TTBR0_EL1 read on arrival. Updates st. */\n"),
]

CKPT3_C = [
    ("order", "\t10, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16,\n",
     "\t10, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21,\n"),
    ("words", "const uint32_t nat036_setttb_words[NAT036_SETTTB_WORDS] = { 0xd5033b9f, 0xd5182000, 0xd5033fdf, 0xd65f03c0 };\n",
     "const uint32_t nat036_setttb_words[NAT036_SETTTB_WORDS] = { 0xd5033b9f, 0xd5182000, 0xd5033fdf, 0xd65f03c0 };\n\n"
     "/* arm_vm_init at 0xfffffff007433b64 of the NAT-020 build-003 payload: the load of _invalid_ttep (0xfffffff0071ac3e0) and the\n"
     " * _set_mmu_ttb call that installs it as TTBR0. The test re-derives this table from the payload bytes on every run. */\n"
     "const uint32_t nat059_vmttb_words[NAT059_VMTTB_WORDS] = { %s };\n" % ", ".join("0x%08x" % w for w in VMTTB_WORDS)),
    ("check", "\tif (rd8(win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base)) != 0)\n\t\treturn NAT036_FLAG_BAD;\n\treturn NAT036_OK;\n",
     "\tif (rd8(win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base)) != 0)\n\t\treturn NAT036_FLAG_BAD;\n"
     "\tif (NAT059_POST_VM(stops[nstops - 1]) &&\n"
     "\t    !words_ok(win_base + (uintptr_t)(NAT059_VMTTB_VA - virt_base), nat059_vmttb_words, NAT059_VMTTB_WORDS))\n"
     "\t\treturn NAT059_VMTTB_BAD;\n\treturn NAT036_OK;\n"),
    ("prepare", "\tst->flag_pa = win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base);\n",
     "\tst->flag_pa = win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base);\n\tst->ttep_pa = win_base + (uintptr_t)(NAT059_TTEP_VA - virt_base);\n"),
    ("resume", "void nat036_decide(struct nat036_state *st, uint64_t x2, uint64_t x3, uint64_t sctlr, uint64_t ttbr0, struct nat036_decision *d)\n{\n",
     "int nat059_resume_ttbr0(const struct nat036_state *st, uint32_t checkpoint, uint64_t *ttbr0)\n{\n"
     "\tuint64_t t;\n\n"
     "\tif (!NAT059_POST_VM(checkpoint)) {\n\t\tt = st->kernel_ttbr0;\n\t} else {\n"
     "#ifndef NAT031_HOST\n"
     "\t\t__asm__ volatile(\"dc civac, %0\\n\\tdsb sy\" :: \"r\"(st->ttep_pa) : \"memory\");\n"
     "#endif\n"
     "\t\tt = *(const volatile uint64_t *)(uintptr_t)st->ttep_pa & NAT059_TTBR0_MASK;\n\t}\n"
     "\t*ttbr0 = t;\n\treturn ttbr0_ok(t);\n}\n\n"
     "void nat059_resume_decision(struct nat036_state *st, struct nat036_decision *d, uint64_t x3, uint64_t *rt)\n{\n"
     "\tint ok;\n\n\t*rt = 0;\n\tif (d->action != NAT036_RESUME_C && !d->final)\n\t\treturn;\n"
     "\tok = nat059_resume_ttbr0(st, (uint32_t)x3, rt);\n"
     "\tif (d->action == NAT036_RESUME_C && !ok) {\t/* nothing plausible to give the kernel back: hold and say so */\n"
     "\t\tst->s.mask |= NAT036_MASK_BAD_TTBR0;\n\t\td->action = NAT036_HOLD;\n\t}\n}\n\n"
     "void nat036_decide(struct nat036_state *st, uint64_t x2, uint64_t x3, uint64_t sctlr, uint64_t ttbr0, struct nat036_decision *d)\n{\n"),
    ("default-list", "#define NAT036_STOP_LIST 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16\n",
     "#define NAT036_STOP_LIST 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16, 17, 18, 19, 20, 21\n"),
    ("msg", "\tcase NAT036_FLAG_BAD: return \"XNU return flag check failed\";\n",
     "\tcase NAT036_FLAG_BAD: return \"XNU return flag check failed\";\n\tcase NAT059_VMTTB_BAD: return \"XNU arm_vm_init check failed\";\n"),
    ("decl", "\tuint64_t ttbr0, ttbr1, tcr, vbar, kv;\n", "\tuint64_t ttbr0, ttbr1, tcr, vbar, kv, rt;\n"),
    ("report", "\tnat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);\n\tkv = nat052_vbar_enter();\n",
     "\tnat059_resume_decision(&nat036_st, &d, f->x[3], &rt);\n"
     "\tnat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);\n"
     "\tif (rt)\n\t\tr.kttbr0 = rt;\t\t/* the note shows the TTBR0 the stub gives back at this stop */\n"
     "\tkv = nat052_vbar_enter();\n"),
    ("cres", "\t\tnat036_cres.ttbr0 = nat036_st.kernel_ttbr0;\n", "\t\tnat036_cres.ttbr0 = rt;\n"),
]


def patch_text(label, text, hunks):
    for key, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{label}: anchor '{key}' occurs {n} times, expected exactly once")
        text = text.replace(old, new)
    return text


def derive(e):
    """{path: text} for ckpt3.c and ckpt3.h of the tree at e (= SOURCE_ROOT/shim/e1s-xnu); nothing is written here."""
    e = Path(e)
    return {
        e / "ckpt3.c": patch_text("ckpt3.c", (e / "ckpt3.c").read_text(), CKPT3_C),
        e / "ckpt3.h": patch_text("ckpt3.h", (e / "ckpt3.h").read_text(), CKPT3_H),
    }


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    out = derive(Path(argv[1]) / "shim" / "e1s-xnu")
    for p, t in out.items():
        p.write_text(t)
    print("wrote", ", ".join(p.name for p in out))


if __name__ == "__main__":
    main(sys.argv)
