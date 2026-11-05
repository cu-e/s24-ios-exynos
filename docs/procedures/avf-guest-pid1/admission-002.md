# VMPID1ABI-002: exact reviewed compiled candidate admission

Original VM-025 owner `codex-guest-exec-20261106-dg` resumes in the same worktree.
Root explicitly approved this host-preflight phase after accepting REV-026's
compiled review; no compiler, linker, binary inspection tool, guest, MAIN
publication/common check or task completion is authorized by that approval.

The immutable original VM-034 build-1 candidate descriptor has SHA256
`0bdfc24445a1a213790546a79a62975691c9ff334cd6bedb6f954859cf41f63e`.
Its image SHA256 is
`fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3`,
source SHA256 is
`68de57b2e27480f39cabdcf1372176ddbf8e275b9c5309c2ac529c6e0be01190`
and actual LLVM IR SHA256 is
`894f382ca5bcc7669acc59125446902df7920c8c483b3c018f42d23995388112`.

REV-026 commits `b1ca07a871f68a95e1a21210a23fcb33d78ce826` and
`ad18859541eb0f7753fd0b6be2c68ae6381f98d6` preserve independent source/IR/
ARM64/static Mach-O review. Its exact evidence SHA256 is
`355fec37eddabb98edfdde1f4c8301366f7d9974ffff0ba23a3a3fe07e79d24c`;
compiled-admission SHA256 is
`72243a1fabe289cd5c313804be0ad187091fb9b4e668c3c992dc23cd4186cbf0`.
The original raw build evidence SHA256 is
`01488b5be195fe61a0e0880c60b51190a7cb38c33dd0ba7af3d68ac22bc266b2`.
All paths and hashes are appended to the owned fixture; prior records and
legacy rejection are retained. The selected kernel namespace and real execution
are separate from this compiled ABI admission.

Register this existing procedure through MAIN before running the phase.
Run the real CLI with the original candidate.json, `--controls` and a new output
directory. Require exit 0, `compiled-only` admission and seventeen actual-image
mutation rejections. Exercise wrong executable/source hashes, actual changed
source and IR copies, malformed image, a structurally valid unreviewed image,
descriptor byte changes, removed review endorsement, and the legacy descriptor
even if mistakenly inserted into the candidate list. Mutate owned copies only;
preserve every command, expected failure, diagnostic and output hash.

The test driver starts only fresh stdlib Python preflights with finite timeouts.
Hashing streams and parsed inputs remain bounded; collect actual current-image
`/proc` VmHWM under 256MiB. No compiler or guest lease is requested or consumed.
Export the measured host-admission evidence and exact original image/provenance
to the VM-024 packager, root and kernel integrator. Retain all runtime/PID1/
stack/signing/console/kernel/boot/PSCI boundaries and the original inconclusive
capsule. Original owner retains the task pending independent acceptance.
