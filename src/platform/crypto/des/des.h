/* Owned narrow bridge using genuine selected XNU declarations. */
#ifndef S24_DES_H
#define S24_DES_H
#include <corecrypto/ccmode_impl.h>
/* Retain an unchanged factory descriptor for the entire context lifetime.
 * triple/decrypt are exactly 0 or 1. roundkey is unsupported (NULL).
 * DES accepts 8 bytes; TDES accepts selected 24 bytes plus local EDE2 16 bytes.
 * No provider registration, allocation or external key retention. */
int s24_des_ecb_descriptor(struct ccmode_ecb *, int triple, int decrypt);
int s24_des_cbc_descriptor(struct ccmode_cbc *, int triple, int decrypt);
int s24_des_ecb_clear(const struct ccmode_ecb *, ccecb_ctx *);
int s24_des_cbc_clear(const struct ccmode_cbc *, cccbc_ctx *);
/* Actual selected register_crypto helper signatures; exactly 8 bytes admitted.
 * Weak classification ignores parity, does not modify key; invalid => nonzero.
 * Parity changes only the low bit of each byte; invalid length/NULL => no-op. */
int s24_des_key_is_weak(void *, unsigned long);
void s24_des_key_set_odd_parity(void *, unsigned long);
#endif
