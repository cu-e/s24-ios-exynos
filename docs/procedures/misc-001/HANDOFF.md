# MISC-001 review handoff — 2026-11-05

Owner: `codex-team-misc-20261105-an`. Branch: `team/misc-001-20261105`. Worktree: `worktrees/misc-001-20261105`. Keep task in progress until coordinator review, integration and global `make check`.

Outcome: exact public-source mappings and explicit unresolved inputs for haptics, NFC, biometric diagnostics/authentication, video codecs and DP external display are documented in `src/platform/misc/README.md`. Every boundary has request/completion/ownership requirements and a separate native acceptance gate. Apple security/service interfaces are explicitly unqualified. No native driver or fake hardware implementation was added.

Reviewed primary repository: `https://github.com/dx4m/android-kernel-samsung-e1s`, current `417484173abc2c4fa93e738ea82ad9f2e84911b1`, comparison BSP `f85e53cfa5497ead5d78821efbac84e51f37a4e1`. Manifest/index pin22 files/81 anchors with complete blob hashes.16 are identical and6 differ. Device context is the sanitized DEV-001 SM-S921B/e1s BYH3 Android15 profile; exact running DT/config, all five native operations and Apple iOS16.5 private frontends remain unverified. Source/license notices remain distinct; no vendor driver implementation was reused.

Key review findings:

- CS40L26 is I2C4/address0x40 with Samsung input-FF semantics, separate DSP/wavetable/SVC firmware and actuator calibration inputs. Firmware filenames do not supply bytes or redistribution rights.
- SEN6 NFC is I2C39/address0x27; defconfig/Makefile select `drivers/nfc/lsi` through `CONFIG_SEC_MX_NFC`. The alternative Samsung header has different commands. LSI SET_MODE treats ioctl arg as a value despite `_IOW`; GET_MODE is declared but not dispatched. Payment/eSE/firmware mode stay unavailable.
- QFS4008 production has secure gating and factory-only normal SPI. FD/IPC events are diagnostics, not matching results. Source read returns `copy_to_user` residual, not positive copied size. Secure-world protocol/token/keys, template isolation and Apple SEP/security equivalence are missing.
- MFC/MFD need matched firmware, imgloader/S2MPU, SYSMMU/36-bit DMA, clocks/power and exact per-plane formats. Codec tables and internal display success cannot qualify video hardware.
- DP depends on Type-C/PD/orientation/HPD/AUX/link training, DECON and DMA ownership. The board file warns its PMIC GPIOs need modification; exact running routing must be obtained. DP source/status cannot qualify a second display or HDCP.

MISCHOST-001 was registered before substantive manifest/check execution. Artifact directory, relative to MAIN: `worktrees/misc-001-20261105/artifacts/misc-001/2026-11-05-source-audit/`. `checks.json` records real UTC times, commands/exits, tested base commit plus uncommitted authored files, exact source hashes, tool versions and max child RSS. `command-1.stdout` has22 verified files,81 anchors and7 rejected controls: abbreviated revision, wrong digest, absent blob, wrong source anchor, false native qualification, wrong comparison digest and path traversal. Other commands: Python byte-compilation, `git diff --check`, Python version and Git version; all exit0. Python3.14.8, Git2.56.0, maximum child RSS21,532KiB. No compilers, heavy builds or VM were used. No phone/ADB/root/MMIO/flash/reboot/NFC/payment or external messages occurred.

The source verifier is a provenance check against actual Git objects, not DTS preprocessing, an ABI/hardware model or native qualification. All7 negative controls are executed against the real pinned reference objects. It disables Git lazy fetch/optional locks. Initial orientation used ordinary Git reads before discovering primary references were promisor clones, so automatic text-object hydration may have occurred; see procedure provenance note. Shared registry mutations used only MAIN CLI. Primary artifacts were not written.

Acceptance assessment:

1. Each of the five peripherals has exact known inputs, explicitly named unknown/proprietary inputs, a required interface and distinct measurable native acceptance: ready for coordinator source/specification review. Unknown values are unavailable rather than guessed. Native acceptance remains open for all five.
2. No Apple security or service compatibility claim: satisfied by the bounded specification and explicit unavailable secure/front-end dependencies.

Next: coordinator review the source assertions/requirements, integrate the owned commit, run global `make check`, and decide MISC-001 completion. Future implementation should be split into narrow hardware transport, native functional acceptance and exact frontend/security tasks; preserve USB/display/audio task ownership and private biometric identities/captures. Do not run native procedures under this host task. The evidence records host provenance checks only.
