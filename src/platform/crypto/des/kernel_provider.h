/* Owned selected-kernel DES publication interface; genuine declarations. */
#ifndef S24_KERNEL_DES_PROVIDER_H
#define S24_KERNEL_DES_PROVIDER_H
#include "des.h"
#define S24_KERNEL_DES_CONTEXT_BYTES 144
#define S24_KERNEL_TDES_CONTEXT_BYTES 400
/* Static const modes require exact descriptor identity on init. Contexts retain
 * accepted DES lifetime/alignment/serialization rules. Selected keys are8/24
 * bytes: the backend's local16-byte EDE2 extension is not published here.
 * Optional roundkey remains NULL/unsupported; no general/private ABI claim. */
extern const struct ccmode_ecb s24_kernel_des_ecb_encrypt,s24_kernel_des_ecb_decrypt;
extern const struct ccmode_ecb s24_kernel_tdes_ecb_encrypt,s24_kernel_tdes_ecb_decrypt;
extern const struct ccmode_cbc s24_kernel_des_cbc_encrypt,s24_kernel_des_cbc_decrypt;
extern const struct ccmode_cbc s24_kernel_tdes_cbc_encrypt,s24_kernel_tdes_cbc_decrypt;
int s24_kernel_des_prepare(void);
const struct ccmode_ecb *s24_kernel_des_ecb_mode(int triple,int decrypt);
const struct ccmode_cbc *s24_kernel_des_cbc_mode(int triple,int decrypt);
/* Genuine register_crypto helper signatures. Exactly8 bytes admitted, weak
 * ignores parity/nonmutating; parity invalid/pre-ready is a no-op. */
int s24_kernel_des_key_is_weak(void *,unsigned long);
void s24_kernel_des_key_set_odd_parity(void *,unsigned long);
#endif
