// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Ordinary language/CodeGen controls compile on independent stock Clang19.
struct Service { virtual int virtualTrap(); int trap(); };
using Method = int (Service::*)();
struct Trap { Service *object; Method function; };
struct Referenced { char &small; int &integer; };
struct Incomplete;
struct IncompleteReference { Incomplete &value; };
struct RvalueReference { int &&value; };
struct __attribute__((packed)) PackedReference { char tag; int &value; };
struct Left { int left; };
struct Right { int right; int adjust(); };
struct Multiple : Left, Right {};
using AdjustedMethod = int (Multiple::*)();
static_assert(sizeof(char&)==1 && sizeof(int&)==4);
static_assert(sizeof(Referenced)==16 && alignof(Referenced)==8);
static_assert(__builtin_offsetof(Referenced,integer)==8);
static_assert(sizeof(Method)==16 && alignof(Method)==8);
static_assert(sizeof(Trap)==24 && __builtin_offsetof(Trap,function)==8);
static_assert(sizeof(IncompleteReference)==8 && sizeof(RvalueReference)==8);
static_assert(sizeof(PackedReference)==9 && __builtin_offsetof(PackedReference,value)==1);
extern "C" {
extern __attribute__((used)) const unsigned long long storage_layout[] = {
 sizeof(char&),sizeof(int&),sizeof(Referenced),alignof(Referenced),
 __builtin_offsetof(Referenced,integer),sizeof(Method),alignof(Method),
 sizeof(Trap),__builtin_offsetof(Trap,function),sizeof(IncompleteReference),
 sizeof(RvalueReference),sizeof(PackedReference),__builtin_offsetof(PackedReference,value)
};
__attribute__((used,section("__DATA_CONST,__s24store"))) Method null_method = nullptr;
__attribute__((used,section("__DATA_CONST,__s24store"))) Method direct_method = &Service::trap;
__attribute__((used,section("__DATA_CONST,__s24store"))) Method virtual_method = &Service::virtualTrap;
__attribute__((used,section("__DATA_CONST,__s24store"))) AdjustedMethod adjusted_method = &Right::adjust;
int call_method(Service *s, Method m) { return (s->*m)(); }
char *reference_address(Referenced *r) { return &r->small; }
}
