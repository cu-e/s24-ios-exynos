/* Host execution of genuine generic integer builtins; no ARM64 execution claim. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef __int128 s128;
typedef unsigned __int128 u128;
extern s128 __divti3(s128,s128);
extern s128 __modti3(s128,s128);
extern u128 __udivti3(u128,u128);
extern u128 __umodti3(u128,u128);
extern s128 __multi3(s128,s128);
extern s128 __ashlti3(s128,int);
extern s128 __lshrti3(s128,int);
extern s128 __ashrti3(s128,int);
extern int __clzti2(s128);
extern int __ctzti2(s128);
extern int __cmpti2(s128,s128);
extern int __ucmpti2(u128,u128);
static uint64_t next(uint64_t *state)
{
    *state^=*state<<13;*state^=*state>>7;*state^=*state<<17;return *state;
}
int main(void)
{
    uint64_t state=0x972189234acd8e13ULL;
    unsigned cases=0;
    /* Construct dividends from known quotient/remainder, never using / or %
       as an oracle that might lower back into the helper under test. */
    for(unsigned i=0;i<10000;i++) {
        uint64_t b=(next(&state)>>1)+1,q=next(&state)>>2;
        uint64_t r=(next(&state)&0xffffu);
        if(r>=b)r=0;
        u128 product=0;
        for(unsigned bit=0;bit<64;bit++) if((q>>bit)&1u) product+=(u128)b<<bit;
        u128 a=product+r;
        assert(__udivti3(a,b)==q && __umodti3(a,b)==r);
        assert(__divti3((s128)a,(s128)b)==(s128)q);
        assert(__modti3((s128)a,(s128)b)==(s128)r);
        assert(__divti3(-(s128)a,(s128)b)==-(s128)q);
        assert(__modti3(-(s128)a,(s128)b)==-(s128)r);
        assert(__divti3((s128)a,-(s128)b)==-(s128)q);
        assert(__multi3((s128)b,(s128)q)==(s128)(a-r));
        cases++;
    }
    for(unsigned bit=0;bit<128;bit++) {
        u128 x=(u128)1<<bit;
        assert((u128)__lshrti3((s128)x,(int)bit)==1);
        assert((u128)__ashlti3(1,(int)bit)==x);
        assert(__ashrti3(-1,(int)bit)==-1);
        assert(__clzti2((s128)x)==127-(int)bit && __ctzti2((s128)x)==(int)bit);
        assert(__cmpti2(-2,3)==0 && __cmpti2(3,-2)==2 && __cmpti2(3,3)==1);
        assert(__ucmpti2(x,x)==1 && __ucmpti2(x,0)==2 && __ucmpti2(0,x)==0);
        cases++;
    }
    puts("PASS 10128 independently constructed integer cases");
    return cases==10128?0:1;
}
