/*
 * NAT-139 host peer: a pin-level synthetic SPI mode-0 target behind the fake GPP9 register page. It sees only what the driver's
 * own gpio_rd/gpio_wr do to GPP9 CON/DAT. It samples its MOSI pad on CLK rising edges while its CS pad is low and drives its MISO
 * pad, shifting on falling edges. A pad configured as an input that nobody drives reads 0 (pull NONE, modelled low; the peer's
 * own CS pad reads inactive high); a pad configured as an output reads its latch.
 *
 * The pads the peer is wired to are PEER_CLK/PEER_MOSI/PEER_MISO/PEER_CS (compile-time). Its answers are synthetic bytes, not an
 * STM's: frames beginning D1 return PEER_DEVID from byte 4, frames beginning FB return PEER_HWID from byte 6.
 * This is not electrical evidence.
 */
#include "../../nat-121/host/shim.h"

uint8_t fake_page[2][4096];
int host_steps = 3, host_bad, host_writes[2], host_irq_attached, host_maps;
static uintptr_t phys_of[2] = { 0x11030000u, 0x12850000u };

#define GPP9_CON 0xe0
#define GPP9_DAT 0xe4

static const uint8_t PEER_DEVID[5] = { 0x5a, 0x13, 0x9c, 0x01, 0x7e };
static const uint8_t PEER_HWID[8] = { 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38 };

static uint32_t latch;                 /* DAT bits as written */
static int selected, bit, miso, clk_level;
static uint8_t in_byte, frame[64];
static unsigned frame_len, clk_edges;
int host_frames, host_clk_edges_outside_frames;

static uint8_t
respond(unsigned index)
{
	if (frame_len >= 1 || index >= 1) {
		uint8_t cmd = frame[0];

		if (cmd == 0xd1 && index >= 4 && index < 9) {
			return PEER_DEVID[index - 4];
		}
		if (cmd == 0xfb && index >= 6 && index < 14) {
			return PEER_HWID[index - 6];
		}
	}
	return 0;
}

static uint32_t
con_field(unsigned pin)
{
	uint32_t con;

	memcpy(&con, fake_page[0] + GPP9_CON, 4);
	return (con >> (pin * 4)) & 0xf;
}

static int
pad_level(unsigned pin)
{
	if (con_field(pin) == 1) {
		return (latch >> pin) & 1;
	}
	if (pin == PEER_MISO && selected) {
		return miso;
	}
	/* an undriven chip-select is taken as inactive (high), so a pad still in input mode never selects the peer */
	return pin == PEER_CS ? 1 : 0;
}

static void
end_frame(void)
{
	printf("FRAME");
	for (unsigned i = 0; i < frame_len; i++) {
		printf(" %02x", frame[i]);
	}
	printf("\n");
	host_frames++;
}

static void
dat_written(uint32_t value)
{
	latch = value;
	int cs = pad_level(PEER_CS), clk = pad_level(PEER_CLK);

	if (!selected && cs == 0) {
		selected = 1;
		frame_len = 0;
		bit = 7;
		in_byte = 0;
		miso = (respond(0) >> 7) & 1;
	} else if (selected && cs == 1) {
		selected = 0;
		end_frame();
	}
	if (clk != clk_level) {
		clk_level = clk;
		if (!selected) {
			host_clk_edges_outside_frames++;
		} else if (clk) {
			in_byte = (uint8_t)((in_byte << 1) | pad_level(PEER_MOSI));
		} else if (bit-- == 0) {
			if (frame_len < sizeof(frame)) {
				frame[frame_len++] = in_byte;
			}
			in_byte = 0;
			bit = 7;
			miso = (respond(frame_len) >> 7) & 1;
		} else {
			miso = (respond(frame_len) >> bit) & 1;
		}
		clk_edges++;
	}
}

vm_offset_t
ml_io_map(vm_offset_t pa, vm_size_t size)
{
	for (int i = 0; i < 2; i++) {
		if (pa == phys_of[i] && size == 0x1000) {
			host_maps++;
			return (vm_offset_t)fake_page[i];
		}
	}
	host_bad++;
	return 0;
}

int
PE_parse_boot_argn(const char *n, void *v, int s)
{
	(void)s;
	if (!strcmp(n, "e1stouch_steps")) {
		*(uint32_t *)v = (uint32_t)host_steps;
		return 1;
	}
	return 0;
}

kern_return_t gic_v3_spi_attach(uint32_t intid, bool edge, void (*h)(void *, uint32_t), void *c) { (void)intid; (void)edge; (void)h; (void)c; host_irq_attached++; return 0; }
void gic_v3_spi_mask(uint32_t i) { (void)i; }
void gic_v3_spi_unmask(uint32_t i) { (void)i; }
void redwood_touch_post(uint32_t type, uint32_t finger, uint32_t x, uint32_t y) { printf("post %u %u %u %u\n", type, finger, x, y); }

static int
page_of(uintptr_t a)
{
	for (int i = 0; i < 2; i++) {
		if (a >= (uintptr_t)fake_page[i] && a + 4 <= (uintptr_t)fake_page[i] + 4096) {
			return i;
		}
	}
	return -1;
}

uint32_t
host_rd(uintptr_t a)
{
	int p = page_of(a);

	if (p < 0) {
		host_bad++;
		return 0;
	}
	if (p == 0 && a == (uintptr_t)fake_page[0] + GPP9_DAT) {
		uint32_t v = 0;

		for (unsigned pin = 0; pin < 8; pin++) {
			v |= (uint32_t)pad_level(pin) << pin;
		}
		return v;
	}
	return *(volatile uint32_t *)a;
}

void
host_wr(uintptr_t a, uint32_t v)
{
	int p = page_of(a);

	if (p < 0) {
		host_bad++;
		return;
	}
	host_writes[p]++;
	*(volatile uint32_t *)a = v;
	if (p == 0 && a == (uintptr_t)fake_page[0] + GPP9_DAT) {
		dat_written(v);
	}
}
