/* Owned ABI/lifecycle glue. AES primitive: Mbed TLS, see vendor/NOTICE.md.
 * GF(2^128) progression and XEX construction adapted from library/aes.c at
 * 068ff080b369adfac81509f9b57b2afabaf82dc5, Apache-2.0 choice.
 * Copyright The Mbed TLS Contributors (upstream primitive/mode construction).
 * No restricted Apple implementation is copied here.
 */
#include "xts.h"
#include <mbedtls/aes.h>
#include <mbedtls/platform_util.h>
#include <stdint.h>
#include <string.h>

struct __attribute__((aligned(16))) key_state {
    mbedtls_aes_context data, tweak;
    uint64_t magic, generation;
    unsigned key_bytes, decrypt;
};
struct __attribute__((aligned(16))) tweak_state {
    uint64_t magic, generation;
    uintptr_t owner;
    size_t blocks;
    unsigned char value[16];
};
#define KEY_MAGIC UINT64_C(0x5854534b45593131)
#define TWEAK_MAGIC UINT64_C(0x58545354574b3131)
_Static_assert(sizeof(struct key_state) <= 1072, "actual selected symmetric_xts storage");
_Static_assert(_Alignof(struct key_state) == 16, "key alignment");
_Static_assert(_Alignof(struct tweak_state) == 16, "tweak alignment");
_Static_assert(_Alignof(ccxts_ctx) == 16 && _Alignof(ccxts_tweak) == 16, "selected opaque alignment");
/* Export numeric measurements for independent target-object decoding. */
const unsigned long long s24_xts_layout[] = {sizeof(struct key_state), _Alignof(struct key_state),
    sizeof(struct tweak_state), _Alignof(struct tweak_state), sizeof(mbedtls_aes_context), sizeof(struct ccmode_xts)};
static uint64_t generation;

