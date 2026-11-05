# DRV-004 integration handoff

Date: 2026-11-05. Owner: `codex-team-ufs-host-20261105-aw`.
Branch: `team/drv-004-20261105`; worktree: `worktrees/drv-004-20261105`.
Task remains `in_progress` until coordinator review/integration/common checks.
Original DRV-002 dependencies and reserved paths are unchanged. No phone,
MMIO, reset, write/erase/format command, DMA mapping or queue action was issued.

## Delivered boundary

`src/platform/storage/ufs/host.c/.h` is project-authored C11. It admits only
strict READ(10), device-to-host, bounded selected LUN/extent/capacity and
nonoverlapping caller-qualified DMA regions. It builds little-endian UTRD and
PRDT plus big-endian command UPIU bytes. Unknown/write directions, commands,
flags, zero counts, extent/LBA crossing, size mismatch, DMA overlap/alignment
and address overflow fail before state admission.

A serialized single-outstanding lease reserves device ownership before real
backend publication, validates UCD address/SQ ID/LUN/task tag and strict success
response, keeps ownership on stale/malformed completion, and quarantines on
matching errors/timeouts. Separate backend reclaim is required even after
logical success; no hardware quiescence is claimed by a flag. Task tags cannot
wrap within an epoch. Reinitializing active DMA storage is forbidden by the
API contract, and native queue drain/coherency remains a backend requirement.
The fixture resets independent synthetic host states; it is not a native
reinitialization/recovery example.

## Source and licensing qualification

Exact Samsung pin 417484173abc2c4fa93e738ea82ad9f2e84911b1 and E1S pin
c8860decc62c6d6180e609036d027a2997972420 are recorded in the source profile.
Five required Samsung blobs were unavailable with lazy fetch disabled. Only
exact public text was fetched into owned ignored artifacts, verified using
pinned tree Git blob SHA1 and SHA256. Main references were not changed.
Existing four-file cache was retained after one interrupted repeated HTTP read;
the additional UPIU header was fetched separately and verified. Full original
copyright/license notices and raw sources remain in evidence. The oracle
contains unchanged genuine declarations, E1S pure builder and Samsung MCQ tag
function with explicit minimal host adapters; no hardware function is copied
into or run by the tracked implementation. E1S blanket licensing remains
unestablished; no full donor implementation is committed.

`source-notes.md` records concrete donor gaps: CQE/tag/residual qualification,
unsafe retry assumptions, capacity sentinel/GPT prerequisites and the 1088-byte
UCD versus 128-byte-aligned pool stride distinction. BYH3/native inputs remain
explicitly unqualified.

## Actual validation

Main-relative final runtime evidence:
`worktrees/drv-004-20261105/artifacts/ufs-host/final-session2/evidence.json`.
Actual runner exit 0 and 22 checks pass:

- Genuine Samsung layout declarations and command/direction constants compile
  independently; actual donor builder matches 56 complete descriptor/UCD cases.
- Actual Samsung MCQ tag function matches 2048 address/SQ encodings; all 32 queue
  IDs pass the owned completion/reclaim lifecycle.
- The C fixture executes 504318 assertions, 94 guard-page truncation lengths,
  all 255 non-READ opcodes, write/direction/extent/DMA/overflow errors, generation
  exhaustion, stale completions, malformed formats, matching OCS/response/
  residual/sense/flag errors, monotonic time, deadline overflow and quarantine.
- Actual ASan+UBSan executes 100000 seeded random completions with ownership
  retained. Deliberate heap-overflow and signed-overflow controls each exit 1
  with the expected sanitizer diagnostic; successful linking alone is not used
  as runtime proof.
- Owned host.c compiles to an inspected arm64-apple-ios16.5 Mach-O object.
  This is compile-only, with no XNU link, SDK or ARM/native execution.

Command, actual exit 0:

```sh
python3 src/platform/storage/ufs/check.py --run final-session2 --lab-root /home/egor/dev/pet/s24-ios-exynos
```

The final capsule retains exact tested sources, original primary inputs,
generated oracle, commands/exits, compiler identity/hash, diagnostics and
artifacts. Initial run also passed; its first registry submission was rejected
because metadata omitted `summary`. The unmodified initial runtime capsule is
linked by `initial-registration/evidence.json`, which supplies the missing
metadata; no failed runtime is relabeled. Final-session1 passed before adding
explicit Qualcomm GPL notice preservation to the generated oracle prefix;
final-session2 tests the exact final source/profile bytes.

A post-commit provenance capsule binds these tested bytes to the owned commit
without repeating successful runtime checks. Acceptance is assessed satisfied
for all three source/host criteria, subject to coordinator review.

## Integration and remaining gates

Cherry-pick the scoped commit. The new fixture lives inside the assigned source
boundary, so main unittest discovery does not automatically run it. Coordinator
review should run the explicit runner with a fresh name and source cache, then
main `make check`. No tests, fixtures, src/xnu or patches/e1s files were changed.

The next DRV-002 backend needs independently qualified capacity/GPT/LUN policy,
real DMA/IOMMU regions, cache/barrier semantics, queue publication/consumption,
and safe drain/ownership return before reuse or epoch reset. Error/timeout
quarantine has no recovery path in this boundary. BYH3 PHY/MCQ handoff, native
kernel linkage/execution and Android userdata decryption remain unverified.
No native phone action is authorized by this handoff.
