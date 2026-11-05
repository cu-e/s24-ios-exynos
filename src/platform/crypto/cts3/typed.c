/* Real selected typedefs, with no foreign schedule or callback pointer casts. */
#include "cts3.h"
#include <libkern/crypto/register_crypto.h>
ccpad_cts3_crypt_fn_t const s24_cts3_typed_encrypt=s24_cts3_encrypt;
ccpad_cts3_crypt_fn_t const s24_cts3_typed_decrypt=s24_cts3_decrypt;
