# Accepted guest source profiles

VM-039 adds explicit admission for two immutable source profiles in the existing
object executor. It does not authorize this tooling task to compile objects.

The legacy profile retains manifest `afc5cd20`, qualification `05845193`, selectors
`85524647`, namespace `a2410326`, its exact key formula, command recipes, and plan
bytes. The second profile binds the accepted VM-038 manifest `be02fbfc`,
qualification `3343a382`, selectors `408720d8`, and namespace `25f22291`. Other
combinations and arbitrary manifest overrides are rejected.

The new route validates the full qualification, export/source/context/index,
exact ordered 1080-row same-position root substitution, 55 generated inputs,
complete parent-plus-one-header namespace and frozen input-key schema. It reuses
the accepted namespace validator without rerunning header export or a compiler.
The old absent root remains absent. No existing object is credited to this new
namespace; resume requires the exact same manifest and namespace identities.

The accepted shared ProjectBudget implementation and APIs remain unchanged from
EFE908ff. The entire executor SHA changes, so VM-036 and future root approvals
must refresh their process pins once after final independent acceptance. No
intermediate candidate is a granted compiler runner.

The owner of VM-039 has a literal reservation exception for source-only plans.
`execute` remains forbidden for this task. Actual shard owners retain their own
literal scope, registered experiments, new root allocations, serial compiler
slots, 512 MiB cap and 120 second per-child guard. Large 222/226-command shards
need a new whole-pipeline deadline of 1800 seconds; the old 600 second launch plan
must not be reused. An actual six-job trial remains a separate root grant.

Run the targeted profile controls after MAIN experiment registration:

```sh
python3 fixtures/public/avf-guest-profile/check.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --experiment VM039PROFILE-001 \
  --out artifacts/avf-guest-profile/frozen-001
```

The controls execute genuine old/new source-only CLI plans, compare legacy plan
bytes and recipes/keys with an immutable prior plan, check unchanged budget ASTs,
and exercise descriptor/manifest/selectors/source/flag/root/symlink/absence/shadow
and cross-profile resume failures. They do not run a compiler, archive/link tool,
QEMU, full common checks or any phone action. Original EJ closes only after
independent review and root common acceptance.
