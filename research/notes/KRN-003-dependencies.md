# KRN-003 dependency handoff

2026-11-05. Owner: `codex-e1s-dependencies-20261105-k`, main checkout. Blocked on the concrete external inputs below, with host component work retained. No phone, root, partition, firmware, upstream setup or SDK download operation performed. KRN-001/NAT-001 retain their original owners and reservations.

## Implemented and measured

KRN-002 inputs are identified by [the qualified tool manifest](../../fixtures/public/xnu-host-tools/qualified-inputs.json). Consumed binaries are hash-verified. The compiler is the explicitly selected installed NDK28.2 Clang19.0.1 executable, targeting arm64-apple-ios16.5; no Android sysroot or Linux libc is used in the passing component fixtures. Apple compiler equivalence is not established.

Pinned sources fetched clean and added to research/sources.json:

- AvailabilityVersions115.4: `5d9baee345b3bc72b26c71adc65f94f2d5e9ced2`.
- libdispatch1415.100.11 kernel firehose: `a641558f447659d90ad002ef0ee6f0212273fbfc`.
- libpthread514.100.2: `a6c70ca0e544347a0377babf748f831577ec24f9`.
- Build donor remains `d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c`; this is distinct from the Linux libdispatch runtime used to build ld64.

A fresh `python3 tools/build/prepare_xnu.py --run e1s-dependency-source-session1` exited0 and produced artifacts/xnu-prepare/e1s-dependency-source-session1/xnu with the pinned Apple/E1S source, all15 E1S patches and the existing STM correction. No full kernel was built. The dependency helper snapshots its builder, prepared-report hash and all prepared source-file hashes per run.

[The small attributed donor patch](../../patches/build-inputs/README.md) requires explicit absolute compiler executables, selects ARM64_BOARD_CONFIG_E1S for firehose/pthread and requires explicit MACHINE=E1S at their build stages. It is applied only in private artifacts copies. Donor diagnostic filtering and kalloc-type builtin fallback remain limitations. Setup/pthread scripts are not executed by the wrapper test.

## Actual experiment outcomes

All commands use `python3 tools/build/xnu_dependencies.py --run RUN --clang /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang --prepared-run artifacts/xnu-prepare/e1s-dependency-source-session1 MODE`. Immutable evidence in state/evidence/E1SDEPS-001.json through005 binds commands, exits, reports, builder snapshots and artifact hashes. Public reports are under fixtures/public/xnu-dependencies; raw local runs are under artifacts/xnu-dependencies.

| Experiment | RUN / MODE | Exit / outcome | Observation |
|---|---|---|---|
| E1SDEPS-001 | include-session1 / --audit-includes | 1 / fail | Board probes pass; eight real syntax attempts fail at string.h |
| E1SDEPS-002 | include-session2 / --audit-includes | 1 / fail | Genuine osfmk/libsa string.h export mapping added; firehose syntax passes both profiles; all six pthread attempts fail at TargetConditionals.h |
| E1SDEPS-003 | firehose-session1 / --build-firehose | 0 / component pass | Unmodified real implementation objects, archives, symbol output and separately compiled constant ABI sections |
| E1SDEPS-004 | profile-session1 / --verify-profile | 1 / fail | Patch applies; missing C compiler rejected; positive fixture omitted freestanding flags and entered Linux libc. C++ not attempted |
| E1SDEPS-005 | profile-session2 / --verify-profile | 0 / fixture pass | Explicit freestanding kernel flags; C/C++ missing-compiler guards reject, both real arm64 Mach-O fixtures compile |

Earlier include JSON parser displays an empty BCM2837 define as null; the preserved raw macro output is authoritative. Later parser distinguishes empty from absent. No historical report was rewritten.

Compiled ABI measurements (no ARM execution):

