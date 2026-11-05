/* SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception */
#include <arm_neon.h>
static_assert(sizeof(uint8x16_t) == 16 && alignof(uint8x16_t) == 16);
static_assert(__builtin_xnu_type_summary(uint8x16_t) == 4);
static_assert(__builtin_xnu_type_summary(uint64x2_t) == 4);
static_assert(__builtin_xnu_type_signature(uint8x16_t)[0] == '2');
static_assert(__builtin_xnu_type_signature(uint8x16_t)[1] == '2');
struct GeneratedVectorSave { uint8x16_t vectors[2]; };
static_assert(sizeof(GeneratedVectorSave) == 32);
static_assert(__builtin_xnu_type_summary(GeneratedVectorSave) == 4);
unsigned generated_neon_metadata(void) { return __builtin_xnu_type_summary(GeneratedVectorSave); }
