# Guest IIG declaration and provider audit

VM-032 supplies a bounded source audit of all 17 generated guest IIG pairs
against the exact 104 selected iokit recipes. It finds no missing lexical method
declaration, dispatch declaration bridge or implementation-provider candidate.
It does not establish that the 16 outstanding implementation interfaces compile
or match the selected Apple RPC ABI. No source patch is justified by these
observations.

`tools/build/avf_guest_iig_closure.py` reads the frozen VM-008 inputs and their
VM-007 composition pins. It verifies the source SHA256 and canonical Git blob
SHA1 of declaration/provider inputs, all 104 bound source/configuration hashes,
17 IDLs and 34 generated outputs, the real typed-builtin compiler, public IIG
producer/source and its libclang/LLVM/resource-header pins. It executes none of
those tools. Output arguments remain templates for new owned directories.

The report contains exact file paths, hashes, line numbers, declaration macro
bodies, public include chains, emitted request/reply record fields and lexical
packing state. Record sizes and offsets are explicitly unmeasured. The lexical
inventory includes conditional candidates; the C++ frontend must still resolve
conditions, overloads, types, inheritance, layout and actual imports.

The inventory contains 95 primary RPC method IDs, 229 primary implementation
method definitions, 564 RPC record declarations and 98 qualified `_Impl`
references. The complete scope inventory also retains auxiliary callback and
metaclass definitions. The provider search follows 932 public source/header
files from the 87 direct iokit source recipes.

| Interface | RPC IDs | Primary definitions | RPC records | `_Impl` references |
| --- | ---: | ---: | ---: | ---: |
| IOBufferMemoryDescriptor | 2 | 6 | 12 | 2 |
| IODMACommand | 5 | 12 | 30 | 5 |
| IODataQueueDispatchSource | 8 | 20 | 48 | 9 |
| IODispatchQueue | 2 | 6 | 12 | 2 |
| IODispatchSource | 4 | 10 | 24 | 1 |
| IOEventLink | 3 | 8 | 18 | 3 |
| IOInterruptDispatchSource | 5 | 13 | 30 | 8 |
| IOMemoryDescriptor | 4 | 10 | 24 | 4 |
| IOMemoryMap | 1 | 4 | 6 | 1 |
| IOService | 36 | 74 | 216 | 38 |
| IOServiceNotificationDispatchSource | 4 | 11 | 24 | 6 |
| IOServiceStateNotificationDispatchSource | 4 | 11 | 24 | 5 |
| IOUserClient | 6 | 14 | 30 | 4 |
| IOUserServer | 3 | 8 | 18 | 4 |
| IOWorkGroup | 3 | 8 | 18 | 3 |
| OSAction | 3 | 8 | 18 | 3 |
| OSObject | 2 | 6 | 12 | 0 |

Two details prevent misleading missing-method diagnoses:

* `OSMetaClass.h` inserts `className_Methods` and `className_KernelMethods`
  through `_OS_ADD_METHODS_dispatch`. Public native class headers use
  `OSDeclare*WithDispatch`; generated KERNEL class declarations use the same
  bridge. OSObject uses the longer
  `OSDeclareAbstractStructorsWithDispatchAndNoOperators` spelling.
* All nine IODataQueueDispatchSource `_Impl` candidates live in
  `iokit/System/IODataQueueDispatchSourceShared.h`, included by the selected
  `iokit/Kernel/IOUserServer.cpp`. Looking only at `.cpp` files loses those
  genuine definitions.

The pinned historical IIG report contains 16 failed implementation compiles
using the older native E1S/NDK context. Thirteen terminate on typed-allocation
builtins and an undeclared `XNU_NO_TYPE_BUILTINS`; three terminate in metaclass
typed allocation for OSAction, IODispatchQueue and IODispatchSource. These logs
are retained with their exact historical commands/exits and capsule-bound
hashes. They do not prove missing guest methods or provide guest compile
results. Every current guest iokit recipe already selects the source-built
typed-builtin compiler and `-DXNU_NO_TYPE_BUILTINS=0`. Its effect on the 16
implementations still needs actual admitted compilation.

VM-008 separately records a genuine OSObject.iig ARM64 representative compile
in `representatives-2/report.json`; this audit does not repeat or broaden that
result. Historical public IORPC layout observations and numeric cross-version
IDs remain separate from a selected-version independent generated-header or
marshalling oracle. The public producer is Nyktis/iig-port
`ea6d147d668ca15d490da638012243fcd705f30d`, reporting DriverKit-440, with retained
target, legacy-RPC and Invoke-guard source ports.

Run the audit with a fresh output path:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  tools/build/avf_guest_iig_closure.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --output artifacts/avf-guest-iig-closure/new-run/report.json
```

The five `--control` modes mutate only in-memory metadata and must reject with
exit 2: `source-hash`, `generated-hash`, `missing-recipe`, `wrong-target` and
`missing-builtin-contract`. Real failures and initial development reports remain
available. Independent review is required before integration. VM-008 acceptance,
root resource admission and the appropriate compile task are required before
new compilation. No compiler, QEMU or physical-phone operation is performed by
this task; no main common check or publication is claimed.
