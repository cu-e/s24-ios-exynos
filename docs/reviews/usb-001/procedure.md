# USBREV-001 independent review procedure

Date: 2026-11-05. Owner: `codex-team-review-usb-20261105-ao`.

Review only commit `e1785878045751213cb1e8e49e42a364333ed496` in
`worktrees/usb-001-20261105`. Never change implementation or donor checkouts.

1. Inspect the protocol, integer extents, disconnect/error/reconnect ownership,
   test runner, source profile and evidence. Check both pinned donor revisions
   and per-file license notices. Distinguish host/source claims from hardware.
2. Audit every existing host-session5 artifact hash and compare executable
   source snapshot bytes with the reviewed commit, accounting for final prose.
3. Extract exact committed sources into reviewer-local ignored outputs. Build
   and execute the existing fixture with NDK27 host ASan+UBSan, then execute
   both deliberate fault controls. Require actual expected diagnostics.
4. Build one unsanitized shared object and independently compare DMA admission
   and output addresses with Python arbitrary-precision inclusive intervals,
   including zero sizes, address-width boundaries and overflowing windows.
5. Record actual commands/exits, tool versions, source/artifact hashes and
   results in dated evidence and an actionable review report and handoff.

Use sequential compiler commands (at most one compiler at a time). Bound each
command to 45 seconds; no heavy builds, phone, ADB, root, MMIO, flash, emulator
or global installation. ASan reserves virtual memory; do not limit its address
space to 1 GiB because that would prevent its runtime from starting. Record
actual child maximum RSS and fail if above 1 GiB. The coordinator owns shared
repository checks after integration.
