# HakiOS reuse audit — 2026-11-06

Observed upstream HEAD is `2631f5d7d4f9d7322aca60991b34ba465dec343b`.
The project research pin is `87bf4851bcc9cbb24fd79997820aa3661abe4ea5`;
the embedded E1S build-tools base is the separate `d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c`.
No source pin or existing checkout was changed. Named source files and complete
Git tree identities were inspected in an independent artifact repository.

## What can be reused

The [Makefile](https://github.com/oosexgang/hakios-xnu-kernel/blob/2631f5d7d4f9d7322aca60991b34ba465dec343b/Makefile#L70)
already supplies the complete common path: `kernel`, `loader-open`, `hello`,
payload packaging and `qemu-open`. The kernel is genuine XNU `8796.121.2`;
`tools/make-kernel.sh` invokes its build and permits only the explicitly named
kext symbol-set failures after requiring a produced kernel. It does not permit
arbitrary compilation or link failures. The hello target compiles the donor's
static raw-syscall program without libc. These are existing results to reproduce,
not a new kernel, loader or PID1 implementation by this project.

There is a material qualification to the advertised open path. The
[dependency setup](https://github.com/oosexgang/hakios-xnu-kernel/blob/2631f5d7d4f9d7322aca60991b34ba465dec343b/xnu-deps/setup.sh#L11)
expects a Theos Linux toolchain and an iPhoneOS16.5 SDK, and obtains matching
MacOSX13.3 Kernel.framework headers for DriverKit/IIG. The open target needs no
Apple **runtime image**, but its stock build is not a build with no SDK inputs.
The three standard SDK directories checked locally do not exist; no claim is
made about an unsearched custom installation. A stock reproduction must first
establish this coherent dependency set. Do not mix those SDK headers into the
current public-source-qualified object set.

The [QEMU runner](https://github.com/oosexgang/hakios-xnu-kernel/blob/2631f5d7d4f9d7322aca60991b34ba465dec343b/qemu/run.sh)
uses UEFI, Cortex-A76/GICv3, a placeholder EFI loader and a payload. Its defaults
are 6GiB guest RAM and 384MiB TCG cache. These do not satisfy this lab's existing
256MiB guest limit automatically. A resource-compatible configuration and actual
firmware availability must be checked before running it. No QEMU or full build
was launched for this audit.

## Version comparison and transition cost

| Candidate change | Useful difference | Compatibility and cost | Decision |
| --- | --- | --- | --- |
| Research `87bf4851` → current `2631f5d7` | Adreno Metal import/fixes, touch polling, platform-specific arguments and guarding framebuffer register reads on unknown SoCs. | Complete trees contain649 and877 entries;258 entries differ. `Makefile`, `xnu-build.sh`, `xnu-env.sh`, dependency setup, QEMU runners and raw hello are unchanged. New Metal/Adreno work is not an Xclipse driver. | No update is needed to obtain the existing common build recipe. Review the unknown-SoC framebuffer guard only if a concrete E1S source path needs it. |
| Embedded E1S tools `d82c64a3` → current | New configuration/driver organization and evolved loader/dependency setup. |591 versus877 complete tree entries,1208 differing path identities including additions/deletions/renames. Kernel patch selection, SDK wrappers, generated headers and libraries must move together; this is not a drop-in wrapper update. | Keep the embedded E1S base coherent. Prefer the three board-port commits audited by CN over replacing the whole common tree. |
| Use stock `make qemu-open` in isolation | Ready loader, hello, packaging and runner, without our general execution framework. | One coherent environment setup and full guest reproduction; SDK/toolchain/UEFI and memory settings are concrete inputs still to qualify. | Fallback common bench if the current one-link diagnostic exposes a broad environment problem. Do not start a second full build speculatively. |

The bounded fetched history contains111 reachable commits above the research pin,
including merged Metal history. The exact complete-tree comparison, rather than
that history count or README performance claims, is the compatibility evidence.
Upstream source and upstream-described demonstrations are not a local successful
boot and are not measurements on this S24.

Local evidence: `artifacts/team-coordination/20261106-team/strategy-reassessment-20261106/`
contains `hakios-tree-comparison.json`, `hakios-commit-counts.json`, the retained
named-file retrieval results, Git metadata repository and fetch log. Transient
HTTP failures/404s remain recorded; successful Git tree inspection was used to
avoid treating missing sparse files as absent upstream features.
