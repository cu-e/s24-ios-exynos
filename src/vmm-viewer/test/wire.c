/* Cross-implementation vectors for the viewer: the VMM's own C encoder/decoder (src/vmm/scfb.c).
 *   wire frames OUT   writes S24F frames made with s24f_encode_header (a full 5x3 frame, then a 2x2
 *                     damage rectangle at (1,1), then a 1x1 rectangle at (4,2)) followed by pixels.
 *   wire touches IN   decodes 20-byte touch messages with s24t_decode and prints one JSON line each. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "scfb.h"

static int write_frame(FILE *out, uint32_t width, uint32_t height, uint64_t seq, uint32_t x, uint32_t y, uint32_t w, uint32_t h,
                       uint8_t base) {
    uint8_t pixels[5 * 3 * 4], header[S24F_HEADER_BYTES];
    struct scfb_frame f = {.width = width, .height = height, .x = x, .y = y, .w = w, .h = h, .seq = seq, .pixels = pixels};
    for (uint32_t i = 0; i < w * h * 4; i++) pixels[i] = (uint8_t)(base + i); /* B, G, R, X per pixel */
    s24f_encode_header(header, &f);
    return fwrite(header, 1, sizeof header, out) != sizeof header || fwrite(pixels, 1, (size_t)w * h * 4, out) != (size_t)w * h * 4;
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    if (!strcmp(argv[1], "frames")) {
        FILE *out = fopen(argv[2], "wb");
        if (!out) return 1;
        int bad = write_frame(out, 5, 3, 7, 0, 0, 5, 3, 0x10) | write_frame(out, 5, 3, 8, 1, 1, 2, 2, 0xa0) |
                  write_frame(out, 5, 3, 0x100000009ull, 4, 2, 1, 1, 0xf0);
        return fclose(out) || bad;
    }
    if (!strcmp(argv[1], "touches")) {
        FILE *in = fopen(argv[2], "rb");
        uint8_t msg[S24T_BYTES];
        if (!in) return 1;
        while (fread(msg, 1, sizeof msg, in) == sizeof msg) {
            struct s24t_touch t = {0};
            int rc = s24t_decode(msg, &t);
            printf("{\"rc\":%d,\"slot\":%u,\"tracking_id\":%d,\"x\":%u,\"y\":%u}\n", rc, t.slot, t.tracking_id, t.x, t.y);
        }
        return fclose(in);
    }
    return 2;
}
