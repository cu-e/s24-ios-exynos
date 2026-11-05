/* Project-authored declaration control using genuine selected kernel headers. */
#include <kern/misc_protos.h>
#include <kern/task.h>
extern int proc_pid(struct proc *);
_Static_assert(__builtin_types_compatible_p(__typeof__(&printf), int (*)(const char *, ...)), "printf prototype");
_Static_assert(__builtin_types_compatible_p(__typeof__(&proc_pid), int (*)(struct proc *)), "proc_pid prototype");
__attribute__((used,section("__DATA_CONST,__s24decl")))
const unsigned long long s24_declaration_layout[] = {
    sizeof(struct proc *), sizeof(int), sizeof(&printf), sizeof(&proc_pid)
};
int declaration_proc_probe(struct proc *process) { return proc_pid(process); }
int declaration_printf_probe(int *counter)
{
    return printf("S24_DECLARATION_FORMAT:%d", (*counter)++);
}
