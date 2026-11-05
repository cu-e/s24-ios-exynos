# RES-009 open-input handoff

2026-11-05; owner `codex-open-inputs-20261105-n`, main checkout. This goal turn produced new source evidence, three retained corrections, real generated headers and a genuine E1S pthread component archive. It did not acquire an Apple SDK/binary/firmware, run Nix/upstream installers, change global tools or issue a phone command. The preceding goal turn also made progress (538bedd: actual BYH3 RIL access boundary), rather than being a wait or no-progress turn.

## Primary sources and provenance

- PureDarwin/PureDarwin6982ddbfca1047c86680ec7c66da152789746efd, current upstream-xnu-12377 branch: named source SDK recipe/flake lock/full target header only. The header carries Apple's APSL2.0 notice; PureDarwin's BSD2/component notices remain separate.
- PureDarwin/iig-tools28010c688caab7eb5400b9c98faa5b1e538e0108, exactly from that flake lock: actual three-source C++17 generator. BSD-3-Clause, copyright2026 Vali0004.
- Apple CarbonHeaders214a9ae7ab3c0c78ddb50328ca226e6313c4c782: older APSL2.0 target-header template and actual three-token Makefile configuration recipe. No installer/removal/symlink target was executed.
- Existing selected Apple XNUc54f35ca767986246321eb901baf8f5ff7923f6a, E1Sc8860decc62c6d6180e609036d027a2997972420 and donor d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c remain unchanged. The full prepared E1S file set, file hashes and report match the earlier immutable witness. Pthread remains a6c70ca0e544347a0377babf748f831577ec24f9; only private artifacts copies are patched.

No submodules, SDK archives, generated Apple binary inputs, image samples or unrelated PureDarwin source expansion were fetched. AvailabilityVersions115.4's actual five-file tree has no TargetConditionals.h. A newer Apple AvailabilityVersions HEAD149b1777f3e8c2133042d8e188f72e3adf6a7110 was observed, but two tree metadata calls ended RemoteDisconnected; no claim about that revision's header inventory follows. The publicly found CF header explicitly targets Linux and was excluded as an iOS input.

Current PureDarwin documentation describes a source-assembled SDK; an older article still describes needing macOS11.3 SDK. The pinned current recipe resolves this temporal distinction. It does not establish selected8796/iOS16.5 compatibility, nor does its open userland supply Apple's iOS GUI.

## Actual experiments

All use python3 tools/research/open-kernel-inputs/check.py with explicit installed NDK28.2 Clang19.0.1, /usr/bin/c++ and artifacts/xnu-prepare/e1s-dependency-source-session1. Exact argv/exits, compiler/source/tool/file hashes and raw commands are bound by state/evidence/OPENINPUT-001.json through004; every run snapshots builder.py.

| Experiment / run | Flags | Exit / outcome | Actual result |
|---|---|---|---|
| OPENINPUT-001 / baseline-session1 | none | 1 / fail | Full PureDarwin header selects macOS for arm64 iOS; raw Carbon template fails ARM64. Actual IIG builds and emits17/17 interface text pairs but conditional semantics/Apple IDs fail qualification |
| OPENINPUT-002 / header-port-session1 | --patch-header | 1 / fail | All six corrected target cases pass. Configuring Carbon's actual three Makefile tokens still leaves its ARM64 gap. Pthread reaches pointer conversion and missing generated Mach headers |
| OPENINPUT-003 / mach-headers-session1 | --patch-header --generate-mach | 1 / fail | All19 real source-listed MIG client headers generated, kern_init compiles arm64; remaining11 pointer/integer diagnostics retained |
| OPENINPUT-004 / typed-pthread-session1 | --patch-header --generate-mach --typed-interfaces | 0 / component pass | All three genuine C units compile arm64 Mach-O with no diagnostics; real archive and four exact defined exports pass |

The small header patch adds native iOS/arm64 simulator detection using the full existing licensed header's Clang-intrinsic path. It is tested against native arm64 iOS16.5, arm64/x86 simulators, macOS13.3, Mac Catalyst and DriverKit controls. It is not a miniature fabricated SDK header. CPU/profile declarations remain separate from complete selected OS ABI.

