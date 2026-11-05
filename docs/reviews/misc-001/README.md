# Independent MISC-001 review

Reviewer: `codex-team-review-misc-20261105-as`; task `REV-005`.
Exact implementation tip: `bf54dcdc4a92111f20b7a05b6ba435b2674d8251`.
Scope: read-only review of peripheral source specifications and provenance;
no native driver, firmware, secure-world or Apple frontend qualification.

## Result — 2026-11-05

**No P0, P1 or P2 finding was identified within this source-specification
boundary.** The requirements and pinned-source index are ready for coordinator
integration review, subject to primary-checkout `make check` and acceptance.
The reviewed commit implements a provenance checker and peripheral requirements;
it supplies no native peripheral driver or authentication service.

No implementation, reference or device files were changed. REV-005 remains in
progress pending coordinator acceptance. Earlier REV-003 has separate evidence
and coordinator acceptance; its state is managed independently.

## Source and evidence binding

The implementation worktree was clean at the exact tip above. Independently read
all 22 current and comparison Git blobs named by `src/platform/misc/sources.json`,
recalculated their full SHA256 digests and byte lengths, checked every one of the
81 line anchors, and compared actual bytes: 16 files match and six differ.
Current revision is `417484173abc2c4fa93e738ea82ad9f2e84911b1`; comparison revision
is `f85e53cfa5497ead5d78821efbac84e51f37a4e1`. Both are full commit identities.
Those pins do not establish the exact running BYH3 sources/configuration/DTBO.

All ten hashes in the original evidence capsule matched actual files. The four
source files recorded by its precommit `checks.json` also matched the committed
Git blobs at the reviewed tip. The original evidence openly records that those
checks preceded the source commit. Its `host-test` capsule wraps execution of a
checker whose result is explicitly `source-review`; neither category is a native
peripheral result. The independent capsule uses `source-review` throughout.

Source notices agree with the requirement to retain per-file licensing:
CS40L26 has GPL-2.0/Cirrus notices, LSI NFC and fingerprint headers carry Samsung
GPL version 2-or-later notices, MFC has its original GPL notices and DisplayPort
states GPL-2.0-only. No driver implementation was imported into XNU. This review
does not authorize later copying under the project license or supply firmware
redistribution rights.

## Independent contextual assessment

Requirement line references below identify `src/platform/misc/README.md` at the
reviewed tip. Upstream paths identify current pinned Git objects, retained in the
review's local artifact capsule as full text for contextual inspection.

| Requirement | Independent source inspection | Assessment |
| --- | --- | --- |
| Haptics, lines 19–25 | Generated `e1s_eur_openx_w01_r13.dts:2403` defines USE_VIBRATOR_i2c; its conditional node at 2428–2433 is hsi2c_4/address 0x40/1 MHz. `cs40l26.dtsi` gives IRQ/reset, deferred firmware, OWT version, actuator-bin ranges and disabled generic VA/VP placeholders. `cs40l26.c:3519` rejects non-FF_PERIODIC effects; the Samsung operation table at 3821 provides upload/playback/gain/erase. Firmware names are literal header constants. | Mapping is supported as pinned source text. Calibration, actual firmware, safe operating limits and physical idle/stop measurements remain unavailable. Source tuning numbers 48/70 are not promoted to verified physical limits. |
| NFC, lines 29–35 | Defconfig lines 8615–8619 plus the actual `drivers/nfc/lsi/Makefile` conditional select nfc_slsi_sec/sec_nfc at this fragment level. The overlay at 4400 gives I2C39/0x27 and the stated pins/rail/SEN6 string. LSI header declares magic S, commands 0–5 and 512/260-byte constants. The entire ioctl switch at `drivers/nfc/lsi/sec_nfc.c:937` casts arg to an integer, dispatches SET_MODE, and has no GET_MODE case; command 6 occurs only in the alternate Samsung header. | The warning against importing the alternate ioctl ABI is correct. This review does not qualify the complete vendor external-module build, loaded BYH3 module, NCI reassembly, RF behavior, eSE, card emulation or payments. |
| Biometrics, lines 39–45 | `fingerprint.h:25` requires FINGERPRINT_SECURE and absence of SEC_FACTORY for ENABLE_SENSORS_FPRINT_SECURE. `fingerprint_qfs4008.dtsi:78` gates ordinary SPI11 on SEC_FACTORY (`!1` is false); production clocks and the disabled generic 3 V regulator stanza match the text. `qfs4008_common.h` defines diagnostic event/control values. Full `qfs4008_read` at common.c:609–679 copies the enum and returns copy_to_user's residual, including zero on successful copy. | Production secure ownership is correctly separated from ordinary SPI/FD/IPC diagnostics. No match/authentication token, trusted application, key hierarchy, enrollment or Apple SEP guarantee is implied. A future adapter needs its own specified byte-count/error semantics. |
| Video codecs, lines 49–55 | `s5e9945-mfc.dtsi` gives both MFC/MFD register pairs, IRQ symbols, SYSMMU/36-bit DMA, memory-region and separate 1 MiB normal/secure firmware IOVA slots. P010/stride/SBWC and codec tables are options, not observations. `mfc.c:1117`/1119 selects separate decoder/encoder operations; mfc_common.h names mfc_fw.bin; core_ops.c:1258 onward supplies conditional imgloader and S2MPU verification hooks. | Firmware IOVA is correctly distinguished from physical RAM. Per-plane ownership, firmware verification and protected decode remain explicit dependencies rather than a fabricated hardware implementation. |
| External display, lines 59–65 | `s5e9945-drm-dpu.dtsi:803` gives the stated three DP/PHY/TCA ranges, interrupt, power domain and two clocks. `s5e9945-e1s_common.dtsi:1266` explicitly says the PMIC GPIOs need modification. Full DP source handles CONNECT/LINK_CONF/HPD at 3367/3405/3448, runs link training and publishes EDID modes. | The warning is retained as an unresolved board input. USB Type-C/PD/orientation and DMA/fence dependencies are separate from internal DSI scanout. No fixed display mode, HDCP key, protected output or Apple second-screen compatibility is invented. |

