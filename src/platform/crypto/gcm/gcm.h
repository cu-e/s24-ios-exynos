/* Owned typed adapter; actual selected XNU declarations, never SDK replicas. */
#ifndef S24_GCM_H
#define S24_GCM_H
#include <corecrypto/ccmode_impl.h>
#define S24_GCM_CONTEXT_CAPACITY 2048
/* Retain descriptor throughout context lifetime; decrypt is exactly 0 or 1. */
int s24_gcm_descriptor(struct ccmode_gcm *mode, int decrypt);
int s24_gcm_init_with_iv(const struct ccmode_gcm *, ccgcm_ctx *, size_t, const void *, const void *);
int s24_gcm_inc_iv(const struct ccmode_gcm *, ccgcm_ctx *, void *);
/* Explicit destruction loses per-context nonce authority: external uniqueness remains required. */
void s24_gcm_clear(ccgcm_ctx *ctx);
#endif