Pthread0002 explicitly converts a pointer to the actual vm_offset_t argument and checks width.0003 uses integer zero at four actual integer user-address sites and explicit uintptr_t casts at seven opaque wait-queue callback sites, adding a second width assertion. The selected XNU callback prototypes/implementations confirm integer turnstile/event keys. No declared external signature, runtime implementation or diagnostic suppression was substituted. Preserve all per-file OSReference/APSL notices. Patches apply only in fresh private copies; originals and previously registered patch bytes remain unchanged.

MIG input names come from actual osfmk/mach/Makefile MIG_UUHDRS. Real target Clang preprocessing plus hash-verified KRN-002 migcom -novouchers generates19 client headers from the exact .defs, with stdin/output/source hashes. This partial genuine generation stage does not run the complete exporthdrs target or bypass IIG.

## Reusable component result

New archive: artifacts/open-kernel-inputs/typed-pthread-session1/libpthread_kext.a, SHA2563514335ee3b8fd08d1e5e309810fd0af16d4a8e68bcadff1fc624ab591ff7aca. The three object hashes, corrected full header, generated header tree and source/tool provenance are in fixtures/public/open-kernel-inputs/reusable-components.json. It also points to the earlier independently built E1S firehose archive. Neither compiled library is committed to Git or claimed as a combined full-kernel/SDK qualification.

The actual pthread archive defines _pthread_start, _pthread_stop, _pthread_internal_functions and _pthread_kext_kern; symbols are checked as exact defined names with real hash-verified nm -gUj. Each component object passes the existing bounded thin-arm64 MH_OBJECT verifier. No target ARM code or concurrency/runtime test executed. Compiler type-builtin compatibility fallback from the original donor remains a security/Apple-compiler equivalence limitation.

## IIG decision and remaining work

The real open IIG emits files for all17 selected definitions, but that is only text generation. Its code explicitly uses FNV method IDs and warns not to mix generated class interfaces with Apple's. It supports the kernel-side subset, not complete user DriverKit metadata. The owned conditional probe emits both method IDs and unconditional generated declarations for -D0 and-D1, while actual Clang preprocessing selects different single methods. This is stronger than a successful CLI exit and prevents a drop-in compatibility claim. Generated headers/implementations were not compiled against an actual selected SDK/header oracle.

KRN-004 must recover and qualify actual selected8796 DriverKit generated-header/RPC/flag inputs before a positive integration result. Public-source or explicitly supplied local inputs need exact provenance and ABI evidence; do not replace unknown IDs with self-consistent synthetic success. Full SDK/private header, exporthdrs, full kernel/link/check_all_exports/symbolset and native/recovery gates remain separately incomplete. The original KRN-001/KRN-003 owners, files, blocked records and historical failed evidence are preserved; this research result does not complete or impersonate those claims.

Optional requests for existing local SDK/iOS/RIL inputs still have no supplied path. No elapsed-time assumption supplies an input. Independent host work remains available; these component results do not complete the full goal or qualify GPU/Wi-Fi/SIM/eSIM hardware.

## Validation and completion

After state/plan updates, make check passed132 default tests plus registry/board/capability checks; the exact log/hash is bound by fixtures/public/open-kernel-inputs/final-checks.json. Supplemental ar extraction verifies all three archive member bytes exactly match their compiler outputs and independently parse as thin arm64 MH_OBJECT; archive-members.json retains real commands/hashes. All four immutable experiment digest sets and139 qualified host-prefix file hashes were revalidated. Consumed selected tool binaries were individually checked before use; this prefix-wide check is explicitly supplemental after the builds.

RES-009's research acceptance is reviewed against these actual artifacts, per-file licenses, rejected candidates and exact remaining gates. Completion of this research/component task does not complete KRN-003, the full kernel, selected SDK/private ABI or native goal. Default tests remain separate from the actual compiler/generator experiments; no repeated Android/hardware experiment was used as substitute evidence. KRN-004 is the concrete next critical build-input task.
