/* Project-authored host-only READ(10) admission; no controller or DMA I/O. */
#ifndef S24_UFS_HOST_H
#define S24_UFS_HOST_H
#include <stddef.h>
#include <stdint.h>
#define UFS_UTRD_BYTES 32u
#define UFS_CQE_BYTES 32u
#define UFS_UCD_BYTES 1088u
#define UFS_RESPONSE_MIN 52u
#define UFS_MAX_TRANSFER 1048576u
#define UFS_PRDT_CHUNK 262144u
#define UFS_TIMEOUT_MAX_NS UINT64_C(5000000000)
enum ufs_result {
    UFS_OK=0, UFS_ARGUMENT, UFS_LENGTH, UFS_WRITE_REJECTED, UFS_COMMAND,
    UFS_EXTENT, UFS_DMA_RANGE, UFS_BUSY, UFS_STALE, UFS_FORMAT,
    UFS_STATUS, UFS_TIMEOUT, UFS_CLOCK, UFS_EXHAUSTED, UFS_OWNERSHIP
};
enum ufs_direction { UFS_FROM_DEVICE=1, UFS_TO_DEVICE=2 };
enum ufs_phase { UFS_IDLE=0, UFS_PREPARED, UFS_DEVICE_OWNED, UFS_COMPLETE, UFS_QUARANTINED };
struct ufs_policy {
    uint64_t lun_blocks, first_block, extent_blocks;
    uint64_t ucd_dma, ucd_bytes, data_dma, data_bytes;
    uint32_t block_bytes, lun, sqid, epoch;
};
struct ufs_token { uint32_t epoch, generation, tag; };
struct ufs_packet { uint8_t utrd[UFS_UTRD_BYTES], ucd[UFS_UCD_BYTES]; uint32_t bytes, prdt_entries; };
struct ufs_host {
    struct ufs_policy policy;
    struct ufs_packet packet;
    struct ufs_token token;
    uint64_t time_ns, deadline_ns;
    uint32_t phase;
};
#ifdef __cplusplus
extern "C" {
#endif
/* Fresh/retired storage only: init is not a DMA cancellation or recovery API. */
uint32_t ufs_host_init(struct ufs_host *, const struct ufs_policy *);
uint32_t ufs_host_prepare(struct ufs_host *, const uint8_t *, size_t, uint32_t, uint64_t);
/* Reserve before backend cache/DMA setup and publication. Never publish after
   nonzero return. Success retains the lease even if backend publication fails. */
uint32_t ufs_host_reserve_device(struct ufs_host *, const struct ufs_token *, uint64_t, uint64_t);
uint32_t ufs_host_complete(struct ufs_host *, const struct ufs_token *, const uint8_t *, size_t, const uint8_t *, size_t, uint64_t);
uint32_t ufs_host_poll_timeout(struct ufs_host *, uint64_t);
/* Backend asserts completion consumption AND real CPU DMA ownership before call. */
uint32_t ufs_host_reclaim(struct ufs_host *, const struct ufs_token *);
/* Prepared only. Device-owned requests cannot be canceled by a logical flag. */
uint32_t ufs_host_cancel_prepared(struct ufs_host *, const struct ufs_token *);
#ifdef __cplusplus
}
#endif
#endif
