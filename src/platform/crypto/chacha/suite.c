/* Expected cryptographic bytes come from primary RFC + independent EVP oracle.
 * Owned-state injection below tests arithmetic guards, not algorithm correctness. */
#include "internal.h"
#include <corecrypto/cc_error.h>
#include <string.h>
#include "vectors.h"
#ifdef CHACHA_HOST
#include <stdio.h>
#define CALL(method,...) s24_chacha_##method(__VA_ARGS__)
#else
#include "functions.h"
#define CALL(method,...) s24_chacha20poly1305_experimental_functions()->method(__VA_ARGS__)
#endif
#define CHECK(test) do { ++checks; if (!(test)) { *count=checks;return __LINE__; } } while (0)
#define REJECT(expression,error) do { memcpy(&before,&ctx,sizeof(ctx)); \
    CHECK((expression)==(error));CHECK(!memcmp(&before,&ctx,sizeof(ctx))); } while (0)
static unsigned char output[VECTOR_MAX+2],scratch[VECTOR_MAX+2];
static int equal(const void *a,const void *b,size_t n) { return !memcmp(a,b,n); }
int chacha_suite(unsigned *count)
{
    unsigned checks=0;const struct ccchacha20poly1305_info *info=CALL(info);
    ccchacha20poly1305_ctx ctx,before;
    unsigned char tag[16],bad[16],nonce[12],one=1;
    CHECK(info!=0);CHECK(!S24_CHACHA_COMPLETE_TABLE_QUALIFIED);
    for(unsigned v=0;v<VECTOR_COUNT;v++) {
        const struct vector *r=&vectors[v];const unsigned char *key=vector_blob+r->key;
        const unsigned char *iv=vector_blob+r->nonce,*aad=vector_blob+r->aad;
        const unsigned char *pt=vector_blob+r->pt,*ct=vector_blob+r->ct;
        const unsigned cuts[]={1,15,16,17,63,64,65,VECTOR_MAX};
        for(unsigned mode=0;mode<sizeof(cuts)/sizeof(cuts[0]);mode++) {
            size_t step=cuts[mode];memset(output,0xa7,sizeof(output));
            CHECK(CALL(init,info,&ctx,key)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,0,0)==0);
            for(size_t n=0;n<r->aad_bytes;) {
                size_t take=r->aad_bytes-n;if(take>step)take=step;
                CHECK(CALL(aad,info,&ctx,take,aad+n)==0);n+=take;
            }
            CHECK(CALL(encrypt,info,&ctx,0,0,0)==0);
            for(size_t n=0;n<r->text_bytes;) {
                size_t take=r->text_bytes-n;if(take>step)take=step;
                CHECK(CALL(encrypt,info,&ctx,take,pt+n,output+1+n)==0);
                CHECK(equal(output+1+n,ct+n,take));n+=take;
            }
            CHECK(CALL(finalize,info,&ctx,tag)==0);CHECK(equal(tag,vector_blob+r->tag,16));
            CHECK(output[0]==0xa7 && output[1+r->text_bytes]==0xa7);
            REJECT(CALL(finalize,info,&ctx,tag),CCERR_CALL_SEQUENCE);
            /* Reset retains the key; decrypt exact ciphertext in place. */
            CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,r->aad_bytes,aad)==0);
            memcpy(output+1,ct,r->text_bytes);
            CHECK(CALL(decrypt,info,&ctx,0,0,0)==0);
            for(size_t n=0;n<r->text_bytes;) {
                size_t take=r->text_bytes-n;if(take>step)take=step;
                CHECK(CALL(decrypt,info,&ctx,take,output+1+n,output+1+n)==0);
                CHECK(equal(output+1+n,pt+n,take));n+=take;
            }
            CHECK(CALL(verify,info,&ctx,tag)==0);CHECK(equal(output+1,pt,r->text_bytes));
            CHECK(output[0]==0xa7 && output[1+r->text_bytes]==0xa7);
            REJECT(CALL(verify,info,&ctx,tag),CCERR_CALL_SEQUENCE);
            /* Encrypt in place, decrypt disjoint: both API buffer forms. */
            CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,r->aad_bytes,aad)==0);memcpy(output,pt,r->text_bytes);
            CHECK(CALL(encrypt,info,&ctx,r->text_bytes,output,output)==0);
            CHECK(CALL(finalize,info,&ctx,tag)==0);CHECK(equal(output,ct,r->text_bytes));
            CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,r->aad_bytes,aad)==0);
            CHECK(CALL(decrypt,info,&ctx,r->text_bytes,ct,scratch)==0);
            CHECK(CALL(verify,info,&ctx,tag)==0);CHECK(equal(scratch,pt,r->text_bytes));
        }
        /* Every tag byte is relevant. Decrypt already emitted unverified
         * plaintext: callers MUST quarantine it until verify succeeds. */
        for(unsigned i=0;i<16;i++) {
            memcpy(bad,vector_blob+r->tag,16);bad[i]^=1;
            CHECK(CALL(init,info,&ctx,key)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,r->aad_bytes,aad)==0);
            CHECK(CALL(decrypt,info,&ctx,r->text_bytes,ct,output)==0);
            CHECK(CALL(verify,info,&ctx,bad)==CCERR_INTEGRITY);
            CHECK(equal(output,pt,r->text_bytes)); /* NOT authenticated */
            REJECT(CALL(verify,info,&ctx,vector_blob+r->tag),CCERR_CALL_SEQUENCE);
            memset(output,0,sizeof(output)); /* fixture explicitly discards it */
        }
        if(r->text_bytes) {
            memcpy(scratch,ct,r->text_bytes);scratch[r->text_bytes/2]^=1;
            CHECK(CALL(init,info,&ctx,key)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,r->aad_bytes,aad)==0);
            CHECK(CALL(decrypt,info,&ctx,r->text_bytes,scratch,output)==0);
            CHECK(CALL(verify,info,&ctx,vector_blob+r->tag)==CCERR_INTEGRITY);
        }
        if(r->aad_bytes) {
            memcpy(scratch,aad,r->aad_bytes);scratch[0]^=1;
            CHECK(CALL(init,info,&ctx,key)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
            CHECK(CALL(aad,info,&ctx,r->aad_bytes,scratch)==0);
            CHECK(CALL(decrypt,info,&ctx,r->text_bytes,ct,output)==0);
            CHECK(CALL(verify,info,&ctx,vector_blob+r->tag)==CCERR_INTEGRITY);
        }
    }
    const unsigned char *key=vector_blob+vectors[0].key,*iv=vector_blob+vectors[0].nonce;
    memset(&ctx,0,sizeof(ctx));
    REJECT(CALL(reset,info,&ctx),CCERR_CALL_SEQUENCE);
    REJECT(CALL(init,info,&ctx,0),CCERR_PARAMETER);
    REJECT(CALL(init,0,&ctx,key),CCERR_PARAMETER);
    REJECT(CALL(init,info,&ctx,(const uint8_t *)&ctx),CCERR_PARAMETER);
    CHECK(CALL(init,info,&ctx,key)==0);
    REJECT(CALL(aad,info,&ctx,0,0),CCERR_CALL_SEQUENCE);
    REJECT(CALL(encrypt,info,&ctx,1,&one,output),CCERR_CALL_SEQUENCE);
    REJECT(CALL(finalize,info,&ctx,tag),CCERR_CALL_SEQUENCE);
    REJECT(CALL(setnonce,info,&ctx,0),CCERR_PARAMETER);
    REJECT(CALL(setnonce,info,&ctx,(const uint8_t *)&ctx),CCERR_PARAMETER);
    CHECK(CALL(setnonce,info,&ctx,iv)==0);
    REJECT(CALL(setnonce,info,&ctx,iv),CCERR_CALL_SEQUENCE);
    REJECT(CALL(aad,info,&ctx,1,0),CCERR_PARAMETER);
    REJECT(CALL(aad,info,&ctx,1,&ctx),CCERR_PARAMETER);
    REJECT(CALL(aad,info,&ctx,2,(const void *)(UINTPTR_MAX-1)),CCERR_PARAMETER);
    REJECT(CALL(encrypt,info,&ctx,1,0,output),CCERR_PARAMETER);
    REJECT(CALL(encrypt,info,&ctx,1,&one,0),CCERR_PARAMETER);
    REJECT(CALL(encrypt,info,&ctx,1,&ctx,output),CCERR_PARAMETER);
    REJECT(CALL(encrypt,info,&ctx,1,&one,&ctx),CCERR_PARAMETER);
    memset(output,0xb4,sizeof(output));
    REJECT(CALL(encrypt,info,&ctx,16,output,output+1),CCERR_PARAMETER);
    CHECK(output[0]==0xb4 && output[16]==0xb4);
    REJECT(CALL(finalize,info,&ctx,0),CCERR_PARAMETER);
    REJECT(CALL(verify,info,&ctx,0),CCERR_PARAMETER);
    CHECK(CALL(encrypt,info,&ctx,1,&one,output)==0);
    REJECT(CALL(aad,info,&ctx,0,0),CCERR_CALL_SEQUENCE);
    REJECT(CALL(decrypt,info,&ctx,0,0,0),CCERR_CALL_SEQUENCE);
    REJECT(CALL(verify,info,&ctx,tag),CCERR_CALL_SEQUENCE);
    CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
    CHECK(CALL(decrypt,info,&ctx,0,0,0)==0);
    REJECT(CALL(encrypt,info,&ctx,0,0,0),CCERR_CALL_SEQUENCE);
    REJECT(CALL(finalize,info,&ctx,tag),CCERR_CALL_SEQUENCE);
    /* Explicitly incomplete nonce method: rejection is NOT increment or
     * exhaustion qualification. Neither nonce bytes nor state may change. */
    memcpy(nonce,iv,12);REJECT(CALL(incnonce,info,&ctx,nonce),CCERR_NOT_SUPPORTED);
    CHECK(equal(nonce,iv,12));
    /* Bounded state injection exercises limits without allocating256GiB. */
    struct s24_chacha_state state;
    CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
    memcpy(&state,&ctx,sizeof(state));state.aad_bytes=UINT64_MAX;
    memcpy(&ctx,&state,sizeof(state));REJECT(CALL(aad,info,&ctx,1,&one),CCERR_OVERFLOW);
    CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
    memcpy(&state,&ctx,sizeof(state));state.text_bytes=CCCHACHA20POLY1305_TEXT_MAX_NBYTES;
    memcpy(&ctx,&state,sizeof(state));output[0]=0xb8;
    REJECT(CALL(encrypt,info,&ctx,1,&one,output),CCERR_OVERFLOW);CHECK(output[0]==0xb8);
    CHECK(CALL(reset,info,&ctx)==0);CHECK(CALL(setnonce,info,&ctx,iv)==0);
    memcpy(&state,&ctx,sizeof(state));state.chacha.MBEDTLS_PRIVATE(state)[12]=UINT32_MAX;
    state.chacha.MBEDTLS_PRIVATE(keystream_bytes_used)=64;memcpy(&ctx,&state,sizeof(state));
    REJECT(CALL(encrypt,info,&ctx,65,scratch,output),CCERR_OVERFLOW);
    CHECK(output[0]==0xb8);
    CHECK(CALL(init,info,&ctx,key)==0);memcpy(&state,&ctx,sizeof(state));
    state.poly.MBEDTLS_PRIVATE(queue_len)=17;memcpy(&ctx,&state,sizeof(state));
    REJECT(CALL(reset,info,&ctx),CCERR_CALL_SEQUENCE);
    s24_chacha20poly1305_clear(&ctx);
    for(size_t i=0;i<sizeof(ctx);i++)CHECK(((const unsigned char *)&ctx)[i]==0);
    CHECK(CALL(init,info,0,key)==CCERR_PARAMETER);
    /* Deliberately invalid aligned-storage pointer, rejected before access. */
    _Alignas(8) unsigned char unaligned[sizeof(ctx)+8];memset(unaligned,0x8e,sizeof(unaligned));
    CHECK(CALL(init,info,(ccchacha20poly1305_ctx *)(void *)(unaligned+1),key)==CCERR_PARAMETER);
    for(size_t i=0;i<sizeof(unaligned);i++)CHECK(unaligned[i]==0x8e);
    *count=checks;return 0;
}
#ifdef CHACHA_HOST
int main(void) { unsigned count;int result=chacha_suite(&count);
    printf("CHACHA HOST %s vectors=%u checks=%u failure_line=%d incnonce=UNQUALIFIED\n",
           result?"FAIL":"PASS",VECTOR_COUNT,count,result);return result?1:0; }
#endif
