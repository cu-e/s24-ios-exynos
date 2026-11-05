/* Owned host-buildable arithmetic and input contract. No display/HID I/O. */
#ifndef S24_UI_CONTRACT_H
#define S24_UI_CONTRACT_H
#include <stddef.h>
#include <stdint.h>
#define UI_INPUT_BYTES 40u
#define UI_MAX_CONTACTS 10u
#define UI_MAX_DIMENSION 16384u
enum ui_result { UI_OK=0, UI_ARGUMENT=1, UI_FORMAT=2, UI_BOUNDS=3,
    UI_OVERFLOW=4, UI_VERSION=5, UI_SESSION=6, UI_LOSS=7,
    UI_DESYNC=8, UI_TRANSITION=9, UI_CLOCK=10, UI_STOPPED=11 };
/* Project values, not Apple pixel-format constants. Linear single-plane only. */
enum ui_format { UI_BGRA8=1, UI_RGBA8=2 };
enum ui_kind { UI_DOWN=1, UI_MOVE=2, UI_UP=3, UI_CANCEL_ALL=4 };
struct ui_layout {
    uint64_t capacity, offset, stride;
    uint32_t width, height, format, flags;
};
struct ui_point { uint32_t x, y; };
struct ui_event {
    uint64_t time_ns;
    uint32_t epoch, sequence, kind, slot, x, y;
};
struct ui_input_state {
    uint64_t time_ns;
    uint32_t epoch, sequence, active, needs_resync, stopped;
};
#ifdef __cplusplus
extern "C" {
#endif
uint32_t ui_layout_check(const struct ui_layout *, uint64_t *);
uint32_t ui_region(const struct ui_layout *, uint32_t, uint32_t, uint32_t, uint32_t, uint64_t *, uint64_t *);
uint32_t ui_map_point(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, struct ui_point *);
uint32_t ui_pixel_point(const struct ui_point *, uint32_t, uint32_t, struct ui_point *);
uint32_t ui_event_decode(const uint8_t *, size_t, struct ui_event *);
uint32_t ui_input_init(struct ui_input_state *, uint32_t);
uint32_t ui_input_apply(struct ui_input_state *, const struct ui_event *);
void ui_input_stop(struct ui_input_state *);
#ifdef __cplusplus
}
#endif
#endif
