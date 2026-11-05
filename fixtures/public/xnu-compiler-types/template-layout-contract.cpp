// Independent concrete ARM64 layout expectations plus dependent instantiation.
struct Base { unsigned char byte; };
struct Derived : Base { void *pointer; };
struct Poly { virtual void f(); unsigned long long data; };
struct __attribute__((packed)) Packed { unsigned char head[4]; void *pointer; };
struct Bits { unsigned first:32; unsigned second:32; };
static_assert(sizeof(Derived)==16 && __builtin_offsetof(Derived,pointer)==8);
static_assert(sizeof(Poly)==16);
static_assert(sizeof(Packed)==12 && __builtin_offsetof(Packed,pointer)==4);
static_assert(sizeof(Bits)==8);
template<class T> constexpr unsigned summary() {
    return __builtin_xnu_type_summary(T) & 0xffff;
}
template<class T> constexpr const char *signature() {
    return __builtin_xnu_type_signature(T);
}
static_assert(__builtin_strcmp(signature<Derived>(), "21")==0);
static_assert(__builtin_strcmp(signature<Poly>(), "12")==0);
static_assert(__builtin_strcmp(signature<Packed>(), "31")==0);
static_assert(__builtin_strcmp(signature<Bits>(), "2")==0);
static_assert(summary<Derived>()==6 && summary<Poly>()==6);
static_assert(summary<Packed>()==10 && summary<Bits>()==4);
