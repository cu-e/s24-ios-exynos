# REV-031 handoff

Original reviewer owner: codex-review-boot-gates-20261106-eb. Worktree `worktrees/rev-boot-eb-20261106`, branch `team/rev-boot-eb-20261106`. Own only `docs/reviews/vm-026`. Task stays in progress.

P2-ENTRY-ALIGN is open against exact VM026 code ffd08db8616f7a486762b951dc69a9ace8716dea / metadata a47a378dac38a0e86f6e7abd66c12f28390fa245. Three independent byte fixtures pass with unaligned PC; actual unchanged CLI returns0/pass for one. Findings and source audit are in README.md. Root, INT002 `/root/lab_worker`, and original dh producer `/root/guest_exec_14` were notified. Producer is preparing a separate alignment-correction worktree; original witnesses remain immutable.

Experiment REVBOOTMEM-001 was registered and verified before checks. Final failing review capsule: `artifacts/rev-boot-memory/20261106-receipt1/evidence.json`, SHA256 aa1f3b0601d49318e326cd9225b6fe5b9b9762f65898c2d3490cafcda99daa86. Twelve focused Python cases, actual CLI invocation, exact commands/exits,30 original artifact hashes and source/tool hashes are retained. Initial reviewer harness KeyError was corrected; original partial failure retained. No compiler/QEMU/common/phone ran.

Next: inspect producer's exact frozen correction and fresh prospective evidence, then register a bounded follow-up before checking the same independent byte fixtures and corrected CLI. Preserve original finding and failures. No broad matrix or runtime repetition. Send final review commit and exact capsule to root and INT002; wait acceptance. A real final kernel/XNUP and later actual runtime FDT/MMU/allocator/RAM checks remain unmeasured. Existing REV022 stays original cl ownership and pending integration, unchanged.
