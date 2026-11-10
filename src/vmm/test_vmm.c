/* Host tests for the s24vmm machine description. The FDT reader here is independent of fdt.c: it walks
 * the blob token by token as the devicetree specification defines it. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fdt.h"
#include "machine.h"

static int failures, checks;
#define CHECK(c) do { checks++; if (!(c)) { failures++; fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint32_t be32(const uint8_t *p) {
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

/* Finds property `prop` of the node at `path` ("/a/b"); returns its data and length, or NULL. */
static const uint8_t *lookup(const uint8_t *blob, const char *path, const char *prop, uint32_t *len) {
    const uint8_t *s = blob + be32(blob + 8), *strings = blob + be32(blob + 12);
    const uint8_t *end = s + be32(blob + 36);
    char stack[8][64];
    int depth = -1;
    while (s < end) {
        uint32_t tok = be32(s);
        s += 4;
        if (tok == 1) {
            const char *name = (const char *)s;
            depth++;
            if (depth >= 8) return NULL;
            snprintf(stack[depth], sizeof stack[depth], "%s", name);
            s += (strlen(name) + 4) & ~3u;
        } else if (tok == 2) {
            depth--;
        } else if (tok == 3) {
            uint32_t plen = be32(s), nameoff = be32(s + 4);
            const uint8_t *data = s + 8;
            char here[256] = "";
            for (int i = 1; i <= depth; i++) {
                strcat(here, "/");
                strcat(here, stack[i]);
            }
            if (!here[0]) strcpy(here, "/");
            if (!strcmp(here, path) && !strcmp((const char *)strings + nameoff, prop)) {
                *len = plen;
                return data;
            }
            s += 8 + ((plen + 3) & ~3u);
        } else if (tok == 4) {
            continue;
        } else if (tok == 9) {
            break;
        } else {
            return NULL;
        }
    }
    return NULL;
}

static uint64_t cells64(const uint8_t *p) {
    return (uint64_t)be32(p) << 32 | be32(p + 4);
}

static void test_fdt_writer_errors(void) {
    static struct fdt_w w;
    uint8_t out[256];
    fdt_w_init(&w);
    fdt_prop_u32(&w, "orphan", 1); /* property outside any node */
    CHECK(fdt_finish(&w, out, sizeof out) == 0);
    fdt_w_init(&w);
    fdt_begin_node(&w, "");
    CHECK(fdt_finish(&w, out, sizeof out) == 0); /* unclosed node */
    fdt_w_init(&w);
    fdt_end_node(&w);
    CHECK(fdt_finish(&w, out, sizeof out) == 0); /* close without open */
    fdt_w_init(&w);
    fdt_begin_node(&w, "");
    fdt_prop_str(&w, "a", "b");
    fdt_end_node(&w);
    CHECK(fdt_finish(&w, out, 40) == 0); /* output too small */
    fdt_w_init(&w);
    fdt_begin_node(&w, "");
    char big[300];
    memset(big, 'x', sizeof big - 1);
    big[sizeof big - 1] = 0;
    for (int i = 0; i < 80 && !w.error; i++) fdt_prop_str(&w, big, "v"); /* same name is interned once */
    CHECK(!w.error && w.strings_len == sizeof big);
    for (int i = 0; i < 100; i++) fdt_prop(&w, "blob", big, sizeof big);
    CHECK(w.error); /* structure overflow is detected */
    fdt_w_init(&w);
    for (int i = 0; i < FDT_W_DEPTH_MAX + 1; i++) fdt_begin_node(&w, "n");
    CHECK(w.error);
}

