#ifndef S24_CHACHA_FUNCTIONS_H
#define S24_CHACHA_FUNCTIONS_H
#include "chacha.h"
#include <libkern/crypto/register_crypto.h>
/* Experimental table; incnonce unsupported, all-ten qualification false. */
ccchacha20poly1305_fns_t s24_chacha20poly1305_experimental_functions(void);
#endif
