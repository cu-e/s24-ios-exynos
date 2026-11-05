/* Test-only CBC-enabled canonical AES profile, not a production provider. */
#ifndef S24_CTS3_AES_PROFILE_H
#define S24_CTS3_AES_PROFILE_H
#define MBEDTLS_AES_C
#define MBEDTLS_AES_ROM_TABLES
#define MBEDTLS_CIPHER_MODE_CBC
#define MBEDTLS_PLATFORM_NO_STD_FUNCTIONS
#define MBEDTLS_PLATFORM_ZEROIZE_ALT
#if defined(MBEDTLS_AES_ALT) || defined(MBEDTLS_AESNI_C) || defined(MBEDTLS_AESCE_C) || defined(MBEDTLS_HAVE_ASM) || defined(MBEDTLS_PADLOCK_C) || defined(MBEDTLS_SELF_TEST)
#error Unqualified fixture AES profile
#endif
#endif