The source checker validates immutable blob identities and anchors. It does not
preprocess DTS, resolve all includes/overlays, build the vendor modules, prove
secure-world behavior or establish loaded firmware. An ancillary read of
`drivers/nfc/Kconfig` found no local blob; it was not fetched and supplies no
evidence. No complete parent build integration claim depends on that read.

Shared request IDs, deadlines, generations, cancellation and exactly-once
ownership are presented as future interface requirements, not an already
implemented Samsung/Apple ABI. Every peripheral retains a separate native gate
with independently observable results and declared failure/cleanup checks.

## Actual independent verification

MISCREV-001 was registered against the procedure below before verification.
From the reviewer worktree:

```sh
python3 docs/reviews/misc-001/reproduce.py review1
```

Exit 0; recorded `2026-11-05T13:54:29.386134+00:00`. The runner executed 66
subprocess commands and five review check groups. Fifty-four commands returned
0; twelve intentional rejection invocations returned 1 with structured fail
results. Peak measured child RSS was 21,456 KiB; no compiler jobs or heavy builds
were used. Subprocesses have 45-second timeouts and lazy fetching/optional Git
locks are disabled.

The actual original checker passed 22 files/81 anchors and its seven negative
controls. Twelve additional reviewer-created manifest controls were rejected by
the unchanged checker: duplicate/absolute/dot-segment paths, zero/bool anchor
lines, empty anchor list, wrong byte size, wrong comparison classification,
missing commit, missing/numeric native flag and empty file list. These controls
use actual pinned objects; no shared reference or implementation mutation is
needed to exercise rejection. Passing those controls is not proof that this
utility validates every possible malformed JSON shape or the truth of arbitrary
prose associated with a valid blob.

[reproduce.py](reproduce.py) retains exact commands, actual exits/stdout/stderr,
Git/Python versions and hashes, source/runner hashes, source-object copies,
original capsule hash, date and resource measurement. The original source checker
and evidence were only read or executed as a host verifier; no upstream code or
script was executed and no device node was opened.

Local evidence:
`worktrees/rev-misc-20261105/artifacts/rev-misc-001/review1/evidence.json`.
SHA256: `1269b94d03533a49dc25eb9769ea6841dab82ae648971584cb8d386fdef5a870`.
Adjacent report SHA256:
`601589b8e063c4008efd34406fe646d090285280307e0086ac3158fc269a1208`.

The coordinator owns primary integration and `make check`. All firmware,
secure-world, exact running board and private Apple inputs remain unavailable;
source provenance success cannot complete any of the five native gates.

## Reproduction procedure

Read the exact committed miscellaneous requirements, manifest, checker, procedure,
handoff and existing evidence. Use only read-only pinned Git-object inspection
with `GIT_NO_LAZY_FETCH=1` and `GIT_OPTIONAL_LOCKS=0`; retain generated outputs
inside this reviewer worktree. Independently check NFC Makefile selection and
ioctl argument handling, biometric secure/factory gates and diagnostic return
semantics, CS40L26 board/firmware/FF mapping, MFC firmware/IOMMU/format separation
and external DP unresolved GPIO/PD requirements. Check source license boundaries.

After registering MISCREV-001 in the primary registry, rerun the actual source
checker and its negative controls, independently compare manifest hashes/anchors
and source differences against Git objects, validate original evidence hashes,
and run additional malformed-manifest rejection controls against the exact
checker without modifying it or shared references. Save actual commands, exits,
tool/source/artifact hashes, date and exact implementation identity. Publish
actionable P0/P1/P2 findings or a bounded no-finding conclusion and a handoff.
Commit only docs/reviews/misc-001 and leave completion to coordinator acceptance.
