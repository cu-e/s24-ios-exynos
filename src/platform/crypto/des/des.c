/* Owned lifecycle and typed ABI glue. Genuine DES primitive in vendor/NOTICE.md.
 * No restricted Apple implementation is copied; selected headers are external. */
#include "des.h"
#include <mbedtls/des.h>
#include <mbedtls/platform_util.h>
#include <stdint.h>
#include <string.h>
struct head { uint64_t magic; uint32_t n; unsigned char triple, decrypt, cbc, reserved; };
struct __attribute__((aligned(16))) single { struct head h; mbedtls_des_context primitive; };
struct __attribute__((aligned(16))) triple { struct head h; mbedtls_des3_context primitive; };
union state { struct single one; struct triple three; };
#define MAGIC UINT64_C(0x4445534144415031)
_Static_assert(sizeof(struct single)<=256 && sizeof(struct triple)<=768,"selected DES key schedule capacity");
_Static_assert(_Alignof(struct single)==16 && _Alignof(struct triple)==16,"context alignment");
_Static_assert(_Alignof(ccecb_ctx)==16 && _Alignof(cccbc_ctx)==16 && _Alignof(cccbc_iv)==16,"genuine opaque alignment");
const unsigned long long s24_des_layout[]={sizeof(struct single),sizeof(struct triple),_Alignof(union state),sizeof(mbedtls_des_context),sizeof(mbedtls_des3_context),sizeof(struct ccmode_ecb),sizeof(struct ccmode_cbc)};
static int extent(const void *p,size_t n) { return p && (uintptr_t)p<=UINTPTR_MAX-n; }
static int aligned(const void *p) { return p && !((uintptr_t)p&15); }
static int overlap(const void *a,size_t an,const void *b,size_t bn)
{ return an && bn && (uintptr_t)a<(uintptr_t)b+bn && (uintptr_t)b<(uintptr_t)a+an; }
static size_t bytes(unsigned t) { return t?sizeof(struct triple):sizeof(struct single); }
/* Forward signatures are real selected callback types, never pointer casts. */
#define DECL(T,D) \
static int ei##T##D(const struct ccmode_ecb*,ccecb_ctx*,size_t,const void*); \
static int ec##T##D(const ccecb_ctx*,size_t,const void*,void*); \
static int ci##T##D(const struct ccmode_cbc*,cccbc_ctx*,size_t,const void*); \
static int cb##T##D(const cccbc_ctx*,cccbc_iv*,size_t,const void*,void*);
DECL(0,0) DECL(0,1) DECL(1,0) DECL(1,1)
static int make_ecb(struct ccmode_ecb *m,int t,int d)
{
 if((!extent(m,sizeof(*m)) || (uintptr_t)m%_Alignof(struct ccmode_ecb)) || (t!=0&&t!=1) || (d!=0&&d!=1)) return CCERR_PARAMETER;
 struct ccmode_ecb r={0}; r.size=bytes((unsigned)t);r.block_size=8;r.impl=CC_IMPL_UNKNOWN;
 if(t) { r.init=d?ei11:ei10;r.ecb=d?ec11:ec10; } else { r.init=d?ei01:ei00;r.ecb=d?ec01:ec00; }
 *m=r;return CCERR_OK;
}
static int make_cbc(struct ccmode_cbc *m,int t,int d)
{
 if((!extent(m,sizeof(*m)) || (uintptr_t)m%_Alignof(struct ccmode_cbc)) || (t!=0&&t!=1) || (d!=0&&d!=1)) return CCERR_PARAMETER;
 struct ccmode_cbc r={0};r.size=bytes((unsigned)t);r.block_size=8;
 if(t) {r.init=d?ci11:ci10;r.cbc=d?cb11:cb10;} else {r.init=d?ci01:ci00;r.cbc=d?cb01:cb00;}
 *m=r;return CCERR_OK;
}
int s24_des_ecb_descriptor(struct ccmode_ecb *m,int t,int d) {return make_ecb(m,t,d);}
int s24_des_cbc_descriptor(struct ccmode_cbc *m,int t,int d) {return make_cbc(m,t,d);}
static int match_ecb(const struct ccmode_ecb *m,unsigned t,unsigned d)
{
 struct ccmode_ecb r;make_ecb(&r,(int)t,(int)d);
 return extent(m,sizeof(*m)) && !((uintptr_t)m%_Alignof(struct ccmode_ecb)) && m->size==r.size && m->block_size==8 && m->init==r.init && m->ecb==r.ecb && !m->roundkey && m->impl==CC_IMPL_UNKNOWN;
}
static int match_cbc(const struct ccmode_cbc *m,unsigned t,unsigned d)
{
 struct ccmode_cbc r;make_cbc(&r,(int)t,(int)d);
 return extent(m,sizeof(*m)) && !((uintptr_t)m%_Alignof(struct ccmode_cbc)) && m->size==r.size && m->block_size==8 && m->init==r.init && m->cbc==r.cbc && !m->custom;
}
static int init(void *ctx,size_t n,const void *key,unsigned t,unsigned d,unsigned c)
{
 union state s;unsigned char raw[24];int r;
 memset(&s,0,sizeof(s));memset(raw,0,sizeof(raw));memcpy(raw,key,n);
 if(t) {
  mbedtls_des3_init(&s.three.primitive);
  if(n==16) r=d?mbedtls_des3_set2key_dec(&s.three.primitive,raw):mbedtls_des3_set2key_enc(&s.three.primitive,raw);
  else r=d?mbedtls_des3_set3key_dec(&s.three.primitive,raw):mbedtls_des3_set3key_enc(&s.three.primitive,raw);
  s.three.h=(struct head){MAGIC,(uint32_t)n,(unsigned char)t,(unsigned char)d,(unsigned char)c,0};
 } else {
  mbedtls_des_init(&s.one.primitive);r=d?mbedtls_des_setkey_dec(&s.one.primitive,raw):mbedtls_des_setkey_enc(&s.one.primitive,raw);
  s.one.h=(struct head){MAGIC,(uint32_t)n,0,(unsigned char)d,(unsigned char)c,0};
 }
 if(!r)memcpy(ctx,t?(const void*)&s.three:(const void*)&s.one,bytes(t));
 mbedtls_platform_zeroize(raw,sizeof(raw));mbedtls_platform_zeroize(&s,sizeof(s));return r?CCERR_INTERNAL:CCERR_OK;
}
static int admissible(const void *m,size_t mn,void *ctx,size_t n,const void *key,unsigned t)
{
 return aligned(ctx) && extent(ctx,bytes(t)) && (t?(n==16||n==24):n==8) && extent(key,n) &&
 !overlap(ctx,bytes(t),key,n) && !overlap(ctx,bytes(t),m,mn);
}
static int operate(const void *ctx,void *iv,size_t blocks,const void *in,void *out,unsigned t,unsigned d,unsigned c)
{
 if(blocks>SIZE_MAX/8) return CCERR_OVERFLOW;
 size_t n=blocks*8,z=bytes(t);struct head h;
 if(!aligned(ctx)||!extent(ctx,z))return CCERR_PARAMETER;
 memcpy(&h,ctx,sizeof(h));
 if(h.magic!=MAGIC||h.triple!=t||h.decrypt!=d||h.cbc!=c||h.reserved||(t?(h.n!=16&&h.n!=24):h.n!=8))return CCERR_CALL_SEQUENCE;
 if(!n)return CCERR_OK;
 if(!extent(in,n)||!extent(out,n)||(in!=out&&overlap(in,n,out,n))||overlap(ctx,z,in,n)||overlap(ctx,z,out,n))return CCERR_PARAMETER;
 if(c && (!aligned(iv)||!extent(iv,8)||overlap(ctx,z,iv,8)||overlap(in,n,iv,8)||overlap(out,n,iv,8)))return CCERR_PARAMETER;
 union state s;unsigned char chain[8]={0};int r=0;memset(&s,0,sizeof(s));
 if(t)memcpy(&s.three,ctx,z);else memcpy(&s.one,ctx,z);
 if(c) {
  memcpy(chain,iv,8);
  r=t?mbedtls_des3_crypt_cbc(&s.three.primitive,d?MBEDTLS_DES_DECRYPT:MBEDTLS_DES_ENCRYPT,n,chain,in,out):
      mbedtls_des_crypt_cbc(&s.one.primitive,d?MBEDTLS_DES_DECRYPT:MBEDTLS_DES_ENCRYPT,n,chain,in,out);
  if(!r)memcpy(iv,chain,8);
 } else for(size_t i=0;i<n&&!r;i+=8) {
  const unsigned char *a=in;unsigned char *b=out;
  r=t?mbedtls_des3_crypt_ecb(&s.three.primitive,a+i,b+i):mbedtls_des_crypt_ecb(&s.one.primitive,a+i,b+i);
 }
 mbedtls_platform_zeroize(chain,sizeof(chain));mbedtls_platform_zeroize(&s,sizeof(s));return r?CCERR_INTERNAL:CCERR_OK;
}
#define BODY(T,D) \
static int ei##T##D(const struct ccmode_ecb*m,ccecb_ctx*c,size_t n,const void*k) { \
 if(!match_ecb(m,T,D)||!admissible(m,sizeof(*m),c,n,k,T))return CCERR_PARAMETER;return init(c,n,k,T,D,0); } \
