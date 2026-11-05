/* Actual selected registration typedefs are consumed, never recreated/cast. */
#include "gcm.h"
#include <libkern/crypto/register_crypto.h>
ccgcm_init_with_iv_fn_t const s24_gcm_init_type_witness=s24_gcm_init_with_iv;
ccgcm_inc_iv_fn_t const s24_gcm_inc_type_witness=s24_gcm_inc_iv;
_Static_assert(__builtin_types_compatible_p(__typeof__(&s24_gcm_init_with_iv),ccgcm_init_with_iv_fn_t),"genuine init helper type");
_Static_assert(__builtin_types_compatible_p(__typeof__(&s24_gcm_inc_iv),ccgcm_inc_iv_fn_t),"genuine nonce helper type");
