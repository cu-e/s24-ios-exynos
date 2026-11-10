/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Independently authored freestanding candidate; no hardware qualification. */
#include "s5e9945.h"
static void barrier(void) {
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}
static int valid(const struct s5e_wdt *w) {
    return w && w->timer && w->pmu && w->cluster < 2;
}
static unsigned route(const struct s5e_wdt *w) {
    return (w->cluster ? 0x1844 : 0x1244) / 4;
}
static uint32_t mask(const struct s5e_wdt *w) { return 1u << (2 + w->cluster); }
int s5e_wdt_query(const struct s5e_wdt *w, struct s5e_wdt_state *s) {
    if (!valid(w) || !s) return -1;
    s->control=w->timer[0]; s->reload=w->timer[1]; s->count=w->timer[2];
    s->route=w->pmu[route(w)];
    return 0;
}
int s5e_wdt_arm(const struct s5e_wdt *w, uint32_t seconds) {
    if (!valid(w) || !seconds || !w->rate_hz) return -1;
    /* Ceiling prevents an early expiry; reject rather than silently clamp. */
    uint64_t ticks=((uint64_t)w->rate_hz * seconds + 127)/128;
    uint64_t divisor=(ticks + 65534)/65535;
    if (!divisor || divisor > 256) return -1;
    uint32_t count=(uint32_t)((ticks + divisor - 1)/divisor);
    w->timer[0] &= ~((1u<<5)|1u);
    barrier();
    w->pmu[route(w)] |= mask(w);
    /* Follow the Samsung windowed sequence; disable debug-ack masking so a
       debug halt cannot deliberately pause this candidate reset timer. */
    w->timer[3]=0;
    w->timer[4]=count*2;
    w->timer[1]=count;
    w->timer[2]=count;
    barrier();
    w->timer[0]=(1u<<20)|((uint32_t)(divisor-1)<<8)|(3u<<3)|(1u<<5)|1u;
    barrier();
    return ((w->pmu[route(w)] & mask(w)) && (w->timer[0]&0x21)==0x21) ? 0 : -1;
}
void s5e_wdt_pet(const struct s5e_wdt *w) {
    if (!valid(w)) return;
    w->timer[3]=0; w->timer[2]=w->timer[1]; barrier();
}
void s5e_wdt_disarm(const struct s5e_wdt *w) {
    if (!valid(w)) return;
    w->timer[0] &= ~0x21u; barrier();
    w->timer[3]=0;
    w->pmu[route(w)] &= ~mask(w); barrier();
}
