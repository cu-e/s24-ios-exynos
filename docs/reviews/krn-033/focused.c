/* Independent owned review probe; genuine selected headers and frozen objects. */
#include "gcm_internal.h"
#include <corecrypto/ccmode.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned checks;
#define C(x) do { ++checks; if (!(x)) { printf("GCM REVIEW FAIL line=%u checks=%u\n", __LINE__, checks); return 1; } } while (0)
#define SAME() C(memcmp(before, ctx, enc.size) == 0)
#define SAVE() memcpy(before, ctx, enc.size)

int main(void)
{
    struct ccmode_gcm enc, dec, bad;
    C(s24_gcm_descriptor(&enc, 0) == 0);
    C(s24_gcm_descriptor(&dec, 1) == 0);
    C(enc.size == sizeof(struct s24_gcm_state) && enc.size == 1312 && enc.size == dec.size);
    C(enc.block_size == 16 && _Alignof(ccgcm_ctx) == 16);
    /* Actual descriptor-sized allocation, with16 bytes of guard on each side. */
    ccgcm_ctx_decl(enc.size + 32, allocation);
    ccgcm_ctx *ctx = (ccgcm_ctx *)(void *)((unsigned char *)allocation + 16);
    ccgcm_ctx_decl(enc.size, copy);
    unsigned char before[enc.size], key[32] = {0}, iv[12] = {0};
    unsigned char text[33], snapshot[33], tag[17], nonce[12];
    const unsigned char ciphertext[16] = {0x03,0x88,0xda,0xce,0x60,0xb6,0xa3,0x92,0xf3,0x28,0xc2,0xb9,0x71,0xb2,0xfe,0x78};
    const unsigned char block_tag[16] = {0xab,0x6e,0x47,0xd4,0x2c,0xec,0x13,0xbd,0xf5,0x3a,0x67,0xb2,0x12,0x57,0xbd,0xdf};
    const unsigned char empty_tag[16] = {0x58,0xe2,0xfc,0xce,0xfa,0x7e,0x30,0x61,0x36,0x7f,0x1d,0x57,0xa4,0xe7,0x45,0x5a};
    memset(allocation, 0xa5, enc.size + 32);
    memset(ctx, 0, enc.size);
    C(enc.init(&enc, ctx, 16, key) == 0);
    SAVE(); C(enc.set_iv(ctx, 0, iv) == CCERR_PARAMETER); SAME();
    C(enc.set_iv(ctx, sizeof(iv), iv) == 0);
    SAVE(); C(enc.gmac(ctx, 1, ctx) == CCERR_PARAMETER); SAME();
    C(enc.gcm(ctx, 0, NULL, NULL) == 0); SAME();
    memset(text, 0, sizeof(text)); memcpy(snapshot, text, sizeof(text));
    C(enc.gcm(ctx, 16, text, text + 1) == CCERR_PARAMETER); SAME();
    C(memcmp(text, snapshot, sizeof(text)) == 0);
    C(enc.gcm(ctx, 16, (void *)(UINTPTR_MAX - 7), text) == CCERR_PARAMETER); SAME();
    C(enc.gcm(ctx, 16, text, ctx) == CCERR_PARAMETER); SAME();
    C(enc.gcm(ctx, 1, text, text) == 0);
    C(text[0] == ciphertext[0] && text[1] == 0);
    SAVE(); C(enc.gmac(ctx, 0, NULL) == CCERR_CALL_SEQUENCE); SAME();
    C(enc.gcm(ctx, 15, text + 1, text + 1) == 0);
    C(memcmp(text, ciphertext, 16) == 0 && text[16] == 0);
    SAVE(); memset(tag, 0xa5, sizeof(tag));
    C(enc.finalize(ctx, 3, tag) == CCERR_PARAMETER); SAME(); C(tag[0] == 0xa5);
    C(enc.finalize(ctx, 17, tag) == CCERR_PARAMETER); SAME(); C(tag[0] == 0xa5);
    C(enc.finalize(ctx, 16, (void *)(UINTPTR_MAX - 7)) == CCERR_PARAMETER); SAME();
    C(enc.finalize(ctx, 16, ctx) == CCERR_PARAMETER); SAME();
    C(enc.finalize(ctx, 16, tag) == 0);
    C(memcmp(tag, block_tag, 16) == 0 && tag[16] == 0xa5);
    SAVE(); C(enc.finalize(ctx, 16, tag) == CCERR_CALL_SEQUENCE); SAME();
    s24_gcm_clear(ctx);

    C(dec.init(&dec, ctx, 16, key) == 0);
    C(dec.set_iv(ctx, sizeof(iv), iv) == 0);
    memcpy(text, ciphertext, 16);
    C(dec.gcm(ctx, 7, text, text) == 0);
    for (unsigned i = 0; i < 7; i++) C(text[i] == 0); /* Immediate provisional plaintext. */
    C(dec.gcm(ctx, 9, text + 7, text + 7) == 0);
    for (unsigned i = 0; i < 16; i++) C(text[i] == 0);
    memcpy(tag, block_tag, 16); tag[5] ^= 1;
    C(dec.finalize(ctx, 16, tag) == CCERR_INTEGRITY);
    C(memcmp(tag, block_tag, 16) == 0); /* Computed-tag overwrite even on mismatch. */
    for (unsigned i = 0; i < 16; i++) C(text[i] == 0); /* No retroactive authentication/wipe promise. */
    SAVE(); C(dec.gcm(ctx, 1, text, text) == CCERR_CALL_SEQUENCE); SAME();
    C(dec.reset(ctx) == 0);
    C(dec.set_iv(ctx, sizeof(iv), iv) == 0);
    memcpy(text, ciphertext, 16); C(dec.gcm(ctx, 16, text, text) == 0);
    memcpy(tag, block_tag, 4); C(dec.finalize(ctx, 4, tag) == 0);
    C(memcmp(tag, block_tag, 4) == 0);
    s24_gcm_clear(ctx);

    /* External key/IV mutation cannot change the owned key schedule/nonce. */
    C(s24_gcm_init_with_iv(&enc, ctx, 16, key, iv) == 0);
    memset(key, 0x6d, sizeof(key)); memset(iv, 0x7e, sizeof(iv));
    C(enc.finalize(ctx, 16, tag) == 0 && memcmp(tag, empty_tag, 16) == 0);
    C(enc.reset(ctx) == 0 && enc.reset(ctx) == 0);
    SAVE(); C(enc.init(&enc, ctx, 16, key) == CCERR_CALL_SEQUENCE); SAME();
    C(s24_gcm_init_with_iv(&dec, ctx, 16, key, iv) == CCERR_CALL_SEQUENCE); SAME();
    C(enc.set_iv(ctx, sizeof(iv), iv) == CCERR_CALL_SEQUENCE); SAME();
    memset(nonce, 0xa5, sizeof(nonce));
    C(s24_gcm_inc_iv(&dec, ctx, nonce) == CCERR_PARAMETER); SAME(); C(nonce[0] == 0xa5);
    C(s24_gcm_inc_iv(&enc, ctx, ctx) == CCERR_PARAMETER); SAME();
    bad = enc; bad.size++;
    C(s24_gcm_inc_iv(&bad, ctx, nonce) == CCERR_PARAMETER); SAME();
    memcpy(copy, ctx, enc.size);
    C(enc.reset(copy) == CCERR_CALL_SEQUENCE);
    C(s24_gcm_inc_iv(&enc, copy, nonce) == CCERR_CALL_SEQUENCE);
    C(memcmp(copy, before, enc.size) == 0);
    C(s24_gcm_inc_iv(&enc, ctx, nonce) == 0);
    for (unsigned i = 0; i < 11; i++) C(nonce[i] == 0);
    C(nonce[11] == 1);
    SAVE(); C(s24_gcm_inc_iv(&enc, ctx, nonce) == CCERR_CALL_SEQUENCE); SAME();
    s24_gcm_clear(ctx);

    memset(key, 0, sizeof(key)); memset(iv, 0, sizeof(iv));
    iv[0] = 1; iv[1] = 2; iv[2] = 3; iv[3] = 4; iv[11] = 0xff;
    C(s24_gcm_init_with_iv(&enc, ctx, 32, key, iv) == 0);
    C(enc.reset(ctx) == 0); /* Discard/reserve initial nonce without finalizing. */
    C(s24_gcm_inc_iv(&enc, ctx, nonce) == 0);
    C(memcmp(iv, nonce, 4) == 0 && nonce[10] == 1 && nonce[11] == 0);
    C(enc.reset(ctx) == 0 && enc.reset(ctx) == 0);
    C(s24_gcm_inc_iv(&enc, ctx, nonce) == 0 && nonce[10] == 1 && nonce[11] == 1);
    s24_gcm_clear(ctx);

    memset(iv + 4, 0xff, 8);
    C(s24_gcm_init_with_iv(&enc, ctx, 24, key, iv) == 0);
    C(enc.reset(ctx) == 0);
    SAVE(); memset(nonce, 0xa5, sizeof(nonce));
    C(s24_gcm_inc_iv(&enc, ctx, nonce) == CCERR_OVERFLOW); SAME();
    for (unsigned i = 0; i < sizeof(nonce); i++) C(nonce[i] == 0xa5);
    C(enc.reset(ctx) == 0); SAVE();
    C(s24_gcm_inc_iv(&enc, ctx, nonce) == CCERR_OVERFLOW); SAME();
    C(enc.init(&enc, ctx, 16, key) == CCERR_CALL_SEQUENCE); SAME();
    C(s24_gcm_init_with_iv(&enc, ctx, 24, key, iv) == CCERR_CALL_SEQUENCE); SAME();
    s24_gcm_clear(ctx);
    /* Destruction/reconstruction is explicitly an external uniqueness boundary. */
    C(s24_gcm_init_with_iv(&enc, ctx, 16, key, iv) == 0);
    s24_gcm_clear(ctx);
    for (size_t i = 0; i < enc.size; i++) C(((unsigned char *)ctx)[i] == 0);
    for (unsigned i = 0; i < 16; i++) {
        C(((unsigned char *)allocation)[i] == 0xa5);
        C(((unsigned char *)ctx)[enc.size + i] == 0xa5);
    }
    printf("GCM REVIEW PASS checks=%u context=%zu alignment=%zu\n", checks, enc.size, _Alignof(ccgcm_ctx));
    return 0;
}
