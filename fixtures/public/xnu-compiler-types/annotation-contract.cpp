// Scalar semantics override must affect actual compiler layout analysis.
typedef unsigned long long Address __attribute__((xnu_usage_semantics("pointer")));
typedef void *UserPointer __attribute__((xnu_usage_semantics("data")));
struct Annotated { Address address; UserPointer user; };
static_assert(__has_attribute(xnu_usage_semantics));
static_assert(__builtin_strcmp(__builtin_xnu_type_signature(Annotated), "12")==0);
static_assert((__builtin_xnu_type_summary(Annotated)&0xffff)==6);
