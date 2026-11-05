/* Independent bit-by-bit unsigned oracle against the actual source helper. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef __int128 signed128;
typedef unsigned __int128 bits128;
extern signed128 __ashrti3(signed128,int);
static bits128 expected(bits128 input,unsigned count)
{
    bits128 result=0;
    unsigned sign=(unsigned)(input>>127);
    for(unsigned bit=0;bit<128;bit++) {
        unsigned source=bit+count;
        unsigned value=source<128?(unsigned)((input>>source)&1):sign;
        if(value) result|=(bits128)1<<bit;
    }
    return result;
}
static uint64_t random64(uint64_t *state)
{
    *state^=*state<<13;*state^=*state>>7;*state^=*state<<17;return *state;
}
int main(void)
{
    const bits128 sign=(bits128)1<<127;
    const bits128 cases[]={0,1,~(bits128)0,sign,sign-1,sign+1,
        ((bits128)UINT64_MAX)<<64,UINT64_MAX,
        ((bits128)UINT64_C(0xaaaaaaaaaaaaaaaa)<<64)|UINT64_C(0x5555555555555555)};
    uint64_t seed=UINT64_C(0x7ca2fe119f51b39d);
    unsigned checks=1;
    /* Original upstream source must diagnose its negative signed left shift. */
    assert(__ashrti3(-1,1)==-1);
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++)
        for(unsigned n=0;n<128;n++,checks++)
            assert((bits128)__ashrti3((signed128)cases[i],(int)n)==expected(cases[i],n));
    for(unsigned i=0;i<1024;i++) {
        bits128 input=((bits128)random64(&seed)<<64)|random64(&seed);
        for(unsigned n=0;n<128;n++,checks++)
            assert((bits128)__ashrti3((signed128)input,(int)n)==expected(input,n));
    }
    printf("PASS %u independent bitwise-oracle arithmetic-shift cases; host only\n",checks);
    return checks==132225?0:1;
}
