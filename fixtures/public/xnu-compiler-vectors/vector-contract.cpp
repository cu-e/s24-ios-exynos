// Public granule expectations and actual target sizes; no SDK/private oracle.
typedef unsigned long long V64x2 __attribute__((ext_vector_type(2)));
typedef unsigned long long V64x3 __attribute__((ext_vector_type(3)));
typedef unsigned int V32x4 __attribute__((ext_vector_type(4)));
typedef unsigned long long Generic64 __attribute__((vector_size(16)));
typedef float VF32x3 __attribute__((ext_vector_type(3)));
struct VectorPointer { V64x2 lanes; void *pointer; };
struct PointerVector { void *pointer; V64x2 lanes; };
struct __attribute__((packed)) PackedVector { unsigned char tag; V64x2 lanes; void *pointer; };
union VectorUnion { V64x2 lanes; void *pointer; };
struct VectorArray { V64x3 lanes[2]; };
static_assert(sizeof(V64x3)==32 && sizeof(VectorPointer)==32);
static_assert(__builtin_xnu_type_summary(V64x2)==4 && __builtin_xnu_type_summary(V32x4)==4);
static_assert(__builtin_xnu_type_summary(Generic64)==4 && __builtin_xnu_type_summary(VF32x3)==4);
static_assert(__builtin_xnu_type_summary(V64x3)==5);
static_assert(__builtin_xnu_type_signature(V64x3)[0]=='2' && __builtin_xnu_type_signature(V64x3)[2]=='2');
static_assert(__builtin_xnu_type_signature(V64x3)[3]=='0');
static_assert(__builtin_xnu_type_summary(VectorPointer)==7 && __builtin_xnu_type_summary(PointerVector)==7);
static_assert(__builtin_xnu_type_signature(VectorPointer)[0]=='2' && __builtin_xnu_type_signature(VectorPointer)[2]=='1');
static_assert(__builtin_xnu_type_signature(VectorPointer)[3]=='0');
static_assert(__builtin_xnu_type_signature(PointerVector)[0]=='1' && __builtin_xnu_type_signature(PointerVector)[1]=='0');
static_assert(__builtin_xnu_type_summary(PackedVector)==14);
static_assert(__builtin_xnu_type_signature(PackedVector)[0]=='2' && __builtin_xnu_type_signature(PackedVector)[1]=='2');
static_assert(__builtin_xnu_type_signature(PackedVector)[2]=='3' && __builtin_xnu_type_signature(PackedVector)[3]=='1');
static_assert(__builtin_xnu_type_summary(VectorUnion)==12);
static_assert(__builtin_xnu_type_summary(VectorArray)==5);
static_assert(__builtin_xnu_type_signature(VectorArray)[3]=='0' && __builtin_xnu_type_signature(VectorArray)[7]=='0');
static_assert(__builtin_xnu_types_compatible(V64x2,Generic64));
static_assert(!__builtin_xnu_types_compatible(VectorPointer,PointerVector));
template<class T> struct VectorMetadata { static constexpr auto value=__builtin_xnu_type_summary(T); };
static_assert(VectorMetadata<V64x3>::value==5);
template<class T> auto vector_symbol(T*) -> decltype((__builtin_xnu_type_summary(T),0)) { return 29; }
template int vector_symbol<V64x3>(V64x3*);
unsigned vector_contract() { return __builtin_xnu_type_summary(VectorPointer); }

typedef unsigned long long NativeNeon64 __attribute__((neon_vector_type(2)));
static_assert(sizeof(NativeNeon64)==16 && __builtin_xnu_type_summary(NativeNeon64)==4);
static_assert(__builtin_xnu_type_signature(NativeNeon64)[0]=='2' && __builtin_xnu_type_signature(NativeNeon64)[1]=='2');
