/* Compiled against genuine selected kernel headers, not a signature replica. */
#include "des.h"
#include <libkern/crypto/des.h>
#include <libkern/crypto/register_crypto.h>
ccdes_key_is_weak_fn_t const s24_des_typed_weak=s24_des_key_is_weak;
ccdes_key_set_odd_parity_fn_t const s24_des_typed_parity=s24_des_key_set_odd_parity;
const unsigned long long s24_des_storage[]={sizeof(((des_ecb_key_schedule*)0)->enc),sizeof(((des3_ecb_key_schedule*)0)->enc),sizeof(ccdes_key_is_weak_fn_t),sizeof(ccdes_key_set_odd_parity_fn_t)};
_Static_assert(sizeof(((des_ecb_key_schedule*)0)->enc)==256,"genuine DES schedule slot");
_Static_assert(sizeof(((des3_ecb_key_schedule*)0)->enc)==768,"genuine TDES schedule slot");
