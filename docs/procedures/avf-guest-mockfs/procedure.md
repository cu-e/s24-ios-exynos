# VM-024 structural packaging procedure

Read the pinned VM-007/VM-008 mockfs, AVF shim, IOKit memory-device and Mach-O
source files. Bind their SHA256 and canonical Git blob SHA1 in `sources.json`.
No source regeneration, compiler, linker, QEMU, device or shared Git hydration.

Run `fixtures/public/avf-guest-mockfs/check.py --out NEW_DIRECTORY` under
constrained stdlib Python. The checker creates its own synthetic, nonbootable
Mach-O structural input, invokes the real CLI with finite deadlines, and keeps
stdout, stderr, exit codes, elapsed times and actual `/proc` VmHWM samples.
It checks deterministic bytes, exact input prefix, zero padding, read-only
verification and rejection of malformed/truncated/oversized/dynamic inputs,
invalid entry/section ranges, changed bytes, wrong provenance/hash and output
reuse. All failures and generated controls remain in that new directory.

Synthetic input has no instruction payload and is never a guest executable.
An actual source-built PID1, code signing, selected kernel/loader compatibility,
memory placement, syscall behavior and boot/stop must be qualified separately.
Original owner submits exact scoped commits and evidence for independent review;
integrators alone publish MAIN and run common checks under the integration lock.
