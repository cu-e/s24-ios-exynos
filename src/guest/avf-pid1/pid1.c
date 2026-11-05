/* Owned minimal guest PID1; no libc, dyld, SDK or Apple launchd.
 * ABI facts derive from the actual selected VM008 prepared public XNU source;
 * full pins/hashes and the preserved legacy defect are in the build procedure.
 * No kernel banner is emitted. The success line is conditional on real syscalls.
 */
#if !defined(__aarch64__) || !defined(__APPLE__) || !defined(__MACH__) || !defined(__LP64__)
#error This owned entry requires the selected LP64 Darwin ARM64 ABI
#endif
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error The selected owned MachO entry is little endian
#endif
typedef __UINTPTR_TYPE__ word;
typedef __INTPTR_TYPE__ signed_word;
typedef __SIZE_TYPE__ usize;
_Static_assert(sizeof(word) == 8 && sizeof(signed_word) == 8 && sizeof(usize) == 8,
               "Selected syscall registers and sysctl length are LP64");

/* Actual selected syscalls.master: exit1,write4,open5,getpid20,sysctlbyname274.
 * SWI_SYSCALL=0x80 is from selected osfmk/mach/arm/vm_param.h; x16 is from
 * proc_reg.h and libsyscall/custom/SYS.h. These are owned ABI bindings, not SDK
 * headers or implementations. O_RDWR=2 is bound to selected bsd/sys/fcntl.h. */
enum { PID1_SYS_EXIT=1, PID1_SYS_WRITE=4, PID1_SYS_OPEN=5,
       PID1_SYS_GETPID=20, PID1_SYS_SYSCTLBYNAME=274, PID1_O_RDWR=2 };
struct result { signed_word value; word secondary; word error; };

static __attribute__((always_inline)) inline struct result
syscall6(word number, word a, word b, word c, word d, word e, word f)
{
    register word x16 __asm__("x16")=number;
    register word x0 __asm__("x0")=a;
    register word x1 __asm__("x1")=b;
    register word x2 __asm__("x2")=c;
    register word x3 __asm__("x3")=d;
    register word x4 __asm__("x4")=e;
    register word x5 __asm__("x5")=f;
    word error;
    /* Selected XNU return path overwrites BOTH x0 and x1, on success/errors.
     * x16 is conservatively read/write; x2..x5 are the direct input registers.
     * Early-clobber prevents the carry-result register aliasing any input.
     * memory covers kernel writes to sysctl buffers/length; cc covers carry. */
    __asm__ volatile("svc #0x80\n\tcset %3, cs"
        : "+r"(x0), "+r"(x1), "+r"(x16), "=&r"(error)
        : "r"(x2), "r"(x3), "r"(x4), "r"(x5)
        : "memory", "cc");
    return (struct result){(signed_word)x0,x1,error};
}

static int write_all(word fd,const char *text,usize count)
{
    /* Every successful iteration advances by at least one byte, bounded by the
     * finite owned message length. Raw carry errors never become byte counts. */
    while(count){
        struct result r=syscall6(PID1_SYS_WRITE,fd,(word)text,count,0,0,0);
        if(r.error || r.value<=0 || (usize)r.value>count)return 0;
        text+=(usize)r.value;count-=(usize)r.value;
    }
    return 1;
}

__attribute__((noreturn)) void start(void)
{
    char ostype[32]={0};usize size=sizeof(ostype);
    struct result console=syscall6(PID1_SYS_OPEN,(word)"/dev/console",PID1_O_RDWR,0,0,0,0);
    struct result pid=syscall6(PID1_SYS_GETPID,0,0,0,0,0,0);
    struct result os=syscall6(PID1_SYS_SYSCTLBYNAME,(word)"kern.ostype",11,
                             (word)ostype,(word)&size,0,0);
    int darwin=size==7 && ostype[0]=='D' && ostype[1]=='a' && ostype[2]=='r' &&
        ostype[3]=='w' && ostype[4]=='i' && ostype[5]=='n' && ostype[6]==0;
    word exit_status=1;
    if(!console.error && console.value>=0 && !pid.error && pid.value==1 && !os.error && darwin){
        static const char verified[]="\nVM002: pid=1 ostype=Darwin owned-entry=v1\n";
        exit_status=write_all((word)console.value,verified,sizeof(verified)-1)?0:2;
    }else if(!console.error && console.value>=0){
        static const char failed[]="\nVM002: guest identity checks failed\n";
        (void)write_all((word)console.value,failed,sizeof(failed)-1);
    }
    /* Real PID1 exit intentionally reaches the selected kernel panic path.
     * Actual panic/PSCI/host-deadline behavior remains a future boot experiment.
     * If exit unexpectedly returns, only an EL0-safe hint is used; no MMIO. */
    (void)syscall6(PID1_SYS_EXIT,exit_status,0,0,0,0,0);
    for(;;)__asm__ volatile("yield" ::: "memory");
}
