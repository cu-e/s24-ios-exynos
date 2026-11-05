/* Independent unsigned 64-bit-limb oracle; no signed shift or __ashrti3 oracle. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef __int128 s128;
typedef unsigned __int128 u128;
extern s128 __ashrti3(s128,int);
static u128 oracle(u128 bits,unsigned n)
{
    uint64_t hi=(uint64_t)(bits>>64),lo=(uint64_t)bits;
    uint64_t sign=(hi>>63)?UINT64_MAX:0,rh,rl;
    if(!n)return bits;
    if(n<64){rl=(lo>>n)|(hi<<(64-n));rh=(hi>>n)|(sign<<(64-n));}
    else if(n==64){rl=hi;rh=sign;}
    else{rl=(hi>>(n-64))|(sign<<(128-n));rh=sign;}
    return ((u128)rh<<64)|rl;
}
static uint64_t next(uint64_t *s)
{
    *s^=*s<<13;*s^=*s>>7;*s^=*s<<17;return *s;
}
int main(void)
{
    const u128 sign=(u128)1<<127;
    const u128 patterns[]={0,1,~(u128)0,sign,sign-1,((u128)UINT64_C(0xaaaaaaaaaaaaaaaa)<<64)|UINT64_C(0x5555555555555555),sign|1,((u128)1<<64)|UINT64_MAX};
    uint64_t seed=UINT64_C(0xb60fa12ac8871231);unsigned cases=1;
    /* Also reproduces original negative-left-shift UBSan finding immediately. */
    assert((u128)__ashrti3(-1,1)==~(u128)0);
    for(unsigned i=0;i<8;i++)for(unsigned n=0;n<128;n++){
        assert((u128)__ashrti3((s128)patterns[i],(int)n)==oracle(patterns[i],n));cases++;
    }
    for(unsigned i=0;i<10000;i++){
        u128 bits=((u128)next(&seed)<<64)|next(&seed);
        for(unsigned n=0;n<128;n++){
            assert((u128)__ashrti3((s128)bits,(int)n)==oracle(bits,n));cases++;
        }
    }
    puts("PASS 1281025 independent arithmetic shift cases");
    return cases==1281025?0:1;
}
