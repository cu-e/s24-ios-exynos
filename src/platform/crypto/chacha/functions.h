#ifndef S24_CHACHA_FUNCTIONS_H
#define S24_CHACHA_FUNCTIONS_H
#include "chacha.h"
#include <libkern/crypto/register_crypto.h>
/* Experimental table; incnonce unsupported, all-ten qualification false. */
ccchacha20poly1305_fns_t s24_chacha20poly1305_experimental_functions(void);
int s24_chacha20poly1305_fill(struct ccchacha20poly1305_fns *);
#ifdef CHACHA_CPU_FIXTURE
int s24_chacha_cpu_prepare(void);
#endif
#endif
