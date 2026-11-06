# STR027BUILD-001 native IOKit build procedure

This is the original STR-027 owner (`codex-e1s-native-objects-20261106-sr27`) host-test experiment for all 102 accepted native IOKit objects. Root authorized only source planning at CM final `1e5a2ee8`; actual execution waits for common84 PASS and a separate root ProjectBudget grant. The earlier source slice, script, and evidence remain immutable.

Frozen physical caller (same path for later execution):
`/home/egor/dev/pet/s24-ios-exynos/worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py`
SHA-256: `2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f`.

Manifest: `/home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106/fixtures/public/e1s-native-objects/iokit/build-001-slice.json`
SHA-256: `00e7338e3dc09207363bb3e71a08e8bfd342c47bbd045363e2c14f86bb2417d7`.
The strict eight fields retain the 102 ordered IDs from the preserved source slice and qualified partition. Whole bound is 7200 seconds; each admitted component uses one serial compiler and at most 512 MiB owned RSS under the common project allocation. The caller supplies existing child deadlines and cancellation/cleanup. Root must supply its outer watchdog and exact grant.

Source-plan argv (once, stdout/stderr/raw exit retained under the task worktree's `artifacts/e1s-native-compile/plan-001`, outside the prospective execution root):

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 /usr/bin/python3 -s /home/egor/dev/pet/s24-ios-exynos/worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py plan --manifest /home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106/fixtures/public/e1s-native-objects/iokit/build-001-slice.json --manifest-sha256 00e7338e3dc09207363bb3e71a08e8bfd342c47bbd045363e2c14f86bb2417d7
```

Prospective execution root (must remain absent until actual root grant):
`/home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106/artifacts/e1s-native-compile/build-001`.
Fresh objects are expected under `objects/iokit/`, genuine MD files under `md/iokit/`, and exact configuration projections under `cwd/iokit/`. No outputs or MD hashes are predicted. The complete source plan will bind exact object/MD identities, original and projected native vectors, 5111 source files, 1334 shared context files, existing non-source metadata, absent inputs, runtime lookup snapshots, and loader commands. A plan is not actual loader/compiler/runtime evidence.

After root admission, invoke the same frozen caller in `execute` mode with the exact manifest and source-plan path/hash, plus root's exact approval path/hash, under root's outer watchdog. Do not create a second executor, add flags/includes, rerun producers/Make/features, adopt old objects, or alter the approved compiler/profile. Actual evidence must preserve every command result, MD qualification, object validity, resource observations and cleanup, including failures. Stop on a refusal. The experiment remains planned after source-plan export; source-only success cannot record actual build PASS.

The sole caller plan invocation exited 0, stderr empty. Frozen source plan:
`/home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106/artifacts/e1s-native-compile/plan-001/plan.json`
SHA-256: `27aa33e4a5e34d0f94cb064f39a379c931ed23fc69b3dcc1e5e88306a1334f5f` (4303852 bytes).
It contains 102 commands, 28 planned projection entries and 6591 input bindings. `/usr/bin/time -v` measured maximum RSS 79752 KiB. The source wrapper used an outer 180-second timeout; that wrapper does not grant actual compilation. [Plan receipt](plan-001-receipt.json) pins raw JSON, stderr, exit, time and retained prelaunch failure. The first shell setup failed before invoking the caller because `mkdir` lacked its absent parent; only directory setup was corrected, followed by the sole caller plan invocation.

Future caller argv, only after root supplies its approval and outer watchdog:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 /usr/bin/python3 -s /home/egor/dev/pet/s24-ios-exynos/worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py execute --manifest /home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106/fixtures/public/e1s-native-objects/iokit/build-001-slice.json --manifest-sha256 00e7338e3dc09207363bb3e71a08e8bfd342c47bbd045363e2c14f86bb2417d7 --source-plan /home/egor/dev/pet/s24-ios-exynos/worktrees/str-027-e1s-native-iokit-20261106/artifacts/e1s-native-compile/plan-001/plan.json --source-plan-sha256 27aa33e4a5e34d0f94cb064f39a379c931ed23fc69b3dcc1e5e88306a1334f5f --approval ROOT_APPROVAL_PATH --approval-sha256 ROOT_APPROVAL_SHA256
```

`ROOT_APPROVAL_PATH` and `ROOT_APPROVAL_SHA256` are unresolved required root inputs. No actual executor launch, loader check, compiler, Make, target tool, or private projection ran. The selected build output remains absent. The original owner experiment is registered and remains `planned`; no actual result was recorded from source planning.
