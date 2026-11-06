# Ordinary E1S loader diagnostic build integration

STR-031 original owner codex-e1s-boot-log-builder-20261106-sr31. Fresh worktree
worktrees/str-031-e1s-boot-log-builder-20261106, branch
team/str-031-e1s-boot-log-builder-20261106, baseline
7189aa4f73582260d15351717eaabc7dd7d8e711. STR020host and STR008ordinary builder
are accepted/done. New code is restricted to tools/build/e1s.py and the two
owned e1s-boot-log-builder fixture/procedure directories.

The new third overlay hook checks accepted log patch56966307 only after unchanged
RAM23b31 and framebuffer0689 checks/applications. It requires both applied flags,
exact loader/UI composed preimages and exact log-overlay postimages before any
target compile. The immutable patch is snapshotted inside the fresh ordinary
run; its source/host provenance and applied state remain distinct report fields.
No override, upstream edit or native sourcecontext mutation is introduced.

The old21 recorded builder run() commands remain intact; two Git log-overlay
check/apply calls yield23 recorded commands. Unchanged sources.verify provenance
Git queries and subprocesses internal to Zig are not relabelled as part of this
23-command list. All8target compiles, two real static links, two objcopy/fix_image/
boot packaging sequences, flags/linker scripts/fresh-output semantics remain.
The source phase must not invoke Zig, a compiler, builder or target tool.

Future separately admitted genuine build must retain actual probe/loader ELF,
Image, boot.img and tar artifacts plus original8object files, complete copied
source and tool/runtime provenance. New log belongs to writable file-backed
merged .data, not necessarily an output section named .data.bootlog. Validate
actual symbol size/alignment, before _payload_start/_end and disjoint from both
source-declared stacks and BSS; magic/zero header/extra terminator storage,
header image_size, objcopy/fix_image padding and real payload_addr ADR must agree.
Relevant actual ADR/ADRP relocations/ranges require validation, including genuine
linker relaxation if present; never change target flags to hide a failed check.

Wrong-input/artifact controls must reject changed patch/preimage/overlay order,
stale source/output bindings, impossible record extent/flags, header/payload
boundary, and legacy-exclusion/ABI source changes. Use genuine new target bytes
as the valid baseline only after the future build; derived invalid copies are
negative controls and never valid artifacts. Accepted STR020host/sanitizer suite
is reused as evidence and is not rerun.

Resource request only: one serial ordinary builder, existing120seconds per inner
child,600seconds whole, at most2GiB combined owned RSS under existing root
supervision. Root's native kernel wave has priority; no compiler or target build
without a separate grant. No new generic executor/resource broker, global tools,
phone/ADB/MMIO/QEMU/flash/reboot or XNU payload. Kernel0011/0012 fixed diagnostic
writes/ownership and physical mappings/cache/reset persistence/log retrieval/
Android recovery remain explicitly unqualified. Source/host artifacts do not
establish a native boot. Task stays in_progress for genuine future evidence,
independent review and root publication/common acceptance.
