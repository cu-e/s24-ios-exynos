/* Owned representation/lifetime glue. Real arithmetic and PKCS#1 unpadding:
 * BearSSL7bea48e5e850ab4cafbe68d3765cdaba13a86d6f, MIT;see vendor/LICENSE.txt.
 * No Apple implementation or replacement ABI records are copied here. */
#include "rsa.h"
#include <bearssl_rsa.h>
#include <mbedtls/platform_util.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define KEY_UNITS ccn_nof(RSA_MAX_KEY_BITSIZE)
_Static_assert(CCN_UNIT_SIZE==8 && KEY_UNITS==64,"selected ARM64 number profile");
_Static_assert(sizeof(rsa_pub_ctx)==1584 && _Alignof(rsa_pub_ctx)==8,"actual selected container");
const unsigned long long s24_rsa_layout[8]={sizeof(rsa_pub_ctx),_Alignof(rsa_pub_ctx),
    KEY_UNITS,CCN_UNIT_SIZE,sizeof(struct ccrsa_pub_ctx),sizeof(struct cczp),
    ccrsa_pub_ctx_size(S24_RSA_MAX_BYTES),offsetof(struct ccrsa_pub_ctx,pb_ccn)};

static int extent(const void *p,size_t bytes){return p && (uintptr_t)p<=UINTPTR_MAX-bytes;}
static int intersects(const void *a,size_t an,const void *b,size_t bn){
    return an && bn && (uintptr_t)a<(uintptr_t)b+bn && (uintptr_t)b<(uintptr_t)a+an;
}
static int context_extent(ccrsa_pub_ctx_t key){
    return extent(key,sizeof(rsa_pub_ctx)) && !((uintptr_t)key&(_Alignof(rsa_pub_ctx)-1));
}
static void decode_number(cc_unit *out,const uint8_t *in,size_t bytes){
    for(size_t i=0;i<bytes;++i)out[i/CCN_UNIT_SIZE]|=(cc_unit)in[bytes-1-i]<<((i%CCN_UNIT_SIZE)*8);
}
static size_t bit_length(const cc_unit *number){
    for(size_t i=KEY_UNITS;i>0;--i)
        if(number[i-1])return (i-1)*CCN_UNIT_BITS+64-(size_t)__builtin_clzll(number[i-1]);
    return 0;
}
static int less_than(const cc_unit *a,const cc_unit *b){
    for(size_t i=KEY_UNITS;i>0;--i)if(a[i-1]!=b[i-1])return a[i-1]<b[i-1];
    return 0;
}
static int numbers_valid(ccrsa_pub_ctx_t key){
    /* The n field is admitted before any macro-derived number offsets. */
    if(ccrsa_ctx_n(key)!=KEY_UNITS)return 0;
    const cc_unit *m=ccrsa_ctx_m(key),*e=ccrsa_ctx_e(key);
    size_t bits=bit_length(m),ebits=bit_length(e);
    return bits>=3 && bits<=RSA_MAX_KEY_BITSIZE && key->pb_bitlen==bits &&
        (m[0]&1) && (e[0]&1) && ebits>=2 && less_than(e,m);
}
int s24_rsa_make_pub(ccrsa_pub_ctx_t destination,size_t exp_bytes,const uint8_t *exp,
    size_t mod_bytes,const uint8_t *mod){
    rsa_pub_ctx staged;int status=CCERR_PARAMETER;
    if(!context_extent(destination) || ccrsa_ctx_n(destination)!=KEY_UNITS)return status;
    if(!exp_bytes || exp_bytes>S24_RSA_MAX_BYTES || !mod_bytes || mod_bytes>S24_RSA_MAX_BYTES ||
       !extent(exp,exp_bytes) || !extent(mod,mod_bytes) ||
       intersects(destination,sizeof(staged),exp,exp_bytes) ||
       intersects(destination,sizeof(staged),mod,mod_bytes))return status;
    memset(&staged,0,sizeof(staged));ccrsa_ctx_n(staged.key)=KEY_UNITS;
    decode_number(ccrsa_ctx_m(staged.key),mod,mod_bytes);
    decode_number(ccrsa_ctx_e(staged.key),exp,exp_bytes);
    staged.key->pb_bitlen=bit_length(ccrsa_ctx_m(staged.key));
    /* funcs and Montgomery regions stay zero and are explicitly unqualified.
     * This selected pair never invokes opaque cczp operations. */
    if(numbers_valid(staged.key)){
        memcpy(destination,&staged,sizeof(staged));status=CCERR_OK;
    }
    mbedtls_platform_zeroize(&staged,sizeof(staged));return status;
}
static size_t encode_number(uint8_t out[S24_RSA_MAX_BYTES],const cc_unit *number){
    size_t bytes=(bit_length(number)+7)/8;
    for(size_t i=0;i<bytes;++i)out[bytes-1-i]=(uint8_t)(number[i/CCN_UNIT_SIZE]>>((i%CCN_UNIT_SIZE)*8));
    return bytes;
}
static int oid_convert(const uint8_t *der,uint8_t out[S24_RSA_OID_PAYLOAD_MAX+1]){
    if(!der)return 1; /* Genuine NULL-OID raw-digest mode. */
    size_t len=der[1];
    if(der[0]!=0x06 || !len || len>S24_RSA_OID_PAYLOAD_MAX)return 0;
    if(der[len+1]&0x80)return 0; /* Unterminated base128 subidentifier. */
    for(size_t i=0;i<len;++i)
        if((i==0 || !(der[i+1]&0x80)) && der[i+2]==0x80)return 0;
    out[0]=(uint8_t)len;memcpy(out+1,der+2,len);return 1;
}
int s24_rsa_verify_pkcs1v15(ccrsa_pub_ctx_t key,const uint8_t *oid,size_t digest_len,
    const uint8_t *digest,size_t sig_len,const uint8_t *signature,bool *valid){
    /* Admission prevents a validity write from changing caller input storage.
     * Accessibility is a caller premise; pointer-range arithmetic is bounded. */
    size_t oid_bytes=0;
    if(!extent(valid,sizeof(*valid)))return CCERR_PARAMETER;
    if(key && (!context_extent(key) || intersects(valid,sizeof(*valid),key,sizeof(rsa_pub_ctx))))return CCERR_PARAMETER;
    if((digest && !extent(digest,digest_len)) || (signature && !extent(signature,sig_len)))return CCERR_PARAMETER;
    if(digest && intersects(valid,sizeof(*valid),digest,digest_len))return CCERR_PARAMETER;
    if(signature && intersects(valid,sizeof(*valid),signature,sig_len))return CCERR_PARAMETER;
    if(oid){
        if(!extent(oid,2))return CCERR_PARAMETER;
        oid_bytes=(size_t)oid[1]+2;
        if(!extent(oid,oid_bytes) || intersects(valid,sizeof(*valid),oid,oid_bytes))return CCERR_PARAMETER;
    }
    *valid=false;
    if(!key || !numbers_valid(key) || !digest || !signature ||
       !digest_len || digest_len>S24_RSA_DIGEST_MAX || !sig_len || sig_len>S24_RSA_MAX_BYTES)return CCERR_PARAMETER;
    struct {
        uint8_t modulus[S24_RSA_MAX_BYTES],exponent[S24_RSA_MAX_BYTES];
        uint8_t oid[S24_RSA_OID_PAYLOAD_MAX+1],recovered[S24_RSA_DIGEST_MAX];
    } work;
    int status=CCERR_PARAMETER;memset(&work,0,sizeof(work));
    if(!oid_convert(oid,work.oid))goto done;
    br_rsa_public_key public_view={0};
    public_view.n=work.modulus;public_view.nlen=encode_number(work.modulus,ccrsa_ctx_m(key));
    public_view.e=work.exponent;public_view.elen=encode_number(work.exponent,ccrsa_ctx_e(key));
    status=CCERR_OK;
    if(sig_len!=public_view.nlen)goto done;
    if(br_rsa_i31_pkcs1_vrfy(signature,sig_len,oid?work.oid:NULL,digest_len,&public_view,work.recovered)){
        uint8_t different=0;
        for(size_t i=0;i<digest_len;++i)different|=work.recovered[i]^digest[i];
        *valid=different==0;
    }
done:
    mbedtls_platform_zeroize(&work,sizeof(work));return status;
}
