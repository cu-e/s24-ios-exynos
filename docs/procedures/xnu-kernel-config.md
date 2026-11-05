# Selected E1S component configuration

KRN-007; owner codex-kernel-config-20261105-r; main at 2c4e673.
Previous goal turn and this turn made concrete host/source-object progress.
All build and audit sessions are terminal. Full kernel/native acceptance remains
unqualified; the complete research/implementation goal stays active.

## Measured result

The unmodified public C generator builds as an actual native host program from
nine source/generated objects. Original doconf runs through the recorded tcsh
and creates all three RELEASE/ARM64/E1S/iPhoneOS component configurations. Its
output explicitly selects config/MASTER.arm64.e1s. Actual generated option and
header counts are:

| Component | CONFIG_DEFINES options | Headers, including meta_features.h |
|---|---:|---:|
| osfmk | 117 | 46 |
| libkern | 120 | 11 |
| pexpert | 124 | 2 |

These counts alone are not qualification. Actual compiler controls check E1S
CONFIG_VNODES=1024, embedded/PPL/NOS_ARM_PMAP/integrity selection and the
component's RELEASE feature values. osfmk has MACH_ASSERT=0, MACH_KDP=1 and
CONFIG_DTRACE=0; libkern has LIBKERNCPP=1, IOTRACKING=0 and CONFIG_DTRACE=0;
pexpert has CONFIG_DTRACE=0. Each deliberate CONFIG_VNODES=1025 mutation is
rejected by the independent source expectations.

Source-declared exports copy18 real internal headers unchanged:7 security,
5 sanitizer-memory and6 sanitizer-coverage headers. The small owned export
resolver's actual empty/reference-variable semantics are checked against GNU
Make expansion of extracted declarative assignments. Unsupported expressions
are rejected; upstream Makefile targets/installers are not executed. The export
copy matches makedefs/MakeInc.rule's byte-preserving internal install rule.

Fresh KCONFIG-005 compiles all three genuine source units with the actual
generated component headers/defines and XNU_NO_TYPE_BUILTINS=0:

| Source | Actual result | Independent code audit |
|---|---|---|
| osfmk/kern/kalloc.c | arm64 Mach-O, exit0, no diagnostics | kalloc_ext, kfree_ext, kalloc_type_impl_external;5863 disassembly instruction lines |
| libkern/c++/OSData.cpp | arm64 Mach-O, exit0,17 warnings | withCapacity/initWithCapacity;2404 instruction lines |
| pexpert/arm/pe_identify_machine.c | arm64 Mach-O, exit0, no diagnostics | pe_identify_machine;639 instruction lines |

KCONFIG-006 uses the unchanged recorded objects, checks the six expected
external symbols have actual code type T, and decodes ARM64 instructions with
independent LLVM tools. These are emitted instructions; none was executed.
Empty conditional translation units cannot explain this result.

The compiler remains HARDEN-002's source-built plain arm64 experimental
compiler, with its Apple/private ABI/PAC/type-layout limits. The original kernel
source bytes and other owners' paths stay unchanged. No source patch or invented
SDK/feature declaration was needed for this component.

## Actual inputs and mechanism

Use prepared XNU8796.121.2 c54f35ca767986246321eb901baf8f5ff7923f6a with
the recorded E1S donor c8860decc62c6d6180e609036d027a2997972420, donor patches
and corrected STM source. Verify the complete prepared-source witness first.
Use HARDEN-002's real source compiler and HARDEN-005 regression evidence, plus
the witnessed IIG/MIG/header roots and HOSTGEN-002 tcsh/unifdef binaries.

The actual SETUP/config/Makefile lists seven C files plus Bison's parser and
Flex's lexer, with YY_NO_INPUT. Build these in new artifacts paths using an
explicit host compiler. The reviewed host recipe omits macOS sysroot, minimum
OS version and codesigning; this is a host build, with original generator C,
grammar and lexer bytes preserved. Record actual failures before any patch.

Run original SETUP/config/doconf through the recorded tcsh -f. Pass actual
RELEASE/arm64/e1s/iPhoneOS arguments and per-component conf directories.
Set SRCROOT/SOURCE/OBJROOT only for the subprocess and put generated files in
new output directories. Preserve MASTER selection, original unifdef/sed/awk
pipeline and generated CONFIG_DEFINES/meta_features.h; do not author replacement
feature headers. Never run the generated Makefile as an uncontrolled build.

