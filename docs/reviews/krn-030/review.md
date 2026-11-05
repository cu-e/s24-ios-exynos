# REV-015 native runtime-link review

No P0/P1/P2 finding was identified within the host/source measurement delivered by frozen candidate `a74c1242c3791cf2ff19529c5cd8dfa49f468f30`, integrated as `45780bf`. The original native driver's qualified compiler-runtime lookup is demonstrated. The full kernel link still exits1 on37 required export-only symbols and produces no image. No full-kernel, all-member runtime, corecrypto, Apple private ABI, startup or native capability is established.

Reviewer owner: `codex-team-review-runtime-link-20261105-bq`; branch/worktree `team/rev-runtime-link-20261105`, `worktrees/rev-runtime-link-20261105`. Review base `220d0030d97d7ec74b39858ad6b045365dfdfb85` contains the integration. Only `docs/reviews/krn-030` is committed. KRN026 remains blocked under its original owner/reservations; no source, provider, reference or shared artifact changed.

## Exact inputs and independent verification

The candidate builder, retained-byte verifier, procedure and public qualified-measurement fixture were read with `git show` at the exact candidate and compared byte-for-byte with integrated files. The post-commit binding report independently matches the builder/verifier committed hashes to the actual native-session1 builder snapshot and acceptance-session1 verifier snapshot; it records actual link exit1/no image. The original precommit capsule commit IDs remain unchanged and are not substituted for the final candidate identity.

The review rehashed both actual KRN030 capsules plus five accepted parent capsules: KPROV003/004, CCKEXT015/017 and CCREV002. Streaming hashes verified6782 unique retained input paths, including all982 current original source/object identities,3156 dependencies, staged objects, metadata, provider archives, runtime members and patch inputs. Every current object also has a genuine thin ARM64 Mach-O object header. Exactly the four accepted SGAP replacements differ from the original graph; the other978 current objects are preserved.

The prior staging report and retained metadata remain identical: native978-entry component filelist,14 HIB and one KLD transformation records,83 aliases, native export/symbolset bytes, original non-LTO flag context, direct-tail inputs and genuine FHDR/PTHP archives. No provider/archive overlap or new missing FHDR/PTHP import is introduced. An independent streaming AR/Mach-O decoder matches all981 native archive payloads against the retained ordinal input manifest, including duplicate-name distinction through ordinals, without invoking an archive tool or rebuilding anything.

The runtime path is exactly the accepted link-only resource root plus `lib/darwin/libclang_rt.cc_kext_ios.a`, SHA256 `67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5`. Independent AR/Mach-O parsing matches all287 retained runtime member names, ordinals and payload digests. This proves archive identity, not runtime member selection or execution. The qualified descriptor explicitly says compiler support, not corecrypto, and identifies the corrected LLVM17 source lineage rather than claiming unmodified upstream code.

The `ashrti3.c` source correction, patch digest and corrected source digest are preserved through the accepted capsules and actual source-input witnesses. Original/corrected native object/archive bytes happen to match under the measured compiler; this does not erase the real source correction or qualify every runtime operation. LLVM source pin is `6009708b4367171ccdbf4b5905cb6a803753fe18`, Apache2 with LLVM exception; component notices stay with original artifacts.

## Original driver, backend and execution evidence

Pinned Clang driver sources at `fa9443738c1a18accef4244732ec6d6ee97a8133` were independently read through guarded Git and compared with the exact source-build lineage. `Driver.cpp` unconditionally rewrites `cc_kext` to the reserved option. `ToolChains/Darwin.cpp:AddCCKextLibArgs` chooses the iPhoneOS resource filename and appends it only when that file exists. These primary source bytes explain both the earlier silent omission and the newly measured absolute archive insertion.

The original frontend differs only by a fresh output, a transparent journaling `--ld-path` wrapper for the same qualified ld64, and explicit link-only `-resource-dir`. It retains the outer `-lcc_kext` and all native input order, export, alias, library and layout flags. Normalizing only those allowed deltas yields the exact original frontend. The wrapper contains one real `os.execv(argv[0], argv)` and journals the original ld64 argv before immediate replacement; no backend cc library is manually restored.

The backend array parsed independently from raw `-###` stderr equals both the execution journal and report's expanded/observed arrays. It contains the genuine runtime absolute path exactly once and no literal backend `-lcc_kext`, force_load, all_load, relocatable-link or weakened undefined-symbol option. Removing only that archive insertion and normalizing the output gives the exact old backend argument order, including the genuine FHDR/PTHP libraries, exports, aliases and section layout.

One additional independent original-Clang `-###` dry-run was performed, using the actual original ld64 path, a fresh review output and the qualified resource directory. Its backend matches the actually executed recorded backend after output normalization. The review output remains absent. This did not execute ld64, the journal wrapper, a compiler build or a full link.

## Actual failure and read-only negative controls

The recorded measurement has exactly three processes: positive dry-run exit0, missing-resource dry-run exit0, and one actual full-link frontend exit1. The raw final stderr bytes equal the report diagnostic. Independent parsing finds exactly37 distinct names, all referenced solely by `-exported_symbol[s_list] command line option`, and the same complete set as KRN024's retained genuine export mapping. There is no new diagnosed name, successful image hash or output file.

Eleven independent controls reject mutations of retained bytes/data without executing another link:

- Wrong native filelist and wrong link-only resource root.
- Literal backend cc restoration, forced runtime loading, removed native exports, removed pthread provider and substituted runtime archive path.
- Reordered execution journal, an added unresolved export, an object-import diagnostic misclassified as export-only, and changed archive bytes/digest.

All31 retained-byte/source/command checks and11 controls pass. Eight review commands were recorded: seven guarded Git/source identity reads and one original-driver dry-run. All18 review artifact hashes were reread and matched. The independent checker did not import or execute the candidate builder or retained-byte verifier, and did not use a full link as a test oracle.

The existing runtime inventory's318 definitions and47 external imports are whole-archive facts from accepted runtime evidence. No selected member count is recorded or inferred. Absence of those47 names from this failed link's diagnostics is not all-member import closure. There is no force/all-load flag or trace-only selection flag; normal lazy archive behavior and the unknown selected set remain explicit. The absolute runtime lookup advances only the former resource-availability gate.

## Remaining gates and handoff

The same17 IOUnifiedAddressTranslator,7 pmap_iommu,11 DART/SART/UAT/NVMe PPL and two pmap query exports still need genuine selected ARM64 implementations and corresponding ABI inputs. The existing KRN026 block and original KRN003/004/008 ownership are untouched. Full linking/image inspection, all-member runtime behavior, corecrypto/callback security, SDK/private Apple ABI, startup/recovery, hardware and iOS userland remain unqualified. A failed link does not become kernel availability because its host measurement capsule passes.

Final source-review evidence: `worktrees/rev-runtime-link-20261105/artifacts/rev-runtime-link/session1/evidence.json`; full input hashes, controls and exact commands are in adjacent `report.json`. `assessment.json` binds their digests and criterion-by-criterion result. The retained independent `review.py` in that capsule supports reproduction after assigning a new output directory and registering a new experiment; rerun only its read-only review/dry-run, never the production builder merely to repeat a known failed link.

All three REV015 criteria are assessed satisfied within this bounded measurement, pending coordinator acceptance. Review commit contains only procedure, assessment and this handoff. Keep REV015 in progress under the original review owner until root approves completion. No new private provider, feature/export change, full link or device action is proposed.
