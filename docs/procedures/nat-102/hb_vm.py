"""NAT-102 test support: run the real NAT-101 `hb` Mach-O (the file that goes into the small root) under Unicorn with a small multi-process fake Darwin kernel.

What this checks and what it does not. Unicorn executes the arm64 instructions of the *final, wrapped file*: the entry point, the stack alignment, the `svc #0x80` register
convention, the carry-flag error convention, the fork child flag in x1, the argument order of fork, open, write, wait4, kill, dup2, execve, select, gettimeofday and getpid/getppid, the
struct timeval layout, the wait-status handling, and the control flow around them (the poll loop, the timeout kill, the failure paths). The "kernel" is written here for this test; it is a
model of the Darwin ABI as the project's XNU source describes it, not the payload kernel: whether the payload kernel behaves the same way (for example whether /dev/console accepts
the writes of a process that PID 1 started, or whether logd's start changes what the console does) is exactly what the native run NAT-103 has to show.

The model has several processes. fork() copies the CPU context, the stack and the descriptor table of the caller; the parent returns first (x0 = child pid, x1 = 0, carry clear), the child
(x0 = parent pid, x1 = 1) runs when the scheduler policy says so (`schedule`: "fork" = before the parent continues, "wait" = at the parent's first wait4 or select, "select" = at the
parent's first select). execve("/bin/ps") is not executed as arm64 code: it hands the argv to a Python fake `ps` that writes its table to whatever descriptors 1 and 2 hold in the child
(so a missing dup2 is visible as lost output), exits, hangs or crashes as the plan says. Time is virtual: select() advances it by its timeout, a child becomes waitable when its virtual
run time has passed, a hung child never does, kill(pid, 9) makes it a zombie with wait status 9.

Needs the `unicorn` package (artifacts/nat-065/venv/bin/python has it); the importing test module skips itself without it."""
import importlib.util
import struct
import sys
from pathlib import Path

from unicorn import (UC_ARCH_ARM64, UC_HOOK_INTR, UC_MODE_ARM, UC_PROT_EXEC, UC_PROT_READ, UC_PROT_WRITE, Uc, UcError)
from unicorn.arm64_const import (UC_ARM64_REG_CPACR_EL1, UC_ARM64_REG_NZCV, UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X0,
                                 UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X16)

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("nat102_probe_vm", HERE.parent / "nat-077" / "probe_vm.py")
PV = importlib.util.module_from_spec(_spec)
sys.modules["nat102_probe_vm"] = PV
_spec.loader.exec_module(PV)
Failure, parse_macho = PV.Failure, PV.parse_macho

STACK_BASE, STACK_SIZE = 0x7ffff0000000, 0x40000
CARRY = 1 << 29
ENOENT, EBADF, ESRCH, ECHILD, EAGAIN, EINVAL, ENOSYS = 2, 9, 3, 10, 35, 22, 78
SYS = dict(exit=1, fork=2, write=4, open=5, wait4=7, getpid=20, kill=37, getppid=39, execve=59, dup2=90, select=93, gettimeofday=116)
NAME = {v: k for k, v in SYS.items()}
O_RDWR, WNOHANG = 2, 1

PS_TABLE = [
    dict(pid=1, ppid=0, stat="Ss", tty="??", time="0:00.12", comm="/sbin/launchd"),
    dict(pid=12, ppid=1, stat="Ss", tty="??", time="0:00.01", comm="/usr/libexec/containermanagerd"),
    dict(pid=16, ppid=1, stat="Ss", tty="??", time="0:00.02", comm="/usr/libexec/logd"),
    dict(pid=19, ppid=1, stat="Z", tty="??", time="0:00.00", comm="(powerd)"),
]


