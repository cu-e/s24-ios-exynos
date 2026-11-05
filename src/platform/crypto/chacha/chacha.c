/* Owned RFC8439 AEAD glue over genuine licensed Mbed TLS streaming primitives.
 * No Apple implementation copied/translated. See vendor/NOTICE.md and
 * docs/procedures/crypto-chacha/nonce-contract.json for the incomplete gate.
 */
#include "internal.h"
#include <corecrypto/cc_error.h>
#include <mbedtls/platform_util.h>
#include "chacha20_internal.h"
#include <string.h>

#define MAGIC UINT64_C(0x5332344348413931)
enum { KEY=1,AAD=2,ENC=3,DEC=4,FINAL=5 };
_Static_assert(sizeof(struct s24_chacha_state)<=sizeof(ccchacha20poly1305_ctx),"owned context fit");
_Static_assert(_Alignof(struct s24_chacha_state)==8 && _Alignof(ccchacha20poly1305_ctx)==8,"actual selected alignment");
_Static_assert(sizeof(ccchacha20poly1305_ctx)==256,"actual selected fixed context");
_Static_assert(sizeof(size_t)==8,"qualified LP64 profile");
const unsigned long long s24_chacha_layout[]={sizeof(struct s24_chacha_state),_Alignof(struct s24_chacha_state),
    sizeof(ccchacha20poly1305_ctx),_Alignof(ccchacha20poly1305_ctx),sizeof(mbedtls_chacha20_context),
    sizeof(mbedtls_poly1305_context)};
/* The genuine selected info type is empty. Owned trailing storage gives its
 * correctly typed first member a stable object identity without an ABI cast. */
