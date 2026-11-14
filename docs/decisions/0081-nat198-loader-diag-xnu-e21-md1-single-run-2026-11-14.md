# Decision 0081: one NAT-198 run of loader-diag-xnu-e21-md1 (secondary EL2→EL1 drop)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052, decision 0061 and
decision 0079.

Decision 0061 covers new images within the bounded CPU experiments without a separate question, including runs that start
secondary cores with PSCI `CPU_ON`. Decision 0079 sets real SMP as the priority. This file is the per-image record that decision
0061 requires.

## Rationale and new verifiable reason

- **NAT-153.** PSCI-started cores enter at EL2 and stop after MMU-on, because XNU programs only EL1.
- **NAT-196.** It measured the EL2 state they find (E-ok on 9/9 cores). The loader's own `from_el2`, which runs on the boot CPU in
  every native run, gives them the boot CPU's configuration. No new register value is needed.
- **This run.** It is the first with the drop (roadmap S8/S9). The image has never run.

## What changes against e2p (NAT-196) and scV (NAT-185)

- **Changed.** `osfmk/start.o` only (`docs/procedures/nat-197/start.patch`). `reset_vector+4` branches, with the same size, to an out-of-line
  block in the reset-vector page. A core at EL2 then:
  1. writes HCR_EL2 = 0x80000000, CNTHCTL_EL2 = 3, ICC_SRE_EL2 |= 9 and CPTR_EL2 = 0;
  2. sets ELR_EL2 and SPSR_EL2 = 0x3c5;
  3. erets to EL1 and continues the unchanged XNU path.

  These are the loader's values, instruction for instruction (host-tested). NAT-195's probe stays as the fallback: a core still at
  EL2 at mark 4 records its state and calls CPU_OFF.
- **Unchanged.**
  - The boot CPU path. It does not take `reset_vector`.
  - Every other object and the kernel layout (segments and nm equal scV).
  - Loader sites (rc 0), the md0 root (NAT-110), and the command line except the tag `nat_attempt=NAT197-e21` (254 bytes).
  - The CPU_ON calls for cpu1–9, the same as every scV run.
- **Not touched.** Everything on the phone outside RAM. No PMIC, clock or GPU change beyond scV's (scV's stock cpu0 FREQ_REQ
  1959000 kHz stays).

## Image

loader-diag-xnu-e21-md1 (NAT-197):
- RECOVERY `artifacts/nat-197/package-001/loader-diag-xnu-e21-md1/recovery.img`, SHA-256
  52a8b24da5124c55b5813bcfc1869b28ff0826c4c5cfa9c78b5595c9a549e110 (100663296 bytes);
- payload b579d77ffda311e326f747d5a315d2d4652a0222ceb957e0dbdeccec2f325b50 (at 2048);
- kernel no-storage 0da06b549569d442f36f2431d27014f14d783a1099e4f545b12453ed10d9b8d3.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot. The session driver is
`docs/procedures/nat-197/session_nat198.py`, SHA-256 9b88664e0b1234342950577391145cf0bc3b3e60bc6ef48aa749536019d143e0.

Stock restore SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-197/smp198.py` on the kernel text, first match:

| verdict | condition |
|---|---|
| S-none | no `GenericARMPE: N of M processors are running` line: inconclusive |
| S-panic | a panic / `Debugger called` line |
| S2-all | running 10, no failure line |
| S1-some | running > 1 |
| S0-none | running 1 |

For each core that did not join:
- where it stopped;
- its EL after the drop (stage-1 value 0x408 = dropped);
- any fault (ESR class, ELR, LR).

Reported beside it:
- the stop-path notes;
- the boot CPU's scV measures (display, fbcopy181, bbd188, top186, cpuclk173, touch170).

S2 or S1 establishes that the scheduler counts the cores as running. It does not establish frame-rate gains, IPIs under load or
topology. Those are S10–S12.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0080:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risks.** For the first time, secondaries may run XNU code and join the scheduler.

- **A core faults at EL1 on its way in.** The existing secondary vectors record it and switch the core off. The boot CPU logs it
  after its 1 s wait.
- **A joined core misbehaves**, for example with missed IPIs or timers. The boot CPU can stall in a cross-call. Then the watchdog
  feed stops, and the hardware watchdog or the loader deadline ends the run. NAT-146's SEC_UPLOAD loop is the known bad outcome of a
  reset.
- **Load and heat.** All ten cores at firmware clocks for at most about 6 minutes. That is within what Android itself runs. The
  hardware thermal trip is unchanged.

**If the phone loops through SEC_UPLOAD (NAT-146):**
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s);
3. the owner holds Volume Up + Volume Down until the blue screen, then presses Volume Up for Download Mode;
4. the stock restore follows.

**Restore.** No partition other than RECOVERY is written. Restore with nat-012 `restore_stock.py` under the venv python, then run
`check_android.py` and the nat-013 assess. `task done` or `task update` comes BEFORE the permission is closed.

One attempt, and no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
