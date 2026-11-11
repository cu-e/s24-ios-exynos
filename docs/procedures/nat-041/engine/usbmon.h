/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * usbmon: a polled, EP0-only DWC3 device engine that serves a RAM log ring and an exception frame to a USB host.
 *
 * Freestanding C: no interrupts, no allocation, no libc, one event buffer, at most two TRBs in flight. The caller owns
 * every byte of memory (struct usbmon with its embedded DMA block, the log ring) and calls usbmon_poll() often enough.
 * What the engine does NOT do: clocks, power domains, PHYs, repeaters (the platform bring-up of NAT-040/NAT-043 must
 * leave the DWC3 core clocked and its PHY running before usbmon_init()), nor does it choose where its DMA block lives.
 *
 * Wire protocol (all multi-byte fields little endian):
 *   USB identity: VID 0x1209 PID 0x0001 (the pid.codes test pair), vendor class 0xff, one configuration, one interface,
 *   no endpoints, high speed only, no string descriptors.
 *   Vendor requests, bmRequestType type = vendor, recipient = device:
 *     0xC0 / 0x01 GET_INFO   wLength >= 1: struct usbmon_info (truncated to wLength)
 *     0xC0 / 0x02 READ_RING  wValue = stream offset low 16 bits, wIndex = high 16 bits, wLength <= 4096:
 *                            struct usbmon_ring_reply header (8 bytes) followed by up to wLength-8 bytes of the log stream
 *     0xC0 / 0x03 GET_EXC    struct usbmon_exc (truncated to wLength); valid == 0 until a fault has been recorded
 *     0x40 / 0x04 SET_NONCE  wLength == 16: the host nonce; GET_INFO echoes it
 *     0xC0 / 0x05 PEEK       reserved (memory/MMIO peek); this engine version answers with a stall
 *   Every other request, and any malformed one, is answered with an EP0 stall.
 */
#ifndef USBMON_H
#define USBMON_H

#include <stddef.h>
#include <stdint.h>
#include "dwc3_regs.h"

#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "the wire structures are little endian and are used in host byte order"
#endif

#define USBMON_VID		0x1209
#define USBMON_PID		0x0001
#define USBMON_PROTO_VERSION	1

#define USBMON_REQ_GET_INFO	0x01
#define USBMON_REQ_READ_RING	0x02
#define USBMON_REQ_GET_EXC	0x03
#define USBMON_REQ_SET_NONCE	0x04
#define USBMON_REQ_PEEK		0x05

#define USBMON_READ_MAX		4096u	/* largest wLength accepted by READ_RING */
#define USBMON_NONCE_LEN	16u
#define USBMON_BOOT_ID_LEN	16u

/* Log record kinds (the 3rd byte of a record header). */
#define USBMON_K_TEXT		1	/* free text, no terminator */
#define USBMON_K_STAGE		2	/* u32 stage number then text */
#define USBMON_K_FAULT		3	/* u64 esr, elr, far then u32 stage */
#define USBMON_K_BOOT		4	/* the image's identity text (image hash, run counter) */
#define USBMON_K_MARK		5	/* free-form marker */
#define USBMON_K_DROP		6	/* the device counts what it could not store: u32 count of records dropped so far */

#define USBMON_REC_HDR		8u
#define USBMON_REC_MAX		1024u	/* payload bytes per record */

/* GET_INFO flags */
#define USBMON_F_NONCE_SET	BIT(0)
#define USBMON_F_FAULT		BIT(1)
#define USBMON_F_HOLD		BIT(2)
#define USBMON_F_CONNECTED	BIT(3)	/* a bus reset and CONNECTDONE were seen since init */
#define USBMON_F_CONFIGURED	BIT(4)	/* SET_CONFIGURATION(1) was accepted */

struct usbmon_info {
	uint8_t magic[4];		/* "S24L" */
	uint16_t version;
	uint16_t size;			/* sizeof(struct usbmon_info) */
	uint32_t flags;
	uint32_t stage;
	uint8_t boot_id[USBMON_BOOT_ID_LEN];
	uint8_t nonce[USBMON_NONCE_LEN];
	uint32_t ring_size;
	uint32_t next_seq;
	uint64_t written;		/* total bytes ever appended to the stream */
	uint64_t oldest;		/* stream offset of the oldest retained record header */
	uint32_t dropped;
	uint32_t setups;		/* SETUP packets handled */
	uint32_t stalls;
	uint32_t faults;
	uint64_t ticks;
	int32_t last_err;
	uint32_t last_depcmd;
	uint32_t events;
	uint32_t resets;		/* USBRST events */
};
_Static_assert(sizeof(struct usbmon_info) == 112, "usbmon_info layout");
_Static_assert(__builtin_offsetof(struct usbmon_info, boot_id) == 16, "usbmon_info layout");
_Static_assert(__builtin_offsetof(struct usbmon_info, nonce) == 32, "usbmon_info layout");
_Static_assert(__builtin_offsetof(struct usbmon_info, written) == 56, "usbmon_info layout");
_Static_assert(__builtin_offsetof(struct usbmon_info, ticks) == 88, "usbmon_info layout");
_Static_assert(__builtin_offsetof(struct usbmon_info, last_err) == 96, "usbmon_info layout");

struct usbmon_ring_reply {
	uint32_t start;			/* stream offset (low 32 bits) of the first payload byte */
	uint32_t end;			/* stream offset (low 32 bits) of the end of the stream when the reply was built */
};
_Static_assert(sizeof(struct usbmon_ring_reply) == 8, "usbmon_ring_reply layout");

/* Register state supplied by the exception handler. */
struct usbmon_exc_in {
	uint64_t esr, elr, far, spsr, sp;
	uint64_t x[31];
};

