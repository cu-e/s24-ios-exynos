# VM-022 handoff

Owner codex-guest-exec-20261106-cu; branch team/vm-022-20261106; worktree
worktrees/vm-022-20261106. Keep the task in progress. Only the original owner may
complete it after independent review, integrator acceptance and fresh MAIN common
checks. No worker publication or common checks have run.

The source/text preparation implementation is frozen in
eef8568420abec1829da6ae628d8f95706ad60f5. Its SHA256 is
d32726c10544c882a6463ca344498f40b72af81cbcfa4a3ca44801e1282fd773.
Both accepted run directories contain the exact executed builder.py bytes.

The corrected source contract is
artifacts/avf-guest-link-inputs/preparation-4/prepared-link-inputs.json, SHA256
125a7627c1178d3812f3e618c8f8bcc125cb77520be100013cbcc710b84c9d3a.
The fresh text manifest is
artifacts/avf-guest-link-inputs/text-1/prepared-text-inputs.json, SHA256
1b630006261b7a00ba111cf5bb1b242faaf53514e26c50574da41ce043cfbc00.
Paths in this paragraph are relative to this worktree. The maintained public
fixture records MAIN-relative artifact paths and exact hashes.

The twelve corrected GNU Make source queries bind 169 actual inputs and select
all 1,080 guest objects in exact component and object order: osfmk325, bsd538,
libkern77, iokit104, pexpert11, libsa1, security23 and san1. Preserve 14 genuine
osfmk HIB transforms, libsa bootstrap.cpo KLD/KLDDATA transforms and the top-level
lastkernelconstructor DATA-to-LASTDATA_CONST transform before archive/link.
Component filelist recipes are retained verbatim in the contract. Actual filelist
production needs accepted fresh object bytes in owned staging; this task does not
claim to have executed those transformations.

The genuine DEVELOPMENT name is mach.development.bcm2837. It does not select the
RELEASE exported-symbols-list flag. Preserve all-kpi.exp as a dependency,
all-alias.exp, the __LINKINFO symbolset section, all segment ordering/protection
flags, libcc_kext, libfirehose_kernel and libpthread_kext. The prepared static
archive would contain 1,083 members only when all fresh inputs exist; nonlto.o
belongs to the direct image link and is outside the static archive recipe.
The exact source-built linker/libtool/setsegname hashes, matching setsegname
source/host port, shared dependencies and compiler hash are checked. Actual final
linker compatibility is unmeasured. Command placeholders require fresh coherent
guest object/link/provider staging; a public source include context is not a
provider SDK.

The separate text phase ran 23 bounded commands and produced actual 5,695 export
lines, 83 alias lines, nine genuine symbolsets with 5,638 entries, a combined XML
plist, a Python binary plist semantic roundtrip and fresh version.c. The genuine
newvers.pl ran only on owned copies with DEVELOPMENT selected. Apple's native
plutil was not an oracle. No object, archive or image was produced.

AVFLINKPREP-001 is deliberately inconclusive. preparation-1 failed because the
VM008 artifact index uses MAIN-relative keys for owned files. preparation-2/3
initially passed object-order checks, but a subsequent source audit found copied
osfmk CONFIG_DEFINES leaking across components/top level. The final tool selects
each component's actual doconf declaration and the genuine empty inherited top/
config context. The failed assertion identified BSD first; all actual declarations
are retained in corrected evidence. Earlier artifacts remain immutable and are
superseded for acceptance. The first ledger record attempt also exited2 because
the summary lacked an artifacts list; the corrected inconclusive capsule is the
recorded evidence.

AVFLINKPREP-002 and AVFLINKTEXT-001 are the passing source/text phases. Current
executable-image VmHWM was 91,926,528 and 92,098,560 bytes, respectively. Three
stable MemAvailable samples were above16GiB. Commands use finite process sessions,
25ms sampled aggregate child RSS, streaming hashes, a256MiB light-command guard
and20s per-command deadlines. Raw getrusage retains separate pre-exec history and
is not used as proof of live allocation. The small sampled child peaks are not a
claim to observe every instantaneous allocation.

Next: review the frozen code, exact source/profile context, all three control
rejections, genuine text outputs and hash bindings. Integrator lab_worker and root
receive this scoped result. Actual compilation waits accepted VM008 namespace,
independently accepted VM009 common executor and explicit root resource lease.
All 1,080 objects, fresh tail objects, fresh providers/imports, private IIG ABI,
complete definitions/exports, archive members, final image layout and guest
console/stopping remain unmeasured. VM021's source-only pthread interface handoff
is e8846761b8150f25a49024b174f5484eb3d86369 plus f10dda9 in its own worktree;
its actual archive remains unqualified. No E1S object/archive was consumed, no
compiler/preprocessor/archive/linker/section processor or QEMU ran, and no phone,
ADB, firmware, native device, main publication or common checks were performed.
