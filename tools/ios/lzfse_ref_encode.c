/* SPDX-License-Identifier: BSD-3-Clause
 * IOS-002 test-vector helper: encode a file with the pinned reference LZFSE encoder (references/lzfse, e634ca58...).
 * Build (no upstream Makefile/CMake):  cc -O2 -Ireferences/lzfse/src tools/ios/lzfse_ref_encode.c references/lzfse/src/lzfse_encode.c \
 *     references/lzfse/src/lzfse_encode_base.c references/lzfse/src/lzvn_encode_base.c references/lzfse/src/lzfse_decode.c \
 *     references/lzfse/src/lzfse_decode_base.c references/lzfse/src/lzfse_fse.c references/lzfse/src/lzvn_decode_base.c -o artifacts/ios-tools/lzfse_ref_encode
 * Usage: lzfse_ref_encode IN OUT ; exit 0 and prints the encoded size. Used only by tools/ios/lzfse_vectors.py --regenerate. */
#include <stdio.h>
#include <stdlib.h>
#include "lzfse.h"

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: %s IN OUT\n", argv[0]); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open in"); return 2; }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    unsigned char *in = malloc(n);
    if (!in || fread(in, 1, n, f) != (size_t)n) { fprintf(stderr, "read failed\n"); return 2; }
    fclose(f);
    size_t cap = (size_t)n + (size_t)n / 8 + 4096;
    unsigned char *out = malloc(cap);
    size_t got = lzfse_encode_buffer(out, cap, in, n, NULL);
    if (got == 0) { fprintf(stderr, "encode failed\n"); return 1; }
    FILE *o = fopen(argv[2], "wb");
    if (!o || fwrite(out, 1, got, o) != got) { fprintf(stderr, "write failed\n"); return 2; }
    fclose(o);
    printf("%zu\n", got);
    return 0;
}
