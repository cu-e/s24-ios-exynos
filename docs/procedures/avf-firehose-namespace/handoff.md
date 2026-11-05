# VM-038 source-only handoff

Owner: `codex-guest-fh-namespace-20261106-ef`; branch
`team/vm-038-20261106`; worktree `worktrees/vm-038-20261106`.
Base MAIN commit: `f22951619f2869adeea329f0ae1a7c3d8fdfc8a4`.
Original VM-020 owner/task/AVFFH-001 remain unchanged. This task owns only
`tools/build/avf_firehose_namespace.py`, `fixtures/public/avf-firehose-namespace`
and `docs/procedures/avf-firehose-namespace`.

The first actual source-only qualification ran after AVFFHNS-001 registration
and returned exit 0. It performed only two read-only Git commands and one
real source-built unifdef export. The complete frozen output is
`qualification-session1/qualified-component.json`, SHA256
`3343a382452d05c382a15ea54e3835c3125c67c451cb586a1c3ed5a939b37174`.
The new immutable install root contains one licensed genuine header at
`installtree/usr/local/include/kernel/os/firehose_buffer_private.h`, exact
SHA256 `14be8d31d66882894037431ec5df75a88e39e2100e8246a7df20ac2f708b6cb2`.
The canonical historical root still does not exist; no old source/header/tree,
manifest, index, selector, receipt or current-wave artifact was changed.

The new 1080-row manifest SHA256 is
`be02fbfc38a73831d3570e69b24277917e69efc09cd696cc853521c393edc298`.
Every row changes only the declared canonical include-root token at its exact
old position. Both failing libkern rows retain 22 roots and zero-based slot20.
All IDs/order/source/configuration/generated/compiler/resources/flags remain
identical; the original expanded make strings retain original provenance.
All 55 generated inputs remain selected. The new embedded namespace digest is
`25f22291e314445a01a4030e7db74f8cebd9a935b604eefc7b1ad9f5ee033461`.
It retains all 6721 parent file bindings plus the one header; the full index
retains all 53976 parent entries and adds 21 new publication inputs.
Derived selector SHA256 is
`408720d8bbdbc982079f778ce662f20051dc1d761b9ca216346896a5dabf0744`:
only child manifest path/digest change from the preserved parent855 selector;
all ten ordered shard partitions remain unchanged.

`manifest-transition.json`, `source-type-closure.json`, `canonical-export-proof.json`
and `consumer-admission-contract.json` contain exact machine-readable lineage.
All 1080 new object keys bind the new version/schema/manifest/namespace/argv
and source/configuration identities; no old object or sidecar is credited as
new-version compilation. Explicit independently reviewed VM-039 consumer
admission after VM-037 ownership release is still required; old afc5-only code
must reject this version. No retry is automatically authorized.

Eight real controls rejected changed export flags/source, a missing header,
extra shadow content, a symlink, a later -UDEVELOPMENT override, a source
binding change and a namespace content change. Source producer VmHWM=115932 kB,
VmRSS=107328 kB. Separate read-only checks in
`fixtures/public/avf-firehose-namespace/check.py` verified all1080 row changes,
namespace/index coverage, old absence, selector lineage and exact object keys
(exit 0). Its first attempt incorrectly required literal absolute keys in the
mixed relative/absolute parent index and failed exit 1; the exact failing
checker/output/result are retained in `independent-check-attempt1*`.
Correcting the checker to the existing accepted main-relative normalization
passed in `independent-check-session2.json`. No qualification output was
regenerated or altered for that checker correction.

No compiler, preprocessor, archive, linker, kernel/guest, physical phone,
source/header matrix or common check ran. The new header's only direct include
is existing XNU stdint.h; first-match firehose/Mach/BSD prerequisite type
headers are bound to parent namespace identities. Literal conditional edges
are recorded, not presented as a measured preprocessed closure or compiled ABI.
Independent review by INT003/INT002 and root, followed by a new reviewed
consumer and root lease, must precede actual targeted OSKext/log compilation.
Original owner alone records task completion after required acceptance.
