# NAT-043: first native USB log run (loader-diag-usbmon), run 001

Evidence kind: **native-device**. On 2026-11-11 the host computer received, by itself and without a camera, the messages of one real run of a
loader image on the S24 (SM-S921B/e1s), through the NAT-041 EP0 log engine, the NAT-045 HSI0 ladder and the NAT-041 host collector. This is the
first time any message of a native run has reached the host: the earlier native runs (001-009, NAT-046) were observed by the display and by USB
enumeration events only (NAT-053 audit).

## What ran

* Decision `docs/decisions/0022-nat043-loader-diag-usbmon-single-run-2026-11-11.md` (decision 0019 protocol); the owner's confirmation of the run
  was recorded and committed (6a324a2) before the launch, the owner installed the udev rule for 1209:0001 (`host_access.py --check` exit 0).
* Image: RECOVERY SHA-256 `c6802dea4682a4bc993885bf525e2907e42e4eeebb964310da82ed79fef7212d` (NAT-047 package-001 `loader-diag-usbmon`),
  written to `/dev/block/sda18` only, full readback equal; one `adb reboot recovery` at 2026-11-11T15:40:52.96Z. The image does **not** start
  XNU: the loader runs the HSI0 ladder, brings up the DWC3 log engine, prepares the XNU handoff, holds, and resets the phone at 45 s.
* Driver `docs/procedures/nat-049/session_usblog.py --image loader-diag-usbmon --out artifacts/nat-043/run-001 --execute`; analyser
  `analyze_usblog.py`, unchanged (command lines in `evidence.json`). Both the USB watcher (start record at -0.3 s) and the collector (first
  `poll` at -0.09 s, heartbeat file) were running before the reboot request, as the NAT-053 audit asked.
* Restore: the phone re-enumerated as 04e8:685d `SAMSUNG USB` at +72.8 s without owner action; NAT-013 `restore_stock.py restore` in one session
  returned stock RECOVERY (`96620b8b...`); `check_android.py` read back the full-hash match and `boot_completed=1`, `assess` = pass (all six stages).
  The `native` permission was closed again (single run consumed).

## What the host observed (timeline from `run-001-usb-events.jsonl`, T0 = reboot request)

| T0 + | Event |
|---|---|
| -0.3 s | watcher started; phone present as 04e8:6860 `SAMSUNG_Android` |
| +3.7 s | phone left the bus |
| +26.8 s | **1209:0001 appeared** (the monitor identity of the image, new device number); collector found it at +26.9 s |
| +26.9 s | first control transfer returned a valid 112-byte `S24L` status; frames followed |
| +30.7..+36.8 s | 127 consecutive timeouts: the loader was not polling the engine (RAM zeroing, see the log) |
| +69.0 s | 1209:0001 left the bus |
| +72.8 s | 04e8:685d `SAMSUNG USB` (Download Mode) |
| +86.3 s, +115.7 s | Download Mode left (restore), Android back as 04e8:6860 |

## What the host received (`run-001-loader-log.txt`, raw `artifacts/nat-043/run-001/archive/`)

* One boot in the archive, id `3d759cf0daa88c2699b60434dc29617d-619fab1900000000892331959b92e645` (the only boot ever archived, so new for this
  run), 148 frames, 146 records (138 text and 8 stage records, plus the boot and the end frame), `dev_seq` and frame sequence contiguous, 0 drops, 0 faults,
  0 stalls; manifest `complete-received-stream`, 35857 bytes; the end frame says `reason=disconnect`, `unread_bytes=0`,
  `next_offset=engine_written=6017`.
* Banner `NAT047 loader-diag-usbmon deadline_s=45 fault=0`, stages 32 loader_main, 33 fb, 48 mem, 49 zero, 50 copy, 51 adt, 52 clean, 64 pre_jump.
* Ladder summaries: reads (rung 2) `err=0 pd_was_on=1 nrec=5`; writes (rung 5) `err=0 pd_was_on=1 nrec=69 gsnpsid=0x33313130`, with 5 + 69
  per-operation lines and no failed read-back or timeout (`err=0`). The DWC3 engine then enumerated and served records, so the L6-L8 bring-up also worked.
* Loader log: framebuffer/GIC/ADT lines, the 512 MiB RAM zeroing in 32 steps (`zero_bytes=0x1000000`...`0x20000000`), the
  ten XNU segments, the command line, `PREPARING XNU HANDOFF (not proof of entry)` and `HOLD stage=0x40 code=0x0`.
* The analyser verdict is **PASS** (transport) under the rules fixed in decision 0022 (`run-001-analysis.json`).

## Findings

* The HSI0 power/clock/PHY/DWC3 sequence of the NAT-045 ladder, the NAT-041 polled EP0 engine and the host collector work on this phone on the
  first attempt, with no hang and no `SEC_UPLOAD`. The register writes of the ladder are the first writes to that block from this loader; they
  read back as expected at every step of the ladder summaries.
* The engine survived one ~7.2 s stretch in which the loader did not poll it (largest gap between successful transfers `+29.7 s`, 127 timeouts in the +30.7..+36.8 s cluster) and
  resumed with a contiguous sequence and no drop. This is one hardware observation of a no-poll gap that the NAT-052 simulation assumed (8 s).
* With the engine up the phone still reset into Download Mode by itself (+72.8 s; NAT-046 without the engine: +73.0 s). The loader's own 45 s deadline start is not logged, so only the end of the monitor (+69.0 s) and the Download Mode appearance are observed.
* Collector counters: 1410 control transfers, 1277 ok, 132 timeouts (127 in the cluster above, 5 as the device went away), 1 `UsbGone`.

## What is not established

* XNU was not started; nothing here says anything about the kernel. The exception path on hardware (the `loader-diag-usbmon-fault` image) has
  not run: this directory shows no exception frame. Decision 0022 grants one image; the fault variant needs its own decision.
* The collector's own manifest keeps `transport_qualified: false` and `hardware_execution_proven: false` and the analyser labels the provenance
  `unqualified-live`: those are the tools' conservative flags for any live run; the claim here rests on the raw files and the timeline above,
  not on those flags.
* One run: repeatability of the enumeration time (+26.8 s), of the bring-up and of the survival of longer no-poll gaps is untested. The cause of
  the 3.8 s between the monitor leaving and Download Mode appearing is not established (consistent with the PMU reset of NAT-046).
* The log is the loader's; kernel messages (NAT-052's checkpoint image) have not been sent yet.
