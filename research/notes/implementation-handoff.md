# First host lab implementation handoff

Session: 2026-11-05, owner `codex-implementation-20261105`, primary checkout `/home/egor/dev/pet/s24-ios-exynos`, branch `main`. Execution started from commit `8fa104ac04ffd3dda8a594729345e22a765d12f1`; implementation was uncommitted during these experiments. Dated evidence and source/artifact digests identify those executions; the implementation commit is the commit containing this handoff.

## What actually works

| Result | Evidence and boundary |
|---|---|
| Source acquisition and provenance verification | `tools/sources.py` fetches exact SHA revisions into ignored references, checks origin/cleanliness and hashes reviewed files. Eleven selected upstreams were inspected, including exact open XNU. Six offline Git tests cover rejection cases. |
| E1S freestanding probe and XNU loader build | Two actual builds with Zig 0.16.0 produced identical bytes for all eight ELF/Image/boot/tar outputs. [Build evidence](../../state/evidence/BLD-001.json). These packages contain freestanding loader code, not a compiled XNU payload. |
| Complete upstream patch application | Exact open XNU `c54f35ca767986246321eb901baf8f5ff7923f6a` is prepared with embedded HakiOS and all E1S patches. See the source registry and [patch report](../../fixtures/public/build/patches-session2.json). No kernel compilation claimed. |
| Independent boot and memory checks | Actual loader packages pass Android boot v4/1584, image/footer/size/tar checks. Five negative-test groups include invalid entry, BSS/gap/non-executable entry and reserved-memory collision. Upstream ADT/FDT/ramdisk tests passed but warned about absent Apple product/D22 nodes. [Evidence](../../state/evidence/BOOTCHECK-001.json). |
| Signed Android probe | ARM64 and x86_64 APK, actual stock Vulkan core, private atomic JSON, explicit export, cooperative Stop, finite fence polling and process-wide worker/restart gate. Host exact-pixel/cancel/injected-timeout and concurrent admission tests passed. [Host evidence](../../state/evidence/VULKANHOST-001.json); [instructions](../../src/android-probe/README.md). |
| Minimal translation and execution | Pinned metal2vulkan built with Rust 1.98.1. Project-owned synthetic AIR-shaped LLVM IR assembled with NDK LLVM 19.0.1, translated and independently checked with spirv-val; the real host Vulkan compute pipeline wrote 9212400 and preserved 15 guard words, zero tolerance. [Evidence](../../state/evidence/METAL-001.json). No Apple-native reference, Metal runtime, render pipeline or Xclipse acceptance. |
| Task coordination and capability accounting | 62 bounded tasks, owner reservations, dependencies, generated Kanban/cards and 15 subsystem capability records. Native support remains `not-tested` for every subsystem. Builds and host tests are not phone measurements. |

The first patch-preparation attempt exposed `git apply` discovering the parent project and skipping nested paths. Required-file checks caught it; an isolated Git root fixed it. Failed and corrected reports remain immutable. Emulator setup/automation failures are also retained; see the experiment registry rather than assuming every run passed.

## Local artifacts

Artifacts and references are intentionally excluded from Git. Public reports retain hashes and commands; another machine must rebuild the binaries.

- Loaders: `artifacts/e1s-build/loader-session2/{probe,loader}/`; independent [reproducibility digest list](../../fixtures/public/build/reproducibility.json).
- Patched source: `artifacts/xnu-prepare/patch-session2/xnu/`.
- APK: `artifacts/android-probe/apk-session5/s24-vulkan-probe.apk`, 11,444,772 bytes, SHA-256 `6e5bbc75f3c76db45c8c826de2e42a3f7f488ee217050e7e93200db7498c3943`. Development key remains local mode 0600. This build includes the reviewed theme/restart/storage fixes and records per-file hashes for actual compiled inputs. Documentation/helpers are excluded from its source digest.
- Translator: `artifacts/metal-build/session1/source/target/debug/metal2vulkan`; initial actual build resolved the subsequently committed Cargo lock. The explicit `build_translator.py --run locked-session2` wrapper also built successfully with `--locked`; [build report](../../fixtures/public/graphics/translator-locked-build.json). Debug binary hashes differ across build paths; no byte reproducibility is claimed for Rust binaries.
- Translated fixture and actual compute output: `artifacts/metal-fixture/fixture-session2/`.
- Final `make check`: 62 tests passed; [stdout](../../fixtures/public/host-lab/final-make-check.stdout.txt), [stderr](../../fixtures/public/host-lab/final-make-check.stderr.txt). This log predates final ledger-only completion updates. Final [audit](../../fixtures/public/host-lab/final-audit.json) checked new evidence artifact hashes, local links, the final APK/compiled inputs and unchanged permissions/historical evidence.

## Resume and missing external inputs

```sh
make doctor
python3 tools/lab.py status
python3 tools/lab.py task next --scope host
python3 tools/lab.py task show KRN-001
python3 tools/lab.py task show NAT-001
make check
```

KRN-001 is blocked: no explicit local iPhoneOS16.5 SDK or reviewed pinned dependency/build-tools directory is configured. [Preflight](../../fixtures/public/build/kernel-preflight.json) exits 2; it does not search the whole machine or assert that no SDK exists anywhere. Supply and verify those inputs, then resume the existing owner or explicitly release/reassign it; build the kernel and dependency set, preserve export-check failures, and record full hashes. Source preparation alone is insufficient.

NAT-001 is blocked: exact matching BYH3 stock images, dated/hash-verified backups, actual unlock/Download Mode evidence and measured Android recovery are missing. [Recovery template](../../docs/procedures/recovery/session-template.json) is a draft with no authorization. NAT-004 qualifies real recovery separately; NAT-003 requires both this and KRN-001. The user's daily phone cannot be promised automatic recovery.

No primary-phone ADB command, APK installation, su request, settings change, reboot, partition write, firmware download or native test occurred in this implementation session. All emulator commands explicitly selected the task-owned emulator. Existing authorization flags and historical device evidence are unchanged. GPU-003, VM-003 and all native tasks remain gated.

Independent host work remains ready on the board: display/HID, USB, Xclipse interface specification, KIWI Wi-Fi, exact Bluetooth transport, sensors/GNSS and Samsung CPIF specifications. A task being ready records dependency readiness, not the availability of every external input. Full native iOS, GPU, Wi-Fi, SIM/eSIM, IMS voice, thermal qualification and 24-hour acceptance remain future engineering and device measurements, not completed support.

## Android UI qualification remains open

Seven fresh Android 36 emulator attempts failed setup/automation: authentication, cold installation deadline, unavailable control hierarchy, System UI ANR and boot timeout. Actual APK installation/opening and an initial light screenshot were observed, but **no passing APK Vulkan report was obtained**. The final APK5 was built after source-review fixes and has not run in an emulator. Source review scored all three findings resolved; its disposition remains **recapture**, not a full UI pass. [Review](../../fixtures/public/host-lab/ui-review.json). TST-002 tracks a functioning isolated guest, exact pixels, dynamic light/dark, enlarged text, result/error states, export, lifecycle and accessibility semantics. Host GPU-002 acceptance is limited to the built APK and real host-core/lifecycle checks. GPU-003 remains the separate physical-phone gate.
