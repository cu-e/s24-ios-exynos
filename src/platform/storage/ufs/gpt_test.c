/* Host tests for gpt.c. Every negative case recomputes the CRCs, so the rule under
 * test is what rejects it rather than a checksum mismatch. No device data is used. */
#define _POSIX_C_SOURCE 200809L
#include "gpt.h"
#include "host.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __func__, __LINE__, #c); exit(1); } } while (0)
#define CHECK_EQ(a, b) do { unsigned long long a_ = (unsigned long long)(a), b_ = (unsigned long long)(b); \
    if (a_ != b_) { fprintf(stderr, "FAIL %s:%d: %s=%llu expected %llu\n", __func__, __LINE__, #a, a_, b_); exit(1); } } while (0)

#define MAX_BLOCK 4096u
#define ENTRIES 16u
#define LUN_BLOCKS UINT64_C(1000000)
#define FIRST_USABLE 34u
#define LAST_USABLE (LUN_BLOCKS - 34u)

static uint8_t H[MAX_BLOCK], E[ENTRIES * UFS_GPT_ENTRY_BYTES];
static struct ufs_gpt_disk D;
static struct ufs_gpt_extent X;
static uint32_t entry_count = ENTRIES;

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static void put64(uint8_t *p, uint64_t v) { put32(p, (uint32_t)v); put32(p + 4, (uint32_t)(v >> 32)); }

static void seal_entries(void) { put32(H + 88, ufs_gpt_crc32(E, (size_t)entry_count * UFS_GPT_ENTRY_BYTES)); }

static void seal(void)
{
    uint8_t copy[UFS_GPT_HEADER_BYTES];
    seal_entries();
    memcpy(copy, H, sizeof copy);
    memset(copy + 16, 0, 4);
    put32(H + 16, ufs_gpt_crc32(copy, sizeof copy));
}

static void entry(unsigned index, const char *name, uint64_t first, uint64_t last)
{
    uint8_t *e = E + index * UFS_GPT_ENTRY_BYTES;
    size_t i;
    memset(e, 0, UFS_GPT_ENTRY_BYTES);
    e[0] = 0xA5; e[16] = (uint8_t)(index + 1);
    put64(e + 32, first); put64(e + 40, last);
    for (i = 0; name[i]; ++i) e[56 + 2 * i] = (uint8_t)name[i];
}

static void build(uint32_t block)
{
    memset(H, 0, sizeof H); memset(E, 0, sizeof E);
    entry_count = ENTRIES;
    D.block_bytes = block; D.lun_blocks = LUN_BLOCKS;
    memcpy(H, "EFI PART", 8);
    put32(H + 8, 0x00010000); put32(H + 12, UFS_GPT_HEADER_BYTES);
    put64(H + 24, 1); put64(H + 32, LUN_BLOCKS - 1);
    put64(H + 40, FIRST_USABLE); put64(H + 48, LAST_USABLE);
    put64(H + 72, 2); put32(H + 80, ENTRIES); put32(H + 84, UFS_GPT_ENTRY_BYTES);
    entry(0, "boot", 100, 199);
    entry(1, "userdata", 1000, 900000);
    entry(2, "vendor_a", 200, 299);
    seal();
}

static uint32_t find(const char *name) { return ufs_gpt_find(H, D.block_bytes, E, (size_t)entry_count * UFS_GPT_ENTRY_BYTES, &D, name, &X); }

static void test_crc_vector(void)
{
    CHECK_EQ(ufs_gpt_crc32((const uint8_t *)"123456789", 9), 0xCBF43926u);
    CHECK_EQ(ufs_gpt_crc32((const uint8_t *)"", 0), 0);
}

static void test_valid_table(void)
{
    uint32_t blocks[] = {512, 4096};
    unsigned i;
    for (i = 0; i < 2; ++i) {
        build(blocks[i]);
        CHECK_EQ(find("boot"), UFS_GPT_OK);
        CHECK_EQ(X.first_block, 100); CHECK_EQ(X.blocks, 100);
        CHECK_EQ(find("vendor_a"), UFS_GPT_OK);
        CHECK_EQ(X.first_block, 200); CHECK_EQ(X.blocks, 100);
        CHECK_EQ(find("BOOT"), UFS_GPT_NOT_FOUND);
        CHECK_EQ(find("boot2"), UFS_GPT_NOT_FOUND);
        CHECK_EQ(find("boo"), UFS_GPT_NOT_FOUND);
    }
    /* A single-block partition and one ending at the last usable block. */
    build(4096); entry(3, "one", 300, 300); entry(4, "end", LAST_USABLE, LAST_USABLE); seal();
    CHECK_EQ(find("one"), UFS_GPT_OK); CHECK_EQ(X.blocks, 1);
    CHECK_EQ(find("end"), UFS_GPT_OK); CHECK_EQ(X.first_block, LAST_USABLE);
}

static void test_userdata_refused(void)
{
    build(4096);
    CHECK_EQ(find("userdata"), UFS_GPT_REFUSED); CHECK_EQ(X.blocks, 0);
    CHECK_EQ(find("USERDATA"), UFS_GPT_REFUSED);
    CHECK_EQ(find("UserData"), UFS_GPT_REFUSED);
    CHECK_EQ(find("userdata2"), UFS_GPT_NOT_FOUND);
}

static void test_arguments(void)
{
    char long_name[UFS_GPT_NAME_CHARS + 2];
    struct ufs_gpt_disk bad;
    build(4096);
    CHECK_EQ(ufs_gpt_find(NULL, 4096, E, sizeof E, &D, "boot", &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4096, NULL, sizeof E, &D, "boot", &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4096, E, sizeof E, NULL, "boot", &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4096, E, sizeof E, &D, NULL, &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4096, E, sizeof E, &D, "boot", NULL), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4095, E, sizeof E, &D, "boot", &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4096, E, sizeof E - 1, &D, "boot", &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(ufs_gpt_find(H, 4096, E, sizeof E + 128, &D, "boot", &X), UFS_GPT_ARGUMENT);
    CHECK_EQ(find(""), UFS_GPT_ARGUMENT);
    CHECK_EQ(find("caf\xC3\xA9"), UFS_GPT_ARGUMENT);
    memset(long_name, 'a', sizeof long_name - 1); long_name[sizeof long_name - 1] = 0;
    CHECK_EQ(find(long_name), UFS_GPT_ARGUMENT);
    long_name[UFS_GPT_NAME_CHARS] = 0; /* 36 characters is the longest legal name. */
    CHECK_EQ(find(long_name), UFS_GPT_NOT_FOUND);
    bad = D; bad.block_bytes = 2048;
    CHECK_EQ(ufs_gpt_find(H, 2048, E, sizeof E, &bad, "boot", &X), UFS_GPT_ARGUMENT);
    bad = D; bad.lun_blocks = 0;
    CHECK_EQ(ufs_gpt_find(H, 4096, E, sizeof E, &bad, "boot", &X), UFS_GPT_ARGUMENT);
}

static void test_failure_zeroes_output(void)
{
    build(4096);
    CHECK_EQ(find("boot"), UFS_GPT_OK);
    CHECK(X.blocks != 0);
    H[0] = 'X'; seal();
    CHECK_EQ(find("boot"), UFS_GPT_SIGNATURE);
    CHECK_EQ(X.first_block, 0); CHECK_EQ(X.blocks, 0);
}

static void test_header_rules(void)
{
    unsigned i;
    for (i = 0; i < 8; ++i) { build(4096); H[i] ^= 1; seal(); CHECK_EQ(find("boot"), UFS_GPT_SIGNATURE); }
    build(4096); put32(H + 8, 0x00010001); seal(); CHECK_EQ(find("boot"), UFS_GPT_HEADER);
    build(4096); put32(H + 12, 96); seal(); CHECK_EQ(find("boot"), UFS_GPT_HEADER);
    build(4096); put32(H + 20, 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_HEADER);
    build(4096); H[92] = 1; seal(); CHECK_EQ(find("boot"), UFS_GPT_HEADER);
    build(4096); H[4095] = 1; seal(); CHECK_EQ(find("boot"), UFS_GPT_HEADER);
    build(512); H[511] = 1; seal(); CHECK_EQ(find("boot"), UFS_GPT_HEADER);
    /* A byte past a 512-byte block is not part of the header. */
    build(512); H[512] = 1; seal(); CHECK_EQ(find("boot"), UFS_GPT_OK);
}

static void test_crc_rules(void)
{
    build(4096); H[16] ^= 1; CHECK_EQ(find("boot"), UFS_GPT_CRC);
    build(4096); H[40] ^= 1; CHECK_EQ(find("boot"), UFS_GPT_CRC); /* field changed, CRC not resealed */
    build(4096); E[0] ^= 1; CHECK_EQ(find("boot"), UFS_GPT_CRC);
    build(4096); E[sizeof E - 1] ^= 1; CHECK_EQ(find("boot"), UFS_GPT_CRC);
}

static void test_lba_rules(void)
{
    build(4096); put64(H + 24, 2); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); put64(H + 32, LUN_BLOCKS); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); put64(H + 32, 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    /* An empty table, so no partition can fail first and hide the inverted range. */
    build(4096); memset(E, 0, sizeof E); put64(H + 40, LAST_USABLE + 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); put64(H + 48, LUN_BLOCKS - 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS); /* reaches the backup */
    build(4096); put64(H + 72, 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); put64(H + 72, FIRST_USABLE); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    /* The array must end before the usable area. 16 entries take one 4K block. */
    build(4096); put64(H + 72, FIRST_USABLE - 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_OK);
    build(512); put64(H + 72, FIRST_USABLE - 3); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS); /* needs 4 blocks */
    build(512); put64(H + 72, FIRST_USABLE - 4); seal(); CHECK_EQ(find("boot"), UFS_GPT_OK);
    /* A partly used last block still occupies the whole block: 15 entries need 4 of 512 bytes. */
    build(512); entry_count = 15; put32(H + 80, 15); put64(H + 72, FIRST_USABLE - 3); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(512); entry_count = 15; put32(H + 80, 15); put64(H + 72, FIRST_USABLE - 4); seal(); CHECK_EQ(find("boot"), UFS_GPT_OK);
    /* Values near UINT64_MAX fail without wrapping. */
    build(4096); put64(H + 48, UINT64_MAX); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); put64(H + 72, UINT64_MAX); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
}

