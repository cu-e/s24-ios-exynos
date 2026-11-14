/* NAT-172 copy of NAT-123's fake APM, plus: a fake CMU_CPUCL0 page whose PLL_CON3 the channel-0 "firmware" changes on a
 * FREQ_REQ {2, kHz, 0, t}, logged as "dvfs ..."; a channel-0 command of any other shape counts as bad. Synthetic.
 *
 * NAT-123 fake APM: SRAM laid out with Samsung's own struct acpm_framework / ipc_channel (framework.h, S5E9945 branch); a
 * mailbox whose INTGR0 write runs the "firmware": it takes the command from the AP's TX queue (APM rx_*), applies it to a fake
 * S2MPS27 register file decoded the way acpm_mfd_spmi.c encodes it, and answers in the APM tx queue. Every command is logged. */
#define CONFIG_EXYNOS_ACPM 1
#define CONFIG_SOC_S5E9945 1
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
typedef uintptr_t vm_offset_t; typedef uintptr_t vm_size_t;
typedef uint32_t u32; typedef uint8_t u8; typedef int32_t s32; typedef uint16_t u16;
struct build_info { char build_version[25]; char build_time[25]; };
#undef true
#undef false
struct dbg_log_info;
struct work_struct;
#include "framework_noinc.h"

#define SRAM_SIZE 0x3A000
#define INITDATA 0x9D00
static uint8_t sram[SRAM_SIZE] __attribute__((aligned(16)));
static uint32_t mbox[0x400];
uint32_t cmu[0x400];
int host_dvfs_cmds, host_dvfs_bad;
uint8_t pmic[16][256][256];        /* [sid][type][reg] */
int host_cmds, host_writes, host_bad_writes, host_steps_arg = 3, host_pmic_mode = 2, host_settle;
char host_log[8192];
const char *host_case = "normal";

static struct ipc_channel *chans(void) { struct acpm_framework *f = (void *)(sram + INITDATA); return (void *)(sram + f->ipc_channels); }

void fakeapm_init(void)
{
	struct acpm_framework *f = (void *)(sram + INITDATA);
	memset(sram, 0, sizeof sram);
	f->ipc_channels = 0x9510 - 12;             /* channel table */
	f->ipc_ap_max = 4;
	f->ipc_base = 0x9500;
	struct ipc_channel *c = chans();
	uint32_t q = 0x20000;
	for (int i = 0; i < 4; i++) {
		c[i].id = i; c[i].type = 1; c[i].ap_poll = 1;
		c[i].ch.q_len = 8; c[i].ch.q_elem_size = 16;
		c[i].ch.rx_rear = 0x10000 + i * 0x40; c[i].ch.rx_front = c[i].ch.rx_rear + 4; c[i].ch.rx_base = q; q += 8 * 16;
		c[i].ch.tx_rear = c[i].ch.rx_rear + 8; c[i].ch.tx_front = c[i].ch.rx_rear + 12; c[i].ch.tx_base = q; q += 8 * 16;
	}
	pmic[0x0d][0x03][0x0e] = 0x01;             /* measured Android PMIC revision, not a fabricated identity */
	if (!strcmp(host_case, "chip-zero")) pmic[0x0d][3][0x0e] = 0;
	if (!strcmp(host_case, "chip-other")) pmic[0x0d][3][0x0e] = 0x41;
	pmic[0x0d][0x05][0x34] = 0x30;             /* LDO9: off, 3.0 V select */
	pmic[0x0d][0x05][0x3d] = 0x18;             /* LDO18: off, 1.8 V select */
	if (!strcmp(host_case, "already-wrong")) pmic[0x0d][5][0x3d] = 0xd9;
	if (!strcmp(host_case, "bad-pointer")) c[2].ch.rx_front = SRAM_SIZE + 4;
	if (!strcmp(host_case, "bad-type")) c[2].type = 2;
	if (!strcmp(host_case, "bad-id")) c[2].id = 31;
	if (!strcmp(host_case, "bad-queue")) c[2].ch.rx_base = SRAM_SIZE - 4;
	cmu[0x10c / 4] = (1u << 31) | (35u << 16) | (1u << 8) | 2u;       /* 76.8 MHz * 35 / (1 << 2) = 672 MHz */
	if (!strcmp(host_case, "at-max")) cmu[0x10c / 4] = (1u << 31) | (102u << 16) | (1u << 8) | 2u;
	if (!strcmp(host_case, "pll-off")) cmu[0x10c / 4] &= ~(1u << 31);
	if (!strcmp(host_case, "dvfs-irq")) c[0].ap_poll = 0;
	if (!strcmp(host_case, "dvfs-pointer")) c[0].ch.tx_front = SRAM_SIZE + 4;
	if (!strcmp(host_case, "dvfs-type")) c[0].type = 2;
}

static uint32_t *u32at(uint32_t off) { return (uint32_t *)(sram + off); }

