# Draft for NAT-078: one native run that delivers the padded root image into RAM and has PID 1 hash it

Status: DRAFT written by NAT-077 (host-test, nothing was run on the phone). It is not a decision. NAT-078 turns it into `docs/decisions/00NN-nat078-...md` after it has built the image, filled every `<TBD>` below from its own build record, and committed the file before any device access (decision 0019 protocol, one image per decision file, RECOVERY only, restore from the pinned stock). The owner's standing statement of 2026-11-12 (decisions 0025, 0026, 0029: launch without asking) applies to runs of this kind; this draft does not widen it.

## 1. The question

After NAT-075 the phone has run the payload kernel with a 4096 MiB window, 16 KiB pages and a registered, **empty** `md1`/`rmd1` of 2,475,720,704 bytes. Nothing has yet put a byte into it. The question of this run:

> Can the host stream the whole padded root image over USB bulk-OUT into the reserved region *before* the jump, and does the payload kernel's `/dev/rmd1` then return exactly those bytes to a user process (MMU on, kernel-side read, user buffer)?

Three separable parts, reported separately: (a) the delivery (loader side, NAT-076 engine); (b) the host-to-device rate; (c) the read-back through the kernel (NAT-077 probe).

## 2. What the run carries (the inputs NAT-077 produced)

| item | value | where |
|---|---|---|
| root image, padded | 2,475,720,704 bytes = 0x93908000 = 151,106 pages of 16 KiB = 4,835,392 sectors | `artifacts/nat-077/system-padded.apfs` (not committed; Apple-derived) |
| padded SHA-256 | `552800ff3ac3de129b550c838681d0cb1d08cc4df0d38b2dc1088a9b258a8258` | `artifacts/nat-077/padded.json` |
| donor image (before padding) | 2,475,712,512 bytes, SHA-256 `6304b2c54d56055e8df7b2b63dcbe79a9415d860b598cb8e11bda5eed47e150f`; 8192 zero bytes appended | same record |
| probe (md0) | static arm64 Mach-O, ad-hoc signed, `hash-probe` built by `docs/procedures/nat-077/build.py`; size and SHA-256 are recorded in `evidence.json` (`artifacts.probe`) and `<TBD: the md0 hash of the final build>` | replaces NAT-065's `probe-init` as the `--ramdisk` of `mkpayload.py` |
| probe device | `/dev/rmd1` (raw device of the reserve-only ramdisk), chunks of 131072 bytes read into a stack buffer | `src/hash-probe.c` |
| kernel command line | NAT-075's line with `nat_attempt=NAT078-root` and `loader_return_after=<TBD, see section 5>`; everything else (`rd=md0`, `e1stouch=0 e1sbattery=0`, `serial=3`, `debug=0xc`) unchanged | `docs/procedures/nat-075/` |
| host-side check of the probe | 4-layer tests: host build over known files, the real Mach-O under Unicorn, file format, refusals | `test_nat077.py` |

The probe prints, on the console ring that the host already reads (NAT-068):

```
*** SWEET hash probe: init running as PID 1 ***
SWEET hash: reading /dev/rmd1 in chunks of 131072
SWEET hash: at=<bytes> sha256=<hex of the first <bytes> bytes> sec=<s.mmm>     (every 128 MiB: 18 lines for 2.31 GiB)
SWEET hash: bytes=<total> sha256=<hex> sec=<s.mmm>
SWEET probe: done, exiting                                                      (exit status 81)
```

Exit classes: 0x60 no console, 0x61 `/dev/rmd1` cannot be opened, 0x62 a read failed (the kernel panics with that status), 0x63 empty device, 81 success for PID 1.

## 3. The observables (all collected by the host; no camera)

