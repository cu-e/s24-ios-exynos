/* Real negative compilation against selected declarations; never a provider. */
#include "kernel_provider.h"
static int wrong_return(const ccxts_ctx *key,ccxts_tweak *t,size_t blocks,const void *in,void *out)
{ (void)key;(void)t;(void)blocks;(void)in;(void)out;return CCERR_PARAMETER; }
const struct ccmode_xts rejected_signature={.xts=wrong_return};