static int ec##T##D(const ccecb_ctx*c,size_t n,const void*a,void*b) {return operate(c,0,n,a,b,T,D,0);} \
static int ci##T##D(const struct ccmode_cbc*m,cccbc_ctx*c,size_t n,const void*k) { \
 if(!match_cbc(m,T,D)||!admissible(m,sizeof(*m),c,n,k,T))return CCERR_PARAMETER;return init(c,n,k,T,D,1); } \
static int cb##T##D(const cccbc_ctx*c,cccbc_iv*v,size_t n,const void*a,void*b) {return operate(c,v,n,a,b,T,D,1);}
BODY(0,0) BODY(0,1) BODY(1,0) BODY(1,1)
int s24_des_ecb_clear(const struct ccmode_ecb*m,ccecb_ctx*c)
{
 for(unsigned t=0;t<2;++t)for(unsigned d=0;d<2;++d)if(match_ecb(m,t,d)) {
  if(!aligned(c)||!extent(c,bytes(t))||overlap(c,bytes(t),m,sizeof(*m)))return CCERR_PARAMETER;
  mbedtls_platform_zeroize(c,bytes(t));return CCERR_OK; }
 return CCERR_PARAMETER;
}
int s24_des_cbc_clear(const struct ccmode_cbc*m,cccbc_ctx*c)
{
 for(unsigned t=0;t<2;++t)for(unsigned d=0;d<2;++d)if(match_cbc(m,t,d)) {
  if(!aligned(c)||!extent(c,bytes(t))||overlap(c,bytes(t),m,sizeof(*m)))return CCERR_PARAMETER;
  mbedtls_platform_zeroize(c,bytes(t));return CCERR_OK; }
 return CCERR_PARAMETER;
}
int s24_des_key_is_weak(void *key,unsigned long n)
{
 if(n!=8||!extent(key,8))return CCERR_PARAMETER;
 unsigned char copy[8];memcpy(copy,key,8);mbedtls_des_key_set_parity(copy);
 int r=mbedtls_des_key_check_weak(copy);mbedtls_platform_zeroize(copy,sizeof(copy));return r;
}
void s24_des_key_set_odd_parity(void *key,unsigned long n)
{
 if(n!=8||!extent(key,8))return;
 unsigned char copy[8];memcpy(copy,key,8);mbedtls_des_key_set_parity(copy);memcpy(key,copy,8);mbedtls_platform_zeroize(copy,sizeof(copy));
}