static const struct { struct ccchacha20poly1305_info selected;unsigned char identity; } descriptor={.identity=0xa5};
const struct ccchacha20poly1305_info *s24_chacha_info(void) { return &descriptor.selected; }
static int extent(const void *p,size_t n)
{ return !n || (p && (uintptr_t)p<=UINTPTR_MAX-n); }
static int aligned(const void *p) { return p && !((uintptr_t)p&7); }
static int overlap(const void *a,size_t an,const void *b,size_t bn)
{ return an && bn && (uintptr_t)a<(uintptr_t)b+bn && (uintptr_t)b<(uintptr_t)a+an; }
static int ctx_ok(const void *p) { return aligned(p) && extent(p,sizeof(ccchacha20poly1305_ctx)); }
void s24_chacha20poly1305_clear(ccchacha20poly1305_ctx *ctx)
{ if(ctx_ok(ctx))mbedtls_platform_zeroize(ctx,sizeof(*ctx)); }
static void clear_state(struct s24_chacha_state *s) { mbedtls_platform_zeroize(s,sizeof(*s)); }
static int load(const struct ccchacha20poly1305_info *info,const ccchacha20poly1305_ctx *ctx,struct s24_chacha_state *s)
{
    if(info!=s24_chacha_info() || !ctx_ok(ctx))return CCERR_PARAMETER;
    memcpy(s,ctx,sizeof(*s));
    if(s->magic!=MAGIC || s->phase<KEY || s->phase>FINAL ||
       s->chacha.MBEDTLS_PRIVATE(keystream_bytes_used)>65 ||
       s->poly.MBEDTLS_PRIVATE(queue_len)>(s->phase==FINAL?16u:15u))return CCERR_CALL_SEQUENCE;
    return CCERR_OK;
}
static void store(ccchacha20poly1305_ctx *ctx,const struct s24_chacha_state *s)
{ s24_chacha20poly1305_clear(ctx);memcpy(ctx,s,sizeof(*s)); }
static int buffer(const ccchacha20poly1305_ctx *ctx,const void *p,size_t n)
{ return extent(p,n) && !overlap(ctx,sizeof(*ctx),p,n); }
static void put32(unsigned char *p,uint32_t value)
{ for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(value>>(8*i)); }
static void put64(unsigned char *p,uint64_t value)
{ for(unsigned i=0;i<8;i++)p[i]=(unsigned char)(value>>(8*i)); }
int s24_chacha_init(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,const uint8_t *key)
{
    struct s24_chacha_state s={0};int result=CCERR_PARAMETER;
    if(info!=s24_chacha_info() || !ctx_ok(ctx) || !buffer(ctx,key,32))goto done;
    mbedtls_chacha20_init(&s.chacha);mbedtls_poly1305_init(&s.poly);
    if(mbedtls_chacha20_setkey(&s.chacha,key)){result=CCERR_INTERNAL;goto done;}
    s.phase=KEY;s.magic=MAGIC;store(ctx,&s);result=CCERR_OK;
done:clear_state(&s);return result;
}
int s24_chacha_reset(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx)
{
    struct s24_chacha_state s={0};unsigned char key[32]={0};int result=load(info,ctx,&s);
    if(result)goto done;
    for(unsigned i=0;i<8;i++)put32(key+i*4,s.chacha.MBEDTLS_PRIVATE(state)[4+i]);
    mbedtls_chacha20_free(&s.chacha);mbedtls_poly1305_free(&s.poly);
    mbedtls_chacha20_init(&s.chacha);mbedtls_poly1305_init(&s.poly);
    if(mbedtls_chacha20_setkey(&s.chacha,key)){result=CCERR_INTERNAL;goto done;}
    s.aad_bytes=0;s.text_bytes=0;s.phase=KEY;store(ctx,&s);
done:mbedtls_platform_zeroize(key,sizeof(key));clear_state(&s);return result;
}
int s24_chacha_setnonce(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,const uint8_t *nonce)
{
    struct s24_chacha_state s={0};unsigned char key_stream[64]={0};int result=load(info,ctx,&s);
    if(result)goto done;
    if(s.phase!=KEY){result=CCERR_CALL_SEQUENCE;goto done;}
    if(!buffer(ctx,nonce,12)){result=CCERR_PARAMETER;goto done;}
    memcpy(s.nonce,nonce,12);
    if(mbedtls_chacha20_starts(&s.chacha,nonce,0) ||
       mbedtls_chacha20_update(&s.chacha,64,key_stream,key_stream) ||
       mbedtls_poly1305_starts(&s.poly,key_stream)){result=CCERR_INTERNAL;goto done;}
    s.aad_bytes=0;s.text_bytes=0;s.phase=AAD;store(ctx,&s);
done:mbedtls_platform_zeroize(key_stream,sizeof(key_stream));clear_state(&s);return result;
}
/* Deliberately unsupported, never a successful placeholder. Exact selected
 * nonce increment contract is unavailable; the full table stays unqualified. */
