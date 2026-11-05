/* Owned genuine-API/lifetime/nonce glue. Backend: Mbed TLS3.6.7 pinned in vendor,
 * Apache-2.0 choice; all upstream notices preserved. No Apple implementation.
 * Normal explicit-IV uniqueness and cross-context/persistent nonce authority
 * remain caller responsibilities. Streamed plaintext is not authenticated yet.
 */
#include "gcm_internal.h"
#include <corecrypto/ccmode.h>
#include <mbedtls/constant_time.h>
#include <mbedtls/platform_util.h>
#include <stdint.h>
#include <string.h>
#define MAGIC UINT64_C(0x47334d434f574e31)
#define WAIT_IV 1U
#define AAD 2U
#define DATA 3U
#define FINAL 4U
#define AAD_MAX (UINT64_MAX / 8)
static const unsigned char mode_token;
_Static_assert(sizeof(struct s24_gcm_state) <= S24_GCM_CONTEXT_CAPACITY, "bounded owned GCM storage");
_Static_assert(_Alignof(struct s24_gcm_state) == 16 && _Alignof(ccgcm_ctx) == 16, "actual selected alignment");
const unsigned long long s24_gcm_layout[] = {sizeof(struct s24_gcm_state),_Alignof(struct s24_gcm_state),sizeof(mbedtls_gcm_context),sizeof(mbedtls_block_cipher_context_t),sizeof(mbedtls_aes_context),sizeof(struct ccmode_gcm)};
static int extent(const void *p,size_t n) { return p && (uintptr_t)p <= UINTPTR_MAX-n; }
static int aligned(const void *p) { return p && !((uintptr_t)p&15); }
static int overlap(const void *a,size_t an,const void *b,size_t bn)
{ return (uintptr_t)a<(uintptr_t)b+bn && (uintptr_t)b<(uintptr_t)a+an; }
static int buffer(const void *ctx,const void *p,size_t n)
{ return extent(p,n) && !overlap(ctx,sizeof(struct s24_gcm_state),p,n); }
void s24_gcm_clear(ccgcm_ctx *ctx)
{ if(aligned(ctx)&&extent(ctx,sizeof(struct s24_gcm_state)))mbedtls_platform_zeroize(ctx,sizeof(struct s24_gcm_state)); }
static int valid_backend(const mbedtls_gcm_context *b,unsigned key_bytes)
{
    const mbedtls_block_cipher_context_t *c=&b->MBEDTLS_PRIVATE(block_cipher_ctx);
    return c->MBEDTLS_PRIVATE(id)==MBEDTLS_BLOCK_CIPHER_ID_AES &&
        c->MBEDTLS_PRIVATE(ctx).MBEDTLS_PRIVATE(aes).MBEDTLS_PRIVATE(nr)==(int)(key_bytes/4+6) &&
        c->MBEDTLS_PRIVATE(ctx).MBEDTLS_PRIVATE(aes).MBEDTLS_PRIVATE(rk_offset)==0 && b->MBEDTLS_PRIVATE(acceleration)==0;
}
static int load(const ccgcm_ctx *ctx,struct s24_gcm_state *s)
{
    if(!aligned(ctx)||!extent(ctx,sizeof(*s)))return 0;
    memcpy(s,ctx,sizeof(*s));
    return s->magic==MAGIC && s->owner==(uintptr_t)ctx && s->phase>=WAIT_IV && s->phase<=FINAL &&
        s->decrypt<=1 && s->managed<=1 && (s->key_bytes==16||s->key_bytes==24||s->key_bytes==32) &&
        s->text_bytes<=CCGCM_TEXT_MAX_NBYTES && s->aad_bytes<=AAD_MAX &&
        valid_backend(&s->seed,s->key_bytes) && valid_backend(&s->active,s->key_bytes) &&
        s->seed.MBEDTLS_PRIVATE(len)==0 && s->seed.MBEDTLS_PRIVATE(add_len)==0 &&
        s->active.MBEDTLS_PRIVATE(len)==s->text_bytes && s->active.MBEDTLS_PRIVATE(add_len)==s->aad_bytes;
}
static int enc_init(const struct ccmode_gcm *,ccgcm_ctx *,size_t,const void *);
static int dec_init(const struct ccmode_gcm *,ccgcm_ctx *,size_t,const void *);
static int set_iv(ccgcm_ctx *,size_t,const void *);
static int aad(ccgcm_ctx *,size_t,const void *);
static int update(ccgcm_ctx *,size_t,const void *,void *);
static int finalize(ccgcm_ctx *,size_t,void *);
static int reset(ccgcm_ctx *);
static int mode_valid(const struct ccmode_gcm *m,unsigned decrypt)
{
    return extent(m,sizeof(*m)) && m->size==sizeof(struct s24_gcm_state) && m->block_size==16 &&
        m->encdec==(decrypt?CCMODE_GCM_DECRYPTOR:CCMODE_GCM_ENCRYPTOR) && m->custom==&mode_token &&
        m->init==(decrypt?dec_init:enc_init) && m->set_iv==set_iv && m->gmac==aad && m->gcm==update &&
        m->finalize==finalize && m->reset==reset;
}
static int start(struct s24_gcm_state *s,size_t n,const void *iv)
{
    s->active=s->seed;
    if(mbedtls_gcm_starts(&s->active,s->decrypt?MBEDTLS_GCM_DECRYPT:MBEDTLS_GCM_ENCRYPT,iv,n))return CCERR_INTERNAL;
    s->phase=AAD;s->text_bytes=0;s->aad_bytes=0;return 0;
}
static int initialize(const struct ccmode_gcm *m,ccgcm_ctx *ctx,size_t n,const void *key,unsigned decrypt,const void *iv)
{
    struct s24_gcm_state s,old;
    memset(&s,0,sizeof(s));memset(&old,0,sizeof(old));int result=CCERR_PARAMETER;
    if(!aligned(ctx)||!extent(ctx,sizeof(s)))goto done;
    if(!mode_valid(m,decrypt)||overlap(ctx,sizeof(s),m,sizeof(*m))||
       (n!=16&&n!=24&&n!=32)||!buffer(ctx,key,n)||
       (iv&&!buffer(ctx,iv,12)))goto done;
    /* Live managed authority cannot be silently reconstructed/rekeyed by init.
     * Explicit clear/destruction and other contexts remain external uniqueness boundaries. */
    if(load(ctx,&old)&&old.managed){result=CCERR_CALL_SEQUENCE;goto done;}
    mbedtls_gcm_init(&s.seed);
    if(mbedtls_gcm_setkey(&s.seed,MBEDTLS_CIPHER_ID_AES,key,(unsigned)n*8)){result=CCERR_INTERNAL;goto done;}
    s.active=s.seed;s.magic=MAGIC;s.owner=(uintptr_t)ctx;s.phase=WAIT_IV;s.decrypt=decrypt;s.key_bytes=(unsigned)n;
    if(iv){s.managed=1;memcpy(s.nonce,iv,12);result=start(&s,12,iv);if(result)goto done;}
    memcpy(ctx,&s,sizeof(s));result=0;
done:
    mbedtls_platform_zeroize(&s,sizeof(s));mbedtls_platform_zeroize(&old,sizeof(old));return result;
}
static int enc_init(const struct ccmode_gcm *m,ccgcm_ctx *c,size_t n,const void *k)
{ return initialize(m,c,n,k,0,NULL); }
static int dec_init(const struct ccmode_gcm *m,ccgcm_ctx *c,size_t n,const void *k)
{ return initialize(m,c,n,k,1,NULL); }
int s24_gcm_init_with_iv(const struct ccmode_gcm *m,ccgcm_ctx *c,size_t n,const void *key,const void *iv)
{
    if(!extent(m,sizeof(*m))||!iv)return CCERR_PARAMETER;
    unsigned decrypt=m->encdec==CCMODE_GCM_DECRYPTOR;
    return initialize(m,c,n,key,decrypt,iv);
}
static int set_iv(ccgcm_ctx *ctx,size_t n,const void *iv)
{
    struct s24_gcm_state s;memset(&s,0,sizeof(s));int result=CCERR_PARAMETER;
    if(!load(ctx,&s)){result=CCERR_CALL_SEQUENCE;goto done;}
    if(s.managed||s.phase!=WAIT_IV){result=CCERR_CALL_SEQUENCE;goto done;}
    if(!n||n>AAD_MAX||!buffer(ctx,iv,n))goto done;
    result=start(&s,n,iv);if(!result)memcpy(ctx,&s,sizeof(s));
done:mbedtls_platform_zeroize(&s,sizeof(s));return result;
}
static int reset(ccgcm_ctx *ctx)
{
    struct s24_gcm_state s;memset(&s,0,sizeof(s));int result=CCERR_CALL_SEQUENCE;
    if(!load(ctx,&s))goto done;
    /* Reset clears message state while retaining key and managed salt/counter. */
    s.active=s.seed;s.text_bytes=0;s.aad_bytes=0;s.phase=WAIT_IV;
    memcpy(ctx,&s,sizeof(s));result=0;
done:mbedtls_platform_zeroize(&s,sizeof(s));return result;
}
int s24_gcm_inc_iv(const struct ccmode_gcm *m,ccgcm_ctx *ctx,void *iv)
{
    struct s24_gcm_state s;memset(&s,0,sizeof(s));int result=CCERR_CALL_SEQUENCE;
    if(!load(ctx,&s)||!s.managed||s.phase!=WAIT_IV)goto done;
    result=CCERR_PARAMETER;
    if(!mode_valid(m,s.decrypt)||overlap(ctx,sizeof(s),m,sizeof(*m))||!buffer(ctx,iv,12)||overlap(m,sizeof(*m),iv,12))goto done;
    unsigned carry=1;
    for(unsigned i=12;i>4;--i){unsigned v=s.nonce[i-1]+carry;s.nonce[i-1]=(unsigned char)v;carry=v>>8;}
    if(carry){result=CCERR_OVERFLOW;goto done;}
    result=start(&s,12,s.nonce);
    if(!result){memcpy(ctx,&s,sizeof(s));memcpy(iv,s.nonce,12);}
done:mbedtls_platform_zeroize(&s,sizeof(s));return result;
}
static int aad(ccgcm_ctx *ctx,size_t n,const void *input)
{
    struct s24_gcm_state s;memset(&s,0,sizeof(s));int result=CCERR_CALL_SEQUENCE;
    if(!load(ctx,&s)||s.phase!=AAD)goto done;
    result=CCERR_PARAMETER;
    if(n>AAD_MAX-s.aad_bytes||(n&&!buffer(ctx,input,n)))goto done;
    if(!n){result=0;goto done;}
    if(mbedtls_gcm_update_ad(&s.active,input,n)){result=CCERR_INTERNAL;goto done;}
    s.aad_bytes+=n;memcpy(ctx,&s,sizeof(s));result=0;
done:mbedtls_platform_zeroize(&s,sizeof(s));return result;
}
static int update(ccgcm_ctx *ctx,size_t n,const void *input,void *output)
{
    struct s24_gcm_state s;memset(&s,0,sizeof(s));int result=CCERR_CALL_SEQUENCE;
    if(!load(ctx,&s)||(s.phase!=AAD&&s.phase!=DATA))goto done;
    result=CCERR_PARAMETER;
    if(n>CCGCM_TEXT_MAX_NBYTES-s.text_bytes||(n&&(!buffer(ctx,input,n)||!buffer(ctx,output,n)||
       (input!=output&&overlap(input,n,output,n)))))goto done;
    if(!n){result=0;goto done;}
    size_t produced=0;
    if(mbedtls_gcm_update(&s.active,input,n,output,n,&produced)||produced!=n){
        /* Unexpected backend failure is distinct from rejected admission. */
        mbedtls_platform_zeroize(output,n);s24_gcm_clear(ctx);result=CCERR_INTERNAL;goto done;
    }
    s.text_bytes+=n;s.phase=DATA;memcpy(ctx,&s,sizeof(s));result=0;
done:mbedtls_platform_zeroize(&s,sizeof(s));return result;
}
static int finalize(ccgcm_ctx *ctx,size_t n,void *tag)
{
    struct s24_gcm_state s;unsigned char computed[16],expected[16];
    memset(&s,0,sizeof(s));memset(computed,0,sizeof(computed));memset(expected,0,sizeof(expected));int result=CCERR_CALL_SEQUENCE;
    if(!load(ctx,&s)||(s.phase!=AAD&&s.phase!=DATA))goto done;
    result=CCERR_PARAMETER;
    if(n<4||n>16||!buffer(ctx,tag,n))goto done;
    if(s.decrypt)memcpy(expected,tag,n);
    size_t produced=0;
    if(mbedtls_gcm_finish(&s.active,NULL,0,&produced,computed,n)||produced){result=CCERR_INTERNAL;goto done;}
    result=s.decrypt&&mbedtls_ct_memcmp(expected,computed,n)?CCERR_INTEGRITY:0;
    /* The selected genuine interface requires computed-tag overwrite even on mismatch. */
    memcpy(tag,computed,n);s.phase=FINAL;memcpy(ctx,&s,sizeof(s));
done:
    mbedtls_platform_zeroize(&s,sizeof(s));mbedtls_platform_zeroize(computed,sizeof(computed));mbedtls_platform_zeroize(expected,sizeof(expected));return result;
}
int s24_gcm_descriptor(struct ccmode_gcm *m,int decrypt)
{
    if(!extent(m,sizeof(*m))||(decrypt!=0&&decrypt!=1))return CCERR_PARAMETER;
    const struct ccmode_gcm value={.size=sizeof(struct s24_gcm_state),.encdec=decrypt?CCMODE_GCM_DECRYPTOR:CCMODE_GCM_ENCRYPTOR,
        .block_size=16,.init=decrypt?dec_init:enc_init,.set_iv=set_iv,.gmac=aad,.gcm=update,.finalize=finalize,.reset=reset,.custom=&mode_token};
    *m=value;return 0;
}
