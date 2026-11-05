/* Project-owned CBC-CS3 composition from NIST SP800-38A Addendum section4
 * and RFC3962 section5; no restricted Apple implementation or XTS substitution.
 * CBC primitive, key expansion and caller state ownership are external. */
#include "cts3.h"
#include <stdint.h>
#include <string.h>
/* Sole implementation is supplied by accepted XTS, never duplicated here. */
extern void mbedtls_platform_zeroize(void *,size_t);
const unsigned long long s24_cts3_layout[]={sizeof(struct ccmode_cbc),sizeof(cccbc_ctx),_Alignof(cccbc_ctx),sizeof(cccbc_iv),_Alignof(cccbc_iv),CCMODE_MAX_BLOCK_SIZE};
static int extent(const void *p,size_t n) {return p && (uintptr_t)p<=UINTPTR_MAX-n;}
static int overlap(const void*a,size_t an,const void*b,size_t bn)
{return an && bn && (uintptr_t)a<(uintptr_t)b+bn && (uintptr_t)b<(uintptr_t)a+an;}
static int aligned(const void*p,size_t alignment) {return p && !((uintptr_t)p%alignment);}
static int admit(const struct ccmode_cbc*m,cccbc_ctx*ctx,cccbc_iv*iv,size_t n,const void*in,void*out)
{
 if(!aligned(m,_Alignof(struct ccmode_cbc))||!extent(m,sizeof(*m)))return 0;
 size_t b=m->block_size,z=m->size;
 if(!b||b>CCMODE_MAX_BLOCK_SIZE||!z||!m->init||!m->cbc||n<=b)return 0;
 if(!aligned(ctx,_Alignof(cccbc_ctx))||!extent(ctx,z)||!aligned(iv,_Alignof(cccbc_iv))||!extent(iv,b)||!extent(in,n)||!extent(out,n))return 0;
 if(in!=out && overlap(in,n,out,n))return 0;
 if(overlap(ctx,z,m,sizeof(*m))||overlap(ctx,z,iv,b)||overlap(ctx,z,in,n)||overlap(ctx,z,out,n))return 0;
 if(overlap(m,sizeof(*m),iv,b)||overlap(m,sizeof(*m),in,n)||overlap(m,sizeof(*m),out,n))return 0;
 if(overlap(iv,b,in,n)||overlap(iv,b,out,n))return 0;
 return 1;
}
static size_t crypt(const struct ccmode_cbc*m,cccbc_ctx*ctx,cccbc_iv*iv,size_t n,const void*in,void*out,int decrypt)
{
 if(!admit(m,ctx,iv,n,in,out))return 0;
 const size_t b=m->block_size,prefix_blocks=(n-1)/b-1,prefix=prefix_blocks*b,d=n-prefix-b;
 const unsigned char *input=in;unsigned char *output=out;
 _Alignas(16) unsigned char tail[2*CCMODE_MAX_BLOCK_SIZE],work[2*CCMODE_MAX_BLOCK_SIZE];
 cccbc_iv_decl(CCMODE_MAX_BLOCK_SIZE,chain);cccbc_iv_decl(CCMODE_MAX_BLOCK_SIZE,zero);
 size_t result=0;
 memset(tail,0,sizeof(tail));memset(work,0,sizeof(work));memset(chain,0,sizeof(chain));memset(zero,0,sizeof(zero));
 memcpy(chain,iv,b);memcpy(tail,input+prefix,b+d);
 if(prefix_blocks && m->cbc(ctx,chain,prefix_blocks,input,output))goto failed;
 if(!decrypt) {
  /* Ordinary CBC on final full block and zero-padded partial block. */
  if(m->cbc(ctx,chain,2,tail,work))goto failed;
  /* CS3 always swaps, including d==b (a complete last block). */
  memcpy(output+prefix,work+b,b);memcpy(output+prefix+b,work,d);
 } else {
  /* CBC with zero IV yields D(Y), where Y is the last ordinary CBC block.
   * Its unexposed suffix recovers the missing suffix of the stolen block X. */
  if(m->cbc(ctx,zero,1,tail,work))goto failed;
  memcpy(work+b,tail+b,d);memcpy(work+b+d,work+d,b-d);
  for(size_t i=0;i<d;++i)work[i]^=tail[b+i];
  /* work[0..d) is final plaintext; decrypt reconstructed X against prior IV. */
  if(m->cbc(ctx,chain,1,work+b,tail+b))goto failed;
  memcpy(output+prefix,tail+b,b);memcpy(output+prefix+b,work,d);
  /* RFC3962 carries Y, not the final partial/swapped output block. */
  memcpy(chain,tail,b);
 }
 memcpy(iv,chain,b);result=n;goto done;
failed:
 /* Explicit failure contract, not a promise to roll back prior in-place input. */
 mbedtls_platform_zeroize(output,n);
done:
 mbedtls_platform_zeroize(tail,sizeof(tail));mbedtls_platform_zeroize(work,sizeof(work));
 mbedtls_platform_zeroize(chain,sizeof(chain));mbedtls_platform_zeroize(zero,sizeof(zero));return result;
}
size_t s24_cts3_encrypt(const struct ccmode_cbc*m,cccbc_ctx*c,cccbc_iv*v,size_t n,const void*a,void*b)
{return crypt(m,c,v,n,a,b,0);}
size_t s24_cts3_decrypt(const struct ccmode_cbc*m,cccbc_ctx*c,cccbc_iv*v,size_t n,const void*a,void*b)
{return crypt(m,c,v,n,a,b,1);}
