/* SPDX-License-Identifier: GPL-2.0-only
 *
 * NAT-065 probe init: the project's stage-0 test /sbin/launchd (not Apple's launchd) reduced to a run that ENDS.
 *
 * Derived from tools/e1s/sweet-init.S of the pinned s24-port tree (artifacts/nat-020/build-003/source, base SHA-256 in build.json and
 * test_nat065.py; upstream licence GPL-2.0-only, see research/sources.json). Differences, all deliberate (docs/procedures/nat-064/README.md):
 *   - no console            -> exit(0x60) instead of hang (the kernel panics with "exit status 96": no console device)
 *   - the /dev/md1 mount and the 5 s heartbeat loop are gone (nothing to mount; a loop would end only through the untested timed return)
 *   - after the banner: select() sleep of 1 s (one user-mode timer measurement in the kernel's own log stamps), then
 *     exit(0x50 + getpid()): PID 1 ran to its end -> the kernel panics with "initproc failed to start -- no exit reason available --
 *     (signal 0, exit status 81 ...)". The panic is the path NAT-063 proved delivers the log to the host.
 */
#define SYS_exit	1
#define SYS_write	4
#define SYS_open	5
#define SYS_getpid	20
#define SYS_select	93
#define O_RDWR		2

	.text
	.globl	_start
	.p2align 2
_start:
	mov	x9, sp
	and	x9, x9, #~15
	mov	sp, x9

	adr	x0, path
	mov	x1, #O_RDWR
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	noconsole
	mov	x19, x0

	adr	x1, hello
	adr	x2, hello_tail
	sub	x2, x2, x1
	bl	write_console

	mov	x16, #SYS_getpid
	svc	#0x80
	mov	x20, x0			/* the PID, for the exit status */
	add	w0, w0, #'0'		/* PID 1 expected: one digit */
	sub	sp, sp, #16
	strb	w0, [sp]
	mov	x1, sp
	mov	x2, #1
	bl	write_console
	add	sp, sp, #16

	adr	x1, hello_tail
	adr	x2, hello_end
	sub	x2, x2, x1
	bl	write_console

	/* select(0, NULL, NULL, NULL, &1s) as a portable sleep */
	mov	x0, #0
	mov	x1, #0
	mov	x2, #0
	mov	x3, #0
	adr	x4, one_sec
	mov	x16, #SYS_select
	svc	#0x80

	adr	x1, done
	adr	x2, done_end
	sub	x2, x2, x1
	bl	write_console

	add	x0, x20, #0x50		/* exit status 0x50 + PID: 81 for PID 1 */
	mov	x16, #SYS_exit
	svc	#0x80
	b	hang

noconsole:
	mov	x0, #0x60		/* exit status 96: /dev/console could not be opened */
	mov	x16, #SYS_exit
	svc	#0x80
hang:
	b	hang

/* write(x19, x1, x2) */
write_console:
	mov	x0, x19
	mov	x16, #SYS_write
	svc	#0x80
	ret

	.p2align 3
one_sec:
	.quad	1			/* tv_sec */
	.quad	0			/* tv_usec (int32 + padding) */
path:
	.asciz	"/dev/console"
hello:
	.ascii	"\n*** SWEET userspace: init running as PID "
hello_tail:
	.ascii	" ***\n"
hello_end:
done:
	.ascii	"SWEET probe: done, exiting\n"
done_end:
