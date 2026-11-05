/* Same real adapter/vector suite is linked on sanitized host and ARM CPU. */
#include "xts.h"
#include <corecrypto/ccmode.h>
#include "vectors.h"
#include <stdint.h>
#include <string.h>
#ifdef XTS_HOST
#include <stdio.h>
#include <stdlib.h>
#endif
static unsigned checks;
static int failure;
#define CHECK(x) do { ++checks; if (!(x)) { failure=__LINE__; goto done; } } while(0)
static int zero(const void *p,size_t n) { const unsigned char *b=p;unsigned v=0;while(n--)v|=*b++;return !v; }
static int run_vector(const struct vector *v)
{
    struct ccmode_xts enc,dec;
    ccxts_ctx_decl(1072,key); /* Actual selected opaque declaration/alignment. */
    ccxts_tweak_decl(64,tweak);
    unsigned char out[VECTOR_MAX],back[VECTOR_MAX],saved[1072];
    const unsigned char *raw=vector_bytes+v->key,*iv=vector_bytes+v->iv,*pt=vector_bytes+v->pt,*ct=vector_bytes+v->ct;
    size_t blocks=v->bytes/16;
    CHECK(s24_xts_descriptor(&enc,0)==0 && s24_xts_descriptor(&dec,1)==0);
    CHECK(enc.size<=1072 && enc.tweak_size<=64 && enc.block_size==16);
    for(unsigned decrypt=0;decrypt<2;++decrypt) {
        const struct ccmode_xts *m=decrypt?&dec:&enc;
        const unsigned char *input=decrypt?ct:pt,*expected=decrypt?pt:ct;
        CHECK(m->init(m,key,v->n,raw,raw+v->n)==0);
        memcpy(saved,key,enc.size);
        CHECK(m->set_tweak(key,tweak,iv)==0);
        CHECK(m->xts(key,tweak,blocks,input,out)==tweak);
        CHECK(!memcmp(out,expected,v->bytes) && !memcmp(saved,key,enc.size));
        CHECK(m->set_tweak(key,tweak,iv)==0);
        memcpy(back,input,v->bytes);
        CHECK(m->xts(key,tweak,blocks,back,back)==tweak && !memcmp(back,expected,v->bytes));
        /* Real continuation at every split for short units; representative long splits. */
        for(size_t split=1;split<blocks;split+=(blocks>32?17:1)) {
            CHECK(m->set_tweak(key,tweak,iv)==0);
            CHECK(m->xts(key,tweak,split,input,out)==tweak);
            CHECK(m->xts(key,tweak,0,NULL,NULL)==tweak);
            CHECK(m->xts(key,tweak,blocks-split,input+16*split,out+16*split)==tweak);
            CHECK(!memcmp(out,expected,v->bytes));
        }
        s24_xts_clear_key(key);CHECK(zero(key,enc.size));
        m->key_sched(m,key,v->n,raw,raw+v->n);
        CHECK(m->set_tweak(key,tweak,iv)==0 && m->xts(key,tweak,blocks,input,out)==tweak && !memcmp(out,expected,v->bytes));
        m->key_sched(m,key,24,raw,raw+v->n);
        CHECK(zero(key,enc.size) && m->set_tweak(key,tweak,iv)!=0 && zero(tweak,enc.tweak_size));
    }
done:
    s24_xts_clear_key(key);s24_xts_clear_tweak(tweak);
    memset(saved,0,sizeof(saved));return !failure;
}
static int contracts(void)
{
    struct ccmode_xts m,wrong;
    ccxts_ctx_decl(1072,key);ccxts_ctx_decl(1072,other);
    ccxts_tweak_decl(64,t);ccxts_tweak_decl(64,snapshot);
    unsigned char k[64],iv[16]={0},buf[128],before[128];
    _Alignas(16) unsigned char unaligned[1100];
    for(unsigned i=0;i<64;++i)k[i]=(unsigned char)i;
    memset(buf,0xa5,sizeof(buf));memcpy(before,buf,sizeof(buf));
    memset(key,0,1072);memset(other,0,1072);memset(t,0,64);
    CHECK(s24_xts_descriptor(&m,0)==0 && s24_xts_descriptor(&wrong,1)==0);
    CHECK(s24_xts_descriptor(NULL,0)!=0 && s24_xts_descriptor(&wrong,2)!=0);
    CHECK(m.set_tweak(key,t,iv)!=0 && m.xts(key,t,1,buf,buf)==NULL);
    for(size_t n=0;n<65;++n)if(n!=16&&n!=32) {
        CHECK(m.init(&m,key,n,k,k+32)!=0 && zero(key,m.size));
    }
    CHECK(m.init(&m,key,16,k,k)!=0 && zero(key,m.size));
    CHECK(m.init(&m,key,16,NULL,k+32)!=0 && zero(key,m.size));
    CHECK(m.init(&m,key,16,k,k+32)==0);
    CHECK(m.xts(key,t,1,buf,buf)==NULL);
    CHECK(m.set_tweak(key,t,iv)==0);memcpy(snapshot,t,m.tweak_size);
    size_t bad[]={SIZE_MAX,SIZE_MAX/16+1,S24_XTS_MAX_BLOCKS+1};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);++i) {
        CHECK(m.xts(key,t,bad[i],buf,buf)==NULL && !memcmp(t,snapshot,m.tweak_size) && !memcmp(buf,before,sizeof(buf)));
    }
    CHECK(m.xts(key,t,2,buf,buf+1)==NULL && !memcmp(t,snapshot,m.tweak_size) && !memcmp(buf,before,sizeof(buf)));
    CHECK(m.xts(key,t,1,NULL,buf)==NULL && m.xts(key,t,1,buf,NULL)==NULL);
    CHECK(m.xts(key,t,1,(const void *)(UINTPTR_MAX-7),buf)==NULL);
    CHECK(m.xts(key,t,1,buf,(void *)(UINTPTR_MAX-7))==NULL);
    CHECK(m.xts(key,t,1,buf,t)==NULL && m.xts(key,t,1,key,buf)==NULL && m.xts(key,t,1,buf,key)==NULL);
    CHECK(m.init(&m,other,16,k,k+32)==0 && m.xts(other,t,1,buf,buf)==NULL);
    CHECK(wrong.xts(key,t,1,buf,buf)==NULL);
    CHECK(m.xts(key,t,0,NULL,NULL)==t && !memcmp(t,snapshot,m.tweak_size));
    CHECK(m.init(&m,key,16,k,k+32)==0 && m.xts(key,t,1,buf,buf)==NULL); /* stale tweak */
    CHECK(m.set_tweak(key,t,iv)==0);
    /* Genuine opaque storage corruption: magic and schedule round metadata. */
    memcpy(unaligned,key,m.size);unaligned[0]^=0xff;memcpy(key,unaligned,m.size);
    CHECK(m.xts(key,t,1,buf,buf)==NULL);
    CHECK(m.init(&m,key,16,k,k+32)==0 && m.set_tweak(key,t,iv)==0);
    CHECK(m.set_tweak(key,t,NULL)!=0 && zero(t,m.tweak_size));
    /* Real byte-backed misalignment admitted only as rejected foreign input. */
    CHECK(m.init(&m,(void *)(unaligned+1),16,k,k+32)!=0);
    CHECK(m.set_tweak(key,(void *)(unaligned+1),iv)!=0);
    CHECK(m.xts((const void *)(unaligned+1),t,1,buf,buf)==NULL);
    CHECK(m.init(&m,NULL,16,k,k+32)!=0);
    CHECK(m.init(NULL,key,16,k,k+32)!=0 && zero(key,m.size));
    CHECK(m.init(&m,key,16,(const void *)(UINTPTR_MAX-7),k+32)!=0 && zero(key,m.size));
    struct ccmode_xts bad_mode=m;bad_mode.size--;
    CHECK(m.init(&bad_mode,key,16,k,k+32)!=0 && zero(key,m.size));
    CHECK(m.init(&m,key,16,k,k+32)==0 && m.set_tweak(key,t,iv)==0);
    CHECK(m.xts(key,t,1,before,buf)==t);unsigned char expected[16];memcpy(expected,buf,16);
    CHECK(m.set_tweak(key,t,iv)==0);memset(k,0xff,sizeof(k));
    CHECK(m.xts(key,t,1,before,buf)==t && !memcmp(buf,expected,16)); /* schedules own both keys */
    for(unsigned i=0;i<64;++i)k[i]=(unsigned char)i;
    CHECK(m.set_tweak(key,t,(const void *)(UINTPTR_MAX-7))!=0 && zero(t,m.tweak_size));
    CHECK(m.set_tweak(key,t,iv)==0);memcpy(snapshot,t,m.tweak_size);
    unsigned char *tbytes=(void *)t;tbytes[0]^=1;
    CHECK(m.xts(key,t,1,before,buf)==NULL);memcpy(t,snapshot,m.tweak_size);
    CHECK(m.xts(key,t,1,before,buf)==t);
    CHECK(m.init(&m,key,16,key,k+32)!=0 && zero(key,m.size));
