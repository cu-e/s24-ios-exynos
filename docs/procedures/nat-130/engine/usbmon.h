/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * usbmon (NAT-076 variant of the NAT-041 engine): a polled DWC3 device engine that serves a RAM log ring and an exception
 * frame to a USB host and, when configured with a destination buffer, receives a file into that buffer over ONE bulk-OUT
 * endpoint (USB endpoint 0x01, physical endpoint 2). The EP0, log ring and fault code are NAT-041's, unchanged except for
 * the descriptor, the endpoint bookkeeping and the request switch. Host work only (see README.md): nothing here has run on a
 * phone.
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
 *     0x40 / 0x06 RX_BEGIN   wLength == 16, data = struct usbmon_rx_begin: arms ONE bulk-OUT transfer of `length` bytes that
 *                            must start at `offset` == the committed offset (a strictly sequential stream). Rejected (EP0
 *                            stall, counter) while a transfer is armed, for offset != committed (duplicate / gap), for a
 *                            length that is 0, not a multiple of 512, above the chunk limit or past the destination size.
 *     0xC0 / 0x07 GET_RX     struct usbmon_rx (truncated to wLength): state, committed offset, counters, last chunk's sum
 *     0x40 / 0x08 RX_ABORT   wLength == 0: ends an armed transfer, nothing is committed
 *   NAT-130 additions (a host that never sends them sees the NAT-076 engine; RX_BEGIN with flags == 0 is unchanged):
 *     RX_BEGIN flags bits 1:0 = checksum mode of the commit (USBMON_SUM_*; direct mode only, other bits must be 0):
 *                            0 PLAIN (NAT-076 loop), 1 FAST (unrolled pair loads, same memory type), 2 CACHED (the port maps
 *                            the range cacheable for the sum and cleans+invalidates it afterwards; refused where the port has
 *                            no such path), 3 NONE (commit without a sum: last_sum = 0, counted in rxt.unsummed; the host
 *                            must verify those bytes later with SUM).
 *     0xC0 / 0x09 GET_RXT    struct usbmon_rxt (truncated to wLength): per-phase tick counters of the receive path and the
 *                            result of the last SUM request.
 *     0x40 / 0x0A SUM        wLength == 16, data = struct usbmon_sum_req: sums [offset, offset+length) of COMMITTED bytes
 *                            with mode 0..2 during the data stage; the result and its ticks are read back with GET_RXT.
 *                            Refused (stall, sreq_status) for an uncommitted range, a length that is 0, not a multiple of
 *                            512 or above the chunk limit, mode 3 or an unavailable mode, or while a transfer is armed.
 *   Every other request, and any malformed one, is answered with an EP0 stall.
 *   Bulk-OUT endpoint (present only when the engine was configured with a destination): high speed, wMaxPacketSize 512.
 *   A chunk is committed only when the whole TRB completed with status OK, residual 0 and no short/bus-error event status;
 *   anything else leaves the committed offset where it was and sets state FAILED, so the host resends from `committed`.
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
#define USBMON_REQ_RX_BEGIN	0x06
#define USBMON_REQ_GET_RX	0x07
#define USBMON_REQ_RX_ABORT	0x08
#define USBMON_REQ_GET_RXT	0x09	/* NAT-130 */
#define USBMON_REQ_SUM		0x0A	/* NAT-130 */

#define USBMON_RX_EP		2u	/* physical endpoint number of USB endpoint 0x01 OUT (1:1 mapping, vendor gadget.c) */
#define USBMON_RX_MPS		512u	/* bulk at high speed */
#define USBMON_RX_TRBS		4u	/* ring: 3 data slots and one link TRB back to slot 0 (the vendor ring has 256) */
#ifndef USBMON_RX_STAGE_BYTES
#define USBMON_RX_STAGE_BYTES	65536u	/* staged mode: bytes the controller writes into the DMA block before the CPU copies them */
#endif
#define USBMON_RX_DIRECT_MAX	0x800000u	/* direct mode: one TRB, below the 16 MiB - 1 TRB size field */

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

#define USBMON_SUM_PLAIN	0u
#define USBMON_SUM_FAST		1u
#define USBMON_SUM_CACHED	2u
#define USBMON_SUM_NONE		3u
#define USBMON_RXB_SUM_MASK	0x3u

