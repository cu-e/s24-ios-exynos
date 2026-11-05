/* Focused independent host DES review controls, not a provider or kernel. */
#include "des.h"
#include <corecrypto/ccmode.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "review_cases.h"
static int allzero(const void *p,size_t n) { const unsigned char *b=p;unsigned v=0;for(size_t i=0;i<n;i++)v|=b[i];return !v; }
int main(void)
{
 unsigned cases=0;
 for(unsigned i=0;i<sizeof(review_cases)/sizeof(review_cases[0]);i++) {
  const struct review_case *v=&review_cases[i];size_t blocks=v->len/8;
  for(int decrypt=0;decrypt<2;decrypt++) {
   struct ccmode_ecb e;struct ccmode_cbc c;unsigned char out[256],inplace[256],saved[768],key[24];
   ccecb_ctx_decl(768,ec);cccbc_ctx_decl(768,bc);cccbc_iv_decl(16,iv);
   assert(s24_des_ecb_descriptor(&e,v->n!=8,decrypt)==CCERR_OK && s24_des_cbc_descriptor(&c,v->n!=8,decrypt)==CCERR_OK);
   assert(e.size<= (v->n==8?256u:768u) && !e.roundkey && e.impl==CC_IMPL_UNKNOWN && !c.custom && c.size==e.size && e.block_size==8 && c.block_size==8);
   const unsigned char *input=decrypt?v->ct:v->pt,*expected=decrypt?v->pt:v->ct;
   memset(ec,0x5a,768);memset(bc,0x5a,768);memcpy(key,v->key,v->n);
   assert((v->cbc?c.init(&c,bc,v->n,key):e.init(&e,ec,v->n,key))==CCERR_OK);
   memset(key,0xee,sizeof(key));memcpy(saved,v->cbc?(const void*)bc:(const void*)ec,e.size);
   memset(iv,0xa5,16);memcpy(iv,v->iv,8);memset(out,0xa5,sizeof(out));
   assert((v->cbc?c.cbc(bc,iv,blocks,input,out+1):e.ecb(ec,blocks,input,out+1))==CCERR_OK);
   assert(!memcmp(out+1,expected,v->len) && out[0]==0xa5 && out[v->len+1]==0xa5);
   assert(!memcmp(saved,v->cbc?(const void*)bc:(const void*)ec,e.size));
   for(unsigned j=8;j<16;j++)assert(((unsigned char*)iv)[j]==0xa5);
   if(v->cbc)assert(!memcmp(iv,v->ct+v->len-8,8));
   memcpy(inplace,input,v->len);memcpy(iv,v->iv,8);
   assert((v->cbc?c.cbc(bc,iv,1,inplace,inplace):e.ecb(ec,1,inplace,inplace))==CCERR_OK);
   assert((v->cbc?c.cbc(bc,NULL,0,NULL,NULL):e.ecb(ec,0,NULL,NULL))==CCERR_OK);
   assert((v->cbc?c.cbc(bc,iv,blocks-1,inplace+8,inplace+8):e.ecb(ec,blocks-1,inplace+8,inplace+8))==CCERR_OK && !memcmp(inplace,expected,v->len));
   unsigned char prior[256],iv_prior[16];memset(out,0x31,sizeof(out));memcpy(prior,out,sizeof(out));memcpy(iv_prior,iv,16);
   assert((v->cbc?c.cbc(bc,iv,2,out,out+1):e.ecb(ec,2,out,out+1))==CCERR_PARAMETER);
   assert(!memcmp(out,prior,sizeof(out)) && !memcmp(iv,iv_prior,16));
   assert((v->cbc?c.cbc(bc,iv,SIZE_MAX/8+1,NULL,NULL):e.ecb(ec,SIZE_MAX/8+1,NULL,NULL))==CCERR_OVERFLOW);
   assert((v->cbc?c.init(&c,bc,7,v->key):e.init(&e,ec,7,v->key))==CCERR_PARAMETER && !memcmp(saved,v->cbc?(const void*)bc:(const void*)ec,e.size));
   if(v->cbc)assert(c.cbc(bc,(cccbc_iv*)(out+1),1,v->pt,out)==CCERR_PARAMETER);
   assert((v->cbc?s24_des_cbc_clear(&c,bc):s24_des_ecb_clear(&e,ec))==CCERR_OK && allzero(v->cbc?(const void*)bc:(const void*)ec,e.size));
   for(size_t j=e.size;j<768;j++)assert((v->cbc?(unsigned char*)bc:(unsigned char*)ec)[j]==0x5a);
   assert((v->cbc?c.cbc(bc,NULL,0,NULL,NULL):e.ecb(ec,0,NULL,NULL))==CCERR_CALL_SEQUENCE);cases++;
  }
 }
 unsigned char key[24],snapshot[24];memset(key,0xfe,sizeof(key));memcpy(snapshot,key,sizeof(key));
 for(unsigned n=0;n<=24;n++)if(n!=8) {
  assert(s24_des_key_is_weak(key,n)!=0);s24_des_key_set_odd_parity(key,n);assert(!memcmp(key,snapshot,sizeof(key)));
 }
 unsigned helper_cases=0;
 for(unsigned b=0;b<256;b++) {
  memset(key,(int)b,8);memcpy(snapshot,key,8);int weak=s24_des_key_is_weak(key,8);assert(weak==0||weak==1);assert(!memcmp(key,snapshot,8));
  s24_des_key_set_odd_parity(key,8);
  for(unsigned j=0;j<8;j++) { unsigned ones=0;for(unsigned bit=0;bit<8;bit++)ones+=(key[j]>>bit)&1;assert((ones&1) && (key[j]&0xfe)==(snapshot[j]&0xfe)); }
  helper_cases++;
 }
 memset(key,0,8);assert(s24_des_key_is_weak(key,8)==1);memset(key,0xff,8);assert(s24_des_key_is_weak(key,8)==1);
 assert(s24_des_key_is_weak(NULL,8)!=0);s24_des_key_set_odd_parity(NULL,8);
 void *wrap=(void*)(uintptr_t)(UINTPTR_MAX-3);assert(s24_des_key_is_weak(wrap,8)!=0);s24_des_key_set_odd_parity(wrap,8);
 printf("{\"focused_mode_directions\":%u,\"helper_inputs\":%u,\"CBC_block_bytes\":8,\"QEMU_executed\":false,\"provider_registered\":false}\n",cases,helper_cases);
 return 0;
}
