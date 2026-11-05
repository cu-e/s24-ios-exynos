/* Experimental explicit-nonce subset; actual selected public declarations. */
#ifndef S24_CHACHA_H
#define S24_CHACHA_H
#include <corecrypto/ccchacha20poly1305.h>
#define S24_CHACHA_COMPLETE_TABLE_QUALIFIED 0
/* These prototypes match the genuine selected method signatures.
 * No provider registration. Streamed plaintext is unauthenticated until verify. */
const struct ccchacha20poly1305_info *s24_chacha_info(void);
int s24_chacha_init(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,const uint8_t *);
int s24_chacha_reset(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *);
int s24_chacha_setnonce(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,const uint8_t *);
/* Unsupported gate; never mutates nonce/context and never returns success. */
int s24_chacha_incnonce(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,uint8_t *);
int s24_chacha_aad(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,size_t,const void *);
int s24_chacha_encrypt(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,size_t,const void *,void *);
int s24_chacha_decrypt(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,size_t,const void *,void *);
int s24_chacha_finalize(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,uint8_t *);
int s24_chacha_verify(const struct ccchacha20poly1305_info *,ccchacha20poly1305_ctx *,const uint8_t *);
void s24_chacha20poly1305_clear(ccchacha20poly1305_ctx *);
#endif
