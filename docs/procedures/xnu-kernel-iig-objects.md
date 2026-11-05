# Experimental selected IOKit IIG object integration

KRN-019, owner `codex-iig-integration-20261105-ad`, parent `cc984c9`.
Host-only work; preserve all original prefixes and KRN-004/KRN-008 ownership.
No SDK/binary acquisition, global installation, phone/root/reboot/flash command.

KTAIL-005/008 bind965 actual objects out of982 known direct entries. The17 gaps
are genuine iokit/*.iig.cpo targets whose DriverKit/*.iig.cpp source paths do not
exist in the original configuration directory. The prior standalone compiler
profile does compile all17 candidate implementations, with forced IOReturn,
IORPC and per-class header inclusion. It does not measure the actual complete
IOKit generated-object rules.

The retained experimental source pairs and generator are IIGABI-013. They come
from Nyktis/iig-port ea6d147d668ca15d490da638012243fcd705f30d plus the recorded
explicit-target,selected24-byte-IORPC,Invoke-guard and host-profile changes.
The upstream tool targets observed DriverKit440 behavior and disclaims full
equivalence. Newer numeric observations are not an exact selected8796 oracle.
Every component here therefore retains false Apple-private-ABI/interoperability,
full-kernel/archive/link/crypto/native qualification flags even if it compiles.

Primary sources:

- [Selected DriverKit generation/export rules](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/iokit/DriverKit/Makefile).
- [Portable generator scope](https://github.com/Nyktis/iig-port/blob/ea6d147d668ca15d490da638012243fcd705f30d/README).

Baseline copies all17 witnessed source/header pairs into a fresh prefix and
derives each complete current command from its genuine original expanded
recipe. The ordinary IOService.cpp command independently identifies the current
global compiler/header delta. IIG's own per-file warnings and configuration
remain intact; no standalone forced-header shortcut is injected. The inherited
965 objects continue to consume their original immutable candidate headers.
Shared copied headers must remain byte-identical or every affected genuine
recipe must be rebuilt before claiming a coherent experimental object graph.

Subsequent generation/precise include/export changes need source justification,
fresh artifacts and exact before/after controls. Verify actual ARM64 objects,
source/header dependencies,symbols and message representations,not just generator
exit status. Preserve malformed-input/unsupported RPC limits. Register every
experiment before execution and retain failures. Final acceptance requires all
four task criteria,complete982 accounting and make check. A source/object result
does not establish a private Apple RPC ABI or native device operation.

## Actual integration result

IIGOBJ-002 passes all17 genuine current IOKit recipes with the unchanged
candidate sources. IIGOBJ-003 runs the recorded generator on all17 original
IDLs again, obtaining byte-identical34 header/source files, then compiles every
regenerated implementation under those full recipes. No kernel/IDL/generator
source fix or extra standalone class-header injection was needed. The actual
genuine meta_features.h forced include remains present. Original965 object
dependencies continue to resolve their original identical candidate headers;
those objects are preserved by digest/provenance,not recompiled or substituted.

IIGOBJ-006 passes22 actual controls. Selected public IORPC layout remains24 bytes
with message/reply/sendSize/replySize offsets0/8/16/20. Under KERNEL, mach_port_t
is an eight-byte ipc_port_t pointer,while mach_port_name_t remains four bytes.
The public mach_msg_header_t is32 bytes,IORPCMessageMach is36 and the port
descriptor is16 (including pad_end at offset12). These follow selected
mach/port.h and mach/message.h,not the user-port layout. Generated Start message/
reply sizes are108/60,content offset68; CopyDispatchQueue sizes are348/84,
content offset52. Both use the unchanged24-byte IORPCMessage content header.
Independent Clang17/19 public-type probes agree. Only the independent Clang19
control removes the obsolete Clang17 zero-init permission option; the actual
zero-initialization policy and genuine production recipes stay unchanged.

Actual object layout/ID data mutations and a recompiled stale-ID header are
detected against public-type/source-algorithm expectations. Message IDs are
compared to the recorded source fasthash helper,which is an internal algorithm
check,not an independent selected Apple oracle. Eleven actual host decoder
cases are rebuilt against the regenerated source,including a real guard-page
truncation check and null/size/descriptor/object-ref/callback/error variants.
That executes only CopyDispatchQueue_Invoke on x86_64 Linux. No sanitizer,
ARM execution,all-method safety or Apple interoperability is inferred.

IIGOBJ-005 independently verifies **all982 known direct ARM64 objects**:
978 selected component entries and four top-level objects. It retains all965
previous source/object/dependency witnesses and records every new exact command
and actual class-header dependency. The graph now has **3152 unique input
files**,and LLVM reports **30170 defined code symbols** (18034 T,12136 t).
An independent Mach-O nlist reader agrees with LLVM's external symbol maps for
all982 objects. There are24069 external provider names,12220 consumer names,
no strong duplicate definitions and no unresolved dependency unique to the
new17 IIG objects. Full linking has not been performed.

Twenty-two names have no provider in these direct objects. They include actual
linker section/segment/image boundaries and external/source/boot provider
requirements. This is an object-symbol inventory,not proof that all22 are absent
from a complete link. KRN-020 is queued to verify real linker synthesis,
matching firehose/pthread libraries,remaining source/boot symbols and exact
archive/link/export inputs. It must not invent empty libraries or successful
CPU/boot/crypto/RPC stubs to obtain a superficial link pass.

Use qualified-component.json,compiled-objects.json and the recorded source,
dependency,provider/consumer/unresolved-symbol manifests. All982-object results
are explicitly experimental because the portable generator and allocator
compiler lack a selected private Apple ABI oracle. KRN-004 retains that ABI
task; KRN-008 retains full object/archive/link integration. Complete SDK/library
profiles,full link/export closure,crypto/runtime,recovery and native boot,
GPU/Wi-Fi/SIM/eSIM remain unqualified. The phone and scope flags are unchanged.

## Preserved failures and replay

IIGOBJ-001 stopped on an overbroad harness guard that rejected genuine
-include meta_features.h. The corrected harness permits that original component
include while injecting none of the standalone class/IORPC/IOReturn shortcuts.
IIGOBJ-004 preserves incorrect user-message size expectations. Source inspection
of actual KERNEL port/header/descriptor definitions justified correcting tests;
no kernel macro/profile was changed to obtain the observed sizes.

The current r/hackios DriverKit search (limit5) timed out in Arctic Shift. Its
result is inconclusive and is not used to assert absence of other solutions.
Primary pinned source and actual local commands support the integration result.

Register fresh experiment IDs before these fresh-run examples:

```sh
python3 tools/build/xnu_kernel_iig_objects.py --run fresh-generation --mode regenerate
python3 tools/build/xnu_kernel_iig_objects.py --run fresh-controls --mode controls --object-evidence IIGOBJ-003
python3 tools/build/xnu_kernel_iig_objects.py --run fresh-audit --mode audit --object-evidence IIGOBJ-003
```
