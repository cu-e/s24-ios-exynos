# VM-036 P2 correction handoff

Original owner: `codex-guest-next-executor-20261106-dz`. Keep `in_progress`.
Independent recheck/root acceptance is pending. No component execution is admitted.

Source freeze: `d5553d007ff1da656b3702ce84f92b67df77ce5b`, based on
`df11548f2c31ba4434d290ba353a0e4e962730f3`, in
`worktrees/vm-036-dz-fix2-20261106`, branch `team/vm-036-dz-fix2-20261106`.
Adapter SHA256: `3ae89e8a19f239a762580b818ab45602721257a528ecf6f9b7a3db54e1735c4f`.
The earlier `vm-036-dz-fix1-20261106` physical source remains exactly
`5152e733f95da9b0d2a01da6e1eb9b1b22d9bd75bc47187387e19d29e515d718`.
All 125 prior artifacts and source bindings were rehashed unchanged; historical
88+12 checks and their failures remain immutable and were not rerun.

Three independently reproduced P2s are corrected:

- Object validation/hash, sections/symbols and probe bytes now use one bounded
  sealed memfd snapshot. Actual source-path replacement cannot mix identities;
  an actual pwrite attempt receives EPERM. The accepted Mach-O helper is unchanged.
- Archives permit only four exact source-backed TOC names and validate counts,
  strings, sorted names, padding and real member offsets. Unknown prefixes,
  duplicate/nonleading TOCs and negative/zero/nondigit/oversized BSD name extents
  fail before unsafe reads. Archive hash and parsing share one stable descriptor.
- Runtime bindings include actual executable/library SHA256 and stable identity;
  ELF metadata and digest share one streamed descriptor. An owned real-tool copy
  append is rejected, a same-byte rewrite changes its frozen identity, and a
  parse-time pathname replacement fails closed.

`AVFCOMP-002` focused controls002 passed 38 checks, exit 0 in 0.35095 seconds,
with sampled controller-plus-child peak 54,337,536 bytes and zero survivors.
The first failed format-witness run is retained: its archive was made by NDK
llvm-ar rather than the selected cctools. The genuine format witness is the
historical source-built MACHOTOOLS-004 `fixtures/libfixture.a`. Historical
objects/archives/tools are parser and negative controls, never new guest products.
Two complete primary cctools files match canonical Git blobs at
`904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb`; the tracked source fixture records
full SHA256 values, file extents and the actual guarded Git command.

Final capsule:
`worktrees/vm-036-dz-fix2-20261106/artifacts/avf-guest-components/handoff-003/evidence.json`
SHA256 `903370a0613e1e3c1c415d9910916d93645ec325879bf788f636b9b1afad8454`.
It indexes 147 artifacts, including the independent failing counterexamples,
preserved prior capsules, the failed run and the passing focused run. The tracked
`prepared-adapter.json` points to this source/capsule with execution_qualified=false.

Only six existing parser/runtime functions changed; execution, owner/resource
checks and quarantine remain AST-identical. No compiler, archiver, loader,
QEMU, phone action, common check or shared source/namespace write occurred.
The process policy remains hard-refused with independently_accepted=false.
Await the one final reviewed VM-039/helper SHA and root common acceptance before
any explicit prospective policy adoption, original-owner source plan refresh
or root allocation. Actual component objects/dependencies/archives, tool load
mappings, callback/layout/VM aliases, full-kernel/native/private-ABI/FIPS gates
remain unmeasured or unqualified.
