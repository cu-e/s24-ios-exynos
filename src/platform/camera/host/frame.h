/* Project-owned host preparation; no camera, ISP or DMA operations. */
#ifndef S24_CAMERA_HOST_FRAME_H
#define S24_CAMERA_HOST_FRAME_H
#include <stddef.h>
#include <stdint.h>
#define CAM_FOURCC(a,b,c,d) ((uint32_t)(a)|((uint32_t)(b)<<8)|((uint32_t)(c)<<16)|((uint32_t)(d)<<24))
#define CAM_YUYV CAM_FOURCC('Y','U','Y','V')
#define CAM_NV12 CAM_FOURCC('N','V','1','2')
#define CAM_NV21 CAM_FOURCC('N','V','2','1')
#define CAM_NV12M CAM_FOURCC('N','M','1','2')
#define CAM_NV21M CAM_FOURCC('N','M','2','1')
/* Exact selected v12.0 header, compiled with 64-bit pinned Linux declarations. */
#define CAM_METADATA_BYTES 30968u
#define CAM_PLANES 3u
#define CAM_DESCRIPTOR_VERSION 1u
enum cam_result { CAM_OK, CAM_ARGUMENT, CAM_TRUNCATED, CAM_FORMAT, CAM_GEOMETRY,
    CAM_OVERFLOW, CAM_CROP, CAM_CAPACITY, CAM_OVERLAP, CAM_STALE, CAM_BUSY,
    CAM_STOPPED, CAM_PRODUCER_ERROR, CAM_TIMEOUT };
enum cam_phase { CAM_IDLE, CAM_INFLIGHT, CAM_READY, CAM_HELD, CAM_RETIRED };
struct cam_plane { uint64_t offset, capacity, used; };
/* Owned in-process descriptor, not a Samsung, firmware, USB or Apple ABI. */
struct cam_frame {
    uint32_t version, fourcc, component_bits, compression;
    uint32_t width, height, bytesperline[2];
    uint32_t crop_x, crop_y, crop_w, crop_h, plane_count, reserved;
    uint64_t allocation_bytes;
    struct cam_plane planes[CAM_PLANES];
};
struct cam_layout { uint32_t stride[2], required[CAM_PLANES], plane_count; };
struct cam_queue {
    uint64_t epoch, last_epoch, next_ticket, active_ticket, deadline, last_now;
    uint32_t running, phase;
    struct cam_frame frame;
    struct cam_layout layout;
};
#ifdef __cplusplus
extern "C" {
#endif
/* Byte length is checked before any descriptor field is read; unaligned input
 * is copied into local storage. Capacities describe one abstract allocation.
 * Plan checks geometry/reservations; admit additionally checks image payloads.
 * Metadata remains opaque, including when used==0. */
enum cam_result cam_plan(const void *, size_t, struct cam_layout *);
enum cam_result cam_admit(const void *, size_t, struct cam_layout *);
/* Zero-initialize queue once and serialize all calls. Clock values are trusted
 * monotonic caller inputs; poll must actually be scheduled by its integrator. */
enum cam_result cam_start(struct cam_queue *, uint64_t epoch);
enum cam_result cam_submit(struct cam_queue *, uint64_t epoch, const void *, size_t,
    uint64_t now, uint64_t timeout, uint64_t *ticket);
enum cam_result cam_complete(struct cam_queue *, uint64_t epoch, uint64_t ticket,
    const void *used_counts, size_t count_bytes, int producer_status, uint64_t now);
enum cam_result cam_poll(struct cam_queue *, uint64_t now);
enum cam_result cam_take(struct cam_queue *, struct cam_frame *, struct cam_layout *);
enum cam_result cam_release(struct cam_queue *, uint64_t epoch, uint64_t ticket);
void cam_stop(struct cam_queue *);
/* Acknowledgement is an external trusted premise, not proof of hardware
 * quiescence. Stop/error/timeout retain reservations until this or held-release. */
enum cam_result cam_quiesced(struct cam_queue *, uint64_t epoch, uint64_t ticket);
#ifdef __cplusplus
}
#endif
#endif
