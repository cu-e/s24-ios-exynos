/* Owned partial genuine caller CPU fixture. Real selected declarations, native
 * corecrypto_des.c/register_crypto.c and focused actual ESP functions execute.
 * test_table is an owned10-slot fixture; full real46-slot provider is native
 * object/source proof only. No full provider startup/kernel/device qualification.
 */
#include <libkern/crypto/crypto_internal.h>
#include <libkern/crypto/des.h>
#include <kern/debug.h>
#include <mbedtls/platform_util.h>
#include "kernel_provider.h"
#include "runtime.h"
#include "vectors.h"
__attribute__((used,aligned(16))) unsigned char kdes_stack[65536];
__attribute__((aligned(4096))) static u64 tt0[512],tt1[512],high_l2[512];
unsigned long __stack_chk_guard=0x6b64657363707531UL;
__attribute__((noreturn)) void __stack_chk_fail(void){(panic)("synthetic canary");}
#define HIGH_L2_FIRST 32
/* Link-image control word; owned images patch its actual data offset, never
 * production algorithm/table/code.0x4b444553=normal,1=wrong expected answer,2=panic,3=spin. */
__attribute__((used)) volatile unsigned kdes_control=0x4b444553U;
static unsigned checks,failure,executed,esp_cases;
static struct crypto_functions test_table={
 .ccdes_ecb_encrypt=&s24_kernel_des_ecb_encrypt,.ccdes_ecb_decrypt=&s24_kernel_des_ecb_decrypt,
 .ccdes_cbc_encrypt=&s24_kernel_des_cbc_encrypt,.ccdes_cbc_decrypt=&s24_kernel_des_cbc_decrypt,
 .cctdes_ecb_encrypt=&s24_kernel_tdes_ecb_encrypt,.cctdes_ecb_decrypt=&s24_kernel_tdes_ecb_decrypt,
 .cctdes_cbc_encrypt=&s24_kernel_tdes_cbc_encrypt,.cctdes_cbc_decrypt=&s24_kernel_tdes_cbc_decrypt,
 .ccdes_key_is_weak_fn=s24_kernel_des_key_is_weak,.ccdes_key_set_odd_parity_fn=s24_kernel_des_key_set_odd_parity};
