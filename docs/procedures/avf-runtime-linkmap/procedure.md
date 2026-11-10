# VM-047 runtime map witness controls

Owner: `codex-guest-linkmap-witness-20261106-fb`. These are bounded host tests.
They execute only Python, using the actual accepted runtime archive and catalog,
the actual/reference pinned linker source bytes, and clearly synthetic temporary
map/image/object-list fixtures. No actual selected runtime success is measured.

Before the first run, register `VM047-HOST-001` with a 120-second timeout against
this procedure. Run the maintained control script with the constrained stdlib
Python environment, a finite `timeout 120s`, and a fresh owned output directory.
The script sets a 256 MiB address-space limit, samples MemAvailable three times
at one-second intervals requiring 4 GiB, and records `/proc/self/status` VmHWM.
It imports the frozen CU source SHA
`0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464`
from `worktrees/vm-022-link-correction-20261106/tools/build/avf_guest_link_inputs.py`
for coherent snapshots and its real compact Mach-O parser. This source import is
API preparation awaiting independent acceptance; it is no execution grant.

The positive case hashes all eight built/reference linker source and license
files, the pinned source-built linker executable without invoking it, all 287
actual AR member bodies in physical order, and the accepted catalog. The map and
tiny ARM64 MH_EXECUTE image are synthetic; the CU parser reads their actual bytes.
The fixture attributes `___divtc3` to physical member 2, `2-divtc3.o`, and reports
its `_logbl` and `_scalbnl` import candidates without claiming closure. A dead-only
member remains separately reported and receives no live provider credit.

Negative controls corrupt identity, source/producer/compiler/archive lineage,
source-only/origin fields, manifest/member/order/hash bindings, map grammar,
unknown/duplicate/out-of-range file IDs, paths, addresses, external providers,
missing required members, line/byte limits, and load diagnostics. Additional
temporary-file controls exercise mutation, path replacement and no-follow
snapshot behavior. Every negative must reject. Save each outcome and preserved
fixture bytes; preserve unexpected failures and do not automatically rerun.

## Source authority and limits

`fixtures/public/avf-runtime-linkmap/source-contract.json` pins cctools-port
revision `904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb`, its APSL license and the actual
source-built linker SHA. `Options.cpp:3464-3465,3744-3745` defines `-why_load` and
`-map PATH`. `OutputFile.cpp:7210-7427` defines the exact map grammar and shows
that map write failure is only a warning. `archive_file.cpp:416-433,463-474,501,517,612`
defines archive(member) names and stdout forced-load diagnostics.
No executable help, compiler driver, linker, archive or section tool is invoked.

The file table includes live atoms, dead atoms and even unused LTO inputs. A file
table entry or forced-load reason alone receives no retained-code credit. Each
required runtime member needs a live atom and a catalog-defined external symbol
whose map address agrees with the final image nlist and section. The result does
not infer callsites, allocation retention or import closure. Ambiguous or unnamed
LTO intermediate products remain rejected until separately qualified evidence
exists. No export/provider-selection change is made.

## Borrowed API

`validate(image_snapshot, image_view, contract, *, map_snapshot, archive_snapshot,
object_list_snapshot, catalog_snapshot)` consumes CU-owned coherent snapshots
inside their contexts and returns JSON primitives. It does not open files or
start child commands. The contract binds each exact path/SHA, the fixed lineage
and source descriptor SHA, architecture, actual `-o`/`-map`/`-why_load` operands,
and a nonempty set of required physical runtime member ordinals.

The sealed object list schema `avf-guest-link-object-list-v1` contains
`source_only:false`, `actual_link_argv`, `objects:[{id,path,sha256}]` and
`archives:[{role,path,sha256,members:[{ordinal,name,sha256}]}]`. Paths must be exact
rendered linker inputs, archive member ordinals start at zero, and runtime is an
exactly-once role. Unknown archives or parent-directory allowances are rejected.
No current LTO intermediate provenance is admitted. CU must independently seal
and bind this list to its actual command and staged input witnesses.

`qualify_sources` hashes borrowed descriptor/source/linker snapshots.
`parse_load_diagnostics` optionally reports bounded runtime stdout load reasons;
it grants no retention credit. The module never authenticates execution or
grants product authority. Its `actual-link` mode reports byte facts requiring CU
authentication; a caller-written contract cannot promote synthetic facts.
CU alone owns its coherent snapshot implementation, child receipts, root grant,
phase orchestration and final product decision. Actual selected runtime success
awaits separately reviewed, leased real linker output.
