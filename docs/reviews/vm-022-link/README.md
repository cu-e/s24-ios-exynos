# REV-041 independent main-link review

Do not accept or execute the frozen main-link candidate
`dc7f669a5a5218ce447f9c98d6cefa3230a42452`, helper
`6061ab8717590b1db02ef8d404071ce3345d35eb4a987c2fed0b3d83301e3006`.
The registered source-only experiment REVMAIN-001 ran 73 controls:
55 passed and 18 failed. Both commands exited 2 as intended for failed review
conditions. No target tool, production allocator, kernel, payload production,
QEMU or common check ran. All producer freezes and failed witnesses remain
unchanged. A corrected candidate requires a new physical freeze and review.

Task owner `codex-review-link-main-20261106-eu`; worktree
`worktrees/rev-vm022-link-eu-20261106`, branch
`team/rev-vm022-link-eu-20261106`, base MAIN
`b000b0af2e67212e4c75a217f2b38467e820268a`.
Only `docs/reviews/vm-022-link` is maintained by this reviewer.
Original REV-039 remains done and its accepted tail source/evidence unchanged.

## Blocking observations

1. **Original object admission does not close ownership or input-key identity.**
   Real `validate_graph`, `expand`, `reusable`, dependency parsing and streamed
   hashes from explicit frozen AF193 were exercised against the actual 1080-row
   source graph and one authored object/MD fixture. Eight contradictory variants
   reached the *missing other 1079 IDs* boundary after per-object credit: wrong
   literal owner, wrong literal task, absent literal reservations, source-only
   raw flag, compiler-never-started flag, wrong raw compiler hash, wrong plan
   compiler hash, and an arbitrarily replaced matching sidecar/plan input key.
   This is a predicate-isolation fixture, with an explicitly temporary in-memory
   profile pin restored to empty afterward. It supplies no actual object,
   accepted profile, full-corpus or root-approval credit. The independent
   acceptance file does not replace checking original execution ownership,
   qualified provenance and derivation of the original key. These checks belong
   in `admission_inputs`, before staged use.
2. **Parsed bytes and returned digests can identify different files.**
   `bounded_macho` and `inspect_xnup` close their parsed stream and call
   `sha(path)` separately. At that exact boundary, a real `os.replace` changed
   the path to a non-format file. Both returned the old accepted metadata and
   size with the new invalid file's real streamed SHA256. No read was bypassed.
   Use one bounded regular-file descriptor/snapshot for parsing and hashing,
   including post-read FD/path identity closure and finite bounds. The image
   witness returned size 1536 with a digest belonging to a 27-byte invalid file;
   the payload witness returned size 1632 with an 11-byte invalid-file digest.
3. **Transform verification accepts trailing bytes after its size comparison.**
   With `verify_segment_processing(original, result, [])`, a real 19-byte append
   after `stat` equality and before the actual result open/read changed 1536
   bytes to 1555. The function returned success because it compares only the
   original-length prefix. Require bounded descriptor reads, exact EOF and
   source/result size and identity closure, including actual concurrent growth,
   shrink and path replacement. The already accepted constructor helper has
   stronger closure; this new generic helper does not inherit it automatically.
4. **Final image section/mapping validation is incomplete.**
   Three real MH_EXECUTE file mutations were accepted: a section claiming
   `__DATA` inside a `__TEXT` command; section file bytes outside its parent
   segment's stored span; and a section file offset inconsistent with its virtual
   mapping. All retain a valid `__start`/UNIXTHREAD equality, showing that entry
   checks alone do not close the actual loaded entry/metadata bytes. Enforce
   image-specific parent names, file/VM containment and mapping relationships;
   preserve legitimate MH_OBJECT conventions separately.
5. **XNUP admission has no typed successful link-phase contract.**
   An explicitly fictional same-byte accepted record with wrong schema/task,
   source_only true, wrong executor and both link/archive-started flags false
   crossed `execute_xnup`'s current producer predicates and reached the
   `project_approval` sentinel. The sentinel raised immediately: no real grant,
   constructor, reservation, output directory or child existed. Actual root
   approval remains a separate gate. Require exact actual phase/schema,
   executor/profile/plan/command/archive identity and complete product closure
   before asking the budget layer to approve packaging.

