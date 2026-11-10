/* Minimal flattened device tree (FDT v17) writer for s24vmm. Fixed-size buffers, no allocation.
 * Any overflow or nesting error sets `error`; fdt_finish then fails and nothing partial is used. */
#ifndef S24VMM_FDT_H
#define S24VMM_FDT_H

#include <stddef.h>
#include <stdint.h>

#define FDT_W_STRUCT_MAX 16384
#define FDT_W_STRINGS_MAX 2048
#define FDT_W_DEPTH_MAX 8

struct fdt_w {
    uint8_t structure[FDT_W_STRUCT_MAX];
    char strings[FDT_W_STRINGS_MAX];
    size_t struct_len, strings_len;
    int depth;
    int error;
};

void fdt_w_init(struct fdt_w *w);
void fdt_begin_node(struct fdt_w *w, const char *name);
void fdt_end_node(struct fdt_w *w);
void fdt_prop(struct fdt_w *w, const char *name, const void *data, size_t len);
void fdt_prop_u32(struct fdt_w *w, const char *name, uint32_t value);
void fdt_prop_u64(struct fdt_w *w, const char *name, uint64_t value);
void fdt_prop_str(struct fdt_w *w, const char *name, const char *value);
/* Big-endian u32 cells from host values. */
void fdt_prop_cells(struct fdt_w *w, const char *name, const uint32_t *cells, size_t count);
void fdt_prop_empty(struct fdt_w *w, const char *name);
/* Writes the complete blob into out. Returns its size, or 0 on any error (including too small out). */
size_t fdt_finish(struct fdt_w *w, uint8_t *out, size_t out_len);

#endif
