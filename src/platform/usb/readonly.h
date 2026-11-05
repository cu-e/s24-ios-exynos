/* Project-owned USB read-only transport boundary. No controller or device I/O. */
#ifndef S24_USB_READONLY_H
#define S24_USB_READONLY_H
#include <stddef.h>
#include <stdint.h>

#define S24R_HEADER_BYTES 40u
#define S24R_MAX_TRANSFER 65536u
#define S24R_VERSION 1u
#define S24R_READ 1u
#define S24R_REPLY 0x8001u

enum s24r_result {
    S24R_OK = 0, S24R_BAD_ARGUMENT, S24R_BAD_GEOMETRY, S24R_BAD_FRAME,
    S24R_UNSUPPORTED_OPERATION, S24R_RANGE, S24R_BUFFER_SMALL,
    S24R_DISCONNECTED, S24R_BUSY, S24R_STALE, S24R_BACKEND_ERROR,
    S24R_ID_EXHAUSTED
};
struct s24r_geometry { uint64_t bytes; uint32_t block_bytes, max_transfer; };
/* The backend must complete synchronously, write at most length bytes and
 * report the actual count. It may disconnect the server, but may not reenter
 * handle/connect. All other calls require a serialized single owner. */
typedef int (*s24r_read_fn)(void *context, uint64_t offset, uint8_t *output,
                          uint32_t length, uint32_t *actual);
struct s24r_server {
    struct s24r_geometry geometry;
    uint64_t session, last_session, last_request;
    s24r_read_fn read;
    void *context;
    uint32_t connected, inflight;
};
struct s24r_client {
    struct s24r_geometry geometry;
    uint64_t session, last_session, next_request, pending_request, pending_offset;
    uint32_t pending_length, connected, pending;
};
/* Reply data is borrowed from the caller's receive buffer, never retained. */
struct s24r_view { const uint8_t *data; uint64_t offset; uint32_t length; };
struct s24_usb_dma_window {
    uintptr_t cpu_start;
    uint64_t bus_start;
    size_t bytes;
    uint32_t address_bits;
};

#ifdef __cplusplus
extern "C" {
#endif
/* Zero-initialize state once. Reconnect needs an increasing nonzero session
 * id. Process restart/peer authentication and USB enumeration are external. */
enum s24r_result s24r_server_connect(struct s24r_server *,
    const struct s24r_geometry *, uint64_t session, s24r_read_fn, void *);
void s24r_server_disconnect(struct s24r_server *);
enum s24r_result s24r_server_handle(struct s24r_server *, const uint8_t *, size_t,
                                  uint8_t *, size_t, size_t *written);
enum s24r_result s24r_client_connect(struct s24r_client *,
    const struct s24r_geometry *, uint64_t session);
void s24r_client_disconnect(struct s24r_client *);
enum s24r_result s24r_client_request(struct s24r_client *, uint64_t lba,
    uint32_t block_count, uint8_t *, size_t);
enum s24r_result s24r_client_complete(struct s24r_client *, const uint8_t *,
                                    size_t, struct s24r_view *);
/* Arithmetic admission only: this does not create/validate an IOMMU mapping,
 * pin memory, synchronize caches or establish the actual DMA address width. */
enum s24r_result s24_usb_dma_slice(const struct s24_usb_dma_window *, uintptr_t,
                                 size_t, uint64_t *bus_address);
#ifdef __cplusplus
}
#endif
#endif
