/* Owned host publication/concurrency controls using genuine selected descriptor
 * and aesxts declarations plus actual accepted AES/XTS implementation. No SDK shim. */
#include "kernel_provider.h"
#include <corecrypto/ccmode.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include "vectors.h"
static unsigned entered,release_gate;
void kxts_factory_gate(void)
{
 if(__atomic_exchange_n(&entered,1,__ATOMIC_ACQ_REL)==0)
  while(!__atomic_load_n(&release_gate,__ATOMIC_ACQUIRE))sched_yield();
}
struct result { int prepare,algorithm; };
__attribute__((unused)) static void *prepare_thread(void *p)
{
 struct result *r=p;r->prepare=s24_kernel_xts_prepare();r->algorithm=0;
 if(!r->prepare) {
  const struct ccmode_xts *m=s24_kernel_xts_encrypt_mode();
  ccxts_ctx_decl(1072,key);ccxts_tweak_decl(64,tweak);unsigned char out[16];
  const struct vector *v=&vectors[0];const unsigned char *k=vector_bytes+v->key;
  if(m && !m->init(m,key,v->n,k,k+v->n) && !m->set_tweak(key,tweak,vector_bytes+v->iv) &&
   m->xts(key,tweak,1,vector_bytes+v->pt,out)==tweak && !memcmp(out,vector_bytes+v->ct,16))r->algorithm=1;
  s24_xts_clear_key(key);s24_xts_clear_tweak(tweak);
 }
 return NULL;
}
int main(void)
{
 unsigned checks=0;int failure=0;pthread_t first={0},threads[16]={0};struct result initial={0},results[16];
 (void)initial;(void)results;
 unsigned created=0;int started=0;unsigned char snapshot[160];
 memcpy(snapshot,&s24_kernel_xts_encrypt,80);memcpy(snapshot+80,&s24_kernel_xts_decrypt,80);
#define CHECK(x) do {++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
 CHECK(!s24_kernel_xts_encrypt_mode() && !s24_kernel_xts_decrypt_mode());
#ifdef KXTS_FACTORY_MISMATCH
 CHECK(s24_kernel_xts_prepare()==CCERR_INTERNAL);
 CHECK(s24_kernel_xts_prepare()==CCERR_INTERNAL);
 CHECK(!s24_kernel_xts_encrypt_mode() && !s24_kernel_xts_decrypt_mode());
#else
 CHECK(pthread_create(&first,NULL,prepare_thread,&initial)==0);started=1;
 while(!__atomic_load_n(&entered,__ATOMIC_ACQUIRE))sched_yield();
 CHECK(!s24_kernel_xts_encrypt_mode() && !s24_kernel_xts_decrypt_mode());
 CHECK(s24_kernel_xts_prepare()==CCERR_CALL_SEQUENCE);
 for(unsigned i=0;i<16;++i) {CHECK(pthread_create(&threads[i],NULL,prepare_thread,&results[i])==0);++created;}
 for(unsigned i=0;i<created;++i) {CHECK(pthread_join(threads[i],NULL)==0);CHECK(results[i].prepare==CCERR_CALL_SEQUENCE && !results[i].algorithm);}
 created=0;__atomic_store_n(&release_gate,1,__ATOMIC_RELEASE);CHECK(pthread_join(first,NULL)==0);started=0;
 CHECK(!initial.prepare && initial.algorithm);
 CHECK(s24_kernel_xts_encrypt_mode()==&s24_kernel_xts_encrypt && s24_kernel_xts_decrypt_mode()==&s24_kernel_xts_decrypt);
 for(unsigned i=0;i<16;++i) {CHECK(pthread_create(&threads[i],NULL,prepare_thread,&results[i])==0);++created;}
 for(unsigned i=0;i<created;++i) {CHECK(pthread_join(threads[i],NULL)==0);CHECK(!results[i].prepare && results[i].algorithm);}
 created=0;CHECK(s24_kernel_xts_prepare()==0);
#endif
 CHECK(!memcmp(snapshot,&s24_kernel_xts_encrypt,80) && !memcmp(snapshot+80,&s24_kernel_xts_decrypt,80));
done:
 __atomic_store_n(&release_gate,1,__ATOMIC_RELEASE);
 if(started)pthread_join(first,NULL);
 for(unsigned i=0;i<created;++i)pthread_join(threads[i],NULL);
 printf("KXTS PUBLICATION %s checks=%u failure_line=%d\n",failure?"FAIL":"PASS",checks,failure);
 return failure?1:0;
}
