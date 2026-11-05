/* Independent installed OpenSSL oracle: genuine public C headers and opaque EVP
 * contexts; no handcrafted OSSL_PARAM/foreign key schedule representations.
 * This test-only native library is never linked into production or ARM payload. */
#include <openssl/evp.h>
#include <openssl/provider.h>
#include <openssl/params.h>
#include <openssl/core_names.h>
#include <limits.h>
#include <stddef.h>
static OSSL_PROVIDER *provider_default,*provider_legacy;
int cts3_oracle_init(void)
{
 provider_default=OSSL_PROVIDER_load(NULL,"default");provider_legacy=OSSL_PROVIDER_load(NULL,"legacy");
 return provider_default&&provider_legacy;
}
void cts3_oracle_finish(void)
{if(provider_legacy)OSSL_PROVIDER_unload(provider_legacy);if(provider_default)OSSL_PROVIDER_unload(provider_default);provider_legacy=provider_default=NULL;}
const char *cts3_oracle_version(void){return OpenSSL_version(0);}
int cts3_oracle_encrypt(const char *algorithm,int cs3,const unsigned char *key,size_t key_bytes,
 const unsigned char *iv,size_t block,const unsigned char *in,size_t n,unsigned char *out,unsigned char *next_iv)
{
 if(!algorithm||!key||!iv||!in||!out||!next_iv||!n||n>INT_MAX||block>INT_MAX||key_bytes>INT_MAX)return 0;
 EVP_CIPHER *cipher=EVP_CIPHER_fetch(NULL,algorithm,NULL);EVP_CIPHER_CTX *ctx=EVP_CIPHER_CTX_new();int result=0,first=0,last=0;
 OSSL_PARAM params[2];char mode[]="CS3";
 params[0]=OSSL_PARAM_construct_utf8_string(OSSL_CIPHER_PARAM_CTS_MODE,mode,0);params[1]=OSSL_PARAM_construct_end();
 if(!cipher||!ctx||EVP_CIPHER_get_key_length(cipher)!=(int)key_bytes||EVP_CIPHER_get_iv_length(cipher)!=(int)block)goto done;
 if(!EVP_EncryptInit_ex2(ctx,cipher,key,iv,cs3?params:NULL)||!EVP_CIPHER_CTX_set_padding(ctx,0))goto done;
 if(!EVP_EncryptUpdate(ctx,out,&first,in,(int)n)||!EVP_EncryptFinal_ex(ctx,out+first,&last))goto done;
 if(first<0||last<0||(size_t)first+(size_t)last!=n||!EVP_CIPHER_CTX_get_updated_iv(ctx,next_iv,block))goto done;
 result=1;
done:EVP_CIPHER_CTX_free(ctx);EVP_CIPHER_free(cipher);return result;
}
