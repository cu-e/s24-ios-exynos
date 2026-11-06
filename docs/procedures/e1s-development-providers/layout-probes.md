# Separate auxiliary native layout measurements: source plan only

Original STR018 owner remains `codex-e1s-development-providers-20261106-sr18`.
`layout-plan.json` binds `layout-plan-001/execution-plan.json` SHA256
`1b6aae04b95c2df05128a40b96e871849bef5d4dae4790e7897b4b2c33ca9858`
and source capsule SHA256
`51491ecee6e7eae855115a7ea385fc063b16a2f997c0cef73e14a75813f9a536`.
Prospective experiment `E1SPROVIDERLAYOUT-001` is separate from ROOT104 production
and ROOT111 tool reads. Fresh `layout-probe-001` is absent. No compiler,
preprocessor, layout probe or target tool has run for this source preparation.

There are exactly two tiny const-only TUs, `layout-provider.c` and
`layout-consumer.c`. They include genuine shared Firehose headers in the
provider/native-consumer spelling and prerequisite order, plus genuine selected
board and mach_assert headers. Provider KERNEL-local switches come from the
actual source; no layout/type/value fallback is defined. Both arrays use a
224-byte __DATA_CONST,__s24fh record with28 unsigned64 fields. These measure the
CPU/cluster/physical-cluster tuple, MACH_ASSERT/DEVELOPMENT, pointer width, and
only genuinely shared tracepoint-id/tracepoint/chunk-position/chunk/range/stream
sizes, alignments and non-bitfield offsets. Format version/word width are record
metadata. Layout answers are not hardcoded; numeric facts remain unknown until
actual target evaluation and comparison.

The provider command is the exact accepted ROOT104 Firehose command from plan003.
The native consumer command is literal current BSDb plan004 command154,
`bsd/subr_log.o`, original BSD selection336, bound by plan SHA256
`c38fcc616647dfba60050d840f17790c00396bfc8783d69d7f2029cd627c6b5f`.
Each command changes exactly three argv positions: source TU, -MF destination,
and -o destination. Flags, include order and cwd are unchanged. The genuine
consumer's two subr_log per-file warning exceptions stay only in its consumer
vector. They do not enter the provider vector. Delta source evidence SHA256 is
`f66d5f7c20c40d1c1529e3ce05f88647c54fa5fe02e28cc8e4efc46d31f1a933`.

Existing ROOT104 native-BSD72files and current consumer73private projections
are fixed read-only inputs; no header/config/MIG/namespace regeneration or fake
SDK is proposed. The source packet pins7410 inputs and a prospective7418-entry
MD identity catalog from accepted namespace/producer inputs. This is not actual
probe dependency closure: each later actual MD must name the exact TU and
object and every transitive path/hash must be qualified. Unknown/changed input
fails closed. Existing actual ROOT104315headers/4objects/2archives and ROOT111
raw outputs remain untouched. Existing source-built compiler7972 and actual
feature receipt01d7 are reused; no feature or source corpus replay occurs.

Root alone may dispatch these two serial compiles after independent source
review and a separate root grant: one compiler,512MiB owned tree,120s per child.
Reuse the reviewed600s dispatch/work-boundary budget plus up to45s final shared
admission and finite owned cleanup; root external GNUtimeout690s is required.
No new controller, parser, timer or shared-helper change is added. Existing
common9929 ProjectBudget/run_child/dependencies and core9f80 cancellation and
coherent Mach-O APIs supply the established boundaries.

After a separately admitted actual run, locate the exact external array symbol
in its genuine file-backed const section using existing core.macho_snapshot.
Require ARM64 subtype0 MH_OBJECT, exact224-byte bounds, no record relocations,
and no unexpected external definitions/imports or functions. A bounded existing
snapshot.read_range and standard struct.unpack(<28Q) read the data; there is no
new Mach-O parser. Check record metadata, actual CPU10/cluster4/PHY9 and selected
MACH_ASSERT1/DEVELOPMENT1, then require all28 actual fields equal between the two
contexts. Preserve actual arrays, commands, MD, diagnostic/resource records,
input/output hashes and zero-owned-survivor cleanup. No numeric Firehose size
is accepted from source planning or unsupported ROOT111 disassembly.

Auxiliary objects never enter archives, final kernel inputs or runtime.
Native pthread_shims/subr_log actual consumer products/MD, callback compatibility
and final selected native definition/alias bindings remain separate requirements.
Even passing these records does not establish full private ABI, a final link or
image, runtime, hardware or iOS. No device or QEMU operation is proposed.