The donor wrapper defaults to DEVELOPMENT. This task explicitly measures the
supported RELEASE profile; other variants need separate configuration/build
qualification. Actual [Apple generator sources](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a/SETUP/config)
and [selected E1S donor](https://github.com/RNDMBG/iOS-On-S24/tree/c8860decc62c6d6180e609036d027a2997972420/xnu/e1s)
provide source context. Locally patched source provenance is the complete
recorded prepared-tree witness, with all component/per-file license notices
preserved in the isolated source copy.

Compile actual kalloc.c, OSData.cpp and pe_identify_machine.c using generated
component inputs and the component's private defines from conf/Makefile.template.
Type checks remain enabled with XNU_NO_TYPE_BUILTINS=0. A full profile/kernel link
or native result requires more than these translation units.

Register KCONFIG experiments before execution; save commands, exits, hashes,
exact output paths and failures. New run names only. No global package/header/
compiler installation, SDK/firmware acquisition, APK/root/device/power operation
or change to other task owners is part of this work.

## Preserved experiments

| Experiment | Actual outcome |
|---|---|
| KCONFIG-001 | Fail: genuine generator and all three original doconf configurations pass; OSData/platform unit compile, kalloc lacks declared security exports |
| KCONFIG-002 | Fail: compiler positive/mutation controls pass and7 genuine security exports advance kalloc to missing san/kasan.h |
| KCONFIG-003 | Fail: owned resolver misreads an empty Make assignment before unit execution; retained as a runner defect |
| KCONFIG-004 | Pass: corrected empty-variable handling matches real GNU Make,18 declared exports and all three actual objects |
| KCONFIG-005 | Pass: fresh complete generator/doconf/control/export/unit execution, with no reused configuration |
| KCONFIG-006 | Pass: independent code-symbol/ARM64-disassembly audit of unchanged actual objects |

Original failures/capsules are immutable. New run names preserve the old prefix.
Reusing a configuration requires a recorded direct generator/configuration run
whose five required checks all passed; no enclosing failure is rewritten.
Repository and complete input-integrity verification is recorded separately
in KCONFIG-007.

## Reproduction and handoff

Register a new owned experiment first, then run the complete fresh path:

    python3 tools/build/xnu_kernel_config.py --run fresh-config --internal-exports

For diagnosis with an immutable verified configuration, use an explicit parent:

    python3 tools/build/xnu_kernel_config.py --run fresh-units --internal-exports \
      --reuse-config-run artifacts/xnu-kernel-config/qualified-release-session1 \
      --config-evidence KCONFIG-005

The corresponding independent object inspection requires a passing recorded
compile capsule:

    python3 tools/build/xnu_kernel_config.py --run fresh-object-audit \
      --audit-run artifacts/xnu-kernel-config/qualified-release-session1 \
      --object-evidence KCONFIG-005

Use a new run and experiment ID after every source/recipe change; do not change
consumed reports, source, headers, archives or objects. The runner sets a
90-second per-command limit and terminates its host process group on timeout;
core dumps are disabled. No observed execution timed out.

The exact reusable configuration/export/object manifest is
fixtures/public/xnu-kernel-config/qualified-component.json; bounded task
acceptance is assessed in acceptance.json. Its pass covers the three components
and source units above. KRN-008 owns the next full selected object-closure work.

Next actions: derive the full selected C/C++/assembly/generated object inventory
from actual component Makefiles, generate remaining component inputs/exports,
trace complete architecture/per-file warning/compile/assembler recipes and
compile every required unit with explicit status. Do not substitute the three
objects here for that object set, or silently omit failed/generated sources.

OSData's17 C99-designator/reorder warnings remain in actual diagnostics.
MakeInc.def enables WERROR and has an explicit no-error exception for reorder
initializers. The complete selected warning/options recipe is still KRN-008;
this bounded compilation does not qualify that full recipe. Complete selected
kernel linking, DriverKit/private ABI/SDK closure, recovery and native iOS
GPU/display/Wi-Fi/SIM/eSIM/userland operation remain separate gates.

No ADB command, phone setting, APK, root, reboot, flash, Apple binary/SDK/archive
acquisition, global package/header/compiler modification or change to device
authorization occurred. The original KRN-001/003/004 owners, source/build paths
and radio/userland/recovery input gates remain unchanged. No external input is
needed to start the next independent host object-closure work.
