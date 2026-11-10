ENTRY(nat034_stub)
SECTIONS {
  . = 0x9e2d80000;
  .text : { ckpt2_stub.S.o(.text*) *(.text*) }
  . = ALIGN(16);
  .rodata : { *(.rodata*) }
  . = 0x9e2e00000;
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
}
