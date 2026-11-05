# VM-024 actual candidate packaging procedure

Root resumed the original VM-024 owner and explicitly authorized packaging the
exact VM-034 image independently reviewed by REV-026. VM-025 owns its separate
candidate preflight. This procedure runs no compiler, linker, QEMU or device.

Use the unchanged packager SHA256 in `vm034-candidate.json`. Rehash the exact
candidate, descriptor, original mockfs provenance, raw build evidence, owned
source, independent review admission/report/evidence and retained linker warning.
Recheck all original mockfs source/license pins. Require three stable MemAvailable
samples above 4 GiB, serial children with 256 MiB address-space limits and finite
deadlines. Record actual `/proc` VmHWM and all commands/exits/times/output hashes.

Run `fixtures/public/avf-guest-mockfs/package_candidate.py --main MAIN --out NEW`
at its committed revision. It creates two fresh owned packages from the exact
original candidate/provenance, verifies them with the real CLI, independently
compares the entire executable prefix and zero padding, and checks deterministic
image/package metadata. Preserve both pristine packages. Use separate copied
packages for changed-prefix, truncation, extension and altered-metadata rejection
controls, preserving all failures. Rehash immutable inputs before/after.

Save an output manifest, full evidence and handoff within VM-024's paths. Keep
`executable_qualified: false` and `guest_executed: false` in package metadata;
external compiled ABI/preflight reviews do not establish kernel exec, PID1
identity, initial stack, signature policy, console, syscalls, panic or PSCI stop.
Retain the original source-build warning about an absent framework search path;
no SDK or proprietary filesystem tool/image is acquired or consumed by packaging.
Only integrators publish MAIN/run common checks; the owner does not close VM-024
before independent acceptance.
