# REV-018 independent GCM review procedure

Owner `codex-team-review-gcm-20261105-ce`; source-review only, with one bounded
independent sanitized host probe. Frozen implementation series:
`245299afcaab8e995c04a2e86b50d793e9102453`,
`f845dc66ff0124bcdbfe36965c95ce18c3da7c8c`,
`d8a9fd106edaa4d3140503237ba6dd99db92b33f`.
Only this review directory may be changed. Shared inputs and implementation
worktree remain read-only with Git lazy fetching and optional locks disabled.

GCMREV-001 prospective procedure:

1. Audit full canonical Mbed member/license/profile identities and the genuine
   selected XNU callback/helper/caller declarations. Trace descriptor-sized
   allocation, inline pointer-free state, ownership, nonce phases, carry and
   exhaustion, reset/reconstruction and external uniqueness limits. Inspect
   actual corpus selection/oracle and host/ARM/control/continuation evidence;
   rehash original artifacts rather than rerunning the full matrix.
2. Independently compile one small probe against the genuine selected headers,
   and link only hash-verified existing sanitized GCM/AES/zeroizer objects.
   Allocate actual descriptor-sized/aligned contexts with guard bytes. Test
   known NIST AES-GCM bytes, immediate partial/in-place output, authentication
   failure and computed-tag overwrite, context/input/output alias admission,
   zero-length/phase errors, managed nonce key/IV copies, salt/carry/reset,
   live reconstruction/copy/mixing/exhaustion and error snapshots.
3. Before each compile/run require MemAvailable >=4 GiB. One compiler job only;
   monitor the owned process tree and stop above256 MiB RSS or finite timeout.
   No full vector repeat, backend/kernel rebuild, QEMU or device work.
4. Preserve commands/exits/source/tool/hash/memory evidence and cleanup, report
   concrete findings with reproduction or a bounded no-finding assessment,
   commit only review files and retain in_progress for root acceptance.

No provider/full-kernel/native/private-ABI/FIPS or end-to-end side-channel
qualification follows from this review. Decrypt output stays provisional
until successful authentication; external persistent nonce uniqueness remains
the caller's responsibility.
