// Unsupported complete-object virtual-base encoding must fail explicitly.
struct Base { unsigned long long data; };
struct Virtual : virtual Base { void *pointer; };
const char *rejected = __builtin_xnu_type_signature(Virtual);
