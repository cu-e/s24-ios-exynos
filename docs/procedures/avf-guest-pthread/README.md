# Fresh guest pthread component

VM-021 prepares the three genuine libpthread kernel translation units at
`a6c70ca0e544347a0377babf748f831577ec24f9` for the immutable VM-008 guest
installed namespace. This preparation performs no compiler or guest execution.
The source plan selects BCM2837, iOS16.5, genuine kext development definitions,
native development LTO disabled, real metadata builtins, and two witnessed
static-integration namespace remaps.

Register a source-preparation experiment before running:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s tools/build/avf_guest_pthread.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-pthread/prepare-1
```

The builder verifies the frozen handoff, graph, prepared descriptor, installed
header manifest and all 1869 installed header hashes. It copies tracked genuine
pthread source text after canonical Git blob SHA1 and SHA256 verification, then
applies the existing narrow address/callback conversion patches only in its
owned copy. The public TargetConditionals contribution is independently bound
to pinned PureDarwin source and its retained native-iOS patch. Availability
supplements come from the exact prepared guest source. Component notices remain
in local source copies; no Apple SDK, archive or binary is committed.

`callback-alias-source-witness.json` records real function and callback table
declarations and the three native VM alias declarations from guest exports.
This is source evidence. Compiled sizes, offsets, types, allocator metadata,
actual provider definitions, undefined imports, archive members and relocation
identity must be measured on freshly compiled guest objects. An old E1S archive
or its measured symbol closure is not a guest result.
The unpreprocessed surface includes 45 function fields and 96 callback fields;
the callback count includes an ARM32-only conditional slot. It is not an ARM64
field count. Compiler preprocessing and layout measurements remain required.

After a preparation is independently reviewed and its execution plan frozen,
run the finite source-plan controls. The current freeze names `prepare-2`:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s docs/procedures/avf-guest-pthread/verify.py \
  --plan artifacts/avf-guest-pthread/prepare-2/component-plan.json \
  --out artifacts/avf-guest-pthread/controls-reviewed-new
```

`validate_plan` binds the complete frozen plan, including every argv token, to
an expected canonical hash committed separately from the candidate. The source
builder's `validate_preparation_plan` checks structure only and cannot admit
execution. New preparations need a reviewed freeze. See the focused
[predicate correction](predicate-review.md); original evidence is preserved.

`component-plan.json` is a proposed three-TU provider plan, outside the 1080
kernel-object graph. VM-009's accepted bounded process API will execute it after
independent namespace acceptance, runner acceptance, a registered compile
experiment and explicit root resource admission. This builder cannot compile.
Archive construction and full callback/metadata/alias controls remain separate
gated work. Only integrators publish main or run common checks under the shared
integration lock. Physical phone operations are outside scope.