struct usbmon_exc {
	uint8_t magic[4];		/* "S24X" */
	uint16_t version;
	uint16_t size;
	uint32_t valid;			/* written last */
	uint32_t stage;
	uint8_t boot_id[USBMON_BOOT_ID_LEN];
	uint64_t esr, elr, far, spsr, sp;
	uint64_t x[31];
	uint32_t count;			/* faults recorded since init; the frame keeps the first */
	uint32_t pad;
};
_Static_assert(sizeof(struct usbmon_exc) == 328, "usbmon_exc layout");
_Static_assert(__builtin_offsetof(struct usbmon_exc, esr) == 32, "usbmon_exc layout");
_Static_assert(__builtin_offsetof(struct usbmon_exc, x) == 72, "usbmon_exc layout");

/* ---- engine state ---- */

#define USBMON_EVT_BYTES	1024u
#define USBMON_OUT_BUF		512u
#define USBMON_REPLY_BUF	(USBMON_READ_MAX + 64u)

/* Everything the controller touches. Every member starts on its own 64-byte cache line. */
struct usbmon_dma {
	uint32_t events[USBMON_EVT_BYTES / 4] __attribute__((aligned(64)));
	struct dwc3_trb trb[2] __attribute__((aligned(64)));
	uint8_t setup[64] __attribute__((aligned(64)));
	uint8_t out[USBMON_OUT_BUF] __attribute__((aligned(64)));
	uint8_t reply[USBMON_REPLY_BUF] __attribute__((aligned(64)));
};

enum usbmon_ep0_state { EP0_UNCONNECTED = 0, EP0_SETUP_PHASE, EP0_DATA_PHASE, EP0_STATUS_PHASE };
enum usbmon_ep0_next { EP0_NEXT_UNKNOWN = 0, EP0_NEXT_COMPLETE, EP0_NEXT_NRDY_DATA, EP0_NEXT_NRDY_STATUS };

struct usbmon_cfg {
	uintptr_t dwc3_base;		/* controller registers */
	uint8_t *ring;			/* log ring storage, caller owned */
	uint32_t ring_size;		/* bytes, >= 2 * (USBMON_REC_HDR + USBMON_REC_MAX) */
	uint8_t boot_id[USBMON_BOOT_ID_LEN];
	uint32_t refclk_hz;		/* "ref" clock of the controller; 0 leaves GUCTL/GFLADJ reference-clock fields alone */
	uint8_t fladj;			/* GFLADJ frame length adjustment (vendor DT: 0x20); 0 leaves it alone */
	uint8_t gfladj_refclk_lpm_sel;	/* vendor DT snps,gfladj-refclk-lpm-sel-quirk */
};

struct usbmon {
	struct usbmon_dma dma;		/* must be first: the loader aligns the whole object to 64 bytes */
	uintptr_t base;
	uint8_t *ring;
	uint32_t ring_size;
	uint64_t written, oldest;
	uint32_t seq;
	uint32_t evt_lpos;
	uint32_t dropped_reported;
	uint32_t flags, stage, dropped, setups, stalls, faults, events, resets;
	int32_t last_err;
	uint32_t last_depcmd;
	uint8_t boot_id[USBMON_BOOT_ID_LEN];
	uint8_t nonce[USBMON_NONCE_LEN];
	struct usbmon_exc exc;
	/* ep0 */
	uint8_t ep0state, ep0_next, expect_in, three_stage, setup_pending, connected;
	uint8_t ep_started[2], ep_rsc[2];
	uint8_t usb_addr, configured;
	uint16_t mps;
	uint8_t out_pending;		/* an OUT data stage of SET_NONCE is in flight */
	uint16_t out_len;
	uint8_t magic_ok;
	uint8_t scratch[USBMON_REPLY_BUF];	/* reply under construction, ordinary memory (not DMA) */
};

#define USBMON_OK	0
#define USBMON_E_ID	(-1)	/* GSNPSID is not a DWC3 / DWC31 core */
#define USBMON_E_RESET	(-2)	/* soft reset did not finish */
#define USBMON_E_CMD	(-3)	/* a device endpoint command failed or timed out */
#define USBMON_E_HALT	(-4)	/* DSTS.DEVCTRLHLT did not clear after RUN_STOP */
#define USBMON_E_CFG	(-5)	/* bad configuration */
#define USBMON_E_ARG	(-6)

/* Bring the controller to "running, waiting for the host". The core must already be clocked and its PHY initialised. */
int usbmon_init(struct usbmon *m, const struct usbmon_cfg *cfg);
/* Process every event the controller has queued, then return. Cheap when idle. */
void usbmon_poll(struct usbmon *m);

/* Append a record to the log stream. Safe to call from an exception handler that interrupted a previous append. */
void usbmon_log(struct usbmon *m, uint8_t kind, const void *data, uint16_t len);
void usbmon_text(struct usbmon *m, const char *s);
void usbmon_stage(struct usbmon *m, uint32_t stage, const char *text);

/* Record an exception: keeps the first frame, appends a FAULT record, sets the hold flag. Returns. */
void usbmon_fault_record(struct usbmon *m, const struct usbmon_exc_in *regs);
/* usbmon_fault_record then poll forever (until the watchdog resets the phone). */
void usbmon_fault(struct usbmon *m, const struct usbmon_exc_in *regs) __attribute__((noreturn));
/* Poll forever. */
void usbmon_hold(struct usbmon *m) __attribute__((noreturn));

#ifdef USBMON_TESTING
/* Test support: append like usbmon_log but stop after `ncopied` bytes were copied, before the stream is committed. */
void usbmon_log_interrupted(struct usbmon *m, uint8_t kind, const void *data, uint16_t len, uint32_t ncopied);
#endif

uint8_t usbmon_crc8(const uint8_t *p, size_t n);

#endif
