# NAT-014: review of the experimental RECOVERY boot loop, saved evidence only, 2026-11-10

Evidence category: source-review. NAT-014 sent no command to the phone, ran no payload and wrote
no partition.

**Gate.** No new XNU execution and no experimental RECOVERY write is authorized:
- decision 0002 forbids writing any existing Android partition;
- decision 0005 covered only the stock RECOVERY restore (NAT-012) and says "No new XNU
  execution is authorized";
- the untracked 0004 draft is not a recorded owner decision.

Further native qualification needs a new owner decision that names the image hash (NAT-002 §6).

Saved inputs:
- `artifacts/recovery-qualification/attempt-001/` (Antigravity session aca2cbd5, registry owner
  `agy-nat006-20261110-aca2`);
- `artifacts/support/2026-11-10-recovery-write-incident.md`;
- `artifacts/support/2026-11-10-post-rescue-hashes.json`;
- the NAT-012 run directory `artifacts/recovery-rescue-20261110-01/` and its handoff;
- `docs/procedures/nat-009`, committed (HEAD) and in the working tree;
- `docs/procedures/nat-010`;
- `planning/tasks/NAT-011.md`.

Timestamps in Antigravity's odin4 logs are local time, UTC+5; they are converted to UTC here.

## 1. What was observed

| UTC | Observation | Source |
|---|---|---|
| 08:07 | NAT-009 committed as "INCONCLUSIVE … Do not close NAT-009 as passed or flash this candidate" | `git show d46915a:docs/procedures/nat-009/README.md` |
| 08:49:36 | Precheck: Android booted. `recovery` = stock `96620b8b…`; candidate `artifacts/nat-009/check-002/recovery.img` = `db19e3b7…` | `precheck.json` |
| 08:49:40 | Root readback of `recovery` = `db19e3b7…` (the experimental image is on the partition), then `adb reboot recovery` | `attempt-001-diag.json`, incident note |
| 08:53:21, 08:53:50 | `04e8:685d` on USB, no ADB | incident note (Claude, passive) |
| 08:55:00–08:55:36 | `04e8:685d` with iProduct **SEC_UPLOAD**, bcdDevice 2.1b. Odin handshake: three 10 s timeouts, then disconnect (-1) 36 s after open | `lsusb-04e8-685d-sec-upload.txt`, `odin4-restore.log` |
| — | "Periodic reset every 30 s; re-enumerates ~17 s later" | Antigravity's own summary in `attempt-001-diag.json`; no saved per-reset timestamps |
| 09:03:53 | `04e8:685d` iProduct "SAMSUNG USB" (Download Mode), stable. odin4 BeginSession times out | `odin4-restore-real.log`, incident note |
| 09:56–10:13 | Three stock restores; the third, single-session one succeeds | NAT-012, NAT-013 §1 |
| 10:13:36 → 10:14:37 | After the restore reboot, ADB first reports the `recovery` state, then Android with the boot animation running | NAT-012 handoff, `android-check-002.json` |
| 10:15:00 | `sys.boot_completed=1`, uptime 39 s, `ro.boot.bootreason=recovery`. All seven boot-chain partitions equal the 2026-11-10 backups | `post-rescue-hashes.json` |

**Established** (device):
- the experimental image was on RECOVERY at 08:49:40Z;
- the phone did not return to Android by itself before the owner entered Download Mode, at about
  09:03Z;
- during that time it appeared on USB as SEC_UPLOAD and later, after the owner's key entry, as
  Download Mode;
- writing back the stock image returned Android after one pass through RECOVERY.

**Not established**:
- that S-Boot started the loader;
- that the loader reached `recovery_guard`, wrote PMU 0x128600bc or armed the watchdog;
- that the resets were watchdog resets;
- that XNU was handed control or ran at all.

No screen record, RAM log, reset-reason readback or per-reset USB timeline was saved. A 30 s
period equal to the guard's nominal timeout is circumstantial. **No XNU execution on this phone
is shown by this attempt.** NAT-008/009/010 host results must not be presented as XNU running on
hardware or as a working watchdog return.

## 2. The SEC_UPLOAD contradiction

iProduct SEC_UPLOAD is S-Boot's upload (RAM dump) identity. Upload mode does not speak the Odin
protocol, so the Odin handshake timeouts at 08:55Z are expected there and say nothing about a
running loader. There are two readings, and neither is verified:
- **A** (Antigravity, `attempt-001-diag.json`): S-Boot's USB descriptor "remains passive" while
  the loader runs.
- **B**: S-Boot itself was running in upload mode after an abnormal reset or exception, and the
  cycle repeated.

The NAT-009 working-tree README written by the same session says a RECOVERY boot sets "upload mode
to disable" (`set_param(17, 0, 0, 1)` at 0x247d9c), "preventing `sbl_check_upload` … from entering
Upload Mode on a subsequent watchdog reset". If that were true, reading B would be excluded, but
then SEC_UPLOAD should not have appeared at all. The observation contradicts the claim, or the
claim's preconditions were not met. This is the main open question about the loop.

## 3. Review of the NAT-009 / NAT-010 / NAT-011 assumptions

