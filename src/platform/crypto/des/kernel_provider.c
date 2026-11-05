/* Owned typed publication glue over accepted real DES factories. No key schedule
 * overlay, SDK records, ABI-forcing casts, heap/entropy or provider registration.
 * Algorithm implementation and component notices remain in unchanged des.c/vendor.
 */
#include "kernel_provider.h"
#include <libkern/crypto/des.h>
#if defined(KERNEL)
#include <libkern/crypto/register_crypto.h>
#include <mach/vm_param.h>
#endif
_Static_assert(sizeof(struct ccmode_ecb)==48 && sizeof(struct ccmode_cbc)==40,"selected mode sizes");
_Static_assert(_Alignof(struct ccmode_ecb)==8 && _Alignof(struct ccmode_cbc)==8,"selected descriptor alignment");
_Static_assert(_Alignof(ccecb_ctx)==16 && _Alignof(cccbc_ctx)==16 && _Alignof(cccbc_iv)==16,"selected opaque alignment");
_Static_assert(S24_KERNEL_DES_CONTEXT_BYTES<=sizeof(((des_ecb_key_schedule *)0)->enc),"selected DES capacity");
_Static_assert(S24_KERNEL_TDES_CONTEXT_BYTES<=sizeof(((des3_ecb_key_schedule *)0)->enc),"selected TDES capacity");
#if defined(KERNEL)
/* Native allocator/layout witness; sanitized host tests use no kernel heap. */
_Static_assert(KALLOC_LOG2_MINALIGN==4,"selected allocator minimum alignment");
const unsigned long long s24_kernel_des_layout[]={sizeof(struct ccmode_ecb),sizeof(struct ccmode_cbc),
 _Alignof(struct ccmode_ecb),_Alignof(struct ccmode_cbc),_Alignof(ccecb_ctx),_Alignof(cccbc_iv),
 sizeof(((des_ecb_key_schedule *)0)->enc),sizeof(((des3_ecb_key_schedule *)0)->enc),
 S24_KERNEL_DES_CONTEXT_BYTES,S24_KERNEL_TDES_CONTEXT_BYTES,KALLOC_LOG2_MINALIGN,
 __builtin_offsetof(struct ccmode_ecb,init),__builtin_offsetof(struct ccmode_ecb,ecb),
 __builtin_offsetof(struct ccmode_ecb,roundkey),__builtin_offsetof(struct ccmode_cbc,init),
 __builtin_offsetof(struct ccmode_cbc,cbc)};
#endif
static struct ccmode_ecb private_ecb[2][2];
static struct ccmode_cbc private_cbc[2][2];
/*0=unprepared,1=preparing,2=ready,3=failed. No reset/reconfiguration. */
static unsigned preparation;
static int ready(void) {return __atomic_load_n(&preparation,__ATOMIC_ACQUIRE)==2;}
static int selectors(int t,int d) {return (t==0||t==1)&&(d==0||d==1);}
static size_t context_size(unsigned t) {return t?S24_KERNEL_TDES_CONTEXT_BYTES:S24_KERNEL_DES_CONTEXT_BYTES;}
static int metadata(unsigned t,unsigned d)
{
 const struct ccmode_ecb *e=&private_ecb[t][d];const struct ccmode_cbc *c=&private_cbc[t][d];
 return e->size==context_size(t) && e->block_size==8 && e->init && e->ecb && !e->roundkey && e->impl==CC_IMPL_UNKNOWN &&
  c->size==context_size(t) && c->block_size==8 && c->init && c->cbc && !c->custom;
}
int s24_kernel_des_prepare(void)
{
 unsigned expected=0;
 if(!__atomic_compare_exchange_n(&preparation,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
  return expected==2?CCERR_OK:expected==3?CCERR_INTERNAL:CCERR_CALL_SEQUENCE;
 for(unsigned t=0;t<2;++t)for(unsigned d=0;d<2;++d) {
  if(s24_des_ecb_descriptor(&private_ecb[t][d],(int)t,(int)d) ||
   s24_des_cbc_descriptor(&private_cbc[t][d],(int)t,(int)d) || !metadata(t,d)) {
   __atomic_store_n(&preparation,3,__ATOMIC_RELEASE);return CCERR_INTERNAL;
  }
 }
 __atomic_store_n(&preparation,2,__ATOMIC_RELEASE);return CCERR_OK;
}
const struct ccmode_ecb *s24_kernel_des_ecb_mode(int t,int d)
{
 if(!selectors(t,d)||!ready())return NULL;
 return t?(d?&s24_kernel_tdes_ecb_decrypt:&s24_kernel_tdes_ecb_encrypt):
          (d?&s24_kernel_des_ecb_decrypt:&s24_kernel_des_ecb_encrypt);
}
const struct ccmode_cbc *s24_kernel_des_cbc_mode(int t,int d)
{
 if(!selectors(t,d)||!ready())return NULL;
 return t?(d?&s24_kernel_tdes_cbc_decrypt:&s24_kernel_tdes_cbc_encrypt):
          (d?&s24_kernel_des_cbc_decrypt:&s24_kernel_des_cbc_encrypt);
}
#define CALLBACKS(T,D) \
static int ei##T##D(const struct ccmode_ecb *m,ccecb_ctx *ctx,size_t n,const void *key) { \
 if(!ready()||m!=s24_kernel_des_ecb_mode(T,D))return CCERR_CALL_SEQUENCE; \
 if(n!=(T?24U:8U))return CCERR_PARAMETER; \
 return private_ecb[T][D].init(&private_ecb[T][D],ctx,n,key); } \
static int ec##T##D(const ccecb_ctx *ctx,size_t n,const void *in,void *out) { \
 return ready()?private_ecb[T][D].ecb(ctx,n,in,out):CCERR_CALL_SEQUENCE; } \
