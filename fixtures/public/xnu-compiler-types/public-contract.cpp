// Owned expectations derived from selected XNU8796 kern/kalloc.h granules.
// Compile-time public-contract controls, not an exact Apple compiler oracle.
struct Data { unsigned long long word; };
struct Pointer { void *pointer; };
struct Mixed { void *pointer; unsigned long long word; };
struct Same { const char *pointer; signed long word; };
struct Padded { alignas(32) unsigned char byte; };
struct Array { void *pointer[2]; };
union Overlap { void *pointer; unsigned long long word; };
static_assert(sizeof(void *) == 8 && sizeof(long) == 8);
#define SIG(T, S) static_assert(__builtin_strcmp(__builtin_xnu_type_signature(T), S)==0)
SIG(Data, "2"); SIG(Pointer, "1"); SIG(Mixed, "12");
SIG(Padded, "2000"); SIG(Array, "11"); SIG(Overlap, "3");
static_assert((__builtin_xnu_type_summary(Data) & 0xffff)==4);
static_assert((__builtin_xnu_type_summary(Pointer) & 0xffff)==2);
static_assert((__builtin_xnu_type_summary(Mixed) & 0xffff)==6);
static_assert((__builtin_xnu_type_summary(Padded) & 0xffff)==5);
static_assert((__builtin_xnu_type_summary(Overlap) & 0xffff)==8);
static_assert(__builtin_xnu_types_compatible(Mixed, Same));
static_assert(!__builtin_xnu_types_compatible(Data, Pointer));
static_assert(!__builtin_xnu_types_compatible(Pointer, void));
static_assert(__builtin_xnu_types_compatible(void, void));
