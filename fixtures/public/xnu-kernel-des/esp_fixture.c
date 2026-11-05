/* Owned focused services/accessor, appended to a fresh genuine selected ESP TU.
 * Genuine records only; bounded <=40-byte packets, no clusters/network model.
 * Unsupported service/extent/ownership requests fail-stop. Test fault injection
 * invalidates a real schedule; it never substitutes a crypto callback result.
 */
#include <mbedtls/platform_util.h>
extern __attribute__((noreturn)) void kdes_fixture_fail(unsigned);
#define FASSERT(x) do{if(!(x))kdes_fixture_fail(__LINE__);}while(0)
#define POOL 24
_Static_assert(MLEN>=44&&MHLEN>=44,"bounded genuine packet capacity");
const unsigned long long kdes_esp_record_layout[]={sizeof(struct mbuf),_Alignof(struct mbuf),sizeof(struct secasvar),_Alignof(struct secasvar),MLEN,MHLEN,__builtin_offsetof(struct mbuf,m_len),__builtin_offsetof(struct mbuf,m_data),__builtin_offsetof(struct secasvar,sched)};
static struct mbuf fixture_pool[POOL];
static unsigned used[POOL],freed[POOL],original[POOL],count,allocations,fail_alloc;
static unsigned scratch_live,fail_scratch,stirs,clear_calls,block_calls,fail_block;
static unsigned saw_split,saw_head_alias,saw_tail_alias,saw_distinct_tail,observed_iv,observed_scratch;
_Alignas(16) static unsigned char scratch[16];
static struct secasvar *active_sav;
static int fixture_triple;
struct kalloc_heap KHEAP_DATA_BUFFERS[1];
int ipsec_debug;
static unsigned index_of(struct mbuf *m)
{
 for(unsigned i=0;i<count;++i)if(m==&fixture_pool[i]){FASSERT(used[i]&&!freed[i]);return i;}
 kdes_fixture_fail(__LINE__);
}
static struct mbuf *node_alloc(int header,unsigned capacity,int orig)
{
 FASSERT(count<POOL);unsigned i=count++;struct mbuf *m=&fixture_pool[i];memset(m,0,sizeof(*m));
 used[i]=1;original[i]=(unsigned)orig;m->m_flags=header?M_PKTHDR:0;m->m_type=MT_DATA;
 FASSERT(capacity<=(unsigned)(header?MHLEN:MLEN));m->m_data=M_START(m)+M_SIZE(m)-capacity;
 FASSERT(((uintptr_t)m->m_data&3)==0);return m;
}
struct mbuf *m_get(int how,int type)
{
 FASSERT(how==M_DONTWAIT&&type==MT_DATA);if(++allocations==fail_alloc)return NULL;
 struct mbuf *m=node_alloc(0,8,0);for(unsigned i=0;i<count-1;++i)if(!freed[i]&&original[i])FASSERT(m!=&fixture_pool[i]);return m;
}
void *m_mtod(struct mbuf *m){(void)index_of(m);return m->m_data;}
struct mbuf *m_free(struct mbuf *m)
{unsigned i=index_of(m);struct mbuf *next=m->m_next;freed[i]++;FASSERT(freed[i]==1);m->m_next=NULL;return next;}
void m_freem(struct mbuf *m){unsigned traversed=0;while(m){FASSERT(++traversed<=POOL);m=m_free(m);}}
void m_copydata(struct mbuf *m,int off,int n,void *dst)
{
 FASSERT(off>=0&&n>=0);unsigned char *p=dst;unsigned nodes=0;
 while(m&&off>=m->m_len){(void)index_of(m);FASSERT(++nodes<=POOL);off-=m->m_len;m=m->m_next;}
 while(n){FASSERT(m);(void)index_of(m);int take=m->m_len-off;if(take>n)take=n;FASSERT(take>0);memcpy(p,m->m_data+off,(size_t)take);p+=take;n-=take;off=0;m=m->m_next;}
}
void m_copyback(struct mbuf *m,int off,int n,const void *src)
{
 FASSERT(off>=0&&n>=0);const unsigned char *p=src;unsigned nodes=0;
 while(m&&off>=m->m_len){(void)index_of(m);FASSERT(++nodes<=POOL);off-=m->m_len;m=m->m_next;}
 while(n){FASSERT(m);(void)index_of(m);int take=m->m_len-off;if(take>n)take=n;FASSERT(take>0);memcpy(m->m_data+off,p,(size_t)take);p+=take;n-=take;off=0;m=m->m_next;}
}
void m_adj(struct mbuf *m,int n){(void)m;(void)n;kdes_fixture_fail(__LINE__);}
struct mbuf *m_mclget(struct mbuf *m,int how){(void)m;(void)how;kdes_fixture_fail(__LINE__);}
int m_mclhasreference(struct mbuf *m){(void)m;kdes_fixture_fail(__LINE__);}
struct kalloc_result (kalloc_ext)(void *heap,vm_size_t n,zalloc_flags_t flags,void *site)
{
 (void)site;FASSERT(heap==KHEAP_DATA_BUFFERS&&n==8&&flags==Z_NOWAIT&&!scratch_live);
 if(fail_scratch)return (struct kalloc_result){NULL,0};
 scratch_live=1;memset(scratch,0xa5,sizeof(scratch));return (struct kalloc_result){scratch,sizeof(scratch)};
}
void kfree_ext(void *heap,void *p,vm_size_t n)
{
 FASSERT(heap==KHEAP_DATA_BUFFERS&&p==scratch&&n==8&&scratch_live);
 for(unsigned i=0;i<8;++i)FASSERT(scratch[i]==0);for(unsigned i=8;i<16;++i)FASSERT(scratch[i]==0xa5);
 scratch_live=0;observed_scratch++;
}
/* This observed fixture definition checks bytes/ownership only. Actual production
 * nonelision is proved separately from the unobserved native ESP object. */
