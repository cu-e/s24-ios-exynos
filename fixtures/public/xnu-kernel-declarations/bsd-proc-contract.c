/* Independent genuine BSD-profile side of the opaque Mach/BSD API. */
#include <sys/proc.h>
_Static_assert(__builtin_types_compatible_p(proc_t, struct proc *), "opaque process pointer");
_Static_assert(__builtin_types_compatible_p(__typeof__(&proc_pid), int (*)(struct proc *)), "canonical BSD proc_pid ABI");
__attribute__((used,section("__DATA_CONST,__s24decl")))
const unsigned long long s24_bsd_proc_layout[] = { sizeof(proc_t), sizeof(int), sizeof(&proc_pid) };
int bsd_proc_probe(proc_t process) { return proc_pid(process); }
