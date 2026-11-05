/* Owned VM-005 SYNTHETIC CPU handoff fixture, not an XNU kernel or userland.
 * Layout/virtual-board constants independently derived from pinned AVF/QEMU
 * source identified in docs/procedures/avf-handoff/experiment.md.
 * All MMIO below targets QEMU's virtual PL011 only; no phone is involved.
 */
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned long uptr;

#define RAM_BASE 0x40000000UL
#define RAM_END 0x50000000UL
#define VIRT_BASE 0xfffffff004000000UL
#define WINDOW_SIZE 0x0e000000UL
#define COOKIE "vm005_cookie=owned-synthetic-v1"

struct video { u64 base, display, rowbytes, width, height, depth; };
struct boot_args {
    unsigned short revision, version;
    u64 virt_base, phys_base, mem_size, top;
    struct video video;
    u32 machine_type;
    u64 dt_virtual;
    u32 dt_length;
    char command[608];
    u64 flags, actual_mem;
};
_Static_assert(sizeof(struct boot_args) == 736, "pinned boot_args size");
_Static_assert(__builtin_offsetof(struct boot_args, command) == 108, "pinned command offset");
_Static_assert(__builtin_offsetof(struct boot_args, dt_virtual) == 96, "pinned DT offset");

static void putc(char c)
{
    volatile u32 *fr = (volatile u32 *)0x09000018UL;
    for (u32 i = 0; i < 100000 && (*fr & 0x20); ++i) { }
    *(volatile u32 *)0x09000000UL = (u8)c;
}

static void text(const char *p)
{
    while (*p) putc(*p++);
}

static void hex(u64 value)
{
    int leading = 1;
    text("0x");
    for (int shift = 60; shift >= 0; shift -= 4) {
        unsigned digit = (unsigned)((value >> shift) & 15);
        if (digit || !leading || !shift) {
            putc((char)(digit < 10 ? '0' + digit : 'a' + digit - 10));
            leading = 0;
        }
    }
}

