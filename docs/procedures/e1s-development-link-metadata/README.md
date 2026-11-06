# Native DEVELOPMENT/E1S link metadata (STR-032)

This packet prepares genuine native metadata recipes. No metadata generator,
converter, compiler, Make query, final link or guest ran in this task preparation.
The task is owned by `codex-e1s-development-link-metadata-20261106-sr32`.

`fixtures/public/e1s-development-link-metadata/input.json` binds the exact local
execution plan and caller. The plan has 37 serial commands and 62 input hashes.
It uses the accepted STR014 native source derivative, STR016 native graph,
STR011 export namespace, and STR012 version context. These retain their original
physical paths. There are no guest/BCM/RELEASE inputs or replacement headers.

## Genuine recipe and consumer

The source paths and hashes are in the plan and CN's inventory
`worktrees/int-platform-20261106/docs/integration/platform/native-link-readiness-20261106/inventory.json`
(SHA256 `88ad0d071bb04b1a061d4ad1e451e2abc3bb40deda32c64c646e9064816ae991`).
Under the accepted source root:

- `config/Makefile:48–51,207–211`: original linker-export and alias scripts,
  with all 17 selected files in native order (seven base/arm64 pairs,
  Unused, Kasan_disabled, Kcov_disabled). No deletions, stubs or ABI clipping.
- `config/Makefile:81–103`: nine byte-identical owned Info template copies,
  each processed by the original `newvers.pl`, followed by the original
  symbolset script and the selected component exports.
- `config/Makefile:111–113`: original combined script in the nine-component
  order BSDKernel, IOKit, Libkern, Mach, MACFramework, Unsupported, Private,
  Kasan, Kcov; then binary serialization. Source spelling `SymbolsSets` and
  `_gOSKextUnresolved` fallback metadata are preserved, with no new provider.
- `makedefs/MakeInc.def:390,813–855`: DEVELOPMENT selects disabled sanitizer
  exports, has no ARM64 exported-symbols-list option, and still requires
  all-kpi plus alias_list and the `__LINKINFO,__symbolsets` section/permissions.
  `config/Makefile:120–145` full `check_all_exports` is a separate future
  linked-image audit; all 37 namespace export/ABI obligations remain.

`newvers.pl` uses the accepted STR012 date/object-root and native `development`
context with MasterVersion 22.5.0. It updates only these nine genuine Info
copies; version.c/version.h are not regenerated. All original version/template
source hashes are bound. A metadata result will not qualify the native objects,
provider implementations, SDK/IPC ABI, final image, runtime or hardware.

## Serializer gap and exact portable proposal

Native `plutil` was absent at `/usr/bin/plutil`,
`/usr/local/swift/usr/bin/plutil`, `/opt/swift/usr/bin/plutil`; `/opt/swift` was
absent. The qualified generator prefix does not supply it. The installed
`/usr/bin/plistutil` is RPM `libplist-2.6.0-5.fc43.x86_64` with
`/usr/lib64/libplist-2.0.so.4.6.0`. Executable/DSO bytes are pinned.
Package ownership and `plistutil --help` were read; no conversion was tested.
This is a real host serializer candidate, without native SDK or ABI authority.

| Genuine Make operation | Proposed libplist operation and required qualification |
|---|---|
| `plutil -lint -s FILE` | `plistutil -i FILE -o OWNED_XML -f xml`; parse both, compare exact typed trees. |
| `plutil -convert binary1 -s FILE` | Preserve original combined XML; `plistutil -i RAW_XML -o FILE -f bin`, then binary-to-XML and typed-tree equality. Require `bplist00`. |

Native `-s` is silent; plistutil `-s` sorts. It is never forwarded. No Python
metadata serializer is used. Python's independent plist parser only reads and
compares typed values, distinguishing bool/int, arrays, dictionaries, bytes,
dates, floats and strings. Dictionary key order is irrelevant; array order is
preserved. The proposed host control includes all those types and XML→binary→XML;
malformed XML, truncated binary, and unknown output-format controls must retain
actual rejection exits. Nine actual symbolset roundtrips and the actual combined
binary/XML roundtrip must also pass. The native-plutil oracle remains unqualified
even if these portable host controls pass.

The caller has independent `exports` (2 commands), `text` (21), and `full` (37)
phases. Thus genuine exports/aliases can proceed without converter execution;
XML/newvers results and serializer results remain distinct. A serializer failure
preserves earlier source-generated outputs and their scoped status, while the
whole full attempt fails. A fresh-output followup must explicitly adopt successful
outputs rather than rerun them. Final consumer paths stay pending until actual
outputs and portable qualification are independently accepted.

## Root-only execution contract

The reviewed caller requires external root grant path+SHA, exact caller/plan
SHA, phase, owner/task, fresh owned output, experiment and lease ID. Root must
preregister the actual experiment and review/run the exact source. The CLI marker
or grant JSON alone is not permission. The caller checks canonical ownership,
input bytes/tool identity/modes, the MAIN resource queue under the existing
integration lock, and three real `qemu_host.recovered` observations.

It reuses the exact accepted `qemu_host.run`, `owned_cancellation`, and diagnostic
work-boundary guard, with no shared edits or new process engine. Limits are one
serial child, 256 MiB combined owned RSS, 20 seconds per child, 180 seconds whole,
and existing 1 GiB child address-space cap. Actual logs, exit/status records,
output hashes, final session inventories, signals and current-image HWM are
preserved. Cleanup releases only its own lease with no live owned survivors.
No target execution is granted by this source packet.

## Preparation evidence and next step

The bounded source check passed 90 checks (recipe/pin/source derivation,
AST syntax, phase and input selection, typed comparison behavior and independent
parsing of the synthetic serializer control inputs). Controller current-image
HWM was 20,127,744 bytes. These are source checks, not serializer qualification.

An earlier inline metadata builder failed before writing the plan: it assumed
all 38 CN pins lived below the XNU source root, but four pins are accepted
interface/graph files outside it. The corrected builder validates every hash and
checks the derivative manifest only for actual source-relative paths. The failed
inline source was not saved; its observed ValueError is recorded separately.
A zsh unmatched-glob library discovery probe also failed, without conversion or
source mutation. No generator experiment failed or ran in preparation.

Next: independent source-plan review; root may grant the smallest genuine text
stage or the complete 37-command packet. Serializer qualification and actual
metadata consumer closure are still pending. Keep STR032 open until accepted.
