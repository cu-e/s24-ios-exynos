#ifndef S24_CHACHA_INTERNAL_H
#define S24_CHACHA_INTERNAL_H
#include "chacha.h"
#include <mbedtls/chacha20.h>
#include <mbedtls/poly1305.h>
#include <stdint.h>
/* Owned self-contained state copied through genuine selected storage.
 * No foreign context pointer is retained or cast from the selected context. */
struct s24_chacha_state {
    mbedtls_chacha20_context chacha;
    mbedtls_poly1305_context poly;
    uint64_t aad_bytes,text_bytes;
    unsigned char nonce[12];
    uint32_t phase;
    uint64_t magic;
};
#endif
