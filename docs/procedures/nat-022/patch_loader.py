#!/usr/bin/env python3
"""Derive an instrumented copy of the NAT-020 build-003 loader source.

Host only. usage: patch_loader.py SOURCE_ROOT (a copy of build-003/source, already
NAT-010-patched). It replaces the silent M/C/EL halts with marker-then-halt and
adds stage markers. UI code is left unchanged; each mk_stage redraws every band,
so partially repainted UI cannot corrupt a marker. Every anchor must match once.
"""
from pathlib import Path
import hashlib, sys

START_SHA = '4a5e1929d31254b5691ee4ad09a544ec48a4c5d242bd6d8e0ad6bfd395fd15f4'
LOADER_SHA = '036e1c951955b6f2d692c8796fa9d335ab8c16e15df21ad261f6bb02e49bc9e8'

def once(s, old, new):
    assert s.count(old) == 1, 'anchor mismatch: ' + old[:80]
    return s.replace(old, new, 1)

def main(root):
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
    p.write_text(s)

if __name__ == '__main__':
    main(sys.argv[1])
