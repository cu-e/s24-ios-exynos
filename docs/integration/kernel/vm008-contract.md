# VM-008 historical namespace and prospective admission

This candidate consumes the five frozen historical VM-008 commits through
`2b5aa36092a672e38c2d5ae3173a57b2fb1b7dbc`, the separately measured admission
followup through `5f4cd4ad2c4e52e7eb59cf9f4fe08954a640695b`, and the four scoped
REV-023 commits through `1f0f62d136ba555518c8dd765a21458e6ac88a34`. The source
and reviewer commit mapping is preserved in the integration plan.

The historical namespace descriptor SHA256 is
`058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7`.
Its implementation identity remains `1d8ebf6bd087431ba0959a5e65296dbd59e15d26`,
tool SHA256 `d56648d24048b97e2c519faf30cb349291b5aea8b85a640af06b71015e28b8c9`.
The frozen physical verification entrypoint is:

```text
/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-008-20261105/tools/build/avf_kernel_headers.py
```

The candidate's newer `tools/build/avf_kernel_headers.py` has SHA256
`b874e60a29ae99e0ee926f7c6fa90c09914ca1bbe5d1a06f6096a9483011a09c`.
It implements prospective three-sample admission and intentionally rejects an
old descriptor's self-hash. Its separate admission-only descriptor is
`fixtures/public/avf-kernel-headers/admission-qualified.json`, SHA256
`a9d40d614ca28bf6719cbde9b9dadcf6f0c92726330ef694768eae05677ae6a0`.
Use the frozen old entrypoint for historical helper verification. Consumers
such as VM-009 may instead verify the frozen descriptor/index and actual
namespace bytes directly without invoking either helper. They must not claim
that the old measurements ran under the new policy.

Every future execution requires three consecutive available-memory samples
at least 4 GiB, with at least one second between samples, plus the appropriate
root lease. Prospective admission does not regenerate or relabel the historical
namespace, representative objects, counter correction or retained failures.

The immutable next-object graph SHA256 is
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
It declares 1,080 DEVELOPMENT/BCM2837 source/recipe rows, including 55 generated
sources, across eight components. Historical evidence covers coherent public
source/header products, ten actual representative ARM64 objects, 192 bytes of
allocator metadata and four original negative controls; it does not establish
all 1,080 object/dependency closures, full link/image, guest startup, PID1 or PSCI
stopping. Those remain the accepted runner, admitted shard/component work and
subsequent independently reviewed boot stages.

The selected guest graph contains its own genuine minicrypto/Monocypher/BearSSL
route. Native E1S KRN-039 crypto acceptance and 37 private E1S export providers
are not artificial prerequisites for this guest profile. No native hardware,
private Apple ABI or SDK equivalence is established by namespace integration.
