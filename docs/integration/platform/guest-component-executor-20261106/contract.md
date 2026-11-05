# Shared guest component executor contract

INT-003 owner `codex-integrator-platform-20261106-cn`; source-only handoff to
the separately assigned VM-036 executor author. This document does not admit
execution. Preserve the frozen DES candidate and its historical plan. No new
component runner is authored by this integrator.

Use the accepted process boundary for both components. Do not invent entries
in VM-008's 1080-row kernel graph or invoke its shard CLI with fabricated rows.
The two four-command units are three compiles followed by one archive each.
Run them serially, under an exact later root lease and original-owner experiments.

## Frozen preparations and predicates

The completed independent source review is
`docs/integration/platform/guest-source-20261106/qualified-review.json`,
SHA256 `3c3a1fcd36c03b4e112e8390daef3eb47de0d2ef9f247cfb86feb18b874c66ff`.
Its source capsule records 2112 checks and 2422 source/input bindings; the
separate corrected-guard capsule records 16 rejections. Reuse those results.
This preparation must not repeat that source/header matrix.

VM-020's source correction is `27303145d33105170a6f9623240c5be0685675fc`.
The original guest row's complete 261-token argv has compact JSON SHA256
`cf737937e6e6c74f00302f2bebcc1ec6a08329fb48ab35b451dd226f590113ca`.
The actual final three-recipe plan is in the VM-020 worktree at
`docs/procedures/avf-guest-firehose/preparation-session3/compile-plan.json`,
raw SHA256 `f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197`.
Bind that entire plan as well as the corrected predicate. Checking only the
original row would not freeze later alterations to the three generated recipes.
Use immutable session3 probe/export paths; earlier mutable probe recipes are
historical evidence only.

VM-021's correction is `1df0f1c9869bc93201a77b897a6ca515c5e7f560`, with
documentation through `34443d5a2c87525cecb7521fbe5dd1e00e7174d9`.
Its original `artifacts/avf-guest-pthread/prepare-2/component-plan.json` has raw
SHA256 `96065bf4ebe697cfd1a0d43eb52d0ae315275f25efe619e60ae14d66ae350298`.
The separately committed execution-plan freeze requires canonical parsed JSON
SHA256 `bfb88d88d6f44d936fd1fc5758b687ba29ca50f19626e6750224d6db2d69f475`.
Call its execution validator, never the preparation-only structural helper.

Validate original templates before replacing output tokens. Permit replacements
only for the declared `-o` and `-MF` values, with exact one-to-one identities.
Reject added, dropped, reordered or replaced options, response files, plugins,
source/compiler/include changes and alternate output mechanisms. Record raw
plan hashes and canonical original/expanded argv hashes. No extra flags are
needed: retain DEVELOPMENT/BCM2837, genuine metadata builtins, pthread
MACH_ASSERT/DEBUG and LTO off, and both existing pthread namespace remaps.
MAX_CPUS=8/MAX_CPU_CLUSTERS=1 are source/header facts, not new overrides.

## Actual four-command products

Firehose compiles provider, provider-layout and interface from the exact three
session3 rows, preserving their declared cwd and `-I.` semantics. Its proposed
fresh output root is the original owner's
`docs/procedures/avf-guest-firehose/execution-session1` in VM-020. It produces
`provider.o`, `provider-layout.o`, `interface.o` and their matching `.d` files.
The archive `libfirehose_kernel.a` contains only `provider.o`; exclude both
probe objects. An independently bound planning filelist names that one future
object. Do not create the execution directory during source planning.

Pthread compiles exactly `kern_init.c`, `kern_support.c` and `kern_synch.c` from
the owned patched `prepare-2` source tree. Its proposed fresh root is the
original owner's `artifacts/avf-guest-pthread/compile-1` in VM-021, producing
the three matching objects/dependency files and `libpthread_kext.a`. The archive
contains exactly those three objects. Freeze an explicit cwd; do not inherit
the invoking shell's directory. The original source plan lacks a cwd.

Use the source-built qualified cctools libtool:
`artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-libtool`,
SHA256 `e9b544277b2194a879a1d186c425d2a1b4620e210b9906a72f0a4a02ba0a8005`.
The fourth command uses `-static -csD -filelist <frozen owned filelist> -o
<fresh archive>` after the three successful compiles and inspections. Bind the
exact argv arrays and filelist bytes. The qualified cctools source's libtool.c
handles `-static` at line 534, `-filelist` at 541 and `s/c/D` in the character
switch at 1156 onward (D at 1212). Its installed manual synopsis permits the
same options. This read-only proof invokes neither tool. Do not choose a tool by
PATH or substitute a different NDK archiver. Abort on any failed prerequisite;
no archive may package an earlier native object or failed/reused guest attempt.

Output hashes are null/unmeasured in the prospective plan. Record actual object,
dependency and archive SHA256 values only after successful bounded commands.
The archive command's inputs are the just-validated actual object bytes, not
guessed future digests. Pin those generated-input digests before the fourth
command and verify that extracted member bytes match them exactly.

## Namespace, compiler and host runtime

Bind the accepted historical VM-008 descriptor SHA256
`058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7`,
artifact index SHA256
`7ad7a1406190116bbd52eec5ea85802e110e2013e928b847a7b470d2abdc1f8a`,
and source/recipe graph SHA256
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
Follow `docs/integration/kernel/vm008-contract.md`: the newer admission helper
does not validate the old descriptor's self-hash. Verify exact published bytes
directly or use the frozen historical verifier without relabeling old policy.

Both plans select the genuine compiler
`artifacts/xnu-compiler-cxx-storage/source-build-session2/clang`, SHA256
`7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82`.
Both use `-nostdinc`. Bind the matched resource qualification descriptor SHA256
`ec099fee0aedf494d8ec277394800b0dfd299695c19ab33bf164b7d96f4d4ddd`;
do not add SDK/resource flags or claim these recipes consume unused resources.
Record actual dependencies if a declared consumer reads resource headers.

