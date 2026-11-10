# NAT-002: control and return paths for a native test

Status: design (source review), 2026-11-10. It grants nothing. Every step that writes a partition,
reboots, enters Download Mode or runs a native image needs its own owner decision (NAT-003 records
it). Decision 0002 does not cover these steps. The untracked `docs/decisions/0004-*` draft is not a
recorded owner decision.

Inputs:
- the NAT-001 recovery plan (`docs/recovery.md`) and the TST-001 package checks;
- NAT-005 (S-Boot runtime FDT), NAT-007 (watchdog registers), NAT-008 (host restore tool), NAT-009
  (S-Boot reboot-reason handling, derived from the binary) and NAT-010 (loader MMU/cache);
- the pinned `s24-port` c8860dec README and the `watchdog-docs` source.

Measured means observed on this phone. Everything else is marked as an inference or a plan.

## 1. Where ADB becomes unavailable

| Phase | What runs | ADB | Other channels to the host | Measured |
|---|---|---|---|---|
| A. Android | stock Android, Magisk root | yes (adbd) | USB ADB | yes (DEV-001, NAT-001) |
| B. Shutdown for a reboot | Android stopping | lost when adbd stops; the host sees the USB device leave | none | no |
| C. S-Boot | Samsung bootloader | no | USB Odin protocol only if Download Mode is entered | no |
| D. Loader and XNU from RECOVERY | the project's loader, then XNU with a RAM root | no: there is no adbd and no USB gadget driver (USB-002 is pending) | screen (S-Boot framebuffer 0xfa200000, NAT-005); RAM log rings at 0x91200000 (loader) and 0x91300000 (XNU console), per `s24-port` patches 0011/0014 | no |
| E. Reset | watchdog expiry, the key combination or PSCI reset | no | none | no |
| F. Back in Android | stock boot path | yes, once adbd starts | USB ADB | no |

ADB is lost at the start of phase B and returns only in phase F. The agent has no input channel at
all from B to F, and no output channel except the screen, which the owner has to look at. A RAM ring
helps only if its contents survive the reset and can be read back from Android. Neither is
established: reading the `sec_debug_next` reservation needs a path that has not been chosen, and
MMIO or `/dev/mem` probes from Android are not authorized.

## 2. The independent control plane

Once ADB is gone, the only controls are:

1. **The owner's hands and eyes** (primary). The owner looks at the screen and can force a restart
   with the key combination. Samsung documents Vol Down + Power held for several seconds. It has
   not been observed on this phone (`docs/recovery.md`).
2. **The hardware watchdog** (automatic return; not available yet). NAT-007 derived the S5E9945
   WTCON/WTDAT/WTCNT sequence and its PMU routing from source, and host-tested it. Whether the
   clocks survive, whether secure PMU access is possible, whether expiry happens at all, and where
   S-Boot goes next are all unmeasured.
3. **The S-Boot reboot reason** (selects the next target). NAT-009 derived from the S-Boot binary
   that clearing panic-inform 0x128600bc to 0x12345600 makes the next reset boot normal Android.
   This is a static-analysis claim, not a measured reset.
4. **Download Mode with the host restore tool** (repair, not return). It is entered with keys
   (not observed on `e1s`). NAT-008's pinned odin4 writes back a backed-up image (see section 4).
5. **Passive host observation.** The host can see which USB device enumerates (none, Download Mode
   or Android ADB) and when. This tells the phase, but it cannot change anything.

The agent cannot act in phases B-E. Its role there is limited to keeping time and recording what
the host sees.

## 3. Validation plan for watchdog and one-shot boot (separate from any XNU boot)

Run each stage only after an owner decision for that stage, and only after the previous stage
passes. A failure stops the plan; it is not retried in a loop. Stages 1-2 involve no native code.

| Stage | Question | Scope | Pass criterion |
|---|---|---|---|
| W0 | Are the restore inputs ready on the host? | host | Backups match `manifest.json`; the restore tool and archive check pass (NAT-001, NAT-008). Done, host only. |
| W1 | Does the forced-restart combination return a running Android to Android? | owner present, no image change | Android and ADB return; uptime resets; no data prompt. |
| W2 | Does stock RECOVERY entry and exit work (NAT-004)? | owner present, stock partitions | Stock recovery appears and is left without touching any menu item, and Android returns. |
| W3 | Does a restore of the unchanged stock `recovery` work? | owner present, Download Mode | The written image equals the backup hash; Android boots; `recovery` hash on the device is unchanged. |
| W4 | Does a minimal RECOVERY image that only clears the reason, arms the watchdog for a short timeout and spins return to Android without the owner? | owner present, RECOVERY only | Android returns within timeout + boot time with one reset, then a second clean boot (no loop). Afterwards the stock `recovery` is restored and its hash checked. |
| W5 | The same image with the reason left at recovery: does S-Boot loop into RECOVERY? | optional, owner present | Records the failure mode the clearing step prevents; the owner's key fallback must work. |

