# VM-018 platform-support source preparation

Owner: `codex-guest-exec-20261106-dc`. Worktree:
`worktrees/vm-018-20261106`, branch `team/vm-018-20261106`, base
`aac27cfbc0d71b34eda33ddf366c72427507ae0b`.

This shard owns exactly 13 IDs: eleven pexpert C objects, the libsa C++
bootstrap object, and the minimal UBSan C object. The allocation and original
VM-008 manifest are immutable. The selection stores row hashes and source pins;
it does not copy compiler recipes or implement another executor.

`fixtures/public/avf-object-shards/platform-support/preflight.py` verifies the
allocation, original manifest, source/configuration bindings, target flags,
output placeholders, C++ bootstrap language, enabled allocator builtins and
compiler pin. It inventories literal includes in the direct sources using the
recorded include search order, and preserves missing declarations and inactive
branch candidates. This lexical inventory does not evaluate the preprocessor
or establish the actual transitive dependency closure.

Before the source-only experiment, register its ID in the sole MAIN registry.
Run with a fresh output directory under this procedure directory:

```sh
env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/avf-object-shards/platform-support/preflight.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out docs/procedures/avf-object-shards/platform-support/runs/preflight-1
```

The script starts no compiler, generator, linker, Make, guest or device process.
It streams file hashes, admits only three stable MemAvailable samples >=4 GiB,
and gates the current Python executable image's `/proc/self/status` VmHWM at
256 MiB. Six mutation controls use owned in-memory copies and never modify
shared inputs. Every attempt retains its report, including admission failures.

After independent VM-008 namespace and VM-009 runner acceptance, use the common
VM-009 `avf_kernel_objects.py --mode plan` with `--task VM-018`, the original
manifest and `--shard platform-support`. Compilation needs its own planned
experiment, explicit root heavy lease and resource admission. The common runner
alone substitutes the owned object/dependency output tokens and checks actual
Mach-O objects and compiler dependency records. No native E1S objects are inputs.

No object, complete kernel, link, console, PID1, stop behavior, native S24 or
private Apple ABI qualification is implied. Only integrators publish to MAIN and
run common checks under `state/.integration.lock`; this worker does neither.
