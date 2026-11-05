# VM027DT-001: bounded source-contract parser controls

Hypothesis: an owned parser can deterministically decode the selected Scion
Apple device-tree wire format and reject malformed structure, missing required
properties and mismatched consumers without executing a compiler or guest.

Before testing, bind the exact Scion generator and VM007 qualified composed
kernel consumers in `fixtures/public/avf-guest-device-tree/source-pins.json`.
The control example is authored test data derived from source interfaces and
documented QEMU addresses. It is never a raw shim-generated runtime tree.

Run the fixture control script with a fresh output directory, stdlib-only Python,
256 MiB address-space cap and a finite 30-second external deadline. Preserve every
output attempt. Record current exec-image VmHWM from `/proc/self/status`, hashes,
commands, exits and elapsed time. Require all structure, missing-property,
semantic mismatch, optional-input and exact source-hash controls to pass.

Independently invoke the public CLI on the authored example and on malformed
data; require exit 0 and exit 2 respectively. Read accepted VM005/031 artifacts
without executing them. An absent serialized Apple-tree capture leaves overall
task acceptance inconclusive even when source preparation controls pass.

No compiler, QEMU, physical device, shared source mutation, SDK, private ABI,
native output reuse or main/common-check execution is part of this experiment.
