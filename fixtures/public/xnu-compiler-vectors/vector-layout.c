// Target layout expectations independent of the custom metadata implementation.
typedef unsigned long long U64x2 __attribute__((ext_vector_type(2)));
typedef unsigned long long U64x3 __attribute__((ext_vector_type(3)));
typedef float F32x3 __attribute__((ext_vector_type(3)));
typedef unsigned char U8x17 __attribute__((ext_vector_type(17)));
struct VectorThenPointer { U64x2 lanes; void *pointer; };
struct PointerThenVector { void *pointer; U64x2 lanes; };
struct __attribute__((packed)) PackedVector { unsigned char tag; U64x2 lanes; void *pointer; };
_Static_assert(sizeof(U64x2)==16 && _Alignof(U64x2)==16,"two lanes");
_Static_assert(sizeof(U64x3)==32 && _Alignof(U64x3)==16,"three lanes have tail padding");
_Static_assert(sizeof(F32x3)==16 && sizeof(U8x17)==32,"rounded vector storage");
_Static_assert(sizeof(struct VectorThenPointer)==32 && __builtin_offsetof(struct VectorThenPointer,pointer)==16,"vector and pointer offsets");
_Static_assert(sizeof(struct PointerThenVector)==32 && __builtin_offsetof(struct PointerThenVector,lanes)==16,"alignment gap");
_Static_assert(sizeof(struct PackedVector)==25 && __builtin_offsetof(struct PackedVector,lanes)==1,"packed vector layout");

typedef unsigned long long NativeNeon64 __attribute__((neon_vector_type(2)));
_Static_assert(sizeof(NativeNeon64)==16 && _Alignof(NativeNeon64)==16,"native NEON vector kind");
