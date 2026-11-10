# NAT-012 stock RECOVERY rescue, 2026-11-10

Owner: codex-stock-rescue-20261110-r2. Authorization: decision 0005.
No XNU execution, repartition, format, reset, or non-RECOVERY writes permitted.

Initial observation: no odin4/heimdall process. Last saved command exited after
handshake with Failed to begin session at host log time 14:39:48; no PIT/transfer
success logged. USB bus 005/device 019; ADB absent. Owner confirms Downloading
screen. This does not establish partition content; only readback after rescue can.
An unrelated Claude ADB-wait process was preserved and not interrupted.

Both 96 MiB stock backups hash to
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
The tar hash matches 2787aa3e07d1f09d5f2c808166e0640719f111a618105ceed1ef67ea721fe84e
and contains only one regular recovery.img with matching size/hash.
The previously modified odin4 binary matches reported
0b5ee5cb13be8f6fb278c23b0f231d77d27fb4e4d0b0b34ceefb4ba0789e37f8.
Prior main/source modifications were snapshotted under the private run directory;
none were overwritten. Antigravity SQLite was read using mode=ro, without immutable
mode, so WAL is included. Credits exhaustion is confirmed in saved steps.

Independent Capstone disassembly of the saved epbl.bin supports the original
pre-BeginSession response-buffer fault: command 0x64 handler at 0x2db864;
subcommand 0 allocates 8-byte response buffer at 0x2db9c4..0x2dba04;
subcommand 1 goes to 0x2dbcb8 and response routine 0x2da62c;
null response at 0x2da684 leads to "prb is null!" and 0x2da700 infinite loop.
This explains the early query risk, not the last patched begin-session timeout.
Disassembly is local diagnostic analysis of the owner's backup, not upstream source.

Alternative transport provisioned from Fedora RPM heimdall-2.2.2-2.fc43.x86_64,
with MIT notices in its private extracted prefix. Matching upstream tag v2.2.2:
https://git.sr.ht/~grimler/Heimdall/commit/d9554e7fa30a00abed7f0ac86b10e63c2c3b8e20
Source checked out under references/heimdall-grimler-rescue. Unlike the patched
Odin tool it starts with BeginSession, uses protocol version 4 and sends the
upstream post-packet empty transfer. FlashAction matches partition by name and
sends its device type + identifier; UFS size check uses 4096-byte blocks. No
--skip-size-check, --repartition, TFlash or extra partition arguments are allowed.

Next: owner was asked to re-enter Download Mode to clear failed protocol state.
Wait for confirmation/new USB enumeration, check no concurrent flasher, then
perform download-pit --no-reboot only. Validate actual RECOVERY name/identifier,
UFS type and capacity before any write. Do not assume synthetic fixture ID 20.

## Fresh-session read-only result and authorized restore plan

Owner re-entered Download Mode; USB re-enumerated as bus005/device020.
`pit-read-001/command.json`: Heimdall download-pit --no-reboot completed exit 0.
Actual PIT has 1 RECOVERY entry: index24, binary_type0, device_type8 (UFS),
identifier18, start block75152, block_count24576 (4096-byte blocks =96MiB),
filename recovery.img. Tuple (binary_type,device_type,identifier) is unique.
The old host fixture ID20 was synthetic and must never select this device target.
The raw table and both independent decodes remain local in the run directory.

Restore command: Heimdall flash --resume --RECOVERY
`devices/recovery/backups/2026-11-10/recovery.img` --verbose --stdout-errors.
--resume follows the successful --no-reboot PIT session; default successful end
reboots the device. Only one partition argument; no PIT argument, repartition,
size-check bypass, EFS clear or other image. Full backup hash rechecked immediately
before launch. No concurrent flash process. Preserve command log and exit code.
Wait for completion without terminating an active data transfer. After success,
observe ADB/boot_completed and root full recovery hash; if stock recovery appears,
owner may select only Reboot system now. Never choose wipe/reset or side-loading.

## Stock transfer result, 2026-11-10T09:58Z

stock-flash-001 completed: RECOVERY upload successful, then session end response
repeatedly timed out (libusb -7); Heimdall exit 1. No auto-reboot confirmation.
No process remains; do not duplicate the partition write based on overall exit1.
The name-selected 96MiB stock file transfer was acknowledged by the device, but
post-boot full hash is still required. Owner asked for ordinary forced restart
(side key + volume down, release at black screen), then only Reboot system now
if stock recovery appears. No manual wipe/reset or additional flash authorized.
Next: observe Android/ADB; record exact recovery hash and user environment state.

## Manual restart failed; revised transport basis

Owner reports the boot loop remained after stock-flash-001, then manually
re-entered Download Mode (bus005/device023); no error line is visible. Android
check001 timed out (inconclusive). Do not interpret upload acknowledgement as
restored disk bytes. No second identical Heimdall flash was launched.

