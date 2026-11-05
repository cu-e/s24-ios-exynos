/* Owned boundary tests run unchanged on real sanitized host and ARM CPU. */
#include "gcm_internal.h"
#include <corecrypto/ccmode.h>
#include <string.h>
#include "vectors.h"
static unsigned checks;
static int failure;
#define CHECK(x) do {++checks;if(!(x)){failure=__LINE__;return 0;}} while(0)
#define B(o) (s24_gcm_vector_bytes+(o))
static int equal(const void *a,const void *b,size_t n){return memcmp(a,b,n)==0;}
static unsigned char out[VECTOR_MAX+32],tag[32];
static struct ccmode_gcm en,de;
static int message(const struct vector *v,unsigned decrypt,unsigned inplace,unsigned step)
{
 ccgcm_ctx_decl(S24_GCM_CONTEXT_CAPACITY,ctx);memset(ctx,0,S24_GCM_CONTEXT_CAPACITY);
 const struct ccmode_gcm *m=decrypt?&de:&en;const unsigned char *input=B(decrypt?v->ct:v->pt),*wanted=B(decrypt?v->pt:v->ct);
 unsigned managed=v->ivn==12 && step==17;
 if(managed){CHECK(s24_gcm_init_with_iv(m,ctx,v->kb,B(v->key),B(v->iv))==0);}
 else {CHECK(m->init(m,ctx,v->kb,B(v->key))==0);CHECK(m->set_iv(ctx,v->ivn,B(v->iv))==0);}
 unsigned split=step?v->an/2:v->an;
 CHECK(m->gmac(ctx,split,B(v->aad))==0);CHECK(m->gmac(ctx,v->an-split,B(v->aad)+split)==0);
 memset(out,0xa5,sizeof(out));if(inplace)memcpy(out,input,v->n);
 for(unsigned pos=0;pos<v->n;){unsigned n=step?step:v->n;if(n>v->n-pos)n=v->n-pos;
  CHECK(m->gcm(ctx,n,inplace?out+pos:input+pos,out+pos)==0);
  /* Compare before finalize: no deferred text, including arbitrary partial bytes. */
  CHECK(equal(out+pos,wanted+pos,n));pos+=n;
 }
 CHECK(m->gcm(ctx,0,NULL,NULL)==0);CHECK(out[v->n]==0xa5);
 memset(tag,0xa5,sizeof(tag));if(decrypt)memcpy(tag,B(v->tag),v->tn);
 int result=m->finalize(ctx,v->tn,tag);
 CHECK(result==(decrypt&&v->bad?CCERR_INTEGRITY:0));CHECK(equal(tag,B(v->computed),v->tn));CHECK(tag[v->tn]==0xa5);
 CHECK(m->gcm(ctx,0,NULL,NULL)==CCERR_CALL_SEQUENCE);CHECK(m->finalize(ctx,v->tn,tag)==CCERR_CALL_SEQUENCE);
 CHECK(m->reset(ctx)==0);
 if(managed){unsigned char next[12],expected[12];memcpy(expected,B(v->iv),12);unsigned carry=1;for(unsigned i=12;i>4;i--){unsigned x=expected[i-1]+carry;expected[i-1]=(unsigned char)x;carry=x>>8;}CHECK(s24_gcm_inc_iv(m,ctx,next)==(carry?CCERR_OVERFLOW:0));if(!carry)CHECK(equal(next,expected,12));}
 else CHECK(m->set_iv(ctx,v->ivn,B(v->iv))==0);
 s24_gcm_clear(ctx);for(size_t i=0;i<m->size;i++)CHECK(((unsigned char*)ctx)[i]==0);
 return 1;
}
static int all_splits(const struct vector *v)
{
 ccgcm_ctx_decl(S24_GCM_CONTEXT_CAPACITY,ctx);
 for(unsigned decrypt=0;decrypt<2;decrypt++)for(unsigned inplace=0;inplace<2;inplace++)for(unsigned split=0;split<=v->n;split++){
  const struct ccmode_gcm *m=decrypt?&de:&en;memset(ctx,0,S24_GCM_CONTEXT_CAPACITY);
  CHECK(m->init(m,ctx,v->kb,B(v->key))==0);CHECK(m->set_iv(ctx,v->ivn,B(v->iv))==0);CHECK(m->gmac(ctx,v->an,B(v->aad))==0);
  const unsigned char *input=B(decrypt?v->ct:v->pt),*wanted=B(decrypt?v->pt:v->ct);memset(out,0xa5,sizeof(out));if(inplace)memcpy(out,input,v->n);
  CHECK(m->gcm(ctx,split,inplace?out:input,out)==0);CHECK(equal(out,wanted,split));
  CHECK(m->gcm(ctx,v->n-split,inplace?out+split:input+split,out+split)==0);CHECK(equal(out,wanted,v->n));
  memcpy(tag,B(v->computed),v->tn);CHECK(m->finalize(ctx,v->tn,tag)==0);CHECK(equal(tag,B(v->computed),v->tn));s24_gcm_clear(ctx);
 }
 /* Every AAD split, independently of text split, including AAD tail padding. */
 for(unsigned split=0;split<=v->an;split++){
  memset(ctx,0,S24_GCM_CONTEXT_CAPACITY);CHECK(en.init(&en,ctx,v->kb,B(v->key))==0);CHECK(en.set_iv(ctx,v->ivn,B(v->iv))==0);
  CHECK(en.gmac(ctx,split,B(v->aad))==0);CHECK(en.gmac(ctx,v->an-split,B(v->aad)+split)==0);CHECK(en.gcm(ctx,v->n,B(v->pt),out)==0);
  CHECK(equal(out,B(v->ct),v->n));CHECK(en.finalize(ctx,v->tn,tag)==0);CHECK(equal(tag,B(v->computed),v->tn));s24_gcm_clear(ctx);
 }
 return 1;
}
static int unchanged(const unsigned char *before,ccgcm_ctx *ctx){return equal(before,ctx,en.size);}
static int boundaries(void)
{
 ccgcm_ctx_decl(S24_GCM_CONTEXT_CAPACITY,ctx);ccgcm_ctx_decl(S24_GCM_CONTEXT_CAPACITY,copy);
 unsigned char before[S24_GCM_CONTEXT_CAPACITY],key[32]={0},iv[12]={1,2,3,4},buf[64]={0},saved[64];
 memset(ctx,0,S24_GCM_CONTEXT_CAPACITY);CHECK(en.reset(ctx)==CCERR_CALL_SEQUENCE);
 memcpy(before,ctx,en.size);CHECK(en.init(&en,ctx,15,key)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.init(&en,ctx,16,key)==0);memcpy(before,ctx,en.size);
 CHECK(en.gcm(ctx,1,buf,out)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(en.set_iv(ctx,0,iv)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.set_iv(ctx,12,iv)==0);memcpy(before,ctx,en.size);
 CHECK(en.set_iv(ctx,12,iv)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(en.finalize(ctx,3,tag)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.finalize(ctx,17,tag)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.finalize(ctx,16,ctx)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.gmac(ctx,1,NULL)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.gcm(ctx,1,NULL,out)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 memcpy(saved,buf,sizeof(buf));CHECK(en.gcm(ctx,16,buf,buf+1)==CCERR_PARAMETER);CHECK(equal(saved,buf,sizeof(buf)));CHECK(unchanged(before,ctx));
 CHECK(en.gcm(ctx,16,ctx,out)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.gcm(ctx,16,buf,ctx)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.gcm(ctx,0,NULL,NULL)==0);CHECK(unchanged(before,ctx));CHECK(en.gmac(ctx,0,NULL)==0);CHECK(unchanged(before,ctx));
 memcpy(copy,ctx,en.size);CHECK(en.reset(copy)==CCERR_CALL_SEQUENCE);CHECK(equal(before,copy,en.size));
 CHECK(en.gcm(ctx,1,buf,out)==0);memcpy(before,ctx,en.size);CHECK(en.gmac(ctx,0,NULL)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(en.finalize(ctx,16,tag)==0);memcpy(before,ctx,en.size);CHECK(en.gcm(ctx,1,buf,out)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(en.reset(ctx)==0);CHECK(s24_gcm_inc_iv(&en,ctx,iv)==CCERR_CALL_SEQUENCE);
 /* Real declared limits admitted before touching caller input. Owned white-box state
  * sets counters consistently; this is a boundary test, not a long-run claim. */
 CHECK(en.set_iv(ctx,12,iv)==0);struct s24_gcm_state s;memcpy(&s,ctx,sizeof(s));
 s.text_bytes=CCGCM_TEXT_MAX_NBYTES;s.active.MBEDTLS_PRIVATE(len)=s.text_bytes;memcpy(ctx,&s,sizeof(s));memcpy(before,ctx,en.size);
 memset(out,0xa5,sizeof(out));CHECK(en.gcm(ctx,1,buf,out)==CCERR_PARAMETER);CHECK(out[0]==0xa5);CHECK(unchanged(before,ctx));
 s.text_bytes=0;s.active.MBEDTLS_PRIVATE(len)=0;s.aad_bytes=UINT64_MAX/8;s.active.MBEDTLS_PRIVATE(add_len)=s.aad_bytes;memcpy(ctx,&s,sizeof(s));memcpy(before,ctx,en.size);
 CHECK(en.gmac(ctx,1,buf)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));s24_gcm_clear(ctx);
 /* Managed salt4/counter8; initial IV consumed, reset reserves rather than reuses. */
 CHECK(s24_gcm_init_with_iv(&en,ctx,16,key,iv)==0);memcpy(before,ctx,en.size);
 CHECK(en.init(&en,ctx,16,key)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(s24_gcm_init_with_iv(&en,ctx,16,key,iv)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(en.reset(ctx)==0);CHECK(en.reset(ctx)==0);memcpy(before,ctx,en.size);memset(buf,0xa5,sizeof(buf));
 CHECK(s24_gcm_inc_iv(&de,ctx,buf)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));CHECK(buf[0]==0xa5);
 CHECK(s24_gcm_inc_iv(&en,ctx,ctx)==CCERR_PARAMETER);CHECK(unchanged(before,ctx));
 CHECK(en.set_iv(ctx,12,iv)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));
 CHECK(s24_gcm_inc_iv(&en,ctx,buf)==0);CHECK(equal(buf,iv,11)&&buf[11]==1&&buf[12]==0xa5);
 CHECK(s24_gcm_inc_iv(&en,ctx,buf)==CCERR_CALL_SEQUENCE);CHECK(en.reset(ctx)==0);CHECK(en.reset(ctx)==0);CHECK(s24_gcm_inc_iv(&en,ctx,buf)==0);CHECK(buf[11]==2);
 CHECK(en.reset(ctx)==0);memcpy(&s,ctx,sizeof(s));memset(s.nonce+4,0xff,8);s.nonce[4]=0;memcpy(ctx,&s,sizeof(s));
 CHECK(s24_gcm_inc_iv(&en,ctx,buf)==0);CHECK(equal(buf,iv,4)&&buf[4]==1);for(unsigned i=5;i<12;i++)CHECK(buf[i]==0);
 CHECK(en.reset(ctx)==0);memcpy(&s,ctx,sizeof(s));memset(s.nonce+4,0xff,8);memcpy(ctx,&s,sizeof(s));memcpy(before,ctx,en.size);memset(buf,0xa5,sizeof(buf));
 CHECK(s24_gcm_inc_iv(&en,ctx,buf)==CCERR_OVERFLOW);CHECK(unchanged(before,ctx));CHECK(buf[0]==0xa5);
 CHECK(en.reset(ctx)==0);CHECK(s24_gcm_inc_iv(&en,ctx,buf)==CCERR_OVERFLOW);s24_gcm_clear(ctx);
 /* Authentication mismatch overwrites computed tag and irreversibly finalizes. */
 CHECK(s24_gcm_init_with_iv(&en,ctx,16,key,iv)==0);CHECK(en.finalize(ctx,16,tag)==0);memcpy(saved,tag,16);s24_gcm_clear(ctx);
 CHECK(s24_gcm_init_with_iv(&de,ctx,16,key,iv)==0);CHECK(de.finalize(ctx,16,tag)==0);CHECK(equal(tag,saved,16));s24_gcm_clear(ctx);
 for(unsigned i=0;i<16;i++){
  CHECK(s24_gcm_init_with_iv(&de,ctx,16,key,iv)==0);memcpy(tag,saved,16);tag[i]^=1;
  CHECK(de.finalize(ctx,16,tag)==CCERR_INTEGRITY);CHECK(equal(tag,saved,16));memcpy(before,ctx,en.size);
  CHECK(de.finalize(ctx,16,tag)==CCERR_CALL_SEQUENCE);CHECK(unchanged(before,ctx));CHECK(de.reset(ctx)==0);CHECK(s24_gcm_inc_iv(&de,ctx,buf)==0);s24_gcm_clear(ctx);
 }
 memset(&s,0,sizeof(s));memset(before,0,sizeof(before));memset(key,0,sizeof(key));return 1;
}
unsigned s24_gcm_suite_checks(void){return checks;}
int s24_gcm_suite(void)
{
 checks=0;failure=0;if(s24_gcm_descriptor(&en,0)||s24_gcm_descriptor(&de,1))return __LINE__;
 for(unsigned i=0;i<VECTOR_COUNT;i++)for(unsigned d=0;d<2;d++)for(unsigned inplace=0;inplace<2;inplace++)if(!message(&vectors[i],d,inplace,(i%3)?1:17))return failure;
 /* Extra oracle corpus covers all requested byte boundary sizes and key widths. */
 for(unsigned i=VECTOR_COUNT-45;i<VECTOR_COUNT;i++)if(!all_splits(&vectors[i]))return failure;
 if(!boundaries())return failure;return 0;
}
#ifdef GCM_PROBE_HOST
#include <stdio.h>
int main(void){int result=s24_gcm_suite();printf("GCM HOST %s vectors=%u checks=%u failure_line=%d\n",result?"FAIL":"PASS",VECTOR_COUNT,checks,result);return result?1:0;}
#endif
