# Independent KRN-022 pthread review

Reviewer: `codex-team-review-pthread-20261105-av`; task REV-006.
Exact authored implementation: `16a7497ef0243a3c4fbdfa7ec5189a864a6a4f88`
(integrated as 3c23af0). Scope is host component qualification only.

## Result — 2026-11-05

**No P0, P1 or P2 finding was identified within the measured component boundary.**
The exact source-qualified archive is suitable for the next controlled link
integration review with its native aliases, genuine required libraries and
recorded BUILD_LTO=0 context retained. This is a bounded host conclusion; it
does not qualify a full kernel link, complete SDK, private Apple ABI, crypto,
runtime or native-device behavior. REV-006 remains in progress pending coordinator
acceptance; KRN-022 ownership was not changed.

## Exact inputs and capsule audit

The current main copies of the builder, public qualified-component manifest and
procedure match their Git blobs at `16a7497ef0243a3c4fbdfa7ec5189a864a6a4f88`
byte-for-byte. Local libpthread and Apple XNU reference HEADs match the full
documented pins and have no tracked changes:

- libpthread `a6c70ca0e544347a0377babf748f831577ec24f9`;
- XNU `c54f35ca767986246321eb901baf8f5ff7923f6a`.

Independently verified **3,578 artifact hash entries** in all five original
passing capsules plus final acceptance. All recorded checks pass; the final
acceptance has the documented 21 checks. Repeated artifact entries across
capsules are counted as entries, not invented independent experiments.

| Capsule | Directory under artifacts/xnu-kernel-pthread-profile | Hash entries / checks |
| --- | --- | --- |
| PTHP-005 | headers-session4 | 2606 / 8 |
| PTHP-007 | compile-session2 | 362 / 9 |
| PTHP-008 | controls-session1 | 169 / 15 |
| PTHP-009 | aliases-session1 | 134 / 7 |
| PTHP-011 | native-mig-session2 | 177 / 7 |
| PTHP-012 | acceptance-session1 | 130 / 21 |

Earlier failures are preserved and are not counted as passing qualification.
No main artifact, reference, implementation, registry ownership or generated
planning file was edited directly by this review.

## Challenged boundaries and actual results

Builder line references identify the exact reviewed source.

| Boundary | Assessment and independent evidence |
| --- | --- |
| Installed header context, lines 89–218 | All installed manifest source/declaration/output hashes and read-only modes match. Counts are 1794 installed, 36 native-filtered-empty and 76 unavailable generated inputs; unavailable and filtered outputs remain absent. The actual native rule installs unifdef output after using decomment only to decide whether content remains. Fresh unifdef on genuine kern/thread.h with the recorded native flags reproduced installed bytes exactly and removed struct thread's implementation body. Compiler definitions added later cannot restore removed text. No raw private-header fallback or invented empty generated header was found. |
| Native SDK-context MIG, lines 437–467 | All four actual defs/raw/installed/consumed header identities and preprocessor-provenance hashes match: mach_port.h, task.h, mach_vm.h and thread_act.h. Inspected native recipe and actual trace use the selected ARM64/E1S/iPhoneOS context. Independently reran the real mach_vm generation with the recorded host MIG tool and preprocessor wrapper, fresh reviewer trace/temp/output directories and genuine defs source; native unifdef output exactly matches the consumed installed header. This reproduces one fresh header, while all four stored byte identities are audited. It supplies no proprietary SDK. |
| 140 callback declarations and 284 layout values, lines 312–385 | Independently compared the complete actual preprocessed pthread_functions_s/pthread_callbacks_s declarations, 45/95 fields. A separately authored Mach-O reader redecoded every stored value from both real kext/kernel probe objects, agreeing with recorded Clang19 values. Fresh compilation of the actual complete kext probe TU reproduced all 284 values against the actual kernel object; table sizes are 1016/1296. Allocator layout is 64/32/40/44. No stand-in record/table replaced either TU. |
| Function-pointer rejection, lines 376–385 | Fresh compilation with the existing mutated actual header failed with incompatible function-pointer diagnostics and produced no object. The mutation changes pthread_init's return type in the genuine consumed header, so this tests a real assignment boundary. Matching offsets alone are not used as proof of matching function types or a private Apple ABI. |
| Genuine allocator metadata, lines 388–413 | Independently decoded actual kern_synch.o descriptor relocations, signatures, flags and sizes with a separate reader: kwq/kwe sizes 248/56, flags 97 and distinct signatures 1111212222222222222211122112222 / 1111221. These equal the real allocator probe's type metadata. Existing fake-signature objects decode to historical 12 and differ; original stock-compiler rejection and full actual command diagnostics are capsule-hash bound. Current compiler bytes match SHA256 7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82. This audit does not independently claim an Apple-private metadata oracle. |
| Real VM alias ownership, lines 61–70 and 415–435 | The selected native alias list maps mach_vm_allocate/map and vm_fault to their actual external providers. Independently repeated the two-object relocatable link of genuine vm_user.o/vm_fault.o, then decoded symbol section/address pairs: each alias equals its intended function. The existing wrong-real-provider control binds vm_fault to a different real function and is independently detected. The genuine vm_fault external declaration has seven arguments; its internal form has eight. No stub or arbitrary same-named symbol satisfies this check. |
| Archive and all imports, lines 263–295 and 488–502 | A separate ar/Mach-O reader verifies all three archive members byte-for-byte against actual compiled objects, independently extracts 39 definitions/61 external imports, and decodes the current 982 genuine kernel objects rather than trusting a provider-name JSON alone. All recorded object/source hashes match. Their 24,070 exported names cover every import directly or through the three native VM aliases, with zero pthread/kernel definition overlap. Every pthread header dependency hash also matches. This is provider availability; it is not a full relocation/link/runtime result. |
| LTO and remaps, lines 247–257 | Real kext.xcconfig has native normal LLVM_LTO=YES; the measured archive deliberately omits LTO for selected BUILD_LTO=0 integration and records that distinction. Actual inputs apply pthread_kern→pthread_kext_kern and current_uthread→pthread_kext_current_uthread; the genuine variable/function bodies remain in the source, and the object definitions expose remapped names. The archive is explicitly not a stock Xcode normal-release binary. Those adaptations must remain part of later integration provenance. |
| Final acceptance scope, lines 469–542 | PTHP-012 revalidates byte witnesses and the cited common-check evidence while leaving complete SDK, stock Xcode release, private Apple ABI, crypto, full link, runtime and native-device flags false. Coordinator subsequently reported a fresh primary make check pass at 3b5b4f9, where this implementation was already integrated. No review step replaces missing corecrypto or other required native libraries. |

