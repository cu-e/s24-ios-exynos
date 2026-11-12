"""NAT-077 test support: run the real probe Mach-O (the file build.py writes) under Unicorn with a small fake Darwin kernel.

What this checks and what it does not. Unicorn executes the arm64 instructions of the *final, signed, wrapped file*: segment layout,
load commands, the entry point, ADRP distances after the wrapper moved the sections, the SHA-256 round constants in `__const`, the
`svc #0x80` register convention and the carry-flag error convention as the probe uses them. The "kernel" here is a few dozen lines
written for this test; it knows the six system calls the probe issues (exit, read, write, open, getpid, gettimeofday) with the XNU
argument order, and anything else is a test failure. It is a model of the Darwin ABI, not the payload kernel: whether the payload
kernel's /dev/rmd1 returns the bytes that were delivered is exactly what NAT-078 has to show on the phone.

Needs the `unicorn` package (artifacts/nat-065/venv/bin/python has it); the importing test module skips itself without it.
"""
import struct

from unicorn import (UC_ARCH_ARM64, UC_HOOK_INTR, UC_MODE_ARM, UC_PROT_EXEC, UC_PROT_READ, UC_PROT_WRITE, Uc, UcError)
from unicorn.arm64_const import (UC_ARM64_REG_CPACR_EL1, UC_ARM64_REG_NZCV, UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X0,
                                 UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X16)

LC_SEGMENT_64, LC_UNIXTHREAD = 0x19, 0x5
STACK_BASE, STACK_SIZE = 0x7ffff0000000, 0x400000
ENOENT, EINTR, EIO, EBADF, ENOSYS, EFAULT = 2, 4, 5, 9, 78, 14
CARRY = 1 << 29
SYS_EXIT, SYS_READ, SYS_WRITE, SYS_OPEN, SYS_GETPID, SYS_GETTIMEOFDAY = 1, 3, 4, 5, 20, 116


class Failure(Exception):
    pass


def parse_macho(data):
    """-> (segments [(name, vmaddr, vmsize, fileoff, filesize, initprot)], unixthread pc). Independent of mkstatic.py on purpose."""
    magic, cpu, _, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<8I", data, 0)
    if magic != 0xfeedfacf or cpu != 0x0100000c or ftype != 2:
        raise Failure("not an arm64 executable")
    segs, pc, off = [], None, 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == LC_SEGMENT_64:
            name = data[off + 8:off + 24].split(b"\0")[0].decode()
            vmaddr, vmsize, fileoff, filesize, _, initprot, _, _ = struct.unpack_from("<4Q2i2I", data, off + 24)
            segs.append((name, vmaddr, vmsize, fileoff, filesize, initprot))
        elif cmd == LC_UNIXTHREAD:
            flavor, count = struct.unpack_from("<II", data, off + 8)
            if flavor != 6 or count != 68:
                raise Failure("not an ARM_THREAD_STATE64 thread")
            regs = struct.unpack_from("<33Q", data, off + 16)
            pc = regs[32]
        off += size
    if pc is None:
        raise Failure("no LC_UNIXTHREAD")
    return segs, pc