## Product obligations and resource diagnostic

The new main-link phase has no final allocator validator. Input `common.macho`
hashes allocator section bytes; it does not resolve allocator record pointers,
string contents or source-to-final retention. Generic final image inspection
does not require this metadata. The historical VM033 resolver's zero-inline-
addend assumption is not adopted by this candidate, but there is no replacement
validation. A new object with nonzero addends needs relocation-aware resolution,
or an explicit closed witness gate with no generic product claim. Preserve the
actual accepted source metadata, record fields and resolved string/pointer
lineage into final mapped image bytes; malformed or discarded metadata must not
qualify an image through JSON assertions.

Actual selected runtime archive members and imports remain explicitly
unmeasured. The vector has no map collection and the passing phase report sets
`actual_selected_archive_member_imports_unmeasured=True`. That disclosure is
honest; it cannot qualify a complete product. Future closure needs a measured
linker map/trace tied to the exact 287-member runtime archive, selected ordinal
member hashes and actual import/definition obligations, with the resulting
image digest. Archive-wide candidates do not establish selection. Keep complete
product/package eligibility closed while allocator or runtime closure is absent.

A 17,500,057-byte object containing 700,000 unique legal-count external symbols
raised `MemoryError` under the preregistered 192 MiB address-space containment.
The child current-image HWM was 192,262,144 bytes; its parser completed the
failure in 0.847 seconds. This establishes failure within the review limit, not
an observed production 512 MiB overrun. The current 2,000,000-symbol and 64 MiB
string limits do not derive Python dictionary growth from the active controller
budget. Compact bounded representation, budget-derived cardinality and finite
whole-parser work are required before claiming bounded production parsing.

## Established positive controls

All inherited tail/cancellation function/class ASTs except the CLI dispatcher
match exact accepted helper99d8. New production wrappers preserve deferred
reserve ownership, caught shared-runner cancellation, release/evidence deferral
and prior-handler restoration. The accepted real cancellation/constructor
results are reused by this exact identity; no cancellation test was represented
as fresh target execution. Original tail grant25 receipts remain separate.

Both full source-vector reconstructions match their frozen link and XNUP plans.
The 1080 ordered unique IDs, eight component commands, 1083 archive cardinality
and nonlto exclusion remain source-derived. DEVELOPMENT has no forced RELEASE
export list or undefined-symbol suppression. Empty profile selection refuses
before corpus access. Real authored object/image/archive/XNUP positive cases and
malformed entry, source, argv, live-process, cross-profile, duplicate-object,
archive truncation and payload cases were exercised. The ordinary file
descriptor count was unchanged. No authored binary fixture is a kernel.

AF193 is imported explicitly from this review worktree only for fixture APIs;
the production candidate retains its original canonical AF193 binding.
MAIN may now advance to BFA8. No old policy path, namespace or receipt was
silently rebound. Future production adoption requires independently reviewed
unchanged-byte historical path qualification where applicable, or fresh inputs
under the final accepted policy/profile. Production profile pins remain empty.

## Evidence and reproduction

Read `evidence.json`, `experiment.md`, `review.py` and `admission.py` here.
Retained artifacts are under this review worktree's
`artifacts/rev-vm022-link/{controls-1,admission-1}` with command stdout/stderr
alongside. The scripts contain exact real mutation barriers and fictional
acceptance boundary fixtures. Both source controls are finite Python/tempFS
operations only. The sole child is the eight-second contained symbol parser;
`subprocess.run` reaped it with exit 0 after it recorded the MemoryError.

Current-image controller HWM was 44,838,912 bytes for controls-1 and
128,090,112 bytes for admission-1. The sum of controls-1 controller and contained
child HWMs is a conservative 237,101,056-byte upper bound, below the registered
256 MiB combined limit; it is not a sampled simultaneous-RSS measurement.

Author `/root/guest_exec_01`, root and INT002 received the failures, exact hashes,
barriers and correction expectations. Next: review a separately frozen corrected
candidate with focused counterexamples, maintaining all closed product gates.
No task completion or actual link permission is requested by this report.