static void test_layout_and_fdt(void) {
    struct vmm_layout l = {.ram_size = 1024ull << 20, .cpus = 4, .image_size = 0x30000, .initrd_size = 20u << 20, .bootargs = "-v cpus=4"};
    CHECK(vmm_plan(&l) == 0);
    CHECK(l.image_addr == VMM_RAM_BASE);
    CHECK(l.initrd_addr == VMM_RAM_BASE + 0x1000000);
    CHECK(l.fdt_addr == VMM_RAM_BASE + (1024ull << 20) - 0x200000);
    CHECK(l.gicr_base == 0x3fff0000ull - 4 * 0x20000ull && l.gicr_size == 0x80000);
    static uint8_t blob[65536];
    size_t n = vmm_build_fdt(&l, blob, sizeof blob);
    CHECK(n > 0 && be32(blob) == 0xd00dfeed && be32(blob + 4) == n && be32(blob + 20) == 17);
    uint32_t len = 0;
    const uint8_t *p = lookup(blob, "/memory@80000000", "reg", &len);
    CHECK(p && len == 16 && cells64(p) == VMM_RAM_BASE && cells64(p + 8) == (1024ull << 20));
    p = lookup(blob, "/memory@80000000", "device_type", &len);
    CHECK(p && !strcmp((const char *)p, "memory"));
    p = lookup(blob, "/chosen", "bootargs", &len);
    CHECK(p && !strcmp((const char *)p, "-v cpus=4"));
    p = lookup(blob, "/chosen", "linux,initrd-start", &len);
    CHECK(p && len == 8 && cells64(p) == l.initrd_addr);
    p = lookup(blob, "/chosen", "linux,initrd-end", &len);
    CHECK(p && len == 8 && cells64(p) == l.initrd_addr + (20u << 20));
    p = lookup(blob, "/intc@3fff0000", "reg", &len);
    CHECK(p && len == 32 && cells64(p) == VMM_GICD_BASE && cells64(p + 8) == VMM_GICD_SIZE && cells64(p + 16) == l.gicr_base &&
          cells64(p + 24) == l.gicr_size);
    p = lookup(blob, "/intc@3fff0000", "compatible", &len);
    CHECK(p && !strcmp((const char *)p, "arm,gic-v3"));
    p = lookup(blob, "/timer", "interrupts", &len);
    CHECK(p && len == 48 && be32(p + 24) == 1 && be32(p + 28) == 11); /* virtual timer PPI 11 = INTID 27 */
    p = lookup(blob, "/uart@3f8", "reg", &len);
    CHECK(p && len == 16 && cells64(p) == 0x3f8 && cells64(p + 8) == 8);
    p = lookup(blob, "/uart@3f8", "compatible", &len);
    CHECK(p && !strcmp((const char *)p, "ns16550a"));
    p = lookup(blob, "/psci", "method", &len);
    CHECK(p && !strcmp((const char *)p, "hvc"));
    p = lookup(blob, "/psci", "compatible", &len);
    CHECK(p && !strcmp((const char *)p, "arm,psci-1.0"));
    p = lookup(blob, "/rtc@2000", "compatible", &len);
    CHECK(p && !strcmp((const char *)p, "arm,pl031"));
    p = lookup(blob, "/cpus/cpu@3", "reg", &len);
    CHECK(p && len == 4 && be32(p) == 3);
    p = lookup(blob, "/cpus/cpu@4", "reg", &len);
    CHECK(p == NULL);
    p = lookup(blob, "/cpus", "#address-cells", &len);
    CHECK(p && be32(p) == 1);
    p = lookup(blob, "/", "interrupt-parent", &len);
    CHECK(p && be32(p) == 1);
    p = lookup(blob, "/intc@3fff0000", "phandle", &len);
    CHECK(p && be32(p) == 1);

    struct vmm_layout bad = l;
    bad.initrd_size = 1024ull << 20; /* cannot fit below the FDT */
    CHECK(vmm_plan(&bad) == -1);
    bad = l;
    bad.cpus = 0;
    CHECK(vmm_plan(&bad) == -1);
    bad = l;
    bad.cpus = VMM_MAX_CPUS + 1;
    CHECK(vmm_plan(&bad) == -1);
    bad = l;
    bad.ram_size = 1000ull << 20 | 4096;
    CHECK(vmm_plan(&bad) == -1);
    bad = l;
    bad.initrd_size = 0;
    CHECK(vmm_plan(&bad) == 0);
    n = vmm_build_fdt(&bad, blob, sizeof blob);
    CHECK(n && lookup(blob, "/chosen", "linux,initrd-start", &len) == NULL);
    CHECK(vmm_build_fdt(&l, blob, 100) == 0);
}