static void apm_run(unsigned id)
{
	struct ipc_channel *c = &chans()[id];
	uint32_t front = *u32at(c->ch.rx_front), rear = *u32at(c->ch.rx_rear);
	while (rear != front) {
		uint32_t *cmd = u32at(c->ch.rx_base + rear * c->ch.q_elem_size);
		uint32_t reg = cmd[0] & 0xff, type = (cmd[0] >> 8) & 0xff, func = cmd[1] & 0xff, sid = (cmd[1] >> 24) & 0xf;
		uint32_t val = (cmd[1] >> 8) & 0xff, mask = (cmd[1] >> 16) & 0xff;
		uint32_t resp[4] = { cmd[0], cmd[1] & 0x0f0000ff, cmd[2], cmd[3] };
		if (id == 0) {
			char l0[128];
			host_dvfs_cmds++;
			snprintf(l0, sizeof l0, "dvfs ch0 %08x %08x %08x %08x\n", cmd[0], cmd[1], cmd[2], cmd[3]);
			strncat(host_log, l0, sizeof host_log - strlen(host_log) - 1);
			if ((cmd[0] & ~(0x3fu << 16)) != 2 || cmd[2] != 0 || cmd[3] != 0 || ((cmd[0] >> 16) & 0x3f) == 0) host_dvfs_bad++;
			else if (strcmp(host_case, "dvfs-ignored")) cmu[0x10c / 4] = (1u << 31) | ((cmd[1] * 4u / 76800u) << 16) | (1u << 8) | 2u;
			resp[0] = cmd[0]; resp[1] = cmd[1]; resp[2] = cmd[2]; resp[3] = cmd[3];
			if (!strcmp(host_case, "dvfs-silent")) return;
			goto answer;
		}
		host_cmds++;
		char line[128];
		snprintf(line, sizeof line, "cmd ch%u func %u sid %#x type %#x reg %#x val %#x mask %#x\n", id, func, sid, type, reg, val, mask);
		strncat(host_log, line, sizeof host_log - strlen(host_log) - 1);
		if (id != 2) host_bad_writes++;
		if (func == 0) resp[1] = (resp[1] & ~0xff00u) | ((uint32_t)pmic[sid][type][reg] << 8);
		else if (func == 1 || func == 2) {
			host_writes++;
			if (!(sid == 0x0d && type == 0x05 && (reg == 0x34 || reg == 0x3d))) host_bad_writes++;
			if (func == 1) pmic[sid][type][reg] = val; else pmic[sid][type][reg] = (pmic[sid][type][reg] & ~mask) | (val & mask);
		}
		resp[1] &= 0x00ffffffu;                    /* return 0 */
		if (!strcmp(host_case, "readback-mismatch") && func == 0 && host_writes && reg == 0x3d)
			resp[1] ^= 1u << 8;
		if (!strcmp(host_case, "readback-error") && func == 0 && host_writes && reg == 0x3d)
			resp[1] |= 1u << 24;
		if (!strcmp(host_case, "rail-read-error") && func == 0 && reg == 0x3d)
			resp[1] |= 1u << 24;
		if (!strcmp(host_case, "chip-error") && func == 0 && type == 3 && sid == 0x0d)
			resp[1] |= 1u << 24;
		if (!strcmp(host_case, "wrong-sequence")) resp[0] ^= 1u << 16;
		if (!strcmp(host_case, "no-response")) return;
answer:;
		uint32_t tf = *u32at(c->ch.tx_front);
		memcpy(sram + c->ch.tx_base + tf * c->ch.q_elem_size, resp, 16);
		*u32at(c->ch.tx_front) = (tf + 1) % c->ch.q_len;
		rear = (rear + 1) % c->ch.q_len;
		*u32at(c->ch.rx_rear) = rear;
		mbox[0x28 / 4] |= 1u << id;                /* INTSR1 */
	}
}

vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t size)
{
	if (pa == 0x12B90000 && size == 0x1000) return (vm_offset_t)mbox;
	if (pa == 0x02055000 && size == SRAM_SIZE) return (vm_offset_t)sram;
	if (pa == 0x1DC40000 && size == 0x1000) return (vm_offset_t)cmu;
	fprintf(stderr, "unexpected map %#lx\n", (unsigned long)pa); exit(3);
}
/* mailbox writes are plain stores: poll them from delay() */
/* Doorbell stores are consumed on the next simulated delay. */
void delay(int us)
{
	(void)us;
	if (mbox[0x20 / 4]) { mbox[0x28 / 4] &= ~mbox[0x20 / 4]; mbox[0x20 / 4] = 0; }  /* INTCR1 clears INTSR1 (written before the doorbell) */
	if (mbox[0x08 / 4]) { uint32_t g = mbox[0x08 / 4]; mbox[0x08 / 4] = 0;
		for (unsigned i = 0; i < 16; i++) if (g & (1u << (16 + i))) apm_run(i); }
}
void delay_for_interval(uint64_t n, uint64_t unit) { (void)n; (void)unit; host_settle++; }
int PE_parse_boot_argn(const char *n, void *v, int s)
{
	(void)s;
	if (!strcmp(n, "e1spmic")) { *(uint32_t *)v = (uint32_t)host_pmic_mode; return 1; }
	if (!strcmp(n, "e1scpuclk") && !strncmp(host_case, "arg-", 4)) { *(uint32_t *)v = (uint32_t)strtoul(host_case + 4, NULL, 10); return 1; }
	return 0;
}
