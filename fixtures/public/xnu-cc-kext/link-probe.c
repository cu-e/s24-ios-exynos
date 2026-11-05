/* Project-owned link probe; never a runtime replacement or kernel entrypoint. */
typedef __int128 s128;
typedef unsigned __int128 u128;
extern s128 __divti3(s128, s128);
extern s128 __modti3(s128, s128);
extern u128 __udivti3(u128, u128);
extern u128 __umodti3(u128, u128);
extern s128 __multi3(s128, s128);
extern s128 __ashrti3(s128,int);
volatile s128 s24_signed_a, s24_signed_b;
volatile u128 s24_unsigned_a, s24_unsigned_b;
long s24_runtime_link_probe(void)
{
    s128 a=s24_signed_a, b=s24_signed_b;
    u128 ua=s24_unsigned_a, ub=s24_unsigned_b;
    return (long)(__divti3(a,b)+__modti3(a,b)+__multi3(a,b))
        +(long)(__udivti3(ua,ub)+__umodti3(ua,ub))+(long)__ashrti3(a,(int)(ua&127u));
}