__attribute__((noreturn)) void (panic)(const char *fmt,...)
{(void)fmt;text("KDES SYNTHETIC PANIC\n");stop();}
__attribute__((noreturn)) void kdes_fixture_fail(unsigned line)
{text("KDES ESP ASSERT line=");hex(line);text(" case=");hex(esp_cases);putc('\n');stop();}
extern int kdes_esp_case(int,int,int,unsigned,unsigned,unsigned,unsigned,const unsigned char*,const unsigned char*,const unsigned char*,const unsigned char*);
#define CHECK(x) do{++checks;if(!(x)){if(!failure)failure=__LINE__;goto done;}}while(0)
static int zero(const void *p,size_t n){const unsigned char *b=p;unsigned v=0;while(n--)v|=*b++;return !v;}
static int vectors_and_contracts(void)
{
 des_ecb_key_schedule single;des3_ecb_key_schedule triple;
 ccecb_ctx_decl(768,ek);cccbc_ctx_decl(768,ck);cccbc_iv_decl(16,iv);
 unsigned char out[VECTOR_MAX+2],back[VECTOR_MAX+2],snapshot[768],expected[VECTOR_MAX],raw[24];
 for(unsigned i=0;i<VECTOR_COUNT;++i){const struct vector *v=&vectors[i];if(v->n==16)continue;executed++;
  const unsigned char *key=vector_bytes+v->key,*initial=vector_bytes+v->iv,*pt=vector_bytes+v->pt,*ct=vector_bytes+v->ct;size_t blocks=v->bytes/8;
  for(int d=0;d<2;++d){const void *input=d?(const void*)ct:(const void*)pt;memcpy(expected,d?pt:ct,v->bytes);
   if(kdes_control==1&&executed==1&&!d)expected[0]^=1;
   const struct ccmode_ecb *e=s24_kernel_des_ecb_mode(v->n==24,d);const struct ccmode_cbc *c=s24_kernel_des_cbc_mode(v->n==24,d);
   CHECK(e&&c&&e->size==(v->n==24?400U:144U)&&c->size==e->size);
   memcpy(raw,key,v->n);memset(ek,0xa5,768);memset(ck,0xa5,768);CHECK((v->cbc?cccbc_init(c,ck,v->n,raw):ccecb_init(e,ek,v->n,raw))==0);memset(raw,0,sizeof(raw));
   memcpy(snapshot,v->cbc?(const void*)ck:(const void*)ek,e->size);CHECK(cccbc_set_iv(c,iv,initial)==0);memset(out,0xa5,sizeof(out));
   CHECK((v->cbc?cccbc_update(c,ck,iv,blocks,input,out+1):ccecb_update(e,ek,blocks,input,out+1))==0);
   CHECK(!memcmp(out+1,expected,v->bytes)&&out[0]==0xa5&&out[v->bytes+1]==0xa5);
   CHECK(!memcmp(snapshot,v->cbc?(const void*)ck:(const void*)ek,e->size));if(v->cbc)CHECK(!memcmp(iv,ct+v->bytes-8,8));
   memcpy(back+1,input,v->bytes);CHECK(cccbc_set_iv(c,iv,initial)==0);CHECK((v->cbc?c->cbc(ck,iv,blocks,back+1,back+1):e->ecb(ek,blocks,back+1,back+1))==0&&!memcmp(back+1,expected,v->bytes));
   if(v->cbc){CHECK(cccbc_set_iv(c,iv,initial)==0);for(size_t j=0;j<blocks;++j)CHECK(cccbc_update(c,ck,iv,1,(const unsigned char*)input+8*j,out+1+8*j)==0);CHECK(!memcmp(out+1,expected,v->bytes)&&!memcmp(iv,ct+v->bytes-8,8));}
   if(!v->cbc){des_cblock keycopy[3];memcpy(keycopy,key,v->n);CHECK((v->n==24?des3_ecb_key_sched(keycopy,&triple):des_ecb_key_sched(keycopy,&single))==0);memset(keycopy,0,sizeof(keycopy));
    for(size_t j=0;j<blocks;++j){des_cblock inblock,outblock;memcpy(inblock,(const unsigned char*)input+8*j,8);CHECK((v->n==24?des3_ecb_encrypt(&inblock,&outblock,&triple,!d):des_ecb_encrypt(&inblock,&outblock,&single,!d))==0);CHECK(!memcmp(outblock,expected+8*j,8));}
   }
  }
 }
 for(unsigned i=0;i<sizeof(helpers)/sizeof(helpers[0]);++i){des_cblock key;memcpy(key,helpers[i].key,8);CHECK(des_is_weak_key(&key)==helpers[i].weak&&!memcmp(key,helpers[i].key,8));g_crypto_funcs->ccdes_key_set_odd_parity_fn(key,8);CHECK(!memcmp(key,helpers[i].parity,8));}
 for(int t=0;t<2;++t)for(int d=0;d<2;++d){const struct ccmode_ecb *e=s24_kernel_des_ecb_mode(t,d);const struct ccmode_cbc *c=s24_kernel_des_cbc_mode(t,d);memset(raw,0,sizeof(raw));memset(ek,0xa5,768);memset(ck,0xa5,768);memcpy(snapshot,ek,768);
  CHECK(e->init(e,ek,t?16:7,raw)==CCERR_PARAMETER&&!memcmp(ek,snapshot,768));CHECK(c->init(c,ck,t?16:9,raw)==CCERR_PARAMETER&&!memcmp(ck,snapshot,768));
  struct ccmode_ecb copy=*e;struct ccmode_cbc ccopy=*c;CHECK(copy.init(&copy,ek,t?24:8,raw)==CCERR_CALL_SEQUENCE);CHECK(ccopy.init(&ccopy,ck,t?24:8,raw)==CCERR_CALL_SEQUENCE);
  CHECK(e->init(e,ek,t?24:8,raw)==0&&c->init(c,ck,t?24:8,raw)==0);memset(out,0xa5,sizeof(out));memcpy(back,out,sizeof(out));
  CHECK(e->ecb(ek,(size_t)-1/8+1,out,out)==CCERR_OVERFLOW&&!memcmp(out,back,sizeof(out)));CHECK(c->cbc(ck,iv,(size_t)-1/8+1,out,out)==CCERR_OVERFLOW&&!memcmp(out,back,sizeof(out)));
  CHECK(e->ecb(ek,1,out,out+1)==CCERR_PARAMETER&&!memcmp(out,back,sizeof(out)));CHECK(c->cbc(ck,iv,1,out,out+1)==CCERR_PARAMETER&&!memcmp(out,back,sizeof(out)));
  CHECK(e->ecb(ek,0,NULL,NULL)==0&&c->cbc(ck,NULL,0,NULL,NULL)==0);
  mbedtls_platform_zeroize(ek,768);mbedtls_platform_zeroize(ck,768);CHECK(e->ecb(ek,1,out,out)!=0&&c->cbc(ck,iv,1,out,out)!=0);
 }
 memset(&single,0,sizeof(single));memset(&triple,0,sizeof(triple));des_cblock input={0},output={0};
 CHECK(des_ecb_encrypt(&input,&output,&single,DES_ENCRYPT)!=0&&des3_ecb_encrypt(&input,&output,&triple,DES_DECRYPT)!=0);
 CHECK(des_ecb_key_sched(NULL,&single)!=0&&des3_ecb_key_sched(NULL,&triple)!=0);
 CHECK(s24_kernel_des_key_is_weak(NULL,8)!=0);memcpy(raw,helpers[0].key,8);g_crypto_funcs->ccdes_key_set_odd_parity_fn(raw,7);CHECK(!memcmp(raw,helpers[0].key,8));
 CHECK(executed==1964);
done:mbedtls_platform_zeroize(ek,768);mbedtls_platform_zeroize(ck,768);mbedtls_platform_zeroize(&single,sizeof(single));mbedtls_platform_zeroize(&triple,sizeof(triple));return !failure;
}
static int esp_contracts(void)
{
 for(int t=0;t<2;++t){const struct vector *v=NULL;for(unsigned i=0;i<VECTOR_COUNT;++i)if(vectors[i].n==(t?24U:8U)&&vectors[i].cbc&&vectors[i].bytes==24){v=&vectors[i];break;}CHECK(v);
  for(int d=0;d<2;++d)for(int fragmented=0;fragmented<3;++fragmented){
   const unsigned char *k=vector_bytes+v->key,*iv=vector_bytes+v->iv,*input=vector_bytes+(d?v->ct:v->pt),*expected=vector_bytes+(d?v->pt:v->ct);
   ++esp_cases;CHECK(kdes_esp_case(t,d,fragmented,0,0,0,0,k,iv,input,expected));
  }
 }
 text("KDES ESP BASELINE SUCCESS cases=");hex(esp_cases);putc('\n');
 for(int t=0;t<2;++t){const struct vector *v=NULL;for(unsigned i=0;i<VECTOR_COUNT;++i)if(vectors[i].n==(t?24U:8U)&&vectors[i].cbc&&vectors[i].bytes==24){v=&vectors[i];break;}CHECK(v);
  for(int d=0;d<2;++d)for(int f=0;f<3;++f){const unsigned char *k=vector_bytes+v->key,*iv=vector_bytes+v->iv,*input=vector_bytes+(d?v->ct:v->pt),*expected=vector_bytes+(d?v->pt:v->ct);
   for(unsigned n=1;n<=3;++n){++esp_cases;CHECK(kdes_esp_case(t,d,f,0,0,n,0,k,iv,input,expected));}
   for(unsigned n=1;n<=3;++n){++esp_cases;CHECK(kdes_esp_case(t,d,f,n,0,0,0,k,iv,input,expected));}
   ++esp_cases;CHECK(kdes_esp_case(t,d,f,0,1,0,0,k,iv,input,expected));
   for(unsigned n=1;n<=2;++n){++esp_cases;CHECK(kdes_esp_case(t,d,f,0,0,0,n,k,iv,input,expected));}
  }
 }
 CHECK(esp_cases==120);
done:return !failure;
}
__attribute__((noreturn)) void mapped_entry(void)
{
 u64 pc,sctlr;__asm__ volatile("adrp %0,_mapped_entry@PAGE\nadd %0,%0,_mapped_entry@PAGEOFF":"=r"(pc));__asm__ volatile("mrs %0,sctlr_el1":"=r"(sctlr));
 text("KDES MAPPED pc=");hex(pc);text(" mode=");hex((uptr)&s24_kernel_des_cbc_encrypt);text(" init=");hex((uptr)s24_kernel_des_cbc_encrypt.init);putc('\n');
 CHECK(pc>=0xfffffff007000000UL&&(sctlr&1));
 const u64 delta=0xffffffefc4000000UL,normal=1UL|(1UL<<10)|(3UL<<8);
 CHECK(tt1[448]==(((uptr)high_l2-delta)|3)&&tt0[1]==(0x40000000UL|normal));
 CHECK(high_l2[32]==(0x40000000UL|normal)&&high_l2[159]==(0x4fe00000UL|normal));CHECK((uptr)&s24_kernel_des_cbc_encrypt>=0xfffffff007000000UL&&(uptr)s24_kernel_des_cbc_encrypt.init>=0xfffffff007000000UL);
 if(kdes_control==2)(panic)("owned panic control");if(kdes_control==3){text("KDES SPIN CONTROL\n");for(;;)__asm__ volatile("wfe");}
 CHECK(!s24_kernel_des_ecb_mode(0,0)&&!s24_kernel_des_cbc_mode(1,1));CHECK(s24_kernel_des_prepare()==0&&s24_kernel_des_prepare()==0);
 CHECK(!g_crypto_funcs&&!crypto_init);CHECK(register_crypto_functions(&test_table)==0&&g_crypto_funcs==&test_table&&crypto_init);CHECK(register_crypto_functions(&test_table)!=0);
 CHECK(g_crypto_funcs->ccdes_ecb_encrypt==&s24_kernel_des_ecb_encrypt&&g_crypto_funcs->cctdes_cbc_decrypt==&s24_kernel_tdes_cbc_decrypt);
 CHECK(vectors_and_contracts());CHECK(esp_contracts());
done:text(failure?"KDES CALLER FAIL":"KDES CALLER PASS");text(" vectors=");hex(executed);text(" esp_cases=");hex(esp_cases);text(" checks=");hex(checks);text(" line=");hex(failure);putc('\n');stop();
}
#include "mapping.inc"