static u64 psci(u64 number)
{
    register u64 x0 __asm__("x0") = number;
    __asm__ volatile("hvc #0" : "+r"(x0) : : "x1", "x2", "x3", "x4", "x5", "x6", "x7",
                     "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "memory", "cc");
    return x0;
}

__attribute__((noreturn)) static void stop(void)
{
    text("VM005 SYNTHETIC PSCI_SYSTEM_OFF\n");
    __asm__ volatile("dsb sy" : : : "memory");
    (void)psci(0x84000008UL);
    text("VM005 SYNTHETIC REJECT psci-returned\n");
    for (;;) __asm__ volatile("wfe");
}

__attribute__((noreturn)) static void reject(const char *why)
{
    text("VM005 SYNTHETIC REJECT "); text(why); putc('\n'); stop();
}

static u32 read32(const u8 *p)
{
    return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24;
}

static u64 read64(const u8 *p)
{
    return (u64)read32(p) | (u64)read32(p + 4) << 32;
}

static int name_is(const u8 *p, const char *wanted)
{
    for (u32 i = 0; i < 32; ++i) {
        if (p[i] != (u8)wanted[i]) return 0;
        if (!wanted[i]) return 1;
    }
    return 0;
}

static int value_is(const u8 *p, u32 length, const char *wanted)
{
    for (u32 i = 0; i < length; ++i) {
        if (p[i] != (u8)wanted[i]) return 0;
        if (!wanted[i]) return i + 1 == length;
    }
    return 0;
}

static u32 found;
enum { UNKNOWN, ROOT_NODE, CHOSEN_NODE, IO_NODE, UART_NODE, GIC_NODE };

static const u8 *node(const u8 *p, const u8 *end, unsigned depth, unsigned parent)
{
    if (depth > 8 || (u64)(end - p) < 8) reject("dt-node-bounds");
    u32 props = read32(p), children = read32(p + 4), mode = UNKNOWN;
    p += 8;
    if (props > 128 || children > 64) reject("dt-counts");
    for (u32 i = 0; i < props; ++i) {
        if ((u64)(end - p) < 36) reject("dt-property-header");
        const u8 *name = p;
        u32 length = read32(p + 32);
        p += 36;
        if (length > (u64)(end - p) || length > 65536) reject("dt-property-data");
        if (name_is(name, "name")) {
            if (!depth && value_is(p, length, "device-tree")) { mode = ROOT_NODE; found |= 1; }
            if (parent == ROOT_NODE && value_is(p, length, "chosen")) mode = CHOSEN_NODE;
            if (parent == ROOT_NODE && value_is(p, length, "arm-io")) mode = IO_NODE;
            if (parent == IO_NODE && value_is(p, length, "uart0")) mode = UART_NODE;
            if (parent == IO_NODE && value_is(p, length, "gic")) mode = GIC_NODE;
        }
        if (mode == CHOSEN_NODE && name_is(name, "psci-method") && value_is(p, length, "hvc")) found |= 2;
        if (mode == CHOSEN_NODE && name_is(name, "dram-base") && length == 8 && read64(p) == RAM_BASE) found |= 4;
        if (mode == CHOSEN_NODE && name_is(name, "dram-size") && length == 8 && read64(p) == WINDOW_SIZE) found |= 8;
        if (mode == UART_NODE && name_is(name, "compatible") && value_is(p, length, "arm,pl011")) found |= 16;
        if (mode == UART_NODE && name_is(name, "reg") && length == 16 && read64(p) + 0x100 == 0x09000000UL) found |= 32;
        if (mode == GIC_NODE && name_is(name, "compatible") && value_is(p, length, "arm,gic-v3")) found |= 64;
        if (mode == GIC_NODE && name_is(name, "reg") && length == 32 &&
            read64(p) + 0x100 == 0x08000000UL && read64(p + 16) + 0x100 == 0x080a0000UL) found |= 128;
        u32 padded = (length + 3) & ~3U;
        if (padded > (u64)(end - p)) reject("dt-property-padding");
        p += padded;
    }
    for (u32 i = 0; i < children; ++i) p = node(p, end, depth + 1, mode);
    return p;
}

static int has_cookie(const char *p)
{
    const char *wanted = COOKIE;
    for (unsigned i = 0; i < 608 && p[i]; ++i) {
        if (i && p[i - 1] != ' ') continue;
        unsigned j = 0;
        while (wanted[j] && i + j < 608 && p[i + j] == wanted[j]) ++j;
        if (!wanted[j] && i + j < 608 && (p[i + j] == ' ' || !p[i + j])) return 1;
    }
    return 0;
}

__attribute__((noreturn)) void synthetic_entry(const struct boot_args *ba)
{
    u64 entry, current_el, sctlr;
    __asm__ volatile("adr %0, _synthetic_entry" : "=r"(entry));
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(current_el));
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    text("VM005 SYNTHETIC ENTER entry="); hex(entry); text(" ba="); hex((uptr)ba); putc('\n');
    if ((uptr)ba < RAM_BASE || (uptr)ba > RAM_END - sizeof(*ba) || ((uptr)ba & 15)) reject("bootargs-pointer");
    if (current_el != 4 || (sctlr & 1)) reject("entry-el-or-mmu");
    if (entry < RAM_BASE + 0x03000000 || entry >= RAM_BASE + 0x03100000) reject("entry-address");
    if (ba->revision != 2 || ba->version != 2) reject("bootargs-version");
    if (ba->virt_base != VIRT_BASE || ba->phys_base != RAM_BASE ||
        ba->mem_size != WINDOW_SIZE || ba->actual_mem != WINDOW_SIZE) reject("memory-contract");
    if (!has_cookie(ba->command)) reject("command-cookie");
    if (ba->dt_virtual < VIRT_BASE || ba->dt_virtual - VIRT_BASE >= WINDOW_SIZE ||
        !ba->dt_length || ba->dt_length > 65536) reject("dt-window");
    uptr dt = ba->phys_base + (ba->dt_virtual - ba->virt_base);
    if (dt + ba->dt_length > RAM_END || (uptr)ba != dt + 65536 ||
        ba->top != (uptr)ba + 16384) reject("bootargs-dt-layout");
    if (node((const u8 *)dt, (const u8 *)(dt + ba->dt_length), 0, UNKNOWN) != (const u8 *)(dt + ba->dt_length) ||
        found != 255) reject("dt-virtual-board-properties");
    u64 version = psci(0x84000000UL);
    if ((version >> 16) != 1) reject("psci-version");
#ifdef VM005_SPIN
    text("VM005 SYNTHETIC SPIN-CONTROL\n");
    for (;;) __asm__ volatile("wfe");
#else
    text("VM005 SYNTHETIC PASS entry="); hex(entry); text(" ba="); hex((uptr)ba);
    text(" dt="); hex(dt); text(" mem="); hex(ba->mem_size); text(" psci="); hex(version); putc('\n');
    stop();
#endif
}
