/* Owned generic CBC-CS3 callback bridge; genuine selected declarations only. */
#ifndef S24_CTS3_H
#define S24_CTS3_H
#include <corecrypto/ccpad.h>
/* Initialized immutable CBC mode/context of the matching direction required.
 * Exactly nbytes on success,0 on failure; nbytes must exceed block_size.
 * Admission errors preserve all buffers. Backend errors clear advertised output
 * and preserve caller IV; exact in-place input is therefore cleared on failure.
 * Caller supplies actual allocations and must honor the result. No provider. */
size_t s24_cts3_encrypt(const struct ccmode_cbc *,cccbc_ctx *,cccbc_iv *,size_t,const void *,void *);
size_t s24_cts3_decrypt(const struct ccmode_cbc *,cccbc_ctx *,cccbc_iv *,size_t,const void *,void *);
#endif
