# REV-043 bounded independent VM-023 review

Reviewer `codex-review-guest-runtime-20261106-ex` atomically claimed REV-043.
Fresh branch/worktree: `team/rev-vm023-ex-20261106` /
`worktrees/rev-vm023-ex-20261106`, based on MAIN
`b000b0af2e67212e4c75a217f2b38467e820268a`. Only `docs/reviews/vm-023` is owned.
Producer DE remains the sole implementation writer and eventual VM-023 closer.
VM-015 is DONE and VM-042's independent source plan remains untouched.

Frozen producer HEAD is `8eefa50abe26ec9e8e8368fea82bc06465841441`;
implementation is `0e44b04827b4c3258ed0f7bd724d03acc728bf26`.
Producer maintained evidence SHA256 is
`feaf78a5050c239f144a1ab56e5bfd481c660a3d2e0347a5c33a3088ab48ce18`.
Read its handoff, README, exact implementation and reused pinned archive parser.
No source mutation, producer CLI invocation, compiler-driver rerun, corpus
rebuild, compiler/assembler/generator/archive/linker/section tool, QEMU, phone,
common checks or root allocation is authorized.

Prospectively register REVVM023-001 before running the pure-Python controls.
The bounded review streams all input hashes, independently walks the 219,448-byte
archive framing and binds all 287 member bytes to the accepted member index.
Inspect ARM64/platform/symbol metadata using the already pinned parser, compare
actual symbol sets and preserve the 47 unresolved archive-wide imports. Verify
the existing 287 source/recipe witnesses and their source digests against the
saved original/corrected reports, including generated outline-atomic wrappers
and the already accepted unsigned-shift correction. This reads existing bytes;
it neither rebuilds nor reruns the producer's qualification program or corpus.

Challenge bounded owned copies of genuine archive/member bytes with malformed
framing, extended-name bounds, CPU/platform and symbol-table/string bounds.
Independently parse the existing two final driver stderr files and compare them
with the recorded backend argv. Require the exact qualified linker and archive
once in the positive record, no unresolved `-lcc_kext`, and omission in the
missing-root record despite exit zero. Reject missing-root evidence presented
as a positive admission, duplicate archive tokens and foreign same-basename
archives. No driver is executed for these controls.

Recheck the exact driver-source snippets responsible for reserved-name rewrite,
resource directory construction, iOS archive selection and missing-file omission.
Inspect the immutable guest graph and its header/resource separation without
granting the runtime root compiler-header or namespace qualification. Existing
failed/inconclusive producer runs and original runtime semantics failure retain
their identities; source/archive lookup is distinct from full guest archive
member selection, final dependency closure, runtime execution and private ABI.

Controls run in the owned review directory with fresh output, a finite
90-second Python deadline, three stable >=4GiB admission samples and <=256MiB
current-image VmHWM. They start no child process. Preserve failed attempts,
commands, exit codes, source/tool/output hashes, current-image memory and the
bounded verdict. Send any actionable finding to producer DE and INT-002/root.
Freeze docs/evidence/handoff for independent integration; do not close REV-043
before accepted current-HEAD integration/common and explicit root authorization.