static void test_entry_array_rules(void)
{
    build(4096); put32(H + 84, 256); seal(); CHECK_EQ(find("boot"), UFS_GPT_ENTRIES);
    build(4096); put32(H + 80, 0); seal(); CHECK_EQ(find("boot"), UFS_GPT_ENTRIES);
    build(4096); put32(H + 80, UFS_GPT_MAX_ENTRIES + 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_ENTRIES);
    build(4096); put32(H + 80, ENTRIES - 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_ARGUMENT); /* buffer must match */
    /* An unused entry must be entirely zero. */
    build(4096); E[3 * UFS_GPT_ENTRY_BYTES + 40] = 1; seal(); CHECK_EQ(find("boot"), UFS_GPT_ENTRIES);
}

static void test_partition_rules(void)
{
    build(4096); entry(3, "bad", 400, 399); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); entry(3, "low", FIRST_USABLE - 1, 40); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); entry(3, "high", 950000, LAST_USABLE + 1); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    build(4096); entry(3, "wrap", UINT64_MAX, UINT64_MAX); seal(); CHECK_EQ(find("boot"), UFS_GPT_BOUNDS);
    /* Overlap: inside, straddling each end, and identical. */
    build(4096); entry(3, "inner", 150, 160); seal(); CHECK_EQ(find("boot"), UFS_GPT_OVERLAP);
    build(4096); entry(3, "left", 50, 100); seal(); CHECK_EQ(find("boot"), UFS_GPT_OVERLAP);
    build(4096); entry(3, "right", 199, 199); seal(); CHECK_EQ(find("boot"), UFS_GPT_OVERLAP); /* shares only boot's last block */
    build(4096); entry(3, "same", 100, 199); seal(); CHECK_EQ(find("boot"), UFS_GPT_OVERLAP);
    /* Touching ranges are not overlap. */
    build(4096); entry(3, "after", 300, 310); entry(4, "before", 40, 99); seal(); CHECK_EQ(find("after"), UFS_GPT_OK); CHECK_EQ(find("before"), UFS_GPT_OK);
    /* An overlap among other entries still fails a lookup of an innocent name. */
    build(4096); entry(3, "x", 300, 320); entry(4, "y", 310, 330); seal(); CHECK_EQ(find("boot"), UFS_GPT_OVERLAP);
}