static void test_image_extent(void) {
    uint8_t img[128] = {0};
    CHECK(vmm_image_extent(img, sizeof img) == 0);
    memcpy(img + 56, "ARM\x64", 4);
    img[16] = 0x00;
    img[17] = 0x10; /* image_size 0x1000 */
    CHECK(vmm_image_extent(img, sizeof img) == 0x1000);
    img[17] = 0;
    CHECK(vmm_image_extent(img, sizeof img) == sizeof img); /* file larger than image_size */
    CHECK(vmm_image_extent(img, 32) == 0);
}

static void test_uart(void) {
    struct vmm_uart u;
    uint8_t tx = 0;
    vmm_uart_reset(&u);
    CHECK(vmm_uart_read(&u, 5) == 0x60);
    CHECK(vmm_uart_write(&u, 0, 'A', &tx) == 1 && tx == 'A');
    CHECK(vmm_uart_write(&u, 3, 0x83, &tx) == 0); /* DLAB on */
    CHECK(vmm_uart_write(&u, 0, 0x01, &tx) == 0 && vmm_uart_read(&u, 0) == 0x01);
    CHECK(vmm_uart_write(&u, 1, 0x02, &tx) == 0 && vmm_uart_read(&u, 1) == 0x02);
    vmm_uart_write(&u, 3, 0x03, &tx); /* DLAB off */
    CHECK(vmm_uart_read(&u, 1) == 0);
    vmm_uart_write(&u, 1, 0x01, &tx);
    CHECK(vmm_uart_read(&u, 1) == 0x01);
    CHECK(vmm_uart_read(&u, 2) == 0xc1);
    CHECK(vmm_uart_push_rx(&u, 'x') == 0 && vmm_uart_push_rx(&u, 'y') == 0);
    CHECK(vmm_uart_read(&u, 5) == 0x61 && vmm_uart_read(&u, 2) == 0xc4);
    CHECK(vmm_uart_read(&u, 0) == 'x' && vmm_uart_read(&u, 0) == 'y' && vmm_uart_read(&u, 5) == 0x60);
    for (int i = 0; i < 64; i++) CHECK(vmm_uart_push_rx(&u, (uint8_t)i) == 0);
    CHECK(vmm_uart_push_rx(&u, 0) == -1);
    for (int i = 0; i < 64; i++) CHECK(vmm_uart_read(&u, 0) == (uint8_t)i);
    CHECK(vmm_uart_read(&u, 6) == 0xb0);
    vmm_uart_write(&u, 7, 0x5a, &tx);
    CHECK(vmm_uart_read(&u, 7) == 0x5a);
}

static void test_rtc(void) {
    struct vmm_rtc r;
    vmm_rtc_reset(&r);
    CHECK(vmm_rtc_read(&r, 0, 1000) == 1000);
    vmm_rtc_write(&r, 8, 5000, 1000);
    CHECK(vmm_rtc_read(&r, 0, 1010) == 5010);
    CHECK(vmm_rtc_read(&r, 0xfe0, 0) == 0x31 && vmm_rtc_read(&r, 0xfe4, 0) == 0x10 && vmm_rtc_read(&r, 0xfe8, 0) == 0x04);
    CHECK(vmm_rtc_read(&r, 0xff0, 0) == 0x0d && vmm_rtc_read(&r, 0xffc, 0) == 0xb1);
    CHECK(vmm_rtc_read(&r, 0xc, 0) == 1);
    vmm_rtc_write(&r, 0xc, 0, 0);
    CHECK(vmm_rtc_read(&r, 0xc, 0) == 1);
    vmm_rtc_write(&r, 0x10, 3, 0);
    CHECK(vmm_rtc_read(&r, 0x10, 0) == 1);
}

static void put_desc(uint8_t *ram, uint64_t base, uint64_t table, unsigned index, uint64_t desc) {
    for (int b = 0; b < 8; b++) ram[table - base + index * 8u + (unsigned)b] = (uint8_t)(desc >> (8 * b));
}

