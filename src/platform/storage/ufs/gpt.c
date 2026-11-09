/* Project-authored strict GPT admission; see gpt.h. Layout follows UEFI 2.x chapter 5. */
#include "gpt.h"

#define REVISION UINT32_C(0x00010000)
#define NAME_OFFSET 56u

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t get64(const uint8_t *p)
{
    return (uint64_t)get32(p) | ((uint64_t)get32(p + 4) << 32);
}

static uint32_t crc_update(uint32_t crc, uint8_t byte)
{
    unsigned i;
    crc ^= byte;
    for (i = 0; i < 8; ++i) crc = (crc >> 1) ^ (UINT32_C(0xEDB88320) & (0u - (crc & 1u)));
    return crc;
}

uint32_t ufs_gpt_crc32(const uint8_t *p, size_t n)
{
    uint32_t crc = UINT32_C(0xFFFFFFFF);
    size_t i;
    for (i = 0; i < n; ++i) crc = crc_update(crc, p[i]);
    return ~crc;
}

static int all_zero(const uint8_t *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; ++i) if (p[i]) return 0;
    return 1;
}

static uint32_t header_crc(const uint8_t *h)
{
    uint32_t crc = UINT32_C(0xFFFFFFFF);
    size_t i;
    /* The stored CRC field counts as zero. */
    for (i = 0; i < UFS_GPT_HEADER_BYTES; ++i) crc = crc_update(crc, (i >= 16 && i < 20) ? 0 : h[i]);
    return ~crc;
}

/* One byte per unit, or 0 for an empty name or any unit above 0xFF. Requested names are
 * ASCII only, so a byte above 0x7F here can never match. Unused entries are all zero. */
static size_t entry_name(const uint8_t *entry, char *out)
{
    size_t i;
    for (i = 0; i < UFS_GPT_NAME_CHARS; ++i) {
        const uint8_t *unit = entry + NAME_OFFSET + 2u * i;
        if (unit[1]) return 0;
        if (!unit[0]) return i;
        out[i] = (char)unit[0];
    }
    return i;
}

static char lower(char c)
{
    return (c >= 'A' && c <= 'Z') ? (char)(c + ('a' - 'A')) : c;
}

static int same_text(const char *a, size_t a_length, const char *b, size_t b_length, int fold)
{
    size_t i;
    if (a_length != b_length) return 0;
    for (i = 0; i < a_length; ++i) if (fold ? lower(a[i]) != lower(b[i]) : a[i] != b[i]) return 0;
    return 1;
}

static uint32_t validate_header(const uint8_t *h, size_t bytes, const struct ufs_gpt_disk *disk, size_t entries_bytes)
{
    uint64_t alternate, first_usable, last_usable, entries_lba, array_blocks, array_bytes;
    uint32_t count, size;
    if (bytes != disk->block_bytes) return UFS_GPT_ARGUMENT;
    if (h[0] != 'E' || h[1] != 'F' || h[2] != 'I' || h[3] != ' ' || h[4] != 'P' || h[5] != 'A' || h[6] != 'R' || h[7] != 'T') return UFS_GPT_SIGNATURE;
    if (get32(h + 8) != REVISION || get32(h + 12) != UFS_GPT_HEADER_BYTES || get32(h + 20)) return UFS_GPT_HEADER;
    if (!all_zero(h + UFS_GPT_HEADER_BYTES, bytes - UFS_GPT_HEADER_BYTES)) return UFS_GPT_HEADER;
    if (header_crc(h) != get32(h + 16)) return UFS_GPT_CRC;

    alternate = get64(h + 32); first_usable = get64(h + 40); last_usable = get64(h + 48);
    entries_lba = get64(h + 72); count = get32(h + 80); size = get32(h + 84);
    if (get64(h + 24) != 1) return UFS_GPT_BOUNDS;
    if (alternate >= disk->lun_blocks) return UFS_GPT_BOUNDS;
    if (first_usable > last_usable || last_usable >= alternate) return UFS_GPT_BOUNDS;
    if (entries_lba < 2 || entries_lba >= first_usable) return UFS_GPT_BOUNDS;

    if (size != UFS_GPT_ENTRY_BYTES || !count || count > UFS_GPT_MAX_ENTRIES) return UFS_GPT_ENTRIES;
    array_bytes = (uint64_t)count * size;
    if (entries_bytes != array_bytes) return UFS_GPT_ARGUMENT;
    array_blocks = array_bytes / disk->block_bytes + (array_bytes % disk->block_bytes != 0);
    /* entries_lba < first_usable above, so this subtraction cannot wrap. */
    if (array_blocks > first_usable - entries_lba) return UFS_GPT_BOUNDS;
    return UFS_GPT_OK;
}