/* Genuine MBEDTLS_PLATFORM_ZEROIZE_ALT implementation: observable volatile stores. */
void mbedtls_platform_zeroize(void *p, size_t n)
{
    volatile unsigned char *q = p;
    while (n--) *q++ = 0;
    __asm__ volatile("" : : "r"(p) : "memory");
}
static int extent(const void *p, size_t n)
{
    return p && (uintptr_t)p <= UINTPTR_MAX - n;
}
static int aligned(const void *p) { return p && !((uintptr_t)p & 15); }
static int overlap(const void *a, size_t an, const void *b, size_t bn)
{
    return (uintptr_t)a < (uintptr_t)b + bn && (uintptr_t)b < (uintptr_t)a + an;
}
void s24_xts_clear_key(ccxts_ctx *ctx)
{
    if (aligned(ctx) && extent(ctx, sizeof(struct key_state))) mbedtls_platform_zeroize(ctx, sizeof(struct key_state));
}
void s24_xts_clear_tweak(ccxts_tweak *ctx)
{
    if (aligned(ctx) && extent(ctx, sizeof(struct tweak_state))) mbedtls_platform_zeroize(ctx, sizeof(struct tweak_state));
}
static int valid_key(const struct key_state *s)
{
    unsigned rounds = s->key_bytes == 16 ? 10 : 14;
    return s->magic == KEY_MAGIC && s->generation && s->decrypt <= 1 &&
        (s->key_bytes == 16 || s->key_bytes == 32) &&
        s->data.MBEDTLS_PRIVATE(nr) == (int)rounds && s->tweak.MBEDTLS_PRIVATE(nr) == (int)rounds &&
        s->data.MBEDTLS_PRIVATE(rk_offset) == 0 && s->tweak.MBEDTLS_PRIVATE(rk_offset) == 0;
}
static int initialize(const struct ccmode_xts *mode, ccxts_ctx *ctx, size_t n,
                      const void *key, const void *tweak, unsigned decrypt)
{
    struct key_state s;
    int result = CCERR_PARAMETER;
    memset(&s, 0, sizeof(s));
    if (!aligned(ctx) || !extent(ctx, sizeof(s))) return result;
    /* Input overlap is rejected before clearing destination storage. */
    int inputs_ok = (n == 16 || n == 32) && extent(key, n) && extent(tweak, n) &&
        !overlap(ctx, sizeof(s), key, n) && !overlap(ctx, sizeof(s), tweak, n);
    if (mode && extent(mode, sizeof(*mode)) && overlap(ctx, sizeof(s), mode, sizeof(*mode))) return result;
    s24_xts_clear_key(ctx);
    if (!extent(mode, sizeof(*mode)) || mode->size != sizeof(s) || mode->tweak_size != sizeof(struct tweak_state) ||
        mode->block_size != 16 || !inputs_ok) goto done;
    unsigned char different = 0;
    const unsigned char *a = key, *b = tweak;
    for (size_t i = 0; i < n; ++i) different |= a[i] ^ b[i];
    if (!different) goto done;
    mbedtls_aes_init(&s.data); mbedtls_aes_init(&s.tweak);
    if ((decrypt ? mbedtls_aes_setkey_dec(&s.data, key, (unsigned)n * 8) :
                   mbedtls_aes_setkey_enc(&s.data, key, (unsigned)n * 8)) ||
        mbedtls_aes_setkey_enc(&s.tweak, tweak, (unsigned)n * 8)) { result = CCERR_INTERNAL; goto done; }
    uint64_t old = __atomic_load_n(&generation, __ATOMIC_RELAXED);
    do {
        if (old == UINT64_MAX) { result = CCERR_OVERFLOW; goto done; }
    } while (!__atomic_compare_exchange_n(&generation, &old, old + 1, 0, __ATOMIC_RELAXED, __ATOMIC_RELAXED));
    s.magic = KEY_MAGIC; s.generation = old + 1; s.key_bytes = (unsigned)n; s.decrypt = decrypt;
    if (!valid_key(&s)) { result = CCERR_INTERNAL; goto done; }
    memcpy(ctx, &s, sizeof(s)); result = CCERR_OK;
done:
    mbedtls_platform_zeroize(&s, sizeof(s)); return result;
}
static int enc_init(const struct ccmode_xts *m, ccxts_ctx *c, size_t n, const void *k, const void *t)
{ return initialize(m, c, n, k, t, 0); }
static int dec_init(const struct ccmode_xts *m, ccxts_ctx *c, size_t n, const void *k, const void *t)
{ return initialize(m, c, n, k, t, 1); }
static void enc_sched(const struct ccmode_xts *m, ccxts_ctx *c, size_t n, const void *k, const void *t)
{ (void)enc_init(m, c, n, k, t); }
static void dec_sched(const struct ccmode_xts *m, ccxts_ctx *c, size_t n, const void *k, const void *t)
{ (void)dec_init(m, c, n, k, t); }
static int set_tweak(const ccxts_ctx *ctx, ccxts_tweak *tw, const void *iv)
{
    struct key_state s;
    struct tweak_state t;
    unsigned char raw[16];
    int result = CCERR_PARAMETER;
    if (!aligned(ctx) || !extent(ctx, sizeof(s)) || !aligned(tw) || !extent(tw, sizeof(t)) ||
        overlap(ctx, sizeof(s), tw, sizeof(t))) return result;
    memset(&s, 0, sizeof(s)); memset(&t, 0, sizeof(t)); memset(raw, 0, sizeof(raw));
    if (!extent(iv, 16) || overlap(tw, sizeof(t), iv, 16)) goto done;
    memcpy(&s, ctx, sizeof(s));
    if (!valid_key(&s)) { result = CCERR_CALL_SEQUENCE; goto done; }
    memcpy(raw, iv, sizeof(raw));
    if (mbedtls_aes_crypt_ecb(&s.tweak, MBEDTLS_AES_ENCRYPT, raw, t.value)) { result = CCERR_INTERNAL; goto done; }
    t.magic = TWEAK_MAGIC; t.generation = s.generation; t.owner = (uintptr_t)ctx;
    memcpy(tw, &t, sizeof(t)); result = CCERR_OK;
done:
    if (result) s24_xts_clear_tweak(tw);
    mbedtls_platform_zeroize(&s, sizeof(s)); mbedtls_platform_zeroize(&t, sizeof(t));
    mbedtls_platform_zeroize(raw, sizeof(raw)); return result;
}
/* Same little-endian polynomial convention as pinned mbedtls_gf128mul_x_ble.
 * Bytewise adaptation avoids alignment and host-endian assumptions. */
