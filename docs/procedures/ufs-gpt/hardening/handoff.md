# DRV-006 handoff

Owner: `claude-ufs-gpt-hardening-20261110-d6`. Branch `team/drv-006-ufs-gpt-hardening-20261110`. Code commit `45e435c8816ca5bed039857db8e228dec525b46d`.
Evidence category: host-test. No phone, MMIO, controller or storage access happened.

## What changed

A source review of DRV-005 found no memory-safety defect, but the parser accepted tables UEFI does
not allow, and the tests missed several mutation classes.

- The backup header must be on the last block of this LUN.
- The usable range must leave room for the backup array.
- At least 16,384 bytes are reserved for the array on each side.
- New tests cover the last table slot, 64-bit truncation, whole-entry zero checks, wide-unit
  terminators, the exact maximum entry count and one-sided comparisons.

## Results

`python3 src/platform/storage/ufs/gpt_check.py --run check-004` exited 0: 14 tests under ASan and
UBSan, 72 mutants killed, 0 survivors.

## Where the geometry rules were checked

The normative UEFI chapter could not be read: `uefi.org` returned HTTP 403 on 2026-11-10. The rules
agree with these secondary sources, which is weaker than the spec itself:

- <https://en.wikipedia.org/wiki/GUID_Partition_Table>
- <https://fuchsia.googlesource.com/fuchsia/+/19cd81191e02/third_party/rust_crates/vendor/gpt/src/header.rs>
- <https://qemu.googlesource.com/u-boot/+/refs/heads/next/doc/README.gpt>

## Not changed, and why

- `UniquePartitionGUID` is not checked. Lookup never uses it, and the rule could refuse a real table.
- Input fields are read more than once, so `gpt.h` now requires a stable kernel-owned buffer.
- The `userdata` refusal covers the requested name only. A disk can label data any way it likes.

## Open

- No real S24 GPT has been read, and these strict rules may refuse one. Measure before relaxing any.
- The commits after the review have tests and mutants but were not reviewed again.
- Nothing binds an extent to its LUN yet, because no integration code exists.
