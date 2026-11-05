# SEN-001 handoff

Owner: `codex-team-sensors-20261105-al`; branch `team/sen-001-20261105`; worktree `worktrees/sen-001-20261105`. Task remains in progress until coordinator acceptance and integrated common `make check`.

Pinned input: `s24-linux` full SHA417484173abc2c4fa93e738ea82ad9f2e84911b1, reviewed through exact read-only Git objects from main `references/s24-linux`. Every reviewed file and tool has a SHA256 in each qualification capsule. `src/platform/sensors/README.md` gives source paths, contracts, identity namespaces, licensing and exact missing proprietary/native inputs.

Changes are confined to the two reserved directories. Bounded allocation-free C parsers accept complete SHUB accel/gyro bypass batches and KEPLER GNSS single frames. No raw-to-SI scale, sensor mounting, fragment reassembly, firmware commands, location fix or private Apple ABI is guessed. SHUB clamps future effective timestamps to boot-time receipt while retaining raw time. GNSS body and padding remain opaque. Unavailable services fail explicitly, and invalid batches publish no output.

Existing device inventory additionally advertises STK6D2X Rear ALS, omitted from DEV-001's summary table; all seven physical-sensor entries (six named parts, accel/gyro share one) are recorded in identities.json and checked against the original capture. This is HAL identity evidence, not a new measurement or silicon ID read. KEPLER is a BSP name; GNSS chip and exact firmware stay unknown.

The GNSS struct declaration conflicts with offset macros and actual writer. The owned adapter uses explicit offsets, with genuine-header static assertions preserving the discrepancy and a differential check of all65524 valid lengths against the genuine helpers. The actual E1S DTS includes the shared-memory version, not S5400 SPI.

Experiment SENHOST-001: original parser ASan/UBSan execution and AArch64 compile passed; genuine SHUB oracle failed because the owned synthetic linux/kernel.h lacked an include guard. Failure capsule `worktrees/sen-001-20261105/artifacts/sen-001/20261105-host-001/evidence.json` preserves commands/exits/logs. No upstream source was changed. Fixed the support guard for SENHOST-002.

Passing final capsule: `worktrees/sen-001-20261105/artifacts/sen-001/20261105-host-002/evidence.json`. SENHOST-002 passed at tested commit `f6b2072` (all owned input hashes recorded): host parser ASan/UBSan executable exit0, freestanding AArch64 compile exit0, genuine SHUB declaration compile/run exit0, genuine GNSS helper differential compile/run exit0, and seven existing HAL capture identity checks. The worker did not run common main make check; the coordinator owns integration verification. The coordinator should inspect that outcome, cherry-pick owned commit(s), and run main `make check`; the checker stays local to this task boundary. Native sensor/clock/firmware/Apple-service work requires new scoped prerequisites, as listed in README. No phone/ADB/root/MMIO/flash/reboot/provisioning operation was issued.

Acceptance assessment:

| Criterion | Result | Evidence and limits |
| --- | --- | --- |
| Pinned hub/GNSS interfaces and exact sensor identities | Met for source-qualified host specification | Full upstream SHA,18 exact source snapshots and hashes; genuine prefix/constants oracle; actual E1S GNSS include path; seven exact existing HAL names/handles/types and inventory hash. BYH3 wire compatibility and GNSS silicon identity remain unqualified. |
| Timestamp, packet truncation and unavailable-service cases tested | Met for host adapter | Every SHUB/GNSS prefix (including GNSS padding), incomplete count and oversized lengths; atomic output publication; capacity; raw future/zero/max and backward batch times; distinct service-down/clock-unavailable controls. GNSS65524 valid length comparisons use genuine source helpers. |

Ready for review; leave SEN-001 in progress until the coordinator cherry-picks and validates common main checks. Integrate implementation commit `f6b2072` plus the documentation-result follow-up. No native capability is advanced.
