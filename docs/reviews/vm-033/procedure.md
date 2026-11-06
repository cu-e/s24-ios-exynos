# REV-046 independent allocator metadata review

Reviewer: `codex-review-guest-allocator-20261106-fa`. Actual atomic claim:
REV-046. Worktree `worktrees/rev-vm033-fa-20261106`, branch
`team/rev-vm033-fa-20261106`, base `b000b0af2e67212e4c75a217f2b38467e820268a`.
The only maintained write boundary is `docs/reviews/vm-033`.

Review the original producer worktree `worktrees/vm-033-20261106`, frozen at
`9248a9dc935602e4391375feb9e69630f099db90`. Its exact linear source chain is
`544ba0875c0648b2cc963ff43bd21644f0005b17`,
`78cc7ad93b2af975538b7031931b5da0a895756a`,
`d9e236a4b09c6a281e595d0a6c271a4f99bfe93f`,
`9248a9dc935602e4391375feb9e69630f099db90`.
Frozen helper SHA256 is
`892db7f0f0764d2ab021a0468f498bd19a53455333e40259bd859007639b43a5`;
primary evidence SHA256 is
`d1a03f41f51d5af24739b5782be3b03fd9dca74638badcee13fc3d7a2ef8ce33`;
boundary supplement SHA256 is
`dedddab57b8e5f568bf807badbba8d56bc2f4700409276e8e8dbf2aecb521dae`.

Register experiment `REV046ALLOC-001` against REV-046 before running focused
controls. The review checker uses Python standard library only, reads the two
small existing genuine object files and exact source/evidence inputs, and writes
fresh evidence and corrupted copies beneath this review directory. It never
executes a compiler, linker, assembler, archive utility, section tool, generator,
guest, common check, phone command or any producer entrypoint. Importing the
frozen producer parser for focused copy controls does not invoke its main/run
corpus preflight. Accepted provenance facts remain historical facts; no broad
dependency/header/tool corpus is rerun.

Run from this worktree:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  docs/reviews/vm-033/check.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out docs/reviews/vm-033/runs/review-001
```

The checker has a 90-second deadline, streaming hashes, three >=4 GiB available
memory samples, bounded object reads and a <=256 MiB current-image VmHWM finish
gate. Preserve every failed attempt. No project allocation is requested.

Independently decode Mach-O section/symbol/relocation fields and inline pointer
addends from the real 72,328-byte OSData object and 224,992-byte kalloc object.
Check the actual 192-byte live-support/8-byte-aligned metadata and six unsigned
64-bit pointer relocations, resolving the real `__cstring` names/signatures.
Decode the real kalloc references to all four fixed/variable boundary symbols,
including exact 16-reference count and public relocation types. Compare these
independent byte observations with the frozen producer reports. Inspect the
pinned allocator, loader, relocation and linker recipe sources directly.

Focused controls use fresh copies of the genuine objects: change metadata
section identity/live-support/count, pointer width/type/pcrel/target and bounds;
damage an actual ARM64 addend pair; remove one consumer boundary's references.
Invoke only the frozen parser/predicates or the independent byte verifier on
these copies. Check the actual existing distinct stock compiler identity against
the selected compiler hash without executing it, and bind its historical real
metadata-builtin failure/diagnostics and absence of fallback output.

Preserve the initial ARM64 addend-parser failed run and subsequent passing
supplement. `live_support` is not unconditional dead-strip retention. Final
linked LTO reachability, record/string retention, boundary extents and boot-time
consumption remain unmeasured. This review must not relabel old objects as a new
profile, qualify a final kernel/runtime ABI or close VM-033. Original producer
DO remains sole implementation writer and eventual source-task closer. Deliver
exact review findings/evidence/handoff to INT002/root; hold review closure for
accepted current-HEAD integration/common checks and root authorization.
