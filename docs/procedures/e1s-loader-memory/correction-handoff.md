# STR-002 correction handoff

Owner: codex-e1s-memory-20261106-sr2. Worktree:
worktrees/str-002-e1s-memory-fix1-20261106; branch:
team/str-002-e1s-memory-fix1-20261106. Parent source commit is
6a1c05d4119acd5146d56d7fc9070742584140cd; its original physical worktree remains
frozen. Production patch 23b31c44, harness 46d5e384 and source manifest f0a09bdd
are unchanged. Only the preparation checker and correction documentation differ.

The actual first original-compile failure is preserved in
failure-001-evidence.json and the root raw evidence/log it binds. STRMEM-001 was
recorded fail; STRMEM-002 was registered planned. At that planning boundary no correction compiler or control had run.
Root subsequently admitted STRMEM-002 once: all six commands passed; see
evidence.json for actual commands, logs, source/runtime/output hashes and cleanup. The initial evidence-record CLI schema rejection
is also retained; the conventional wrapper subsequently recorded successfully.

The selected six-command plan and exact resource contract are in
procedure-002.md. Root executed plan cb3b5d9f with checker 57e1aae0 once under grant36. Earlier correction plans remain unexecuted and superseded.
The actual baseline reproduced six defects; patched actual C passed35 controls
under ASan/UBSan. Both patched files compiled to ELF64 ET_REL/EM_AARCH64 objects.
All24 input hashes and all4 output hashes match. Next: independent code review
and root acceptance; do not repeat commands or close the task before acceptance. No task completion,
ordinary builder application or hardware safety claim follows from preparation.

The original attributed patch contains literal unified-diff whitespace. Preserve
its exact bytes: the whole outer diff check reports context-prefix whitespace;
the exact one-path exclusion for patches/e1s-boot/0001-loader-memory-validation.patch
passes. Do not rewrite donor context to hide that recorded formatting exception.