done:
    s24_xts_clear_key(key);s24_xts_clear_key(other);s24_xts_clear_tweak(t);s24_xts_clear_tweak(snapshot);
    return !failure;
}
#ifdef XTS_HOST
static int maximum_unit(void)
{
    struct ccmode_xts m;ccxts_ctx_decl(1072,key);ccxts_tweak_decl(64,t);
    unsigned char raw[32],iv[16]={0};size_t bytes=S24_XTS_MAX_BLOCKS*16;
    unsigned char *buf=malloc(bytes);if(!buf)return 0;
    memset(buf,0,bytes);for(unsigned i=0;i<32;++i)raw[i]=(unsigned char)i;
    CHECK(s24_xts_descriptor(&m,0)==0 && m.init(&m,key,16,raw,raw+16)==0 && m.set_tweak(key,t,iv)==0);
    CHECK(m.xts(key,t,S24_XTS_MAX_BLOCKS-1,buf,buf)==t);
    CHECK(m.xts(key,t,1,buf+bytes-16,buf+bytes-16)==t);
    unsigned char saved[64];memcpy(saved,t,m.tweak_size);
    CHECK(m.xts(key,t,1,buf,buf)==NULL && !memcmp(saved,t,m.tweak_size));
    CHECK(m.xts(key,t,0,NULL,NULL)==t);
done:s24_xts_clear_key(key);s24_xts_clear_tweak(t);free(buf);return !failure;
}
#endif
int xts_suite(unsigned *count)
{
    checks=0;failure=0;
    for(unsigned i=0;i<VECTOR_COUNT && !failure;++i)run_vector(&vectors[i]);
    if(!failure)contracts();
#ifdef XTS_HOST
    if(!failure)maximum_unit();
#endif
    *count=checks;return failure;
}
#ifdef XTS_HOST
int main(void) { unsigned count;int error=xts_suite(&count);printf("XTS HOST %s vectors=%u checks=%u failure_line=%d\n",error?"FAIL":"PASS",VECTOR_COUNT,count,error);return error?1:0; }
#endif
