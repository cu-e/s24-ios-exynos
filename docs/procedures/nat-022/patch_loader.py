#!/usr/bin/env python3
"""Derive an instrumented copy of the NAT-020 build-003 loader source.

Host only. usage: patch_loader.py SOURCE_ROOT [--trig-hold] (a copy of build-003/source,
already NAT-010-patched). It replaces the silent M/C/EL halts with marker-then-halt and
adds stage markers. UI code is left unchanged; each mk_stage redraws every band,
so partially repainted UI cannot corrupt a marker. Every anchor must match once.

--trig-hold (loader-diag-trig, built with MK_TRIG=1 MK_LOADER=1 MK_HOLD=1): additionally
marks loader_main entry and the start of the full-window cache clean, reports every fail()
and invalid-FDT return with a held STAGE frame (code = mk_hash16 of the message), draws on
the fixed marker region even if the loader's own framebuffer differs, reports loader
exceptions unconditionally, and replaces the jump into the kernel copy by mk_hold(): this
variant NEVER executes the payload.

--adt-aligned (NAT-027): additionally rewrites adt_patch.c so that every 64-bit ADT property access is
two aligned 32-bit accesses (run 005 took an alignment fault in adt_set_dram: the loader runs with the
MMU off and ADT values are only 4-byte aligned). Anchored on the base adt_patch.c hash.

--xnu-entry (NAT-028, requires --trig-hold): turns the PRE_JUMP hold into a real jump whose target is
a stub the loader installs over the first words of the kernel copy's entry point (xnu_entry.c,
xnu_stub.S). The stub only calls mk_xnu_entry_hold(), which draws STAGE 0x50 and holds; the kernel's
own first instruction is overwritten and never executed. The installer runs before the full-window
cache clean so the clean covers the patched words, and fails (marker, no jump) unless the words it
overwrites are NOP padding inside the file-backed part of the entry's segment.
"""
from pathlib import Path
import hashlib, sys

START_SHA = '4a5e1929d31254b5691ee4ad09a544ec48a4c5d242bd6d8e0ad6bfd395fd15f4'
LOADER_SHA = '036e1c951955b6f2d692c8796fa9d335ab8c16e15df21ad261f6bb02e49bc9e8'
ADT_PATCH_SHA = '415bf5c0cbb99dfa74f0ecaf1338a85ffc1a1e371ef5f27b9a39b52eba63166e'

def once(s, old, new):
    assert s.count(old) == 1, 'anchor mismatch: ' + old[:80]
    return s.replace(old, new, 1)

