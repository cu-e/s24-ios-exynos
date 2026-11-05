# VM-038 canonical firehose namespace derivation

Owner: `codex-guest-fh-namespace-20261106-ef`. Worktree:
`worktrees/vm-038-20261106`, branch `team/vm-038-20261106`.

The original VM-014 guest OSKext/log attempts failed because their declared
canonical private kernel include root was absent and contained no installed
`os/firehose_buffer_private.h`. The exact public libdispatch kernel export
recipe installs this header privately at `/usr/local/include/kernel/os`.
This source-only derivation creates that one genuine filtered header in a NEW
immutable root and replaces the already declared search-root token in place.
It adds no `-I`, flag, SDK, stub or type definition and does not modify any
historical/current source tree, manifest, namespace or index.

The original VM-020 source handoff is commit
`c68cf193713769f92a4558ba82e3fc26be1f0a40`. The pinned upstream libdispatch
commit is `a641558f447659d90ad002ef0ee6f0212273fbfc`; the actual kernel xcconfig,
private PBX header phase, source Git blobs, license and source-built unifdef
are independently bound by the producer's public input fixture. It performs
one real unifdef export using the four canonical flags and requires exact
output SHA256 `14be8d31d66882894037431ec5df75a88e39e2100e8246a7df20ac2f708b6cb2`.

The parent manifest is `afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`;
parent qualification is `058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7`.
The exact parent namespace receipt is the immutable VM-018 execute-001
`input-bindings.json` file with SHA256
`60f7b4774bcec32ff83093629d5f1fa00ade24ecddbd4c64a2d6e96c8d75221e`.
Its embedded namespace digest is
`a2410326ba3560948edb9923b8dd8382d0557060ceaaf031735feef1bfbaa70a`:
32 reduced roots, 6721 files and four absent search roots. The new version
inherits every exact indexed parent input identity, adds the single new
header root/file, and removes the old root from the active search absence
list while explicitly requiring that retired old physical path stay absent.
No inherited source/header matrix is regenerated or relabeled.

The complete new 1080-row manifest preserves every original field except the
explicit ordered `next_owned_compile_argv_template` root-token substitutions.
The original genuine expanded make recipe stays as provenance. The
machine-readable transition binds every original/new argv digest and exact
search slot/token. Both failing libkern rows have 22 search roots and the
changed root is zero-based slot 20, one-based position 21. All source,
configuration, generated-input, compiler, resource, argument order and other
flag identities are preserved. The full artifact index inherits all 53976
parent entries unchanged and adds new publication inputs. The index and its
referring descriptor/evidence are excluded from self-indexing; all actual
compilation namespace content is bound completely.

The new header has one direct include, `<stdint.h>`, supplied by existing XNU
EXTERNAL_HEADERS. Its external firehose and Mach/BSD types are supplied by the
callers' preceding genuine tracepoint/chunk/type headers in the old namespace.
`source-type-closure.json` records exact source/header hashes, first-match
search results and literal dependency edges. Conditional edge selection and
actual preprocessed/compiled ABI closure remain unmeasured until an explicitly
admitted targeted retry. No broader new installed content is introduced.

The descriptor and `consumer-admission-contract.json` require explicit new
VM-039 consumer acceptance after VM-037 releases ownership. The old runner's
`afc5...` hard PIN must not silently accept the new version. Every object key
binds schema, new manifest, new namespace, exact argv digest, source,
configuration, compiler path and cwd. Cross-version sidecars/resume must be
rejected; old objects keep their actual old namespace provenance and are never
credited as new-version compilation.

Controls use actual isolated files and the real admission predicates to reject
changed export flags/source, missing new headers, extra shadow files, symlinks,
profile overrides, source binding changes and namespace content changes.
The old absent roots and exact parent manifest/qualification/index/receipt
hashes are rechecked before publishing the source-only capsule.
No compiler, archive, full kernel build/link, guest, phone or common check is
run. Independent review, a reviewed new consumer and an explicit root lease
are prerequisites for any future retry.

The derived `object-shards.json` preserves parent selector file `855246...`
physically. Only `source_manifest` and `sha256` become the child manifest path
and digest; all ten ordered shard arrays and their 1080 IDs are identical.
The new consumer must enforce that identity instead of waiving the old check.
Artifact-index keys retain the parent's main-relative or absolute spelling.
Apply the existing `(MAIN / Path(name)).absolute()` normalization and reject
conflicting aliases before namespace coverage checks; do not confuse this
normalization with permission to mutate any physical old path.
