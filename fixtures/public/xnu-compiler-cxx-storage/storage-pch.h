// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
struct PchService { int method(); };
struct PchStorage { char &reference; int (PchService::*method)(); };
template<class T> struct StoredMetadata {
 static constexpr auto value=__builtin_xnu_type_summary(T);
 static constexpr auto signature=__builtin_xnu_type_signature(T);
};
static_assert(sizeof(PchStorage)==24 && StoredMetadata<PchStorage>::value==6);
static_assert(StoredMetadata<PchStorage>::signature[0]=='1' && StoredMetadata<PchStorage>::signature[1]=='2' && StoredMetadata<PchStorage>::signature[2]=='2');
template<class T> auto stored_symbol(T*) -> decltype((__builtin_xnu_type_summary(T),0)) { return 43; }
template int stored_symbol<PchStorage>(PchStorage*);
extern unsigned external_storage_one();
unsigned storage_contract() { return external_storage_one()+StoredMetadata<PchStorage>::value; }