def main(root, trig_hold=False, adt_aligned=False, xnu_entry=False):
    assert not xnu_entry or trig_hold, '--xnu-entry requires --trig-hold'
    src = Path(root) / 'shim/e1s-xnu'
    p = src / 'start.S'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == START_SHA, 'start.S base changed'
    s = p.read_text()
    s = once(s, '''	msr	daifset, #0xf
	mov	x19, x0			/* S-Boot DTB */
	mrs	x20, CurrentEL
	cmp	x20, #0x8
	b.eq	from_el2
	cmp	x20, #0x4
	b.ne	halt
	b	el1_entry
''', '''	msr	daifset, #0xf
	mov	x19, x0			/* S-Boot DTB */
	/* NAT-022: draw an entry marker before any decision. Unlike the original
	 * silent halt, M/C/EL problems below are reported on the framebuffer. */
	msr	spsel, #1
	adr	x1, _stack_top
	mov	sp, x1
	adr	x0, _head
	adr	x1, _end
	mov	x2, x19
	bl	mk_fb_safe
	cbz	x0, halt		/* marker region overlaps image or DTB: stay silent */
	mrs	x20, CurrentEL
	mrs	x22, sctlr_el1
	mov	x21, x22
	cmp	x20, #8
	b.ne	1f
	mrs	x21, sctlr_el2
1:	mov	x0, x20
	mov	x1, x21
	mov	x2, x22
	bl	mk_entry_frame
	cmp	x20, #0x8
	b.eq	from_el2
	cmp	x20, #0x4
	b.ne	gate_el
	b	el1_entry

gate_el:
	mov	x0, #3			/* MK_ST_GATE_EL */
	mov	x1, x20
	mov	x2, x21
	mov	x3, x22
	bl	mk_gate_halt
''')
    s = once(s, '''	mrs	x1, sctlr_el1
	tbnz	x1, #0, halt
	tbnz	x1, #2, halt
''', '''	mrs	x1, sctlr_el1
	tbnz	x1, #0, gate_mc
	tbnz	x1, #2, gate_mc
''')
    s = once(s, '''	.globl halt
halt:''', '''gate_mc:
	mov	x0, #2			/* MK_ST_GATE_MC */
	mov	x2, x1
	mov	x3, x1
	mov	x1, #4			/* EL1 (raw CurrentEL encoding) */
	bl	mk_gate_halt

	.globl halt
halt:''')
    p.write_text(s)

    p = src / 'loader.c'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == LOADER_SHA, 'loader.c base changed'
    s = p.read_text()
    s = once(s, 'static struct ui_fb ui;', '''#include "marker.h"
/* Draw only on the validated framebuffer: elsewhere the fixed marker region could
 * lie inside the XNU RAM window and corrupt copied kernel segments. */
#define NAT022_STAGE(st) do { if (fb_base == MK_FB_BASE && \\
	fb_size >= MK_BANDS * MK_BAND_BYTES) mk_stage(st); } while (0)
static struct ui_fb ui;''')
    s = once(s, '\tdiagnostic_value("loader_main_enter",dtb);', '\tdiagnostic_value("loader_main_enter",dtb);')
    s = once(s, '''	ui_set_stage(&ui, UI_STAGE_FB, have_fb ? UI_OK : UI_WARN);
	fb_flush();
''', '''	ui_set_stage(&ui, UI_STAGE_FB, have_fb ? UI_OK : UI_WARN);
	fb_flush();
	NAT022_STAGE(MK_ST_LOADER_FB);
''')
    s = once(s, '''	ui_set_stage(&ui, UI_STAGE_RAM, UI_OK);
	fb_flush();
''', '''	ui_set_stage(&ui, UI_STAGE_RAM, UI_OK);
	fb_flush();
	NAT022_STAGE(MK_ST_LOADER_MEM);
''')
    s = once(s, '\tlog_str("zeroed\\n");\n', '\tlog_str("zeroed\\n");\n\tNAT022_STAGE(MK_ST_LOADER_ZERO);\n')
    s = once(s, '\tui_set_stage(&ui, UI_STAGE_COPY, UI_OK);\n', '\tui_set_stage(&ui, UI_STAGE_COPY, UI_OK);\n\tNAT022_STAGE(MK_ST_LOADER_COPY);\n')
    s = once(s, '''	clean(adt_pa, ba_pa + PAGE_16K);
	ui_set_stage(&ui, UI_STAGE_ADT, UI_OK);
''', '''	clean(adt_pa, ba_pa + PAGE_16K);
	ui_set_stage(&ui, UI_STAGE_ADT, UI_OK);
	NAT022_STAGE(MK_ST_LOADER_ADT);
''')
    s = once(s, '\tdiagnostic_value("return_entry_to_assembly",entry_pa);\n', '\tNAT022_STAGE(MK_ST_PRE_JUMP); /* last marker before BR: not proof of kernel entry */\n\tdiagnostic_value("return_entry_to_assembly",entry_pa);\n')
    s = once(s, '''	__asm__ volatile("mrs %0, far_el1" : "=r"(far));
	log_str("\\nEXCEPTION slot=");''', '''	__asm__ volatile("mrs %0, far_el1" : "=r"(far));
	if (fb_base == MK_FB_BASE && fb_size >= MK_BANDS * MK_BAND_BYTES)
		mk_exception_loop((uint32_t)slot, esr, elr, far);
	log_str("\\nEXCEPTION slot=");''')
    if trig_hold:
        # The kernel copy is never entered, so a marker landing in the XNU window cannot corrupt a
        # running kernel; the loader's own framebuffer is not required to be at the marker region.
        s = once(s, '''#define NAT022_STAGE(st) do { if (fb_base == MK_FB_BASE && \\
	fb_size >= MK_BANDS * MK_BAND_BYTES) mk_stage(st); } while (0)''', '''#define NAT022_STAGE(st) mk_stage(st)
#define NAT022_HOLD(st, code) mk_hold((st), (code))''')
        s = once(s, '\tdiagnostic_value("loader_main_enter",dtb);\n',
                 '\tdiagnostic_value("loader_main_enter",dtb);\n\tNAT022_STAGE(MK_ST_LOADER_MAIN);\n')
        s = once(s, '\t\tdiagnostic_value("invalid_fdt",dtb);\n',
                 '\t\tdiagnostic_value("invalid_fdt",dtb);\n\t\tNAT022_HOLD(MK_ST_LOADER_FAIL, 0xfd7d);\n')
        s = once(s, '''		ui_fail(&ui, why);
		fb_flush();
	}
	return 0;''', '''		ui_fail(&ui, why);
		fb_flush();
	}
	NAT022_HOLD(MK_ST_LOADER_FAIL, mk_hash16(why));
	return 0;''')
        s = once(s, '\tdiagnostic_value("clean_full_window_begin",win_base);\n',
                 '\tNAT022_STAGE(MK_ST_LOADER_CLEAN);\n\tdiagnostic_value("clean_full_window_begin",win_base);\n')
        s = once(s, '\tNAT022_STAGE(MK_ST_PRE_JUMP); /* last marker before BR: not proof of kernel entry */\n',
                 '\tNAT022_STAGE(MK_ST_PRE_JUMP); /* last marker before BR: not proof of kernel entry */\n'
                 '\tNAT022_HOLD(MK_ST_PRE_JUMP, 0); /* loader-diag-trig: never jump */\n')
        s = once(s, '''	if (fb_base == MK_FB_BASE && fb_size >= MK_BANDS * MK_BAND_BYTES)
		mk_exception_loop((uint32_t)slot, esr, elr, far);''', '''	mk_exception_loop((uint32_t)slot, esr, elr, far);''')
    if xnu_entry:
        # _stack_top is a local label of start.S; the stub's stack literal needs its address.
        sp = src / 'start.S'
        t = once(sp.read_text(), '_stack_top:\n\t.space 0x4000\n', '\t.globl _stack_top\n_stack_top:\n\t.space 0x4000\n')
        sp.write_text(t)
        s = once(s, '#include "marker.h"\n', '#include "marker.h"\n#include "xnu_entry.h"\n')
        s = once(s, '\tNAT022_HOLD(MK_ST_PRE_JUMP, 0); /* loader-diag-trig: never jump */\n',
                 '\t/* loader-diag-xnu-entry: no hold here; start.S jumps and the installed stub reports from the entry */\n')
        s = once(s, '\tNAT022_STAGE(MK_ST_LOADER_CLEAN);\n', '''\t{
\t\textern char _stack_top[];
\t\tuint32_t stub_orig0 = 0;
\t\tuint64_t stub_room = nat028_entry_room(&p->segs[0], p->nsegs, p->entry_va);

\t\tif (nat028_install_stub(entry_pa, stub_room, (uint64_t)(uintptr_t)_stack_top,
\t\t    (uint64_t)(uintptr_t)mk_xnu_entry_hold, &stub_orig0))
\t\t\treturn fail("XNU entry stub install failed");
\t\tlog_kv("\\nentry_word_orig", stub_orig0);
\t}
\tNAT022_STAGE(MK_ST_LOADER_CLEAN);
''')
    p.write_text(s)
    if adt_aligned:
        patch_adt_aligned(src)

