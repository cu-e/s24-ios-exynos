/* Owned host arithmetic/input stress. Synthetic, no pixels or HID dispatch. */
#include "contract.h"
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"failed line %d\n",__LINE__); return 1; } } while (0)
static uint32_t step(uint32_t *s) { *s^=*s<<13; *s^=*s>>17; *s^=*s<<5; return *s; }
int main(void)
{
    uint32_t seed=UINT32_C(0xe19945),i,j,result;
    uint8_t wire[40];
    struct ui_event event;
    struct ui_input_state state;
    struct ui_point point;
    struct ui_layout layout;
    uint64_t end;
    for (i=0;i<4096;++i) {
        layout.capacity=((uint64_t)step(&seed)<<32)|step(&seed);
        layout.offset=((uint64_t)step(&seed)<<32)|step(&seed);
        layout.stride=((uint64_t)step(&seed)<<32)|step(&seed);
        layout.width=(step(&seed)%16384)+1;layout.height=(step(&seed)%16384)+1;layout.format=1;layout.flags=0;
        result=ui_layout_check(&layout,&end);
        CHECK(result==UI_OK || result==UI_BOUNDS || result==UI_OVERFLOW);
        CHECK(result ? end==0 : end<=layout.capacity);
        for (j=0;j<sizeof(wire);++j) wire[j]=(uint8_t)step(&seed);
        CHECK(ui_event_decode(wire,step(&seed)%41,&event)!=UI_OK);
        CHECK(ui_map_point(i,i,4095,4095,i%4,i%4,&point)==UI_OK);
        CHECK(point.x<=65535 && point.y<=65535);
    }
    CHECK(ui_input_init(&state,1)==UI_OK);
    event=(struct ui_event){1,1,1,UI_CANCEL_ALL,0,0,0};
    CHECK(ui_input_apply(&state,&event)==UI_OK);
    event=(struct ui_event){2,1,2,UI_DOWN,9,65535,65535};
    CHECK(ui_input_apply(&state,&event)==UI_OK && state.active==512);
    event.sequence=4;event.time_ns=4;event.kind=UI_MOVE;
    CHECK(ui_input_apply(&state,&event)==UI_LOSS && state.active==512);
    ui_input_stop(&state);
    CHECK(ui_input_apply(&state,&event)==UI_STOPPED && state.active==512);
    puts("{\"outcome\":\"pass\",\"synthetic_cases\":4096,\"device_io\":false}");
    return 0;
}