def ps_output(argv, table=PS_TABLE, self_pid=99):
    """What the fake ps prints for the two argv shapes hb uses; anything else is an error (-> status 1)."""
    rows = list(table) + [dict(pid=self_pid, ppid=40, stat="R+", tty="??", time="0:00.00", comm="ps")]
    if argv[1:] == [b"-A"]:
        out = ["  PID TTY           TIME CMD"] + ["%5d %-3s %12s %s" % (r["pid"], r["tty"], r["time"], r["comm"]) for r in rows]
        return ("\n".join(out) + "\n").encode(), 0
    if argv[1:] == [b"-Ao", b"pid,ppid,stat,comm"]:
        out = ["  PID  PPID STAT COMM"] + ["%5d %5d %-4s %s" % (r["pid"], r["ppid"], r["stat"], r["comm"]) for r in rows]
        return ("\n".join(out) + "\n").encode(), 0
    return b"ps: illegal option\n", 1


class Proc:
    def __init__(self, pid, ppid):
        self.pid, self.ppid = pid, ppid
        self.fds = {}                      # fd -> "console"
        self.ctx = None
        self.stack = None
        self.state = "ready"               # new (forked, never ran) | ready (runnable, not running) | zombie | hung (alive, never finishes)
        self.status = 0
        self.finish_us = 0
        self.children = []
        self.image = "hb"
        self.nwait = 0