static void test_names(void)
{
    uint8_t *e;
    char full[UFS_GPT_NAME_CHARS + 1];
    build(4096); entry(3, "boot", 300, 399); seal(); CHECK_EQ(find("boot"), UFS_GPT_AMBIGUOUS); CHECK_EQ(X.blocks, 0);
    /* A non-ASCII entry never matches, and does not break other lookups. */
    build(4096); entry(3, "dtbo", 300, 399); e = E + 3 * UFS_GPT_ENTRY_BYTES; e[57] = 0x04; seal();
    CHECK_EQ(find("dtbo"), UFS_GPT_NOT_FOUND); CHECK_EQ(find("boot"), UFS_GPT_OK);
    build(4096); entry(3, "dtbo", 300, 399); e = E + 3 * UFS_GPT_ENTRY_BYTES; e[56] = 0x80; seal();
    CHECK_EQ(find("dtbo"), UFS_GPT_NOT_FOUND);
    /* All 36 units in use, with no terminator. */
    memset(full, 'n', UFS_GPT_NAME_CHARS); full[UFS_GPT_NAME_CHARS] = 0;
    build(4096); entry(3, full, 300, 399); seal();
    CHECK_EQ(find(full), UFS_GPT_OK); CHECK_EQ(X.first_block, 300);
    /* Unused entries are skipped, so a zero name cannot match. */
    build(4096); CHECK_EQ(find("vendor_b"), UFS_GPT_NOT_FOUND);
}

