/* SPDX-License-Identifier: Apache-2.0 */
/* Compile the actual pinned provider and export target-derived layout bytes. */
#include "firehose_buffer.c"
__attribute__((used,section("__DATA_CONST,__s24fh")))
const unsigned long long s24_firehose_provider[] = {
    MAX_CPUS, MAX_CPU_CLUSTERS, sizeof(void *),
    sizeof(struct firehose_buffer_header_s), sizeof(union firehose_buffer_u),
    sizeof(struct firehose_buffer_stream_s), sizeof(struct firehose_tracepoint_s),
    __builtin_offsetof(struct firehose_tracepoint_s, ft_data),
    __builtin_offsetof(struct firehose_buffer_header_s, fbh_unused)
};