1. **Device-reported delivery** (NAT-076 `GET_RX`, read by `tools/ios/root_send.py` while the loader is still running): `committed` offset, `rx_bytes`, `rx_errors`, `rx_dups`, `rx_gaps`, `rx_rejects`, `rx_resets`, `rx_aborts`, `last_sum`. The sender prints the *device's* committed offset at the end, never its own count.
2. **Rate**: host monotonic clock around the sender, `rx_bytes / seconds` (reported as MB/s and MiB/s), plus the per-chunk times from the sender log. Reported separately for the self-test span (section 4, step 2) and for the bulk.
3. **Read-back**: the probe's progress and final lines from the kernel message buffer / console ring (the same dump NAT-068 used). The host recomputes `hashlib.sha256(image[:at])` for every `at` and the whole-image digest and compares.
4. **Page size and memory** after `md0`/`md1`: `vm_page_bootstrap` free and wired pages from the kernel text (NAT-075's reading), so that the 1.61 GiB left above the reserve is visible.
5. **The ending**: `cap-reset` (Download Mode at the NAT-075 window), `upload` (SEC_UPLOAD), or other, as in decision 0029's table.

## 4. Sequence (what NAT-078 builds; the host does the sending)

1. Loader: NAT-041's engine replaced by NAT-076's (`docs/procedures/nat-076/engine/usbmon.c`), `rx_dest` = the md1 reserve, `rx_size` = 0x93908000, **staged** mode (the default; `direct` only if NAT-040 item U5 is resolved, which it is not). The loader pets the watchdog on the NAT-075 schedule while it waits for the transfer.
2. Host: `pyusb` enumerates `1209:0001`, sends `SET_CONFIGURATION(1)` (the NAT-041 collector never does; the endpoint exists only after it) and streams the image with `tools/ios/root_send.py` in checked chunks. Nothing is skipped or reordered for a rate test: the first 64 MiB are simply timed separately from the rest, so a rate estimate exists even if the transfer is cut. The sender does not abort early; it ends at `committed == N` or at the delivery deadline, and a deadline end is a partial delivery (section 6, row 3).
3. At the delivery deadline or when `committed == rx_size`, the loader pets and jumps to the payload kernel; the kernel boots with `rd=md0`; PID 1 = the hash probe reads `/dev/rmd1`.
4. The host collects the console text through the existing USB log chain; the sender has finished before the jump, so USB roles do not overlap.

## 5. Budgets, with what is known and what is not

Known (host-tested or measured earlier): image 2,475,720,704 bytes. NAT-075: the loader's cap is 150 loader-seconds with pets every 30 s; Download Mode appeared at +165 … +195 s after the reboot request; a loader second is 0.95–1.0 host seconds; the hardware watchdog ends an *unpetted* run at about 83 s (runs 001–009: SEC_UPLOAD at +95 s ± 10 s).

| quantity | value | consequence |
|---|---|---|
| rate needed to deliver in D loader-seconds | 2,475,720,704 / D: **24.8 MB/s for D = 100 s**, 20.6 MB/s for 120 s, 41.3 MB/s for 60 s | no host-to-phone rate has ever been measured. USB 2.0 high-speed bulk is at best about 40–48 MB/s in practice; the engine in staged mode DMAs 512-byte packets into a 64 KiB loader block and copies every chunk to the destination with the CPU, so the real number is the finding |
| hash time on the host | 6.6 s for the padded image (x86-64, same C file, 373 MB/s) | no information about the S24's CPU at that point of the boot (clock, caches) |
| hash time budget on the device | the kernel is unpetted after the jump: boot to PID 1 plus the hash must fit in about 83 s unless NAT-071 (kernel-side keepalive / timed return) exists | at 2.31 GiB, **30 MB/s** is the floor for hashing alone to fit in 83 s; the progress lines show the real rate after the first 128 MiB even if the run is cut |
| `loader_return_after` | NAT-075 used 8 s, which would end a hash that needs tens of seconds | NAT-078 must set it from the NAT-075 kernel timeline plus a hash estimate, or make the return conditional on the probe's exit (NAT-071). `<TBD>` |

About 1.6 GiB of RAM is left above the reserve (decision 0029: 1661 MiB above `boot_args`); this run does not touch it.

## 6. Pass rule, fixed before the run (an analyser reads these; it is not changed after)

Let `N = 2,475,720,704` and `H = 552800ff…8258`.

| # | Observation | Meaning | Decision |
|---|---|---|---|
| 1 | **PASS**: device `committed == N`, `rx_errors == 0` or every error recovered with a matching `committed`; probe final line `bytes=N sha256=H`; every progress line equals the host's prefix digest; exit 81; ending `cap-reset` (Download Mode in the NAT-075 window) | a full-size root is in RAM and the kernel reads it back unchanged; the rate is measured | next: a new task to mount APFS from md1 in the payload kernel, then dyld and launchd |
| 2 | digest mismatch with `committed == N` | the bytes changed between the engine's checksum-verified commit and the kernel's read: cache coherency (staged copy not cleaned/invalidated), a second writer, the kernel clearing the reserve, or a wrong md1 base | the first differing progress line localises it to 128 MiB; a finding, not a pass; analyse with the prefix lines before any re-run |
| 3 | `committed = X < N`, every progress line with `at ≤ X` equals the host's prefix digest | the path is correct and the rate is the limit | the rate and X are the finding; a delivery that fits needs a different budget (longer cap with kernel pets, compression of the zero-rich image, or a smaller root) |
| 4 | progress lines stop before the end and the ending is `upload` | the unpetted watchdog ended the run: the hash was slower than the budget | the last `at` and its `sec=` give the device-side hash rate; NAT-071 becomes mandatory |
| 5 | `0x61` (cannot open `/dev/rmd1`) | the node name differs in this kernel (the kernel text says what md1 is called) | read the NAT-075 kernel text for the registered name; fix; not a pass |
| 6 | `0x62` read failure | `mdevrw` rejected a read (alignment, range) | errno in the console line is the finding |
| 7 | the device never reports `ENABLED` / the sender gets stalls | the NAT-076 engine did not come up on the real controller (U5, the PMMU in front of DWC3 DMA, endpoint resources) | the controller's `last_trb_status` and `last_evt_status` are the finding; no retry in the same run |
| 8 | anything else | | the first panic or loader line is the finding |

A result other than PASS is evidence, not a reason to run again. The rate and the byte counts are reported whether or not the run passes.

## 7. What a PASS does not say

That APFS mounts, that the volume is consistent, that dyld or any Apple binary runs, or anything about display or GPU. It says only that a full-size image can be placed in RAM over USB and read back unchanged by a user process of the project's kernel. The probe is not Apple's launchd.

## 8. Preconditions NAT-078 has to meet before this becomes a decision

The registry gives NAT-078 only the native run; the host work it needs is larger than one task, so it is split (child tasks added by NAT-077's owner, see the registry):

* **NAT-079 (host-test): the delivery loader.** `docs/procedures/nat-076/engine/` integrated into the NAT-074 loader build following the six integration steps at the end of `docs/procedures/nat-076/README.md`: `rx_dest` = the md1 reserve computed from the layout, staged mode, the staged-write self-test of the first and last page of the reserve (so a failure of the receive path is distinguishable from a failure of the kernel's read), a bounded receive phase between layout and the jump (cap and pet schedule as NAT-074; a final pet before the jump), delivery counters in the loader log.
* **NAT-080 (host-test): the session driver and analyser.** The NAT-075 driver derived so that the sender starts after the collector reports the engine up; the NAT-041 collector uses only vendor control transfers on endpoint 0 and the sender adds bulk-OUT on the same device (coexistence to be shown on the model device, including a bus reset); an analyser that applies the table of section 6 to the archive formats.
* U5 stays unresolved; staged mode only. If the integration finds that the loader's own memory map or caches make staged mode impossible at this size, that is a finding of that host work, not a reason to run.
* The pinned-stock restore (NAT-013, pyusb venv python) and the Android check after the run, exactly as in decision 0029.
* A line in the decision naming the SHA-256 of `recovery.img`, the packaged payload, the md0 probe and the padded image, and of the sender (`tools/ios/root_send.py`) and the analyser.
* The kernel's unpetted time after the jump (section 5, rows 3 and 4) has to be settled in the decision: either the delivery phase ends with a final pet so that boot plus a 30 MB/s hash fits the 83 s period (the NAT-071 alternative is a kernel-side keepalive), or the decision accepts row 4 of the pass table as a possible outcome and says so beforehand.

## 9. Deviations from the registry text of NAT-078, to be recorded in its decision

* "4908 MiB window": the loader refuses `mem_size > 4 GiB` (NAT-075). The window is 4096 MiB.
* "md0 on it": md0 stays the 16 KiB-class probe ramdisk (`rd=md0` is how the kernel finds PID 1); the root image goes to the reserve-only `md1`/`rmd1` registered in NAT-075. The probe reads `/dev/rmd1`.
