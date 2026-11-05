# AUD-003: source-qualified ABOX PCM host admission and ownership

Date: 2026-11-05. Owner: `codex-team-audio-host-20261105-bh`.
Branch/worktree: `team/aud-003-20261105`, `worktrees/aud-003-20261105`.

This is an input-only host preparation component. It validates selected AP-side
ABOX message snapshots and bounded PCM ring extents, then tracks local period
leases through Stop/error/quarantine. It never submits an IPC command, maps DMA,
touches MMIO, loads firmware or plays/captures audio. **It does not complete
AUD-001 or qualify native sound, CS35L43 operation or a private Apple ABI.**

## Actual source and interface

The source is [selected E1S Linux at
417484173abc2c4fa93e738ea82ad9f2e84911b1](https://github.com/dx4m/android-kernel-samsung-e1s/tree/417484173abc2c4fa93e738ea82ad9f2e84911b1),
the exact `s24-linux` pin in the primary catalog. The fixed
[`profile.json`](../../../src/platform/audio/host/profile.json) records all
sixteen full Git blob IDs, SHA256 hashes and byte extents. `source.py` reads the
shared tree with `GIT_NO_LAZY_FETCH=1` and `GIT_OPTIONAL_LOCKS=0`; missing blobs
are fetched as explicit public raw text into this worktree only and verified
against the tree blob identity before reuse. Existing references and other
owners' artifacts are read-only. Source responses/cache files are size bounded.

| Source | Established interface |
| --- | --- |
| `include/sound/samsung/abox_ipc.h` | Actual `ABOX_IPC_MSG` size 768, PCMTASK size 88, SET_BUFFER size 24, HW_PARAMS size 20, parameter offset 16, declared `phys` offset 32; playback/capture IDs 2/3 and SET_BUFFER/HW_PARAMS/POINTER/CLOSED types 20/14/18/23 |
| `abox_rdma.c`, `abox_wdma.c` | `setbuff.size = params_period_bytes(params)` and `count = params_periods(params)`; width/channels/packed copied to HW_PARAMS; pointer notification stores an absolute IOVA and calls `snd_pcm_period_elapsed`; CLOSED completes the separate close completion |
| Driver `abox.h` | Standard RDMA0/WDMA0 IOVAs `0x91000000`/`0x92000000`; 1 MiB channel partitions; generic buffer maximum 1 MiB, period bytes 16..512 KiB, source period count 2..65536 |
| `include/sound/pcm.h`, `sound/core/pcm_misc.c` | Genuine byte/frame calculations; S16_LE physical width 16, S24_LE physical width 32, S24_3LE physical width 24, S32_LE physical width 32 |

The consumer accepts **AP-side in-memory snapshots of the selected native
little-endian 64-bit declarations**, not an asserted DSP queue/wire ABI. The
original RDMA/WDMA request helpers submit `sizeof(ABOX_IPC_MSG)`. The provider
must supply the actual captured extent; an invented length cannot certify the
backing allocation. ARM64 compilation checks the real source declaration layout.

The owned profile deliberately supports only ordinary DMA channel 0 in either
direction and at most 32 periods. It excludes compressed, sync, RAM, ION,
backend, USB and other channel/routing paths. These are narrower host limits,
not new firmware constraints. It requires frame-aligned periods/positions and
rejects a pointer at/after the ring end instead of guessing wrap behavior. The
source pointer helper itself has no matching end bound and floors byte/frame
division; valid aligned vectors are compared against that genuine helper.

`packed=1` is admitted only for 24-bit packed format. Unpacked 24-bit uses the
actual ALSA 32-bit physical container. A positive source `int` sample rate is
stored as metadata; admission does not promise the hardware supports that rate.
The source advertises KNOT rates and 1..8 channels. Caller-supplied mapping
extents must fit the source's 1 MiB IOVA partition and contain the whole
period-by-count ring. No mapping is actually created or probed.

Only fields assigned/read by the selected source path are consumed. The source
SET_BUFFER path does not assign its declared `phys` field; unused union/padding
and `ip_type` are not treated as mandatory zeroes. Oracle snapshots fill these
bytes with `0xa5`. Incoming notification `task_id` is ignored like the source
handlers, while configuration task/channel IDs must agree with the channel-0
profile. Incoming POINTER/CLOSED are the only admitted event types.

## Ownership contract

Calls require external serialization; this component is not an IRQ-safe native
driver and adds no kernel locking or cache-coherency claim.

1. `pcm_admit_plan` commits output only after full validation; `pcm_host_bind`
   revalidates the plan and requires a new nonzero epoch while idle.
2. Start permits bounded per-period leases. A unique local serial identifies
   each slot lease; stale/duplicate/forged extents cannot retire another lease.
3. Pointer callbacks require the live local epoch and a newer dispatch ticket.
   Repeating a position with a new ticket is allowed, as after a ring wrap.
   Repeating a callback ticket is rejected. POINTER does not retire a lease.
4. Stop blocks new work and pointer callbacks while retaining every outstanding
   lease. Errors enter fault/quarantine and invalidate prior close evidence.
   A subsequent Stop has a new local stop serial.
5. A matching CLOSED notification alone never permits release. Every lease
   must first be retired, and a trusted future provider must explicitly attest
   both DMA quiescence and draining of old callbacks. Only then can the mapping
   reach quiescent/released state. Missing/error/timeout evidence leaves it held.

Epochs, lease/dispatch serials and stop tokens are **local ownership metadata**;
they do not exist in the pinned DSP message. They prevent stale local callbacks,
not firmware replay. A future native transport must establish its real drain,
fence and generation association before using this model. Tests of the provider
attestation are host contract tests, not measurements of stopped ABOX DMA.

## Independent source oracle and measured checks

`oracle.py` compiles the actual complete IPC header and unchanged selected source
functions `abox_rdma_pointer`, `abox_wdma_pointer`, `bytes_to_frames`,
`frames_to_bytes`, plus the original SET_BUFFER/HW_PARAMS assignment slices and
four physical-format initializers. Their exact source fragments and hashes are
retained in `oracle-source.json`. Minimal host scaffolding supplies runtime/DAI
context and parameter accessors; hardware fallback calls abort and are never
executed by valid vectors. Private format lookup indices are test indices, not
asserted ALSA or firmware ABI IDs. No hand-written replacement calculation
stands in for the source pointer functions.

The first sanitized link with system GCC failed because its scripts refer to
missing `/usr/lib64/libasan.so.8.0.0` and `libubsan.so.1.0.0`; that complete failed
capsule is preserved. Existing NDK27 Clang18 supplies native
`x86_64-unknown-linux-gnu` runtime archives; their actual paths/hashes and link
plan are recorded. Android runtime archives are not substituted into glibc.
No package or toolchain was installed.

The measured host pass contains 380,513 assertions: 1,920 valid configurations,
122,880 differential pointer calculations against genuine source and 40,000
mutations. Explicit cases cover signed/high IOVA fields, truncated/misaligned
snapshots, period/count/extent bounds, stale/duplicate notifications and leases,
Stop/error transitions, CLOSED-with-owned-buffers, provider-fence gating and
counter exhaustion. Deliberate heap overflow and signed overflow controls both
produce actual ASan/UBSan diagnostics and nonzero termination. Four real target
objects cover adapter and genuine declaration assertions for AArch64 ELF64 and
arm64 Mach-O. This is compile-only ARM evidence.

All compiler jobs and tests run sequentially with owned-session cleanup,
20-second command deadlines and a sampled 256 MiB total owned RSS budget. The
initial passing run peaked at 126.984375 MiB. No heavy build lease is used.
Final commit-bound measurements and artifact hashes are in `evidence.json`.
Main common checks and acceptance remain the coordinator's review step.

## Board provenance and unavailable native inputs

The E1S common source declares two CS35L43 devices on enabled `hsi2c_9`, at
addresses `0x40` (`cs35l43_r`, `cs35l43-bot`, Right AMP SPK → SPEAKER) and `0x41`
(`cs35l43_l`, `cs35l43-rcv`, Left AMP SPK → RECEIVER). It names ABOX as the PCM
front end and describes amplifier/codec routes. The SoC source supplies ABOX
IOMMU/reserved-memory/IPC-region declarations, CA32 cores, `calliope_sram.bin`,
`calliope_dram.bin`, `abox_solution.conf` and `abox_system.conf`. CS35L43 code
has its separate wm_adsp/firmware/coefficient requirements.

These are public source declarations. Exact BYH3 firmware bytes, selected
overlay/topology/configuration, fitted amplifier/calibration state, real DMA
mapping/coherency/quiescence and actual speaker/microphone operation are not
qualified. No PCM0-to-speaker route is inferred from this host component.
Private iOS audio services/ABI and the full XNU/native adapter remain unavailable.
The original source notices stay intact: ABOX/PCM headers/drivers GPL2-or-later,
PCM misc Library GPL2-or-later, and per-file GPL2-only codec/DTS/macro notices.
No blanket project license replaces component terms.

## Reproduction

From this worktree, with a new output directory:

```sh
python3 src/platform/audio/host/source.py \
  --repo /home/egor/dev/pet/s24-ios-exynos/references/s24-linux \
  --cache artifacts/audio-host/source-session1
python3 src/platform/audio/host/check.py \
  --cache artifacts/audio-host/source-session1 \
  --out artifacts/audio-host/NEW-check
```

Source blobs, failed acquisition/link evidence, generated oracles, compiler/test
commands, diagnostics, resource JSONL and target objects stay under this
worktree's `artifacts/audio-host/`. Shared-registry links use the
`worktrees/aud-003-20261105/` prefix. No phone/ADB, root, MMIO, real PCM
playback/capture, firmware loading, native hardware or Apple compatibility
qualification is authorized or reported here.
