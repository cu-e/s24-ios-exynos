.section __TEXT,__text,regular,pure_instructions
.globl _probe_entry
_probe_entry:
 ret
.section __DATA,__percpu
 .quad 0
.section __DATA_CONST,__kalloc_type
 .quad 0
.section __DATA_CONST,__kalloc_var
 .quad 0
.section __BOOTDATA,__init_entry_set
 .quad 0
.section __TEXT,__thread_starts
 .quad 0
.section __DATA,__data
.globl _boundary_references
_boundary_references:
 .quad ___dso_handle
 .quad __mh_execute_header
 .quad section$end$__BOOTDATA$__init_entry_set
 .quad section$end$__DATA$__percpu
 .quad section$end$__DATA_CONST$__kalloc_type
 .quad section$end$__DATA_CONST$__kalloc_var
 .quad section$end$__TEXT$__thread_starts
 .quad section$start$__BOOTDATA$__init_entry_set
 .quad section$start$__DATA$__percpu
 .quad section$start$__DATA_CONST$__kalloc_type
 .quad section$start$__DATA_CONST$__kalloc_var
 .quad section$start$__TEXT$__thread_starts
 .quad segment$start$__DATA