static int ci##T##D(const struct ccmode_cbc *m,cccbc_ctx *ctx,size_t n,const void *key) { \
 if(!ready()||m!=s24_kernel_des_cbc_mode(T,D))return CCERR_CALL_SEQUENCE; \
 if(n!=(T?24U:8U))return CCERR_PARAMETER; \
 return private_cbc[T][D].init(&private_cbc[T][D],ctx,n,key); } \
static int cb##T##D(const cccbc_ctx *ctx,cccbc_iv *iv,size_t n,const void *in,void *out) { \
 return ready()?private_cbc[T][D].cbc(ctx,iv,n,in,out):CCERR_CALL_SEQUENCE; }
CALLBACKS(0,0) CALLBACKS(0,1) CALLBACKS(1,0) CALLBACKS(1,1)
#define ECB(NAME,T,D,SIZE) const struct ccmode_ecb NAME={.size=SIZE,.block_size=8,.init=ei##T##D,.ecb=ec##T##D,.roundkey=NULL,.impl=CC_IMPL_UNKNOWN}
#define CBC(NAME,T,D,SIZE) const struct ccmode_cbc NAME={.size=SIZE,.block_size=8,.init=ci##T##D,.cbc=cb##T##D,.custom=NULL}
ECB(s24_kernel_des_ecb_encrypt,0,0,S24_KERNEL_DES_CONTEXT_BYTES);
ECB(s24_kernel_des_ecb_decrypt,0,1,S24_KERNEL_DES_CONTEXT_BYTES);
ECB(s24_kernel_tdes_ecb_encrypt,1,0,S24_KERNEL_TDES_CONTEXT_BYTES);
ECB(s24_kernel_tdes_ecb_decrypt,1,1,S24_KERNEL_TDES_CONTEXT_BYTES);
CBC(s24_kernel_des_cbc_encrypt,0,0,S24_KERNEL_DES_CONTEXT_BYTES);
CBC(s24_kernel_des_cbc_decrypt,0,1,S24_KERNEL_DES_CONTEXT_BYTES);
CBC(s24_kernel_tdes_cbc_encrypt,1,0,S24_KERNEL_TDES_CONTEXT_BYTES);
CBC(s24_kernel_tdes_cbc_decrypt,1,1,S24_KERNEL_TDES_CONTEXT_BYTES);
int s24_kernel_des_key_is_weak(void *key,unsigned long n)
{return ready()?s24_des_key_is_weak(key,n):CCERR_CALL_SEQUENCE;}
void s24_kernel_des_key_set_odd_parity(void *key,unsigned long n)
{if(ready())s24_des_key_set_odd_parity(key,n);}
/* Real selected helper typedef assignment is a compile-time ABI constraint. */
#if defined(KERNEL)
ccdes_key_is_weak_fn_t const s24_kernel_des_typed_weak=s24_kernel_des_key_is_weak;
ccdes_key_set_odd_parity_fn_t const s24_kernel_des_typed_parity=s24_kernel_des_key_set_odd_parity;
#endif
