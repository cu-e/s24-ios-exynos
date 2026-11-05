// Real selected allocation macros must emit distinct usable metadata records.
#include <kern/kalloc.h>
struct S24Mixed { void *pointer; unsigned long long data; };
struct S24Data { unsigned long long data[2]; };
struct S24Pointers { void *pointer[2]; };
static_assert(sizeof(S24Mixed)==16 && sizeof(S24Data)==16 && sizeof(S24Pointers)==16);
extern "C" {
KALLOC_TYPE_DEFINE(s24_mixed_view, S24Mixed, KT_DEFAULT);
KALLOC_TYPE_DEFINE(s24_data_view, S24Data, KT_DEFAULT);
KALLOC_TYPE_DEFINE(s24_pointer_view, S24Pointers, KT_DEFAULT);
extern const unsigned long long s24_allocator_layout[] = {
    sizeof(kalloc_type_view),
    __builtin_offsetof(kalloc_type_view, kt_signature),
    __builtin_offsetof(kalloc_type_view, kt_flags),
    __builtin_offsetof(kalloc_type_view, kt_size),
};
}
