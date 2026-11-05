# VM-013 IOKit shard source admission

Owner `codex-guest-exec-20261106-cv`, worktree `worktrees/vm-013-20261106`,
branch `team/vm-013-20261106`, initial base `aac27cf`.
This task owns exactly the 104 IDs in the frozen `iokit` selector and only this
procedure directory plus `fixtures/public/avf-object-shards/iokit`.
The actual language inventory is 103 C++ inputs (including 17 generated IIG
implementations) and one C input. File suffixes alone do not determine language.

The source-only inspector reads the immutable VM008 1080-row manifest and the
coordinator selector. It checks their exact SHA256 pins, complete disjoint
partition, each selected row, actual source/config/compiler hashes, genuine
DEVELOPMENT/BCM2837/arm64 flags, output placeholders and forced include lookup.
The selected report references canonical row/recipe/template hashes instead of
copying compiler recipes. It observes literal direct includes without claiming
conditional or transitive dependency closure. Missing search directories may be
unused genuine upstream arguments; retain them as observations.

Run from this worktree with constrained standard-library Python:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/avf-object-shards/iokit/inspect.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out docs/procedures/avf-object-shards/iokit/selected-source-manifest.json
```

Register the bounded source inspection experiment in MAIN before execution.
Save actual command exits, output hashes and current-image RSS. Negative controls
use owned temporary copies with changed manifest/selector bytes; both must fail
before source admission and must publish no selection. Existing output files
must also be rejected. Preserve unsuccessful attempts.

The shared VM009 runner owns actual compilation and dependency/object inspection.
Do not duplicate it. Its plan mode can consume this shard after exact runner
review. Execute mode additionally waits for VM008 acceptance and explicit root
resource admission/lease. No compiler, linker, Make, QEMU, old E1S product,
private SDK, invented provider, physical phone action or MAIN publication is
part of this source-only procedure. Full IIG ABI remains a separate assessment.
