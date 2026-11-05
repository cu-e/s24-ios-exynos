# VM-036 isolated correction: independent acceptance

Accept source correction `d5553d007ff1da656b3702ce84f92b67df77ce5b`, adapter
SHA256 `3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f`,
with documentation through fd5ae558. All three reproduced P2 findings are
resolved; no unresolved P0/P1/P2 remains in this bounded corrected-adapter
review. The old 5152 source, failed review and original worktree are preserved.

Object bytes now enter one bounded sealed memfd. Structural validation, digest,
sections, symbols and probe data all consume that immutable snapshot. The real
pathname-replacement counterexample cannot borrow provider symbols, writes to
the captured fd fail with EPERM, and good captured metadata cannot authorize
different restored archive-member bytes. Probe payloads remain snapshot-bound.

Archive inspection restricts genuine TOC names, bounds BSD names and payloads,
checks TOC structure/member offsets/string ranges and keeps hash/parsing on one
stable open file. The original hidden-prefix counterexample and negative name
extents reject. A real qualified cctools archive remains a positive format
witness. The historical NDK llvm-ar archive is a different format, not relabeled
as the selected tool; no archiver was run for this review.

Host executables and libraries now bind their expected content digest, dev/inode,
size and nanosecond timestamps with ELF facts from the same open descriptor.
The owned real-tool-copy append and actual path replacement both reject;
same-content rewrites change runtime identity. No original tool was changed
and no copied tool was executed.

Independent PLATCOMP-002 passed 21 targeted regressions, exit 0 in 0.564 seconds,
peak controller-plus-owned RSS 49213440 bytes, child VmHWM 27368 KiB, and no
owned survivors. Stable three one-second samples passed 4 GiB admission. The
author's 38 focused controls and preserved baseline88/followup12 are separate;
they were not rerun wholesale. AST comparison confirms only the six intended
old parsing/inspection functions changed; original authority, recipes, process,
dependency and quarantine functions remain unchanged. Policy acceptance is
still explicitly false. Evidence and all raw commands are in evidence-pass2.

This accepts the implementation at source stage. It does not adopt the
quarantined VM-037 API, grant a component lease or prove compilation, linker
closure, callback/alias ABI, kernel startup, private Apple SDK/ABI, native
hardware, FIPS or side-channel safety. Actual component units require a narrow
independently accepted process-policy update and new original-owner plan/root
allocation. Original dz alone closes VM-036 after the required integration
and root acceptance; original cx/cy retain component measurement ownership.
