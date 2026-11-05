// Independent plain arm64 Darwin storage/offset expectations, no SDK.
struct ThreeBytes { unsigned char bytes[3]; };
struct ThreeWords { unsigned int words[3]; };
struct AtomicThenPointer { _Atomic(struct ThreeWords) value; void *pointer; };
struct __attribute__((packed)) PackedPointer { unsigned char marker; _Atomic(void *) pointer; };
_Static_assert(sizeof(void *) == 8 && sizeof(unsigned long long) == 8, "LP64 storage");
_Static_assert(sizeof(_Atomic(void *)) == 8 && _Alignof(_Atomic(void *)) == 8, "atomic pointer");
_Static_assert(sizeof(_Atomic(unsigned long long)) == 8, "atomic data");
_Static_assert(sizeof(struct ThreeBytes) == 3 && sizeof(_Atomic(struct ThreeBytes)) == 4, "promoted atomic bytes");
_Static_assert(_Alignof(_Atomic(struct ThreeBytes)) == 4, "atomic byte alignment");
_Static_assert(sizeof(struct ThreeWords) == 12 && sizeof(_Atomic(struct ThreeWords)) == 16, "promoted atomic words");
_Static_assert(_Alignof(_Atomic(struct ThreeWords)) == 16, "atomic word alignment");
_Static_assert(__builtin_offsetof(struct AtomicThenPointer, pointer) == 16, "storage stride");
_Static_assert(sizeof(struct AtomicThenPointer) == 32 && _Alignof(struct AtomicThenPointer) == 16, "outer padding");
_Static_assert(__builtin_offsetof(struct PackedPointer, pointer) == 1, "packed pointer offset");
_Static_assert(sizeof(struct PackedPointer) == 9 && _Alignof(struct PackedPointer) == 1, "packed storage");
unsigned independent_atomic_storage(void) { return sizeof(struct AtomicThenPointer); }
