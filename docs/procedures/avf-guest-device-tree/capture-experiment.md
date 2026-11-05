# VM027DT-002: actual unchanged AVF shim Apple-tree capture

Prospective plan; no new guest is authorized by this document. Owner remains
`codex-guest-exec-20261106-di`, task VM-027. Root's explicit single-QEMU lease is
required before execution. Source-only evidence VM027DT-001 remains inconclusive.

Reuse the exact source-built QEMU, unchanged VM002 AVF Image and accepted VM005
owned synthetic spin payload. Stream and match all hashes against qualified
identities and the historical VM005 artifact index. Do not compile, edit binaries,
attach storage/network, pass through devices or operate a phone. This capture
does not execute XNU or PID1.

The immutable prospective plan JSON includes every input path/hash/size, runner
and accepted supervisor hashes, exact QEMU argv and canonical owned fresh output.
The only added QEMU option is its local Unix QMP socket. One vCPU, virt/GICv3,
TCG cortex-a76,256MiB guest RAM and512MiB total owned RSS limit remain fixed.

Require three MemAvailable samples >=4GiB one second apart. The direct QEMU runs
in a new owned session; reuse accepted qemu_host.py sample/terminate functions.
Record samples every polling round, stop on an RSS limit, post-spawn available
memory below4GiB or55-second whole-capture deadline, and bound cleanup by the
accepted finite session cleanup. SIGTERM raises KeyboardInterrupt through the
Python cleanup path, including when raised inside a procfs helper that catches
OSError. Outer timeout is60 seconds. Never signal unrelated processes. Recheck the exact root lease
throughout admission and execution; absence/revocation fails closed.

Connect to QMP, verify greeting and negotiate qmp_capabilities. Wait for the
actual `VM005 SYNTHETIC SPIN-CONTROL` console marker and exactly one shim
`avfboot: device tree ADDRESS+LENGTH boot_args ADDRESS` record. The separate
inputFDT console address0x48200000 is not used. Require the dynamic tree extent
to be wholly inside guest virtual RAM0x40000000..0x50000000 with nonzero length
<=1MiB. Require canonical new destination below this worktree's owned artifacts.

Send QMP stop, then query-status and require running=false/status=paused. Issue
only pmemsave for the validated dynamic physical virtual-RAM address/length to
apple-tree.adt. Require an exact-sized regular output, send quit, require exit0
and no live owned survivors. Preserve console/QMP/samples/failed captures and all
exact commands/exits/timing/hashes. Kernel/profile compatibility remains unproved.

Then run the existing bounded Apple-tree parser/preflight on these actual bytes,
followed by controls that remove or truncate actual required properties. Preserve
all failures. An actual parser pass and honest selected-contract negative controls
can close the previous raw-data gap; independent review, integrator acceptance and
fresh MAIN common checks still precede original-owner task completion.
