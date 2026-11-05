# VM-025: owned PID1 ABI admission

The existing VM-002 executable is structurally eligible for the selected static
arm64 loader, but its source has an invalid inline assembly contract. Admission
must remain inconclusive. No compiler, guest, phone or executable input is run by
this tool. Root assigned a separate VM-034 replacement; VM-002 source stays owned
by its original blocked task.

## Exact source findings

`fixtures/public/avf-guest-pid1/inputs.json` freezes nineteen real input hashes,
including the historical source/object/executable/build commands/evidence and
the actual VM-008 prepared selected XNU source. The source lineage is Scion
`a6f4bc38aa244359cd365c976244a88c9d6b3304` over public XNU
`c54f35ca767986246321eb901baf8f5ff7923f6a`; VM-008 review/acceptance is separate.

* The actual `bsd/kern/syscalls.master` defines exit 1, write 4, open 5,
  getpid 20 and sysctlbyname 274. The six sysctlbyname arguments are name,
  name length, old value, old length pointer, new value and new length. The owned
  program passes eleven bytes for `kern.ostype`, a writable 32-byte buffer and
  an eight-byte LP64 length, and requires the seven-byte `Darwin` plus NUL result.
* `osfmk/arm64/proc_reg.h:1941` defines syscall code register 16.
  `osfmk/arm64/sleh.c:1652` dispatches SVC through that saved register; positive
  numbers enter BSD syscall handling. `bsd/dev/arm/systemcalls.c:462` copies
  direct arguments from x0 upward. Its return path at 587 writes the error to
  x0, zeroes x1 and sets carry on failure. Success writes x0 and x1 according to
  return type, including zeroing x1 for a size/ssize return. The wrapper at 657
  clears carry before dispatch. `cset ..., cs` correctly captures an error flag;
  both x0 and x1 must be outputs/clobbered to describe the machine effects.
* `src/virtualization/pid1.c:24` declares x0 and the error flag as outputs,
  but x1 only as input. Selected XNU changes x1. The C compiler may consequently
  retain a pointer or another live value in x1 across `svc`. This is a compiler
  contract defect even if a particular full console write happens to succeed.
  Actual historical optimized-code behavior is not established by this audit.
* `bsd/kern/mach_loader.c:865` admits static non-x86 executables only under
  DEVELOPMENT or DEBUG. The actual selected BSD configuration is DEVELOPMENT.
  `load_unixthread` at 2733 requires one thread, obtains the stack and entry and
  sets `unixproc`. `osfmk/arm64/status.c:1992` obtains ARM_THREAD_STATE64 PC;
  a zero stack state reaches the default `USRSTACK64` path at 1860. Exec later
  installs its argument stack and entry; this program consumes no argc/argv.
  This source inspection does not execute the loader or establish stack mapping.
* The real historical binary has entry `0x100003ddc`, a zero initial stack,
  ARM_THREAD_STATE64 flavor 6/count 68, a hard 4GiB pagezero, read/execute
  `__TEXT`, read-only `__LINKEDIT` and no dynamic loader. Its segment mappings
  align to 16KiB and the entry lies in file-backed `__text`. Its build commands
  used existing Android NDK18 Clang plus the project source-built ld64. It was
  not built with the newly source-built guest compiler.

The source inspections bind the real prepared files individually; no upstream
header or SDK equivalent is invented. Existing source licenses remain with the
immutable preparation tree. Only owned tooling and metadata are added here.

## Read-only interface and acceptance

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  tools/build/avf_guest_pid1.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --controls --out artifacts/avf-guest-pid1/NEW-preflight
```

Exit 2 is the expected honest result for the original artifact: structural
inspection and corruption controls may pass while ABI admission is rejected.
Exit 1 denotes invalid or changed input. Exit 0 requires an exact independently
reviewed candidate entry in the maintained fixture; the initial list is empty.
`--candidate FILE` takes an explicit JSON descriptor containing `path`, `sha256`,
`source_path` and `source_sha256`, all relative to MAIN. A supplied hash binds
bytes but never grants approval. Review must bind source-built tool/recipe
provenance, corrected assembly semantics and executable identity before adding
that exact descriptor to `qualified_candidates`. The original defective binary
stays rejected even if added there accidentally.

The parser checks a deliberately narrow arm64-all/static/16KiB/default-stack
contract and rejects unsupported commands, dynamic linking, malformed extents,
W+X, overlap, incorrect thread state and invalid entry placement. Its bounds are
policy for this owned tiny program, not a complete Mach-O or XNU loader model.
Corruption controls mutate actual executable bytes in memory; they do not write
to any source or input artifact. Hashing streams in fixed-size chunks and inputs
parsed into memory are limited to 1MiB. Actual current-image `/proc/self/status`
VmRSS and VmHWM are reported; inherited `ru_maxrss` is not used.

Fresh reports preserve every run, exact argv, exits, times and implementation,
fixture and input hashes. No common `make check` or MAIN publication occurs here.
The task remains in progress pending independent review and integrator acceptance.

## Execution remains unmeasured

A new candidate still needs the accepted coherent VM-008 namespace, a complete
qualified guest kernel, the identical raw mockfs `/sbin/launchd` package, actual
exec/code-signature policy and stack/console/sysctl behavior. Root must grant a
single finite QEMU lease. The integrator must bind genuine Darwin boot output to
the actual conditional owned PID1 identity marker, then distinguish the intended
PID1-exit panic/PSCI natural stop from host deadline termination. A marker string,
host preflight, source-built object or source profile does not establish boot,
Apple launchd, iOS, an S24 result or a measured guest stop.

VM-024 owns raw mockfs packaging. VM-009's common process helper is a kernel
object engine; PID1 is not an invented 1081st kernel object. This read-only
preflight starts no subprocess and does not duplicate that engine.
