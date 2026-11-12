# Template for the NAT-078 decision: one native run that delivers the padded root image into RAM and has PID 1 hash it

Status: TEMPLATE written by NAT-079 (host-test; nothing was run on the phone). It is not a decision. NAT-078 turns it into `docs/decisions/00NN-nat078-...md` after it has re-checked every hash below against its own files, re-checked the sender, companion, session-driver and analyser hashes in section 2 (filled from the NAT-080 evidence, recorded in the commit that completed NAT-080), and committed the file before any device access (decision 0019 protocol: one image per decision file, RECOVERY only, restore from the pinned stock). The owner's standing statements of 2026-11-12 (decisions 0025, 0026, 0029: runs of this kind are launched without a question) apply; this template does not widen them.

It replaces the staged-mode statements of `docs/procedures/nat-077/decision-draft.md` (section 4 and section 8, last two bullets): NAT-079 judged the staged copy not workable at this point of the boot (see the README, "Direct versus staged": the loader runs with the MMU off and the engine's staged copy is a byte-granular `mcopy` loop; this is an engineering judgement, not a measurement), so the receive phase is **direct DMA into the reserve**. Sections 1, 3, 6 and 7 of that draft are kept; the pass table is restated below with the loader and companion outcomes that NAT-079/NAT-080 added.

## 1. The question

> Can the host stream the whole padded root image over USB bulk-OUT straight into the reserved md1 region before the jump, and does the payload kernel's `/dev/rmd1` then return exactly those bytes to a user process (MMU on, kernel-side read)?

Reported separately: (a) delivery (loader side: NAT-076 engine, NAT-079 receive phase), (b) host-to-device rate, (c) read-back through the kernel (NAT-077 hash probe), (d) whether the DWC3 DMA reaches the reserve above 4 GiB (NAT-040 item U5; the first accepted chunk answers it).

## 2. The image and its inputs (hashes of the host-test build; NAT-078 re-checks them)

| item | value |
|---|---|
| RECOVERY image (`recovery.img`, 100,663,296 B) | SHA-256 `d95024989a2cc8cd96c39a10bf9c4c33552047c36dc0c2618b88dcfef10c02ef` (`artifacts/nat-079/package-002`) |
| pinned stock RECOVERY, restore source | SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` |
| `Image.payload` (21,956,576 B, offset 2048) | SHA-256 `95aec19a75594a89378f79fe372bf67db1301667073ceef3036a61ad59520512` |
| loader image | SHA-256 `713b0330c487b6e0ad88e4996dabf206d135bd6fce8fd1c5ee446e87d5109442` |
| md0 = PID 1 = NAT-077 hash probe (16,635 B, static arm64 Mach-O, ad-hoc signed) | SHA-256 `dc5c7845b3856274b0c8b5519f5b2a726c595de5410cb6cfa818fe0645a258b7`; it replaces NAT-065's probe-init through `build.py --ramdisk` (build record: `nat079_ramdisk`) |
| root image, padded, 2,475,720,704 B = 0x93908000 = 151,106 pages of 16 KiB | SHA-256 `552800ff3ac3de129b550c838681d0cb1d08cc4df0d38b2dc1088a9b258a8258` (`artifacts/nat-077/padded.json`; the donor image before padding is 2,475,712,512 B, `6304b2c5…`) |
| sender | `tools/ios/root_send.py` SHA-256 `a07b9ba94a2b5c37723cac76439a305669d4825042d2e2c520e76a66b83e69ef` |
| delivery companion | `docs/procedures/nat-080/deliver_nat080.py` SHA-256 `dfa65d66378e5bc2701b92e268c4ccb46b753b3074e120bc98df540d6c79fbf6` |
| session driver | `docs/procedures/nat-080/session_nat078.py` SHA-256 `d4c1a99b22137ed48e5d23d1fcad86e020b3bddab012a3044d28ebde04987c2b` (derived from `session_nat075.py`; `derive.py --check` is exit 0) |
| analyser | `docs/procedures/nat-080/analyze_nat080.py` SHA-256 `88774a55870c4da37fe507bd05488f319f69e8022b52b06f86e2491e20964766` |
| loader source | NAT-074 chain (NAT-065 / NAT-052 / NAT-047 sources, GPL-2.0, base SHAs in the build record) + `docs/procedures/nat-076/engine/` + `docs/procedures/nat-079/{make_variant79.py,src/}` |
| kernel command line | NAT-067's line with `nat_attempt=NAT078-rx1` and `loader_return_after=45`; `rd=md0`, `e1stouch=0 e1sbattery=0`, `serial=3`, `debug=0xc`, `launchdsuffix=release`, `cs_enforcement_disable=1` as in NAT-075 (`nat079_cmdline_append` in the build record) |

The probe prints on the console ring the host already reads (NAT-068):

```
*** SWEET hash probe: init running as PID 1 ***
SWEET hash: reading /dev/rmd1 in chunks of 131072
SWEET hash: at=<bytes> sha256=<hex of the first <bytes> bytes> sec=<s.mmm>     (every 128 MiB: 18 lines for 2.31 GiB)
SWEET hash: bytes=<total> sha256=<hex> sec=<s.mmm>
SWEET probe: done, exiting                                                      (exit status 81)
```

Exit classes: 0x60 no console, 0x61 `/dev/rmd1` cannot be opened, 0x62 a read failed, 0x63 empty device, 81 success for PID 1.

## 3. Timeline and the rules that bind it (all checked by `build.py` and by `derive.py --check`)

| quantity | value | rule |
|---|---|---|
| NAT-044 hard deadline D (the run's length: the loader holds until it) | 360 s | `D >= R + N + 60`, `D <= 600` |
| receive cap R (loader seconds, from the moment RX_BEGIN can be accepted) | 240 s | `0 < R <= 580` |
| kernel free run N (`loader_return_after`) | 45 s | `8 <= N <= 63` (the kernel runs unpetted; watchdog about 83 s, 20 s margin) |
| watchdog pet | every 30 s, from `nat044_tick()` in every round of the receive loop and from `nat074_pet` | NAT-074 rule: pet + 20 <= 83 |
| progress line | every 10 s: `NAT079 rx MiB=<n> trbs=<n> err=<n> t=<n>s` | on the loader's log ring |
| companion: wait for the device to be ready | 300 s | the engine comes up about 27 s after the reboot request in NAT-075 |
| companion: delivery cap + margin | 225 s + 15 s | `225 + 15 <= R = 240`: the host stops sending before the loader gives up |

Rate needed: 2,475,720,704 B / 225 s = **11.0 MB/s** (10.5 MiB/s) to deliver within the companion's cap, 10.3 MB/s within the loader's cap. No host-to-phone rate has been measured on this device; the real number is part of the finding. The hash needs 2.31 GiB / (45 s - boot to PID 1) of kernel time; at 55 MB/s or more the whole digest can finish inside N = 45 s; below that the digest stops at some progress line (row 3a) and the prefix digests still verify what was delivered.

The cable stays connected for the whole run (the run needs USB both ways: the log chain and the stream); the phone has no other host.

## 4. Sequence

1. Host (before anything is sent to the phone): confirm the Android check (`check_android.py`), the RECOVERY slot hash against the pinned stock, the Download Mode path of NAT-013 as in decision 0029. Start the collector (NAT-041 `s24_logd.py`; vendor requests 0x01..0x05 on EP0 only), then start the delivery companion **detached and confirm its `loaded` record in its journal**, then issue the single `adb reboot recovery`. The driver exits after the reboot; the companion runs on its own and never touches the reboot.
2. Loader: engine up with a 512-byte placeholder destination (`NAT079_HOLD_BYTES`), the window/ELF/ADT work as in NAT-075, then `nat079_receive_root()`: validate arguments, refuse if host traffic arrived before the destination was real (`PREMATURE`), CPU self-test of 8 pages of the reserve (a failure refuses the stream: RX_BEGIN stays impossible because the capacity the host sees stays 512 B), install `rx_dest`/`rx_size`, loop `nat044_tick(); nat047_poll();` until `rx_committed == bytes` (`DONE`), the cap (`TIMEOUT`) or the engine going down (`ENGINE_DOWN`). `DONE` means the device's committed offset equals the size and the byte counters agree; it does not mean the bytes were verified.
3. Companion: polls `GET_RX` with the device unconfigured (EP0 only). It sends nothing until the engine reports PRESENT, capacity equal to the root size, committed 0, state IDLE; the 512-byte placeholder means "wait", anything else means "refuse" (exit 5). Then it configures the device once and runs `root_send.send()` through the metered transport: checked chunks (per-chunk checksum `sum += word * (2 * i + 1)`), resume from the device's committed offset after a failure, bus resets survived by reconnect. The first accepted chunk is the answer to U5; a failure there leaves `committed = 0` and the device's `last_trb_status`/`last_evt_status` in the `GET_RX` record.
4. At `DONE`, at the cap or at engine-down, the loader pets, flushes the log, cleans the caches over the window and jumps to the payload kernel (it boots whatever the receive result was). PID 1 = the hash probe reads `/dev/rmd1`. After N seconds the kernel returns to the loader, which dumps the console text for the host.
5. The host collects the text through the existing log chain (the collector never writes to the phone), the analyser classifies the run, the restore follows decision 0029 (NAT-013 with the pyusb venv python `artifacts/recovery-rescue-20261110-01/venv/bin/python`), then the Android check.

## 5. Observables

1. **Device-reported delivery**: `GET_RX` `committed`, `rx_bytes`, errors, dups, gaps, rejects, resets, aborts, `last_sum`, read by the companion while the loader runs, and the loader's own `nat079_*` values after the receive phase (`nat079_status`, `nat079_committed`, `nat079_rx_bytes`, `nat079_trbs`, `nat079_errors`, `nat079_resets`, `nat079_dups`, `nat079_gaps`, `nat079_rejects`, `nat079_aborts`, `nat079_last_sum`, `nat079_elapsed_ticks`, `nat079_freq`, `nat079_selftest_bad_pa`). The sender reports the device's committed offset at the end, never its own count.
2. **Rate**: the companion's progress journal (`delivery.jsonl`): bytes, host monotonic seconds, MB/s and MiB/s, plus per-chunk times.
3. **Read-back**: the probe's lines above; the host recomputes `sha256(image[:at])` for every `at` and the whole digest.
4. **Page size and memory** from the kernel text (as in NAT-075), **the ending** (`cap-reset`, `upload`, other).

## 6. Pass rule, fixed before the run

Let `N = 2,475,720,704` and `H = 552800ff…8258`. A result other than PASS is evidence, not a reason to run again.

| # | Observation | Meaning | Decision |
|---|---|---|---|
| 1 | **PASS**: device `committed == N`, loader `nat079_status == 0`, errors zero or every error recovered with a matching `committed`; probe final line `bytes=N sha256=H`; every progress line equals the host's prefix digest; exit 81; ending `cap-reset` (Download Mode in the NAT-075 window) | a full-size root is in RAM and the kernel reads it back unchanged; the rate is measured; U5 is answered (the DMA reaches the reserve) | next: a task to mount APFS from md1 in the payload kernel, then dyld and launchd |
| 2 | digest mismatch with `committed == N` | the bytes changed between the engine's checksum-verified commit and the kernel's read: cache coherency of the direct DMA (the loader's final clean covers the window but a dirty stale line from the self-test or the placeholder could win), a second writer, or a wrong md1 base | the first differing progress line localises it to 128 MiB; a finding, not a pass |
| 3 | `committed = X < N` (companion exit 3 `cap-reached`, loader `TIMEOUT`), every progress line with `at <= X` equals the host's prefix digest | the path is correct and the rate is the limit | rate and X are the finding; a delivery that fits needs a different budget (longer cap with kernel keepalive, compressing the zero-rich image, a smaller root) |
| 3a | `committed == N`, digests of all printed progress lines equal the host's, but no final line, ending a timed return (not `upload`) | delivery verified up to the last `at`; the hash was slower than N | the last `at` and its `sec=` give the device hash rate; a longer N (up to 63) or NAT-071 |
| 4 | progress lines stop before the end and the ending is `upload` (SEC_UPLOAD) | the unpetted watchdog ended the run | NAT-071 becomes mandatory; `loader_return_after` was too long for this kernel |
| 5 | `0x61` (cannot open `/dev/rmd1`) | the node name differs (the kernel text says what md1 is called) | fix the name; not a pass |
| 6 | `0x62` read failure | `mdevrw` rejected a read | errno in the console line |
| 7 | the device never becomes ready (companion exit 4), is refused (exit 5) or the first chunk fails with `committed = 0` (loader `NOT_PRESENT`, `NO_ENGINE`, `ENGINE_DOWN`) | the NAT-076 engine did not come up on the real controller, or U5 is false: the PMMU in front of DWC3 DMA does not map the reserve | `last_trb_status`, `last_evt_status` and the loader status are the finding; no retry in the same run |
| 8 | anything else | | the first panic or loader line is the finding |
| 9 | loader `SELFTEST` (with `nat079_selftest_bad_pa`), `BAD_ARGS`, `PREMATURE` or `INCONSISTENT` | the loader refused or distrusted the receive phase; the stream was not accepted or not trusted | the status and the address are the finding; read-back results are void |
| 10 | companion digest check: the device's last checksum differs from the sender's (`DeliveryError`) with the same chunk repeated 5 times | a data path fault (device-side write, or cache), localised to one chunk | the chunk offset is the finding |

## 7. What a PASS does not say

That APFS mounts, that the volume is consistent, that dyld or any Apple binary runs, or anything about display or GPU. It says only that a full-size image can be placed in RAM over USB and read back unchanged by a user process of the project's kernel. The probe is not Apple's launchd. Evidence category of the run: native-device. Everything before it (NAT-076, NAT-077, NAT-079, NAT-080) is host-test.

## 8. Preconditions NAT-078 has to meet before this becomes a decision

* NAT-079 and NAT-080 are `done` with `evidence.json` outcome pass; the hashes in section 2 are recomputed from files, not copied.
* `python3 tools/lab.py board` shows no other active task on `native`; the `native` permit is opened citing the decision and closed after the run; `task done NAT-078` before the permit is closed.
* The pinned-stock restore (NAT-013, pyusb venv python) and the Android check after the run, exactly as in decision 0029; Android, data and settings untouched.
* Android properties and the device state are read before the reboot with the ordinary ADB checks; no `su`, no partition other than the test RECOVERY slot `/dev/block/sda18` is written.

## 9. Deviations from the registry text of NAT-078, to be recorded in its decision

* "4908 MiB window": the loader refuses `mem_size > 4 GiB` (NAT-075). The window is 4096 MiB.
* "md0 on it": md0 stays the 16 KiB-class probe ramdisk (`rd=md0` is how the kernel finds PID 1); the root image goes to the reserve-only `md1`/`rmd1` registered in NAT-075. The probe reads `/dev/rmd1`.
* "staged" mode of the NAT-077 draft: direct DMA instead (README, "Direct versus staged"). Consequence: U5 is tested by the first accepted chunk of the real run rather than avoided; the staged fallback stays in the engine (`rx_direct = 0` is a build option) if U5 turns out false, and that is a rebuild and a new decision file.
