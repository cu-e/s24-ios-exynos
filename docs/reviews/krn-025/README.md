# Independent KRN-025 cc_kext review

Reviewer `codex-team-review-cc-runtime-20261105-bl`, task REV-010.
Frozen implementation: c512e446fe2b6fe96b7b47c7304b7861525c2023,
c0c69ee1fe8d0ac84dbc7700dfaf5e03b2e1cce6; prose handoff
6dbcd7cddf485ebc7f0e51d1fab200213794cf7b.

## Result — 2026-11-05

**No P0, P1 or P2 finding was identified within the stated component scope.**
The genuine public runtime archive and explicit link-only resource tree are ready
for coordinator integration review. The source correction removes the measured
negative signed left shift while preserving every selected native member and
the measured native archive bytes. The successful tiny helper link establishes
its required helper closure; it does not establish complete kernel/runtime
closure or behavior of all 287 helpers.

REV-010 remains in progress pending coordinator acceptance. No implementation,
shared reference/prefix, original compiler/resource, artifact or original task
ownership was changed by this review. No full compiler/runtime rebuild, kernel
link, ARM execution or phone operation was performed.

## Exact source and original evidence

The frozen builder/fixtures/patch at c0c69ee and final prose at 6dbcd7c match their
actual committed Git blobs and integrated main copies. The final controls'
builder snapshot matches the frozen executable bytes. All **4,706 artifact hash
entries** in the five relevant original capsules matched:

| Capsule | Actual directory under worktrees/krn-025-20261105/artifacts/xnu-cc-kext | Hash entries |
| --- | --- | --- |
| CCKEXT-004 | source-session4 | 9 |
| CCKEXT-013 | headers-session5 | 1572 |
| CCKEXT-014 | build-session5, preserved actual UBSan failure | 1717 |
| CCKEXT-015 | corrected-session1 | 1317 |
| CCKEXT-017 | controls-session2 | 91 |

CCKEXT-015's 305 checks and CCKEXT-017's 343 checks pass. The original failing
CCKEXT-014 is retained as a failure, and its actual source diagnostic is not
reclassified as successful behavior. Tool-byte hashes match current actual tools.

The 472 recovered source files independently match both their raw SHA256 and
Git-blob SHA1 identities. Their complete required subtrees are bound to LLVM
17.0.6 commit 6009708b4367171ccdbf4b5905cb6a803753fe18; the truncated release
download is correctly described as incomplete. The source recovery does not
claim that an HTTP success or a partial XZ archive proves an entire release.

All 149 recorded public declaration files match raw SHA256/Git-blob identities,
including the gethostuuid.h source-symlink payload chain. The original native
build has **509** dependency witnesses; the corrected build has **514**, retaining
the original witnesses and adding corrected-source inputs. Every dependency hash
matches. This distinction avoids calling the corrected aggregate a 509-file set.
The Libc internal sys/cdefs.h remains absent from the staged declaration tree;
its raw source explicitly says it is not to be installed. Actual source/header
provenance, generated alias/availability headers, -nostdinc and source-qualified
include order remain separate from a complete SDK/private-ABI qualification.

Original LLVM Apache-2.0 WITH LLVM-exception and Apple/BSD/APSL source notices
remain applicable. The patch's pin records base, postimage, license and exact
one-line change. This documentation commit contains no runtime archive, SDK,
Apple headers or redistributed source snapshot.

## Challenged boundaries

Line references identify the frozen tools/build/xnu_cc_kext.py.

| Boundary | Independent assessment |
| --- | --- |
| Native source selection, lines 428–468 | Inspected actual pinned builtins/Darwin CMake expressions and retained feature probes: atomic keyword, assembler LSE and unwind header all pass. Actual selection has 287 unique sources, including 125 outline atomic variants and six genuine Darwin profiling sources. The cc_kext filter has no MIN_VERSION, retaining the native kext policy rather than dropping functions presumed to exist in libSystem. Each selected source independently binds its ordinal actual compile command and member name; original commands retain -mkernel/KERNEL_USE/-nostdinc/HAS_ASM_LSE. No selected function was silently skipped. |
| Source correction, lines 604–650 | Original ashrti3 requires valid counts 0..127. In the affected branch count is 1..63, so bits_in_dword-count is also 1..63. Converting the high word to du_int before the cross-word left shift preserves its modulo word bits and defines the shift. Signed arithmetic right shifts retain the documented compiler-rt assumption. The corrected file equals exactly that one-line replacement, and all other 471 pinned source files match. Invalid shift-count behavior is not newly promised. |
| Actual native members | A separate ar/Mach-O reader checks all 287 real payloads, plain ARM64 subtype, iOS16.5 platform/minimum and symbol sets. Each payload matches its actual object. All 286 unaffected objects are byte-identical to the original build; the recompiled ashrti3 object is also byte-identical under the native selected compiler, with SHA c965a5b0a688a78528abf9b74d4e65826a8c01ee87a1cf6c10ecd8fec73ae077. Original/corrected/final archives all match SHA 67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5. Identical native bytes do not excuse the original source UB; corrected provenance remains explicit. |
| Symbol closure and limits | Actual members contain 318 external definitions and 47 remaining external imports. Those include unwind, profiling/libc/pthread and linker section-magic names, with examples fopen$UNIX2003, stderr, dispatch_once_f and pthread_key_create. These are explicit lazy-member imports, not proof that every member is a complete kernel provider. No -all_load/force-load inference follows from the tiny helper. Crypto, full-kernel, full-runtime, private Apple and native flags remain false. |
| Positive native probe, lines 655–683 | Independently decoded the retained real MH_EXECUTE helper image: it has no undefined imports and includes actual div/mod/multiply/shift helper symbols plus its entrypoint. Runtime helpers are correctly hidden/private defined section symbols after linking, not required public image exports. The native ARM64 object/image was inspected, not executed by the host source test. |
| Driver resource mapping | All seven actual backend journals equal their captured expansions. Positive resource lookup supplies exactly the genuine absolute libclang_rt.cc_kext_ios.a. Fresh selected-driver -### reproduces that expansion exactly; outer -lcc_kext is rewritten as expected, with no literal backend bypass. The root is link-only; separately qualified compile-resource headers must remain in use for kernel compilation. No global resource installation, renamed libcc_kext.a or corecrypto interpretation is introduced. |
| Negative archives/platforms, lines 703–753 | Retained missing, corrupt, incomplete, foreign CPU, wrong platform and literal-bypass link cases all have actual exit 1 with no image. Genuine archive/profile guards and independent architecture/platform inspections bind those controls to actual input bytes. The foreign-x86 fixture correctly uses the existing multi-target compiler while positive/iOS platform controls retain the selected compiler. These are source- and target-qualified controls; no empty success archive is substituted. |
| Finite cleanup, lines 166–206 and 685–694 | The retained owned parent/child PID journal shares the measured process group. Actual timeout 0.5 seconds escalates after TERM to SIGKILL, exit -9 in 3.556 seconds, with no live owned descendants recorded. Source cleanup also checks descendants after leader exit. This bounds that owned test; it is not recovery proof after external SIGKILL, a phone watchdog or return-to-Android evidence. Reviewer verification did not signal any original historical process group. |

