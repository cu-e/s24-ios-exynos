#include "gcm.h"
#include <corecrypto/ccmode.h>
#include <string.h>
#ifdef GCM_PROBE_HOST
#include <stdio.h>
#endif
int s24_gcm_probe(void)
{
 struct ccmode_gcm enc,dec;ccgcm_ctx_decl(S24_GCM_CONTEXT_CAPACITY,ctx);
 unsigned char key[16]={0},iv[12]={0},tag[16]={0};
 const unsigned char expected[16]={0x58,0xe2,0xfc,0xce,0xfa,0x7e,0x30,0x61,0x36,0x7f,0x1d,0x57,0xa4,0xe7,0x45,0x5a};
 memset(ctx,0,S24_GCM_CONTEXT_CAPACITY);
 if(s24_gcm_descriptor(&enc,0)||s24_gcm_descriptor(&dec,1)||enc.size>S24_GCM_CONTEXT_CAPACITY||enc.size!=dec.size)return 1;
 if(enc.init(&enc,ctx,16,key)||enc.set_iv(ctx,12,iv)||enc.finalize(ctx,16,tag)||memcmp(tag,expected,16))return 2;
 s24_gcm_clear(ctx);memset(tag,0,sizeof(tag));
 if(s24_gcm_init_with_iv(&dec,ctx,16,key,iv)||dec.finalize(ctx,16,tag)!=CCERR_INTEGRITY||memcmp(tag,expected,16))return 3;
 if(dec.reset(ctx)||s24_gcm_inc_iv(&dec,ctx,iv)||iv[11]!=1)return 4;
 s24_gcm_clear(ctx);return 0;
}
#ifdef GCM_PROBE_HOST
int main(void){int n=s24_gcm_probe();printf("GCM PROBE %s failure=%d\n",n?"FAIL":"PASS",n);return n;}
#endif