| Field | E1S | BCM2837 |
|---|---:|---:|
| max_cpus | 10 | 8 |
| max_clusters | 4 | 1 |
| pointer_bytes | 8 | 8 |
| header_bytes | 4096 | 4096 |
| buffer_bytes | 262144 | 262144 |
| stream_bytes | 128 | 128 |
| tracepoint_bytes | 24 | 24 |
| tracepoint_data_offset | 24 | 24 |
| header_unused_offset | 1584 | 1584 |

Both implementation objects have SHA256 `3820dd8daded9bd23eb2a0647e1c8dca095b1a0059573663f4127bd95f1867be`. The E1S archive SHA256 is `0b4608274630df99cad5b74799cdbaf5715a29f5cf8f9d6f37a15a1908cb7f7e`; BCM archive SHA256 is `16d22773825b26d5c518903b52287c41e8a1d28c1abe9a190db7463f3d5929e0`. These specific observations do not prove general ABI equivalence or corruption. No pthread archive is qualified.

The final ABI reader rejects malformed/nonconstant/file-unbacked records. Five adversarial fixture tests passed. Supplemental inspection rereads both actual ABI objects using this reader and requires the exact defined Mach-O symbol `___firehose_buffer_tracepoint_reserve` with qualified nm -gUj. Preserve final-checks-session1's initial failed symbol-name assertion: it expected one leading underscore, whereas the actual C implementation has two plus Mach-O's prefix. The corrected final-checks-session2 inspection passes; this is a verifier correction, not a source/archive defect. Supplemental public reports retain both outcomes. The final helper uses exact defined-name matching rather than the original substring test.

## External input gap and next step

KRN-003 remains incomplete. Genuine pthread compilation stops at osfmk/kern/debug.h:43 including TargetConditionals.h. The donor's checked-in pthread copy explicitly labels itself a minimal stand-in and is deliberately excluded. Once genuine inputs are supplied, later missing headers or ABI issues may emerge; this is the first observed gap, not proof it is the only one.

Full XNU exporthdrs invokes iig for17 DriverKit interfaces. The donor substitutes matching macOS13.3 Kernel.framework generated headers and provides partial runtime implementations. No provenanced SDK/DriverKit paths are configured, and no complete exporthdrs/SDK ABI, pthread dependency set, full kernel or native execution is qualified. Do not use dummy SDK metadata or unsupported RPC success stubs.

The optional earlier request for a local SDK path has no answer; do not infer approval or a supplied input from elapsed time. A bounded filename-only survey of existing /home/egor/Downloads found no SDKSettings.json/TargetConditionals.h/iPhoneOS SDK match (rg exit1); candidate ~/theos, ~/.theos, ~/Library/Developer, /opt/theos and /opt/apple directories were absent. This is not a global absence claim. See artifacts/xnu-dependencies/local-input-survey-session1/report.json. No private file contents were ingested.

Next: obtain explicitly supplied local SDK and matching DriverKit/header origins, record settings/header/version/hash provenance, then extend this task's helper to use genuine exported inputs and build/inspect all actual E1S dependency archives. Preserve the old KRN-001 preflight as historical owner-reserved code; its literal SDK16.5 label test is not sufficient ABI evidence (RES-008 established the donor's Theos16.5 directory has SDK16.4 metadata). Full-kernel task handoff must distinguish this corrected understanding from its original report.

Released the finished shared research/sources.json reservation through an audited owner transaction while retaining this task's narrow implementation paths. Other independent host tasks can continue; this input gap does not block the entire research goal. No native capability status is advanced by this host work.

## Verification

`make check` passed124 tests, registry validation, generated board consistency and capability evidence checks after the exact-symbol correction. The latest log is artifacts/xnu-dependencies/final-checks-session2/make-check.log; its digest and final source/test/patch hashes are in fixtures/public/xnu-dependencies/final-checks.json. All five immutable experiment evidence digests were revalidated, and original KRN-001/NAT-001 task records and reserved implementation files are unchanged. No Android guest rerun or physical-phone operation is needed for this host change.