def patch_adt_aligned(src):
    """NAT-027: make every 64-bit ADT property access two aligned 32-bit accesses.

    Run 005 (loader-diag-trig-hold-adt8) took a data abort at adt_set_dram+0x268 (ESR EC 0x25, DFSC 0x21
    alignment fault, FAR = ADT base + 1020 = the value of `dram-size`): ADT property values start at
    node offset + 36, so they are only 4-byte aligned, and the loader runs with the MMU off (all data
    accesses are Device memory and must be naturally aligned). Every property offset is a multiple of 4
    (node header 8, property header 36, value length rounded up to 4), so 32-bit accesses are always
    aligned. The ADT is little-endian on this target; the halves are stored low word first."""
    p = src / 'adt_patch.c'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == ADT_PATCH_SHA, 'adt_patch.c base changed'
    s = p.read_text()
    s = once(s, '''static int rd32(uintptr_t base, uint64_t size, uint32_t off, uint32_t *v)''', '''/* ADT property values are 4-byte aligned only; the MMU is off, so 64-bit accesses would fault. */
static inline uint64_t adt_ld64(uintptr_t a)
{
	return (uint64_t)*(const volatile uint32_t *)a |
	    ((uint64_t)*(const volatile uint32_t *)(a + 4) << 32);
}

static inline void adt_st64(uintptr_t a, uint64_t v)
{
	*(volatile uint32_t *)a = (uint32_t)v;
	*(volatile uint32_t *)(a + 4) = (uint32_t)(v >> 32);
}

static int rd32(uintptr_t base, uint64_t size, uint32_t off, uint32_t *v)''')
    s = once(s, '*(volatile uint64_t *)(adt + off + 36) = value;', 'adt_st64(adt + off + 36, value);')
    s = once(s, '*(volatile uint64_t *)(adt + off + 36) = base;', 'adt_st64(adt + off + 36, base);')
    s = once(s, '*(volatile uint64_t *)(adt + off + 44) = pram_size;', 'adt_st64(adt + off + 44, pram_size);')
    s = once(s, 'phys = *(const volatile uint64_t *)(adt + off + 36);', 'phys = adt_ld64(adt + off + 36);')
    s = once(s, '''*(volatile uint64_t *)(adt + off + 36) =
			    phys + (uint64_t)delta;''', 'adt_st64(adt + off + 36, phys + (uint64_t)delta);')
    assert 'uint64_t *)' not in s.replace('(uint64_t)', ''), 'a 64-bit pointer access remains'
    p.write_text(s)

if __name__ == '__main__':
    main(sys.argv[1], '--trig-hold' in sys.argv[2:], '--adt-aligned' in sys.argv[2:], '--xnu-entry' in sys.argv[2:])
