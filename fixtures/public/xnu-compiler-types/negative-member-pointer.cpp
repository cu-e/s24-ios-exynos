// Unsupported target member-pointer representation must fail explicitly.
struct Record { int field; };
struct Member { int Record::*member; };
const char *rejected = __builtin_xnu_type_signature(Member);
