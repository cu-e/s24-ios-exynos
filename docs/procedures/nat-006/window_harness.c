/* NAT-006 host harness: run the E1S loader's own DTB parsing and RAM-window choice on a real DTB.
 *
 * Built by check_loader.py from the project-built loader source (tools/build/e1s.py output):
 *   fdt.c compiled unchanged, and loader.c lines holding ranges_sort .. choose_window copied verbatim
 *   (check_loader.py records their hash) into window_extract.inc.
 * The DTB is mapped at the physical address the loader would see (MAP_FIXED), because choose_window
 * excludes the DTB's own address range. Prints one JSON object. Host only; no device access. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#include "fdt.h"

#define LOG_BASE 0x91200000UL   /* as loader.c */
#define LOG_RESERVE 0x200000UL  /* as loader.c */
#include "window_extract.inc"

static void *map_at(uint64_t pa, size_t len) {
    size_t span = (len + 0xfffff) & ~(size_t)0xfffff;
    void *p = mmap((void *)(uintptr_t)pa, span, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    return p == MAP_FAILED || p != (void *)(uintptr_t)pa ? NULL : p;
}

int main(int argc, char **argv) {
    if (argc != 6) {
        fprintf(stderr, "usage: %s DTB DTB_PA LOADER_PA LOADER_END_PA PAYLOAD_PA\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 2;
    static uint8_t blob[4 << 20];
    size_t len = fread(blob, 1, sizeof blob, f);
    fclose(f);
    uint64_t dtb_pa = strtoull(argv[2], NULL, 0), image = strtoull(argv[3], NULL, 0);
    uint64_t image_end = strtoull(argv[4], NULL, 0), payload = strtoull(argv[5], NULL, 0);
    uint8_t *dtb = map_at(dtb_pa, len);
    if (!dtb) { fprintf(stderr, "mmap %llx: %s\n", (unsigned long long)dtb_pa, strerror(errno)); return 3; }
    memcpy(dtb, blob, len);
    uintptr_t d = (uintptr_t)dtb;

    int valid = fdt_validate(d);
    struct fdt_range mem[16], occ[96];
    int nmem = valid ? fdt_memory_ranges(d, mem, 16) : -1, nocc = valid ? fdt_reserved_ranges(d, occ, 92) : -1;
    uint64_t fb_base = 0, fb_size = 0;
    uint32_t w = 0, h = 0, stride = 0;
#ifdef HAVE_SELECT_FB  /* loader.c with the NAT-006 S-Boot framebuffer fallback */
    int fb_source = valid ? loader_select_fb(d, &fb_base, &fb_size, &w, &h, &stride) : 0;
#else
    int fb_source = valid ? fdt_find_framebuffer(d, &fb_base, &fb_size, &w, &h, &stride) : 0;
#endif
    int have_fb = fb_source != 0;
    uint64_t initrd_start = 0, initrd_end = 0;
    int have_initrd = valid && fdt_chosen_u64(d, "linux,initrd-start", &initrd_start) && fdt_chosen_u64(d, "linux,initrd-end", &initrd_end);
    uint64_t loader_size = 0, win_base = 0, win_size = 0;
    int reserved_ok = loader_reserved_size(image, image_end, payload, &loader_size);
    int window = valid && reserved_ok && choose_window(d, image, loader_size, fb_base, fb_size, &win_base, &win_size);

    printf("{\"valid\":%d,\"memory_ranges\":%d,\"reserved_ranges\":%d,\"framebuffer\":{\"source\":%d,\"found\":%d,\"base\":\"0x%llx\",\"size\":\"0x%llx\","
           "\"width\":%u,\"height\":%u,\"stride\":%u},\"initrd\":{\"found\":%d,\"start\":\"0x%llx\",\"end\":\"0x%llx\"},"
           "\"loader\":{\"image\":\"0x%llx\",\"reserved_ok\":%d,\"reserved_size\":\"0x%llx\"},\"window\":{\"found\":%d,\"base\":\"0x%llx\",\"size\":\"0x%llx\"},",
           valid, nmem, nocc, fb_source, have_fb, (unsigned long long)fb_base, (unsigned long long)fb_size, w, h, stride, have_initrd,
           (unsigned long long)initrd_start, (unsigned long long)initrd_end, (unsigned long long)image, reserved_ok,
           (unsigned long long)loader_size, window, (unsigned long long)win_base, (unsigned long long)win_size);
    printf("\"memory\":[");
    for (int i = 0; i < nmem; i++)
        printf("%s[\"0x%llx\",\"0x%llx\"]", i ? "," : "", (unsigned long long)mem[i].base, (unsigned long long)mem[i].size);
    printf("],\"reserved\":[");
    for (int i = 0; i < nocc; i++)
        printf("%s[\"0x%llx\",\"0x%llx\"]", i ? "," : "", (unsigned long long)occ[i].base, (unsigned long long)occ[i].size);
    printf("]}\n");
    return 0;
}
