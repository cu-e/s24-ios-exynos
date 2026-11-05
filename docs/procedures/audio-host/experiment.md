# AUDIOHOST-001: pinned ABOX PCM source and bounded host ownership

Date: 2026-11-05. Owner: codex-team-audio-host-20261105-bh. Task: AUD-003.

Use only public source at selected E1S Linux commit
`417484173abc2c4fa93e738ea82ad9f2e84911b1`. Inspect actual ABOX IPC/PCM/DMA
headers and drivers, board DTS routing and CS35L43 declarations. Shared references
and prior artifacts remain read-only; every Git child uses GIT_NO_LAZY_FETCH=1
and GIT_OPTIONAL_LOCKS=0. If a selected blob is absent, fetch its primary raw
text into this worktree's artifact cache and verify the exact tree Git blob ID
plus SHA256 before reuse. Preserve component license notices.

Before implementation, trace genuine field layouts, byte/frame/sample units,
ring/period calculations, direction and channel boundaries, notification and
Stop/close/error paths. Keep public declarations distinct from unavailable exact
BYH3 firmware, fitted amplifier/routing and actual speaker/DSP behavior.

Implement one narrow host-only C admission/ownership boundary. Do not transmit
DSP commands, synthesize firmware behavior, access MMIO, load firmware, play or
record audio, select a phone/ADB, invoke root or claim private Apple/native ABI.

Compile an independent oracle against actual selected donor declarations and
source calculations, retaining its provenance and any minimal host scaffolding.
Exercise genuine valid vectors and adversarial extents/overflow, stale callback,
duplicate/error/Stop ownership cases. Run actual ASan/UBSan tests with independent
instrumentation-failure controls and compile real AArch64 ELF/Mach-O objects.

One small compiler job at a time, <=256 MiB new RSS; finite per-command timeout
and owned-process cleanup. No heavy build lease. Record actual commands/exits,
source/tool/object/artifact hashes and dated evidence/handoff. Passing this host
preparation does not complete native AUD-001 or establish audible/captured output.
