// SPDX-License-Identifier: MIT
// Linux host compilation only; no target kernel declarations or Mach-O ABI shim.
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <mach/machine/vm_types.h>
#include <mach/boolean.h>
// The original program uses this solely in its usage diagnostic.
#define getprogname() program_invocation_short_name
_Static_assert(sizeof(vm_offset_t)==sizeof(void *), "host mmap address must fit");
_Static_assert(sizeof(vm_size_t)==sizeof(size_t), "host file extent must fit");
