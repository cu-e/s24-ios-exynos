# Host boot package validation

`python3 tools/verify/boot.py IMAGE --tar TAR` independently checks unsigned kernel-only Android boot v4/1584 packaging, 64 MiB bounds, padded kernel, footer and AArch64 Image size/magic. It compares the one regular tar member without extracting files. The output explicitly leaves XNU payload and hardware acceptance false.

`spans()` rejects overflow, overlap and reserved-memory collisions for supplied ranges. Synthetic fixtures test those failure classes; they do not establish the phone's live physical map. Exact live reservations and firmware matching remain a native-entry prerequisite.

Run selected upstream ADT/FDT/ramdisk tests from an artifacts/ copy with the pinned source. Save actual exit codes. Upstream source-token checks, parser tests and QEMU previews remain host evidence, never phone execution. A final native image additionally needs payload/ADT validation against the actual selected kernel and recovered live map; a freestanding loader package cannot pass that requirement.
