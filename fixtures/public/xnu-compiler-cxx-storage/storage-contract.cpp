// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "storage-layout.cpp"
typedef unsigned long long Vector __attribute__((ext_vector_type(2)));
struct VectorReference { Vector &value; };
template<class T> struct StorageMetadata {
 static constexpr auto value = __builtin_xnu_type_summary(T);
 static constexpr auto signature = __builtin_xnu_type_signature(T);
};
static_assert(StorageMetadata<Referenced>::value==2);
static_assert(StorageMetadata<Referenced>::signature[0]=='1' && StorageMetadata<Referenced>::signature[1]=='1');
static_assert(StorageMetadata<Method>::value==4);
static_assert(StorageMetadata<Method>::signature[0]=='2' && StorageMetadata<Method>::signature[1]=='2');
static_assert(StorageMetadata<Trap>::value==6);
static_assert(StorageMetadata<Trap>::signature[0]=='1' && StorageMetadata<Trap>::signature[1]=='2' && StorageMetadata<Trap>::signature[2]=='2' && StorageMetadata<Trap>::signature[3]=='\0');
static_assert(StorageMetadata<IncompleteReference>::value==2);
static_assert(StorageMetadata<RvalueReference>::value==2);
static_assert(StorageMetadata<VectorReference>::value==2);
static_assert(StorageMetadata<PackedReference>::value==10);
static_assert(StorageMetadata<PackedReference>::signature[0]=='3' && StorageMetadata<PackedReference>::signature[1]=='1');
template<class T> auto storage_symbol(T*) -> decltype((__builtin_xnu_type_summary(T),0)) { return 43; }
template int storage_symbol<Trap>(Trap*);
