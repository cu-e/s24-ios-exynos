# Open kernel-input alternatives

RES-009 investigates real open-source header/SDK/IIG alternatives. It does not replace the approved E1S/XNU8796.121.2/iOS16.5 runtime or modify KRN-001/KRN-003 reserved implementation/evidence. Source experiments, generated text and component archives remain distinct from a full SDK/export/kernel/native qualification. No phone, global Nix setup, SDK/firmware/Apple binary download or upstream installer is used.

Pinned candidates:

- PureDarwin/PureDarwin6982ddbfca1047c86680ec7c66da152789746efd: current upstream-xnu-12377 build method, source-assembled SDK recipe and its real TargetConditionals header. Review per-file APSL notices plus project/component licenses. This is not a prequalified iOS16.5 SDK.
- PureDarwin/iig-tools28010c688caab7eb5400b9c98faa5b1e538e0108, exactly from that flake lock. BSD-3-Clause, copyright2026 Vali0004. Three real C++17 source files build a host generator; no Nix activation is necessary for this isolated measurement. It explicitly supports the kernel-side subset and uses non-Apple FNV message IDs. Do not mix its generated interface for a class with Apple's or claim drop-in ABI.
- Apple CarbonHeaders214a9ae7ab3c0c78ddb50328ca226e6313c4c782: older public APSL target-condition header, checked as a candidate rather than assumed ARM64 support. The separately found Apple CF Linux-only header is not an iOS header and is excluded from adoption.

Current [PureDarwin SDK documentation](https://puredarwin.org/handbook/building/apple-sdk.html) describes collecting source headers and real MIG output, with a small authored overlay. Its newer source tree and reconstructed stubs need their own version/ABI review; source-only availability is not compatibility with this selected Apple userland. The old article requiring a macOS11.3 SDK and newer source-built-SDK instructions refer to different states, so use the actual pinned recipe instead of merging them into one claim.

## Actual measurements

Register OPENINPUT-001 before the baseline command. The checker verifies exact source pins/clean state, the prepared E1S report and its complete immutable file witness. It observes actual target macro profiles for arm64 iOS16.5 device, arm64/x86_64 iOS simulator and arm64 macOS13.3 negative control. A filename/Apple origin is not enough; wrong target macros reject adoption.

```sh
python3 tools/sources.py verify puredarwin-build-inputs puredarwin-iig apple-carbon-headers
python3 tools/research/open-kernel-inputs/check.py --run baseline-session1 \
  --clang /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang \
  --host-cxx /usr/bin/c++ \
  --prepared-run artifacts/xnu-prepare/e1s-dependency-source-session1
```

The checker builds the real reviewed IIG tool in the new ignored run and invokes it on all17 actual selected-kernel DriverKit definitions. Output text hashes/exit codes are retained, but generated text is neither a compiled-header pass nor Apple RPC ABI qualification. An owned conditional fixture compares actual -D0/-D1 generator outputs with a genuine Clang preprocessing oracle; inspect the resulting methods and preserved conditions before interpreting differences. Do not treat successful file creation as honored compiler flags.

No genuine iOS16.5 SDK or Apple-generated header oracle is supplied. The tool does not infer matching Apple message IDs from self-consistency. If target profiles require a source correction, retain a small attributed patch to the actual full open header, test all controls and document the deviation before separately compiling any pthread component. Never create a tiny replacement TargetConditionals header or invent missing types/functions to make compilation pass.

An explicitly preregistered --patch-header experiment can apply the retained correction only in a new artifacts copy. After every measured profile matches, it compiles the three real pinned pthread C translation units for E1S against genuine source headers and the already reviewed donor compiler-compatibility header. If all actual arm64 objects compile, it uses hash-verified KRN-002 Mach-O tools to build/inspect a real archive. Any missing next header/compiler issue remains an actual failure; do not substitute unsupported code or call this a full exporthdrs/SDK pass.

Per-command maximum60 seconds within a300-second command budget. Run names are new; prior failed reports/builders/patches retain their bytes. No ARM code executes. Completion of this research task requires accurate candidate decisions, tested applicable behavior and precise remaining inputs; KRN-003/full-kernel acceptance remains separately reserved.

OPENINPUT-001 retained actual failure: the full PureDarwin header recognizes ARM64 CPU but selects macOS for native iOS and the arm64 simulator. The old Carbon file is also an unprocessed build template, with no ARM64 CPU branch; raw template failure alone is not proof of a missing configuration-independent OS API. The real IIG tool built and generated17/17 interface text pairs, but the conditional probe emitted both methods/IDs for either flag while Clang's oracle selected one. Its code explicitly labels its FNV RPC IDs non-Apple. Do not adopt it as a drop-in Apple generator.

Register OPENINPUT-002 before a fresh `--run header-port-session1 --patch-header`. The [small full-header correction](../../../patches/open-kernel-inputs/README.md) uses the existing compiler-intrinsic platform detection; it does not invent SDK declarations. Test native iOS, both simulators, macOS, Mac Catalyst and DriverKit controls. Separately apply only the old Carbon Makefile's three literal configuration substitutions, with recorded parameters, to distinguish its real configuration stage from its intrinsic ARM64 gap. No installer/symlink/removal recipe is executed.

OPENINPUT-002 passes all six corrected target cases and retains actual pthread failures: kern_init reaches an implicit void-pointer to vm_offset_t diagnostic; kern_support/kern_synch need genuine generated mach/mach_port.h and mach/task.h. Register OPENINPUT-003 before `--run mach-headers-session1 --patch-header --generate-mach`. Apply a separate explicit typed-address cast/width assertion only in a private pthread source copy. Generate the client headers listed by the exact osfmk/mach/Makefile through real Clang preprocessing plus hash-verified KRN-002 migcom, retaining source/stdin/output hashes and failures. This reproduces the source's MIG client-header rule with -novouchers and actual kernel definitions; it is a partial genuine generation stage, not full exporthdrs or an SDK replacement. No public/native RPC success is fabricated.

OPENINPUT-003 generated all19 actual source-listed client headers and compiled kern_init to arm64 Mach-O. The other units retain11 strict Clang diagnostics: four pointer-NULL uses for integer user_addr_t values and seven pointer wait-queue keys at uintptr_t callbacks. The exact selected XNU bsd/sys/pthread_shims.h declares those integer types, and bsd/pthread/pthread_shims.c uses the numeric key for turnstile/event identity. Register OPENINPUT-004 before `--run typed-pthread-session1 --patch-header --generate-mach --typed-interfaces`: use explicit integer zero at integer address sites and explicit uintptr_t casts plus a width assertion. Do not suppress diagnostics, alter external prototypes or invent implementations. The first three failed experiments and source patches remain immutable.

OPENINPUT-004 passes: three genuine arm64 Mach-O pthread objects and libpthread_kext.a with exact defined pthread_start/pthread_stop/pthread_internal_functions/pthread_kext_kern symbols (Mach-O leading underscores). All19 genuine Mach client headers and six target cases pass. The three C compile stderr logs contain no diagnostics. The archive SHA256 is3514335ee3b8fd08d1e5e309810fd0af16d4a8e68bcadff1fc624ab591ff7aca. Reuse only after checking [the component manifest](../../../fixtures/public/open-kernel-inputs/reusable-components.json), actual file hashes, source profile and limitations; no archive or Apple SDK is bundled in Git. IIG ABI, full export/link/symbolsets and native execution remain separate gates.
