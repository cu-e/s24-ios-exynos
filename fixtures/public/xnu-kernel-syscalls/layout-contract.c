// Owned target layout expectations from selected syscall_arg_t/sysent rules.
#include <sys/sysproto.h>
#include <sys/sysent.h>
#include <sys/syscall.h>
#define OFF(T,F) __builtin_offsetof(struct T,F)
_Static_assert(SYS_read==3 && SYS_write==4 && SYS_open==5 && SYS_close==6,"selected stable syscall numbers");
_Static_assert(CONFIG_REQUIRES_U32_MUNGING==1,"selected argument munging profile");
_Static_assert(sizeof(struct read_args)==24 && OFF(read_args,cbuf)==8 && OFF(read_args,nbyte)==16,"read argument slots");
_Static_assert(sizeof(struct open_args)==24 && OFF(open_args,flags)==8 && OFF(open_args,mode)==16,"open argument slots");
_Static_assert(sizeof(struct sysent)==24 && OFF(sysent,sy_arg_munge32)==8 && OFF(sysent,sy_return_type)==16,"selected dispatch record");
_Static_assert(OFF(sysent,sy_narg)==20 && OFF(sysent,sy_arg_bytes)==22,"selected dispatch counts");
_Static_assert(__builtin_types_compatible_p(__typeof__(&read),int (*)(struct proc *,struct read_args *,user_ssize_t *)),"genuine read prototype");
#ifdef S24_WRONG_LAYOUT
_Static_assert(sizeof(struct read_args)==16,"deliberately wrong argument layout");
#endif
const unsigned long long s24_syscall_layout[]={sizeof(struct sysent),OFF(sysent,sy_return_type),OFF(sysent,sy_narg),OFF(sysent,sy_arg_bytes),sizeof(struct read_args),SYS_MAXSYSCALL};
