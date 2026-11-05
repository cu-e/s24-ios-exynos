/* Owned SYNTHETIC ARM caller runtime. Genuine selected headers and caller code;
 * no SDK records, fake algorithm/provider, physical board or XNU boot claim.
 * The partial table below tests only the two real XTS slots and the actual
 * register_crypto_functions routine; the full mc_provider is separately compiled
 * and all56 slots inspected. Its PRNG/startup is not simulated here.
 */
#include <libkern/crypto/crypto_internal.h>
#include <libkern/crypto/aesxts.h>
#include <kern/debug.h>
#include <mbedtls/platform_util.h>
#include "kernel_provider.h"
#include "runtime.h" /* Accepted owned helper, unchanged; QEMU virtual UART only. */
#include "vectors.h" /* Accepted primary NIST + independent OpenSSL corpus. */

__attribute__((used,aligned(16))) unsigned char kxts_stack[65536];
__attribute__((aligned(4096))) static u64 tt0[512],tt1[512],high_l2[512];
/* Public constant canary is synthetic fixture support, never kernel entropy. */
unsigned long __stack_chk_guard=0x6b78747363707531UL;
__attribute__((noreturn)) void __stack_chk_fail(void) { (panic)("synthetic stack canary failed"); }
#ifdef KXTS_BAD_MAPPING
#define HIGH_L2_FIRST 33
#else
#define HIGH_L2_FIRST 32
#endif
static unsigned checks;
static unsigned failure;
static struct crypto_functions test_table={.ccaes_xts_encrypt=&s24_kernel_xts_encrypt,
 .ccaes_xts_decrypt=&s24_kernel_xts_decrypt};
/* Synthetic runtime services have real semantics, not successful algorithm
 * callbacks: zeroization delegates to accepted volatile stores; panic stops. */
