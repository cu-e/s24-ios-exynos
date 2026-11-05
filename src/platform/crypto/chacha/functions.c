/* Native genuine table typing; no replacement ABI records or function casts. */
#include "functions.h"
static const struct ccchacha20poly1305_fns functions={
    s24_chacha_info,s24_chacha_init,s24_chacha_reset,s24_chacha_setnonce,s24_chacha_incnonce,
    s24_chacha_aad,s24_chacha_encrypt,s24_chacha_finalize,s24_chacha_decrypt,s24_chacha_verify
};
const unsigned long long s24_chacha_table_layout[]={sizeof(functions),_Alignof(struct ccchacha20poly1305_fns)};
ccchacha20poly1305_fns_t s24_chacha20poly1305_experimental_functions(void) { return &functions; }
