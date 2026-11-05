# CELL-010 handoff

2026-11-05. Owner `codex-ril-inputs-20261105-m`, main checkout. This turn made progress by implementing/testing a narrow collector and measuring the exact live vendor-file acquisition boundary. Actual file contents remain unavailable; CELL-010 acceptance is incomplete. No phone writes, root request, settings/connection changes, installs, reboot, modem request, subscription operation or RIL execution occurred. Daily Android was not replaced.

## Implemented

tools/research/ril-capture/capture.py permits only literal model/device/build, uid, bounded regular-file stat/checksum and normal ADB pull operations for five named vendor libraries. It snapshots itself per run and records actual redacted commands/exits/log hashes. Fresh exact-target inventories and private0700/0600 artifacts retain provenance; raw enumeration serials are never saved. Wrong identity, ambiguous reference metadata, bad architecture, nonregular/unbounded files, changed digests/identity and mismatched duplicate sync reads are rejected.

Eight synthetic local-peer guard groups pass; they are host tests only. Original remote-checksum verification remains the default. The optional normal-sync verification mode was added after a measured shell denial and requires two independently retrieved full files with equal size/local SHA256, with unavailable remote SHA256 fields left null. This does not compute a signed-stock attestation or change device permissions. It failed to acquire actual contents here as well.

## Actual attempts

| Experiment | Command/action | Exit / outcome | Evidence |
|---|---|---|---|
| RILINPUT-001 | capture.py --run byh3-session1 | 1 / inconclusive | Three endpoints; stopped before properties/files |
| RILINPUT-002 | adb devices -l with a strict unique-USB metadata selector | enumeration0, selector1 / inconclusive | No usb tag advertised; byh3-session2 collector never launched |
| RILINPUT-003 | capture.py --run byh3-session3 --select-reference | 1 / inconclusive | One matching model/device entry; actual BYH3 properties and uid2000 verified; shell SHA256 denied |
| RILINPUT-004 | capture.py --run byh3-session4 --select-reference --verify-sync-reads | 1 / inconclusive | Same target rechecked before/after; normal ADB sync pull also denied |

Script commands use python3 tools/research/ril-capture/capture.py. Immutable state/evidence/RILINPUT-001.json through004 bind the exact actual runs and sanitized public reports. The initial RILINPUT-001 evidence registration was rejected for missing the mandatory device_inventory field; before successful registration it was corrected to identify earlier DEV-001 context explicitly, without pretending a new selected-device observation.001/002 use that contextual inventory;003/004 use fresh actual property inventories. No registered evidence was rewritten.

A metadata-only enumeration review identified one exact-model entry and two differently tagged emulator entries; it did not save serials or infer the actual transport from missing usb tags. All library access then used explicit selection plus actual property checks. No default emulator target or assumed endpoint identity was used.

Actual regular file metadata: /vendor/lib64/libsec-ril.so is5459848 bytes and /vendor/lib64/libsecril-client.so is134368 bytes. The other three allowlisted candidate filenames returned no such file. Both SHA256 reads and normal pull returned Permission denied for existing files. No proprietary file bytes, digest, ELF architecture, symbol or command-layout claim follows from metadata. No claimed whole-device absence or automatic root requirement follows from the narrow check.

## Next action

Stop this acquisition branch at the measured boundary; do not retry with root, permissions/SELinux changes, injected helpers or alternate privileged services. An explicitly supplied matching local RIL or BYH3 vendor-image artifact can unblock CELL-009 offline work independently of live access. The optional existing-local-input question has no supplied path yet. No firmware archive download is authorized by this task.

CELL-009's input handoff is docs/procedures/ril/handoff.md, with minimal machine-readable metadata at fixtures/public/ril-capture/offline-input-handoff.json. No matching binary was analyzed. BaseMirror's documented Ghidra9.2.2/JDK11 environment is not qualified on the current host's JDK25. A command decoder/model remains distinct from real modem behavior. Other independent host tasks remain available; neither this blocked acquisition nor task count completes the overall goal.

## Verification

After final registry updates, make check passed132 tests plus registry, board and capability checks. The log is artifacts/ril-capture/byh3-session4/make-check.log; its hash and final code/test digests are in fixtures/public/ril-capture/final-checks.json. Keep all four inconclusive device outcomes alongside host guard results. Original KRN-001/KRN-003/ESIM-004/NAT-001 ownership, implementation and native capability state remain unchanged. Only passive reads were issued; no native recovery or automatic phone-control claim was advanced.
