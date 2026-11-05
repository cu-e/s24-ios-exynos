/* SPDX-License-Identifier: Apache-2.0 */
/* Actual selected XNU types and genuine exported libdispatch declarations. */
#include <sys/types.h>
#include <mach/mach_types.h>
#include <firehose/tracepoint_private.h>
#include <firehose/chunk_private.h>
#include <firehose/ioctl_private.h>
#include <os/firehose_buffer_private.h>

#define SAME(fn, type) _Static_assert(__builtin_types_compatible_p(__typeof__(&(fn)), type), #fn " prototype")
SAME(__firehose_buffer_tracepoint_reserve, firehose_tracepoint_t (*)(uint64_t, firehose_stream_t, uint16_t, uint16_t, uint8_t **));
SAME(__firehose_buffer_tracepoint_flush, void (*)(firehose_tracepoint_t, firehose_tracepoint_id_u));
SAME(__firehose_buffer_create, firehose_buffer_t (*)(size_t *));
SAME(__firehose_merge_updates, bool (*)(firehose_push_reply_t));
SAME(__firehose_kernel_configuration_valid, int (*)(uint8_t, uint8_t));
SAME(__firehose_allocate, void (*)(vm_offset_t *, vm_size_t));
SAME(__firehose_critical_region_enter, void (*)(void));
SAME(__firehose_critical_region_leave, void (*)(void));
SAME(__firehose_buffer_push_to_logd, void (*)(firehose_buffer_t, bool));
_Static_assert(sizeof(__firehose_buffer_kernel_chunk_count) == 1, "chunk count");
_Static_assert(sizeof(__firehose_num_kernel_io_pages) == 1, "io pages");
_Static_assert(OS_FIREHOSE_SPI_VERSION == 20180226, "selected SPI version");
_Static_assert(sizeof(struct firehose_tracepoint_s) == 24, "tracepoint bytes");
_Static_assert(__builtin_offsetof(struct firehose_tracepoint_s, ft_data) == 24, "tracepoint payload");
_Static_assert(sizeof(struct firehose_chunk_s) == 4096, "chunk bytes");
_Static_assert(__builtin_offsetof(struct firehose_chunk_s, fc_data) == 16, "chunk payload");
_Static_assert(sizeof(struct firehose_buffer_range_s) == 4, "range bytes");
_Static_assert(sizeof(firehose_chunk_pos_u) == 8, "position bytes");
_Static_assert(sizeof(firehose_push_reply_t) == 16, "reply bytes");

__attribute__((used,section("__DATA_CONST,__s24fh")))
const unsigned long long s24_firehose_interface[] = {
    OS_FIREHOSE_SPI_VERSION, sizeof(struct firehose_tracepoint_s),
    __builtin_offsetof(struct firehose_tracepoint_s, ft_data),
    sizeof(struct firehose_chunk_s), __builtin_offsetof(struct firehose_chunk_s, fc_data),
    sizeof(struct firehose_buffer_range_s), sizeof(firehose_chunk_pos_u), sizeof(firehose_push_reply_t),
    FIREHOSE_BUFFER_KERNEL_MIN_CHUNK_COUNT, FIREHOSE_BUFFER_KERNEL_MAX_CHUNK_COUNT,
    FIREHOSE_BUFFER_KERNEL_DEFAULT_IO_PAGES
};
/* Emit real references so symbol checking cannot pass from declarations alone. */
void * const s24_firehose_calls[] = {
    (void *)&__firehose_buffer_tracepoint_reserve,
    (void *)&__firehose_buffer_tracepoint_flush,
    (void *)&__firehose_buffer_create,
    (void *)&__firehose_merge_updates,
    (void *)&__firehose_kernel_configuration_valid,
    (void *)&__firehose_allocate,
    (void *)&__firehose_critical_region_enter,
    (void *)&__firehose_critical_region_leave,
    (void *)&__firehose_buffer_push_to_logd
};