Independent read-only ELF inspection finds compiler DT_NEEDED libm.so.6,
libstdc++.so.6, libgcc_s.so.1, libc.so.6 and ld-linux-x86-64.so.2. Its RUNPATH
contains a literal backslash before `$ORIGIN` and a trailing empty component.
Libtool needs libm.so.6/libc.so.6 and has build-time dependency RUNPATHs. Resolve
the actual interpreter and transitive host libraries under the exact sanitized
environment, pin their bytes, and preserve symlink/lookup provenance. Candidate
system paths are not proof of actual loader resolution. Reject library shadows
in cwd, qualified tool-relative/search directories and relevant RUNPATH roots;
do not assume clearing LD_* makes embedded lookup paths harmless. Reject new,
missing or changed relevant entries before and after each command. If runtime
resolution cannot be verified, defer execution/qualification rather than infer
it from the compiler's file hash. Do not use ldd on an untrusted binary.

Reuse frozen source/header input manifests for planning. Before real execution,
verify the actual reduced include/search namespace and direct inputs, including
cwd, forced includes and sanitizer ignorelist. Reject newly shadowing, missing,
changed or symlink-escaped inputs. Source preparation is not a fresh dependency
closure: parse each actual `.d`, require its real source and intended output,
and hash every real dependency before accepting the resulting object. Detect
input changes during a command and before reuse; keep failures immutable.

## Ownership and common process boundary

MAIN's accepted process tool after the VM-035 common boundary at
`12a43eef4a00da24bed6604655854ef533d2bbb2` has SHA256
`5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8`.
The historical physical VM-009 worktree still has SHA256
`13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47`.
Do not pair the current MAIN path with that old digest. Independent AST comparison
finds unchanged run_child, landlock, stable_memory, supervisor and current-image
memory helpers; this is a source equality check, not a repeat runtime acceptance.
The supervisor is `tools/build/qemu_host.py`, SHA256
`faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99`.
Freeze the actual chosen physical path. If later common integration changes it,
bind and review the actual accepted version before any resource receipt. Do not
silently import whichever MAIN version exists when execution starts.

Reuse its `run_child`, Landlock, sanitized environment, prospective three
one-second >=4 GiB samples, live 256 MiB controller-plus-owned-tree RSS cap,
finite timeout and owned session termination/cleanup. Run one serial child at
a time, including the archive command; no outer parallel component jobs. Retain
the accepted 2 GiB virtual-address cap separately from the 256 MiB RSS cap.
Propose <=120 seconds per command, including the bounded archive; the final root
lease supplies a finite whole-attempt deadline. Defer below the memory floor.
For new plans after the next build boundary, the user's project-wide ceiling
is six compilers and 6 GiB total new project-process RSS, with the same stable
4 GiB available-memory floor. It is not six jobs per component. Keep these
component units serial and bind their slot to the root's shared resource queue.
The already running wave3's two-job limits and immutable inputs are unchanged.
Record whole-attempt and per-command wall time, sampled peak RSS and active
swap-in/swap-out counter deltas with sampling times. Swap occupancy alone does
not measure active swapping. An eight-compiler trial needs a separate measured
plan after stable resource evidence; this contract does not authorize it.
Never kill unrelated processes. Preserve actual process samples, command exits,
stdout/stderr hashes and final empty owned-process lists. Report current-image
VmHWM separately from inherited ru_maxrss.

Before mkdir, verify live MAIN registry ownership, original owner, literal task
paths and recorded worktree, exact component identity, canonical fresh output
root, no parent traversal/symlink aliases or shared overwrite, and current exact
root lease/plan hash. Source-only VM-036 owns the executor implementation, not
another owner's component task. Original VM-020/VM-021 owners register and
record their own component experiments. This integrator does not mutate those
tasks. No automatic MAIN publication or common check is part of the executor.

## Acceptance and required controls

Read each actual Mach-O header/load command/section and raw symbols; require
ARM64 MH_OBJECT, nontruncated extents and genuine expected allocator/type
metadata where the real producer emits it. Inspect the real Firehose layout and
interface probe records and selected provider exports/imports. Preserve pthread
metadata, real definitions/imports, namespace remaps and absence of unexpected
duplicates. Compare archive member order/set and exact member bytes, including
index handling; archive exit zero alone is insufficient.

Three pthread TU objects plus an archive do not establish the entire guest
kernel/kext callback ABI or its three VM alias provider identities. Additional
fresh compiled layout/type/alias probes and selected guest object/provider
closure remain separately required before claiming those acceptance criteria.
Likewise no component archive proves a full link, startup, console, entropy,
private Apple ABI, native hardware, FIPS or side-channel safety.

Source-only mutation controls must exercise the real new admission predicates:
wrong/raw/canonical plan; dropped or overriding DEVELOPMENT, MACH_ASSERT or
DEBUG; source/compiler/namespace changes; output/path/task/owner/shard confusion;
response/plugin/include options; new library/include shadows; stale tool/runtime
bindings; attempted archive of probes or wrong/missing/duplicate/native members;
truncated/wrong-CPU/wrong-metadata object; changed real dependencies; failed
compile continuation; and reuse of changed/failed outputs. Reuse the accepted
supervisor's genuine finite exit/timeout/Landlock controls instead of inventing
a second supervision engine. Synthetic controls remain labeled synthetic and
cannot replace the first real component compile/member evidence.

The current plan is preparation only: adapter implementation, independent review,
original-owner registrations, exact final hashes and scheduled root lease are
still required. No compiler, archive or guest is authorized by this contract.
