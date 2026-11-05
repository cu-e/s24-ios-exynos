/* SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception */
#include <arm_neon.h>
#include <arm_acle.h>

struct NeonAndPointer { uint8x16_t lanes; void *pointer; };
_Static_assert(sizeof(uint8x8_t) == 8 && _Alignof(uint8x8_t) == 8, "narrow vector");
_Static_assert(sizeof(uint8x16_t) == 16 && _Alignof(uint8x16_t) == 16, "wide vector");
_Static_assert(sizeof(uint16x8_t) == 16 && sizeof(uint32x4_t) == 16, "integer lanes");
_Static_assert(sizeof(uint64x2_t) == 16 && sizeof(float32x4_t) == 16, "wide lanes");
_Static_assert(sizeof(float64x2_t) == 16 && sizeof(bfloat16_t) == 2, "float lanes");
_Static_assert(sizeof(struct NeonAndPointer) == 32, "aggregate storage");
_Static_assert(__builtin_offsetof(struct NeonAndPointer, pointer) == 16, "pointer placement");
__attribute__((used,section("__DATA_CONST,__s24neon")))
const unsigned long long s24_neon_layout[] = {
    sizeof(uint8x8_t), _Alignof(uint8x8_t), sizeof(uint8x16_t), _Alignof(uint8x16_t),
    sizeof(uint16x8_t), sizeof(uint32x4_t), sizeof(uint64x2_t), sizeof(float32x4_t),
    sizeof(float64x2_t), sizeof(bfloat16_t), sizeof(struct NeonAndPointer),
    __builtin_offsetof(struct NeonAndPointer, pointer)
};
uint8x16_t neon_add(uint8x16_t a, uint8x16_t b) { return vaddq_u8(a, b); }
uint16x8_t neon_widen(uint8x16_t a) { return vpaddlq_u8(a); }
uint32x4_t neon_adler_step(uint32x4_t sum, uint16x8_t bytes, uint16x8_t weights)
{
    sum = vmlal_u16(sum, vget_low_u16(bytes), vget_low_u16(weights));
    return vmlal_high_u16(sum, bytes, weights);
}
void neon_mix(uint8_t *dst, const uint8_t *a, const uint8_t *b)
{
    vst1q_u8(dst, veorq_u8(vld1q_u8(a), vld1q_u8(b)));
}
uint32_t neon_sum(uint32x4_t a) { return vaddvq_u32(a); }
unsigned neon_constant(void)
{
    return vgetq_lane_u8(vaddq_u8(vdupq_n_u8(17), vdupq_n_u8(35)), 7);
}
