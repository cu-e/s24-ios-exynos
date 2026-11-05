// Owned independent plain/atomic target-layout expectations, with no SDK.
#if !__has_builtin(__builtin_xnu_type_summary) || !__has_builtin(__builtin_xnu_type_signature)
#error S24_METADATA_API_MISSING
#endif
#ifdef S24_ATOMIC
typedef _Atomic(void *) Pointer;
typedef _Atomic(unsigned long long) Data;
#else
typedef void *Pointer;
typedef unsigned long long Data;
#endif
struct PointerBox { Pointer pointer; };
struct DataBox { Data value; };
_Static_assert(sizeof(struct PointerBox) == 8, "target pointer storage");
_Static_assert(sizeof(struct DataBox) == 8, "target data storage");
_Static_assert(__builtin_xnu_type_summary(struct PointerBox) == 2, "pointer granule");
_Static_assert(__builtin_xnu_type_summary(struct DataBox) == 4, "data granule");
const char *pointer_signature = __builtin_xnu_type_signature(struct PointerBox);
const char *data_signature = __builtin_xnu_type_signature(struct DataBox);
unsigned pointer_summary(void) { return __builtin_xnu_type_summary(struct PointerBox); }
unsigned data_summary(void) { return __builtin_xnu_type_summary(struct DataBox); }
