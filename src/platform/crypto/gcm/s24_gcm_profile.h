/* Fixed no-heap GCM profile; shares the accepted software AES configuration. */
#ifndef S24_GCM_PROFILE_H
#define S24_GCM_PROFILE_H
#include "../xts/s24_xts_profile.h"
#define MBEDTLS_GCM_C
#define MBEDTLS_BLOCK_CIPHER_C
#if defined(MBEDTLS_GCM_ALT) || defined(MBEDTLS_CIPHER_C) || defined(MBEDTLS_PSA_CRYPTO_C) || defined(MBEDTLS_USE_PSA_CRYPTO) || defined(MBEDTLS_BLOCK_CIPHER_SOME_PSA) || defined(MBEDTLS_GCM_LARGE_TABLE)
#error Unqualified GCM allocation/backend profile
#endif
/* Namespace only newly owned backend symbols; AES and zeroizer remain shared. */
#define mbedtls_gcm_init s24_gcm_backend_init
#define mbedtls_gcm_free s24_gcm_backend_free
#define mbedtls_gcm_setkey s24_gcm_backend_setkey
#define mbedtls_gcm_starts s24_gcm_backend_starts
#define mbedtls_gcm_update_ad s24_gcm_backend_update_ad
#define mbedtls_gcm_update s24_gcm_backend_update
#define mbedtls_gcm_finish s24_gcm_backend_finish
#define mbedtls_gcm_crypt_and_tag s24_gcm_backend_crypt_and_tag
#define mbedtls_gcm_auth_decrypt s24_gcm_backend_auth_decrypt
#define mbedtls_block_cipher_free s24_gcm_backend_block_free
#define mbedtls_block_cipher_setup s24_gcm_backend_block_setup
#define mbedtls_block_cipher_setkey s24_gcm_backend_block_setkey
#define mbedtls_block_cipher_encrypt s24_gcm_backend_block_encrypt
#define mbedtls_ct_zero s24_gcm_backend_ct_zero
#define mbedtls_ct_memcmp s24_gcm_backend_ct_memcmp
#define mbedtls_ct_memcmp_partial s24_gcm_backend_ct_memcmp_partial
#define mbedtls_ct_memmove_left s24_gcm_backend_ct_memmove_left
#define mbedtls_ct_memcpy_if s24_gcm_backend_ct_memcpy_if
#define mbedtls_ct_memcpy_offset s24_gcm_backend_ct_memcpy_offset
#define mbedtls_ct_zeroize_if s24_gcm_backend_ct_zeroize_if
#endif
