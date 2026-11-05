// Selected kalloc pointer compatibility uses a GNU typeof expression for void*.
static_assert(__is_same(__typeof__(*(void *)0), void));
template<class T> constexpr bool is_void_target(T *pointer) {
    return __is_same(__typeof__(*pointer), void);
}
static_assert(is_void_target((void *)0));
static_assert(!is_void_target((unsigned long long *)0));
