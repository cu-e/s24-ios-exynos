# Genuine kernel declaration closure

KRN-016, owner `codex-kernel-declarations-20261105-aa`, parent `487b7a9`.
The bounded declaration component passes. Work is host-only: no phone command,
SDK acquisition, global installation or original source/compiler/header change.
Android and native scopes remain unchanged.

The full current profile produces **959 component objects plus version.o:
960 known direct ARM64 objects**. All 962 current source recipes were retried;
every prior 958 successful direct object still compiles. Both genuine formerly
failing mc_provider.c and user_exception_trace.c compile. Of 978 component entries,
19 remain unresolved: two unsupported C++ metadata cases and 17 missing IIG
sources. Three additional direct objects are unattempted, so 22 of 982 known
direct prerequisites remain unresolved. Archive/link closure is separate.

## Exact source origins and declaration rules

The selected source is Apple XNU
`c54f35ca767986246321eb901baf8f5ff7923f6a`, plus s24-port donor
`c8860decc62c6d6180e609036d027a2997972420` and recorded preparation fixes.
Both affected source files and minicrypto.h are exact pinned
[donor files](https://github.com/RNDMBG/iOS-On-S24/tree/c8860decc62c6d6180e609036d027a2997972420/xnu/hackios/files/osfmk).
The runner compares actual prepared files against Git blobs and binds canonical
headers/API provider/source hashes. Original prepared 5111-file kernel,
10889-file compiler source and 198 original build inputs remain unchanged.

Selected [kern/misc_protos.h](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/kern/misc_protos.h)
and BSD libkern headers already declare int printf(const char *,...). With the
actual CONFIG_NO_PRINTF_STRINGS/KERNEL_PRIVATE configuration, the function-like
printf macro calls _consume_printf_args and omits the format string. The donor's
subsequent duplicate declaration expands into invalid syntax. The first source
port removes only that duplicate; it preserves the existing canonical prototype,
macro policy and all runtime algorithm/callback source.

The selected [BSD proc API](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/bsd/sys/proc.h)
and [real provider](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/bsd/kern/kern_proc.c)
use int proc_pid(proc_t), with proc_t an opaque struct proc pointer. Directly
including the whole BSD header in the Mach source is invalid for this profile:
KDECL-003 measures conflicting daddr_t,dev_t and clock_t typedefs. No typedef,
header guard,warning or configuration suppression is used to hide the conflicts.

The selected [Mach task client](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/kern/task.c)
already contains the exact opaque bridge declaration:

```c
extern int proc_pid(struct proc *);
```

The second source port copies that exact declaration next to the existing
proc_name_address declaration. It imports no conflicting BSD system typedefs.
Separate complete Mach- and BSD-profile controls verify the canonical return
and opaque pointer types, sizes and actual required provider symbol. This is a
matched existing interface, without an invented substitute prototype.

The genuine neighboring minicrypto.h is copied unchanged beside the owned
mc_provider.c. That preserves original quoted-header search semantics after
moving the translation unit. All other source/header paths remain unchanged.
Patch attribution and APSL2/per-file notices are preserved in
patches/kernel-declarations. License text uses repository LF endings; original
measured license/source bytes stay unchanged. Generated copies/objects stay in
ignored local artifacts.

## Whole recipes and actual contracts

The exact source compiler is VCOMP-002's
artifacts/xnu-compiler-vectors/source-build-session1/clang, SHA256
`3b11f867131e9a22a3671101ffb09dcecaf2b6831e5fd2c384b95075f29008a3`.
Current RHDR-004 recipes retain source/cwd/per-file flags, actual
XNU_NO_TYPE_BUILTINS=0 allocator checks, matched resource headers, coherent
MIG/syscalls, target offsets/local version, startup source port and firehose
inputs. Only the two declared source paths and object/dependency outputs
change. No source-only object cache is used in the full retry.

One real recipe uses relative ioconf.c against its recorded BSD configuration
cwd. Preflight resolves all 962 input bindings and preserves this relative
argument unchanged. KDECL-006 retains the failed earlier runner assumption
that all source arguments were absolute, including 672 successful compiler
commands and their artifacts. KDECL-008 repeats the complete profile in fresh
paths with exact argument/cwd/source associations, not a partial cache merge.

The genuine declaration contracts cover:

- Canonical int printf(const char *,...) and int proc_pid(struct proc *) in the
  Mach profile, plus independent canonical proc_t equivalence in the BSD profile.
- Actual target values 8,4,8,8 for pointer/int/function-pointer storage, and 8,4,8
  on the independent BSD side.
- Actual proc_pid provider references and printf versus consume-args call symbols.
- Format marker absence under the current configured macro and presence under
  an explicitly controlled CONFIG_NO_PRINTF_STRINGS=0 variation.
- Actual optimized LLVM IR retaining the counter increment/store and expected
  variadic callee under both format policies.
- Conflicting proc prototype,restored redundant printf declaration,removed opaque
  proc declaration and duplicate patch negatives,all with precise real failures.

Alternate-format flags are only a control variation. The full kernel recipe
configuration is unchanged. The failed direct BSD-header attempt is retained;
no fake shared type or header stand-in replaces it.

## Crypto limits remain real

The unchanged actual crypto_functions initializer is 448 bytes on this target.
An independent source-containing layout probe emits genuine offsetof values,
while the pure full provider object is inspected separately. Both have the
expected real relocations for ccdigest_init_fn and ccaes_ecb_encrypt.

Eight inspected unsupported slots remain zero without relocations: XTS encrypt/
decrypt,GCM encrypt/decrypt,ChaCha20-Poly1305 functions,DES ECB encrypt and the
two RSA functions. Actual raw byte and active relocation mutations are rejected.
The probe's extra measurement record is separate from the pure provider object.
These are compiled initializer observations,not algorithm tests or runtime
provider registration. Other initialization,including the existing SHA256
assignment,is preserved unchanged. No full crypto,FIPS,encrypted-volume,signature
verification,Apple private ABI or native operation is qualified by this task.

## Measured runs and reproduction

| Experiment | Actual outcome |
|---|---|
| KDECL-001 | Fail: both original full recipes reproduce declaration failures |
| KDECL-002 | Fail: first insufficient-context patch fails before compilation |
| KDECL-003 | Fail: corrected patches apply and minicrypto compiles; direct BSD header causes genuine Mach typedef conflicts |
| KDECL-004 | Pass: exact opaque API bridge and minimal declaration ports,both full consumers |
| KDECL-005 | Pass: 25 canonical/profile/macro/table/mutation controls |
| KDECL-006 | Fail: earlier full runner stops at relative ioconf.c after 672 actual successful compiler calls |
| KDECL-007 | Pass: independent full object/source-port/dependency audit |
| KDECL-008 | Pass for partial closure: all 962 recipes,960 actual ARM64 objects,zero 958-prior regressions |
| KDECL-009 | Final bounded acceptance,patch/provenance/dependency/replay and repository checks |

All failed prefixes and diagnostic/source/patch snapshots remain immutable.
The latest patch form uses full context; GNU-style empty context lines retain
valid Git application without confusing patch-format blank lines with trailing
source whitespace. Qualified source bytes must match exact permitted deltas.

Register fresh experiments before running:

```sh
python3 tools/build/xnu_kernel_declarations.py --run NEW_PORTS --mode port
python3 tools/build/xnu_kernel_declarations.py --run NEW_CONTROLS \
  --mode controls --port-evidence KDECL-004
python3 tools/build/xnu_kernel_declarations.py --run NEW_PROFILE \
  --mode kernel --port-evidence KDECL-004 --jobs 2
python3 tools/build/xnu_kernel_declarations.py --run NEW_AUDIT \
  --mode audit --port-evidence KDECL-004 --profile-evidence KDECL-008
```

Run names must be new. Reports preserve all exact argv,cwd,exits,diagnostics,
source/patch/header and output hashes. Capsules explicitly label representative
command samples. Actual process timeouts terminate their process groups; the
registry's experiment timeout field alone is not a device watchdog.

## Handoff and remaining scope

The [qualified component](../../fixtures/public/xnu-kernel-declarations/qualified-component.json)
binds exact source deltas,original/ported hashes,canonical Mach/BSD API inputs,
quoted header copy,compiler,retained resource/firehose components,crypto table
observations and full regression/audit evidence.
[Compiled objects](../../fixtures/public/xnu-kernel-declarations/compiled-objects.json)
include version.o; [unresolved objects](../../fixtures/public/xnu-kernel-declarations/unresolved-objects.json)
include all 19 component gaps and three additional direct objects.

Fresh prefixes under artifacts/xnu-kernel-declarations:

- source-ports-session3: qualified source copies,patch snapshots and unchanged quoted header.
- controls-session1:25 actual contracts/negatives and separate crypto table probe/mutations.
- full-profile-session2: all 962 complete current source recipe attempts.
- object-audit-session1: independent 960 ARM64 headers,29449 defined code symbols,
  3127 actual dependency hashes and complete per-object graphs.

The actual minicrypto graph consumes the owned byte-identical header. The Mach
trace graph retains its compatible opaque API boundary. Complete exact argv
checks allow only the declared source/output substitutions; original source,
compiler,config,resource and header prefixes remain unchanged.

KRN-017 is the narrow follow-up for actual MiniIOSurface member-function-pointer
and IONVRAM reference-field metadata. It requires pinned target AST/CodeGen/C++
ABI evidence,all actual helper consumers rebuilt in a new prefix,independent
layout/raw/PCH/mutation controls and full prior 960 regressions. Existing original
compiler/fixture/report bytes and unsupported security/target limits are retained.
KRN-008 retains full archive/link closure,and KRN-004 retains IIG/private ABI;
no owner was reclaimed. Native boot/recovery,iOS userland,GPU,Wi-Fi,SIM/eSIM and
complete crypto support remain unqualified,and phone scopes are unchanged.

A bounded Reddit MCP corecrypto search in r/hackios timed out at both limits 10
and 5; this is inconclusive search coverage. Primary pinned source and actual
local compiler/object measurements support this component; no absence of an
implementation is inferred from the archive timeouts.