void cc_clear(size_t n,void *p)
{
 FASSERT(n==8||n==16);mbedtls_platform_zeroize(p,n);clear_calls++;
 if(p==scratch){FASSERT(n==8&&scratch_live);observed_scratch++;}
 else {FASSERT(n==16);observed_iv++;}
}
/* Explicit synthetic deterministic IV-update service, not entropy or kernel key
 * management. Success paths must call once; all error paths must call zero times. */
void key_sa_stir_iv(struct secasvar *sav)
{FASSERT(sav==active_sav&&sav->iv&&sav->ivlen==8);stirs++;for(unsigned i=0;i<8;++i)sav->iv[i]^=(char)(0x51+i);}
int assfail(const char *s,const char *file,int line)
{(void)s;(void)file;(void)line;kdes_fixture_fail(__LINE__);}
/* Called from the owned instrumented copy immediately before a real block call. */
void kdes_before_block(struct secasvar *sav,struct mbuf *m,struct mbuf *scut,struct mbuf *d0,struct mbuf *d,unsigned char *sp,unsigned char *sbuf)
{
 FASSERT(sav==active_sav);block_calls++;saw_split|=sp==sbuf;saw_head_alias|=m==scut;saw_tail_alias|=d0==d;saw_distinct_tail|=d0!=d;
 FASSERT(original[index_of(m)]&&!original[index_of(d0)]&&!original[index_of(d)]);
 for(unsigned i=0;i<count;++i)if(original[i]&&!freed[i])for(unsigned j=0;j<count;++j)if(!original[j]&&!freed[j])FASSERT(&fixture_pool[i]!=&fixture_pool[j]);
 if(block_calls==fail_block)mbedtls_platform_zeroize(sav->sched,fixture_triple?sizeof(des3_ecb_key_schedule):sizeof(des_ecb_key_schedule));
}
static void reset_fixture(void)
{
 memset(fixture_pool,0,sizeof(fixture_pool));memset(used,0,sizeof(used));memset(freed,0,sizeof(freed));memset(original,0,sizeof(original));
 count=allocations=scratch_live=stirs=clear_calls=block_calls=saw_split=saw_head_alias=saw_tail_alias=saw_distinct_tail=observed_iv=observed_scratch=0;
}
/* Genuine algorithm records selecting the actual static block functions; unused
 * network startup/maturity/schedule services are not simulated by this fixture. */
