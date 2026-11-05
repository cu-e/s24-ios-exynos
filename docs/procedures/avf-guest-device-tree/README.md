# VM-027: AVF guest serialized device tree

Owner `codex-guest-exec-20261106-di`; branch `team/vm-027-20261106`;
worktree `worktrees/vm-027-20261106`. All preparation is host-only.

The actual-data gap is now resolved for the selected console contract. One
root-leased run of the unchanged source-built shim and existing owned synthetic
spin payload produced an Apple tree at `0x4300c000`, length `0x30fc` (12,540
bytes). QMP confirmed paused state, saved precisely that virtual RAM extent,
and quit with exit 0 and no surviving owned processes. The existing parser passed
14 nodes and 38 property checks; all nine missing/malformed actual-byte copies
were rejected. The dump SHA256 is
`afa048b454b658399636030abe71bc706665fb722564459b93e75609f7d6d491`.
See [capture evidence](evidence-capture.json). This observed a shim and synthetic
spin fixture, with no XNU, PID1 or phone execution. The historical source-only
inconclusive capsule remains unchanged.

The owned parser and preflight target the exact Scion AVF shim at
`a6f4bc38aa244359cd365c976244a88c9d6b3304`, with the accepted VM007 composed
QEMU XNU tree `6a955269a8f4e17d21239f75cef9fbe66cffc56c` based on public XNU
`c54f35ca767986246321eb901baf8f5ff7923f6a`. The source pins list SHA256,
content Git blob SHA1, size and origin for each traced source. A composed-file
blob identity does not assert that the file occurs in the unpatched public tree.
Original license texts remain beside immutable sources; upstream code is not
vendored by this task.

The shim consumes a big-endian flattened device tree from QEMU/crosvm and emits
a different Apple serialized tree at runtime. `avf/shim/avfboot.c:488` writes
little-endian `u32 property_count, u32 child_count`, then properties, then child
nodes recursively. Each property is a zero-padded 32-byte C name, little-endian
u32 byte length, raw value, and zero alignment padding to four bytes. Numeric
values use the little-endian ARM64 native widths, rather than FDT big-endian
cells. The source `DeviceTreeNode` and `DeviceTreeNodeProperty` definitions and
`next_prop_region()` agree with those widths and alignment.

The parser limits the input to the genuine `DT_MAX=65536`, depth to the writer's
16-entry stack, and uses finite additional node/property budgets. It rejects
truncation, huge counts/lengths, nonterminated or ambiguous names, duplicate
properties/nodes, nonzero padding, and trailing data. These are deliberate
selected-writer restrictions; the parser is not a complete generic Apple DT ABI.
It never infers runtime provenance from successful parsing.

| Producer and node/property | Genuine consumer and meaning |
| --- | --- |
| `avfboot.c:882`, root `name`, `platform-name=t8015`, cell widths=2 | `pexpert/gen/device_tree.c` performs name/path/property lookup; `pe_init.c` reads root identity. Identity is source-provided, with no hardware compatibility claim. |
| `avfboot.c:893`, `/chosen` random-seed64, dram-base/size u64, PSCI string | `osfmk/arm/arm_init.c:765` reads DRAM; `pexpert/gen/pe_gen.c:148` reads entropy; `psci_smp.c:201` reads method for SYSTEM_OFF even with one CPU. `hvc` selects HVC, `smc` selects SMC. |
| `avfboot.c:931`, `/chosen/memory-map/RAMDisk` u64 physical address,size | `iokit/bsddev/IOKitBSDInit.cpp:770` uses this as a RAM device. The property is conditional on a nonempty payload ramdisk; raw executable/root packaging remains VM024/025 work. `--require-ramdisk` makes its absence an explicit preflight failure. |
| `avfboot.c:986`, `/pram/reg` two u64 and `/chosen/embedded-panic-log-size` u32 | `pexpert/arm/pe_init.c:122` locates panic storage. The shim reserves this at the high physical RAM tail, so this tool does not require containment within the smaller chosen DRAM window. |
| `avfboot.c:991`, `/cpus/cpuN`: state, reg u32, cpu-id u32, frequencies u64 | `pe_identify_machine.c:72` reads running CPU frequencies; `GenericARMPE.cpp:72` requires state and reg then asks kernel topology for the CPU number; `machine_routines.c` parses CPU topology. The selected shim exposes at most eight CPUs. |
| `avfboot.c:1012`, `/arm-io/ranges` three u64 {0,io_base,io_size} | `pe_identify_machine.c:185` takes the second u64 as SoC base. Driver register addresses below are offsets from it. The literal device_type `crosvm` is also used for QEMU. |
| `avfboot.c:1017`, `/arm-io/gic`: compatible arm,gic-v3, reg four u64, virtual-timer-intid u32 | `gic_v3_irq.c:591` requires at least32 bytes and maps distributor/redistributor at SoC base plus offsets. Crucially `gic_v3_irq.c:100` fixes virtual timer PPI27 and does not read the timer property. Preflight rejects any emitted timer ID other than27. |
| `avfboot.c:1026`, `/arm-io/uart0`: compatible, reg two u64, boot-console1 | `pe_serial.c:881` finds uart0; ns16550a selects the 8250/16550 path, otherwise the existing PL011 path. Preflight admits only the two strings emitted by this shim. UART is optional to the writer but required for this console objective. |
| `avfboot.c:1043`, conditional `/pci0`: compatible, ecam, bus-range, pci-ranges, intx-map/mask, probe-only | `bsd/dev/hakios.pci.c:202` selects CAM shift16 only for pci-host-cam-generic, else ECAM shift20. Ranges are32-byte records, INTx maps16-byte records. `--require-pci` is optional because a tree alone does not establish a virtio device/backend. |

Exact source line numbers above refer to the pinned immutable files, not a
current upstream branch. The writer also adds product/identity, options, NVRAM,
optional camera, boot-epoch and machine-timeout data. This initial console
preflight parses and preserves unknown properties but does not qualify those
userspace/device functions or claim exhaustive kernel/IOKit property closure.

Run light controls in a new directory:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  timeout 30s python3 -s fixtures/public/avf-guest-device-tree/controls.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-device-tree/NEW-controls
```

Inspect a real serialized Apple-tree capture, when independently available:

```sh
python3 -s tools/build/avf_guest_device_tree.py CAPTURE.adt \
  --require-ramdisk --out NEW-report.json
```

The CLI writes a fresh output only, exits0 on contract pass and2 on rejected
input, and marks runtime provenance unverified. Capture provenance must bind the
actual running source-built Image, payload, QEMU binary/options, physical tree
address, byte count and acquisition process. The input must contain exactly
`boot_args.deviceTreeLength` bytes, not the entire64KiB reserved region.

Accepted VM005 historical evidence reports genuine shim/owned synthetic guest
assertions over the translated Apple tree. Its `qemu.dtb` is an independently
generated **input FDT**, not the emitted Apple tree. It cannot substitute for a
raw Apple-tree capture. The separately leased VM027DT-002 run now supplies that
capture. No additional QEMU or compiler is authorized by this procedure.
Any future capture needs root's explicit single-guest lease and a bounded owned
runner; no phone operation is involved. Parser controls alone leave this task's
actual-data acceptance open. Independent review, integrator acceptance and fresh
MAIN common checks remain required before original-owner completion.
