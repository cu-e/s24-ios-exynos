"""NAT-045 test oracle, in Python: the platform the ladder runs against (the same semantics as plat.c) and an independent
reference interpreter of the op table.

 DevModel   plain 32-bit register file; HSI0 power domain (PMU config bit0 -> status bit0 after `pd_delay` microseconds);
            every access to the HSI0 block (0x17800000..0x1790ffff) while the status bit is 0 is a violation; an access to
            an address the table does not list is a violation; virtual time advances only through delay().
 ref_run    walks the table from ladder_regs.h with its own few lines of semantics and returns the expected access log
            [(R|W, addr, value, t_us)]. The C interpreter (x86, plat.c) and the same C compiled for aarch64 (unicorn) must produce
            exactly this log.
Nothing here is the S24; this is the contract written down twice.
"""
import struct

GATE_LO, GATE_HI = 0x17800000, 0x17910000
PMU_CFG, PMU_STATUS = 0x12862000, 0x12862004
DWC3_LO, DWC3_HI = 0x17900000, 0x17910000
GSNPSID_ADDR = 0x1790C120
NAT041_MODEL_ID = 0x5533330A          # the NAT-041 model's default GSNPSID (model_reset)
ALIVE_WORD = 0x00010203               # what a "present" block answers in the fixture (not 0, not 0xffffffff)

F_POWERON, F_NOTALIVE, F_SOFT, F_CMUINIT, F_DWC3ID = 0x1, 0x2, 0x4, 0x8, 0x10


class DevModel:
    def __init__(self, table, pd_on=False, pd_delay=50, follow=True, gsnpsid=NAT041_MODEL_ID, delay_cost=lambda us: us):
        self.regs = {}
        for o in table:
            if o["kind"] not in ("SET", "CONST", "DELAY"):
                self.regs[o["addr"]] = ALIVE_WORD if o["flags"] & F_NOTALIVE else 0
        self.regs[PMU_CFG] = 1 if pd_on else 0
        self.regs[PMU_STATUS] = 1 if pd_on else 0
        self.regs[GSNPSID_ADDR] = gsnpsid
        self.pd_delay, self.follow = pd_delay, follow
        self.pending_due = None
        self.t = 0
        self.log = []
        self.viol = []
        self.delay_cost = delay_cost
        self.flip = {}

    def _settle(self):
        if self.follow and self.pending_due is not None and self.t >= self.pending_due:
            self.regs[PMU_STATUS] = (self.regs[PMU_STATUS] & ~1) | (self.regs[PMU_CFG] & 1)
            self.pending_due = None

    def _gate(self, a):
        if GATE_LO <= a < GATE_HI and not self.regs.get(PMU_STATUS, 0) & 1:
            self.viol.append("HSI0 block accessed while the domain is off @%#x t=%d" % (a, self.t))

    def rd(self, a):
        self._settle()
        self._gate(a)
        if a not in self.regs:
            self.viol.append("read of an undeclared register @%#x" % a)
            v = 0
        else:
            v = self.regs[a] ^ self.flip.get(a, 0)
        self.log.append(("R", a, v, self.t))
        return v

    def wr(self, a, v):
        self._settle()
        self._gate(a)
        self.log.append(("W", a, v, self.t))
        if a not in self.regs:
            self.viol.append("write of an undeclared register @%#x" % a)
            return
        self.regs[a] = v
        if a == PMU_CFG and self.follow:
            self.pending_due = self.t + self.pd_delay
            self._settle()

    def delay(self, us):
        self.t += self.delay_cost(us)


class Stop(Exception):
    def __init__(self, rung, code, op):
        self.rung, self.code, self.op = rung, code, op


def ref_run(table, dev, stop_after, allow_poweron=True, pd_wait_us=0, writing=True):
    """Expected behaviour of lad_run: returns (error or None, state). error = (rung, code-name, op index)."""
    st = dict(rung_done=0, pd_was_on=None, soft=0, gsnpsid=0, nrec=0)
    wait_idx = next(o["i"] for o in table if o["kind"] == "WAIT" and o["flags"] & F_POWERON)
    wait_op = table[wait_idx]
    try:
        for r in range(1, stop_after + 1):
            if r >= 3 and not writing:
                raise Stop(r, "disabled", len(table))
            reg = chk = 0
            for o in (x for x in table if x["rung"] == r):
                k = o["kind"]
                if k == "RD":
                    v = dev.rd(o["addr"])
                    st["nrec"] += 1
                    if o["flags"] & F_NOTALIVE and v in (o["val"], o["val2"]):
                        raise Stop(r, "notalive", o["i"])
                    if o["flags"] & F_DWC3ID:
                        if (v & 0xFFFF0000) not in (0x55330000, 0x33310000):
                            raise Stop(r, "notalive", o["i"])
                        st["gsnpsid"] = v
                    if r == 1 and o["addr"] == wait_op["addr"]:
                        st["pd_was_on"] = int((v & wait_op["mask"]) == wait_op["val"])
                    continue
                if r == 3:
                    if o["flags"] & (F_POWERON | F_CMUINIT):
                        if st["pd_was_on"]:
                            continue
                        if not allow_poweron:
                            raise Stop(r, "state", o["i"])
                if k == "WRP":
                    dev.wr(o["addr"], o["val"])
                    rb = dev.rd(o["addr"])
                    st["nrec"] += 1
                    if rb != o["val"]:
                        raise Stop(r, "readback", o["i"])
                elif k == "WRM":
                    v = dev.rd(o["addr"])
                    want = (v & ~o["mask"] & 0xFFFFFFFF) | (o["val"] & o["mask"])
                    dev.wr(o["addr"], want)
                    rb = dev.rd(o["addr"])
                    st["nrec"] += 1
                    if (rb ^ want) & o["mask"]:
                        raise Stop(r, "readback", o["i"])
                elif k == "WAIT":
                    limit = pd_wait_us or 200000
                    n = 0
                    while True:
                        v = dev.rd(o["addr"])
                        if (v & o["mask"]) == o["val"]:
                            break
                        n += 1
                        dev.delay(1)
                        if n > limit:
                            st["nrec"] += 1
                            raise Stop(r, "timeout", o["i"])
                    st["nrec"] += 1
                elif k == "LOAD":
                    reg = dev.rd(o["addr"])
                    chk = 0
                    st["nrec"] += 1
                elif k == "SET":
                    reg = (reg & ~o["mask"] & 0xFFFFFFFF) | o["val"]
                    chk |= o["mask"]
                elif k == "CONST":
                    reg, chk = o["val"], 0xFFFFFFFF
                elif k == "STORE":
                    dev.wr(o["addr"], reg)
                    rb = dev.rd(o["addr"])
                    st["nrec"] += 1
                    if (rb ^ reg) & chk:
                        if o["flags"] & F_SOFT:
                            st["soft"] += 1
                        else:
                            raise Stop(r, "readback", o["i"])
                elif k == "RDLOG":
                    dev.rd(o["addr"])
                    st["nrec"] += 1
                elif k == "DELAY":
                    dev.delay(o["val"])
                else:
                    raise AssertionError(k)
            st["rung_done"] = r
    except Stop as e:
        return (e.rung, e.code, e.op), st
    return None, st
