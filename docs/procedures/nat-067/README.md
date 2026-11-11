# NAT-067: `loader-diag-xnu-ne1-usb` — the md0 image with the e1s touch and battery drivers off

Evidence kind: **host-test** (derivation, static reads of the real payload and the pinned patches, the NAT-065 driver/analyser re-derived and run against simulated archives and the real NAT-066 log). Nothing ran on the phone.

## Why

NAT-066 (native, decision 0027) got the payload kernel as far as `BSD root: md0` and the e1s driver init in `bsd_init`, then it took a data abort in `_e1s_touch_init + 0x174` before `load_init_program`: the touch driver patch
(`references/s24-port/xnu/e1s/patches/0003-e1s-touch.patch`) reads GPIO registers through physical-address macros instead of the `ml_io_map`ped base. The driver returns before touching anything when the boot-arg `e1stouch=0` is given;
the battery driver (`0008-e1s-battery.patch`) does the same for `e1sbattery=0` and is the other e1s driver that maps the GPIO block and bit-bangs pins from a kernel thread. This image is NAT-065's with exactly those two boot-args added.
The question of the next run is unchanged: **does PID 1 run?**

## What was built

| item | value |
| --- | --- |
| image name | `loader-diag-xnu-ne1-usb` (same length as NAT-065's, so the loader moves nothing) |
| RECOVERY image | `artifacts/nat-067/package-001/loader-diag-xnu-ne1-usb/recovery.img`, SHA-256 `ae946b4be577b8179ad55f8c43bc4c9ca8afc50c25c131f6823f99d98ea2552d` |
| `Image.payload` | SHA-256 `9fd29fb999dab902f63f04d9f01313be9171c55d539de86cf4dd20c3f18c9cda`, 21878704 bytes |
| kernel command line (227 bytes) | NAT-065's with `NAT065-md0` -> `NAT067-md0` and ` e1stouch=0 e1sbattery=0` appended |
| everything else | NAT-065's: loader, stub, USB log chain, kernel, ADT (14008 bytes), 16635-byte probe-init ramdisk |

`build.py` loads NAT-065's `build.py` and replaces three module values (name, tag, appended boot-args); two builds (`build-001`, `build-002`) give identical hashes. `derive.py` derives `session_nat067.py` (the driver) from NAT-065's
`session_nat065.py` by asserted text substitution (it fails if NAT-065's file drifts; `derive.py --check` compares the committed file to the derivation). `analyze_nat067.py` is NAT-065's analyser run under the new image name.
The decision draft is `decision-draft.md`; it is promoted to `docs/decisions/0028-...` and committed before any device access (NAT-068).

## Host tests (`test_nat067.py`, 24 tests, 0 skipped) and mutation run (`mutants.py`)

* Build: two builds identical; the build record carries the changes and NAT-065's pins; the command line is NAT-065's with the new tag and the two boot-args; a command line that already contains them is refused.
* Payload: the loader Image differs from NAT-065's in exactly six boot-id/name immediate words (the FNV chunks of the name and the folded tail of the name); the XNU payload differs only in the command-line field; the ramdisk is NAT-065's.
* Kernel: both boot-arg names are the ones the pinned patches parse, and both drivers return at the check before they map any register; the NAT-066 abort address lies inside `_e1s_touch_init` in the pinned kernel's Mach-O symbol table;
  the touch driver does read through physical-address macros (the defect behind that abort).
* Driver: the committed file equals the derivation; the derivation changes only the listed lines; gates on a temporary tree (no decision file, a missing hash or `decision 0019`, two decision files, `native` unset, a `native` decision citing another file, each required task not done). The one-shot marker is NAT-065's mechanism with the path moved to `artifacts/nat-067/` by the derivation (the `marker=` line is one of the seven lines the derivation test lists as changed; no test makes a launch).
* Analyser: under the new image name the real NAT-066 log is `other-panic` (not a pass) and a probe exit is `probe-ran-to-exit`; a boot of another image is not accepted.
* Mutants: 37 (command line, tags, pins, derivation, driver, analyser); 36 killed, 1 equivalent (D9, reason in `mutants.py`), 0 survived, 0 invalid.

## Established, not established

* Established (host-test): the image is reproducible and differs from the one that ran in NAT-066 only in the places listed; the two boot-args are parsed by the pinned patches before any register access; the driver and analyser cannot be
  used for another image or without the decision file.
* Not established: that `e1stouch=0 e1sbattery=0` is sufficient (other drivers or services may fault later in `bsd_init`); that mockfs serves the ramdisk bytes as `/sbin/launchd`; that exec of the ad-hoc-signed probe is allowed
  (`cs_enforcement_disable=1`; `rd=md0` skips `FSIOC_KERNEL_ROOTAUTH`, NAT-064); that PID 1's console text reaches the log; the timed `loader_return_after=8` return. Each is resolved or not by the run in NAT-068.

## Next

NAT-068 (native): promote `decision-draft.md` to decision 0028, commit it, open `native` citing it, one launch of `session_nat067.py --image loader-diag-xnu-ne1-usb --execute`, restore the pinned stock RECOVERY, check Android, analyse with `analyze_nat067.py`.
Pass rule: `root.outcome == "probe-ran-to-exit"`.

## Files

`build.py`, `derive.py`, `session_nat067.py`, `analyze_nat067.py`, `test_nat067.py`, `mutants.py`, `decision-draft.md`, `evidence.json`. Build/package/test/mutant artifacts are in the gitignored `artifacts/nat-067/`.
