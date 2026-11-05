/* Owned synthetic mapping sequence adapted from accepted KRN-031 fixture.
 * Legacy xts_entry name is required by the unchanged accepted runtime helper;
 * the actual entry executes this DES caller fixture.
 * Shared runtime/shim/QEMU unchanged; no XNU MMU or physical-board claim. */
__attribute__((noreturn)) static void activate_high_mapping(void)
{
 /*4KiB granule,39-bit VA. TTBR0 keeps identity RAM+device UART; TTBR1 maps
  * fffffff004000000..+256MiB to40000000..+256MiB in1282MiB L2 blocks.
  * This is owned component-fixture mapping, never XNU/kernel MMU policy. */
 const u64 normal=1UL | (1UL<<10) | (3UL<<8);
 tt0[0]=normal | (1UL<<2) | (1UL<<53) | (1UL<<54); /* device, execute-never */
 tt0[1]=0x40000000UL|normal;
 tt1[448]=(uptr)high_l2|3;
 for(unsigned i=0;i<128;++i)high_l2[HIGH_L2_FIRST+i]=(0x40000000UL+((u64)i<<21))|normal;
 u64 tcr=25UL | (1UL<<8) | (1UL<<10) | (3UL<<12) | (25UL<<16) | (1UL<<24) | (1UL<<26) | (3UL<<28) | (2UL<<30);
 u64 mair=0xff,root0=(uptr)tt0,root1=(uptr)tt1,sctlr,cpacr;
 __asm__ volatile("mrs %0,cpacr_el1":"=r"(cpacr));cpacr|=3UL<<20;
 __asm__ volatile("msr cpacr_el1,%0\nisb"::"r"(cpacr):"memory");
 __asm__ volatile("dsb sy\nmsr mair_el1,%0\nmsr tcr_el1,%1\nmsr ttbr0_el1,%2\nmsr ttbr1_el1,%3\nisb\ntlbi vmalle1\ndsb sy\nisb"::"r"(mair),"r"(tcr),"r"(root0),"r"(root1):"memory");
 __asm__ volatile("mrs %0,sctlr_el1":"=r"(sctlr));sctlr|=1;
 __asm__ volatile("msr sctlr_el1,%0\nisb"::"r"(sctlr):"memory");
 __asm__ volatile("movz x10,#0\nmovk x10,#0xc400,lsl #16\nmovk x10,#0xffef,lsl #32\nmovk x10,#0xffff,lsl #48\n"
  "adrp x9,_mapped_entry@PAGE\nadd x9,x9,_mapped_entry@PAGEOFF\nadd x9,x9,x10\nadd sp,sp,x10\nbr x9":::"x9","x10","memory");
 __builtin_unreachable();
}
__attribute__((noreturn)) void unmapped_entry(const struct boot_args *args)
{
 xts_runtime_begin(args);text("KDES MAPPING START\n");
#ifdef KDES_SPIN_CONTROL
 text("KDES SPIN CONTROL\n");for(;;)__asm__ volatile("wfe");
#endif
 activate_high_mapping();
}
__attribute__((naked,noreturn)) void xts_entry(void)
{
 __asm__ volatile("adrp x9,_kdes_stack@PAGE\nadd x9,x9,_kdes_stack@PAGEOFF\nadd x9,x9,#16,lsl #12\nmov sp,x9\nb _unmapped_entry");
}
