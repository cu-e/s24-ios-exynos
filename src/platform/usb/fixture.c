#define _POSIX_C_SOURCE 200809L
#include "readonly.h"
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"check failed at line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
static const struct s24r_geometry geometry = { 131072, 512, 65536 };
static uint8_t response[S24R_HEADER_BYTES + S24R_MAX_TRANSFER];
static const uint8_t golden[S24R_HEADER_BYTES] = {
    'S','2','4','R',1,0,1,0,7,0,0,0,0,0,0,0,
    1,0,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,2,0,0,0,0,0,0
};
struct backend {
    unsigned calls, mode;
    int fd;
    struct s24r_server *server;
};
static int read_backend(void *context, uint64_t offset, uint8_t *out,
    uint32_t length, uint32_t *actual) {
    struct backend *b = context; ++b->calls;
    if (b->fd >= 0) {
        ssize_t got;
        if (offset > INT64_MAX) return -1;
        got = pread(b->fd, out, length, (off_t)offset);
        if (got < 0) return -1;
        *actual = (uint32_t)got;
    } else {
        for (uint32_t i = 0; i < length; ++i) out[i] = (uint8_t)((offset + i) % 251);
        *actual = length;
    }
    if (b->mode == 1) return -1;
    if (b->mode == 2) *actual = length - 1;
    if (b->mode == 3) {
        s24r_server_disconnect(b->server);
        CHECK(s24r_server_connect(b->server, &geometry, 8, read_backend, b) == S24R_BUSY);
    }
    if (b->mode == 4) *actual = length + 1;
    return 0;
}
static void initialize(struct s24r_server *s, struct s24r_client *c, struct backend *b) {
    memset(s,0,sizeof(*s)); memset(c,0,sizeof(*c)); memset(b,0,sizeof(*b));
    b->fd = -1; b->server = s;
    CHECK(s24r_server_connect(s,&geometry,7,read_backend,b) == S24R_OK);
    CHECK(s24r_client_connect(c,&geometry,7) == S24R_OK);
}
static void valid_roundtrip(void) {
    struct s24r_server s; struct s24r_client c; struct backend b; struct s24r_view view;
    uint8_t request[40]; size_t written = 99;
    initialize(&s,&c,&b);
    CHECK(s24r_client_request(&c,1,1,request,sizeof(request)) == S24R_OK);
    CHECK(memcmp(request,golden,40) == 0);
    CHECK(s24r_client_request(&c,2,1,request,sizeof(request)) == S24R_BUSY);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_OK);
    CHECK(written == 552 && b.calls == 1);
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_OK);
    CHECK(view.length == 512 && view.offset == 512 && view.data == response + 40);
    for (uint32_t i = 0; i < view.length; ++i) CHECK(view.data[i] == (uint8_t)((512+i)%251));
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_STALE);
    CHECK(view.data == NULL && view.length == 0);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_STALE);
    CHECK(b.calls == 1 && written == 0);
    CHECK(s24r_client_request(&c,128,128,request,40) == S24R_OK);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_OK);
    CHECK(written == sizeof(response));
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_OK && view.length == 65536);
    CHECK(s24r_server_handle(&s,golden,40,response,sizeof(response),&written) == S24R_STALE && b.calls == 2 && written == 0);
    CHECK(s24r_client_request(&c,255,1,request,40) == S24R_OK);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_OK);
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_OK && view.offset == 130560);
}
static void malformed(void) {
    struct s24r_server s; struct s24r_client c; struct backend b; uint8_t raw[42]; size_t written;
    initialize(&s,&c,&b);
    for (size_t n = 0; n < 40; ++n) {
        written = 123; CHECK(s24r_server_handle(&s,golden,n,response,sizeof(response),&written) == S24R_BAD_FRAME);
        CHECK(b.calls == 0 && written == 0);
    }
    memcpy(raw+1,golden,40);
    CHECK(s24r_server_handle(&s,raw+1,41,response,sizeof(response),&written) == S24R_BAD_FRAME);
    for (unsigned field = 0; field < 7; ++field) {
        memcpy(raw+1,golden,40);
        switch (field) {
        case 0: raw[1] = 'X'; break;
        case 1: raw[5] = 2; break;
        case 2: raw[7] = 2; break; /* unsupported/write-like opcode */
        case 3: raw[37] = 1; break;
        case 4: raw[33] = 0; raw[34] = 0; break;
        case 5: raw[25] = 1; break;
        default: memset(raw+25,255,8); break;
        }
        CHECK(s24r_server_handle(&s,raw+1,40,response,sizeof(response),&written) != S24R_OK);
        CHECK(b.calls == 0 && written == 0);
    }
    CHECK(s24r_server_handle(&s,golden,40,response,551,&written) == S24R_BUFFER_SMALL);
    CHECK(b.calls == 0);
    memcpy(raw+1,golden,40); /* unaligned but valid wire storage */
    CHECK(s24r_server_handle(&s,raw+1,40,response,sizeof(response),&written) == S24R_OK);
    CHECK(b.calls == 1 && written == 552);
}
static void ranges(void) {
    struct s24r_server s; struct s24r_client c; struct backend b;
    uint8_t request[40]; struct s24r_geometry bad;
    initialize(&s,&c,&b);
    CHECK(s24r_client_request(&c,UINT64_MAX,1,request,40) == S24R_RANGE);
    CHECK(s24r_client_request(&c,0,UINT32_MAX,request,40) == S24R_RANGE);
    CHECK(s24r_client_request(&c,0,0,request,40) == S24R_RANGE);
    CHECK(s24r_client_request(&c,256,1,request,40) == S24R_RANGE);
    CHECK(s24r_client_request(&c,255,2,request,40) == S24R_RANGE);
    CHECK(s24r_client_request(&c,0,129,request,40) == S24R_RANGE);
    CHECK(s24r_client_request(&c,0,1,request,39) == S24R_BUFFER_SMALL);
    c.next_request = UINT64_MAX;
    CHECK(s24r_client_request(&c,0,1,request,40) == S24R_ID_EXHAUSTED);
    CHECK(!c.pending && b.calls == 0);
    for (unsigned i = 0; i < 6; ++i) {
        struct s24r_client empty = {0}; bad = geometry;
        switch(i) {
        case 0: bad.block_bytes = 0; break;
        case 1: bad.block_bytes = 1025; break;
        case 2: bad.bytes--; break;
        case 3: bad.max_transfer = 65537; break;
        case 4: bad.max_transfer = 0; break;
        default: bad.bytes = 0; break;
        }
        CHECK(s24r_client_connect(&empty,&bad,1) == S24R_BAD_GEOMETRY);
    }
    {
        struct s24r_server huge = {0}; struct s24r_client huge_client = {0};
        struct s24r_geometry g = {UINT64_MAX-511,512,65536}; size_t written;
        b.server = &huge;
        CHECK(s24r_server_connect(&huge,&g,7,read_backend,&b)==S24R_OK);
        CHECK(s24r_client_connect(&huge_client,&g,7)==S24R_OK);
        CHECK(s24r_client_request(&huge_client,g.bytes/512,1,request,40)==S24R_RANGE);
        memcpy(request,golden,40); request[24]=0; request[25]=0xfe;
        for(unsigned i=26;i<32;++i)request[i]=0xff;
        CHECK(s24r_server_handle(&huge,request,40,response,sizeof(response),&written)==S24R_RANGE && b.calls==0 && written==0);
        CHECK(s24r_client_request(&huge_client,g.bytes/512-1,1,request,40)==S24R_OK);
        CHECK(s24r_server_handle(&huge,request,40,response,sizeof(response),&written)==S24R_OK && written==552);
    }
}
static void lifecycle(void) {
    struct s24r_server s; struct s24r_client c; struct backend b; struct s24r_view view;
    uint8_t request[40]; size_t written;
    for (unsigned mode = 1; mode < 5; ++mode) {
        initialize(&s,&c,&b); b.mode = mode;
        CHECK(s24r_client_request(&c,1,1,request,40) == S24R_OK);
        memset(response,0xa5,552);
        CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == (mode==3?S24R_DISCONNECTED:S24R_BACKEND_ERROR));
        CHECK(written == 0 && b.calls == 1 && s.inflight == 0);
        for (size_t i = 0; i < 552; ++i) CHECK(response[i] == 0);
    }
    initialize(&s,&c,&b);
    CHECK(s24r_client_request(&c,1,1,request,40) == S24R_OK);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_OK);
    s24r_client_disconnect(&c); s24r_server_disconnect(&s);
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_DISCONNECTED);
    CHECK(s24r_client_connect(&c,&geometry,7) == S24R_STALE);
    CHECK(s24r_server_connect(&s,&geometry,7,read_backend,&b) == S24R_STALE);
    CHECK(s24r_client_connect(&c,&geometry,8) == S24R_OK);
    CHECK(s24r_server_connect(&s,&geometry,8,read_backend,&b) == S24R_OK);
    CHECK(s24r_client_request(&c,1,1,request,40) == S24R_OK);
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_BAD_FRAME); /* old USB completion */
    CHECK(!c.connected && !c.pending && !view.data);
    CHECK(s24r_server_handle(&s,golden,40,response,sizeof(response),&written) == S24R_STALE);
    CHECK(s24r_client_connect(&c,&geometry,9) == S24R_OK);
    s24r_server_disconnect(&s);
    CHECK(s24r_server_connect(&s,&geometry,9,read_backend,&b) == S24R_OK);
    CHECK(s24r_client_request(&c,4,1,request,40) == S24R_OK);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_OK);
    CHECK(s24r_client_complete(&c,response,written,&view) == S24R_OK && view.offset == 2048);
}
static void response_errors(void) {
    for (unsigned field = 0; field < 8; ++field) {
        struct s24r_server s; struct s24r_client c; struct backend b; struct s24r_view v;
        uint8_t request[40]; size_t written;
        initialize(&s,&c,&b); CHECK(s24r_client_request(&c,1,1,request,40) == S24R_OK);
        CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written) == S24R_OK);
        switch(field) {
        case 0: response[8]++; break;
        case 1: response[16]++; break;
        case 2: response[24]++; break;
        case 3: response[32]++; break;
        case 4: response[36]++; break;
        case 5: written--; break;
        case 6: CHECK(response[7] == 0x80); response[7] = 0; break;
        default: written++; break;
        }
        CHECK(s24r_client_complete(&c,response,written,&v) == S24R_BAD_FRAME);
        CHECK(!c.pending && !c.connected && !v.data && !v.length);
    }
}
static void dma_ranges(void) {
    struct s24_usb_dma_window w = {0x100000,0x800000,4096,36}; uint64_t bus = 0xdead;
    CHECK(s24_usb_dma_slice(&w,0x100200,512,&bus) == S24R_OK && bus == 0x800200);
    CHECK(s24_usb_dma_slice(&w,0x0fffff,1,&bus) == S24R_RANGE);
    CHECK(s24_usb_dma_slice(&w,0x101000,1,&bus) == S24R_RANGE);
    CHECK(s24_usb_dma_slice(&w,0x100000,4097,&bus) == S24R_RANGE);
    CHECK(s24_usb_dma_slice(&w,0x100000,0,&bus) == S24R_BAD_ARGUMENT);
    w.bus_start = UINT64_C(1)<<36;
    CHECK(s24_usb_dma_slice(&w,0x100000,1,&bus) == S24R_RANGE);
    w.address_bits = 64; w.bus_start = UINT64_MAX-2;
    CHECK(s24_usb_dma_slice(&w,0x100000,1,&bus) == S24R_RANGE);
    w.bus_start = 0; w.cpu_start = UINTPTR_MAX-2;
    CHECK(s24_usb_dma_slice(&w,w.cpu_start,1,&bus) == S24R_RANGE);
    w.cpu_start = 0x100000; w.address_bits = 65;
    CHECK(s24_usb_dma_slice(&w,0x100000,1,&bus) == S24R_BAD_ARGUMENT);
    w.address_bits=64; w.bus_start=UINT64_MAX-3; w.bytes=4;
    CHECK(s24_usb_dma_slice(&w,0x100000,4,&bus)==S24R_OK && bus==UINT64_MAX-3);
}
static uint32_t random_word(uint32_t *state) {
    uint32_t x=*state; x ^= x<<13; x ^= x>>17; x ^= x<<5; return *state=x;
}
static void mutation_inputs(void) {
    uint32_t seed=0x31415926;
    for (unsigned i=0;i<20000;++i) {
        struct s24r_server s; struct s24r_client c; struct backend b; uint8_t packet[80]; size_t written=1;
        initialize(&s,&c,&b); memcpy(packet,golden,40);
        unsigned at=random_word(&seed)%40; packet[at]^=(uint8_t)((random_word(&seed)%255)+1);
        size_t length=random_word(&seed)%81;
        enum s24r_result result=s24r_server_handle(&s,packet,length,response,sizeof(response),&written);
        CHECK((result==S24R_OK && written>=552 && written<=sizeof(response) && b.calls==1) ||
              (result!=S24R_OK && written==0 && b.calls==0));
    }
}
static void actual_file(const char *path) {
    struct s24r_server s; struct s24r_client c; struct backend b; struct s24r_view view;
    uint8_t request[40]; size_t written;
    initialize(&s,&c,&b); b.fd=open(path,O_RDONLY);
    CHECK(b.fd>=0 && (fcntl(b.fd,F_GETFL)&O_ACCMODE)==O_RDONLY);
    CHECK(s24r_client_request(&c,1,1,request,40)==S24R_OK);
    CHECK(s24r_server_handle(&s,request,40,response,sizeof(response),&written)==S24R_OK);
    CHECK(s24r_client_complete(&c,response,written,&view)==S24R_OK);
    for(unsigned i=0;i<512;++i)CHECK(view.data[i]==(uint8_t)((512+i)%251));
    CHECK(close(b.fd)==0);
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    valid_roundtrip(); malformed(); ranges(); lifecycle(); response_errors(); dma_ranges(); mutation_inputs(); actual_file(argv[1]);
    printf("{\"outcome\":\"pass\",\"checks\":%u,\"mutation_inputs\":20000,\"readonly_file_read_bytes\":512,\"device_io\":false,\"golden_request_hex\":\"",checks);
    for(size_t i=0;i<40;++i)printf("%02x",golden[i]);
    puts("\"}"); return 0;
}
