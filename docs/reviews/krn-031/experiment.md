# REV-017 independent review plan

Owner: `codex-team-review-kernel-xts-20261105-ca`. Task remains in progress
until coordinator acceptance. Review files only; shared registry uses main.

Review frozen implementation `1bd64b4265cccf866bd1a3e1e1bcb3dde66d2877`
and named followups against genuine selected XNU and donor Git objects. Check
publication happens after both real factories pass metadata validation, immutable
descriptor lifetime/typing, once-state acquire/release behavior, actual provider
slot retention and actual caller rejection propagation.

Before executing the independent audit, register `REVKXTS-001`. Run the owned
Python auditor with Git lazy fetch and optional locks disabled. It reads genuine
source and existing native/guest capsules without launching a compiler or guest.
Independently decode Mach-O symbols, relocations, instructions, descriptor bytes
and linked callback addresses rather than trusting producer pass markers.
Rehash named source, command, object, recipe, import, layout, runtime and export
bindings. Preserve missing, failed or inconclusive capsules; development positives
alone cannot satisfy acceptance.

Final review requires a qualified final native/host/guest replay and meaningful
original-caller, corrupted-vector, publication, admission, mapping and cleanup
controls. Existing selected 34 relocated callbacks, deferred SHA256 and 19
unsupported slots must survive with exactly two XTS additions. The actual full
provider is compile/relocation evidence; guest execution uses an owned two-slot
table and genuine selected caller/registration. No full provider, XNU boot, native
device, private Apple ABI, full crypto, FIPS, page-protection or 37-export closure
claim follows.

No phone, ADB, root, physical MMIO, flash, reboot, APK or provisioning operations.
No full kernel build/link. This review needs no new compiler or QEMU process;
any later compiler requires one job <=256MiB and MemAvailable >=4GiB, and any
QEMU requires an explicit coordinator exclusive lease (256MiB RAM/512MiB RSS).
