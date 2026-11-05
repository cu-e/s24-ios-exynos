#include "readonly.h"
static_assert(sizeof(uint64_t)==8 && sizeof(uint32_t)==4 && sizeof(uint16_t)==2);
static_assert(S24R_HEADER_BYTES==40 && S24R_MAX_TRANSFER==65536);
static_assert(sizeof(((s24r_view*)0)->length)==4);
extern "C" const unsigned long long s24r_layout[] = {
    sizeof(s24r_geometry),sizeof(s24r_server),sizeof(s24r_client),sizeof(s24r_view),
    __builtin_offsetof(s24r_geometry,bytes),__builtin_offsetof(s24r_geometry,block_bytes)
};
