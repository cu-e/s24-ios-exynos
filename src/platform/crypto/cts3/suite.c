/* Same real generic composition, real CBCs and oracle records on host/ARM CPU. */
#include "cts3.h"
#include "fixture_aes.h"
#include "vectors.h"
#include <stdint.h>
#include <string.h>
#ifdef CTS3_HOST
#include <stdio.h>
#endif
static unsigned checks,active_vector;
static int failure;
#define CHECK(x) do{++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
#define CRYPT(d,m,c,v,n,a,b) ((d)?s24_cts3_decrypt(m,c,v,n,a,b):s24_cts3_encrypt(m,c,v,n,a,b))
static int zero(const void*p,size_t n){const unsigned char*b=p;unsigned x=0;while(n--)x|=*b++;return !x;}
static int tail_canary(const void*p,size_t b){const unsigned char*a=p;for(size_t i=b;i<16;++i)if(a[i]!=0x77)return 0;return 1;}
static void set_iv(cccbc_iv*v,const unsigned char*p,size_t b){memset(v,0x77,16);memcpy(v,p,b);}
static int run_vector(const struct vector*v)
{
 struct ccmode_cbc m={0};cccbc_ctx_decl(768,key);cccbc_ctx_decl(768,copy);cccbc_iv_decl(16,iv);
 unsigned char out[VECTOR_MAX+2],back[VECTOR_MAX+2],saved[768],raw[32];
 const unsigned char *k=vector_bytes+v->key,*initial=vector_bytes+v->iv,*pt=vector_bytes+v->pt,*ct=vector_bytes+v->ct,*next=vector_bytes+v->next_iv;
 size_t prefix_blocks=(v->bytes-1)/v->b-1;
 for(int d=0;d<2;++d){
  const unsigned char*input=d?ct:pt,*expected=d?pt:ct;
  CHECK(cts3_fixture_mode(&m,v->algorithm,d)==0&&m.block_size==v->b&&m.size<=768);
  memset(key,0x5a,768);memcpy(raw,k,v->n);CHECK(m.init(&m,key,v->n,raw)==0);memset(raw,0xa5,32);
  memcpy(saved,key,m.size);memcpy(copy,key,m.size);
  memset(out,0xa5,sizeof(out));set_iv(iv,initial,v->b);
  CHECK(CRYPT(d,&m,key,iv,v->bytes,input,out+1)==v->bytes);
  CHECK(!memcmp(out+1,expected,v->bytes)&&out[0]==0xa5&&out[v->bytes+1]==0xa5);
  CHECK(!memcmp(iv,next,v->b)&&tail_canary(iv,v->b)&&!memcmp(saved,key,m.size));
  memset(back,0xa5,sizeof(back));memcpy(back+1,input,v->bytes);set_iv(iv,initial,v->b);
  CHECK(CRYPT(d,&m,key,iv,v->bytes,back+1,back+1)==v->bytes&&!memcmp(back+1,expected,v->bytes));
  CHECK(back[0]==0xa5&&back[v->bytes+1]==0xa5&&!memcmp(iv,next,v->b)&&tail_canary(iv,v->b));
  /* Selected NFS-style split: ordinary CBC prefix followed by one CTS tail. */
  for(size_t split=0;split<=prefix_blocks;++split){
   memset(out,0xa5,sizeof(out));set_iv(iv,initial,v->b);size_t bytes=split*v->b;
   if(split)CHECK(m.cbc(key,iv,split,input,out+1)==0);
   CHECK(CRYPT(d,&m,key,iv,v->bytes-bytes,input+bytes,out+1+bytes)==v->bytes-bytes);
   CHECK(!memcmp(out+1,expected,v->bytes)&&!memcmp(iv,next,v->b)&&tail_canary(iv,v->b));
   CHECK(out[0]==0xa5&&out[v->bytes+1]==0xa5&&!memcmp(saved,key,m.size));
  }
  /* Continue with a second independent CTS message, carrying the actual IV. */
  const unsigned char *second_in=d?vector_bytes+v->chain_ct:pt,*second_expected=d?pt:vector_bytes+v->chain_ct;
  CHECK(CRYPT(d,&m,key,iv,v->bytes,second_in,out)==v->bytes&&!memcmp(out,second_expected,v->bytes));
  CHECK(!memcmp(iv,vector_bytes+v->chain_iv,v->b)&&tail_canary(iv,v->b));
  /* A real self-contained copied backend key survives original clearing. */
  CHECK(cts3_fixture_clear(&m,key)==0&&zero(key,m.size));set_iv(iv,initial,v->b);
  CHECK(CRYPT(d,&m,copy,iv,v->bytes,input,out)==v->bytes&&!memcmp(out,expected,v->bytes));
  CHECK(!memcmp(saved,copy,m.size)&&!memcmp(iv,next,v->b));
  memset(out,0xa5,sizeof(out));set_iv(iv,initial,v->b);
  CHECK(CRYPT(d,&m,key,iv,v->bytes,input,out+1)==0&&zero(out+1,v->bytes));
  CHECK(out[0]==0xa5&&out[v->bytes+1]==0xa5&&!memcmp(iv,initial,v->b)&&tail_canary(iv,v->b));
  CHECK(cts3_fixture_clear(&m,copy)==0&&zero(copy,m.size));
 }
done:memset(key,0,768);memset(copy,0,768);memset(raw,0,32);return !failure;
}
static int backend_faults(const struct vector*v)
{
 struct ccmode_cbc m={0},wrapped;cccbc_ctx_decl(768,key);cccbc_iv_decl(16,iv);
 unsigned char out[VECTOR_MAX+2],input[VECTOR_MAX+2],saved[768];
 const unsigned char*k=vector_bytes+v->key,*initial=vector_bytes+v->iv;
 for(int d=0;d<2;++d){
  const unsigned char*data=vector_bytes+(d?v->ct:v->pt),*expected=vector_bytes+(d?v->pt:v->ct);
  CHECK(cts3_fixture_mode(&m,v->algorithm,d)==0&&m.init(&m,key,v->n,k)==0);memcpy(saved,key,m.size);
  cts3_fixture_fault(&m,0,&wrapped);set_iv(iv,initial,v->b);
  CHECK(CRYPT(d,&wrapped,key,iv,v->bytes,data,out)==v->bytes&&!memcmp(out,expected,v->bytes));
  unsigned calls=cts3_fixture_calls();CHECK(calls==((v->bytes>2*v->b)?1u:0u)+(d?2u:1u));
  for(unsigned at=1;at<=calls;++at)for(unsigned in_place=0;in_place<2;++in_place){
   cts3_fixture_fault(&m,at,&wrapped);set_iv(iv,initial,v->b);
   memset(out,0xa5,sizeof(out));memset(input,0x5a,sizeof(input));memcpy(input+1,data,v->bytes);
   if(in_place)memcpy(out+1,data,v->bytes);
   CHECK(CRYPT(d,&wrapped,key,iv,v->bytes,in_place?out+1:input+1,out+1)==0);
   CHECK(cts3_fixture_calls()==at&&zero(out+1,v->bytes)&&out[0]==0xa5&&out[v->bytes+1]==0xa5);
   CHECK(!memcmp(iv,initial,v->b)&&tail_canary(iv,v->b)&&!memcmp(key,saved,m.size));
   CHECK(!memcmp(input+1,data,v->bytes)&&input[0]==0x5a&&input[v->bytes+1]==0x5a);
  }
  CHECK(cts3_fixture_clear(&m,key)==0);
 }
done:memset(key,0,768);return !failure;
}
static int qualify_cbc16(const struct vector*v)
{
 struct ccmode_cbc m={0};cccbc_ctx_decl(768,key);cccbc_iv_decl(16,iv);
 unsigned char out[VECTOR_MAX+2],saved[768];const unsigned char*k=vector_bytes+v->key,*initial=vector_bytes+v->iv;
 for(int d=0;d<2;++d){
  const unsigned char *in=vector_bytes+(d?v->ct:v->pt),*expected=vector_bytes+(d?v->pt:v->ct);
  CHECK(cts3_fixture_mode(&m,2,d)==0&&m.init(&m,key,v->n,k)==0);memcpy(saved,key,m.size);
  set_iv(iv,initial,16);CHECK(m.cbc(key,iv,v->bytes/16,in,out+1)==0&&!memcmp(out+1,expected,v->bytes));
  CHECK(!memcmp(iv,vector_bytes+v->next_iv,16)&&!memcmp(key,saved,m.size));
  memcpy(out+1,in,v->bytes);set_iv(iv,initial,16);CHECK(m.cbc(key,iv,v->bytes/16,out+1,out+1)==0&&!memcmp(out+1,expected,v->bytes));
  for(unsigned split=0;split<=v->bytes/16;++split){
   set_iv(iv,initial,16);CHECK(m.cbc(key,NULL,0,NULL,NULL)==0);
   CHECK(m.cbc(key,iv,split,in,out)==0&&m.cbc(key,iv,v->bytes/16-split,in+split*16,out+split*16)==0);
   CHECK(!memcmp(out,expected,v->bytes)&&!memcmp(iv,vector_bytes+v->next_iv,16)&&!memcmp(key,saved,m.size));
  }
  CHECK(cts3_fixture_clear(&m,key)==0&&zero(key,m.size));
 }
done:memset(key,0,768);return !failure;
}
static int contracts(void)
{
 struct ccmode_cbc m={0},bad,snap;cccbc_ctx_decl(768,key);cccbc_iv_decl(16,iv);
 unsigned char k[32],input[96],out[96],before[96],saved[768],ivsave[16];
 _Alignas(16) unsigned char unaligned[800];
 for(unsigned i=0;i<32;++i)k[i]=(unsigned char)i;
 for(unsigned algorithm=0;algorithm<3;++algorithm)for(int d=0;d<2;++d){
  size_t kn=algorithm==0?8:algorithm==1?24:32;
  CHECK(cts3_fixture_mode(&m,algorithm,d)==0);size_t b=m.block_size,n=2*b+1;
  memset(key,0x5a,768);CHECK(m.init(&m,key,kn,k)==0);memcpy(saved,key,768);snap=m;
  memset(input,0x6a,96);memset(out,0xa5,96);memcpy(before,out,96);memset(iv,0x77,16);memcpy(ivsave,iv,16);
  for(size_t short_n=0;short_n<=b;++short_n){
   CHECK(CRYPT(d,&m,key,iv,short_n,input,out)==0&&!memcmp(out,before,96));
   CHECK(!memcmp(iv,ivsave,16)&&!memcmp(key,saved,768));
  }
  CHECK(CRYPT(d,NULL,key,iv,n,input,out)==0&&CRYPT(d,&m,NULL,iv,n,input,out)==0&&CRYPT(d,&m,key,NULL,n,input,out)==0);
  CHECK(CRYPT(d,&m,key,iv,n,NULL,out)==0&&CRYPT(d,&m,key,iv,n,input,NULL)==0);
  CHECK(!memcmp(out,before,96)&&!memcmp(iv,ivsave,16)&&!memcmp(key,saved,768));
  bad=m;bad.block_size=0;CHECK(CRYPT(d,&bad,key,iv,n,input,out)==0);
  bad=m;bad.block_size=CCMODE_MAX_BLOCK_SIZE+1;CHECK(CRYPT(d,&bad,key,iv,n,input,out)==0);
  bad=m;bad.size=0;CHECK(CRYPT(d,&bad,key,iv,n,input,out)==0);
  bad=m;bad.size=SIZE_MAX;CHECK(CRYPT(d,&bad,key,iv,n,input,out)==0);
  bad=m;bad.init=NULL;CHECK(CRYPT(d,&bad,key,iv,n,input,out)==0);
  bad=m;bad.cbc=NULL;CHECK(CRYPT(d,&bad,key,iv,n,input,out)==0);
  CHECK(!memcmp(out,before,96)&&!memcmp(iv,ivsave,16)&&!memcmp(key,saved,768));
  CHECK(CRYPT(d,&m,key,iv,n,input,input+1)==0&&CRYPT(d,&m,key,iv,n,input+1,input)==0);
  CHECK(CRYPT(d,&m,key,iv,n,key,out)==0&&CRYPT(d,&m,key,iv,n,input,key)==0);
  CHECK(CRYPT(d,&m,key,iv,n,&m,out)==0&&CRYPT(d,&m,key,iv,n,input,&m)==0&&!memcmp(&m,&snap,sizeof(m)));
  CHECK(CRYPT(d,&m,key,iv,n,iv,out)==0&&CRYPT(d,&m,key,iv,n,input,iv)==0);
  CHECK(CRYPT(d,&m,key,(cccbc_iv*)key,n,input,out)==0);
  CHECK(CRYPT(d,&m,(cccbc_ctx*)&m,iv,n,input,out)==0);
  CHECK(!memcmp(out,before,96)&&!memcmp(iv,ivsave,16)&&!memcmp(key,saved,768));
  memset(unaligned,0xa5,sizeof(unaligned));
  CHECK(CRYPT(d,(const struct ccmode_cbc*)(unaligned+1),key,iv,n,input,out)==0);
  CHECK(CRYPT(d,&m,(cccbc_ctx*)(unaligned+1),iv,n,input,out)==0);
  CHECK(CRYPT(d,&m,key,(cccbc_iv*)(unaligned+1),n,input,out)==0);
  for(unsigned i=0;i<sizeof(unaligned);++i)CHECK(unaligned[i]==0xa5);
  const void*wrap=(const void*)(uintptr_t)(UINTPTR_MAX-3);
  CHECK(CRYPT(d,&m,key,iv,n,wrap,out)==0&&CRYPT(d,&m,key,iv,n,input,(void*)wrap)==0);
  CHECK(CRYPT(d,&m,key,iv,SIZE_MAX,input,out)==0);
  CHECK(CRYPT(d,&m,(cccbc_ctx*)(uintptr_t)(UINTPTR_MAX-15),iv,n,input,out)==0);
  CHECK(CRYPT(d,(const struct ccmode_cbc*)(uintptr_t)(UINTPTR_MAX-15),key,iv,n,input,out)==0);
  CHECK(!memcmp(out,before,96)&&!memcmp(iv,ivsave,16)&&!memcmp(key,saved,768)&&!memcmp(&m,&snap,sizeof(m)));
  if(algorithm==2){
   for(size_t kn_bad=0;kn_bad<34;++kn_bad)if(kn_bad!=16&&kn_bad!=24&&kn_bad!=32)
    CHECK(m.init(&m,key,kn_bad,k)==CCERR_PARAMETER&&!memcmp(key,saved,768));
   CHECK(m.init(&m,key,kn,NULL)==CCERR_PARAMETER&&m.init(&m,key,kn,key)==CCERR_PARAMETER&&!memcmp(key,saved,768));
   CHECK(m.cbc(key,iv,SIZE_MAX/16+1,input,out)==CCERR_OVERFLOW&&!memcmp(out,before,96));
   CHECK(m.cbc(key,iv,2,input,input+1)==CCERR_PARAMETER);
  }
  CHECK(cts3_fixture_clear(&m,key)==0&&zero(key,m.size));
  for(size_t i=m.size;i<768;++i)CHECK(((unsigned char*)key)[i]==0x5a);
 }
done:memset(key,0,768);return !failure;
}
int cts3_suite(unsigned *count)
{
 checks=0;failure=0;active_vector=0;
 if(contracts()){
  for(unsigned i=0;i<CBC_VECTOR_COUNT;++i){active_vector=i;if(!qualify_cbc16(cbc_vectors+i))goto done;}
  for(unsigned i=0;i<VECTOR_COUNT;++i){
   active_vector=i;const struct vector*v=vectors+i;if(!run_vector(v))break;
   if((v->bytes==v->b+1||v->bytes==2*v->b||v->bytes==4*v->b+1)&&!backend_faults(v))break;
  }
 }
done:*count=checks;return failure;
}
#ifdef CTS3_HOST
int main(void){unsigned count;int f=cts3_suite(&count);printf("CTS3 HOST %s vectors=%u cbc16=%u checks=%u failure_line=%d active_vector=%u\n",f?"FAIL":"PASS",VECTOR_COUNT,CBC_VECTOR_COUNT,count,f,active_vector);return !!f;}
#endif
