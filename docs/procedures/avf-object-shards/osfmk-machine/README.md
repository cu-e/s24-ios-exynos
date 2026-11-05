# VM-015: osfmk machine source admission

Owner `codex-guest-exec-20261106-cz`; branch `team/vm-015-20261106`;
worktree `worktrees/vm-015-20261106`. This task reserves only this procedure
directory and `fixtures/public/avf-object-shards/osfmk-machine`.

`selection.json` selects exactly the 77 `osfmk-machine` IDs from the coordinator's
disjoint 1,080-object allocation. The frozen VM-008 manifest SHA256 is
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
The selected profile is ARM64/DEVELOPMENT/BCM2837, canonical source tree
`6a955269a8f4e17d21239f75cef9fbe66cffc56c`. Existing E1S objects are not guest inputs.

The standard-library `preflight.py` audits data without running a compiler,
preprocessor, generator, donor build, or guest. It verifies the full allocation
partition, exact selected row order, immutable source/configuration hashes,
qualification/index/source-composition bindings, genuine compiler identity,
target and metadata flags, and per-object output placeholders. It preserves the
unaltered complete selected rows as an artifact, rather than copying an executor.

Declared search roots retain their exact order, including genuine absent search
directories. All forced includes and sanitizer inputs must exist and match the
qualified index. A lexical scan records literal direct source includes and hashes
the first existing candidate in the declared search order. Conditional and macro
includes are not evaluated. Unresolved literal includes are observations, not
proof of an actual missing compiler dependency. This scan does not establish the
preprocessor's active transitive dependency closure, which remains unmeasured
until an admitted real compile produces dependency files.

Register the experiment in the sole MAIN registry before the source check:

```sh
env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/avf-object-shards/osfmk-machine/preflight.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-015-20261106/artifacts/avf-object-shards/osfmk-machine/preparation-1
```

Outputs must occupy a new directory under the owned worktree's `artifacts`.
Every attempt retains its report, errors, commands, exit code, hashes, time and
actual `/proc/self/status` VmHWM/VmRSS. The inherited Linux ru_maxrss is recorded
separately. Hashes stream file contents. Admission uses three one-second samples
of MemAvailable >=4GiB; continuation checks the floor, 256MiB executable-image
high-water mark and 180-second deadline. No process is launched or terminated.

Five negative controls reject duplicate allocation, foreign object substitution,
changed source binding, an escaped object output and disabled allocator metadata.
They mutate owned in-memory copies and leave all shared source bytes untouched.
Actual compiler success, object hashes/metadata and active dependency closure
remain required before shard build acceptance.

VM-009 owns the common executor. Its compatible CLI is `--mode plan --main MAIN
--task VM-015 --owner codex-guest-exec-20261106-cz --experiment PLANNED_ID
--manifest FROZEN_MANIFEST --manifest-sha256 FROZEN_SHA --qualification VM008_JSON
--qualification-sha256 QUALIFICATION_SHA --selectors ROOT_OBJECT_SHARDS_JSON
--selectors-sha256 ALLOCATION_SHA --shard osfmk-machine --out NEW_OWNED_DIRECTORY`.
Do not invoke that runner before its independent acceptance. Compile only the
77 allocated IDs after VM-008 namespace acceptance, VM-009 executor acceptance
and an explicit root heavy lease. Keep at most two compiler jobs total, at most
2GiB new owned RSS and the stable 4GiB admission floor under that lease.

No SDK/private ABI, full kernel/link, guest/boot or phone claim follows from
source preparation. MAIN publication and common checks belong to the permanent
integrator under MAIN `state/.integration.lock`. Keep VM-015 in progress until
independent review, integration and root acceptance.
