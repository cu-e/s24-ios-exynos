# STR-041 handoff

The complete native DEVELOPMENT E1S image is linked:
`artifacts/e1s-native-link/link-001/kernel/kernel.unstripped` in this worktree
(sha256 `4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f`,
21539800 bytes, entry `__start` at `0xfffffff00743b4a8`, no undefined symbols).

This is host-test evidence of one file. Nothing has booted it.

Still open: `check_all_exports` was not run, private37 ABI obligations stay with
STR-037, and STR-024 stays with its Codex owner. The next step toward a boot is a
packaging and loader task, which needs a separately authorized hardware scope for
anything on the phone.
