# Independent KRN-024 kernel provider-link review

Reviewer: `codex-team-review-kernel-link-20261105-bc`; task REV-008.
Exact candidate: `a8c45325356ed2842d34a8901fba92136564a397` (integrated b52538c).

## Result — 2026-11-05

**No P0, P1 or P2 finding was identified within this bounded measurement
boundary.** The evidence establishes a coherent, intact-library link attempt
that actually fails because the required cc_kext library is unavailable. No
kernel image was produced. Earlier 37 export-only errors belong to the attempt
whose compiler driver omitted that library; they remain separately actionable
source/configuration requirements. Compiler-support cc_kext is not identified
with corecrypto.

The review is ready for coordinator acceptance; REV-008 remains in progress.
Implementation/reference/main-artifact bytes and KRN-024 ownership were unchanged.
All full-kernel, crypto, SDK/private-ABI, runtime and native qualification gates
remain open. Follow-up KRN-025/026 scopes remain distinct.

## Identity and retained evidence

All four committed candidate files match their exact Git blobs at the candidate
tip and current integrated main byte-for-byte. The commit-binding report's
builder/verifier hashes match the actual native-session3 builder snapshot and
acceptance-session1 verifier snapshot. Those original precommit capsules retain
their original base-commit identities; the later binding establishes exactly
which committed executable bytes were tested without rewriting the evidence.

Independently rehashed **3,366 artifact entries** across native-session1/2/3 and
acceptance-session1: 1115/1120/1128/3. The first capsule is a preserved failure;
the latter capsules pass measurement checks. Current session3 has the stated 32
passing checks; acceptance has 23. All 45 original command argv/stdout/stderr
hashes, current source-input hashes and actual tool hashes match. These checks
verify retained evidence integrity; they do not turn a failed full link into
kernel construction.

## Independent challenges

Source line references identify tools/build/xnu_kernel_provider_link.py at the
exact reviewed tip; native helper references identify the hash-bound primary
tools/build/xnu_kernel_link_inputs.py.

| Boundary | Actual independent assessment |
| --- | --- |
| Current graph, lines 169–217 | All 982 source/object pairs and 3,156 dependency hashes match. Their identity set matches the earlier genuine inventory; exactly caches_asm.o/start.o/model_dep.o/pe_init.o use the accepted SGAP replacements. The staged manifest binds every current original and output, with no stale pre-SGAP graph substituted. Fresh invocation of the actual read-only validator rejects the genuine earlier graph. |
| Native transforms/filelists | Independently generated expected section-header segment-name byte edits from each original Mach-O and compared every staged byte. Exactly 14 HIB objects and one KLD/KLDDATA object have those native edits; other staged objects are identical. Debug sections retain their native handling. Eight component lists concatenate in recorded native component/object order to 978 entries. No library-only unbuilt object was relabeled as a full-image member. |
| Native archive | Streamed the actual 109,915,456-byte ar file with a separate reader: all 981 ordinal names/payload digests equal the 978 filelist objects plus version.o, lastkerneldataconst.o and lastkernelconstructor.o, in order. nonlto.o stays outside the archive. Container metadata is not substituted for member identity. The original archive-building recipe and helper source hashes are retained. This archive is an input artifact, not a linked kernel image. |
| Genuine providers, lines 308–351 | A separate Mach-O symbol reader examines actual current objects and real provider member payloads. Firehose has eight definitions/11 external imports; pthread has 39/61 and the already accepted exact archive digest. Every provider import has a real current kernel/native-alias provider and no definition overlap. Only the 13 recorded linker-boundary names remain in the combined object/provider subset. This does not prove export closure or runtime correctness. |
| Native aliases | Re-derived the complete 83-name mapping independently from the actual selected export source files, including native whitespace normalization. The three VM aliases retain their exact external targets. Original generated alias bytes match their capsule hash; fresh actual-validator input with mach_vm_map bound to the wrong real provider is rejected. The prior independent genuine VM-code alias review remains a prerequisite. |
| Compiler policy, lines 251–272 | Retrieved actual Driver.cpp/Darwin.cpp/ToolChain.cpp Git blobs at fa9443738c1a18accef4244732ec6d6ee97a8133 with lazy fetching disabled. They match both recorded hashes and compiler-source lineage files. Driver.cpp:493 unconditionally rewrites cc_kext to its reserved option. Darwin.cpp:2839–2868 selects libclang_rt.cc_kext_ios.a for iPhoneOS and only appends it if present. This explains missing compiler-support insertion; it establishes no corecrypto/KEC identity. |
| Actual backend, lines 389–472 | Fresh actual Clang -### expansion reproduces the retained linker argv exactly and omits cc_kext. The measured direct argv equals that expansion with only literal -lcc_kext restored immediately before -lfirehose_kernel; all other argument order/values remain unchanged. All three required library flags are present in the actual executed command. Fresh invocation of the unchanged validator rejects the omitted backend. No downgraded undefined/flat-namespace/relocatable mode is substituted. |
| Link outcome | Original direct attempt has actual exit 1 and the retained library-not-found diagnostic, with no output file/image. The resource directory reported freshly by the actual compiler matches the record and its cc_kext iOS runtime candidate remains absent. This reviewer executed no linker. Missing-library failure cannot establish whether later errors are fixed. |
| 37 earlier exports | Independently matched every earlier quoted linker error and its exported-symbol-list-only reference. Each name is absent from actual kernel/provider definitions and has exactly one selected export-source line: 35 in Private.arm64.exports and two in Private.exports. The native-session2 command omitted cc_kext; those diagnostics cannot be treated as the result of the intact-library session3 command. Source/configuration-consistent provider correction remains required; no exports were removed and no bodies/stubs invented. |
| Resource and qualification scope | Original commands carry bounded time/group/RSS observations and retained output hashes. The new audit uses streaming hashes/member reads and dry-run/input-validator controls only. No heavy rebuild, full-link replay, QEMU, install, source hydration or device operation occurred. Python binary plist roundtrip remains explicitly separate from an Apple plutil oracle. All full-system qualification flags remain false. |

