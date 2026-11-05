# VM-035 measured namespace iteration cost

Owner codex-guest-namespace-cost-20261106-dt; separate worktree/branch
worktrees/vm-035-20261106 / team/vm-035-20261106, base36c7dce7c18a2cefbf5ae41032915b2a8a5a8006.
Only tools/build/avf_kernel_objects.py, fixtures/public/avf-namespace-cost and
this procedure directory are owned. No MAIN publication/common checks or
compiler/QEMU is authorized. Old physical VM009 helper132135... is immutable;
existing77/104-object jobs continue using it. Root acceptance/publication only
at a build boundary.

Actual baseline is VM018 platform-support plan-001/plan:6721 bound files,
32 present roots,4 absent roots,53976 artifact index entries; observed prior
shared plan75.907s. Its exact provenance and source descriptor are pinned in
inputs.json. Profile real binding on those immutable files, with independent
fresh Digests instances and no cross-run validation cache. Measure wall/process
CPU plus cProfile call/time data. The prospective optimization only hoists Path
parsing out of the index-by-root loop and compares complete path-part prefixes.
All filesystem, missing, absent/shadow/symlink, digest/ctime, recipe flags,
provenance and authorization/resource code must remain unchanged.

Compare actual selected plan/input-binding bytes (normalizing owned output root
only), source/config/header namespace digest, and every1080 recipe/input key.
The complete graph plan projection uses the exact unchanged pure tail of bind
AFTER actual shared validation of all1080 sources/recipes and namespace; it is an
equivalence proof, not an operational extra shard or executor. No compiler is
called and no operational selector is extended. Existing baseline13-ID plan is
also compared to fresh original/candidate actual bind results.

Focused negative controls use real owned temporary files/directories, not a fake
filesystem or simulated timing: missing indexed input, unindexed/shadow input,
optional absent-root appearance, directory symlink, indexed file symlink,
component-prefix collision and genuine ctime-triggered hashing with restored
mtime. Actual performance numbers come only from the frozen real guest context.
All run failures, real commands/exits, file/tool/source/output hashes and current
image controller/owned RSS are retained. Register before running; source-only
children use the reviewed finite process guard, <=256MiB controller+child and
three >=4GiB samples. No source/global host/cache/swap changes, no phone.

## Actual result

The baseline cProfile run took178.243359 s wall /175.927211 s process CPU;
namespace accounted for176.613945 s. Its1,633,334 is_relative_to calls took
170.252371 s cumulative (~95.5% of bind), including repeated ancestor creation
on the actual Python3.14 pathlib implementation. The candidate took7.802603 s
wall /7.011098 s process CPU under the same profiler, about22.84 times faster
for this measured profiled bind. These are profiler-instrumented timings, not
unprofiled future build promises; the immutable75.907 s prior shared run is
context only. No compiler timing is included or changed.

The only production code change replaces the missing-index comprehension with
one Path(name).parts parse per index entry and complete-root-part tuple-prefix
comparison. Index iteration/error order and every filesystem check are retained.
No hashes, checks, includes, flags, metadata support, output policy, selector,
resource policy or cache lifetime changed. Source matching in check.py requires
the entire candidate file to equal the original plus that exact replacement.

Actual sha calls6726, stat calls16660, resolve calls28512 and engine Digests.get
calls9934 are unchanged. Current image HWM was101617664 /101797888 bytes;
combined guard peaks126488576 /126656512 bytes with zero live children. cProfile
raw files and call tables are retained. Every bind creates fresh Digests; the
comparison independently rehashes all6721 actual files after both runs.

VMNSCOST-002 passed19 equivalence/real-filesystem checks. Actual binding bytes
match original VM018 SHA60f7b4774bcec32ff83093629d5f1fa00ade24ecddbd4c64a2d6e96c8d75221e,
namespace digest a2410326ba3560948edb9923b8dd8382d0557060ceaaf031735feef1bfbaa70a.
The actual13-ID selected plans normalize to identical bytes with only the two
owned output arguments replaced. The actual unchanged pure tail projects every
1080 validated row and verifies exact input keys/argv/provenance bytes, also only
normalizing those outputs; this proof is not an operational extra shard. All ten
real selector sets are checked. Projection does not replace any actual binding
or compiler checks; both real full binds independently performed those first.

Focused real-FS results preserve first missing-error order, complete-component
prefix behavior, literal parent-component index semantics, changed/missing/
unindexed/shadow headers, absent-root appearance, directory-symlink rejection,
qualified file-symlink behavior and ctime cache invalidation after actual writes
with restored mtime. The comparison's first attempt incorrectly treated relative
report-directory arguments as absolute and rejected an owned output; it remains
failed in equality-session1. Fixing only comparison normalization produced
PASS equality-session2. Neither expensive measurement was repeated. Captured
measurement fixtures remain in their artifacts; later comparison-only fixture
changes do not change the measured function or production code.

Reproduce using the pinned original physical helper and reviewed finite guard:
`check.py --phase supervised-measure --engine FILE --engine-sha256 SHA --out NEW`.
Then `check.py --phase compare --original OLD_MEASUREMENT_JSON --candidate
NEW_MEASUREMENT_JSON --out NEW`. The benchmark calls actual source-only bind;
it does not impersonate a shard owner, run the operational CLI or start a
compiler. No MAIN publication/common checks occurred. Existing build jobs must
continue on132135 until independent review/integrator/root approval at a BUILD
BOUNDARY. Existing strict executor-hash resume checks are unchanged; no automatic
cross-version resume is claimed.
