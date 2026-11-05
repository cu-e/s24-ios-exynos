/* Independently authored contracts using genuine selected opaque declarations. */
#include "xts.h"
#include <corecrypto/ccmode.h>
#include "testdata/vectors.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define CK(x) do { checks++; assert(x); } while(0)
static int zero(const void *p,size_t n)
{ const unsigned char *b=p;unsigned value=0;while(n--)value|=*b++;return value==0; }
static void vectors_direct(void)
{
    struct ccmode_xts modes[2];
    ccxts_ctx_decl(1072,key);ccxts_tweak_decl(64,tweak);
    unsigned char out[VECTOR_MAX],saved[1072];
    CK(s24_xts_descriptor(&modes[0],0)==0 && s24_xts_descriptor(&modes[1],1)==0);
    for(unsigned i=0;i<VECTOR_COUNT;i++) for(unsigned d=0;d<2;d++) {
        const struct vector *v=&vectors[i];const struct ccmode_xts *m=&modes[d];
        const unsigned char *raw=vector_bytes+v->key,*iv=vector_bytes+v->iv;
        const unsigned char *input=vector_bytes+(d?v->ct:v->pt),*expected=vector_bytes+(d?v->pt:v->ct);
        CK(m->init(m,key,v->n,raw,raw+v->n)==0);memcpy(saved,key,m->size);
        CK(m->set_tweak(key,tweak,iv)==0 && m->xts(key,tweak,v->bytes/16,input,out)==tweak);
        CK(!memcmp(out,expected,v->bytes) && !memcmp(saved,key,m->size));
        s24_xts_clear_key(key);s24_xts_clear_tweak(tweak);
        CK(zero(key,m->size) && zero(tweak,m->tweak_size));
    }
}
static void contracts(void)
{
    struct ccmode_xts m,dec;memset(&m,0,sizeof(m));memset(&dec,0,sizeof(dec));
    ccxts_ctx_decl(1072,key);ccxts_ctx_decl(1072,other);
    ccxts_tweak_decl(64,t);ccxts_tweak_decl(64,copy);
    unsigned char raw[64],iv[16]={0},state[1072],tw[64],buf[128],before[128],out[128];
    for(unsigned i=0;i<sizeof(raw);i++)raw[i]=(unsigned char)(i+1);
    CK(s24_xts_descriptor(&m,0)==0 && s24_xts_descriptor(&dec,1)==0);
    struct ccmode_xts saved=m;
    CK(s24_xts_descriptor(&m,-1)!=0 && !memcmp(&m,&saved,sizeof(m)));
    CK(s24_xts_descriptor(&m,2)!=0 && !memcmp(&m,&saved,sizeof(m)));
    CK(m.init(&m,key,16,raw,raw+32)==0 && m.set_tweak(key,t,iv)==0);
    memcpy(state,key,m.size);memcpy(tw,t,m.tweak_size);memset(out,0xa7,sizeof(out));
    /* Every byte-offset alias into key or tweak storage is rejected atomically. */
    const unsigned char *kb=(const void *)key,*tb=(const void *)t;
    for(size_t i=0;i+16<=m.size;i++) {
        CK(m.xts(key,t,1,kb+i,out)==NULL && !memcmp(out,(unsigned char[128]){[0 ... 127]=0xa7},sizeof(out)));
        CK(!memcmp(state,key,m.size) && !memcmp(tw,t,m.tweak_size));
        CK(m.xts(key,t,1,out,(unsigned char *)(void *)key+i)==NULL);
        CK(!memcmp(state,key,m.size) && !memcmp(tw,t,m.tweak_size));
    }
    for(size_t i=0;i+16<=m.tweak_size;i++) {
        CK(m.xts(key,t,1,tb+i,out)==NULL && !memcmp(tw,t,m.tweak_size));
        CK(m.xts(key,t,1,out,(unsigned char *)(void *)t+i)==NULL && !memcmp(tw,t,m.tweak_size));
    }
    for(int delta=-31;delta<=31;delta++)if(delta) {
        for(unsigned i=0;i<sizeof(buf);i++)buf[i]=(unsigned char)i;
        memcpy(before,buf,sizeof(buf));
        CK(m.xts(key,t,2,buf+32,buf+32+delta)==NULL);
        CK(!memcmp(buf,before,sizeof(buf)) && !memcmp(tw,t,m.tweak_size) && !memcmp(state,key,m.size));
    }
    for(unsigned i=0;i<sizeof(buf);i++)buf[i]=(unsigned char)(3*i);
    CK(m.xts(key,t,2,buf,buf+32)==t); /* Exact adjacent ranges are disjoint. */
    CK(m.set_tweak(key,t,iv)==0 && m.xts(key,t,2,buf,buf)==t);
    CK(m.set_tweak(key,t,iv)==0);memcpy(tw,t,m.tweak_size);
    size_t bad[]={SIZE_MAX,SIZE_MAX/16+1,S24_XTS_MAX_BLOCKS+1};
    for(unsigned i=0;i<3;i++) {
        memcpy(before,buf,sizeof(buf));CK(m.xts(key,t,bad[i],buf,out)==NULL);
        CK(!memcmp(before,buf,sizeof(buf)) && !memcmp(tw,t,m.tweak_size));
    }
    CK(m.xts(key,t,0,NULL,NULL)==t && !memcmp(tw,t,m.tweak_size));
    CK(dec.xts(key,t,1,buf,out)==NULL && !memcmp(tw,t,m.tweak_size));
    memcpy(other,key,m.size);memcpy(copy,t,m.tweak_size);
    CK(m.xts(other,copy,1,buf,out)==NULL); /* Key address binding rejects relocation. */
    CK(m.init(&m,key,16,raw,raw+32)==0);
    CK(m.xts(key,t,1,buf,out)==NULL && !memcmp(tw,t,m.tweak_size)); /* Identical rekey is a new generation. */
    m.key_sched(&m,key,32,raw,raw+32);CK(m.set_tweak(key,t,iv)==0);
    memcpy(state,key,m.size);memcpy(iv,key,16); /* IV alias into const key is safe. */
    CK(m.set_tweak(key,t,iv)==0);memcpy(tw,t,m.tweak_size);
    CK(m.set_tweak(key,t,key)==0 && !memcmp(tw,t,m.tweak_size) && !memcmp(state,key,m.size));
    /* Initializer errors clear admitted destination state; const aliases do not
     * override that documented clearing policy for rejected inputs. */
    CK(m.set_tweak(key,t,t)!=0 && zero(t,m.tweak_size) && !memcmp(state,key,m.size));
    CK(m.init(&m,key,16,key,raw+32)!=0 && zero(key,m.size));
    m.key_sched(&m,key,24,raw,raw+32);CK(zero(key,m.size));
    CK(m.set_tweak(key,t,iv)!=0 && zero(t,m.tweak_size));
    CK(m.init(&m,key,16,raw,raw)!=0 && zero(key,m.size));
    s24_xts_clear_key(key);s24_xts_clear_key(other);s24_xts_clear_tweak(t);s24_xts_clear_tweak(copy);
}
int main(void)
{
    vectors_direct();contracts();
    printf("PASS independent XTS probe: %u records both directions, %u checks; no provider\n",VECTOR_COUNT,checks);
    return 0;
}