void cc_clear(size_t n,void *p) { mbedtls_platform_zeroize(p,n); }
__attribute__((noreturn)) void (panic)(const char *fmt,...)
{ (void)fmt;text("KXTS SYNTHETIC PANIC\n");stop(); }
static int all_zero(const void *p,size_t n)
{ const unsigned char *b=p;unsigned v=0;while(n--)v|=*b++;return !v; }
#define CHECK(x) do {++checks;if(!(x)){failure=__LINE__;goto done;}}while(0)
static int vectors_and_errors(void)
{
 symmetric_xts key;
 unsigned char out[VECTOR_MAX],back[VECTOR_MAX],saved[64];
 for(unsigned i=0;i<VECTOR_COUNT;++i) {
  const struct vector *v=&vectors[i];const unsigned char *raw=vector_bytes+v->key,*iv=vector_bytes+v->iv,*pt=vector_bytes+v->pt,*ct=vector_bytes+v->ct;
  CHECK(xts_start(0,NULL,raw,(int)v->n,raw+v->n,(int)v->n,0,0,&key)==0);
  CHECK(xts_encrypt(pt,v->bytes,out,iv,&key)==0 && !memcmp(out,ct,v->bytes));
  CHECK(xts_decrypt(ct,v->bytes,out,iv,&key)==0 && !memcmp(out,pt,v->bytes));
  memcpy(back,pt,v->bytes);CHECK(xts_encrypt(back,v->bytes,back,iv,&key)==0 && !memcmp(back,ct,v->bytes));
  CHECK(xts_decrypt(back,v->bytes,back,iv,&key)==0 && !memcmp(back,pt,v->bytes));
  xts_done(&key);CHECK(all_zero(&key,sizeof(key)));
 }
 const struct vector *v=&vectors[0];const unsigned char *raw=vector_bytes+v->key,*iv=vector_bytes+v->iv,*pt=vector_bytes+v->pt;
 CHECK(xts_start(0,NULL,raw,(int)v->n,raw+v->n,(int)v->n,0,0,&key)==0);
 memset(out,0xa5,sizeof(out));memcpy(saved,out,sizeof(saved));
 CHECK(xts_encrypt(pt,(S24_XTS_MAX_BLOCKS+1)*16,out,iv,&key)==CCERR_PARAMETER && !memcmp(out,saved,sizeof(saved)));
 CHECK(xts_decrypt(pt,(S24_XTS_MAX_BLOCKS+1)*16,out,iv,&key)==CCERR_PARAMETER && !memcmp(out,saved,sizeof(saved)));
 CHECK(xts_encrypt(out,32,out+1,iv,&key)==CCERR_PARAMETER && !memcmp(out,saved,sizeof(saved)));
 CHECK(xts_decrypt(out,32,out+1,iv,&key)==CCERR_PARAMETER && !memcmp(out,saved,sizeof(saved)));
 CHECK(xts_encrypt(pt,16,NULL,iv,&key)==CCERR_PARAMETER);
 CHECK(xts_decrypt(pt,16,NULL,iv,&key)==CCERR_PARAMETER);
 CHECK(xts_encrypt(pt,16,out,NULL,&key)!=0 && !memcmp(out,saved,sizeof(saved)));
 CHECK(xts_decrypt(pt,16,out,NULL,&key)!=0 && !memcmp(out,saved,sizeof(saved)));
 CHECK(xts_encrypt(NULL,0,NULL,iv,&key)==0 && xts_decrypt(NULL,0,NULL,iv,&key)==0);
 xts_done(&key);CHECK(all_zero(&key,sizeof(key)));
 CHECK(xts_encrypt(pt,16,out,iv,&key)!=0 && xts_decrypt(pt,16,out,iv,&key)!=0);
 CHECK(xts_start(0,NULL,raw,24,raw+v->n,24,0,0,&key)!=0 && all_zero(&key,S24_KERNEL_XTS_KEY_BYTES));
 CHECK(xts_start(0,NULL,raw,(int)v->n,raw,(int)v->n,0,0,&key)!=0);
#ifdef KXTS_PANIC_CONTROL
 (void)xts_encrypt(pt,17,out,iv,&key);CHECK(0);
#endif
done:xts_done(&key);return !failure;
}
__attribute__((noreturn)) void mapped_entry(void)
{
 unsigned char before[sizeof(struct ccmode_xts)*2];
 ccxts_ctx_decl(1072,key);
 u64 pc,sctlr,tcr,base0,base1;
 __asm__ volatile("adrp %0,_mapped_entry@PAGE\nadd %0,%0,_mapped_entry@PAGEOFF":"=r"(pc));
 __asm__ volatile("mrs %0,sctlr_el1":"=r"(sctlr));__asm__ volatile("mrs %0,tcr_el1":"=r"(tcr));
 __asm__ volatile("mrs %0,ttbr0_el1":"=r"(base0));__asm__ volatile("mrs %0,ttbr1_el1":"=r"(base1));
 text("KXTS MAPPED pc=");hex(pc);text(" mode=");hex((uptr)&s24_kernel_xts_encrypt);
 text(" init=");hex((uptr)s24_kernel_xts_encrypt.init);text(" tt0=");hex(base0);text(" tt1=");hex(base1);text(" tcr=");hex(tcr);putc('\n');
 CHECK(pc>=0xfffffff007000000UL && pc<0xfffffff008000000UL && (sctlr&1));
 CHECK((uptr)&s24_kernel_xts_encrypt>=0xfffffff007000000UL && (uptr)s24_kernel_xts_encrypt.init>=0xfffffff007000000UL);
 const u64 delta=0xffffffefc4000000UL,normal=1UL|(1UL<<10)|(3UL<<8);
 CHECK(tt1[448]==(((uptr)high_l2-delta)|3));
 CHECK(high_l2[32]==(0x40000000UL|normal) && high_l2[159]==(0x4fe00000UL|normal));
 CHECK(tt0[1]==(0x40000000UL|normal));
 CHECK(!s24_kernel_xts_encrypt_mode() && !s24_kernel_xts_decrypt_mode());
 memset(key,0xa5,1072);
 CHECK(s24_kernel_xts_encrypt.init(&s24_kernel_xts_encrypt,key,16,vector_bytes,vector_bytes+16)==CCERR_CALL_SEQUENCE && all_zero(key,S24_KERNEL_XTS_KEY_BYTES));
 s24_kernel_xts_encrypt.key_sched(&s24_kernel_xts_encrypt,key,16,vector_bytes,vector_bytes+16);
 CHECK(all_zero(key,S24_KERNEL_XTS_KEY_BYTES));
 memcpy(before,&s24_kernel_xts_encrypt,sizeof(struct ccmode_xts));memcpy(before+sizeof(struct ccmode_xts),&s24_kernel_xts_decrypt,sizeof(struct ccmode_xts));
#ifdef KXTS_FACTORY_MISMATCH
 CHECK(s24_kernel_xts_prepare()==CCERR_INTERNAL);
 CHECK(s24_kernel_xts_prepare()==CCERR_INTERNAL && !s24_kernel_xts_encrypt_mode() && !s24_kernel_xts_decrypt_mode());
 CHECK(s24_kernel_xts_encrypt.init(&s24_kernel_xts_encrypt,key,16,vector_bytes,vector_bytes+16)==CCERR_CALL_SEQUENCE);
 text("KXTS FACTORY MISMATCH REJECTED\n");
#else
 CHECK(s24_kernel_xts_prepare()==0 && s24_kernel_xts_prepare()==0);
 CHECK(s24_kernel_xts_encrypt_mode()==&s24_kernel_xts_encrypt && s24_kernel_xts_decrypt_mode()==&s24_kernel_xts_decrypt);
 CHECK(!memcmp(before,&s24_kernel_xts_encrypt,sizeof(struct ccmode_xts)) && !memcmp(before+sizeof(struct ccmode_xts),&s24_kernel_xts_decrypt,sizeof(struct ccmode_xts)));
 CHECK(s24_kernel_xts_encrypt.init(&s24_kernel_xts_decrypt,key,16,vector_bytes,vector_bytes+16)==CCERR_CALL_SEQUENCE);
 CHECK(!g_crypto_funcs && !crypto_init);
 CHECK(register_crypto_functions(&test_table)==0 && g_crypto_funcs==&test_table && crypto_init);
 CHECK(register_crypto_functions(&test_table)!=0);
 CHECK(g_crypto_funcs->ccaes_xts_encrypt==&s24_kernel_xts_encrypt && g_crypto_funcs->ccaes_xts_decrypt==&s24_kernel_xts_decrypt);
 (void)vectors_and_errors();
#endif
done:
#ifdef KXTS_FACTORY_MISMATCH
 text(failure?"KXTS FACTORY FAIL":"KXTS FACTORY PASS");text(" vectors=");hex(0);
#else
 text(failure?"KXTS CALLER FAIL":"KXTS CALLER PASS");text(" vectors=");hex(VECTOR_COUNT);
#endif
text(" checks=");hex(checks);text(" line=");hex(failure);putc('\n');stop();
}
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
 xts_runtime_begin(args);text("KXTS MAPPING START\n");
#ifdef KXTS_SPIN_CONTROL
 text("KXTS SPIN CONTROL\n");for(;;)__asm__ volatile("wfe");
#endif
 activate_high_mapping();
}
__attribute__((naked,noreturn)) void xts_entry(void)
{
 __asm__ volatile("adrp x9,_kxts_stack@PAGE\nadd x9,x9,_kxts_stack@PAGEOFF\nadd x9,x9,#16,lsl #12\nmov sp,x9\nb _unmapped_entry");
}
