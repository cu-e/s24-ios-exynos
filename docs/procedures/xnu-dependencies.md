# KRN-003: actual E1S kernel dependencies

Scope: isolated host compilation/input analysis, no phone or Apple SDK download. Preserve original KRN-001/NAT-001 owners, reserved files and failed evidence. A local input profile or source patch is not a completed archive build.

Use the real [KRN-002 input manifest](../../fixtures/public/xnu-host-tools/qualified-inputs.json): generators-session2, macho-session4 tools and verified macho-session3 host dependencies. Verify every consumed binary/prefix digest before reuse. Map tool names only inside the new artifacts run; do not create global compiler symlinks or rename LLVM tools to imply ld64 compatibility.

Pin the actual donor-declared AvailabilityVersions115.4, libdispatch1415.100.11 kernel firehose and libpthread514.100.2 sources. These kernel sources are distinct from the Linux libdispatch runtime used to build ld64. Read component/per-file notices before compilation and preserve them with artifacts.

The donor stage2/library scripts hardcode ARM64_BOARD_CONFIG_BCM2837. KRN-003 must use the exact prepared E1S kernel, explicitly select the compiler and E1S board, and measure actual included types/symbols rather than infer corruption from CPU-count macros. Apply small attributed patches only in an artifacts copy. No global compiler/header/library replacement is implied.

Full XNU exporthdrs traverses iokit/DriverKit and generates headers from iig definitions. The pinned donor substitutes pre-generated matching Kernel.framework headers and partial implementations. No supplied SDK/DriverKit paths are currently configured. Do not invent those headers, pretend the partial iig RPCs are functional, or call a restricted C-only source-header analysis a successful full exporthdrs/full kernel build.

Before deciding whether the external C libraries independently require those closed inputs, trace their actual includes and generator needs. An explicit source-only header profile may be investigated only using genuine pinned source/compiler headers and real generators, with every origin recorded. No missing API/structure may be replaced by a success stub to obtain a green build. Any such partial analysis remains separate from actual SDK/header ABI qualification and the task's complete archive acceptance.

Register E1SDEPS-001 before the initial bounded compiler/include experiment. The first hypothesis tests the actual compiler/board/header requirements of the pinned firehose and pthread translation units, with no SDK or archive pass inferred. Use a fresh artifacts/xnu-dependencies run, the exact prepared-source report and source pin checks. Retain genuine compiler failures and the include graph; these determine the next input/generator step.

Completion requires real E1S arm64 Mach-O dependency archives, members/symbols and relevant ABI/layout measurements with provenanced inputs. Record precise external gaps rather than reusing BCM2837, a different OS or fake SDK metadata. Full kernel/export checks remain KRN-001, and native execution/recovery remain separately gated.

E1SDEPS-001 failed all eight actual syntax attempts at string.h while the board macro probes passed. The genuine header exists at osfmk/libsa/string.h, whose Makefile exports it at the osfmk header root. E1SDEPS-002 adds that exact source-export alias to the raw-source audit; no Linux libc header, SDK file or invented declaration is substituted. This remains an include audit, not a full exporthdrs or archive pass.

```sh
python3 tools/build/xnu_dependencies.py --run unique-include-audit \
  --clang /home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang \
  --prepared-run artifacts/xnu-prepare/e1s-dependency-source-session1 --audit-includes
```

E1SDEPS-002 passes actual firehose syntax in both profiles but retains failure for all pthread units at TargetConditionals.h. Register E1SDEPS-003 before `--build-firehose` (replacing --audit-includes): it compiles the real unmodified firehose implementation into arm64 Mach-O objects, creates real archives with the qualified libtool, inspects definitions with nm and reads nine ABI fields from a separately compiled constant Mach-O section. No ARM code is executed. The bare empty BCM2837 macro must be distinguished from an undefined macro in new reports; the original raw macro output remains authoritative for earlier parser-null displays.

This is a firehose component experiment, not a completed KRN-003 or fake SDK path. Keep the pthread SDK/header gap and full exporthdrs/SDK/DriverKit ABI acceptance open. Differences in CPU/cluster macros alone do not prove library ABI corruption; report the actual compiled sizes/offsets and leave unmeasured fields unknown.

Register E1SDEPS-004 before --verify-profile. It applies the [attributed donor patch](../../patches/build-inputs/README.md) only in the new run, verifies missing explicit compiler variables fail before object creation, then compiles genuine C/C++ arm64 Mach-O fixtures through the patched wrapper. The patch selects E1S/explicit-machine guards for the two dependency scripts, but those setup/pthread scripts are not executed by this check. Their complete workflow remains unqualified until actual SDK/exported-header inputs are supplied. No global compiler symlink or SDK stand-in is created.

E1SDEPS-004 applied the patch and rejected an absent C compiler, then failed because the fixture omitted freestanding kernel flags and entered host libc headers. Preserve that failure. E1SDEPS-005 uses the same genuine source headers with explicit -mkernel/-nostdinc/kernel defines: both C and C++ negative guards reject missing compiler variables, and both positive cases emit actual arm64 Mach-O objects. This qualifies the wrapper fixture only. It neither runs the setup scripts nor establishes full compiler/SDK ABI compatibility.

The ABI reader rejects wrong architectures/file types, duplicate or absent records, incorrect extents, relocations, zero-fill sections, header aliases and bytes outside their parent file-backed segment. Host byte fixtures test these rejection paths. Separately reread the actual saved compiler objects with the current verifier; retain the original experiment reports and builder snapshots unchanged. New archive runs use nm -gUj to require a defined external symbol; supplemental inspection of the original archives with these flags is recorded with final checks.
