# REV-027 independent PID1 admission review

No actionable finding was identified in the exact prospective implementation
3fdc1f0ae467792135c32eea57a486cbbb58612c ->
1610ed23e716a8f5c229d6d77677142f96cb7995 ->
cdcaebaf759d4f4a62a20959fda5bd024ceb203f. The bounded host admission route
passes independent review for the exact fac53 candidate only. This does not
repeat or expand REV-026's compiled ABI review, and establishes no runtime result.

Original reviewer owner codex-review-boot-inputs-20261106-du atomically claimed
REV-027. Worktree/branch: worktrees/rev-boot-du-20261106 /
team/rev-boot-du-20261106, base fd20170. Only docs/reviews/vm-025 changed.
REVPID1ADM-001 was verified planned before execution. No producer edit, compiler,
binary inspection program, executable image execution, QEMU, MAIN publication,
common check, SDK, phone or ADB operation occurred.

The prospective source and fixture are physically in
worktrees/vm-025-admission-20261106. The original
worktrees/vm-025-20261106 remains a historical raw-build witness at 2b11bcf.
Its tool, fixture and inconclusive evidence match the original hashes before and
after this review. The registered original admission-002 procedure stays present
at its physical path and unchanged. The current prospective fixture preserves
the literal original eighteen input records plus historical compiler (nineteen
original hashes), appends new source/review/build and historical-witness records,
and verifies forty-one inputs in total. All hashes stream, including the large
historical compiler, which is never executed or approved for future compilation.

Independent verification passed 132 checks: all forty fixture file bindings plus
the historical compiler, fifty continuation-index artifact hashes, exact current
source/fixture/evidence Git bytes, literal historical prefix, full candidate
allowlist identity, prior compiled review pins, actual image/header/entry mapping
and historical physical-witness stability. The image is exactly
fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3;
source hash is
68de57b2e27480f39cabdcf1372176ddbf8e275b9c5309c2ac529c6e0be01190.

Nine fresh real CLI cases passed their expected outcomes:

- The unchanged reviewed descriptor returns exit 0, compiled-only, forty-one
  input records, and every runtime qualification flag false.
- Default legacy and legacy mistakenly inserted in the qualified list both
  return exit 2 with rejected admission. Legacy precedence occurs before
  endorsement processing and cannot become a success through that list.
- Added descriptor whitespace preserves the JSON object but changes its raw
  bytes; it returns exit 1 at the descriptor digest gate.
- An extra object field, a byte-identical source at another path, and a genuine
  instruction mutation with a recomputed image hash return exit 2 as unqualified.
  Structural eligibility or newly supplied hashes do not confer admission.
- Changed metadata in the historical input prefix and an endorsement digest
  substitution each return exit 1 with the specific baseline/binding diagnostic.

Three additional independently authored actual-image mutations reject wrapping
VM extent, inconsistent section count and a duplicate valid thread command in
real header padding. These narrow checks complement the exact-image hash gate;
the parser remains a deliberately limited Mach-O policy, not a complete loader
or arbitrary-executable ABI verifier. The controller current-image VmHWM was
22,016,000 bytes; the largest fresh CLI VmHWM was 21,970,944 bytes. The sequential
review ran under a 256 MiB AS cap and finite process timeouts.

A separate read-only lineage audit verified the eleven preserved producer CLI
reports (ten expected nonzero exits) against the exact initial 3fdc1f0 source
hash, and all seventeen preserved real-image corruption rejections. The fresh
continuation positive binds 1610ed2 source, compiled-only and forty-one inputs.
The initial UUID-assumption driver failure remains indexed and preserved; no
historical result was rewritten, relabeled or claimed as rerun after restoration.
Local mutated binary/source copies are ignored by Git, retained at their recorded
physical paths, and hash-bound by evidence. Reproduction lives in verify.py.

The source checks full descriptor equality, raw descriptor SHA256, exact reviewed
endorsement and its pinned evidence/admission/raw-build chain. The original
physical baseline is separately pinned and tied to raw-build tool/fixture
witnesses. All runtime flags remain false. This admission does not qualify the
selected kernel, source-built tool reuse, stack mapping, exec/signing policy,
console/sysctl execution, PID1 identity, boot, panic/PSCI stop, Apple launchd,
iOS, private ABI or S24 behavior. Mockfs raw packaging is independently reviewed
under REV-028; its artifact binding here adds no runtime claim.

Submit this scoped review/evidence to kernel integrator INT-002 and root. Only
integrators publish exact reviewed candidates and run serialized fresh MAIN
common checks. Keep REV-027 and VM-025 with their original owners until root and
integrator acceptance; no task completion follows from this review alone.