| Claim | Where | Status |
|---|---|---|
| S-Boot copies PMU_PANIC_INFORM 0x12345604 into param(0) REBOOT_MODE=4 and zeroes the register (`0x29d994..0x29dde8`) | NAT-009 working tree §1 | static reading of `epbl`, unverified on the device |
| With 0x12345600 in the register, the next watchdog reset makes S-Boot set REBOOT_MODE 0 and boot Android | NAT-009 working tree §1/§3, `recovery_guard.c` | **prediction not met**: the loop happened. Either the guard did not run or write, or S-Boot does not evaluate the register after this reset, or something else intervened |
| On WDTRESET, `sbl_check_reboot_mode` skips "without evaluating PMU_PANIC_INFORM" | `attempt-001-diag.json`, written after the failure | post-hoc static reading, listed as "proven" but unmeasured. It conflicts with §1 of the same session's README, which has the function read the register first and skip only when the magic is absent |
| "S-Boot accepted and loaded the custom RECOVERY image"; "Loader entered … recovery_guard and armed the … watchdog"; "watchdog clock remained ungated and reset the SoC after 30 seconds" | `attempt-001-diag.json` "proven_facts" 1–3 | inferences from the 30 s period; nothing in the saved evidence observes them |
| Loader/XNU did not reach Android or re-enumerate USB | "proven_facts" 4 | the second half is observed; whether XNU ran is unknown (§1) |
| S-Boot handoff state: EL2, SCTLR M/C clear, x0 = FDT 0xa0000000 | NAT-010, NAT-009 §4 | binary-derived and host-tested only; the loop neither confirms nor refutes it |
| A PMU SWRESET with SEC_RESET_REASON_UNKNOWN makes S-Boot clear REBOOT_MODE | NAT-011 (proposal) | rests on the post-hoc WDTRESET claim, on secure PMU write access from EL1/EL2 (unmeasured), and on S-Boot then clearing param(0) (unmeasured). Testing it needs another experimental RECOVERY write, which is not authorized. It is a proposal, not a fix |
| REBOOT_MODE=4 persisted in `param` after the attempt | NAT-011 premise | consistent with the first post-restore boot entering RECOVERY (`ro.boot.bootreason=recovery`, ADB `recovery`). Not distinguished from Samsung's own post-Download-Mode recovery pass or a `misc` command. Unverified |

**Registry finding (process).** NAT-009 is recorded done by `agy-nat006-20261110-aca2` with evidence
hash `a9d068e8…`:
- that hash is the uncommitted working-tree `evidence.json`; HEAD's file hashes to `094a4f4a…`;
- its own progress note says "Overall evidence inconclusive";
- AGENTS.md says an inconclusive outcome does not complete a task.

The flashed candidate `check-002` was built from the uncommitted `recovery_guard.c`, which also
rewrites a zero register. It is not the committed NAT-009 state. Whether to reopen NAT-009 is the
owner's decision; NAT-014 does not change another owner's task.

## 4. What the rescue did measure (useful for NAT-002 §7)

These are owner-performed and reported in NAT-012, not planned W-stage runs:
- Download Mode entry with the keys works on `e1s`. The NAT-012 handoff records owner entries for
  USB devices 20, 23 and 24;
- a fresh single Odin session restores RECOVERY and returns Android (NAT-013);
- the first boot after the restore passed through RECOVERY and then reached Android. Whether the
  owner pressed anything there is not recorded.

The forced-restart combination was used once, after `stock-flash-001`. It ended the cycle, but the
phone returned to the loop because RECOVERY was still not stock. It does not show a return to a
running Android, so W1 remains open.

## 5. Additions to the future qualification gate

1. **No experimental write rests on static S-Boot analysis alone.** NAT-002 W1–W3 come first;
   W4 is the only test of an automatic return.
2. **A falsified prediction ends the line until a review.** A follow-up image built on a post-hoc
   explanation (NAT-011) is not the next step.
3. **Observation channel.** Each native attempt keeps a screen record (the owner's photo or
   notes) and a per-reset USB log with iProduct. Without them, neither "XNU ran" nor "XNU did not
   run" can be claimed.
4. **SEC_UPLOAD means stop.** No Odin tool is run against an upload-mode enumeration.
5. **One Odin session per Download Mode entry**, using the NAT-013 tool only.
6. **Done means acceptance met.** An inconclusive host result is not completed, and evidence is
   committed before it is recorded.

## 6. Unknowns and what would resolve them

| Unknown | Resolved by |
|---|---|
| Whether the loader or XNU ran during the loop | not recoverable from saved evidence; future attempts need §5.3 |
| Why SEC_UPLOAD appeared | an applicable S-Boot upload-decision reading, plus a per-reset USB log in a future authorized attempt |
| Whether REBOOT_MODE persists in `param` and is cleared on a normal boot | a read-only `param`/`misc` comparison against a pre-attempt copy (`precheck.json` holds only a `misc` hash). This needs a narrowly scoped read-only task |
| Whether the reason register is read after a watchdog reset | W4/W5 under a new owner decision |
