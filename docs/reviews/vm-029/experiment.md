# REV-033 prospective independent review

Owner codex-review-boot-gates-20261106-ec; task REV-033; worktree
worktrees/rev-boot-ec-20261106, branch team/rev-boot-ec-20261106.
Review only docs/reviews/vm-029; producer remains read-only. Subject full commit
5974ab73d5beebb43c170231f4c9533214bf3941, implementation predecessor
b4ae11ed2db7d248e5c8d594d3d5b6a8d3a163d1, producer worktree vm-029-20261106.

Before any verification child, register REV033-001 through sole MAIN CLI and
independently verify saved owner/task/planned entry. Preserve all prior producer
and reviewer failures and keep task in_progress until coordinator acceptance.

Review exact committed Python/JSON/docs and actual pinned guest GIC, timer,
configuration, shim conversion, QEMU source and manifest recipe bytes. Independently
trace GICv3 selection, timer PPI27, CPU/PSCI and physical MMIO/DT arithmetic,
initialization and IRQ acknowledge/dispatch/EOI ordering, controller SPI
intersection32..287 versus guest32..1019/48 simultaneous slots. Verify all19 source/
tool/config descriptor hashes and actual recorded controls/artifact identities.
No source token ordering is treated as preprocessing or runtime interrupt proof.

Targeted checks: import the exact committed inspector without running main; compare
its launch predicate against an independently authored narrow declarative model.
Use boundary32/287/31/288/1019, duplicate/boolean/scalar/malformed SPI cases and
closed-shape/type/config negatives, plus one bounded real CLI accepted launch and
real CLI rejected boundary input using existing pinned source. Mutate only owned
review copies, never producer/shared source. Preserve actual outputs/exits and
check no compiler/linker/QEMU/common/phone process is invoked. Bound each Python
child to30seconds and<=256MiB current-image RSS where practical, no global install,
shared promisor hydration or Git optional locks. Stop on any unexpected execution
or tool-control rejection; report findings promptly to root/INT002.

Dated evidence must name exact commit, code/tool hashes, actual commands/exits,
case results, artifacts and limitations. A bounded no-finding verdict establishes
only this preboot source/declarative contract. Clock rate, timer delivery/rearm,
EOI behavior and actual XNU boot/console/MMU remain unobserved and require later
separately leased runtime evidence. No compiler/link/QEMU/common replay is allowed
in this review, including make check; the explicit coordinator restriction governs.
