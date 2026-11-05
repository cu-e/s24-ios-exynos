/* Public vector/ABI/lifetime tests. Actual selected caller is compiled apart. */
#include "rsa.h"
#include "typed.h"
#include <libkern/crypto/crypto_internal.h>
#include <mbedtls/platform_util.h>
#include <stdint.h>
#include <string.h>
#include "vectors.h"
#ifdef RSA_HOST
#include <stdio.h>
#endif
static ccrsa_make_pub_fn_t s24_rsa_constructor_callback;
static ccrsa_verify_pkcs1v15_fn_t s24_rsa_verifier_callback;
/* Genuine table type, two-slot synthetic dispatch only. Never registered. */
static struct crypto_functions pair;
crypto_functions_t g_crypto_funcs;
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x))return __LINE__;}while(0)
static const struct rsa_vector *positive(void){
    for(unsigned i=0;i<RSA_VECTOR_COUNT;++i)if(rsa_vectors[i].valid)return &rsa_vectors[i];
    return 0;
}
static int vectors(void){
    for(unsigned i=0;i<RSA_VECTOR_COUNT;++i){
        const struct rsa_vector *v=&rsa_vectors[i];rsa_pub_ctx key;bool valid=true;
        CHECK(v->n_off<=RSA_VECTOR_BYTES-v->n_len && v->e_off<=RSA_VECTOR_BYTES-v->e_len);
        CHECK(v->sig_off<=RSA_VECTOR_BYTES-v->sig_len && v->hash_off<=RSA_VECTOR_BYTES-v->hash_len);
        const uint8_t *oid=v->oid_len?vector_bytes+v->oid_off:NULL;
        memset(&key,0xa5,sizeof(key));ccrsa_ctx_n(key.key)=64;
        CHECK(s24_rsa_constructor_callback(key.key,v->e_len,vector_bytes+v->e_off,v->n_len,vector_bytes+v->n_off)==CCERR_OK);
        CHECK(ccrsa_ctx_n(key.key)==64 && key.key->pb_funcs==NULL);
        CHECK(s24_rsa_verifier_callback(key.key,oid,v->hash_len,vector_bytes+v->hash_off,v->sig_len,vector_bytes+v->sig_off,&valid)==CCERR_OK);
        CHECK(valid==!!v->valid);
        mbedtls_platform_zeroize(&key,sizeof(key));
        const uint8_t *bytes=(const uint8_t *)&key;
        for(size_t at=0;at<sizeof(key);++at)CHECK(bytes[at]==0);
    }
    return 0;
}
static int lifetime_and_caller(void){
    const struct rsa_vector *v=positive();CHECK(v!=NULL);
    uint8_t modulus[512],exponent[512];rsa_pub_ctx key,snapshot;bool valid;
    memset(modulus,0,sizeof(modulus));memset(exponent,0,sizeof(exponent));
    memcpy(modulus+512-v->n_len,vector_bytes+v->n_off,v->n_len);
    memcpy(exponent+512-v->e_len,vector_bytes+v->e_off,v->e_len);
    memset(&key,0,sizeof(key));
    /* Actual unchanged wrapper prewrites n itself and dispatches real slots. */
    CHECK(rsa_make_pub(&key,512,exponent,512,modulus)==CCERR_OK);
    CHECK(ccrsa_ctx_n(key.key)==64);
    cc_unit low=0;for(unsigned i=0;i<8;++i)low|=(cc_unit)modulus[511-i]<<(i*8);
    CHECK(ccrsa_ctx_m(key.key)[0]==low);
    mbedtls_platform_zeroize(modulus,sizeof(modulus));mbedtls_platform_zeroize(exponent,sizeof(exponent));
    memcpy(&snapshot,&key,sizeof(key));
    valid=false;CHECK(rsa_verify_pkcs1v15(&key,vector_bytes+v->oid_off,v->hash_len,vector_bytes+v->hash_off,v->sig_len,vector_bytes+v->sig_off,&valid)==CCERR_OK && valid);
    CHECK(memcmp(&snapshot,&key,sizeof(key))==0);
    for(unsigned i=0;i<v->n_len;++i)modulus[i]=vector_bytes[v->n_off+v->n_len-1-i];
    ccrsa_ctx_n(key.key)=64;
    CHECK(s24_rsa_constructor_callback(key.key,v->e_len,vector_bytes+v->e_off,v->n_len,modulus)==CCERR_OK);
    valid=true;CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,v->hash_len,vector_bytes+v->hash_off,v->sig_len,vector_bytes+v->sig_off,&valid)==CCERR_OK && !valid);
    memcpy(&key,&snapshot,sizeof(key));
    uint8_t wrong_hash[64];memcpy(wrong_hash,vector_bytes+v->hash_off,v->hash_len);wrong_hash[0]^=1;
    valid=true;CHECK(rsa_verify_pkcs1v15(&key,vector_bytes+v->oid_off,v->hash_len,wrong_hash,v->sig_len,vector_bytes+v->sig_off,&valid)==CCERR_OK && !valid);
    CHECK(memcmp(&snapshot,&key,sizeof(key))==0);
    /* The wrapper's own oversize rejection precedes its n prewrite. */
    CHECK(rsa_make_pub(&key,513,exponent,512,modulus)==-1 && memcmp(&snapshot,&key,sizeof(key))==0);
    return 0;
}
static int constructor_errors(void){
    const struct rsa_vector *v=positive();rsa_pub_ctx key,before;uint8_t n[513],e[513];
    for(unsigned test=0;test<14;++test){
        memset(&key,0x55,sizeof(key));ccrsa_ctx_n(key.key)=64;
        size_t nl=v->n_len,el=v->e_len;memcpy(n,vector_bytes+v->n_off,nl);memcpy(e,vector_bytes+v->e_off,el);
        const uint8_t *np=n,*ep=e;
        switch(test){
        case 0:ccrsa_ctx_n(key.key)=0;break;
        case 1:ccrsa_ctx_n(key.key)=63;break;
        case 2:ccrsa_ctx_n(key.key)=65;break;
        case 3:ccrsa_ctx_n(key.key)=SIZE_MAX;break;
        case 4:nl=0;break;
        case 5:el=0;break;
        case 6:nl=513;break;
        case 7:el=513;break;
        case 8:memset(n,0,nl);break;
        case 9:n[nl-1]&=0xfe;break;
        case 10:memset(e,0,el);e[el-1]=1;break;
        case 11:memset(e,0,el);e[el-1]=2;break;
        case 12:el=nl;memcpy(e,n,nl);break;
        default:ep=(const uint8_t *)&key;el=3;break;
        }
        memcpy(&before,&key,sizeof(key));
        CHECK(s24_rsa_constructor_callback(key.key,el,ep,nl,np)==CCERR_PARAMETER);
        CHECK(memcmp(&key,&before,sizeof(key))==0);
    }
    CHECK(s24_rsa_constructor_callback(NULL,3,e,v->n_len,n)==CCERR_PARAMETER);
    unsigned char unaligned[sizeof(key)+1];memset(unaligned,0xa5,sizeof(unaligned));
    CHECK(s24_rsa_constructor_callback((void *)(unaligned+1),3,e,v->n_len,n)==CCERR_PARAMETER);
    for(size_t i=0;i<sizeof(unaligned);++i)CHECK(unaligned[i]==0xa5);
    return 0;
}
static int verifier_errors(void){
    const struct rsa_vector *v=positive();rsa_pub_ctx key,before;bool valid;
    uint8_t hash[65],signature[513],oid[35];
    memcpy(hash,vector_bytes+v->hash_off,v->hash_len);memcpy(signature,vector_bytes+v->sig_off,v->sig_len);
    ccrsa_ctx_n(key.key)=64;CHECK(s24_rsa_constructor_callback(key.key,v->e_len,vector_bytes+v->e_off,v->n_len,vector_bytes+v->n_off)==CCERR_OK);
    memcpy(&before,&key,sizeof(key));
    for(unsigned test=0;test<17;++test){
        memcpy(&key,&before,sizeof(key));memset(oid,0,sizeof(oid));memcpy(oid,vector_bytes+v->oid_off,v->oid_len);
        const uint8_t *hp=hash,*sp=signature;size_t hl=v->hash_len,sl=v->sig_len;
        switch(test){
        case 0:ccrsa_ctx_n(key.key)=0;break;
        case 1:ccrsa_ctx_n(key.key)=65;break;
        case 2:key.key->pb_bitlen=0;break;
        case 3:ccrsa_ctx_e(key.key)[0]=1;break;
        case 4:hl=0;break;
        case 5:hl=65;break;
        case 6:sl=0;break;
        case 7:sl=513;break;
        case 8:hp=NULL;break;
        case 9:sp=NULL;break;
        case 10:oid[0]=0x30;break;
        case 11:oid[1]=0;break;
        case 12:oid[1]=33;break;
        case 13:oid[1]=0x81;break;
        case 14:oid[2]=0x80;break;
        case 15:oid[oid[1]+1]|=0x80;break;
        default:oid[3]=0x80;oid[2]&=0x7f;break;
        }
        rsa_pub_ctx attempt;memcpy(&attempt,&key,sizeof(key));valid=true;
        CHECK(s24_rsa_verifier_callback(key.key,oid,hl,hp,sl,sp,&valid)==CCERR_PARAMETER && !valid);
        CHECK(memcmp(&attempt,&key,sizeof(key))==0);
    }
    memcpy(&key,&before,sizeof(key));
    /* Wrong OID is a cryptographic mismatch, not successful validity. */
    memcpy(oid,vector_bytes+v->oid_off,v->oid_len);oid[v->oid_len-1]^=1;valid=true;
    CHECK(s24_rsa_verifier_callback(key.key,oid,v->hash_len,hash,v->sig_len,signature,&valid)==CCERR_OK && !valid);
    valid=true;CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,v->hash_len,hash,v->sig_len-1,signature,&valid)==CCERR_OK && !valid);
    /* Signature integer == modulus is rejected, and signature bytes unchanged. */
    memcpy(signature,vector_bytes+v->n_off,v->n_len);valid=true;
    CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,v->hash_len,hash,v->n_len,signature,&valid)==CCERR_OK && !valid);
    CHECK(memcmp(signature,vector_bytes+v->n_off,v->n_len)==0);
    memcpy(signature,vector_bytes+v->sig_off,v->sig_len);
    CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,v->hash_len,hash,v->sig_len,signature,(void *)&key)==CCERR_PARAMETER);
    CHECK(memcmp(&key,&before,sizeof(key))==0);
    unsigned char snap[513];memcpy(snap,signature,v->sig_len);
    CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,v->hash_len,hash,v->sig_len,signature,(void *)signature)==CCERR_PARAMETER);
    CHECK(memcmp(snap,signature,v->sig_len)==0);
    uint8_t hash_snapshot[64];memcpy(hash_snapshot,hash,v->hash_len);
    CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,v->hash_len,hash,v->sig_len,signature,(void *)hash)==CCERR_PARAMETER);
    CHECK(memcmp(hash_snapshot,hash,v->hash_len)==0);
    memcpy(oid,vector_bytes+v->oid_off,v->oid_len);uint8_t oid_snapshot[35];memcpy(oid_snapshot,oid,v->oid_len);
    CHECK(s24_rsa_verifier_callback(key.key,oid,v->hash_len,hash,v->sig_len,signature,(void *)oid)==CCERR_PARAMETER);
    CHECK(memcmp(oid_snapshot,oid,v->oid_len)==0);
    valid=true;CHECK(s24_rsa_verifier_callback(key.key,vector_bytes+v->oid_off,SIZE_MAX,hash,v->sig_len,signature,&valid)==CCERR_PARAMETER && valid);
    valid=true;CHECK(s24_rsa_verifier_callback(NULL,vector_bytes+v->oid_off,v->hash_len,hash,v->sig_len,signature,&valid)==CCERR_PARAMETER && !valid);
    return 0;
}
int rsa_suite(unsigned *count){
    checks=0;
    int result=s24_rsa_callbacks(&s24_rsa_constructor_callback,&s24_rsa_verifier_callback);
    if(result)return __LINE__;
    pair.ccrsa_make_pub_fn=s24_rsa_constructor_callback;pair.ccrsa_verify_pkcs1v15_fn=s24_rsa_verifier_callback;g_crypto_funcs=&pair;
    result=vectors();if(!result)result=lifetime_and_caller();
    if(!result)result=constructor_errors();if(!result)result=verifier_errors();
    *count=checks;return result;
}
#ifdef RSA_HOST
int main(void){unsigned count;int result=rsa_suite(&count);printf("RSA HOST %s vectors=%u checks=%u failure_line=%d\n",result?"FAIL":"PASS",RSA_VECTOR_COUNT,count,result);return result?1:0;}
#endif