The `-ca` archive and the actual native full-image command are assessed as their
distinct native stages: the full command preserves the 978-object filelist,
direct version/last/nonlto order, native layout/export/symbolset/alias options,
BUILD_LTO=0 and required libraries. Neither stage justifies substituting an empty
library, the historical pthread archive or a successful crypto/RPC stub.

The exact compiler-runtime and source-gated export inputs need later qualified
work. After those gates, a fresh intact link must produce a genuine image before
image structure, remaining relocations/exports, segment protections/order or
runtime startup can be assessed. SDK/private Apple compatibility and native
hardware/recovery are separate unresolved outcomes.

## Actual reviewer experiments

KLINKREV-001 was planned before verification and is retained as a failed reviewer
experiment: its first four groups passed, then the reviewer's overly literal
source-alias comparison rejected harmless whitespace in three genuine exports.
The candidate's native generator and consumer correctly normalize that whitespace.
No candidate defect was inferred. The failed runner's original bytes were saved
under local failed-inputs before correction; original evidence remains unchanged.

KLINKREV-002 was separately planned before the corrected independent run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-024/reproduce.py review2
```

Exit 0; UTC `2026-11-05T14:51:56.006604+00:00`. Eight check groups and ten actual
subprocess commands pass. Fresh controls use the unchanged candidate's read-only
validator with real retained context: omitted required backend library, wrong
real VM alias and stale real graph are all rejected. The native driver command
uses -### only; no output image path is written. No compilation or relink occurs.

Actual reviewer process VmHWM was **37,516 KiB**, child peak RSS **35,796 KiB**.
Raw Linux ru_maxrss was 995,980 KiB and retained a pre-exec high-water mark: a
separate tiny Python process reported that same raw value with actual VmHWM
11,596 KiB. Both raw and actual-image measurements are preserved; the raw value
is not attributed to allocations made by this audit. Every subprocess has a
45-second timeout; no compiler/linker build jobs were launched.

[reproduce.py](reproduce.py) and [object_reader.py](object_reader.py) are authored
review controls. They retain exact commands/exits/stdout/stderr, source/tool/input
hashes, capsule identities, source-export mappings, date and resource information.
All generated artifacts remain local in the reviewer worktree; no vendor/Apple
SDK, headers or binaries are committed.

Passing evidence:
`worktrees/rev-kernel-link-20261105/artifacts/rev-krn-024/review2/evidence.json`

SHA256: `7159f1558be221bd327dbd58dc6796a12baa3a6be31522bc653082f26cccb141`.

Adjacent report SHA256:
`7f5917c7b0f1870ac293e31259e8d03cd2754f260b3e4b360de8e327a3cfb3f6`.

Coordinator: inspect this bounded review and evidence, decide acceptance and
retain distinct compiler-runtime/export-provider follow-ups. This reviewer
performed no primary common-check run or implementation/task-owner changes.

## Reproduction procedure

Register KLINKREV-001 before verification. Read the exact builder, retained-byte
verifier, manifest and procedure. Audit actual native-session3, acceptance-session1
and commit-binding capsules; independently validate the 982-object/3156-dependency
graph, native filelist/archive member order and section-only transformations,
actual firehose/pthread definitions/imports and 83 generated aliases. Inspect
pinned Clang source and actual driver/backend command bytes for reserved cc_kext
mapping, silent omission and literal restoration. Distinguish 37 export-only
diagnostics from missing compiler runtime; cc_kext is not inferred to be crypto.

Use read-only primary artifacts/references with GIT_NO_LAZY_FETCH=1 and
GIT_OPTIONAL_LOCKS=0. Execute only bounded necessary source/command/object checks
with reviewer-local outputs, including a fresh driver -### expansion if useful;
no relink, heavy build, global install or device operation. Save actual commands,
exits, source/tool/output hashes, exact commit/date, report and handoff. Commit
only docs/reviews/krn-024; retain REV-008 in progress for coordinator acceptance.
