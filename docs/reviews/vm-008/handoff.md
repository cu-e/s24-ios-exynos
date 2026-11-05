# REV-023: frozen public guest namespace review

Owner: codex-review-integration-20261106-ct. Actual atomic claim: REV-023; the coordinator explicitly swapped reviewer roles after the two atomic claims landed in reverse order. The sole reservation is docs/reviews/vm-008. Worktree: worktrees/rev-vm008-ct-20261106; branch: team/rev-vm008-ct-20261106; review base aac27cfbc0d71b34eda33ddf366c72427507ae0b.

## Frozen source and scope

VM-008 source commits, in order:

- 141c778dac91117497f61169c8067c1996449a56
- d1efc4bbb6f201ca1b522d1a3ed99f32e1669bec
- 6bb3d2e2fcfe56e8bd7901671d9d28bb69ceb2a4
- 1d8ebf6bd087431ba0959a5e65296dbd59e15d26
- 2b5aa36092a672e38c2d5ae3173a57b2fb1b7dbc

Producer worktree: worktrees/vm-008-20261105. Frozen descriptor SHA256: 058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7. Frozen evidence SHA256: 6209dde21ba80535e3cc15139dc6165b5e120674920b9382257dddab3fa9fbf1. Next1080 graph SHA256: afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd.

The review reads source, genuine Make recipes, immutable report bindings, selected namespace products, representative Mach-O bytes and actual dependency files. The independent verifier is verify.py; verification.json records actual results and exact streamed bindings. It does not invoke the producer verifier or repeat its53976-file sweep, compiler, preprocessor, generator, Make, guest or common check. Fresh detector controls check rejection of a wrong expected SHA256 and a zero-filled invalid Mach-O header.

## Source assessment

The source keeps the selected ARM64/DEVELOPMENT/BCM2837 configuration separate from native E1S products. It expands genuine component rules with GNU Make, pins the source-built compiler and public host tools, reconstructs the public TargetConditionals contribution with its accepted source port, and retains exact public availability and IIG sources. The Make command shim supplies host tools and genuine platform/logging definitions; it does not fabricate target declarations or SDK metadata.

MIG preprocessing verifies that actual temporary bytes equal the selected .defs source, records real preprocessor dependencies, forwards the preprocessor exit, and keeps internal/export namespaces separate. Partial C/header products from a failed preprocessor are quarantined; a failed invocation does not publish a positive component. The public IIG candidate generates17 pairs, with only the real OSObject.iig.cpp guest compile demonstrated. Its source ports and selected Apple private RPC/ABI limitations remain explicit.

Installed headers follow the genuine unifdef/decomment/install rules. Private implementation defines are removed, and the upstream rule only installs a filtered file if decomment finds a nonempty body. This accounts for1869 read-only installed outputs and36 absent empty-body outputs. The final namespace copies rehashed prior passing products and executes the two missing genuine VPATH asm.h rules. Kernel core compile recipes retain raw interfaces; the filtered installed framework namespace is not globally substituted for them. A literal donor backslash is retained as a missing recursion Makefile fact, with no hidden selected header entry.

The ten distinct object identities include real board, IRQ, early ARM, mockfs, startup, C++, generated IIG, assembly, allocator C and allocator C++ inputs. The actual OSData Mach-O has192 bytes of __DATA_CONST,__kalloc_type metadata. This is an emitted metadata witness; it is not runtime allocator behavior. The stock-compiler control fails on the real XNU metadata builtin dependency, rather than substituting a constant allocator implementation.

The1080 graph enumerates selected component primary source/recipe slots, including55 actual generated C/C++ sources and75 generated raw exports. It is not a complete linked kernel graph. Top-level direct tails/version/nonlto/constructor/data products, external firehose/pthread providers, crypto/provider/archive resolution and guest link/image/entry qualification require their own fresh evidence. Missing declared -I roots can be benign for a particular TU; actual conditional dependency closure is measured only for the compiled representatives, not every future slot.

## Resource policy and retained history

The original AVFHEAD-001 plan/card required >=4GiB admission with post-launch monitoring. The frozen helper takes one pre-spawn sample and then samples controller plus owned session RSS and the memory floor every25ms. It does not establish three stable pre-spawn samples. The producer confirmed no outer three-sample wrapper existed. The coordinator explicitly retained historical acceptance against that original policy and prohibited a retroactive three-sample claim. Prospective reuse must use a separate minimal three-sample guard follow-up; no header or TU rebuild is justified for that prospective policy correction.

The /proc/self/status VmHWM correction is appropriate: raw getrusage ru_maxrss can carry pre-exec history. The preserved same-PID64MiB/exec control demonstrates that distinction. Current-image VmHWM and current RSS are retained separately from raw rusage. The retracted read_bytes/large-library diagnosis and the original inconclusive false-counter runs remain in the producer evidence. This reviewer streams all file hashes and records its own current-image VmHWM.

## Limits and next step

Full SDK identity, selected Apple private DriverKit/RPC ABI, all17 IIG implementation TUs, the complete1080 object build, external guest providers, full kernel link/image correctness, first genuine XNU console, owned PID1, PSCI stop, AVF behavior and all S24/native hardware operation remain unqualified. Existing native reservations and exports are preserved. No phone, ADB, compiler, guest, firmware, power operation or MAIN common check is performed by this review.

The independent byte verification PASS completed in 5.823 seconds: 38,910 checks and 5,929 distinct streamed file bindings, with current-image VmHWM 120,283,136 bytes. All 1,905 namespace entries, 1,080 source/recipe slots, 55 generated sources, 75 generated raw exports, 127 MIG products and 80 exact preprocessing traces, 34 IIG products, 10 ARM64 object identities, real OSData metadata and four original negative controls passed. Both fresh detector controls rejected their deliberately invalid input. No broad artifact sweep, compiler, preprocessor, generator, Make, guest or MAIN common check ran.

Two failed reviewer harness attempts are retained with their exact script bytes. Attempt 1 assumed every historical object row had an allocator_metadata_sections field. Attempt 2 incorrectly treated an omitted field as an empty section list; the independent parser found a real 192-byte metadata section in mockfs_vfsops.o. The final verifier compares metadata wherever the historical report records it, and independently records sections for all ten objects. These were reviewer assumptions, not candidate defects.

Verdict: accept the frozen VM-008 bounded public source/header/representative qualification against its original experiment policy. No actionable P0/P1/P2 source or evidence finding remains within that scope. Future execution must use the separately reviewed prospective stable-admission correction; historical runs do not establish three-sample admission.

The task remains in progress for the separately bound prospective guard assessment, coordinator acceptance and integrator MAIN common checks. Only the original ct owner may complete REV-023 after that acceptance. Review files must be integrated separately from producer source commits; do not publish stale worktree registry/views.
