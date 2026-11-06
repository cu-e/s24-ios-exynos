# VM022 bounded tail execution correction

Original owner: `codex-guest-exec-20261106-cu`, task `VM-022`.
Correction worktree: `worktrees/vm-022-execution-20261106`, branch
`team/vm-022-execution-20261106`, based on `6735a6a`.
The previous preparation, text outputs and final-plan evidence stay frozen in
`worktrees/vm-022-20261106`. This correction does not remeasure its194 objects.

The previous helper emitted a static plan only. Its four top-level compiler
recipes contain nonexistent query-only `preparation-4/EXPORT_HDRS` and
`preparation-4/san` paths. They came from the query's isolated `OBJROOT`.
The new `tail-plan` mode resolves only those Make-derived prefixes to the
`OBJROOT` assignment in VM008's original successful query (`handoff-1`).
It also applies the exact accepted VM038 old-to-new include root substitution,
resolves fresh version.c, and redirects only dependency/object outputs.
Every original argument, ordered substitution and resolved argument is saved.
No new include root, component CONFIG_DEFINES, metadata relaxation, SDK header,
native object, or old archive is introduced. Genuine tail compilation may
still fail; a successful source plan is not a measured compile.

`execute-tails` reconstructs the entire deterministic plan from pinned inputs
and requires equality before invoking the accepted AF193 project-budget API.
Its label is `guest-link-tails`. It uses the common supervisor, same-byte JSON
loader, source namespace validator, dependency parser, Mach-O object validator,
write confinement, stable memory admission, process cleanup and project budget.
Source-context contains version.c only; all objects, deps, logs, temp/home and
raw constructor bytes remain outside the include cwd. Before every compile and
after all processing it rejects newly shadowing, missing or changed inputs.
Actual compiler dependencies must all match the accepted namespace receipt.
Tool/source/sanitizer/rule bytes are checked before and after production.
The sanitizer digest is the unchanged entry in the accepted VM038 artifact
index (`handoff-1/san/kasan-blacklist-arm64`), not an invented policy.

Four commands preserve top-level C_RULE_1A exactly: nonlto.o, version.o,
lastkerneldataconst.o, lastkernelconstructor.o. The genuine source-built
setsegname then renames eligible constructor section segment names from
`__DATA` to `__LASTDATA_CONST`. The raw object is retained; every transformed
byte is compared against that source-defined operation, including the required
constructor section. Each measured object and depfile receives its own hash.
Reports distinguish current-image `/proc` VmHWM from inherited raw ru_maxrss.

## Source-only experiment AVFLINKTAILPLAN-001

Hypothesis: the accepted genuine tail recipes can become a finite separately
leasable executable phase with only source-derived root/output substitutions,
without launching a target tool or rehashing the historical object corpus.
Before running, register this procedure through MAIN tools/lab.py and update
the original task's worktree metadata to this correction worktree.

Run the source-only fixture controls, then generate the plan:

```sh
python3 -s fixtures/public/avf-guest-link-inputs/check-tails.py --main /home/egor/dev/pet/s24-ios-exynos --vm008 /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-008-20261105 --out artifacts/avf-guest-link-inputs/tail-controls-1
python3 -s tools/build/avf_guest_link_inputs.py --main /home/egor/dev/pet/s24-ios-exynos --vm008 /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-008-20261105 --out /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-022-execution-20261106/artifacts/avf-guest-link-inputs/tail-plan-1 --execute-out /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-022-execution-20261106/artifacts/avf-guest-link-inputs/tails-execute-1 --mode tail-plan --experiment AVFLINKTAILPLAN-001
```

Expected bounded outcome: four source-supported commands, exact finite token
changes, all invalid controls rejected, no target child/process and no actual
tail object/archive/image. Time budget120 seconds, controller256MiB. Preserve
failures, exact plan hash, helper bytes and current-image memory observations.

## Separate execution admission and remaining sequence

An independent review of this exact executor and root allocation binding the
exact plan/output/owner/new production experiment must precede `execute-tails`.
Its CLI additionally requires `--source-plan`, `--source-plan-sha256`,
`--approval` and `--approval-sha256`; the shared root grant fixes the selected
slot and project budget.
The source-only experiment cannot authorize execution. No production was run
while preparing this correction. A planned output path grants no permission.

The next distinct `guest-link-stage` implementation must consume accepted
actual shard receipts for all1080 IDs, measured accepted tail objects and
Firehose/pthread component capsules. The existing final-link-plan records the
genuine source sequence: copy immutable originals; perform14 HIB transforms,
libsa bootstrap.cpo's two KLD passes; produce the eight component filelists in
source order and concatenate1080 entries; stage exact accepted provider archive
members; run the genuine DEVELOPMENT direct image link with VM023's link-only
cc_kext resource directory; only after successful image produce the genuine
1083-member static archive (nonlto remains outside that archive).
That complete stage executor is still missing. This correction deliberately
provides only the nearest independently executable four-tail phase.
The exact previously measured final sequence remains available at
`worktrees/vm-022-20261106/artifacts/avf-guest-link-inputs/link-plan-2/final-link-execution-plan.json`
(SHA256 `a14c985397c125f99ae94007454021bd6b17a5ad10166c1441fb6b9eead4567c`).
Its194-object snapshot and seven unresolved queued output roots are historical;
new current owner receipts must replace those admission inputs before linking.

Link success must precede actual ARM64 MH_EXECUTE/entry/segment/definition/
extent checks. The frozen source-supported route is genuine uncompressed
Mach-O to Scion mkpayload.py XNUP kernel entry to the existing source-built AVF
shim Image. There is no extra kernelcache/IM4P conversion in that route.
Packaging needs its own bounded admission; runtime additionally needs the
exclusive root QEMU lease and reviewed memory/MMU/DT/PSCI/console/stop gates.
Console without an accepted PID1/mockfs root cannot satisfy full VM002.

## Frozen source-only result

Final executor SHA256:
`67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f`.
Final plan is `artifacts/avf-guest-link-inputs/tail-plan-3/execution-plan.json`,
SHA256 `d67ab9e647c7f468a1cd8b789884c5f97e3ddaa3d0a26e0831e24af66e65d499`.
The final24 source-only controls at `tail-controls-4/evidence.json` passed.
The plan generation and controls both exited0; maximum measured current-image
VmHWM was38227968 bytes. Inherited raw ru_maxrss was1380720640 bytes, and is
reported separately. No target tool ran; `tails-execute-1` remains absent.
Earlier source-only attempts are preserved and explicitly superseded.
Machine-readable handoff: `fixtures/public/avf-guest-link-inputs/tail-executor.json`.
Aggregate evidence: `docs/procedures/avf-guest-link-inputs/tail-plan-evidence.json`.
VM022 remains in progress pending independent review and genuine production.
