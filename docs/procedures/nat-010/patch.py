#!/usr/bin/env python3
"""Apply fail-closed entry and full-window coherency to NAT-006 build-002 source."""
from pathlib import Path
import hashlib
import sys
src=Path(sys.argv[1])/'shim/e1s-xnu'
p=src/'start.S'; s=p.read_text()
assert hashlib.sha256(p.read_bytes()).hexdigest()=='787649bf31bb47f168eed8f72031b694d614e25a58da955fbe91112fe930f01f'
s=s.replace('el1_entry:\n', '''el1_entry:
	/* No incoming translation tables or physical identity witness are known.
	 * Reject M or C before stack/BSS/DTB/high-DRAM accesses. Never turn off
	 * a live incoming mapping while executing at an unproven VA. */
	mrs	x1, sctlr_el1
	tbnz	x1, #0, halt
	tbnz	x1, #2, halt
''')
s=s.replace('\tldr\tx0, boot_args_pa', '''	/* Persist loader globals (boot_args_pa) and stacks before cache-off.
	 * x16 holds entry; this loop performs no stores after its own clean. */
	adr	x1, _head
	adr	x2, _end
	mrs	x3, ctr_el0
	ubfx	x3, x3, #16, #4
	mov	x4, #4
	lsl	x4, x4, x3
	sub	x3, x4, #1
	bic	x1, x1, x3
4:	dc	civac, x1
	add	x1, x1, x4
	cmp	x1, x2
	b.lo	4b
	dsb	sy
	ldr	x0, boot_args_pa''')
s=s.replace('\tmsr\tsctlr_el1, x14','\tdsb\tsy\n\tmsr\tsctlr_el1, x14\n\tisb')
p.write_text(s)
p=src/'loader.c'; s=p.read_text()
assert hashlib.sha256(p.read_bytes()).hexdigest()=='961f15a2b5cc92ce0d0fa78fac207b90b37bfdab6e4827d8006fc021f4c9b276'
assert s.count('\thold_seconds(hold);')==1
s=s.replace('\thold_seconds(hold);','''	/* Includes untouched zero pages and gaps between Mach-O segments. */
	clean(win_base, mem_end);
	hold_seconds(hold);''')
p.write_text(s)
