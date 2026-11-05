/* Owned typed publication glue. Real AES/XTS implementation stays in accepted
 * xts.c, with Mbed component attribution there. No provider registration or
 * replacement SDK records are supplied by this unit. */
#include "kernel_provider.h"
#include <libkern/crypto/aesxts.h>
#include <stdint.h>

_Static_assert(sizeof(struct ccmode_xts)==80, "selected descriptor size");
_Static_assert(_Alignof(struct ccmode_xts)==8, "selected descriptor alignment");
_Static_assert(S24_KERNEL_XTS_KEY_BYTES<=sizeof(((symmetric_xts *)0)->enc), "selected encrypt caller storage");
_Static_assert(S24_KERNEL_XTS_KEY_BYTES<=sizeof(((symmetric_xts *)0)->dec), "selected decrypt caller storage");
_Static_assert(_Alignof(ccxts_ctx)==16 && _Alignof(ccxts_tweak)==16, "selected opaque alignment");
const unsigned long long s24_kernel_xts_layout[]={sizeof(struct ccmode_xts),_Alignof(struct ccmode_xts),
 sizeof(((symmetric_xts *)0)->enc),sizeof(((symmetric_xts *)0)->dec),_Alignof(ccxts_ctx),
 S24_KERNEL_XTS_KEY_BYTES,S24_KERNEL_XTS_TWEAK_BYTES,
 __builtin_offsetof(struct ccmode_xts,init),__builtin_offsetof(struct ccmode_xts,key_sched),
 __builtin_offsetof(struct ccmode_xts,set_tweak),__builtin_offsetof(struct ccmode_xts,xts)};
static struct ccmode_xts private_encrypt,private_decrypt;
/*0=unprepared,1=preparing,2=ready,3=failed. No reset/reconfiguration API. */
static unsigned preparation;
static int ready(void) { return __atomic_load_n(&preparation,__ATOMIC_ACQUIRE)==2; }
static int metadata(const struct ccmode_xts *m)
{
 return m->size==S24_KERNEL_XTS_KEY_BYTES && m->tweak_size==S24_KERNEL_XTS_TWEAK_BYTES &&
  m->block_size==16 && m->init && m->key_sched && m->set_tweak && m->xts &&
  !m->custom && !m->custom1 && m->impl==CC_IMPL_AES_XTS_GENERIC;
}
int s24_kernel_xts_prepare(void)
{
 unsigned expected=0;
 if(!__atomic_compare_exchange_n(&preparation,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
  return expected==2?CCERR_OK:expected==3?CCERR_INTERNAL:CCERR_CALL_SEQUENCE;
 int rc=s24_xts_descriptor(&private_encrypt,0);
 if(!rc)rc=s24_xts_descriptor(&private_decrypt,1);
 if(rc || !metadata(&private_encrypt) || !metadata(&private_decrypt)) {
  __atomic_store_n(&preparation,3,__ATOMIC_RELEASE);return CCERR_INTERNAL;
 }
 __atomic_store_n(&preparation,2,__ATOMIC_RELEASE);return CCERR_OK;
}
const struct ccmode_xts *s24_kernel_xts_encrypt_mode(void)
{ return ready()?&s24_kernel_xts_encrypt:NULL; }
const struct ccmode_xts *s24_kernel_xts_decrypt_mode(void)
{ return ready()?&s24_kernel_xts_decrypt:NULL; }
static int enc_init(const struct ccmode_xts *m,ccxts_ctx *c,size_t n,const void *k,const void *t)
{
 if(!ready() || m!=&s24_kernel_xts_encrypt) { s24_xts_clear_key(c);return CCERR_CALL_SEQUENCE; }
 return private_encrypt.init(&private_encrypt,c,n,k,t);
}
static int dec_init(const struct ccmode_xts *m,ccxts_ctx *c,size_t n,const void *k,const void *t)
{
 if(!ready() || m!=&s24_kernel_xts_decrypt) { s24_xts_clear_key(c);return CCERR_CALL_SEQUENCE; }
 return private_decrypt.init(&private_decrypt,c,n,k,t);
}
static void enc_sched(const struct ccmode_xts *m,ccxts_ctx *c,size_t n,const void *k,const void *t)
{
 if(!ready() || m!=&s24_kernel_xts_encrypt) { s24_xts_clear_key(c);return; }
 private_encrypt.key_sched(&private_encrypt,c,n,k,t);
}
static void dec_sched(const struct ccmode_xts *m,ccxts_ctx *c,size_t n,const void *k,const void *t)
{
 if(!ready() || m!=&s24_kernel_xts_decrypt) { s24_xts_clear_key(c);return; }
 private_decrypt.key_sched(&private_decrypt,c,n,k,t);
}
static int enc_tweak(const ccxts_ctx *c,ccxts_tweak *t,const void *iv)
{ return ready()?private_encrypt.set_tweak(c,t,iv):CCERR_CALL_SEQUENCE; }
static int dec_tweak(const ccxts_ctx *c,ccxts_tweak *t,const void *iv)
{ return ready()?private_decrypt.set_tweak(c,t,iv):CCERR_CALL_SEQUENCE; }
static void *enc_blocks(const ccxts_ctx *c,ccxts_tweak *t,size_t n,const void *i,void *o)
{ return ready()?private_encrypt.xts(c,t,n,i,o):NULL; }
static void *dec_blocks(const ccxts_ctx *c,ccxts_tweak *t,size_t n,const void *i,void *o)
{ return ready()?private_decrypt.xts(c,t,n,i,o):NULL; }
const struct ccmode_xts s24_kernel_xts_encrypt={
 .size=S24_KERNEL_XTS_KEY_BYTES,.tweak_size=S24_KERNEL_XTS_TWEAK_BYTES,.block_size=16,
 .init=enc_init,.key_sched=enc_sched,.set_tweak=enc_tweak,.xts=enc_blocks,
 .custom=NULL,.custom1=NULL,.impl=CC_IMPL_AES_XTS_GENERIC};
const struct ccmode_xts s24_kernel_xts_decrypt={
 .size=S24_KERNEL_XTS_KEY_BYTES,.tweak_size=S24_KERNEL_XTS_TWEAK_BYTES,.block_size=16,
 .init=dec_init,.key_sched=dec_sched,.set_tweak=dec_tweak,.xts=dec_blocks,
 .custom=NULL,.custom1=NULL,.impl=CC_IMPL_AES_XTS_GENERIC};