static void advance(unsigned char t[16])
{
    unsigned carry = 0;
    for (unsigned i = 0; i < 16; ++i) { unsigned next = t[i] >> 7; t[i] = (unsigned char)((t[i] << 1) | carry); carry = next; }
    t[0] ^= (unsigned char)(0x87 & (0U - carry));
}
static void *crypt_blocks(const ccxts_ctx *ctx, ccxts_tweak *tw, size_t blocks,
                          const void *input, void *output, unsigned decrypt)
{
    struct key_state s;
    struct tweak_state t;
    unsigned char x[16];
    void *result = NULL;
    if (!aligned(ctx) || !extent(ctx, sizeof(s)) || !aligned(tw) || !extent(tw, sizeof(t)) ||
        overlap(ctx, sizeof(s), tw, sizeof(t))) return NULL;
    memcpy(&s, ctx, sizeof(s)); memcpy(&t, tw, sizeof(t)); memset(x, 0, sizeof(x));
    if (!valid_key(&s) || s.decrypt != decrypt || t.magic != TWEAK_MAGIC ||
        t.owner != (uintptr_t)ctx || t.generation != s.generation || t.blocks > S24_XTS_MAX_BLOCKS ||
        blocks > S24_XTS_MAX_BLOCKS - t.blocks || blocks > SIZE_MAX / 16) goto done;
    size_t bytes = blocks * 16;
    if (!blocks) { result = tw; goto done; }
    if (!extent(input, bytes) || !extent(output, bytes) ||
        overlap(ctx, sizeof(s), input, bytes) || overlap(ctx, sizeof(s), output, bytes) ||
        overlap(tw, sizeof(t), input, bytes) || overlap(tw, sizeof(t), output, bytes) ||
        (input != output && overlap(input, bytes, output, bytes))) goto done;
    const unsigned char *in = input;
    unsigned char *out = output;
    for (size_t i = 0; i < blocks; ++i) {
        for (unsigned j = 0; j < 16; ++j) x[j] = in[16*i+j] ^ t.value[j];
        if (mbedtls_aes_crypt_ecb(&s.data, decrypt ? MBEDTLS_AES_DECRYPT : MBEDTLS_AES_ENCRYPT, x, x)) {
            /* Unexpected backend failure: erase any produced output and invalidate tweak. */
            mbedtls_platform_zeroize(output, bytes); s24_xts_clear_tweak(tw); goto done;
        }
        for (unsigned j = 0; j < 16; ++j) out[16*i+j] = x[j] ^ t.value[j];
        advance(t.value);
    }
    t.blocks += blocks; memcpy(tw, &t, sizeof(t)); result = tw;
done:
    mbedtls_platform_zeroize(&s, sizeof(s)); mbedtls_platform_zeroize(&t, sizeof(t));
    mbedtls_platform_zeroize(x, sizeof(x)); return result;
}
static void *enc_blocks(const ccxts_ctx *c, ccxts_tweak *t, size_t n, const void *i, void *o)
{ return crypt_blocks(c,t,n,i,o,0); }
static void *dec_blocks(const ccxts_ctx *c, ccxts_tweak *t, size_t n, const void *i, void *o)
{ return crypt_blocks(c,t,n,i,o,1); }
int s24_xts_descriptor(struct ccmode_xts *mode, int decrypt)
{
    if (!mode || !extent(mode, sizeof(*mode)) || (decrypt != 0 && decrypt != 1)) return CCERR_PARAMETER;
    /* Typed volatile field stores avoid copying absolute linked virtual function
     * addresses into the MMU-off synthetic guest. They also test actual calls. */
    volatile struct ccmode_xts *m = mode;
    m->size = sizeof(struct key_state); m->tweak_size = sizeof(struct tweak_state); m->block_size = 16;
    m->init = decrypt ? dec_init : enc_init; m->key_sched = decrypt ? dec_sched : enc_sched;
    m->set_tweak = set_tweak; m->xts = decrypt ? dec_blocks : enc_blocks;
    m->custom = NULL; m->custom1 = NULL; m->impl = CC_IMPL_AES_XTS_GENERIC;
    return CCERR_OK;
}
