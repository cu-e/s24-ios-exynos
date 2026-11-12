/* NAT-077 host test driver: runs hash-probe.c (compiled with -DHOST_TEST) against file descriptor 3 as the "root device" and the standard
 * output as the "console". Options set the test hooks of hash-probe.c:
 *     host-main [read_limit [eintr_budget [fail_after [fake_step_us [backwards [write_limit]]]]]]
 * (every argument is a decimal number; 0 or a missing argument leaves the hook off; fail_after uses "none" for off).
 * At exit one line "HOSTSTAT ..." on stderr says how often each hook acted.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef ROOT_DEV
#define ROOT_DEV "/dev/fd/3"
#endif
#define CONSOLE_DEV "/dev/fd/1"
#include "hash-probe.c"

static void print_stats(void)
{
	fprintf(stderr, "HOSTSTAT reads=%lu eintr=%lu limited=%lu cut=%lu failed=%lu writes=%lu short_writes=%lu fake_clock=%lu real_clock=%lu\n",
		g_stat_reads, g_stat_eintr, g_stat_limited, g_stat_cut, g_stat_failed, g_stat_writes, g_stat_short_writes, g_stat_fake_clock,
		g_stat_real_clock);
}

int main(int argc, char **argv)
{
	atexit(print_stats);
	if (argc > 1)
		g_read_limit = strtoul(argv[1], 0, 10);
	if (argc > 2)
		g_eintr_budget = strtoul(argv[2], 0, 10);
	if (argc > 3 && strcmp(argv[3], "none"))
		g_fail_after = strtoull(argv[3], 0, 10);
	if (argc > 4)
		g_fake_step_us = strtoul(argv[4], 0, 10);
	if (argc > 5)
		g_clock_backwards = atoi(argv[5]);
	if (argc > 6)
		g_write_limit = strtoul(argv[6], 0, 10);
	return probe_main();
}
