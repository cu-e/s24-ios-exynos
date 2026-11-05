/* Compile-only negative: genuine callback must not accept a 32-bit count return. */
#include <libkern/crypto/register_crypto.h>
extern int cts3_incompatible_count_return(const struct ccmode_cbc *,cccbc_ctx *,cccbc_iv *,size_t,const void *,void *);
ccpad_cts3_crypt_fn_t cts3_rejected_return_signature=cts3_incompatible_count_return;
