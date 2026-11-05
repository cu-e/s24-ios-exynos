/* Native genuine table typing; no replacement ABI records or function casts. */
#include "functions.h"
#include <corecrypto/cc_error.h>
#define BINDINGS(X) X(info) X(init) X(reset) X(setnonce) X(incnonce) X(aad) X(encrypt) X(finalize) X(decrypt) X(verify)
#define CONSTANT(name) .name=s24_chacha_##name,
#ifndef CHACHA_CPU_FIXTURE
static const struct ccchacha20poly1305_fns functions={
    BINDINGS(CONSTANT)
};
ccchacha20poly1305_fns_t s24_chacha20poly1305_experimental_functions(void) { return &functions; }
#else
/* Single-thread synthetic fixture only. Prepared before the unchanged suite;
 * never a mutable provider singleton or a kernel registration mechanism. */
static struct ccchacha20poly1305_fns cpu_functions;
int s24_chacha_cpu_prepare(void) { return s24_chacha20poly1305_fill(&cpu_functions); }
ccchacha20poly1305_fns_t s24_chacha20poly1305_experimental_functions(void) { return &cpu_functions; }
#endif
#undef CONSTANT
const unsigned long long s24_chacha_table_layout[]={sizeof(struct ccchacha20poly1305_fns),_Alignof(struct ccchacha20poly1305_fns)};
int s24_chacha20poly1305_fill(struct ccchacha20poly1305_fns *out)
{
    if(!out || ((uintptr_t)out&7) || (uintptr_t)out>UINTPTR_MAX-sizeof(*out))return CCERR_PARAMETER;
    /* Accepted owned XTS descriptor pattern: volatile genuine typed stores
     * force actual PC-relative runtime addresses in the MMU-off fixture.
     * The static native table has a separate relocation proof. */
    volatile struct ccchacha20poly1305_fns *table=out;
#define STORE(name) table->name=s24_chacha_##name;
    BINDINGS(STORE)
#undef STORE
    return CCERR_OK;
}
#undef BINDINGS
