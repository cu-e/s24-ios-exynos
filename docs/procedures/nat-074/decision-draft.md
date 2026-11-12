# DRAFT — decision for NAT-075 (not a decision; promoted to docs/decisions/00NN-… only after NAT-075 has packaged and tested its image)

Evidence kind of this draft: **source-review / host-test**. Nothing here ran on the phone. Written by `claude-nat065-20261112-ramdisk` on 2026-11-12 from the NAT-074 build (`artifacts/nat-074/build-001`, local). Hashes are placeholders until NAT-075 packages the image; the decision file must name them (the driver reads it from the tree).

## The question this run answers

Can the NAT-068 chain (loader → payload kernel → md0 probe PID 1 → exit 81 → host receives the text) run unchanged with three differences, and what does the kernel say about the second ramdisk?

1. a **4096 MiB window** instead of 512 MiB (NAT-073 found two 512 MiB limiters, both lifted: loader `MAX_WINDOW`, payload `mem_size`). The kernel's page size then becomes 16 KiB (`memSize > 1 GiB`), which has never run on this phone;
2. a **reserve-only `RAMDisk1`** of 2,475,720,704 bytes (the 2.31 GiB root volume size rounded up to 16 KiB) inside the payload's `kernel_end`, no bytes in the payload, not touched by the loader's clear;
3. a **bounded watchdog pet** (every 30 s while the 150 s cap has not passed, once more before the jump). `hold_seconds` does not poll it; `mk_hold` after the kernel's return (`loader_return_after=8`) does.

md0 stays the 16,635-byte probe of NAT-068; the kernel command line is NAT-067's (`e1stouch=0 e1sbattery=0`, tag `NAT075-md1`).

## Observables (host only, USB log chain; no camera) and what each outcome decides

| Observation | Meaning | Decision |
|---|---|---|
| Chain verdict as in 0026–0028, plus kernel text `Added memory device md1/rmd1 … for 0000000093908000` (the line's size field is in bytes, as md0's `0000000000008000` in NAT-066; 2,475,720,704 B = 604,424 blocks of 4 KiB) next to md0 | window, reserve and ADT property reach the kernel; md1 is mapped for the full range | NAT-076 (bulk-OUT receive engine) is justified |
| `zero_bytes` final 146,259,968 and `clean_full_window_*` present | the three-span clear ran; cache clean over 4 GiB completed within the loader's clocks | keep the clear plan |
| Probe exit 81 as in NAT-068 | a 16 KiB-page kernel still boots to PID 1 | window size is not the blocker |
| Return to Download Mode at ~150 s after enumeration, **no SEC_UPLOAD** | the pet kept the 83 s watchdog from expiring; the cap reset path still works | cap and pet design stand; NAT-076 can plan on ≥150 s |
| SEC_UPLOAD / automatic restart at ~83 s | the pet had no effect on this windowed watchdog | no longer than 83 s per run: the delivery must fit (NAT-076 re-planned for a 60 s window or an early-dumped transfer), pet code removed |
| Loader text `reserve layout does not fit the window` | layout check refused | read the printed values; host `check_layout` and the loader disagree |
| Kernel panic before PID 1 (first line is the finding) | 16 KiB pages or a 4 GiB map faulted | symbolicate with the pinned kernel as in NAT-066; do not re-run until the cause is addressed |
| No enumeration of 1209:0001 although the loader ran | FAIL (the USB log chain, not this change, unless the loader hung before the engine) | evidence, not a reason to repeat |

Pass criterion fixed in advance: **chain verdict PASS, `md1` reported with 604,424 4-KiB blocks (or the kernel's exact, recorded statement of the size), `root.outcome == "probe-ran-to-exit"`, and the return arrives by the NAT-044 reset path (Download Mode) rather than SEC_UPLOAD.** Anything else is recorded as informative with the reading in the table. A result other than PASS is evidence, not a reason to run again.

## Risks and recovery (unchanged protocol of decision 0019)

* Write only RECOVERY (`/dev/block/sda18`), full readback; one `adb reboot recovery`; restore the pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose iProduct is `SAMSUNG USB`; Android check. No retry.
* New risk relative to 0028: the **watchdog is petted**. A hung kernel could outlive 83 s only up to the 150 s cap, and only while the loader's own reset path is still armed: a refused reset (read-back mismatch) leaves the watchdog unpetted, so the hardware watchdog still ends the run within 83 s of the last pet (host-tested in `test_model.py`, not hardware-observed). The two unobserved cases are a pet with no effect on this windowed watchdog (SEC_UPLOAD at ~83 s, table above) and a pet that works but a kernel that never returns (reset at the cap).
* New risk: the kernel zero-fills nothing in the reserve and the loader does not clear it, so the first window boot carries whatever RAM held. That is intended (the root will be written there); it means md1's content is undefined in this run and nothing may mount it.
* NAT-051: a debugfs `clk_summary` read once sent the phone through SEC_UPLOAD; never repeated.

## Image identity to fill in when NAT-075 packages it

* Image `loader-diag-xnu-bigwin-md1` (NAT-074 `build.py`; sources hashed into `build.json` `nat074_sources`); `Image.payload`, loader `Image`, XNU payload, RECOVERY: SHA-256 `TBD` each; `mkpayload74.py` derived from the pinned mkpayload.py (`50c043e4…13ed7`), patched `46229c7c…3d582`.
* Driver and analyser: NAT-075 derives them from NAT-067's (`derive.py`); the analyser gains `md1`, `zero_bytes` and return-path readings; both must be fixed before the run and unchanged after it.
* Not granted: another image, a second run, any partition other than RECOVERY, GPU bring-up, kexec, GPT, EFS, keys, erase/factory reset, boot-chain changes, `sudo`. The boundary of decision 0002 holds: Android, apps, settings, accounts and user data stay intact.

## Owner's standing authorisation

As in decision 0028: the owner's statements recorded in decisions 0025/0026 ("launch yourself, without asking") are read as covering runs of this kind; the agent first tries to launch and asks only if the launch is refused. Each run still gets its decision file naming its hashes.