static void cdb_read(uint8_t *c, uint32_t lba, uint32_t blocks)
{
    memset(c, 0, 10); c[0] = 0x28;
    c[2] = (uint8_t)(lba >> 24); c[3] = (uint8_t)(lba >> 16); c[4] = (uint8_t)(lba >> 8); c[5] = (uint8_t)lba;
    c[7] = (uint8_t)(blocks >> 8); c[8] = (uint8_t)blocks;
}

/* The point of the parser: its extent becomes the bound the READ(10) admission enforces. */
static void test_extent_drives_read_admission(void)
{
    struct ufs_policy p;
    struct ufs_host h;
    uint8_t c[10];
    build(4096);
    CHECK_EQ(find("boot"), UFS_GPT_OK);
    memset(&p, 0, sizeof p);
    p.lun_blocks = D.lun_blocks; p.first_block = X.first_block; p.extent_blocks = X.blocks;
    p.ucd_dma = UINT64_C(0x123450001000); p.ucd_bytes = UFS_UCD_BYTES;
    p.data_dma = UINT64_C(0x123450002000); p.data_bytes = UFS_MAX_TRANSFER;
    p.block_bytes = D.block_bytes; p.epoch = 7;

    CHECK_EQ(ufs_host_init(&h, &p), UFS_OK);
    cdb_read(c, 100, 1);
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_OK);
    CHECK_EQ(ufs_host_cancel_prepared(&h, &h.token), UFS_OK);

    CHECK_EQ(ufs_host_init(&h, &p), UFS_OK);
    cdb_read(c, 199, 1); /* last block of the partition */
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_OK);
    CHECK_EQ(ufs_host_cancel_prepared(&h, &h.token), UFS_OK);

    CHECK_EQ(ufs_host_init(&h, &p), UFS_OK);
    cdb_read(c, 99, 1);
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_EXTENT);
    cdb_read(c, 200, 1);
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_EXTENT);
    cdb_read(c, 199, 2); /* crosses the end */
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 8192), UFS_EXTENT);

    /* A write is refused regardless of where it points. */
    memset(c, 0, 10); c[0] = 0x2A; c[5] = 100; c[8] = 1;
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_TO_DEVICE, 4096), UFS_WRITE_REJECTED);
    CHECK_EQ(ufs_host_prepare(&h, c, 10, UFS_FROM_DEVICE, 4096), UFS_COMMAND);
}

int main(void)
{
    static void (*const tests[])(void) = { test_crc_vector, test_valid_table, test_userdata_refused, test_arguments, test_failure_zeroes_output,
        test_header_rules, test_crc_rules, test_lba_rules, test_entry_array_rules, test_partition_rules, test_names, test_extent_drives_read_admission };
    size_t i, count = sizeof tests / sizeof tests[0];
    for (i = 0; i < count; ++i) tests[i]();
    printf("{\"outcome\":\"pass\",\"tests\":%zu}\n", count);
    return 0;
}
