/* Owned publication controls; genuine modes and real unchanged DES algorithm. */
#include "kernel_provider.h"
#include <corecrypto/ccmode.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include "vectors.h"
static unsigned entered,release_gate;
void kdes_factory_gate(void)
{
 if(!__atomic_exchange_n(&entered,1,__ATOMIC_ACQ_REL))
  while(!__atomic_load_n(&release_gate,__ATOMIC_ACQUIRE))sched_yield();
}
struct result { int prepare,algorithm; };
static int algorithm(void)
{
 const struct vector *v=&vectors[1];cccbc_ctx_decl(768,key);cccbc_iv_decl(8,iv);unsigned char out[8];
 const struct ccmode_cbc *m=s24_kernel_des_cbc_mode(0,0);
 memcpy(iv,vector_bytes+v->iv,8);
 int good=m && !m->init(m,key,8,vector_bytes+v->key) && !m->cbc(key,iv,1,vector_bytes+v->pt,out) && !memcmp(out,vector_bytes+v->ct,8);
 memset(key,0,sizeof(key));return good;
}
__attribute__((unused)) static void *prepare_thread(void *p)
{struct result *r=p;r->prepare=s24_kernel_des_prepare();r->algorithm=!r->prepare&&algorithm();return NULL;}
int main(void)
{
 unsigned checks=0,created=0;int failure=0,started=0;pthread_t first={0},threads[16]={0};struct result initial={0},results[16];
 (void)initial;(void)results;
 unsigned char before[352];size_t at=0;cccbc_ctx_decl(768,key);
 for(int t=0;t<2;++t)for(int d=0;d<2;++d) {
  const struct ccmode_ecb *e=t?(d?&s24_kernel_tdes_ecb_decrypt:&s24_kernel_tdes_ecb_encrypt):(d?&s24_kernel_des_ecb_decrypt:&s24_kernel_des_ecb_encrypt);
  const struct ccmode_cbc *c=t?(d?&s24_kernel_tdes_cbc_decrypt:&s24_kernel_tdes_cbc_encrypt):(d?&s24_kernel_des_cbc_decrypt:&s24_kernel_des_cbc_encrypt);
  memcpy(before+at,e,sizeof(*e));at+=sizeof(*e);memcpy(before+at,c,sizeof(*c));at+=sizeof(*c);
 }
#define CHECK(x) do {++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
 CHECK(at==sizeof(before));CHECK(!s24_kernel_des_ecb_mode(0,0)&&!s24_kernel_des_cbc_mode(1,1));
 CHECK(s24_kernel_des_cbc_encrypt.init(&s24_kernel_des_cbc_encrypt,key,8,vector_bytes)==CCERR_CALL_SEQUENCE);
 CHECK(s24_kernel_des_key_is_weak((void*)vector_bytes,8)==CCERR_CALL_SEQUENCE);
#ifdef KDES_FACTORY_MISMATCH
 CHECK(s24_kernel_des_prepare()==CCERR_INTERNAL);CHECK(s24_kernel_des_prepare()==CCERR_INTERNAL);
 CHECK(!s24_kernel_des_ecb_mode(0,0)&&!s24_kernel_des_cbc_mode(1,1));
 CHECK(s24_kernel_des_cbc_encrypt.init(&s24_kernel_des_cbc_encrypt,key,8,vector_bytes)==CCERR_CALL_SEQUENCE);
#else
 CHECK(pthread_create(&first,NULL,prepare_thread,&initial)==0);started=1;
 while(!__atomic_load_n(&entered,__ATOMIC_ACQUIRE))sched_yield();
 CHECK(s24_kernel_des_prepare()==CCERR_CALL_SEQUENCE);CHECK(!s24_kernel_des_ecb_mode(0,0));
 for(unsigned i=0;i<16;++i){CHECK(pthread_create(&threads[i],NULL,prepare_thread,&results[i])==0);++created;}
 for(unsigned i=0;i<created;++i){CHECK(pthread_join(threads[i],NULL)==0);CHECK(results[i].prepare==CCERR_CALL_SEQUENCE&&!results[i].algorithm);}
 created=0;__atomic_store_n(&release_gate,1,__ATOMIC_RELEASE);CHECK(pthread_join(first,NULL)==0);started=0;
 CHECK(!initial.prepare&&initial.algorithm);
 for(unsigned i=0;i<16;++i){CHECK(pthread_create(&threads[i],NULL,prepare_thread,&results[i])==0);++created;}
 for(unsigned i=0;i<created;++i){CHECK(pthread_join(threads[i],NULL)==0);CHECK(!results[i].prepare&&results[i].algorithm);}
 created=0;CHECK(s24_kernel_des_prepare()==0);CHECK(algorithm());
 CHECK(!s24_kernel_des_ecb_mode(2,0)&&!s24_kernel_des_cbc_mode(0,-1));
 CHECK(s24_kernel_tdes_cbc_encrypt.init(&s24_kernel_tdes_cbc_encrypt,key,16,vector_bytes)==CCERR_PARAMETER);
 struct ccmode_cbc copy=s24_kernel_des_cbc_encrypt;
 CHECK(copy.init(&copy,key,8,vector_bytes)==CCERR_CALL_SEQUENCE);
#endif
 at=0;
 for(int t=0;t<2;++t)for(int d=0;d<2;++d){
  const struct ccmode_ecb *e=t?(d?&s24_kernel_tdes_ecb_decrypt:&s24_kernel_tdes_ecb_encrypt):(d?&s24_kernel_des_ecb_decrypt:&s24_kernel_des_ecb_encrypt);
  const struct ccmode_cbc *c=t?(d?&s24_kernel_tdes_cbc_decrypt:&s24_kernel_tdes_cbc_encrypt):(d?&s24_kernel_des_cbc_decrypt:&s24_kernel_des_cbc_encrypt);
  CHECK(!memcmp(before+at,e,sizeof(*e)));at+=sizeof(*e);CHECK(!memcmp(before+at,c,sizeof(*c)));at+=sizeof(*c);
 }
done:
 __atomic_store_n(&release_gate,1,__ATOMIC_RELEASE);if(started)pthread_join(first,NULL);
 for(unsigned i=0;i<created;++i)pthread_join(threads[i],NULL);
 printf("KDES PUBLICATION %s checks=%u failure_line=%d\n",failure?"FAIL":"PASS",checks,failure);return failure?1:0;
}
