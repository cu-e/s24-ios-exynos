ENTRY(nat036_stub)
SECTIONS {
  . = 0x9e2d80000;
  .text : { ckpt3_stub.S.o(.text*) *(.text*) }
  . = ALIGN(16);
  .rodata : { *(.rodata*) }
  . = 0x9e2e00000;
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
}
