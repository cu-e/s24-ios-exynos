# Decision text template: a native run that ends with the NAT-042 reset-to-Download-Mode path

Not a decision. Under decision 0019 (owner full-automatic mode) the agent writes the decision file itself, as
`docs/decisions/00NN-<task>-<image>-single-run-<date>.md`, **before** the run, and commits it with the image build record.
Fill every `<...>`; delete nothing from "Not granted" or "Known limits". The protocol is that of runs 001-009
(decisions 0011-0017): only RECOVERY is written, the pinned stock RECOVERY is restored afterwards, full-hash readback.

```markdown
# 00NN: One native run of <image name> with the NAT-042 reset path (<date>)

Status: recorded by the agent under decision 0019 (owner full-automatic mode) before the run; no question was asked.

## Scope
Exactly one image: <image>, RECOVERY SHA-256 <sha>, loader Image SHA-256 <sha>, payload SHA-256 <sha>, built by <task> from
commit <sha>. NAT-042 module `docs/procedures/nat-042/module/s5e9945_reset.{h,c}` at SHA-256 <sha>, linked in; plan
verified 105/105 (`artifacts/nat-042/verify.json`). Sequence: full-hash write to RECOVERY (`/dev/block/sda18`) only, full
readback, one `adb reboot recovery`, one-shot marker <path>, the run, then restore of the pinned stock RECOVERY (stock SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device
whose iProduct is `SAMSUNG USB`.

Reset path: at deadline <t> s (before the 83 s WDT failsafe) the loader calls `s5e_reset_to(PMU 0x12860000, 0x12345601)`:
INFORM2 byte 2 := 0x4e, INFORM3 := 0x12345601, reboot-cmd bits [2:0] := 0, each read back, then `0x3c00 := 2`.

## Device access granted (and nothing else)
As in the previous decision for the image's base, plus the PMU window `0x12860000`: reads and writes at offsets 0xb8, 0xbc,
0x190 and 0x3c00 only. No storage device and no partition other than RECOVERY is written.

## Pass/fail, fixed in advance
* success: the host sees VID 04e8 with iProduct `SAMSUNG USB` within <bound> s of the deadline without an owner action and
  before the WDT would have fired;
* U1/U2 refuted: no reset until the WDT elapses (host sees SEC_UPLOAD at ~+95 s as in runs 001-009);
* U3/U4 refuted: a reset happens at the deadline but the host sees SEC_UPLOAD, a normal boot or nothing;
* any outcome is evidence; none is "return to Android is solved". Nothing is retried.

## Not granted
Any other image or partition, a second run, any other MMIO, GPU bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys,
erase/factory reset. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed
* Source review + host tests only (NAT-042): the sequence is the vendor kernel's, minus the ACPM STOP request (U2) and the cache
  flush; U1-U4 are open.
* If the reset does not happen the WDT is the failsafe; Download Mode may then need the owner's keys or a longer wait.
* A run with no host observation is inconclusive. RAM contents are volatile.
```
