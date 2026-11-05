#include "contract.h"

static int add(uint64_t a, uint64_t b, uint64_t *out)
{ if (a > UINT64_MAX-b) return 0; *out=a+b; return 1; }
static int mul(uint64_t a, uint64_t b, uint64_t *out)
{ if (b && a > UINT64_MAX/b) return 0; *out=a*b; return 1; }

uint32_t ui_layout_check(const struct ui_layout *p, uint64_t *end)
{
    uint64_t row, tail, value;
    if (!p || !end) return UI_ARGUMENT;
    *end=0;
    if (p->flags || (p->format!=UI_BGRA8 && p->format!=UI_RGBA8)) return UI_FORMAT;
    if (!p->width || !p->height || p->width>UI_MAX_DIMENSION || p->height>UI_MAX_DIMENSION) return UI_BOUNDS;
    row=(uint64_t)p->width*4;
    if (p->stride<row) return UI_BOUNDS;
    if (!mul(p->stride,p->height-1,&tail) || !add(p->offset,tail,&value) || !add(value,row,&value)) return UI_OVERFLOW;
    if (value>p->capacity) return UI_BOUNDS;
    *end=value;
    return UI_OK;
}

uint32_t ui_region(const struct ui_layout *p, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint64_t *begin, uint64_t *end)
{
    uint32_t result;
    uint64_t extent;
    if (!begin || !end || begin==end) return UI_ARGUMENT;
    *begin=*end=0;
    result=ui_layout_check(p,&extent);
    if (result) return result;
    if (!w || !h || x>=p->width || y>=p->height || w>p->width-x || h>p->height-y) return UI_BOUNDS;
    /* Layout validation proves these subsets cannot overflow. End excludes
       trailing row padding; the interval can contain inter-row padding. */
    *begin=p->offset+(uint64_t)y*p->stride+(uint64_t)x*4;
    *end=p->offset+(uint64_t)(y+h-1)*p->stride+(uint64_t)(x+w)*4;
    return UI_OK;
}

uint32_t ui_map_point(uint32_t x, uint32_t y, uint32_t maxx, uint32_t maxy, uint32_t flip, uint32_t rotation, struct ui_point *out)
{
    uint32_t nx,ny;
    if (!out) return UI_ARGUMENT;
    out->x=out->y=0;
    if (!maxx || !maxy || maxx>65535 || maxy>65535 || x>maxx || y>maxy || flip>3 || rotation>3) return UI_BOUNDS;
    nx=(uint32_t)((uint64_t)x*65535/maxx); ny=(uint32_t)((uint64_t)y*65535/maxy);
    if (flip&1) nx=65535-nx;
    if (flip&2) ny=65535-ny;
    switch (rotation) {
    case 0: out->x=nx; out->y=ny; break;
    case 1: out->x=65535-ny; out->y=nx; break;
    case 2: out->x=65535-nx; out->y=65535-ny; break;
    default: out->x=ny; out->y=65535-nx; break;
    }
    return UI_OK;
}

uint32_t ui_pixel_point(const struct ui_point *in, uint32_t width, uint32_t height, struct ui_point *out)
{
    uint32_t x,y;
    if (!in || !out) return UI_ARGUMENT;
    x=in->x; y=in->y;
    out->x=out->y=0;
    if (x>65535 || y>65535 || !width || !height || width>UI_MAX_DIMENSION || height>UI_MAX_DIMENSION) return UI_BOUNDS;
    out->x=(uint32_t)((uint64_t)x*(width-1)/65535); out->y=(uint32_t)((uint64_t)y*(height-1)/65535);
    return UI_OK;
}

static uint16_t rd16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8)); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)rd16(p)|((uint32_t)rd16(p+2)<<16); }
static uint64_t rd64(const uint8_t *p) { return (uint64_t)rd32(p)|((uint64_t)rd32(p+4)<<32); }
static uint32_t event_valid(const struct ui_event *p)
{
    if (!p->epoch || !p->sequence || !p->time_ns) return UI_ARGUMENT;
    if (p->kind<UI_DOWN || p->kind>UI_CANCEL_ALL || p->slot>=UI_MAX_CONTACTS || p->x>65535 || p->y>65535) return UI_BOUNDS;
    if (p->kind==UI_CANCEL_ALL && (p->slot || p->x || p->y)) return UI_ARGUMENT;
    return UI_OK;
}

uint32_t ui_event_decode(const uint8_t *wire, size_t size, struct ui_event *out)
{
    struct ui_event empty={0};
    if (!out) return UI_ARGUMENT;
    *out=empty;
    if (!wire || size!=UI_INPUT_BYTES) return UI_ARGUMENT;
    if (rd32(wire)!=UINT32_C(0x49483145) || rd16(wire+4)!=1 || rd16(wire+6)!=UI_INPUT_BYTES) return UI_VERSION;
    if (rd32(wire+36)) return UI_ARGUMENT;
    out->epoch=rd32(wire+8); out->sequence=rd32(wire+12); out->time_ns=rd64(wire+16);
    out->kind=rd16(wire+24); out->slot=rd16(wire+26); out->x=rd32(wire+28); out->y=rd32(wire+32);
    {
        uint32_t result=event_valid(out);
        if (result) *out=empty;
        return result;
    }
}

uint32_t ui_input_init(struct ui_input_state *s, uint32_t epoch)
{
    struct ui_input_state empty={0};
    if (!s) return UI_ARGUMENT;
    *s=empty; s->needs_resync=1;
    if (!epoch) return UI_ARGUMENT;
    s->epoch=epoch;
    return UI_OK;
}

uint32_t ui_input_apply(struct ui_input_state *s, const struct ui_event *e)
{
    uint32_t result,bit;
    if (!s || !e || !s->epoch) return UI_ARGUMENT;
    if (s->stopped) return UI_STOPPED;
    result=event_valid(e);
    if (result) { s->needs_resync=1; return result; }
    if (e->epoch!=s->epoch) return UI_SESSION;
    if (e->sequence<=s->sequence) { s->needs_resync=1; return UI_LOSS; }
    if (e->time_ns<s->time_ns) { s->needs_resync=1; return UI_CLOCK; }
    if (e->kind==UI_CANCEL_ALL) {
        /* Logical accepted cancellation only. The adapter must actually
           dispatch all releases before applying this transition. */
        s->active=0; s->needs_resync=0;
    } else {
        if (s->needs_resync) return UI_DESYNC;
        if (e->sequence!=s->sequence+1) { s->needs_resync=1; return UI_LOSS; }
        bit=UINT32_C(1)<<e->slot;
        if ((e->kind==UI_DOWN && (s->active&bit)) || (e->kind!=UI_DOWN && !(s->active&bit))) {
            s->needs_resync=1; return UI_TRANSITION;
        }
        if (e->kind==UI_DOWN) s->active|=bit;
        if (e->kind==UI_UP) s->active&=~bit;
    }
    s->sequence=e->sequence; s->time_ns=e->time_ns;
    return UI_OK;
}

void ui_input_stop(struct ui_input_state *s) { if (s) s->stopped=1; }
