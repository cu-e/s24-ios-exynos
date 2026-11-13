/* NAT-121 host harness: e1s_touch.c (as patched) compiled on the host; ml_io_map returns fake pages; every access is checked. */
#include "shim.h"
uint8_t fake_page[2][4096];
int host_steps = 3, host_bad, host_writes[2], host_irq_attached, host_maps;
static uintptr_t phys_of[2] = { 0x11030000u, 0x12850000u };

vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t size)
{
	for (int i = 0; i < 2; i++) if (pa == phys_of[i] && size == 0x1000) { host_maps++; return (vm_offset_t)fake_page[i]; }
	host_bad++; return 0;
}
int PE_parse_boot_argn(const char *n, void *v, int s)
{
	(void)s;
	if (!strcmp(n, "e1stouch_steps")) { *(uint32_t *)v = (uint32_t)host_steps; return 1; }
	if (!strcmp(n, "e1stouch_irq")) { *(uint32_t *)v = 1; return 1; }
	return 0;
}
kern_return_t gic_v3_spi_attach(uint32_t intid, bool edge, void (*h)(void *, uint32_t), void *c) { (void)intid; (void)edge; (void)h; (void)c; host_irq_attached++; return 0; }
void gic_v3_spi_mask(uint32_t i) { (void)i; }
void gic_v3_spi_unmask(uint32_t i) { (void)i; }
void redwood_touch_post(uint32_t type, uint32_t finger, uint32_t x, uint32_t y) { printf("post %u %u %u %u\n", type, finger, x, y); }
static int page_of(uintptr_t a) { for (int i = 0; i < 2; i++) if (a >= (uintptr_t)fake_page[i] && a + 4 <= (uintptr_t)fake_page[i] + 4096) return i; return -1; }
uint32_t host_rd(uintptr_t a) { if (page_of(a) < 0) { host_bad++; return 0; } return *(volatile uint32_t *)a; }
void host_wr(uintptr_t a, uint32_t v) { int p = page_of(a); if (p < 0) { host_bad++; return; } host_writes[p]++; *(volatile uint32_t *)a = v; }