int s24_chacha_incnonce(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,uint8_t *nonce)
{ (void)info;(void)ctx;(void)nonce;return CCERR_NOT_SUPPORTED; }
int s24_chacha_aad(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,size_t n,const void *input)
{
    struct s24_chacha_state s={0};int result=load(info,ctx,&s);
    if(result)goto done;
    if(s.phase!=AAD){result=CCERR_CALL_SEQUENCE;goto done;}
    if(!buffer(ctx,input,n)){result=CCERR_PARAMETER;goto done;}
    if(n>UINT64_MAX-s.aad_bytes){result=CCERR_OVERFLOW;goto done;}
    if(n && mbedtls_poly1305_update(&s.poly,input,n)){result=CCERR_INTERNAL;goto done;}
    s.aad_bytes+=n;store(ctx,&s);
done:clear_state(&s);return result;
}
static int pad(struct s24_chacha_state *s,uint64_t count)
{
    static const unsigned char zeros[16]={0};unsigned tail=(unsigned)(count&15);
    return tail && mbedtls_poly1305_update(&s->poly,zeros,16-tail)?CCERR_INTERNAL:CCERR_OK;
}
static int text_update(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,
                       size_t n,const void *input,void *output,unsigned direction)
{
    struct s24_chacha_state s={0};int result=load(info,ctx,&s);
    if(result)goto done;
    if(s.phase!=AAD && s.phase!=direction){result=CCERR_CALL_SEQUENCE;goto done;}
    if(!buffer(ctx,input,n) || !buffer(ctx,output,n) ||
       (input!=output && overlap(input,n,output,n))){result=CCERR_PARAMETER;goto done;}
    if(s.text_bytes>CCCHACHA20POLY1305_TEXT_MAX_NBYTES ||
       n>CCCHACHA20POLY1305_TEXT_MAX_NBYTES-s.text_bytes){result=CCERR_OVERFLOW;goto done;}
    if(mbedtls_chacha20_check_counter_wrap(&s.chacha,n)){result=CCERR_OVERFLOW;goto done;}
    if(s.phase==AAD && (result=pad(&s,s.aad_bytes)))goto done;
    s.phase=direction;
    if(direction==DEC && n && mbedtls_poly1305_update(&s.poly,input,n)){result=CCERR_INTERNAL;goto done;}
    if(n && mbedtls_chacha20_update(&s.chacha,n,input,output)){result=CCERR_INTERNAL;goto done;}
    if(direction==ENC && n && mbedtls_poly1305_update(&s.poly,output,n)){result=CCERR_INTERNAL;goto done;}
    s.text_bytes+=n;store(ctx,&s);
done:clear_state(&s);return result;
}
int s24_chacha_encrypt(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,size_t n,const void *input,void *output)
{ return text_update(info,ctx,n,input,output,ENC); }
int s24_chacha_decrypt(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,size_t n,const void *input,void *output)
{ return text_update(info,ctx,n,input,output,DEC); }
static int finish(struct s24_chacha_state *s,unsigned direction,unsigned char tag[16])
{
    unsigned char lengths[16]={0};int result=CCERR_CALL_SEQUENCE;
    if(s->phase!=AAD && s->phase!=direction)goto done;
    if(s->phase==AAD && (result=pad(s,s->aad_bytes)))goto done;
    if((result=pad(s,s->text_bytes)))goto done;
    put64(lengths,s->aad_bytes);put64(lengths+8,s->text_bytes);
    if(mbedtls_poly1305_update(&s->poly,lengths,16) || mbedtls_poly1305_finish(&s->poly,tag)){
        result=CCERR_INTERNAL;goto done;
    }
    s->phase=FINAL;result=CCERR_OK;
done:mbedtls_platform_zeroize(lengths,sizeof(lengths));return result;
}
int s24_chacha_finalize(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,uint8_t *tag)
{
    struct s24_chacha_state s={0};unsigned char computed[16]={0};int result=load(info,ctx,&s);
    if(result)goto done;
    if(!buffer(ctx,tag,16)){result=CCERR_PARAMETER;goto done;}
    result=finish(&s,ENC,computed);
    if(!result){store(ctx,&s);memcpy(tag,computed,16);}
done:mbedtls_platform_zeroize(computed,sizeof(computed));clear_state(&s);return result;
}
int s24_chacha_verify(const struct ccchacha20poly1305_info *info,ccchacha20poly1305_ctx *ctx,const uint8_t *tag)
{
    struct s24_chacha_state s={0};unsigned char computed[16]={0};int result=load(info,ctx,&s);
    if(result)goto done;
    if(!buffer(ctx,tag,16)){result=CCERR_PARAMETER;goto done;}
    result=finish(&s,DEC,computed);
    if(!result){
        /* Exactly16 public-index byte comparisons; volatile accumulation
         * prevents substitution by a short-circuit comparison. No global helper. */
        volatile unsigned difference=0;
        for(unsigned i=0;i<16;i++)difference|=(unsigned)(computed[i]^tag[i]);
        store(ctx,&s);result=difference?CCERR_INTEGRITY:CCERR_OK;
    }
done:mbedtls_platform_zeroize(computed,sizeof(computed));clear_state(&s);return result;
}