## Fresh independent semantics and lookup

CCREV-001 was registered before its run and is retained as a reviewer failure:
five byte/source groups passed, then my positive-image assertion incorrectly
required the hidden runtime helpers to remain external exports. Actual image
symbols are valid private/local N_SECT entries (0x1e), and no imports remain.
The failed reviewer runner was saved locally before correcting that filter.
This was a reviewer assertion defect, not a candidate finding.

CCREV-002 was separately registered before the corrected run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-025/reproduce.py review2
```

Exit 0; UTC `2026-11-05T16:19:11.109090+00:00`; eight check groups and 13 actual
commands. Twelve commands exit 0; the original-source UBSan negative intentionally
exits 1 with the real negative-left-shift diagnostic. Every command has an owned
process group, 30-second deadline, sampled 256 MiB RSS limit and finite cleanup;
all report no live owned descendants on completion. One small job at a time.
Actual reviewer VmHWM was **31,360 KiB** and peak sampled owned-child RSS was
**80,972 KiB**. Inherited raw ru_maxrss is not reported as this run's new footprint.

[shift_probe.c](shift_probe.c) supplies a separately authored bit-by-bit unsigned
128-bit oracle. Full ASan+UBSan at O3 first reproduces the original source error,
then the corrected actual source passes **132,225 cases**, covering every valid
shift count for signed boundary patterns and 1024 deterministic random values.
The oracle constructs each result bit individually and uses no signed shift or
call to the helper under test. These are host x86_64 source executions. The
original 10,128 integer/1,281,025 shift harness evidence is audited separately;
neither suite claims behavior of all 287 components or execution of ARM64 code.

[reproduce.py](reproduce.py) and [object_reader.py](object_reader.py) retain actual
commands/exits/stdout/stderr, source/tool/reviewer hashes, capsule identities,
remaining imports, process observations and report. No full runtime/compiler
rebuild, native helper relink, full kernel link, global install or device access
occurred in this review.

Passing evidence:
`worktrees/rev-cc-kext-20261105/artifacts/rev-krn-025/review2/evidence.json`

SHA256: `463653f0cc89df25d150d49988dbc8dbd4c2cba18b8d364d5823d42d4a3f548b`.

Adjacent report SHA256:
`685a9472dc9063e1658d2adb394224c5096fa899a8bbd3cb1a2ff056a13d037a`.

Coordinator: inspect/accept this review, retain the exact archive/resource/source
correction and qualified compile-header inputs, then measure the next intact
kernel link separately. This review closes no full-system/private-input gate.

## Reproduction procedure

Register CCREV-001 before verification. Audit actual CCKEXT-004/013/014/015/017
source/header/build/correction/controls capsules, native source/feature selection,
287 archive members and symbols, 149 declarations/509 original dependencies,
one-line unsigned-shift correction and 286 retained objects, native byte identity,
driver/resource/backend/tiny-Mach-O and invalid-archive/finite-stop evidence.
Independently run a bounded arithmetic source check and driver dry-run if useful.

Use only read-only shared references/artifacts with Git lazy fetch/optional locks
disabled and reviewer-local outputs. One small subprocess at a time, at most
256 MiB actual RSS; no compiler/runtime rebuild or full kernel link. Record
source/tool/commands/exits/hashes, actual process VmHWM and finite owned cleanup.
Publish actionable P0/P1/P2 findings or bounded no-finding report, evidence and
handoff; commit only docs/reviews/krn-025 and retain in progress for acceptance.
Preserve arithmetic-harness versus all-287 behavior and lazy-member versus complete
kernel-provider limits; no SDK/private Apple/crypto/native promotion.