class Kernel:
    def __init__(self, pid=40, ppid=1, plan=None, schedule="wait", console_ok=True, first_fd=0, fork_fail_rounds=(), step_us=20, ps_path=b"/bin/ps", console_path=b"/dev/console",
                 start_us=1700000000 * 1000000, reaped_elsewhere=False, max_syscalls=200000):
        self.plan = plan or (lambda n, argv: dict(mode="ok", us=120000))
        self.schedule = schedule
        self.console_ok, self.first_fd = console_ok, first_fd
        self.fork_fail_rounds = set(fork_fail_rounds)
        self.step_us, self.ps_path, self.console_path = step_us, ps_path, console_path
        self.now_us = start_us
        self.start_us = start_us
        self.reaped_elsewhere = reaped_elsewhere
        self.max_syscalls = max_syscalls
        self.procs = [Proc(pid, ppid)]
        self.next_pid = pid + 1
        self.cur = self.procs[0]
        self.console = []                  # (virtual us since start, pid, bytes)
        self.calls = []                    # (pid, name, args)
        self.writes = []                   # (pid, fd, bytes) as the process issued them
        self.errors = []
        self.exit_code = None
        self.forks = 0
        self.execs = []                    # (path, [argv], [envp])
        self.selects = []                  # (nfds, r, w, e, sec, usec)
        self.kills = []
        self.stop_req = None
        self.failure = None
        self.sp_seen = set()
        self.ps_runs = 0

    # ---- helpers ----
    def alloc(self, p):
        fd = self.first_fd
        while fd in p.fds:
            fd += 1
        p.fds[fd] = "console"
        return fd

    @staticmethod
    def cstr(uc, ptr, limit=512):
        out = bytearray()
        while len(out) < limit:
            b = bytes(uc.mem_read(ptr + len(out), 1))
            if b == b"\0":
                return bytes(out)
            out += b
        raise Failure("unterminated string")

    def strvec(self, uc, ptr):
        out = []
        while True:
            q = struct.unpack("<Q", bytes(uc.mem_read(ptr + 8 * len(out), 8)))[0]
            if not q:
                return out
            out.append(self.cstr(uc, q))
            if len(out) > 16:
                raise Failure("argv/envp without a terminator")

    def emit(self, p, fd, data):
        what = p.fds.get(fd)
        if what != "console":
            return False
        self.console.append((self.now_us - self.start_us, p.pid, bytes(data)))
        return True

    # ---- the syscalls ----
    def handle(self, vm, num, args):
        """-> (value, errno or 0). May set self.stop_req."""
        uc, p = vm.uc, self.cur
        self.now_us += self.step_us
        self.calls.append((p.pid, NAME.get(num, num), tuple(args)))
        if len(self.calls) > self.max_syscalls:
            raise Failure("more than %d system calls: runaway" % self.max_syscalls)
        a0, a1, a2, a3, a4 = args
        if num == SYS["exit"]:
            code = a0 & 0xffffffff
            if p is self.procs[0]:
                self.exit_code = code
                self.stop_req = "end"
            else:
                p.state, p.status, p.finish_us = "zombie", (code & 0xff) << 8, self.now_us
                self.stop_req = "exit"
            return 0, 0
        if num == SYS["getpid"]:
            return p.pid, 0
        if num == SYS["getppid"]:
            return p.ppid, 0
        if num == SYS["open"]:
            path = self.cstr(uc, a0)
            if path == self.console_path and self.console_ok:
                if (a1 & 3) != O_RDWR:
                    self.errors.append("console opened with flags %#x, expected O_RDWR" % a1)
                return self.alloc(p), 0
            return 0, ENOENT
        if num == SYS["gettimeofday"]:
            if a1 or a2:
                self.errors.append("gettimeofday with a non-NULL tzp or mach_absolute_time pointer")
            uc.mem_write(a0, struct.pack("<qii", self.now_us // 1000000, self.now_us % 1000000, 0))
            return 0, 0
        if num == SYS["write"]:
            fd = a0 & 0xffffffff
            data = bytes(uc.mem_read(a1, a2))
            self.writes.append((p.pid, fd, data))
            if not self.emit(p, fd, data):
                return 0, EBADF
            return a2, 0
        if num == SYS["dup2"]:
            if (a0 & 0xffffffff) not in p.fds:
                return 0, EBADF
            p.fds[a1 & 0xffffffff] = p.fds[a0 & 0xffffffff]
            return a1 & 0xffffffff, 0
        if num == SYS["fork"]:
            self.forks += 1
            if self.forks in self.fork_fail_rounds:
                return 0, EAGAIN
            child = Proc(self.next_pid, p.pid)
            self.next_pid += 1
            child.fds = dict(p.fds)
            child.state, child.finish_us = "new", None
            p.children.append(child)
            self.procs.append(child)
            vm.fork_child(child)                      # snapshots the CPU state with the child's return registers
            if self.schedule == "fork":
                self.stop_req = "yield"
            return child.pid, 0
        if num == SYS["execve"]:
            path = self.cstr(uc, a0)
            argv, envp = self.strvec(uc, a1), self.strvec(uc, a2)
            self.execs.append((path, argv, envp))
            if path != self.ps_path:
                return 0, ENOENT
            self.ps_runs += 1
            spec = self.plan(self.ps_runs, argv)
            mode = spec.get("mode", "ok")
            if mode == "fail-exec":
                return 0, ENOENT
            now = self.now_us
            if mode == "hang":
                p.state, p.finish_us = "hung", None
            else:
                out, status = ps_output(argv, self_pid=p.pid)
                if mode == "crash":
                    p.status, p.state = 11, "zombie"          # killed by SIGSEGV: wait status = the signal number
                else:
                    if p.fds.get(1) != "console":
                        self.errors.append("ps stdout is not the console")
                    if p.fds.get(2) != "console":
                        self.errors.append("ps stderr is not the console")
                    self.emit(p, 1, out)
                    p.status, p.state = (status << 8), "zombie"
                p.finish_us = now + spec.get("us", 120000)
            self.stop_req = "exit"
            return 0, 0
        if num == SYS["wait4"]:
            want = a0 if a0 < (1 << 63) else a0 - (1 << 64)
            if a3:
                self.errors.append("wait4 with a non-NULL rusage")
            kids = [c for c in p.children if want in (-1, c.pid)]
            if not kids:
                return 0, ECHILD
            if self.reaped_elsewhere:
                p.children = [c for c in p.children if c not in kids]
                return 0, ECHILD
            if self.schedule == "wait" and any(c.state in ("new", "ready") for c in self.procs if c is not p):
                self.stop_req = "yield"
            ready = [c for c in kids if c.state == "zombie" and c.finish_us is not None and c.finish_us <= self.now_us]
            if not ready and not (a2 & WNOHANG):
                pending = [c for c in kids if c.state == "zombie" and c.finish_us is not None]
                if not pending:
                    raise Failure("blocking wait4 on a child that never finishes or has not run: the process would block forever")
                self.now_us = max(self.now_us, min(c.finish_us for c in pending))
                ready = [c for c in pending if c.finish_us <= self.now_us]
            if not ready:
                return 0, 0                                  # WNOHANG, nothing waitable yet
            c = ready[0]
            if a1:
                uc.mem_write(a1, struct.pack("<i", c.status))
            p.children.remove(c)
            return c.pid, 0
        if num == SYS["kill"]:
            sig = a1 & 0xffffffff
            self.kills.append((a0, sig))
            for c in p.children:
                if c.pid == a0 and c.state in ("hung", "ready", "zombie"):
                    if c.state != "zombie" or c.finish_us is None or c.finish_us > self.now_us:
                        if sig:
                            c.state, c.status, c.finish_us = "zombie", sig, self.now_us
                    return 0, 0
            return 0, ESRCH
        if num == SYS["select"]:
            if a0 or a1 or a2 or a3:
                self.errors.append("select used as a sleep with nfds=%d and fd-set pointers %#x %#x %#x" % (a0, a1, a2, a3))
            if not a4:
                self.errors.append("select with no timeout would block forever")
                return 0, EINVAL
            sec, usec, pad = struct.unpack("<qii", bytes(uc.mem_read(a4, 16)))
            if sec < 0 or not 0 <= usec < 1000000:
                self.errors.append("select with an invalid timeval %d.%d" % (sec, usec))
                return 0, EINVAL
            self.selects.append((a0, a1, a2, a3, sec, usec))
            self.now_us += sec * 1000000 + usec
            if self.schedule in ("wait", "select") and any(c.state in ("new", "ready") for c in self.procs if c is not p):
                self.stop_req = "yield"
            return 0, 0
        self.errors.append("unknown system call %d" % num)
        return 0, ENOSYS

    def console_text(self):
        return b"".join(b for _, _, b in self.console).decode(errors="replace")


class VM:
    def __init__(self, macho, kernel, stack_fill=0):
        self.k = kernel
        segs, self.entry = parse_macho(macho)
        self.uc = uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        for name, vmaddr, vmsize, fileoff, filesize, prot in segs:
            if name in ("__PAGEZERO", "__LINKEDIT") or not vmsize:
                continue
            perm = (UC_PROT_READ if prot & 1 else 0) | (UC_PROT_WRITE if prot & 2 else 0) | (UC_PROT_EXEC if prot & 4 else 0)
            if perm & UC_PROT_WRITE:
                raise Failure("segment %s is writable: this model keeps only the stack per process" % name)
            uc.mem_map(vmaddr, vmsize, UC_PROT_READ | UC_PROT_WRITE | UC_PROT_EXEC)
            uc.mem_write(vmaddr, macho[fileoff:fileoff + filesize])
            uc.mem_protect(vmaddr, vmsize, perm)
        uc.mem_map(STACK_BASE, STACK_SIZE, UC_PROT_READ | UC_PROT_WRITE)
        if stack_fill:
            uc.mem_write(STACK_BASE, bytes([stack_fill]) * STACK_SIZE)
        uc.reg_write(UC_ARM64_REG_SP, STACK_BASE + STACK_SIZE - 0x40)
        uc.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)
        uc.reg_write(UC_ARM64_REG_PC, self.entry)
        uc.hook_add(UC_HOOK_INTR, self.on_intr)
        self.loaded = kernel.procs[0]

    def save(self, p):
        p.ctx = self.uc.context_save()
        p.stack = bytes(self.uc.mem_read(STACK_BASE, STACK_SIZE))

    def load(self, p):
        if self.loaded is p:
            return
        if p.ctx is None:
            raise Failure("process %d would be resumed but was never suspended (it ended or replaced itself)" % p.pid)
        self.uc.context_restore(p.ctx)
        self.uc.mem_write(STACK_BASE, p.stack)
        self.loaded = p

    def fork_child(self, child):
        """Called from the fork handler while the parent's return registers are not yet written: snapshot the child with x0 = parent pid, x1 = 1, carry clear."""
        uc = self.uc
        keep = [uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_NZCV)]
        uc.reg_write(UC_ARM64_REG_X0, child.ppid)
        uc.reg_write(UC_ARM64_REG_X1, 1)
        uc.reg_write(UC_ARM64_REG_NZCV, 0)
        self.save(child)
        for r, v in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_NZCV), keep):
            uc.reg_write(r, v)

    def on_intr(self, uc, intno, _):
        k = self.k
        try:
            if intno != 2:
                raise Failure("exception %d at pc %#x" % (intno, uc.reg_read(UC_ARM64_REG_PC)))
            sp = uc.reg_read(UC_ARM64_REG_SP)
            if sp % 16:
                raise Failure("sp %#x is not 16-byte aligned at a system call" % sp)
            num = uc.reg_read(UC_ARM64_REG_X16)
            args = [uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4)]
            if num == SYS["fork"]:
                args = [0, 0, 0, 0, 0]
            value, err = k.handle(self, num, args)
            if err:
                uc.reg_write(UC_ARM64_REG_X0, err)
                uc.reg_write(UC_ARM64_REG_NZCV, CARRY)
            else:
                uc.reg_write(UC_ARM64_REG_X0, value & 0xffffffffffffffff)
                uc.reg_write(UC_ARM64_REG_NZCV, 0)
            if num == SYS["fork"] and not err:
                uc.reg_write(UC_ARM64_REG_X1, 0)          # the parent's second return register
            if k.stop_req:
                uc.emu_stop()
        except Failure as e:
            k.failure = e
            uc.emu_stop()
        except (UcError, struct.error) as e:
            k.failure = Failure("model error in a system call: %r" % (e,))
            uc.emu_stop()

    def run(self, chunk=20_000_000):
        k, uc = self.k, self.uc
        pc = self.entry
        while True:
            k.stop_req = None
            try:
                uc.emu_start(pc, 0, count=chunk)
            except UcError as e:
                raise Failure("CPU fault: %s (pc %#x, pid %d)" % (e, uc.reg_read(UC_ARM64_REG_PC), k.cur.pid))
            if k.failure:
                raise k.failure
            if k.stop_req is None:
                raise Failure("instruction budget of %d exhausted without a system call (pid %d)" % (chunk, k.cur.pid))
            if k.stop_req == "end":
                break
            cur = k.cur
            nxt = next((c for c in k.procs if c is not cur and c.state in ("new", "ready")), None)
            if k.stop_req == "yield" and nxt is not None:
                self.save(cur)                              # the parent waits, runnable, with its return registers already written
                cur.state = "ready"
            elif k.stop_req == "exit":
                nxt = nxt or k.procs[0]                     # a process that ended its own code (exit, or exec of the fake ps) hands over
                if nxt is cur or nxt.state not in ("ready", "running"):
                    raise Failure("no runnable process is left: pid %d ended its code while the original process is %s" % (cur.pid, nxt.state))
            else:
                nxt = cur
            if nxt is not cur:
                self.load(nxt)
                nxt.state = "ready" if nxt is k.procs[0] else "running"
                k.cur = nxt
            pc = uc.reg_read(UC_ARM64_REG_PC)
        if k.errors:
            raise Failure("; ".join(k.errors))
        return k
