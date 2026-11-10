#include "fdt.h"

#include <string.h>

#define FDT_MAGIC 0xd00dfeedu
#define FDT_BEGIN_NODE 1u
#define FDT_END_NODE 2u
#define FDT_PROP 3u
#define FDT_END 9u
#define HEADER_BYTES 40u
#define RSVMAP_BYTES 16u

static void put_be32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)v;
}

static void emit(struct fdt_w *w, const void *data, size_t len) {
    if (w->error) return;
    size_t padded = (len + 3u) & ~(size_t)3u;
    if (padded < len || padded > FDT_W_STRUCT_MAX - w->struct_len) {
        w->error = 1;
        return;
    }
    memcpy(w->structure + w->struct_len, data, len);
    memset(w->structure + w->struct_len + len, 0, padded - len);
    w->struct_len += padded;
}

static void emit32(struct fdt_w *w, uint32_t v) {
    uint8_t b[4];
    put_be32(b, v);
    emit(w, b, 4);
}

static uint32_t string_offset(struct fdt_w *w, const char *name) {
    size_t len = strlen(name) + 1;
    for (size_t at = 0; at < w->strings_len; at += strlen(w->strings + at) + 1)
        if (!strcmp(w->strings + at, name)) return (uint32_t)at;
    if (len > FDT_W_STRINGS_MAX - w->strings_len) {
        w->error = 1;
        return 0;
    }
    memcpy(w->strings + w->strings_len, name, len);
    w->strings_len += len;
    return (uint32_t)(w->strings_len - len);
}

void fdt_w_init(struct fdt_w *w) {
    memset(w, 0, sizeof *w);
}

void fdt_begin_node(struct fdt_w *w, const char *name) {
    if (w->depth >= FDT_W_DEPTH_MAX) {
        w->error = 1;
        return;
    }
    emit32(w, FDT_BEGIN_NODE);
    emit(w, name, strlen(name) + 1);
    w->depth++;
}

void fdt_end_node(struct fdt_w *w) {
    if (w->depth <= 0) {
        w->error = 1;
        return;
    }
    emit32(w, FDT_END_NODE);
    w->depth--;
}

void fdt_prop(struct fdt_w *w, const char *name, const void *data, size_t len) {
    if (w->depth <= 0 || len > UINT32_MAX) {
        w->error = 1;
        return;
    }
    uint32_t offset = string_offset(w, name);
    emit32(w, FDT_PROP);
    emit32(w, (uint32_t)len);
    emit32(w, offset);
    if (len) emit(w, data, len);
}

void fdt_prop_cells(struct fdt_w *w, const char *name, const uint32_t *cells, size_t count) {
    uint8_t buf[256];
    if (count > sizeof buf / 4) {
        w->error = 1;
        return;
    }
    for (size_t i = 0; i < count; i++) put_be32(buf + 4 * i, cells[i]);
    fdt_prop(w, name, buf, 4 * count);
}

void fdt_prop_u32(struct fdt_w *w, const char *name, uint32_t value) {
    fdt_prop_cells(w, name, &value, 1);
}

void fdt_prop_u64(struct fdt_w *w, const char *name, uint64_t value) {
    uint32_t cells[2] = {(uint32_t)(value >> 32), (uint32_t)value};
    fdt_prop_cells(w, name, cells, 2);
}

void fdt_prop_str(struct fdt_w *w, const char *name, const char *value) {
    fdt_prop(w, name, value, strlen(value) + 1);
}

void fdt_prop_empty(struct fdt_w *w, const char *name) {
    fdt_prop(w, name, NULL, 0);
}

size_t fdt_finish(struct fdt_w *w, uint8_t *out, size_t out_len) {
    if (w->depth != 0) w->error = 1;
    emit32(w, FDT_END);
    if (w->error) return 0;
    size_t off_struct = HEADER_BYTES + RSVMAP_BYTES;
    size_t off_strings = off_struct + w->struct_len;
    size_t total = off_strings + w->strings_len;
    if (total > out_len || total > UINT32_MAX) return 0;
    memset(out, 0, total);
    put_be32(out + 0, FDT_MAGIC);
    put_be32(out + 4, (uint32_t)total);
    put_be32(out + 8, (uint32_t)off_struct);
    put_be32(out + 12, (uint32_t)off_strings);
    put_be32(out + 16, HEADER_BYTES);
    put_be32(out + 20, 17);
    put_be32(out + 24, 16);
    put_be32(out + 28, 0);
    put_be32(out + 32, (uint32_t)w->strings_len);
    put_be32(out + 36, (uint32_t)w->struct_len);
    memcpy(out + off_struct, w->structure, w->struct_len);
    memcpy(out + off_strings, w->strings, w->strings_len);
    return total;
}
