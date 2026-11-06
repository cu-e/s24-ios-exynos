# REV-043: compiler runtime resource lookup review

Verdict: **PASS within the frozen archive/provenance and recorded resource-lookup
scope. No actionable P0/P1/P2 finding was identified.** This is an independent
review of VM-023 HEAD `8eefa50abe26ec9e8e8368fea82bc06465841441` and implementation
`0e44b04827b4c3258ed0f7bd724d03acc728bf26`. The original producer DE retains
implementation ownership and source-task closure. Integration/root acceptance
of this review remains pending.

The producer tool's current bytes match SHA256
`847ebaed1349b8139f0df55490b61afe4c966d017731314c61ade19a6e66a197` and Git blob
`8fdf96a5623ea79509cad640d9620af7ed0b3cab` in the implementation commit. Its
owned source/fixture/documentation scope is clean. The maintained producer
capsule matches the supplied frozen SHA256
`feaf78a5050c239f144a1ab56e5bfd481c660a3d2e0347a5c33a3088ab48ce18`.

The independent ar walker agrees with the pinned production parser on all 287
ordered member names and bytes in the 219,448-byte qualified archive. Every
member hash matches the accepted index. An independent Mach-O/header/platform/
symbol walk agrees with the reused parser and saved member index: plain ARM64
MH_OBJECT and iOS16.5 metadata, with the same definition/import sets. All 287
actual object files also match their archive member bytes and saved source/argv/
cwd/exit witnesses. Source witnesses comprise 161 canonical source records,
125 genuine generated outline-atomic wrappers and one accepted unsigned-shift
correction. Source SHA256, available canonical Git blobs, generated dependency
pins and the original/corrected witness distinction all match.

The aggregate archive retains **47 external names**, including kernel/libc,
unwind and linker section-magic dependencies. This review leaves them explicit.
It does not determine which archive members a complete guest link will select,
resolve those imports or requalify runtime semantics. The original runtime
integer-semantics failure and accepted correction remain separate records; no
runtime or host test corpus was rerun.

The existing final positive driver stderr independently parses to the exact
qualified linker and exactly one qualified `libclang_rt.cc_kext_ios.a` token.
The existing absent-resource stderr parses to the same qualified linker and no
runtime archive. Both preserved commands exit zero, contain the actual `-###`
dry-run flag and use `/dev/null` as an explicitly non-provider `-x object` input.
Their output hashes, backend argv, memory/cleanup records and absent declared
outputs match the frozen capsule. The reviewer did not execute either command.
The missing-root exit-zero record fails positive admission in the new controls;
a successful process exit is not sufficient runtime selection evidence.

The pinned primary driver sources support the observations: `Driver.cpp` rewrites
the reserved cc_kext name unconditionally and honors explicit `-resource-dir`;
`Darwin.cpp` appends `lib/darwin`, selects the iOS archive and appends it only
when it exists. The runtime root remains a **link-only** resource root. The
producer's exact immutable 1,080-row graph binding and namespace loop were
reviewed; representative C/C++/assembly templates independently retain the
guest target and exclude that root from compile headers. This review does not
grant compiler-header/SDK qualification. That historical graph remains `afc5cd20`;
it is not relabeled as the later Firehose `be02fbfc` namespace.

Prospectively registered REVVM023-001 passed **10,858 checks**, 624 streamed
before/after file bindings and ten negative controls. Controls reject truncated
archive bytes, negative member size, oversized BSD name, foreign CPU, wrong iOS
version, oversized symbol count, invalid external string index, missing-root
evidence presented as positive, duplicate archive tokens and foreign archives
with the same basename. Mutations used owned bounded byte copies; original
inputs were unchanged. Control copies remain locally preserved with hashes.

The control run took 2.465497 seconds including three one-second-spaced memory
admission samples. Current-image VmHWM was 84,918,272 bytes and final VmRSS was
45,203,456 bytes. Inherited ru_maxrss is separately recorded. The control process
launched no child, compiler driver, frontend, assembler, generator, archive/link
tool, section tool, QEMU or common check, and obtained no root allocation.
Producer prepare-1/driver-1 failures and the reviewer's corrected pre-control
index-schema inspection mistake are retained in evidence, not discarded or
attributed to a producer defect.

The bounded verdict is archive/source/recipe and recorded lookup acceptance.
There is no complete guest link, archive-member selection/reference closure,
full runtime behavior, corecrypto/private Apple ABI, XNU console/PID1/stop,
native E1S or physical phone result. Independent integration on current MAIN,
fresh common checks by the designated publisher and explicit root authorization
remain required before review-task completion.
