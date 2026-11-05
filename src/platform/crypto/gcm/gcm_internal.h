/* Owned implementation layout, exposed to boundary tests, not an Apple ABI. */
#ifndef S24_GCM_INTERNAL_H
#define S24_GCM_INTERNAL_H
#include "gcm.h"
#include <mbedtls/gcm.h>
#include <stdint.h>
struct __attribute__((aligned(16))) s24_gcm_state {
    mbedtls_gcm_context seed, active;
    uint64_t magic;
    uintptr_t owner;
    uint64_t text_bytes, aad_bytes;
    uint32_t phase, decrypt, managed, key_bytes;
    unsigned char nonce[12];
};
#endif
