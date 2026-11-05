/* Test-only typed CBC16 bridge over the genuine unchanged Mbed AES CBC body.
 * Not production code or an Apple context replica. Same canonical primitive
 * object supplies immutable accepted XTS adapter imports; old AES.o not linked. */
#include "fixture_aes.h"
#include "des.h"
#include <mbedtls/aes.h>
#include <mbedtls/platform_util.h>
#include <stdint.h>
#include <string.h>
struct __attribute__((aligned(16))) aes_state {uint64_t magic;unsigned n,decrypt;mbedtls_aes_context key;};
#define AES_MAGIC UINT64_C(0x4354533341455331)
_Static_assert(_Alignof(struct aes_state)==16,"genuine opaque CBC context alignment");
const unsigned long long s24_cts3_fixture_layout[]={sizeof(struct aes_state),_Alignof(struct aes_state),sizeof(mbedtls_aes_context),sizeof(struct ccmode_cbc)};
static int extent(const void*p,size_t n){return p&&(uintptr_t)p<=UINTPTR_MAX-n;}
static int aligned(const void*p){return p&&!((uintptr_t)p&15);}
static int overlap(const void*a,size_t an,const void*b,size_t bn){return an&&bn&&(uintptr_t)a<(uintptr_t)b+bn&&(uintptr_t)b<(uintptr_t)a+an;}
static int aes_init_e(const struct ccmode_cbc*,cccbc_ctx*,size_t,const void*);
static int aes_init_d(const struct ccmode_cbc*,cccbc_ctx*,size_t,const void*);
static int aes_cbc_e(const cccbc_ctx*,cccbc_iv*,size_t,const void*,void*);
static int aes_cbc_d(const cccbc_ctx*,cccbc_iv*,size_t,const void*,void*);
static int matches(const struct ccmode_cbc*m,unsigned d)
{return extent(m,sizeof(*m))&&!((uintptr_t)m%_Alignof(struct ccmode_cbc))&&m->size==sizeof(struct aes_state)&&m->block_size==16&&m->init==(d?aes_init_d:aes_init_e)&&m->cbc==(d?aes_cbc_d:aes_cbc_e)&&!m->custom;}
static int initialize(const struct ccmode_cbc*m,cccbc_ctx*c,size_t n,const void*k,unsigned d)
{
 if(!matches(m,d)||!aligned(c)||!extent(c,sizeof(struct aes_state))||(n!=16&&n!=24&&n!=32)||!extent(k,n)||overlap(c,sizeof(struct aes_state),m,sizeof(*m))||overlap(c,sizeof(struct aes_state),k,n))return CCERR_PARAMETER;
 struct aes_state s;memset(&s,0,sizeof(s));mbedtls_aes_init(&s.key);
 int r=d?mbedtls_aes_setkey_dec(&s.key,k,(unsigned)n*8):mbedtls_aes_setkey_enc(&s.key,k,(unsigned)n*8);
 if(!r){s.magic=AES_MAGIC;s.n=(unsigned)n;s.decrypt=d;memcpy(c,&s,sizeof(s));}
 mbedtls_platform_zeroize(&s,sizeof(s));return r?CCERR_INTERNAL:CCERR_OK;
}
static int crypt(const cccbc_ctx*c,cccbc_iv*iv,size_t blocks,const void*in,void*out,unsigned d)
{
 if(blocks>SIZE_MAX/16)return CCERR_OVERFLOW;
 if(!aligned(c)||!extent(c,sizeof(struct aes_state)))return CCERR_PARAMETER;
 struct aes_state s;memcpy(&s,c,sizeof(s));int result=CCERR_CALL_SEQUENCE;unsigned char chain[16]={0};size_t n=blocks*16;
 if(s.magic!=AES_MAGIC||s.decrypt!=d||(s.n!=16&&s.n!=24&&s.n!=32)||s.key.MBEDTLS_PRIVATE(nr)!=(int)(s.n/4+6)||s.key.MBEDTLS_PRIVATE(rk_offset)!=0)goto done;
 result=CCERR_OK;if(!n)goto done;
 result=CCERR_PARAMETER;
 if(!aligned(iv)||!extent(iv,16)||!extent(in,n)||!extent(out,n)||(in!=out&&overlap(in,n,out,n))||overlap(c,sizeof(s),in,n)||overlap(c,sizeof(s),out,n)||overlap(c,sizeof(s),iv,16)||overlap(iv,16,in,n)||overlap(iv,16,out,n))goto done;
 memcpy(chain,iv,16);
 result=mbedtls_aes_crypt_cbc(&s.key,d?MBEDTLS_AES_DECRYPT:MBEDTLS_AES_ENCRYPT,n,chain,in,out)?CCERR_INTERNAL:CCERR_OK;
 if(!result)memcpy(iv,chain,16);
done:mbedtls_platform_zeroize(&s,sizeof(s));mbedtls_platform_zeroize(chain,sizeof(chain));return result;
}
static int aes_init_e(const struct ccmode_cbc*m,cccbc_ctx*c,size_t n,const void*k){return initialize(m,c,n,k,0);}
static int aes_init_d(const struct ccmode_cbc*m,cccbc_ctx*c,size_t n,const void*k){return initialize(m,c,n,k,1);}
static int aes_cbc_e(const cccbc_ctx*c,cccbc_iv*v,size_t n,const void*a,void*b){return crypt(c,v,n,a,b,0);}
static int aes_cbc_d(const cccbc_ctx*c,cccbc_iv*v,size_t n,const void*a,void*b){return crypt(c,v,n,a,b,1);}
int cts3_fixture_mode(struct ccmode_cbc*m,unsigned algorithm,int decrypt)
{
 if(algorithm<2)return s24_des_cbc_descriptor(m,algorithm==1,decrypt);
 if(algorithm!=2||!extent(m,sizeof(*m))||((uintptr_t)m%_Alignof(struct ccmode_cbc))||(decrypt!=0&&decrypt!=1))return CCERR_PARAMETER;
 struct ccmode_cbc r={0};r.size=sizeof(struct aes_state);r.block_size=16;r.init=decrypt?aes_init_d:aes_init_e;r.cbc=decrypt?aes_cbc_d:aes_cbc_e;*m=r;return CCERR_OK;
}
int cts3_fixture_clear(const struct ccmode_cbc*m,cccbc_ctx*c)
{
 if(matches(m,0)||matches(m,1)) {
  if(!aligned(c)||!extent(c,sizeof(struct aes_state))||overlap(c,sizeof(struct aes_state),m,sizeof(*m)))return CCERR_PARAMETER;
  mbedtls_platform_zeroize(c,sizeof(struct aes_state));return CCERR_OK;
 }
 return s24_des_cbc_clear(m,c);
}
static struct ccmode_cbc underlying;
static unsigned fail_at,calls;
static int fault(const cccbc_ctx*c,cccbc_iv*v,size_t n,const void*a,void*b)
{++calls;if(fail_at&&calls==fail_at)return CCERR_INTERNAL;return underlying.cbc(c,v,n,a,b);}
void cts3_fixture_fault(const struct ccmode_cbc*m,unsigned at,struct ccmode_cbc*out)
{underlying=*m;calls=0;fail_at=at;*out=*m;out->cbc=fault;}
unsigned cts3_fixture_calls(void){return calls;}
