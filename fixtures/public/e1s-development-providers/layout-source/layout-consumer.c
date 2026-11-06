/* Genuine native subr_log header spelling, order and selected board context. */
#include <machine/atomic.h>
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/proc_internal.h>
#include <sys/vnode.h>
#include <stdbool.h>
#include <firehose/tracepoint_private.h>
#include <firehose/chunk_private.h>
#include <firehose/ioctl_private.h>
#include <os/firehose_buffer_private.h>
#include <pexpert/arm64/board_config.h>
#include <mach_assert.h>

/* Measurement data only: no implementation, function, fallback type or runtime. */
__attribute__((used, section("__DATA_CONST,__s24fh")))
const unsigned long long s24_e1s_firehose_consumer_layout[] = {
    1ULL,
    sizeof(unsigned long long),
    MAX_CPUS,
    MAX_CPU_CLUSTERS,
    MAX_CPU_CLUSTER_PHY_ID,
    MACH_ASSERT,
    DEVELOPMENT,
    sizeof(void *),
    sizeof(firehose_tracepoint_id_u),
    _Alignof(firehose_tracepoint_id_u),
    sizeof(struct firehose_tracepoint_s),
    _Alignof(struct firehose_tracepoint_s),
    __builtin_offsetof(struct firehose_tracepoint_s, ft_thread),
    __builtin_offsetof(struct firehose_tracepoint_s, ft_stamp_and_length),
    __builtin_offsetof(struct firehose_tracepoint_s, ft_data),
    sizeof(firehose_chunk_pos_u),
    _Alignof(firehose_chunk_pos_u),
    sizeof(struct firehose_chunk_s),
    _Alignof(struct firehose_chunk_s),
    __builtin_offsetof(struct firehose_chunk_s, fc_pos),
    __builtin_offsetof(struct firehose_chunk_s, fc_timestamp),
    __builtin_offsetof(struct firehose_chunk_s, fc_data),
    sizeof(struct firehose_chunk_range_s),
    _Alignof(struct firehose_chunk_range_s),
    __builtin_offsetof(struct firehose_chunk_range_s, fcr_offset),
    __builtin_offsetof(struct firehose_chunk_range_s, fcr_length),
    FIREHOSE_CHUNK_SIZE,
    sizeof(firehose_stream_t),
};
