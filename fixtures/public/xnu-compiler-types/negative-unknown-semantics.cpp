// Unrecognized semantics must not silently become pointer or data.
typedef unsigned long long Bad __attribute__((xnu_usage_semantics("unknown")));