The compiler, installed-header set and native recipes are source-qualified local
inputs, not a recovered selected Apple SDK. In particular, source-generated
Availability headers and the earlier pinned public TargetConditionals contribution
retain their documented boundaries. Generic success from the existing test
suite, matching layouts and resolvable symbol names cannot establish private
service compatibility, lock behavior, callback runtime correctness or native boot.
Upstream component notices remain applicable; this review commits only code and
review prose, with no Apple headers, SDK or binary archive.

## Independent reproduction

Experiment PTHPREV-001 was registered against the procedure below before
verification. Actual command from the reviewer worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-022/reproduce.py review1
```

Exit 0; recorded UTC `2026-11-05T14:09:18.752734+00:00`. Nine independent check
groups passed across 15 exact subprocess commands. Thirteen exits were 0; native
unifdef returned its expected changed-output exit 1 and the intentional wrong
function-pointer compile returned 1. Both outcomes were explicitly assessed;
neither is silently counted as an ordinary compile success. Peak measured child
RSS was 70,864 KiB. Compiler calls were sequential and subprocess timeouts were
45 seconds. No heavy rebuild, full acceptance-chain rerun, QEMU, install or
device operation occurred.

[object_reader.py](object_reader.py) provides the separate ar/Mach-O reader;
[reproduce.py](reproduce.py) audits actual capsules and records exact commands,
stdout/stderr, exits, dates, source/tool/reviewer hashes, header/probe/MIG outputs
and resource observations. Generated data remains local in the reviewer worktree.

Evidence:
`worktrees/rev-pthread-20261105/artifacts/rev-krn-022/review1/evidence.json`

SHA256: `503062615d13cc093aabf05393c4b289f0cb0a8e21742b16b770cf1221324785`.

Adjacent report SHA256:
`6ebb6a58c438456c4a7c5f253bc281f6416aa3d02a9872048191655449f4b3d3`.

Coordinator: assess the review, then carry the exact archive, native aliases,
source/header/compiler witnesses and required genuine libraries into the next
controlled link stage. This result closes no private Apple or full-system gate.

## Reproduction procedure

Read the exact builder, qualified-component manifest and procedure. Independently
validate pinned source and all artifact hashes in PTHP-005/007/008/009/011 plus
PTHP-012, installed native-unifdef context and unavailable-input accounting,
the four native SDK-context MIG byte identities, actual callback objects and
declarations, allocator metadata and executed negatives, real VM provider alias
objects, all archive members/imports/definitions and kernel overlap, LTO and the
two namespace remaps. Treat existing main artifacts and references as read-only.

Register PTHPREV-001 before independent verification. Use separately authored
bounded object/source checks and selected sequential small reproductions with
fresh reviewer outputs. Never run the builder with its main output root, launch
a heavy build, acquire the exclusive QEMU lease, install anything or access a
device. Save exact commands/exits, hashes, commit, date, resource observations
and outputs under this reviewer worktree. Publish concrete P0/P1/P2 findings or
a bounded no-finding conclusion, handoff and review-only commit. Do not mutate
KRN-022 ownership or complete REV-006 before coordinator acceptance.
