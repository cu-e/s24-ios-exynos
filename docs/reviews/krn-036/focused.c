/* Independent review probe. Existing genuine CBC objects supply all crypto.
 * Fault controls first execute the real CBC, then report an admitted error. */
#include "cts3.h"
#include "fixture_aes.h"
#include "records.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned checks,calls,fail_at;
static struct ccmode_cbc backend;
static int postwrite_error(const cccbc_ctx *k,cccbc_iv *v,size_t n,const void *a,void *b)
{
 int r=backend.cbc(k,v,n,a,b);++calls;
 if(!r&&calls==fail_at)return CCERR_INTERNAL;
 return r;
}
static int zeros(const void *p,size_t n){const unsigned char*b=p;unsigned x=0;while(n--)x|=*b++;return x==0;}
#define REQUIRE(x) do{++checks;if(!(x)){printf("REVIEW CTS3 FAIL line=%u checks=%u record=%u direction=%u\n",__LINE__,checks,index,d);return 1;}}while(0)
#define RUN(m,k,v,n,a,b) (d?s24_cts3_decrypt(m,k,v,n,a,b):s24_cts3_encrypt(m,k,v,n,a,b))
int main(int argc,char **argv)
{
 int wrong=argc==2&&!strcmp(argv[1],"--wrong-expected");
 for(unsigned index=0;index<PROBE_RECORDS;++index)for(unsigned d=0;d<2;++d){
  const struct probe_record *r=probe_records+index;
  struct ccmode_cbc m,wrapped;cccbc_ctx_decl(768,key);cccbc_iv_decl(16,iv);
  unsigned char out[274],input[274],snapshot[768],saved_iv[16],wanted[272];
  const unsigned char *plain=d?r->ct:r->pt,*expected=d?r->pt:r->ct;
  REQUIRE(cts3_fixture_mode(&m,r->algorithm,d)==0&&m.block_size==r->block&&m.size<=768);
  memset(key,0x5a,768);REQUIRE(m.init(&m,key,r->keybytes,r->key)==0);memcpy(snapshot,key,768);
  memset(iv,0x77,16);memcpy(iv,r->iv,r->block);memset(out,0xa5,sizeof(out));
  memcpy(wanted,expected,r->bytes);if(wrong&&index==0&&!d)wanted[0]^=1;
  REQUIRE(RUN(&m,key,iv,r->bytes,plain,out+1)==r->bytes);
  REQUIRE(!memcmp(out+1,wanted,r->bytes)&&out[0]==0xa5&&out[r->bytes+1]==0xa5);
  REQUIRE(!memcmp(iv,r->next,r->block)&&!memcmp(key,snapshot,768));
  memset(iv,0x77,16);memcpy(iv,r->iv,r->block);memcpy(input+1,plain,r->bytes);
  REQUIRE(RUN(&m,key,iv,r->bytes,input+1,input+1)==r->bytes&&!memcmp(input+1,expected,r->bytes));
  REQUIRE(!memcmp(iv,r->next,r->block)&&!memcmp(key,snapshot,768));
  size_t prefix=((r->bytes-1)/r->block-1)*r->block;
  if(prefix){
   memcpy(iv,r->iv,r->block);memset(out,0xa5,sizeof(out));
   REQUIRE(m.cbc(key,iv,prefix/r->block,plain,out+1)==0);
   REQUIRE(RUN(&m,key,iv,r->bytes-prefix,plain+prefix,out+1+prefix)==r->bytes-prefix);
   REQUIRE(!memcmp(out+1,expected,r->bytes)&&!memcmp(iv,r->next,r->block));
  }
  /* Every admitted invocation fails AFTER real CBC has written output and IV. */
  backend=m;wrapped=m;wrapped.cbc=postwrite_error;
  unsigned stages=(prefix?1:0)+(d?2:1);
  for(unsigned stage=1;stage<=stages;++stage)for(unsigned inplace=0;inplace<2;++inplace){
   calls=0;fail_at=stage;memset(out,0xa5,sizeof(out));memcpy(input+1,plain,r->bytes);
   if(inplace)memcpy(out+1,plain,r->bytes);
   memset(iv,0x77,16);memcpy(iv,r->iv,r->block);memcpy(saved_iv,iv,16);
   REQUIRE(RUN(&wrapped,key,iv,r->bytes,inplace?out+1:input+1,out+1)==0);
   REQUIRE(calls==stage&&zeros(out+1,r->bytes)&&out[0]==0xa5&&out[r->bytes+1]==0xa5);
   REQUIRE(!memcmp(iv,saved_iv,16)&&!memcmp(key,snapshot,768));
   REQUIRE(!memcmp(input+1,plain,r->bytes));
  }
  /* Admission must not call even a correctly typed real backend wrapper. */
  calls=0;fail_at=0;memset(out,0xa5,sizeof(out));memset(iv,0x77,16);memcpy(saved_iv,iv,16);
  for(size_t n=0;n<=r->block;++n)REQUIRE(RUN(&wrapped,key,iv,n,plain,out+1)==0);
  REQUIRE(calls==0&&!memcmp(iv,saved_iv,16)&&!memcmp(key,snapshot,768));
  for(unsigned i=0;i<sizeof(out);++i)REQUIRE(out[i]==0xa5);
  REQUIRE(RUN(&wrapped,key,iv,r->bytes,input,input+1)==0&&calls==0);
  REQUIRE(RUN(&wrapped,key,iv,SIZE_MAX,input,out)==0&&calls==0);
  REQUIRE(RUN(&wrapped,key,iv,r->bytes,key,out)==0&&calls==0);
  REQUIRE(RUN(&wrapped,key,iv,r->bytes,input,iv)==0&&calls==0);
  struct ccmode_cbc malformed=wrapped;malformed.block_size=0;
  REQUIRE(RUN(&malformed,key,iv,r->bytes,input,out)==0&&calls==0);
  malformed=wrapped;malformed.size=SIZE_MAX;
  REQUIRE(RUN(&malformed,key,iv,r->bytes,input,out)==0&&calls==0);
  REQUIRE(cts3_fixture_clear(&m,key)==0&&zeros(key,m.size));
 }
 printf("REVIEW CTS3 PASS records=%u checks=%u post-real-CBC-error=all-stages\n",PROBE_RECORDS,checks);
 return 0;
}