**Software timeout vs hardware watchdog.** These are separate:
- the *software timeout* is the host's or the owner's clock: when to stop waiting and act by hand;
- the *hardware watchdog* is the SoC timer that resets the phone with nobody acting.

A loader's own timeout loop is software and dies with the code that runs it; it does not count as
a return path. Only W4 can show that the hardware watchdog works.

Until W4 passes, the one-shot property is unproven. The NAT-009 analysis says S-Boot persists and
zeroes the reason, but that has not been observed on this phone.

## 4. Manual fallback

In order:
1. Forced restart with the keys. If Android comes back, stop and record.
2. If the phone returns to RECOVERY again (a loop), enter Download Mode with the keys.
3. Restore the stock `recovery` from `devices/recovery/backups/2026-11-10/` with the NAT-008 tool,
   as in `docs/recovery.md`. Write only that image, then confirm the hash once Android is back.

Only `recovery` is ever the target. `boot`, `init_boot`, `vendor_boot`, `vbmeta`, `dtbo`, `userdata`,
EFS and keys are never written. A change confined to `recovery` does not touch user data, and the
normal boot path does not read it.

Limits:
- Fallback steps 1-2 depend on key combinations that have not been observed on `e1s`; W1 and W3
  measure them.
- Android's `install-recovery` may rewrite a non-stock `recovery` on a normal boot (not observed).
  It could hide a failed restore, so the hash check after the return is mandatory.

## 5. RAM root without access to personal data

The first native image boots XNU with a RAM disk root (`rd=md0`), as the VM-002 payload does under
s24vmm (VM-054). It must not touch storage:
- no UFS driver attached, or its probing disabled by the image's configuration;
- no `rd=ufsroot0`: `s24-port` patch 0013 marks that path untested;
- no mount of any block device;
- no write path to storage in the image.

This is checked on the host before any session, by inspecting the image's configuration and driver
list (a TST-001-style check), not trusted from a description. Reads of DPU registers stay opt-in
(`e1sdisp=2`), because the upstream notes that a read from a gated block can hang the interconnect.

## 6. When an autonomous loop is prohibited

An agent must not run any native boot, flash or reboot cycle on its own. Each session is a single
attempt that the owner approves and attends. In particular:

- **No verified restore, no session.** Until W3 passes, no native image is written at all. Until W4
  passes, every native session has the owner present for the full fallback in section 4.
- **No action after losing the channel.** Once ADB is gone, the agent does not flash, reboot or send
  commands again. It waits for the agreed software timeout, then hands over to the owner.
- **One attempt per decision.** A failed or unclear boot is not retried automatically. A new attempt
  needs a new decision that names the image hash.
- **Stop criteria** (any one ends the session and starts the fallback):
  - ADB not back within the agreed timeout (for example, watchdog timeout plus 120 s);
  - two resets without Android in between;
  - any recovery or data prompt (factory reset, wipe), which is never answered;
  - battery below 50 % or a temperature warning;
  - an unexpected screen;
  - a `recovery` hash that differs from the image that was supposed to be there.
- **Stopping the agent stops nothing on the phone.** A running native image ends only by the
  watchdog, the keys or power. No return to Android is promised before W4 measures it.

## 7. What is still unknown and what resolves it

| Unknown | Resolved by |
|---|---|
| Key combinations on `e1s` (forced restart, Download Mode) | W1, W3 |
| Stock RECOVERY entry and exit | W2 (NAT-004) |
| Whether S-Boot boots a non-stock `recovery` in the orange state | W4 |
| Whether watchdog clocks and PMU routing work from the loader at EL1/EL2 | W4 |
| Whether the reason is consumed and cleared by S-Boot (one-shot) | W4, W5 |
| Whether RAM logs survive a reset and can be read back | a separate read-path decision after W4 |
| Whether `install-recovery` rewrites `recovery` | hash check after W3/W4 |
