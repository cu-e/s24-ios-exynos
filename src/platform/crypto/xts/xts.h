/* Owned full-block XTS bridge; actual selected XNU declarations, not SDK replicas. */
#ifndef S24_XTS_H
#define S24_XTS_H
#include <corecrypto/ccmode_impl.h>
#define S24_XTS_MAX_BLOCKS ((size_t)1 << 20)
/* Initialize once, then retain immutable descriptor throughout context lifetime.
 * decrypt must be 0 or 1. No crypto provider is registered by this function. */
int s24_xts_descriptor(struct ccmode_xts *mode, int decrypt);
void s24_xts_clear_key(ccxts_ctx *ctx);
void s24_xts_clear_tweak(ccxts_tweak *ctx);
#endif