/* Indices below are computed by hand from the architecture's bit fields, not from vmm_walk. */
static void test_walk(void) {
    static uint8_t ram[0x40000];
    const uint64_t B = 0x80000000ull;
    uint64_t pa = 0;
    /* 4K granule with the TCR_EL1 the XNU guest set on the S24: T0SZ = T1SZ = 26 (38-bit VA), TG1 = 4K. */
    const uint64_t tcr = 0x22a51a251aull;
    memset(ram, 0, sizeof ram);
    put_desc(ram, B, B + 0x1000, 0xc0, (B + 0x2000) | 3);    /* VA bits 37:30 of 0xfffffff007004123 */
    put_desc(ram, B, B + 0x2000, 0x38, (B + 0x3000) | 3);    /* bits 29:21 */
    put_desc(ram, B, B + 0x3000, 0x04, 0x83004000ull | 0x403); /* bits 20:12, AF | page */
    put_desc(ram, B, B + 0x3000, 0x06, 0x83006000ull | 0x401); /* level 3 with type 01 is reserved */
    put_desc(ram, B, B + 0x2000, 0x39, 0x83200000ull | 0x401); /* 2 MiB block */
    const uint64_t ttbr1 = (5ull << 48) | (B + 0x1000);        /* ASID must be ignored */
    put_desc(ram, B, B + 0x4000, 2, 0x80000000ull | 0x401);    /* TTBR0: 1 GiB block, identity */
    put_desc(ram, B, B + 0x4000, 3, 0x200000000ull | 3);       /* table outside RAM */
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xfffffff007004123ull, &pa) == 0 && pa == 0x83004123ull);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xfffffff007201234ull, &pa) == 0 && pa == 0x83201234ull);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xfffffff007005000ull, &pa) == 4);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xfffffff007006000ull, &pa) == 4);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xffffffc000000000ull, &pa) == 2);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xffff000000000000ull, &pa) == -1);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0x80001234ull, &pa) == 0 && pa == 0x80001234ull);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0xc0000000ull, &pa) == -2);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, B + 0x4000, ttbr1, 0x4000000000ull, &pa) == -1); /* above 38 bits */
    CHECK(vmm_walk(ram, B, sizeof ram, tcr | 1ull << 23, B + 0x4000, ttbr1, 0xfffffff007004123ull, &pa) == -1); /* EPD1 */
    CHECK(vmm_walk(ram, B, sizeof ram, tcr, 0x10000000ull, ttbr1, 0x1000ull, &pa) == -2);

    /* 16K granule, T1SZ = 25 (39-bit VA): levels 1 (bits 38:36), 2 (35:25), 3 (24:14). */
    const uint64_t tcr16 = (0x19ull << 16) | (1ull << 30) | 0x19ull | (2ull << 14);
    memset(ram, 0, sizeof ram);
    put_desc(ram, B, B + 0x4000, 7, (B + 0x8000) | 3);
    put_desc(ram, B, B + 0x8000, 0x003, (B + 0xc000) | 3);
    put_desc(ram, B, B + 0xc000, 0x401, 0x83004000ull | 0x403);
    put_desc(ram, B, B + 0x4000, 6, 0x1000000000ull | 1); /* a level-1 block is not allowed with 16K */
    put_desc(ram, B, B + 0x8000, 0x004, 0x84000000ull | 0x401); /* 32 MiB level-2 block */
    CHECK(vmm_walk(ram, B, sizeof ram, tcr16, 0, B + 0x4000, 0xfffffff007004123ull, &pa) == 0 && pa == 0x83004123ull);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr16, 0, B + 0x4000, 0xffffffe000000000ull, &pa) == 2);
    CHECK(vmm_walk(ram, B, sizeof ram, tcr16, 0, B + 0x4000, 0xfffffff009012345ull, &pa) == 0 && pa == 0x85012345ull);
}

int main(void) {
    test_walk();
    test_fdt_writer_errors();
    test_layout_and_fdt();
    test_image_extent();
    test_uart();
    test_rtc();
    printf("{\"checks\":%d,\"failures\":%d}\n", checks, failures);
    return failures ? 1 : 0;
}
