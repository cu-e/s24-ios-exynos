/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Test-only API; the generated implementation compiles genuine pinned source. */
#ifndef AUDIO_ORACLE_API_H
#define AUDIO_ORACLE_API_H
#include <stddef.h>
#include <stdint.h>
uint64_t oracle_value(unsigned index);
unsigned oracle_width(unsigned format);
unsigned oracle_physical_width(unsigned format);
void oracle_message(unsigned direction, unsigned kind, unsigned format,
                    unsigned rate, unsigned channels, unsigned period_bytes,
                    unsigned periods, unsigned pointer, void *out);
uint64_t oracle_pointer(unsigned direction, unsigned frame_bits, unsigned pointer);
uint64_t oracle_frame_bytes(unsigned frame_bits, unsigned frames);
#endif
