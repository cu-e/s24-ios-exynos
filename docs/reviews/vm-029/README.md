# REV-033 independent VM-029 review

Bounded verdict: **accept the preboot source/declarative contract**, with no
remaining P0/P1/P2 finding in this scope. Subject is exactly
5974ab73d5beebb43c170231f4c9533214bf3941, including implementation
b4ae11ed2db7d248e5c8d594d3d5b6a8d3a163d1. Producer files stayed read-only.
This verdict establishes no delivered timer interrupt or running XNU kernel.

The independent audit checked six committed producer files, all19 declared
source/tool/configuration inputs,32 preserved producer artifacts and four real
GIC/machine/ARM-init/rtclock recipe/source/configuration bindings. No recipe was
compiled. The inspector is lexical source inspection, not a C preprocessor or a
complete QEMU argv/permission validator. The frozen README makes those limits
explicit, and its runtime/phone/compiler claims remain false.

Selected source agrees on generic GICv3, virtual timer PPI27, one Cortex-A76 CPU
under TCG, and converted Apple DT. Distributor0x08000000+0x10000 and
redistributor0x080a0000+0xf60000 round-trip through shim io_base0x100 offsets and
guest SoC-base addition. A0x20000 redistributor frame fits the declared window;
MPIDR matching/wake completion still need runtime observation. QEMU source uses
256 external plus32 internal IDs, making the peripheral intersection32..287
against the guest's32..1019 range and48 simultaneous SPI attachments.

Manual and executable source traces independently bound the actual functions:

| Primary source in the frozen inputs | Checked boundary |
| --- | --- |
| gic_v3_irq.c100..103,375..410 | PPI27, SPI ranges, IAR1 acknowledge, timer dispatch to rtclock_intr(TRUE), then EOIR1 |
| gic_v3_irq.c580..678 | Converted DT mapping, ICC system-register enable, matching redistributor, Group1 enable and handler installation |
| arm_init.c745..746,886..888; pe_identify_machine.c444..460; pe_fiq.c175..180 | Both boot and secondary paths call PE initialization/generic GIC before enabling virtual timer context |
| machine_routines.c2387..2410; rtclock.c148..161 | Virtual timer enable; source deadline/counter and clock initialization/resync paths |
| avfboot.c355..376,874..877,999,1019..1022 | GICv3 FDT and timer triple conversion, actual frequency source and physical offsets |
| QEMU virt.c148,176,184,835..838,907..924 | Actual MMIO/controller capacity and GTIMER_VIRT wiring |
| QEMU virt.c2277..2282,3473..3476; shim chosen/psci-method; selected psci_smp.c169..174,221..224 | Default secure=false/virtualization=false HVC source intersection and guest method consumption; no PSCI execution result |

There were129 independent checks and38 predicate cases. New real inspector CLI
runs accepted required SPI287(exit0), rejected288(exit2), and rejected SPI160
against a test-local copy of genuine QEMU virt.c re-pinned with NUM_IRQS128
(exit2, derived maximum159). That last control distinguishes source-derived
capacity from a hardcoded287 expectation. Copies retain source notices and remain
local artifacts; original inputs never changed. Boolean/scalar/unhashable/duplicate
SPI declarations,49 attachment slots, closed-shape/type and configuration
mismatches were also rejected. The existing source-identity and timer-semantic
producer failures were rehashed, not rewritten.

The review started no native compiler, linker, QEMU, common suite or phone action.
Three sequential Python inspector children were bounded to30seconds; the inspector
itself starts no child. Current reviewer-image VmHWM was77,082,624 bytes. Exact
argv/exits, source identities and output hashes are in the review receipt.

Next gate: independent integration and fresh shared MAIN checks, followed only
when separately authorized by a complete accepted kernel/image and an explicit
finite guest lease. Record actual launch/image/tool/DT identities, counter rate,
IRQ arrival, repeated deadline rearm and EOI/stop behavior. Generic-source
redistributor/distributor waits remain unbounded; timer-enable text alone proves
none of those runtime properties. No native-device, MMU, SMP or Apple compatibility
claim follows from this review.