/* SUM request data (NAT-130) */
struct usbmon_sum_req {
	uint64_t offset;		/* destination offset; offset + length <= committed */
	uint32_t length;		/* > 0, a multiple of 512, <= the chunk limit */
	uint32_t mode;			/* USBMON_SUM_PLAIN, _FAST or _CACHED */
};
_Static_assert(sizeof(struct usbmon_sum_req) == 16, "usbmon_sum_req layout");

#define USBMON_SREQ_NONE	0u	/* no SUM request yet */
#define USBMON_SREQ_OK		1u
#define USBMON_SREQ_REFUSED	2u

struct usbmon_rxt {			/* GET_RXT reply (NAT-130) */
	uint8_t magic[4];		/* "S24T" */
	uint16_t version;		/* 1 */
	uint16_t size;			/* sizeof(struct usbmon_rxt) */
	uint64_t now;			/* usbmon_ticks() when the reply was built */
	uint64_t freq;			/* usbmon_freq(): ticks per second */
	uint32_t caps;			/* bit m set: checksum mode m is available */
	uint32_t last_mode;		/* mode of the last committed chunk */
	uint64_t t_arm0, t_arm1;	/* last chunk: RX_BEGIN accepted (before the destination sync), transfer started */
	uint64_t t_done, t_sum1;	/* last chunk: completion seen, commit finished (sync + sum) */
	uint64_t tot_arm;		/* sum over chunks of t_arm1 - t_arm0 (destination clean before the controller writes) */
	uint64_t tot_wire;		/* sum of t_done - t_arm1 (controller receiving) */
	uint64_t tot_sum;		/* sum of t_sum1 - t_done (invalidate + checksum) */
	uint64_t tot_gap;		/* sum of t_arm0 - previous t_sum1 (host turnaround, control requests) */
	uint32_t chunks;		/* chunks timed (== rx_trbs unless a chunk failed) */
	uint32_t unsummed;		/* chunks committed with mode NONE */
	uint64_t sreq_off;		/* last SUM request */
	uint32_t sreq_len, sreq_mode;
	uint64_t sreq_sum, sreq_ticks;
	uint32_t sreq_count, sreq_status;
	uint32_t sreq_refused;
	uint32_t sum_fallbacks;		/* CACHED sums the port computed with FAST instead (usbmon_port_sum_fallbacks()) */
};
_Static_assert(sizeof(struct usbmon_rxt) == 152, "usbmon_rxt layout");
_Static_assert(__builtin_offsetof(struct usbmon_rxt, t_arm0) == 32, "usbmon_rxt layout");
_Static_assert(__builtin_offsetof(struct usbmon_rxt, sreq_off) == 104, "usbmon_rxt layout");

/* RX_BEGIN request data */
struct usbmon_rx_begin {
	uint64_t offset;		/* must equal the committed offset */
	uint32_t length;		/* bytes of the bulk transfer: > 0, a multiple of 512, <= the chunk limit */
	uint32_t flags;			/* NAT-130: bits 1:0 checksum mode (USBMON_SUM_*), the rest must be 0 */
};
_Static_assert(sizeof(struct usbmon_rx_begin) == 16, "usbmon_rx_begin layout");

#define USBMON_RX_IDLE		0u
#define USBMON_RX_ARMED		1u
#define USBMON_RX_FAILED	2u
#define USBMON_RXF_PRESENT	BIT(0)	/* the engine was configured with a destination */
#define USBMON_RXF_ENABLED	BIT(1)	/* the bulk endpoint is enabled (after SET_CONFIGURATION(1)) */
#define USBMON_RXF_DIRECT	BIT(2)	/* the controller writes into the destination itself; otherwise staged and copied */

