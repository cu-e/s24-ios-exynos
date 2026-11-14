/* NAT-174 host harness for e1s_swipe_thread(): a simulated clock that delay_for_interval advances, every redwood_touch_post
 * printed with that clock, and the program ends at 400 s of simulated uptime. Synthetic. */
#include <stdlib.h>
#include "../../nat-121/host/shim.h"

uint8_t fake_page[2][4096];
int host_steps = 3, host_bad, host_writes[2], host_irq_attached;
uint64_t host_ns = 123000000000ULL;                 /* the event thread starts at ~123 s on the phone */

void host_delay(uint64_t n, uint64_t unit)
{
	host_ns += n * unit;
	if (host_ns > 400000000000ULL) {
		printf("RESULT end at %llu us\n", (unsigned long long)(host_ns / 1000));
		exit(0);
	}
}
uint32_t host_rd(uintptr_t a) { (void)a; return 0; }
void host_wr(uintptr_t a, uint32_t v) { (void)a; (void)v; }
vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t size) { (void)pa; (void)size; return (vm_offset_t)fake_page[0]; }
int PE_parse_boot_argn(const char *n, void *v, int s)
{
	(void)s;
	if (!strcmp(n, "e1stouch_swipe") && getenv("E1STOUCH_SWIPE")) { *(uint32_t *)v = (uint32_t)atoi(getenv("E1STOUCH_SWIPE")); return 1; }
	return 0;
}
int gic_v3_spi_attach(uint32_t i, bool e, void (*h)(void *, uint32_t), void *c) { (void)i; (void)e; (void)h; (void)c; return 0; }
void gic_v3_spi_mask(uint32_t i) { (void)i; }
void gic_v3_spi_unmask(uint32_t i) { (void)i; }
void redwood_touch_post(uint32_t type, uint32_t finger, uint32_t x, uint32_t y)
{
	printf("post %u %u %u %u at %llu\n", type, finger, x, y, (unsigned long long)(host_ns / 1000));
}
