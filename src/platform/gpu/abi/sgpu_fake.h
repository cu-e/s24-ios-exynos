/* Host-only synthetic protocol peer; never include in a native driver target. */
#ifndef S24_SGPU_FAKE_H
#define S24_SGPU_FAKE_H
#include "sgpu_abi.h"
#ifdef __cplusplus
extern "C" {
#endif
struct sgpu_fake { uint64_t calls; uint32_t stopped, reserved; };
uint32_t sgpu_fake_exchange(struct sgpu_fake *, const void *, size_t, void *, size_t, size_t *);
#ifdef __cplusplus
}
#endif
#endif
