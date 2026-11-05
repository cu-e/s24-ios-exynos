// Owned target-type control; genuine declarations come from generated headers.
#include <IOKit/system.h>
#include <mach/mach_vm.h>
#include <mach/vm_map.h>
#ifdef S24_WRONG_SIZE_TYPE
using ExpectedSize = unsigned int;
#else
using ExpectedSize = memory_object_size_t;
#endif
using Entry = kern_return_t (*)(vm_map_t, ExpectedSize *, memory_object_offset_t,
    vm_prot_t, mem_entry_name_port_t *, mem_entry_name_port_t);
static_assert(__is_same(decltype(&_mach_make_memory_entry), Entry));
static_assert(!__is_same(decltype(&_mach_make_memory_entry), decltype(&mach_make_memory_entry)));
static_assert(sizeof(mach_vm_address_t)==8 && sizeof(memory_object_size_t)==8);
static_assert(sizeof(void*)==8);
extern "C" const unsigned long long s24_mig_widths[]={
    sizeof(void*),sizeof(mach_vm_address_t),sizeof(memory_object_size_t)};
