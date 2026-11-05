/* Owned fixed-container callback pair; genuine selected XNU declarations. */
#ifndef S24_CRYPTO_RSA_H
#define S24_CRYPTO_RSA_H
#include <corecrypto/ccrsa.h>
#include <libkern/crypto/rsa.h>
#define S24_RSA_MAX_BYTES (RSA_MAX_KEY_BITSIZE / 8)
#define S24_RSA_OID_PAYLOAD_MAX 32u
#define S24_RSA_DIGEST_MAX 64u
/* Caller supplies an actual rsa_pub_ctx and prewrites n=ccn_nof(4096).
 * Failure preserves the entire destination. N/E are copied, not borrowed. */
int s24_rsa_make_pub(ccrsa_pub_ctx_t, size_t, const uint8_t *, size_t, const uint8_t *);
/* Valid output must be writable and disjoint from all input extents. Invalid
 * output aliases or nonrepresentable pointer extents are rejected transactionally
 * without writing any storage. With those preconditions, *valid is cleared on
 * entry and only set for verified padding AND recovered-digest equality.
 * The OID must be readable for its DER-declared extent; ABI has no span argument. */
int s24_rsa_verify_pkcs1v15(ccrsa_pub_ctx_t, const uint8_t *, size_t,
    const uint8_t *, size_t, const uint8_t *, bool *);
extern const unsigned long long s24_rsa_layout[8];
#endif
