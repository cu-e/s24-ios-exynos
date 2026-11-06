# REV-040 resource namespace review

Owner: `codex-review-resource-namespace-20261106-et`.
Worktree: `worktrees/rev-vm045-et-20261106`; branch:
`team/rev-vm045-et-20261106`; base:
`8261ce7edcfb32d5804e52f36005d76b4a27791d`.
Scope: only `docs/reviews/vm-045`.

## Intake checkpoint

The sole MAIN atomic claim-next returned exactly REV-040, exit 0. VM-039 is
done. The separate review worktree was created at the assigned base, exit 0.
REV-037 remains done and unchanged. The VM-045 author is
`codex-guest-resource-namespace-20261106-es`, in
`worktrees/vm-045-es-20261106`.

Contract intake is in progress; the reviewer has requested the exact final
author source/output freeze. No final controls or producer implementation
execution have run. No verdict is established by this intake document.

The actual correction at
`worktrees/vm-011-profile-v1-20261106/artifacts/avf-object-shards/bsd-filesystems/profile-v1/arm-neon-source-facts-001/correction-v1.json`
hashes to `19e0f8e8520df36fceaad5e8a2d687f3ed62fdaef2353c906dc3eb987457bc29`.
It explicitly preserves the superseded incomplete-display hypothesis and
records the full original argv: `-idirafter` is already at index243, the
absent historical compiler resource operand is at244, and the next argument
is `-I.`. The source rule is the target-specific
`apfs_deflate.o_CFLAGS_ADD += -idirafter $(shell $(CC) -print-resource-dir)/include`.
No flag addition or generic include-root replacement is justified.

Accepted immutable VM-038 parent facts are reused: manifest `be02fbfc`,
qualification `3343a382`, namespace `25f22291`, index `612589b5` and selectors
`408720d8`. The source-resource inputs are the existing genuine compiler
`7972eb28`, LLVM revision `fa9443738c1a18accef4244732ec6d6ee97a8133` and
RHDR002 output. Read reports hash to generation `41cfca89` and compiler
`e7811221`. This reuses source/build evidence; no compiler/generator is run.

## Prospective review boundary

After exact source freeze, register focused source/helper/temp-filesystem
controls before execution. Independently check three genuine resource-header
bytes and source/generation provenance; canonical root and search order;
exact same-slot root replacement over ordered1080 rows; new namespace,
manifest, selectors and per-object input keys; complete inherited index and
parent namespace closure; and preservation of original absent roots/receipts.
Exercise meaningful changed resource/source/compiler/provenance/flags/order,
wrong root/symlink/shadow/absence/profile controls against frozen code.

No duplicate full corpus research, compiler, preprocessor, generator, archive,
linker, QEMU, guest, common check or phone operation is authorized. No consumer
helper edits, generic `-I` workaround, pin override, SDK fallback or creation of
the old absent compiler root. Old objects remain old-profile receipts until
separate explicit adoption; no new-key/resume credit follows from derivation.

Next step: receive exact author freeze, register bounded independent controls,
and publish the review capsule and scoped commits to root/INT002. Task remains
in progress until actual integration/common acceptance and original-owner
closure authorization.