Read-only probe001 uses no ZLP, exact-length responses and records wire results.
BeginSession, part-size, actual PIT dump, PIT end and session end all passed;
PIT hash matches first read exactly. Begin ack is 0x00038000. This isolates a
working control transport on the current session but not the Heimdall write fault.
The original Heimdall ResponsePacket only validates response type; the rescue
transport additionally requires zero command results, confirms every chunk index,
uses exact 8-byte responses and has no empty transfers or automatic retransmits.

restore_stock.py exposes no image/partition choice: exact stock hash and size,
exact actual PIT hash, unique global identifier18, UFS8 and measured bounds.
It has no PIT write, erase, repartition, EFS-clear or boot-chain command. Each
30MiB/last6MiB sequence targets only RECOVERY; any unexpected reply stops the
attempt. 3 host guard tests pass (forbidden opcodes/targets/flags, corrupted PIT,
nonzero result). This is a changed, constrained transport attempt based on the
successful probe, not a retry of the failed executable. It resumes the confirmed
probe session and allows 120 seconds for individual flash/end acknowledgements.

## Corrected session lifecycle, 2026-11-10T10:12Z

stock-flash-002 also exited 1: all four sequence results were zero, but EndSession
timed out after 120 seconds. No reboot command was sent; no writer remains.
Both restore attempts incorrectly resumed a session after a standalone PIT
EndSession. That was the rescue agent's sequencing error, not proof of a storage
failure or a defective original image.

Further local S-Boot analysis: async initializer 0x2839b0 has one direct call site
in the code range, at Download Mode initialization 0x282af4. BeginSession handler
0x2db8c8 allocates/reset protocol buffers but does not invoke it. EndSession calls
0x283980 ->0x2dd32c, setting worker stop flag 0x931804; an empty work queue with
that flag branches via 0x2dd470 to permanent loop 0x2dd89c. The second write worker
is likewise stopped through 0x283600 ->0x2dcbdc. Thus a subsequent BeginSession
can receive/acknowledge queued data without a live worker to commit it. This is
a strong source-based explanation; a fresh-session device result must confirm it.
Private disassembly/provenance: session-lifecycle-disassembly.txt and
session-lifecycle-analysis.json under the run directory.

Owner asked to re-enter Download Mode. Do not touch the current failed session.
Next attempt performs handshake, BeginSession, PIT read/validation, stock-only
transfer, EndSession and ordinary reboot in ONE fresh session. No preliminary
standalone probe, no --resume, no second handshake between PIT and flash.
The exact image/target/bounds/flags guards remain in place. All 3 host guard tests
still pass. Full Android/root readback remains mandatory.

## Successful stock restoration and Android return

Owner confirmed fresh Download Mode entry; bus005/device024. No other writer.
stock-flash-003 ran 2026-11-10T10:13:32.647158Z..10:13:36.068790Z, exit 0.
The single session read and validated the exact same PIT, acknowledged four
RECOVERY sequences (30+30+30+6 MiB), then confirmed EndSession result0 and
ordinary reboot result0. This successful fresh-session result supports the
stopped-worker explanation of the two resumed-session failures. No other
partition, PIT, EFS, format, wipe or repartition command was sent.

ADB briefly reported recovery, then Android. android-check-002 observed early
boot (animation running, boot_completed empty) and already confirmed the full
stock RECOVERY hash; it was correctly recorded as inconclusive. Final
android-check-003 at 2026-11-10T10:14:50.957827Z passed: SM-S921B/e1s,
S921BXXS9BYH3, sys.boot_completed=1, animation stopped, current user0,
/data/user/0 and /data/app present, root full RECOVERY SHA-256
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
user-session-check at 10:15:55.635406Z further confirms RUNNING_UNLOCKED,
package/activity services present and boot_completed=1. No personal content,
account list or application inventory was read; individual apps were not audited.

Do not run another flash or experimental image. Save final evidence, record
experiment003, complete NAT-012 and disable the temporary native registry flag.
Follow-ups: NAT-013 (host restore transport/lifecycle/PIT qualification) and
NAT-014 (saved-evidence review of boot-loop return assumptions, no native test).
NAT-008/009/010 host completion must not be presented as proven XNU execution or
working watchdog return on hardware. Existing NAT-011 is a proposal, not a proven
fix; the current owner explicitly prohibits new XNU attempts.

Final host validation: `make check` completed exit0 at
2026-11-10T10:16:49.009765Z, 208 tests passed. Command/provenance and complete
output are in final-host-checks/ under the private run directory. The separate
three restricted-transport guard tests also passed after the lifecycle correction.
Device experiment003 is recorded against evidence.json; experiments001/002
retain their failed outcomes. Evidence is immutable after registry recording.
