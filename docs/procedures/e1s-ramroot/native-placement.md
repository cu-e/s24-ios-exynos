# Native E1S placement: reuse raw bytes, use the existing native packer

The accepted RAM-root bytes are reusable; the guest XNUP command is not a native
loader input. The actual STR003 loader source with RAM patch23b31 accepts
`SWEETXNU` version1 from an appended payload or FDT initrd. It rejects an XNUP
container. The guest BCM2837 image/profile and its AVF DT cannot become an E1S
kernel/ADT by replacing the RAM-root member.

The existing c886 native `tools/e1s/xnu/mkpayload.py` already accepts positional
`KERNEL ADT OUT --ramdisk IMAGE --cmdline TEXT`. Its build() appends IMAGE as a
16 KiB-rounded segment after the kernel, extends kernel_end and writes the ADT
`/chosen/memory-map/RAMDisk` base/size. For the accepted32768-byte image, padding
is already correct. `rd=md0` must be supplied in the native cmdline; the native
loader copies that cmdline and does not add this root argument automatically.
Do not add guest-only avf_exit semantics to a native stop claim.

Actual patched loader.c copies all payload segments into its selected RAM
window, places ADT at kernel_end and boot_args after the ADT, and sets
`topOfKernelData` beyond boot_args. Its `adt_rebase_ramdisk` relocates the RAMDisk
base by `win_base - payload.phys_base`, retaining its size. Correct native packer
output therefore keeps the root below ADT/boot_args and inside reserved kernel
data. This source contract uses the native ADT's dram-base/size and the separate
accepted loader window checks; no physical window, S-Boot input or actual native
RAMDisk placement has been measured.

Concrete incompatible inputs are: the guest XNUP container; a raw root passed
alone as the native initrd; the guest BCM2837 kernel/AVF ADT/profile; or an ADT
RAMDisk base/size unrelated to the actual appended root segment. The existing
ADT rebase helper validates property representation, not the claimed RAMDisk
range against a segment/window, so arbitrary ADTs are not qualified by23b31.
A future admitted native packet must bind the actual E1S kernel, source-derived
ADT, native packer and exact segment/property/boot_args extents. Reuse the
accepted b267 raw root as `--ramdisk`; no new format or implementation is needed.

This followup reads the frozen actual STR003 prepared loader/ADT/packer source.
It changes none of the accepted STR006 descriptor/evidence bytes, runs no
packer/compiler/guest and grants no native runtime or shutdown qualification.
