"""NAT-052 simulator: NAT-047's Sim47 (the built loader.elf in unicorn, the NAT-041 DWC3 host model behind the engine's MMIO) with two additions
the checkpoint stub needs.

  queue_gap(seconds)   the payload kernel runs: the CPU is busy for that long and the loader makes NO engine poll, so the USB host's
                       transfers meet a device side that does not run (the model's poll callback is not called). The real controller
                       would answer nothing in the same situation: the simulated host sees a timeout, as the collector would.
  queue_py(fn)         an instantaneous step of the test between two loader calls (set VBAR_EL1, read a register).

Everything else is Sim47 unchanged. Evidence kind: host-test (no caches, no MMU, no interrupts, no real controller)."""
import unicorn
from unicorn import arm64_const as A

import sim47 as S

GAP, PY = "__gap__", "__py__"


class Sim52(S.Sim47):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.gap_until = 0
        self.gap_polls_blocked = 0
        self.gaps = []                                  # (start_t, end_t) of every gap that ran

    def queue_gap(self, seconds):
        self.queue.append((GAP, (seconds,)))

    def queue_py(self, fn):
        self.queue.append((PY, (fn,)))

    def vbar(self):
        return self.mu.reg_read(A.UC_ARM64_REG_VBAR_EL1)

    def set_vbar(self, v):
        self.mu.reg_write(A.UC_ARM64_REG_VBAR_EL1, v)

    def _guest_poll(self):
        if self.t < self.gap_until:                     # the kernel is running: nobody services the controller
            self.gap_polls_blocked += 1
            return
        super()._guest_poll()

    def advance(self, target_s=None, target_t=None, slice_insn=20_000_000):
        """Sim47.advance with the two pseudo-calls handled between real ones."""
        self.target = target_t if target_t is not None else self.t0 + int(target_s * S.FREQ)
        mu = self.mu
        while self.t < self.target and not self.stopped:
            if self.cur is None:
                if not self.queue:
                    self.t = self.target
                    break
                name, args = self.queue[0]
                if name == PY:
                    self.queue.pop(0)
                    args[0](self)
                    continue
                if name == GAP:
                    if not self.gap_until:
                        self.gap_until = self.t + int(args[0] * S.FREQ)
                        self.gaps.append([self.t, self.gap_until])
                    self.t = min(self.target, self.gap_until)
                    if self.t >= self.gap_until:
                        self.queue.pop(0)
                        self.gap_until = 0
                    continue
                self.queue.pop(0)
                self._begin(name, args)
            self.paused = False
            try:
                mu.emu_start(self.pc, S.STOP, count=slice_insn)
            except unicorn.UcError as e:
                raise AssertionError("%s: %s at pc=%#x (image offset %#x)" % (self.cur, e, mu.reg_read(A.UC_ARM64_REG_PC),
                                                                               mu.reg_read(A.UC_ARM64_REG_PC) - S.LOAD))
            self.pc = mu.reg_read(A.UC_ARM64_REG_PC)
            if not (self.paused or self.stopped or self.pc == S.STOP):
                self.insn_budget -= slice_insn
                assert self.insn_budget > 0, "instruction budget exhausted (the simulation does not make progress)"
            if self.pc == S.STOP:
                self.done_calls.append((self.cur, mu.reg_read(A.UC_ARM64_REG_X0)))
                self.done_polls.append(self.polls)
                self.cur = None
        return self.t
