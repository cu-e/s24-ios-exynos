# Source-only firehose namespace handoff to VM-038

Original VM-020 owner remains `codex-guest-exec-20261106-cx`; the task and
AVFFH-001 planned experiment are not completed or reassigned. Root separated
the missing guest header namespace into a new VM-038 task, requiring its own
unique owner/worktree and explicit new qualification/manifest route. No
additional process metadata refresh is made while VM-037 API acceptance is
pending. The existing bounded four-command plan and filelist remain unchanged.

Read-only source facts established while inspecting the reported VM-014
failures, without compiler, preprocessor, unifdef or source/header matrix rerun:

- Genuine pinned libdispatch revision is
  `a641558f447659d90ad002ef0ee6f0212273fbfc`. Its
  `xcodeconfig/libfirehose_kernel.xcconfig` line 29 declares
  `PRIVATE_HEADERS_FOLDER_PATH = /usr/local/include/kernel/os`.
- The real kernel Headers phase exports `firehose_buffer_private.h` privately;
  the exact flags are `-DKERNEL=1 -DOS_FIREHOSE_SPI=1
  -DOS_VOUCHER_ACTIVITY_SPI_TYPES=1 -UOS_VOUCHER_ACTIVITY_SPI`.
- The genuine preserved session3 export is
  `preparation-session3/export/include/kernel/os/firehose_buffer_private.h`,
  SHA256 `14be8d31d66882894037431ec5df75a88e39e2100e8246a7df20ac2f708b6cb2`.
  It includes only `<stdint.h>` directly and retains the upstream license.
- The actual frozen `libkern/OSKext.cpo` and `libkern/log.o` rows each have
  22 include search roots. The existing canonical
  `handoff-1/public-source-context/usr/local/include/kernel` root is itself
  absent, at zero-based search slot 20 (one-based position 21). Do not create
  it or change its old absence proof. Root replacement must preserve that exact
  search position and argument form, adding no include option.
- Both callers include genuine `firehose/tracepoint_private.h` then
  `firehose/chunk_private.h` immediately before the missing os header.
  Their first matching headers are in the selected new guest source
  `prepare-2/source/xnu/libkern/firehose`, ahead of raw exports.
- The exported header's direct `<stdint.h>` resolves to existing selected
  `prepare-2/source/xnu/EXTERNAL_HEADERS/stdint.h`. The adjacent `<stdbool.h>`
  resolves to that same EXTERNAL_HEADERS root when requested.
- `firehose_types_private.h`, imported by the preceding tracepoint/chunk
  headers, provides `firehose_stream_t`, `firehose_push_reply_t` and
  `firehose_buffer_t`; it imports `<mach/mach_types.h>`, `<mach/std_types.h>`
  and `<os/base.h>`. The tracepoint header provides
  `firehose_tracepoint_t` and `firehose_tracepoint_id_u`. These are existing
  guest namespace dependencies, not new stubs to manufacture. No compiled
  type/layout or complete preprocessed closure is claimed by this read-only
  observation.

One discovery `rg` mistakenly searched raw `EXPORT_HDRS/bsd/stdint.h`, which
is absent, returning exit 2. Actual argv-based lookup established the existing
EXTERNAL_HEADERS path above. No source or namespace was modified.

Next VM-038 should reuse these established facts, freeze the one genuine
header at canonical install layout in a NEW immutable physical root, inventory
its exact source/type dependency edges and first-match resolutions, and issue
new complete namespace/index/1080-manifest/input keys. It must explicitly bind
a new accepted consumer route; the historical `afc5...` manifest PIN cannot
silently accept replacement roots. Old roots, manifests, indexes, active wave
inputs and evidence remain immutable. Root/INT002/INT003 coordinate acceptance;
no automatic retry, rebuild, compiler, archiver, guest or common check follows
from source preparation.
