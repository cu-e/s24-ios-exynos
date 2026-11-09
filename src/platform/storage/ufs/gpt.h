/* Pure primary-GPT reader for the read-only UFS boundary. No I/O of any kind.
 *
 * The caller supplies bytes it already holds. A passing table shows those bytes
 * are a self-consistent GPT, not that they came from a particular device: the
 * caller must still qualify the source. The backup GPT is not examined.
 */
#ifndef S24_UFS_GPT_H
#define S24_UFS_GPT_H
#include <stddef.h>
#include <stdint.h>
#define UFS_GPT_HEADER_BYTES 92u
#define UFS_GPT_ENTRY_BYTES 128u
#define UFS_GPT_MAX_ENTRIES 256u
#define UFS_GPT_NAME_CHARS 36u
enum ufs_gpt_result {
    UFS_GPT_OK=0, UFS_GPT_ARGUMENT, UFS_GPT_SIGNATURE, UFS_GPT_HEADER, UFS_GPT_CRC,
    UFS_GPT_BOUNDS, UFS_GPT_ENTRIES, UFS_GPT_OVERLAP, UFS_GPT_NOT_FOUND,
    UFS_GPT_AMBIGUOUS, UFS_GPT_REFUSED
};
struct ufs_gpt_disk { uint64_t lun_blocks; uint32_t block_bytes; };
struct ufs_gpt_extent { uint64_t first_block, blocks; };
#ifdef __cplusplus
extern "C" {
#endif
uint32_t ufs_gpt_crc32(const uint8_t *, size_t);
/* header is exactly one block (LBA 1); entries is exactly the declared array.
 * The whole table is validated before any lookup. out is zeroed on failure.
 * Android userdata is always refused: it is not assumed to be readable. */
uint32_t ufs_gpt_find(const uint8_t *header, size_t header_bytes, const uint8_t *entries, size_t entries_bytes,
    const struct ufs_gpt_disk *disk, const char *name, struct ufs_gpt_extent *out);
#ifdef __cplusplus
}
#endif
#endif