struct usbmon_rx {			/* GET_RX reply */
	uint8_t magic[4];		/* "S24R" */
	uint16_t version;
	uint16_t size;			/* sizeof(struct usbmon_rx) */
	uint32_t state;			/* USBMON_RX_* */
	uint32_t flags;			/* USBMON_RXF_* */
	uint64_t committed;		/* bytes in the destination that are complete and in order */
	uint64_t armed_off;
	uint32_t armed_len;
	uint32_t chunk_max;
	uint64_t capacity;		/* destination size */
	uint64_t rx_bytes;		/* == committed unless a chunk was committed twice (a defect) */
	uint32_t rx_trbs;		/* chunks committed */
	uint32_t rx_errors;		/* chunks that ended with an error status, a short packet or a reset */
	uint32_t rx_dups;		/* RX_BEGIN with offset below the committed offset */
	uint32_t rx_gaps;		/* RX_BEGIN with offset above the committed offset */
	uint32_t rx_rejects;		/* RX_BEGIN refused for any other reason */
	uint32_t rx_resets;		/* transfers lost to a bus reset or a disconnect */
	uint32_t rx_aborts;
	uint32_t last_trb_status;	/* TRBSTS of the last completed TRB */
	uint32_t last_residual;
	uint32_t last_evt_status;	/* event status bits of the last completion event */
	uint32_t last_len;
	uint32_t pad;
	uint64_t last_off;
	uint64_t last_sum;		/* usbmon_rx_sum() of the last committed chunk */
};
_Static_assert(sizeof(struct usbmon_rx) == 120, "usbmon_rx layout");
_Static_assert(__builtin_offsetof(struct usbmon_rx, committed) == 16, "usbmon_rx layout");
_Static_assert(__builtin_offsetof(struct usbmon_rx, rx_bytes) == 48, "usbmon_rx layout");
_Static_assert(__builtin_offsetof(struct usbmon_rx, last_off) == 104, "usbmon_rx layout");

/* Position-sensitive 64-bit checksum of a chunk: the sum over little-endian 64-bit words w[i] of w[i] * (2*i + 1), modulo
 * 2^64 (the length is a multiple of 8). Cheap enough for the loader, strong enough to localise a bad chunk; the end-to-end
 * check of a whole image is a SHA-256 taken by the kernel side (NAT-077). */
static inline uint64_t usbmon_rx_sum_step(uint64_t sum, uint64_t word, uint64_t index) { return sum + word * (2 * index + 1); }

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
	struct dwc3_trb rxtrb[USBMON_RX_TRBS] __attribute__((aligned(64)));	/* bulk-OUT ring: 4 x 16 B = one cache line */
	uint8_t setup[64] __attribute__((aligned(64)));
	uint8_t out[USBMON_OUT_BUF] __attribute__((aligned(64)));
	uint8_t reply[USBMON_REPLY_BUF] __attribute__((aligned(64)));
	uint8_t rxstage[USBMON_RX_STAGE_BYTES] __attribute__((aligned(64)));	/* staged mode only */
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
	uint8_t *rx_dest;		/* NAT-076: destination of the bulk-OUT stream; 0 = no bulk endpoint (the NAT-041 engine) */
	uint64_t rx_size;		/* bytes available at rx_dest; a multiple of 512 */
	uint8_t rx_direct;		/* 1: the controller DMAs straight into rx_dest (the window must be reachable by the DWC3's
					 * DMA master, NAT-040 item U5, unproven); 0: DMA into the DMA block, then copy */
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
	uint8_t ep_started[3], ep_rsc[3];
	uint8_t usb_addr, configured;
	uint16_t mps;
	uint8_t out_pending;		/* an OUT data stage of SET_NONCE or RX_BEGIN is in flight */
	uint8_t out_kind;		/* 0 = SET_NONCE, 1 = RX_BEGIN, 2 = SUM (NAT-130) */
	uint16_t out_len;
	uint8_t magic_ok;
	/* NAT-076 bulk-OUT receive */
	uint8_t *rx_dest;
	uint64_t rx_size;
	uint8_t rx_present, rx_direct, rx_enabled, rx_state, rx_enq, rx_deq, rx_end_pending, rx_restart;
	uint64_t rx_committed, rx_armed_off, rx_bytes, rx_last_off, rx_last_sum;
	uint32_t rx_armed_len, rx_trbs, rx_errors, rx_dups, rx_gaps, rx_rejects, rx_resets, rx_aborts, rx_spurious;
	uint32_t rx_last_trb_status, rx_last_residual, rx_last_evt_status, rx_last_len;
	/* NAT-130: checksum mode of the armed chunk, phase ticks, SUM request */
	uint32_t rx_mode, rx_last_mode, rx_unsummed, rx_timed;
	uint64_t rx_t_arm0, rx_t_arm1, rx_t_done, rx_t_sum1, rx_prev_sum1, rx_tot_arm, rx_tot_wire, rx_tot_sum, rx_tot_gap;
	uint64_t sreq_off, sreq_sum, sreq_ticks;
	uint32_t sreq_len, sreq_mode, sreq_count, sreq_status, sreq_refused;
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
/* Sum of a destination range as the engine reads it (usbmon_rx_sum_step over 64-bit words); exported for the tests and for
 * the loader's own verification. `n` must be a multiple of 8. The range must already have been synced (direct mode). */
uint64_t usbmon_rx_sum(const uint8_t *p, size_t n);
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
