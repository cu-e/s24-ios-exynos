/* SPDX-License-Identifier: GPL-2.0-only
 * Host-only tests of included actual STR019 source, never a target runtime. */
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "actual-loader-log.inc"
#include "extent-cases.inc"

static unsigned long checks;
#define CHECK(c) do { checks++; if (!(c)) { \
    fprintf(stderr, "STR019 fail line %d: %s\n", __LINE__, #c); exit(3); \
} } while (0)

static void snapshot(unsigned char *out)
{
    const volatile unsigned char *p = (const volatile unsigned char *)&loader_log;
    for (size_t i = 0; i < sizeof(loader_log); i++) out[i] = p[i];
}

static void write_record(FILE *file)
{
    unsigned char bytes[sizeof(loader_log)];
    snapshot(bytes);
    CHECK(fwrite(bytes, 1, sizeof(bytes), file) == sizeof(bytes));
}

/* Only this deliberate ASan control excludes UBSan, so its independent
 * expected failure must be AddressSanitizer. Production functions stay intact. */
__attribute__((noinline, no_sanitize("undefined")))
static int negative_asan(void)
{
    char *p = malloc(8);
    if (!p) return 2;
    volatile char *v = p;
    v[8] = 0x5a;
    free(p);
    return 0;
}

__attribute__((noinline))
static int negative_ubsan(void)
{
    volatile int a = INT_MAX, b = 1;
    return a + b;
}

int main(int argc, char **argv)
{
    _Static_assert(sizeof(uintptr_t) == 8, "qualified host64 only");
    if (argc == 2 && !strcmp(argv[1], "--negative-asan")) return negative_asan();
    if (argc == 2 && !strcmp(argv[1], "--negative-ubsan")) return negative_ubsan();
    if (argc != 3 || strcmp(argv[1], "--records")) return 2;
    FILE *file = fopen(argv[2], "wb");
    CHECK(file != NULL);
    CHECK(fwrite("STR019!", 1, 7, file) == 7);

    /* Existing image initializer is observable before explicit initialization. */
    CHECK(!memcmp((const void *)loader_log.magic, "E1SXNU01", 8));
    CHECK(loader_log.length == 0 && loader_log.reserved == 0);
    CHECK(loader_log.text[0] == 0);
    for (unsigned i = 0; i <= LOG_MAX; i++) loader_log.text[i] = (char)0xa5;
    log_init();
    CHECK(!memcmp((const void *)loader_log.magic, "E1SXNU01", 8));
    CHECK(loader_log.length == 0 && loader_log.reserved == 0 && loader_log.text[0] == 0);
    CHECK((unsigned char)loader_log.text[1] == 0xa5);

    log_str("hello\n");
    log_hex(0);
    log_char(' ');
    log_hex(UINT64_MAX);
    log_char(' ');
    log_kv("EL", 1);
    static const char text[] = "hello\n0x0 0xffffffffffffffff EL=0x1 ";
    CHECK(loader_log.length == sizeof(text) - 1);
    for (size_t i = 0; i < sizeof(text); i++) CHECK(loader_log.text[i] == text[i]);

    log_init();
    for (unsigned i = 0; i < LOG_MAX - 1U; i++) log_char((char)(i * 17U + 1U));
    CHECK(loader_log.length == LOG_MAX - 1U);
    CHECK(loader_log.text[LOG_MAX - 1U] == 0);
    log_char((char)((LOG_MAX - 1U) * 17U + 1U));
    CHECK(loader_log.length == LOG_MAX && loader_log.text[LOG_MAX] == 0);
    for (unsigned i = 0; i < LOG_MAX; i++)
        CHECK((unsigned char)loader_log.text[i] == (unsigned char)(i * 17U + 1U));
    unsigned char before[sizeof(loader_log)], after[sizeof(loader_log)];
    snapshot(before);
    for (unsigned i = 0; i < 4096; i++) log_char('!');
    snapshot(after);
    CHECK(!memcmp(before, after, sizeof(before)));
    write_record(file);

    loader_log.length = LOG_MAX + 1U;
    snapshot(before);
    log_char('?');
    snapshot(after);
    CHECK(!memcmp(before, after, sizeof(before)));
    loader_log.length = UINT32_MAX;
    snapshot(before);
    log_char('?');
    snapshot(after);
    CHECK(!memcmp(before, after, sizeof(before)));

    log_init();
    CHECK(loader_log.length == 0 && loader_log.text[0] == 0);
    log_kv("decoder", UINT64_MAX);
    CHECK(loader_log.length == sizeof("decoder=0xffffffffffffffff ") - 1U);
    CHECK(fwrite("---", 1, 3, file) == 3);
    write_record(file);
    CHECK(fclose(file) == 0);

    for (size_t i = 0; i < sizeof(extent_cases) / sizeof(extent_cases[0]); i++) {
        const struct extent_case *v = &extent_cases[i];
        uint64_t size = UINT64_C(0x1122334455667788);
        int valid = loader_reserved_size(v->image, v->end, v->payload, &size);
        CHECK(valid == v->valid);
        CHECK(size == (valid ? v->size : UINT64_C(0x1122334455667788)));
    }
    printf("STR019 actual host assertions=%lu extent_vectors=%zu record_size=%zu\n",
        checks, sizeof(extent_cases) / sizeof(extent_cases[0]), sizeof(loader_log));
    return 0;
}
