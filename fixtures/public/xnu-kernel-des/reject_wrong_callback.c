/* Genuine selected callback negative, never linked as a provider. */
#include "kernel_provider.h"
static void wrong(const ccecb_ctx *ctx,size_t n,const void *in,void *out)
{(void)ctx;(void)n;(void)in;(void)out;}
const struct ccmode_ecb rejected_callback={.ecb=wrong};
