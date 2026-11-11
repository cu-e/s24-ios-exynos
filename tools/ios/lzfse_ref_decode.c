/* SPDX-License-Identifier: BSD-3-Clause
 * IOS-002 test oracle: decode a raw LZFSE stream with the pinned reference decoder (references/lzfse, e634ca58...).
 * Build (no upstream Makefile/CMake):  cc -O2 -Ireferences/lzfse/src tools/ios/lzfse_ref_decode.c references/lzfse/src/lzfse_decode.c \
 *     references/lzfse/src/lzfse_decode_base.c references/lzfse/src/lzfse_fse.c references/lzfse/src/lzvn_decode_base.c -o artifacts/ios-tools/lzfse_ref_decode
 * Usage: lzfse_ref_decode IN OUT OUT_CAPACITY_BYTES ; exit 0 and prints the decoded size, or exit 1. Host-only helper; the project's decoder is tools/ios/lzfse_py.py. */
#include <stdio.h>
#include <stdlib.h>
#include "lzfse.h"

int main(int argc, char **argv) {
    if (argc != 4) { fprintf(stderr, "usage: %s IN OUT CAPACITY\n", argv[0]); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open in"); return 2; }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    unsigned char *in = malloc(n);
    if (!in || fread(in, 1, n, f) != (size_t)n) { fprintf(stderr, "read failed\n"); return 2; }
    fclose(f);
    size_t cap = strtoull(argv[3], 0, 10);
    unsigned char *out = malloc(cap);
    if (!out) { fprintf(stderr, "alloc failed\n"); return 2; }
    size_t got = lzfse_decode_buffer(out, cap, in, n, NULL);
    if (got == 0 || got == cap) { fprintf(stderr, "decode failed or output filled the buffer (got %zu)\n", got); return 1; }
    FILE *o = fopen(argv[2], "wb");
    if (!o || fwrite(out, 1, got, o) != got) { fprintf(stderr, "write failed\n"); return 2; }
    fclose(o);
    printf("%zu\n", got);
    return 0;
}
