/* Independent public-boundary controls; genuine selected XNU declarations. */
#include "rsa.h"
#include "typed.h"
#include "review_cases.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define REQUIRE(x) do { ++checks; if (!(x)) { fprintf(stderr,"review failure line %d\n",__LINE__); return 1; } } while (0)
static int verify(const struct review_case *v,rsa_pub_ctx *key,bool *valid) {
    return s24_rsa_verify_pkcs1v15(key->key,v->oid_len?v->oid:NULL,v->hash_len,v->hash,v->sig_len,v->sig,valid);
}
int main(void) {
    ccrsa_make_pub_fn_t make=NULL; ccrsa_verify_pkcs1v15_fn_t check=NULL;
    REQUIRE(s24_rsa_callbacks(&make,&check)==CCERR_OK && make==s24_rsa_make_pub && check==s24_rsa_verify_pkcs1v15);
    REQUIRE(sizeof(rsa_pub_ctx)==1584 && _Alignof(rsa_pub_ctx)==8);
    unsigned positive=0;
    for (size_t i=0;i<sizeof(review_cases)/sizeof(review_cases[0]);++i) {
        const struct review_case *v=&review_cases[i];
        struct { uint64_t pre; rsa_pub_ctx key; uint64_t post; } guarded;
        rsa_pub_ctx snapshot; uint8_t n[512],e[512]; bool valid=true;
        guarded.pre=UINT64_C(0x2b34a9ff66112233);guarded.post=~guarded.pre;
        memset(&guarded.key,0xaa,sizeof(guarded.key));ccrsa_ctx_n(guarded.key.key)=64;
        memcpy(n,v->n,v->n_len);memcpy(e,v->e,v->e_len);
        REQUIRE(make(guarded.key.key,v->e_len,e,v->n_len,n)==CCERR_OK);
        memset(n,0,sizeof(n));memset(e,0,sizeof(e)); /* Lifetime independent of borrowed bytes. */
        memcpy(&snapshot,&guarded.key,sizeof(snapshot));
        REQUIRE(verify(v,&guarded.key,&valid)==v->status && valid==!!v->valid);
        REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
        REQUIRE(guarded.pre==UINT64_C(0x2b34a9ff66112233) && guarded.post==~guarded.pre);
        if (v->valid) {
            ++positive;
            struct review_case different=*v;different.hash[0]^=1;valid=true;
            REQUIRE(verify(&different,&guarded.key,&valid)==CCERR_OK && !valid);
            different=*v;different.sig_len--;valid=true;
            REQUIRE(verify(&different,&guarded.key,&valid)==CCERR_OK && !valid);
            /* A byte-for-byte retained public context remains self-contained. */
            memset(&guarded.key,0,sizeof(guarded.key));valid=false;
            REQUIRE(verify(v,&snapshot,&valid)==CCERR_OK && valid);
            memcpy(&guarded.key,&snapshot,sizeof(snapshot));
        }
        /* Callback failure preserves all previous key bytes. */
        REQUIRE(make(guarded.key.key,1,(const uint8_t[]){2},v->n_len,v->n)==CCERR_PARAMETER);
        REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
        REQUIRE(make(guarded.key.key,1,(void *)&guarded.key,v->n_len,v->n)==CCERR_PARAMETER);
        REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
        REQUIRE(make(guarded.key.key,1,(const uint8_t *)(uintptr_t)UINTPTR_MAX,v->n_len,v->n)==CCERR_PARAMETER);
        REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
        const size_t offsets[]={0,23,24,535,1055,1567,1583};
        for(size_t j=0;j<sizeof(offsets)/sizeof(offsets[0]);++j) {
            bool *alias=(void *)((unsigned char *)&guarded.key+offsets[j]);
            REQUIRE(check(guarded.key.key,v->oid_len?v->oid:NULL,v->hash_len,v->hash,v->sig_len,v->sig,alias)==CCERR_PARAMETER);
            REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
        }
        /* Wrong n must reject before computing a macro-derived exponent offset. */
        ccrsa_ctx_n(guarded.key.key)=SIZE_MAX; memcpy(&snapshot,&guarded.key,sizeof(snapshot)); valid=true;
        REQUIRE(verify(v,&guarded.key,&valid)==CCERR_PARAMETER && !valid);
        REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
        REQUIRE(make(guarded.key.key,v->e_len,v->e,v->n_len,v->n)==CCERR_PARAMETER);
        REQUIRE(memcmp(&snapshot,&guarded.key,sizeof(snapshot))==0);
    }
    /* Minimal accepted odd modulus/exponent is admissible but cannot hold a PKCS signature. */
    rsa_pub_ctx small,snapshot;bool valid=true;ccrsa_ctx_n(small.key)=64;
    REQUIRE(make(small.key,1,(const uint8_t[]){3},1,(const uint8_t[]){7})==CCERR_OK);
    memcpy(&snapshot,&small,sizeof(snapshot));
    REQUIRE(check(small.key,NULL,1,(const uint8_t[]){0},1,(const uint8_t[]){0},&valid)==CCERR_OK && !valid);
    REQUIRE(memcmp(&small,&snapshot,sizeof(snapshot))==0);
    valid=true;REQUIRE(check(small.key,NULL,SIZE_MAX,(const uint8_t *)1,1,(const uint8_t[]){0},&valid)==CCERR_PARAMETER && valid);
    valid=true;REQUIRE(check(NULL,NULL,1,(const uint8_t[]){0},1,(const uint8_t[]){0},&valid)==CCERR_PARAMETER && !valid);
    printf("{\"cases\":%zu,\"positive_cases\":%u,\"checks\":%u,\"QEMU_executed\":false,\"provider_registered\":false}\n",sizeof(review_cases)/sizeof(review_cases[0]),positive,checks);
    return 0;
}