static const struct esp_algorithm fixture_des={.padbound=8,.name="owned-selected-des",.blockencrypt=esp_des_blockencrypt,.blockdecrypt=esp_des_blockdecrypt};
static const struct esp_algorithm fixture_tdes={.padbound=8,.name="owned-selected-tdes",.blockencrypt=esp_3des_blockencrypt,.blockdecrypt=esp_3des_blockdecrypt};
/* A call is success, scratch allocation failure, output allocation N failure,
 * real algorithm failure at block N, or populated-IV validation failure. */
int kdes_esp_case(int triple,int decrypt,int fragmented,unsigned allocation_failure,unsigned scratch_failure,unsigned algorithm_failure,unsigned validation,const unsigned char *key,const unsigned char *iv,const unsigned char *input,const unsigned char *expected)
{
 des_ecb_key_schedule single;des3_ecb_key_schedule three;struct secasvar sav={0};unsigned char packet[40],out[40],saved_iv[8];des_cblock raw[3];
 reset_fixture();fail_alloc=allocation_failure;fail_scratch=scratch_failure;fail_block=algorithm_failure;fixture_triple=triple;
 memset(packet,0x39,16);memcpy(packet+8,iv,8);memcpy(packet+16,input,24);memcpy(saved_iv,iv,8);
 sav.iv=(caddr_t)saved_iv;sav.ivlen=8;sav.sched=triple?(void*)&three:(void*)&single;sav.schedlen=triple?sizeof(three):sizeof(single);active_sav=&sav;
 memcpy(raw,key,triple?24U:8U);FASSERT((triple?des3_ecb_key_sched(raw,&three):des_ecb_key_sched(raw,&single))==0);mbedtls_platform_zeroize(raw,sizeof(raw));
 struct mbuf *head=NULL,*tail=NULL;unsigned at=0;const unsigned lengths[4]={8,12,4,16};unsigned nodes=fragmented==1?4:1;
 for(unsigned i=0;i<nodes;++i){unsigned n=fragmented==1?lengths[i]:40;struct mbuf *m=node_alloc(i==0,n+(fragmented==2?4:0),1);if(fragmented==2)m->m_data++;m->m_len=(int)n;memcpy(m->m_data,packet+at,n);at+=n;if(tail)tail->m_next=m;else head=m;tail=m;}
 FASSERT(at==40);head->m_pkthdr.len=validation==1?15:validation==2?39:40;
 const struct esp_algorithm *algo=triple?&fixture_tdes:&fixture_des;
 int result=decrypt?esp_cbc_decrypt(head,0,&sav,algo,8):esp_cbc_encrypt(head,0,24,&sav,algo,8);
 int error=allocation_failure||scratch_failure||algorithm_failure||validation;
 if(error){FASSERT(result==(validation||algorithm_failure?EINVAL:ENOBUFS));for(unsigned i=0;i<count;++i)FASSERT(freed[i]==1);FASSERT(!stirs);}
 else {
  FASSERT(result==0);m_copydata(head,0,40,out);FASSERT(!memcmp(out,packet,16)&&!memcmp(out+16,expected,24));
  FASSERT(stirs==(unsigned)!decrypt);if(!decrypt)for(unsigned i=0;i<8;++i)FASSERT((unsigned char)saved_iv[i]==(unsigned char)(iv[i]^(0x51+i)));
  m_freem(head);for(unsigned i=0;i<count;++i)FASSERT(freed[i]==1);
 }
 FASSERT(!scratch_live);
#ifndef KDES_ORIGINAL_CALLER
 FASSERT(observed_iv==1&&clear_calls==(scratch_failure||validation?1U:2U));
 FASSERT(observed_scratch==(scratch_failure||validation?0U:2U));
#endif
 if(!error){FASSERT(block_calls==3);FASSERT(saw_head_alias==(unsigned)(fragmented!=1));FASSERT(saw_split==(unsigned)(fragmented!=0));FASSERT(saw_tail_alias&&saw_distinct_tail);}
 mbedtls_platform_zeroize(&single,sizeof(single));mbedtls_platform_zeroize(&three,sizeof(three));return 1;
}