class FakeKernel:
    """The system-call side. `device` is the byte string behind the root device node."""

    def __init__(self, device, pid=1, console=True, device_path=b"/dev/rmd1", console_path=b"/dev/console", read_limit=0, write_limit=0,
                 eintr=0, fail_after=None, step_us=0, backwards=False, device_missing=False, start_us=1700000000 * 1000000,
                 first_fd=0, write_stall_after=None, write_error_after=None, fd_plan=None):
        self.device, self.pid = device, pid
        self.console_ok, self.device_path, self.console_path = console, device_path, console_path
        self.read_limit, self.write_limit, self.eintr, self.fail_after = read_limit, write_limit, eintr, fail_after
        self.step_us, self.backwards, self.device_missing, self.now_us = step_us, backwards, device_missing, start_us
        self.fds = {}				# fd -> ("console",) | ("device", offset)
        self.console = bytearray()
        self.opens, self.calls, self.read_sizes, self.exit_code = [], [], [], None
        self.errors = []
        # Whether the payload kernel hands PID 1 open stdio descriptors is not established. first_fd=0 models a process that starts with none
        # (the first open() returns 0, which is a valid descriptor); first_fd=3 one that inherited stdin/stdout/stderr. The probe must work in both.
        self.first_fd = first_fd
        self.fd_plan = list(fd_plan or ())	# descriptors to hand out, in the order of the successful open() calls (a kernel that is not lowest-free-first)
        self.write_stall_after, self.write_error_after = write_stall_after, write_error_after	# once the console holds this many bytes: write() returns 0 / EIO

    def alloc(self, what):
        if self.fd_plan:
            fd = self.fd_plan.pop(0)
            self.fds[fd] = what
            return fd
        fd = self.first_fd		# lowest free descriptor, the way the BSD layer hands them out
        while fd in self.fds:
            fd += 1
        self.fds[fd] = what
        return fd

    def handle(self, uc, num, a0, a1, a2):
        """-> (value, errno or 0)"""
        self.calls.append((num, a0, a1, a2))
        if num == SYS_EXIT:
            self.exit_code = a0 & 0xffffffff
            uc.emu_stop()
            return 0, 0
        if num == SYS_GETPID:
            return self.pid, 0
        if num == SYS_OPEN:
            path = self.cstr(uc, a0)
            self.opens.append((path, a1 & 0xffffffff, a2 & 0xffffffff))
            if path == self.console_path and self.console_ok:
                return self.alloc(("console",)), 0
            if path == self.device_path and not self.device_missing:
                return self.alloc(["device", 0]), 0
            return 0, ENOENT
        if num == SYS_GETTIMEOFDAY:
            if a1 or a2:
                self.errors.append("gettimeofday called with a non-NULL tzp or mach_absolute_time pointer")
            if self.step_us:
                self.now_us += -self.step_us if self.backwards else self.step_us
            uc.mem_write(a0, struct.pack("<qii", self.now_us // 1000000, self.now_us % 1000000, 0))
            return 0, 0
        if num == SYS_WRITE:
            what = self.fds.get(a0 & 0xffffffff)
            if not what or what[0] != "console":
                return 0, EBADF
            if self.write_error_after is not None and len(self.console) >= self.write_error_after:
                return 0, EIO
            if self.write_stall_after is not None and len(self.console) >= self.write_stall_after:
                return 0, 0
            n = min(a2, self.write_limit) if self.write_limit else a2
            self.console += bytes(uc.mem_read(a1, n))
            return n, 0
        if num == SYS_READ:
            what = self.fds.get(a0 & 0xffffffff)
            if not what or what[0] != "device":
                return 0, EBADF
            self.read_sizes.append(a2)
            if self.eintr:
                self.eintr -= 1
                return 0, EINTR
            off = what[1]
            if self.fail_after is not None and off >= self.fail_after:
                return 0, EIO
            n = min(a2, len(self.device) - off)
            if self.read_limit:
                n = min(n, self.read_limit)
            if self.fail_after is not None:
                n = min(n, self.fail_after - off)
            n = max(n, 0)
            if n:
                uc.mem_write(a1, self.device[off:off + n])
            what[1] = off + n
            return n, 0
        self.errors.append("unknown system call %d" % num)
        return 0, ENOSYS

    @staticmethod
    def cstr(uc, ptr):
        out = bytearray()
        while len(out) < 256:
            b = bytes(uc.mem_read(ptr + len(out), 1))
            if b == b"\0":
                return bytes(out)
            out += b
        raise Failure("unterminated path")


def run(macho, kernel, max_insns=2_000_000_000, sp_misalign=0, stack_fill=0):
    """Execute the Mach-O's entry until exit(). -> dict(console, exit_code, insns_hint, kernel). Raises Failure on a CPU fault or a runaway.
    stack_fill: the byte the whole stack holds before the entry runs (a real stack is not zero)."""
    segs, pc = parse_macho(macho)
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for name, vmaddr, vmsize, fileoff, filesize, prot in segs:
        if name in ("__PAGEZERO", "__LINKEDIT") or not vmsize:
            continue
        perm = (UC_PROT_READ if prot & 1 else 0) | (UC_PROT_WRITE if prot & 2 else 0) | (UC_PROT_EXEC if prot & 4 else 0)
        uc.mem_map(vmaddr, vmsize, UC_PROT_READ | UC_PROT_WRITE | UC_PROT_EXEC)	# fill it first,
        uc.mem_write(vmaddr, macho[fileoff:fileoff + filesize])
        uc.mem_protect(vmaddr, vmsize, perm)						# then take the segment's own permissions
    uc.mem_map(STACK_BASE, STACK_SIZE, UC_PROT_READ | UC_PROT_WRITE)
    if stack_fill:
        uc.mem_write(STACK_BASE, bytes([stack_fill]) * STACK_SIZE)
    uc.reg_write(UC_ARM64_REG_SP, STACK_BASE + STACK_SIZE - 0x40 - sp_misalign)
    uc.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)	# FP/SIMD allowed at EL1 (Unicorn runs user code at EL1)
    uc.reg_write(UC_ARM64_REG_PC, pc)

    def on_intr(uc_, intno, _):
        if intno != 2:
            raise Failure("exception %d" % intno)
        num = uc_.reg_read(UC_ARM64_REG_X16)
        a0, a1, a2 = (uc_.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2))
        value, err = kernel.handle(uc_, num, a0, a1, a2)
        if err:
            uc_.reg_write(UC_ARM64_REG_X0, err)
            uc_.reg_write(UC_ARM64_REG_NZCV, CARRY)
        else:
            uc_.reg_write(UC_ARM64_REG_X0, value & 0xffffffffffffffff)
            uc_.reg_write(UC_ARM64_REG_NZCV, 0)

    uc.hook_add(UC_HOOK_INTR, on_intr)
    try:
        uc.emu_start(pc, 0, count=max_insns)
    except UcError as e:
        raise Failure("CPU fault: %s (pc %#x)" % (e, uc.reg_read(UC_ARM64_REG_PC)))
    if kernel.exit_code is None:
        raise Failure("the probe did not call exit() within %d instructions (pc %#x)" % (max_insns, uc.reg_read(UC_ARM64_REG_PC)))
    if kernel.errors:
        raise Failure("; ".join(kernel.errors))
    return {"console": bytes(kernel.console), "exit_code": kernel.exit_code, "kernel": kernel}
