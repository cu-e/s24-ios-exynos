/* SCFB, the Scion shared framebuffer (scion-avf a6f4bc3: avf/shim/avfboot.c, xnu patches 1200 and 1204),
 * read from the host side, and the s24vmm frame/touch protocol between the VMM and its viewer app.
 *
 * Header layout (little endian, at scfb.addr; buffer 0 at +0x10000):
 *   0 magic "SCFB", 4 version, 8 width, 12 height, 16 stride, 20 format (XR24), 24 buf_offset[2],
 *   32 nbufs, 36 flags (1 READY, 2 POLL, 4 DAMAGE), 40 front, 44 drawing,
 *   48 frame_seq, 56 input_seq, 64 guest_ns, 72 dirty[4] (x, y, w, h), 88 host_seq, 96 host_reading,
 *   104 host_ns.
 * Seqlock: the guest waits while host_reading is set, sets drawing, draws, clears drawing and bumps
 * frame_seq. The host sets host_reading, backs off if drawing is set, copies, clears host_reading. */
#ifndef S24VMM_SCFB_H
#define S24VMM_SCFB_H

#include <stddef.h>
#include <stdint.h>

#define SCFB_MAGIC 0x42464353u
#define SCFB_FB_OFFSET 0x10000u
#define SCFB_FORMAT_XR24 0x34325258u
#define SCFB_F_READY 1u
#define SCFB_F_POLL 2u
#define SCFB_F_DAMAGE 4u
#define SCFB_HEADER_BYTES 112u

/* Bytes to reserve for a w x h framebuffer (header page + buffer), rounded up to 2 MiB. */
uint64_t scfb_region_size(uint32_t width, uint32_t height);

enum scfb_result { SCFB_NOTHING = 0, SCFB_FRAME = 1, SCFB_BUSY = 2, SCFB_INVALID = 3 };

struct scfb_reader {
    uint64_t last_seq;
    int have_frame;
    uint64_t frames, busy, invalid, full_copies;
};

struct scfb_frame {
    uint32_t width, height, x, y, w, h;
    uint64_t seq;
    uint8_t *pixels; /* w*h*4 bytes, tightly packed rows; caller-owned, width*height*4 capacity */
};

/* Reads the region (header at region, region_len bytes long). On SCFB_FRAME, out holds the changed
 * rectangle (the whole frame when damage is unknown or frames were skipped). force asks for a whole
 * frame even if nothing changed (a newly connected viewer). */
enum scfb_result scfb_read(struct scfb_reader *r, uint8_t *region, uint64_t region_len, uint32_t expect_w,
                           uint32_t expect_h, int force, struct scfb_frame *out);

/* Wire protocol on a localhost TCP stream. VMM -> viewer: a 48-byte frame header followed by
 * w*h*4 pixel bytes. Viewer -> VMM: 20-byte touch messages. All fields little endian. */
#define S24F_MAGIC 0x46343253u /* "S24F" */
#define S24T_MAGIC 0x54343253u /* "S24T" */
#define S24F_HEADER_BYTES 48u
#define S24T_BYTES 20u
void s24f_encode_header(uint8_t out[S24F_HEADER_BYTES], const struct scfb_frame *f);
struct s24t_touch {
    uint32_t slot;
    int32_t tracking_id; /* -1: finger lifted */
    uint32_t x, y;       /* framebuffer pixels */
};
/* Returns 0 and fills t when in holds a valid touch message. */
int s24t_decode(const uint8_t in[S24T_BYTES], struct s24t_touch *t);

#endif