static uint32_t validate_entries(const uint8_t *h, const uint8_t *entries)
{
    uint32_t count = get32(h + 80), i, j;
    uint64_t first_usable = get64(h + 40), last_usable = get64(h + 48);
    if (ufs_gpt_crc32(entries, (size_t)count * UFS_GPT_ENTRY_BYTES) != get32(h + 88)) return UFS_GPT_CRC;
    for (i = 0; i < count; ++i) {
        const uint8_t *e = entries + (size_t)i * UFS_GPT_ENTRY_BYTES;
        uint64_t first = get64(e + 32), last = get64(e + 40);
        if (all_zero(e, 16)) {
            if (!all_zero(e, UFS_GPT_ENTRY_BYTES)) return UFS_GPT_ENTRIES;
            continue;
        }
        if (first > last || first < first_usable || last > last_usable) return UFS_GPT_BOUNDS;
        for (j = 0; j < i; ++j) {
            const uint8_t *o = entries + (size_t)j * UFS_GPT_ENTRY_BYTES;
            if (first <= get64(o + 40) && get64(o + 32) <= last) return UFS_GPT_OVERLAP;
        }
    }
    return UFS_GPT_OK;
}

uint32_t ufs_gpt_find(const uint8_t *header, size_t header_bytes, const uint8_t *entries, size_t entries_bytes,
    const struct ufs_gpt_disk *disk, const char *name, struct ufs_gpt_extent *out)
{
    static const char refused[] = "userdata";
    char candidate[UFS_GPT_NAME_CHARS];
    size_t wanted = 0;
    uint32_t i, count, result, matches = 0;
    uint64_t first = 0, last = 0;
    if (!out) return UFS_GPT_ARGUMENT;
    out->first_block = 0; out->blocks = 0;
    if (!header || !entries || !disk || !name) return UFS_GPT_ARGUMENT;
    if (disk->block_bytes != 512 && disk->block_bytes != 4096) return UFS_GPT_ARGUMENT;
    if (!disk->lun_blocks) return UFS_GPT_ARGUMENT;
    while (wanted <= UFS_GPT_NAME_CHARS && name[wanted]) {
        if ((unsigned char)name[wanted] > 0x7Fu) return UFS_GPT_ARGUMENT;
        ++wanted;
    }
    if (!wanted || wanted > UFS_GPT_NAME_CHARS) return UFS_GPT_ARGUMENT;

    result = validate_header(header, header_bytes, disk, entries_bytes);
    if (result) return result;
    result = validate_entries(header, entries);
    if (result) return result;
    if (same_text(name, wanted, refused, sizeof refused - 1, 1)) return UFS_GPT_REFUSED;

    count = get32(header + 80);
    for (i = 0; i < count; ++i) {
        const uint8_t *e = entries + (size_t)i * UFS_GPT_ENTRY_BYTES;
        size_t length;
        length = entry_name(e, candidate);
        if (length && same_text(candidate, length, name, wanted, 0)) {
            ++matches;
            first = get64(e + 32);
            last = get64(e + 40);
        }
    }
    if (!matches) return UFS_GPT_NOT_FOUND;
    if (matches > 1) return UFS_GPT_AMBIGUOUS;
    out->first_block = first;
    out->blocks = last - first + 1;
    return UFS_GPT_OK;
}
