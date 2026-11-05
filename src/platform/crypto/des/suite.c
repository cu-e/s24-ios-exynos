/* Same real DES adapter suite is executed on sanitized host and actual ARM CPU. */
#include "des.h"
#include <corecrypto/ccmode.h>
#include "vectors.h"
#include <stdint.h>
#include <string.h>
#ifdef DES_HOST
#include <stdio.h>
#endif
static unsigned checks;
static int failure;
#define CHECK(x) do { ++checks;if(!(x)) { failure=__LINE__;goto done; } } while(0)
static int zero(const void *p,size_t n) {const unsigned char*b=p;unsigned v=0;while(n--)v|=*b++;return !v;}
static int run_vector(const struct vector*v)
{
 struct ccmode_ecb e;struct ccmode_cbc c;
 ccecb_ctx_decl(768,ek);ccecb_ctx_decl(768,ecopy);
 cccbc_ctx_decl(768,ck);cccbc_ctx_decl(768,ccopy);cccbc_iv_decl(8,iv);
 unsigned char out[VECTOR_MAX+2],back[VECTOR_MAX+2],saved[768],raw[24];
 const unsigned char *key=vector_bytes+v->key,*initial=vector_bytes+v->iv,*pt=vector_bytes+v->pt,*ct=vector_bytes+v->ct;
 size_t blocks=v->bytes/8;
 for(int d=0;d<2;++d) {
  const unsigned char *input=d?ct:pt,*expected=d?pt:ct;
  CHECK(s24_des_ecb_descriptor(&e,v->n!=8,d)==0 && s24_des_cbc_descriptor(&c,v->n!=8,d)==0);
  CHECK(!e.roundkey && e.impl==CC_IMPL_UNKNOWN && !c.custom && e.block_size==8 && c.block_size==8);
  CHECK(e.size<=(v->n==8?256:768) && c.size==e.size);
  memset(ek,0xa5,768);memset(ck,0xa5,768);memcpy(raw,key,v->n);
  CHECK((v->cbc?c.init(&c,ck,v->n,raw):e.init(&e,ek,v->n,raw))==0);
  memset(raw,0xa6,sizeof(raw)); /* schedule owns key bytes; caller storage expires */
  if(v->cbc) {memcpy(saved,ck,c.size);memcpy(ccopy,ck,c.size);memcpy(iv,initial,8);}
  else {memcpy(saved,ek,e.size);memcpy(ecopy,ek,e.size);}
  memset(out,0xa5,sizeof(out));
  CHECK((v->cbc?c.cbc(ck,iv,blocks,input,out+1):e.ecb(ek,blocks,input,out+1))==0);
  CHECK(!memcmp(out+1,expected,v->bytes) && out[0]==0xa5 && out[v->bytes+1]==0xa5);
  CHECK(!memcmp(saved,v->cbc?(const void*)ck:(const void*)ek,e.size));
  if(v->cbc)CHECK(!memcmp(iv,ct+v->bytes-8,8));
  memcpy(back+1,input,v->bytes);if(v->cbc)memcpy(iv,initial,8);
  CHECK((v->cbc?c.cbc(ccopy,iv,blocks,back+1,back+1):e.ecb(ecopy,blocks,back+1,back+1))==0);
  CHECK(!memcmp(back+1,expected,v->bytes));
  if(v->cbc)CHECK(!memcmp(iv,ct+v->bytes-8,8));
  for(size_t split=0;split<=blocks;++split) {
   if(v->cbc)memcpy(iv,initial,8);
   CHECK((v->cbc?c.cbc(ck,iv,split,input,out+1):e.ecb(ek,split,input,out+1))==0);
   CHECK((v->cbc?c.cbc(ck,NULL,0,NULL,NULL):e.ecb(ek,0,NULL,NULL))==0);
   CHECK((v->cbc?c.cbc(ck,iv,blocks-split,input+8*split,out+1+8*split):e.ecb(ek,blocks-split,input+8*split,out+1+8*split))==0);
   CHECK(!memcmp(out+1,expected,v->bytes));
   if(v->cbc)CHECK(!memcmp(iv,ct+v->bytes-8,8));
  }
  CHECK(!memcmp(saved,v->cbc?(const void*)ck:(const void*)ek,e.size));
  CHECK(s24_des_ecb_clear(&e,ek)==0 && zero(ek,e.size));
  CHECK(s24_des_cbc_clear(&c,ck)==0 && zero(ck,c.size));
  CHECK(e.ecb(ek,0,NULL,NULL)==CCERR_CALL_SEQUENCE && c.cbc(ck,NULL,0,NULL,NULL)==CCERR_CALL_SEQUENCE);
  /* A copied schedule remains independently usable after clearing original. */
  if(v->cbc)memcpy(iv,initial,8);
  CHECK((v->cbc?c.cbc(ccopy,iv,blocks,input,out):e.ecb(ecopy,blocks,input,out))==0 && !memcmp(out,expected,v->bytes));
  CHECK(s24_des_ecb_clear(&e,ecopy)==0 && s24_des_cbc_clear(&c,ccopy)==0);
 }
done:
 memset(ek,0,768);memset(ck,0,768);memset(ecopy,0,768);memset(ccopy,0,768);memset(raw,0,sizeof(raw));return !failure;
}
static int contracts(void)
{
 struct ccmode_ecb e,wrong,snap;struct ccmode_cbc c,cwrong,csnap;
 ccecb_ctx_decl(768,ek);cccbc_ctx_decl(768,ck);cccbc_iv_decl(16,iv);
 unsigned char key[24],buf[64],before[64],saved[768],ivsave[16];
 _Alignas(16) unsigned char unaligned[800],misdesc[80];
 for(unsigned i=0;i<24;++i)key[i]=(unsigned char)i;
 for(int t=0;t<2;++t)for(int d=0;d<2;++d) {
  CHECK(s24_des_ecb_descriptor(&e,t,d)==0 && s24_des_cbc_descriptor(&c,t,d)==0);
  snap=e;csnap=c;
  memset(misdesc,0xa5,sizeof(misdesc));
  CHECK(s24_des_ecb_descriptor((struct ccmode_ecb*)(misdesc+1),t,d)==CCERR_PARAMETER);
  CHECK(s24_des_cbc_descriptor((struct ccmode_cbc*)(misdesc+1),t,d)==CCERR_PARAMETER);
  for(unsigned i=0;i<sizeof(misdesc);++i)CHECK(misdesc[i]==0xa5);
  CHECK(s24_des_ecb_descriptor(NULL,t,d)==CCERR_PARAMETER && s24_des_cbc_descriptor(NULL,t,d)==CCERR_PARAMETER);
  CHECK(s24_des_ecb_descriptor(&e,2,d)==CCERR_PARAMETER && !memcmp(&e,&snap,sizeof(e)));
  CHECK(s24_des_cbc_descriptor(&c,t,-1)==CCERR_PARAMETER && !memcmp(&c,&csnap,sizeof(c)));
  memset(ek,0x5a,768);memset(ck,0x5a,768);memcpy(saved,ek,768);
  CHECK(e.ecb(ek,0,NULL,NULL)==CCERR_CALL_SEQUENCE && c.cbc(ck,NULL,0,NULL,NULL)==CCERR_CALL_SEQUENCE);
  for(size_t n=0;n<33;++n)if(t?(n!=16&&n!=24):n!=8) {
   CHECK(e.init(&e,ek,n,key)==CCERR_PARAMETER && !memcmp(ek,saved,768));
   CHECK(c.init(&c,ck,n,key)==CCERR_PARAMETER && !memcmp(ck,saved,768));
  }
  size_t n=t?24:8;
  memset(unaligned,0xa5,sizeof(unaligned));
  CHECK(e.init(&e,(ccecb_ctx*)(unaligned+1),n,key)==CCERR_PARAMETER);
  CHECK(c.init(&c,(cccbc_ctx*)(unaligned+1),n,key)==CCERR_PARAMETER);
  CHECK(e.ecb((const ccecb_ctx*)(unaligned+1),1,key,buf)==CCERR_PARAMETER);
  CHECK(c.cbc((const cccbc_ctx*)(unaligned+1),iv,1,key,buf)==CCERR_PARAMETER);
  for(unsigned i=0;i<sizeof(unaligned);++i)CHECK(unaligned[i]==0xa5);
  CHECK(e.init(&e,ek,n,NULL)==CCERR_PARAMETER && !memcmp(ek,saved,768));
  CHECK(c.init(&c,ck,n,NULL)==CCERR_PARAMETER && !memcmp(ck,saved,768));
  CHECK(e.init(&e,ek,n,key)==0 && c.init(&c,ck,n,key)==0);
  for(size_t i=e.size;i<768;++i)CHECK(((unsigned char*)ek)[i]==0x5a && ((unsigned char*)ck)[i]==0x5a);
  memcpy(saved,ek,768);
  CHECK(e.init(&e,ek,7,key)==CCERR_PARAMETER && !memcmp(ek,saved,768));
  CHECK(e.init(&e,ek,n,ek)==CCERR_PARAMETER && !memcmp(ek,saved,768));
  wrong=e;wrong.size++;CHECK(e.init(&wrong,ek,n,key)==CCERR_PARAMETER && !memcmp(ek,saved,768));
  CHECK(s24_des_ecb_descriptor(&wrong,t,!d)==0 && wrong.ecb(ek,1,key,buf)==CCERR_CALL_SEQUENCE);
  CHECK(s24_des_cbc_descriptor(&cwrong,t,!d)==0 && cwrong.cbc(ck,iv,1,key,buf)==CCERR_CALL_SEQUENCE);
  CHECK(e.ecb(ek,SIZE_MAX/8+1,NULL,NULL)==CCERR_OVERFLOW && c.cbc(ck,iv,SIZE_MAX,NULL,NULL)==CCERR_OVERFLOW);
  CHECK(e.ecb(ek,0,NULL,NULL)==0 && c.cbc(ck,NULL,0,NULL,NULL)==0);
  memset(buf,0xa5,64);memcpy(before,buf,64);memset(iv,0x77,16);memcpy(ivsave,iv,16);
  CHECK(e.ecb(ek,2,buf,buf+1)==CCERR_PARAMETER && !memcmp(buf,before,64));
  CHECK(c.cbc(ck,iv,2,buf,buf+1)==CCERR_PARAMETER && !memcmp(buf,before,64) && !memcmp(iv,ivsave,16));
  CHECK(e.ecb(ek,1,NULL,buf)==CCERR_PARAMETER && e.ecb(ek,1,buf,NULL)==CCERR_PARAMETER);
  CHECK(e.ecb(ek,1,ek,buf)==CCERR_PARAMETER && e.ecb(ek,1,buf,ek)==CCERR_PARAMETER && !memcmp(ek,saved,768));
  CHECK(c.cbc(ck,NULL,1,buf,buf)==CCERR_PARAMETER);
  CHECK(c.cbc(ck,(cccbc_iv*)ck,1,buf,buf)==CCERR_PARAMETER);
  CHECK(c.cbc(ck,iv,1,iv,buf)==CCERR_PARAMETER && c.cbc(ck,iv,1,buf,iv)==CCERR_PARAMETER);
  const void *wrap=(const void*)(uintptr_t)(UINTPTR_MAX-3);
  CHECK(e.ecb(ek,1,wrap,buf)==CCERR_PARAMETER && e.ecb(ek,1,buf,(void*)wrap)==CCERR_PARAMETER);
  CHECK(c.cbc(ck,iv,1,wrap,buf)==CCERR_PARAMETER && !memcmp(iv,ivsave,16));
  CHECK(e.init(&e,ek,n,wrap)==CCERR_PARAMETER && !memcmp(ek,saved,768));
  CHECK(e.ecb((const ccecb_ctx*)(uintptr_t)(UINTPTR_MAX-15),1,key,buf)==CCERR_PARAMETER);
  CHECK(c.cbc(ck,(cccbc_iv*)(unaligned+1),1,buf,buf)==CCERR_PARAMETER);
  CHECK(!memcmp(buf,before,64));
  memcpy(saved,ck,768);cwrong=c;cwrong.block_size=16;
  CHECK(c.init(&cwrong,ck,n,key)==CCERR_PARAMETER && !memcmp(ck,saved,768));
  CHECK(c.init(&c,ck,n,ck)==CCERR_PARAMETER && !memcmp(ck,saved,768));
  CHECK(s24_des_ecb_clear(&e,ek)==0 && zero(ek,e.size));
  CHECK(s24_des_cbc_clear(&c,ck)==0 && zero(ck,c.size));
  for(size_t i=e.size;i<768;++i)CHECK(((unsigned char*)ek)[i]==0x5a && ((unsigned char*)ck)[i]==0x5a);
  CHECK(s24_des_ecb_clear(NULL,ek)==CCERR_PARAMETER && s24_des_cbc_clear(NULL,ck)==CCERR_PARAMETER);
 }
done:return !failure;
}
static int helper_tests(void)
{
 unsigned char key[10],saved[10];
 for(unsigned i=0;i<sizeof(helpers)/sizeof(helpers[0]);++i) {
  key[0]=0x5a;key[9]=0xa5;memcpy(key+1,helpers[i].key,8);memcpy(saved,key,10);
  CHECK(s24_des_key_is_weak(key+1,8)==helpers[i].weak && !memcmp(key,saved,10));
  s24_des_key_set_odd_parity(key+1,8);
  CHECK(!memcmp(key+1,helpers[i].parity,8) && key[0]==0x5a && key[9]==0xa5);
  for(unsigned j=0;j<8;++j) {
   CHECK((key[j+1]&0xfe)==(saved[j+1]&0xfe));
   unsigned ones=0;for(unsigned bit=0;bit<8;++bit)ones+=(key[j+1]>>bit)&1;
   CHECK(ones&1);
  }
  memcpy(saved,key,10);s24_des_key_set_odd_parity(key+1,8);CHECK(!memcmp(saved,key,10));
 }
 for(unsigned n=0;n<33;++n)if(n!=8) {
  memset(key,0xa5,10);memcpy(saved,key,10);
  CHECK(s24_des_key_is_weak(key+1,n)==CCERR_PARAMETER && !memcmp(key,saved,10));
  s24_des_key_set_odd_parity(key+1,n);CHECK(!memcmp(key,saved,10));
 }
 CHECK(s24_des_key_is_weak(NULL,8)==CCERR_PARAMETER);s24_des_key_set_odd_parity(NULL,8);
 void *wrap=(void*)(uintptr_t)(UINTPTR_MAX-3);
 CHECK(s24_des_key_is_weak(wrap,8)==CCERR_PARAMETER);s24_des_key_set_odd_parity(wrap,8);
done:return !failure;
}
int des_suite(unsigned *count)
{
 checks=0;failure=0;
 if(contracts() && helper_tests())for(unsigned i=0;i<VECTOR_COUNT;++i)if(!run_vector(vectors+i))break;
 *count=checks;return failure;
}
#ifdef DES_HOST
int main(void)
{
 unsigned count;int f=des_suite(&count);printf("DES HOST %s vectors=%u checks=%u failure_line=%d\n",f?"FAIL":"PASS",VECTOR_COUNT,count,f);return !!f;
}
#endif
