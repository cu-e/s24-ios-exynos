/* Owned software-only primitive profile. No heap, entropy or ISA dispatch. */
#ifndef S24_CHACHA_PROFILE_H
#define S24_CHACHA_PROFILE_H
#define MBEDTLS_CHACHA20_C
#define MBEDTLS_POLY1305_C
#define MBEDTLS_PLATFORM_NO_STD_FUNCTIONS
#define MBEDTLS_PLATFORM_ZEROIZE_ALT
#if defined(MBEDTLS_CHACHA20_ALT) || defined(MBEDTLS_POLY1305_ALT) || defined(MBEDTLS_HAVE_ASM)
#error Unqualified ChaCha/Poly1305 primitive profile
#endif
#endif
