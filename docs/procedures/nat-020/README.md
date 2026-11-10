# NAT-020: 83-second diagnostic candidate, 2026-11-10

Evidence category: host-test. This procedure does not flash or reboot a phone.
Owner: `codex-83s-candidate-20261110-r6`, primary checkout, branch `main`.

The owner amended the requested watchdog timeout to 83 seconds. `build.py`
derives a separate candidate from NAT-006 build-002 source, the exact STR-041
linked kernel and the NAT-010 entry/cache changes. Original artifacts remain
unchanged. Source licenses remain in the copied source; the watchdog and guard
are GPL-2.0-or-later, and the loader is GPL-2.0-only.

Accepted host candidate:

- `artifacts/nat-020/build-003/recovery.img`, exactly 100663296 bytes;
- SHA-256 `b5ff3bf7e4d6bcd36cc518fbc4ab0daaaf8a1985056a65708f60b51f4f9a6a49`;
- actual emitted guard calls `s5e_wdt_arm(...,83)` once, without pet/disarm;
- nominal timeout 83.000850 seconds at the uncalibrated 25.6 MHz clock;
- 29 entry stubs disable the E1S UFS driver, Redwood UFS/mailbox entry points
  and the separately linked UFSHC probe/switch/read paths. Each emitted stub is
  a register-only return sequence. Mach-O layout and all other bytes are kept;
- explicit `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0`
  arguments. No native filesystem is attached to the internal storage. There is
  no RAM-root filesystem in this payload, so reaching root selection may panic;
  this is a kernel diagnostic, not an iOS userspace boot;
- reject SCTLR_EL1.M/C before stack/BSS/high-DRAM access; clean the complete
  selected 512 MiB RAM window and the loader before final cache-off/handoff.

Containment is static entry-point denial, not hardware memory isolation. It
does not prove that an arbitrary kernel/firmware fault could never damage state.
The previous experiment looped; this candidate does not establish automatic
return to Android. A manual Download Mode/stock restoration may be necessary.

## Diagnostic coverage

The loader initializes its image-owned RAM log after stack/BSS initialization,
before the watchdog guard and DTB validation. It records timer ticks, reason
before/after, watchdog registers/decrement, 16 MiB clearing progress, cache-clean
boundaries and the entry address returned to assembly. Existing exception
records retain vector slot, ESR, ELR and FAR. The bounded log now counts discarded
characters with saturation instead of silently dropping them. The handoff marker
explicitly says it is not proof of XNU entry.

**This is not a qualified early log channel.** There is no native USB transmitter
or connected UART receiver. Logs before safe stack setup are absent; loader RAM
and the kernel's separate RAM ring have no proven reset retention or host read
path. The owner was informed of this before selecting 83 seconds. NAT-017 remains
unqualified. Do not describe this image as preserving all logs across reset.

`observe_usb.py` passively reads sysfs and creates a fresh exclusive file for
each enumeration transition. Each event and its directory are fsynced. It never
opens USB devices or records serial numbers. Host USB events are not CPU-stage
or kernel execution evidence. For a real run use a new directory and a bounded
duration; the existing NAT-016 collector is still available for a real native
producer when one exists.

## Checks and failed host preparations

`build-001` stopped on the expected resolved Linux Image header relocation being
incorrectly treated as a C absolute relocation. The corrected check requires that
one exact assembly-header relocation and rejects every absolute C relocation.
`build-002` produced an image but failed the independent restore check because
the builder omitted `SHA256SUMS`. `build-003` supplies and checks the manifest.
No failed build was used on the phone.

The independent NAT-006 verifier is copied locally with precisely two pinned
identity substitutions: the derived kernel digest and the exact new command
line. All structure, segment-byte, restore and runtime-FDT checks are retained.
All 20 checks pass, including the selected range
`[0x9de400000,0x9fe400000)` and stock framebuffer exclusion. `inspect_binary.py`
uses Capstone independently of the compiler to check the real stubs, the guard's
83-second argument and entry rejection before stack use. All C objects have zero
absolute relocations. Commands, exit codes and source/binary digests are local in
the build report.

The read-only ADB binary-stdin control streamed all 100663296 candidate bytes
through the phone's Toybox `dd` into `sha256sum`, with no output file. Its digest
matched. Toybox supports `iflag=count_bytes`; `iflag=fullblock` was not assumed.
The preflight still observes boot-completed Android and the exact stock RECOVERY,
with target `/dev/block/sda18`, size 100663296, battery 84%, temperature 29.8 C.

Reproduce in a **new** output directory:

```sh
python3 -I docs/procedures/nat-020/build.py --out artifacts/nat-020/NEW
artifacts/recovery-rescue-20261110-01/venv/bin/python -I \
  docs/procedures/nat-020/inspect_binary.py --build artifacts/nat-020/NEW \
  --out artifacts/nat-020/NEW/binary-review.json
```

Phone execution and return assessment belong to a separate native-device task.
The stock fallback is the unchanged 96 MiB original, SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`.
Its Odin tar has exactly one `recovery.img` and SHA-256
`2787aa3e07d1f09d5f2c808166e0640719f111a618105ceed1ef67ea721fe84e`.
Use NAT-013's fixed-stock tool in one fresh physical Download Mode entry if ADB
does not return. Never use the retired modified Odin4, resume a used session,
write another partition, or select a data-reset action.
