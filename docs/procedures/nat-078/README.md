# NAT-078: the first root delivery over USB (native-device, 2026-11-12)

One native run of `loader-diag-xnu-rx-md1` under decision 0030 (decision 0019 protocol): the host streamed the padded root image
(2,475,720,704 bytes) over USB bulk-OUT into the md1 reserve, the payload kernel booted and PID 1 (the NAT-077 hash probe) read `/dev/rmd1`.
The phone was restored from the pinned stock RECOVERY with NAT-013 and Android was checked afterwards.

**Outcome of the pre-registered pass rule: row 3a, not a pass (evidence outcome: inconclusive).** The delivery is complete and verified by the device
and the host; the kernel read back and hashed 59.6% of the image correctly, then the kernel's timed return (45 s) cut the hash short, so the
digest of the whole image was not obtained. The registry task NAT-078 is therefore not `done` (a completed task needs passing evidence).

Everything below is native-device unless it says otherwise. Nothing here shows that APFS mounts or that any Apple code runs.

## Numbers (reported separately, as the task requires)

| quantity | value | source |
|---|---|---|
| bytes received by the device (committed offset) | 2,475,720,704 = the whole image | companion `delivery.json` (device view) and the loader's own `nat079_committed` |
| bytes written by the host | 2,475,720,704 in 296 chunks, 0 retries, 0 resumes | companion / sender |
| time, host | 152.98 s sending (15.434 MiB/s, **16.183 MB/s**) | `delivery.json` |
| time, device | 152.97 s (`nat079_elapsed_ticks` 3,915,973,010 at 25.6 MHz) | loader values |
| `rx_errors`, dups, gaps, rejects, resets, aborts | all 0 (`rx_trbs` 296) | device and loader |
| last chunk | offset 2,474,639,360, length 1,081,344, `last_trb_status` 0 | `delivery.json` |
| destination | PA 0x902d7c000 (about 36 GiB, above 4 GiB); CPU self-test of 8 pages passed (`selftest_bad_pa` 0) | loader values |
| loader status | 0 = done | `nat079_status` |
| wait before the device was ready | 31.08 s after the companion started (placeholder 512 B until then, then capacity = image size) | `delivery.jsonl` |
| kernel page size and memory | 16 KiB pages: `vm_page_bootstrap` 105,775 free + 156,369 wired = 262,144 pages = 4 GiB (same as NAT-075); `md0/rmd0` 0x8000 B, `md1/rmd1` 0x93908000 B, BSD root md0 | kernel text |
| PID 1's digests | 11 progress lines, `at` = 128 MiB ... 1,476,395,008 B (1.375 GiB, 59.6% of the image); **all 11 equal the host's SHA-256 of the same prefix of the image**; no final line | kernel text vs host (analyser) |
| PID 1's rate | 1,476,395,008 B in 44.74 s = 33.0 MB/s (read + SHA-256 in plain C together) | `sec=` of the last line |
| kernel run | the project kernel ran for the whole `loader_return_after` = 45 s unpetted and returned by itself ("loader_return_after expired" in its text); no SEC_UPLOAD | kernel text |
| ending | `1209:0001` left the bus at +378.55 s, Download Mode (`04e8:685d`, iProduct `SAMSUNG USB`, not SEC_UPLOAD) at **+382.39 s** after the reboot request: inside the cap-reset window 364.0-405.0 s | USB watcher |
| restore | NAT-013 `restore_stock.py restore` (pyusb venv python) exit 0, `awaiting-readback`; Android booted (`sys.boot_completed=1` by 09:39:01Z); `check_android.py` pass: RECOVERY equals the pinned stock hash, user data directories present; `assess` pass (PIT validated, upload acknowledged, session end, reboot confirmed, Android booted, readback matches) | restore-001 |

Timeline (UTC, 2026-11-12): reboot requested 09:31:31.976; `1209:0001` at +21.4 s; ready +31 s; delivery finished about 09:34:36; kernel returned about
09:35:23; Download Mode 09:37:54; restore 09:38:21-09:38:24; Android on ADB by 09:39.

## What this run established (native-device)

* The NAT-076 bulk-OUT engine, the NAT-079 receive phase and the NAT-080 companion worked on the real controller on the first try: 2.31 GiB over USB
  into RAM in 153 s at 16.2 MB/s, no error, no retry. The 225 s budget needed 11.0 MB/s; the measured rate is 1.5 times that.
* **NAT-040 item U5 is answered: the DWC3 DMA reaches the md1 reserve above 4 GiB** (PA 0x902d7c000), directly, without staging.
* Cache visibility: the kernel's reads (MMU on, `/dev/rmd1`) matched the host for the first 1.375 GiB, so the loader's final cache clean over the
  window was sufficient for that span; nothing contradicts it for the rest, but the rest was not read.
* The unpetted kernel ran 45 s without the 83 s hardware watchdog expiring (the loader pets at DONE and before the jump).
* `pyusb set_configuration` by the companion while the collector polls endpoint 0 did not stop the collector: it kept receiving the loader text live during the stream.

## What it did not establish

* The digest of the whole image: 40.4% (the last 999 MB, offsets 1,476,395,008 ... 2,475,720,704) was never read back by the kernel. The device's
  per-chunk checksum was verified by the engine at commit time for every chunk, which is a different check.
* Whether APFS mounts from md1, whether any Apple binary runs. The probe is not Apple's launchd.
* The cause of the second boot in the collector archive (below).

## The archive has two boots, and the shipped analyser misreads that (finding about the tooling)

The collector reported `capture-error start-failed` (`UsbTimeout: [Errno 5] Input/Output Error`) at 09:35:22Z, about when the kernel returned to the
loader, and 15 s later opened a new session with a new nonce (`explicit-producer-boot-marker; reset cause unverified`). The archive therefore holds two
boots of this image: boot 1 (187 records) is the live loader stream up to the jump; boot 2 (360 records) is the replay of the whole ring after the
return and contains the kernel text and the probe's lines. Runs NAT-066, 068 and 075 had one boot each. The cause of the break is not established
(it coincides with the kernel's return and the loader restarting its USB engine; the new engine and the host's earlier `set_configuration` are
candidates, not findings).

`analyze_nat080.py` (unchanged since decision 0030) takes the first boot of the image. Its formal output on the whole archive is therefore **row 8
("other": the whole image was committed but no probe line was seen)**, `artifacts/nat-078/run-001/analysis.json`, which is wrong about the phone: the
probe did run. The same unchanged analyser on a copy of the archive that holds only boot 2 (the manifest omitted because it lists boot 1's files)
gives **row 3, variant a** with the numbers above, `artifacts/nat-078/run-001-boot2-view-final/analysis.json`. Which of the two the pre-registered
rule "means" is not a judgement call: the rule is about the phone's behaviour, the probe's lines are in boot 2 in the host's own archive, and the
first output is a limitation of the analyser. Both outputs are kept; the first analysis run (made while the watcher and collector were still within
their 600 s windows) is kept as `analysis-early.json` and `run-001-boot2-view-early`.

Follow-up for the analyser: pick the last boot of the image that contains the kernel text (or merge boots by device sequence); the real archive of this run is the regression fixture.

## Files

* `artifacts/nat-078/` (gitignored): `preflight-001`, `run-001` (driver report, USB events, collector archive, delivery journal/summary, analyses),
  `run-001-boot2-view-final`, `restore-001`, `check-android.stdout`, `assess-001.stdout`, the one-shot marker.
* This directory: `README.md`, `evidence.json`, `numbers.json` (the figures above in machine-readable form). The kernel text is not committed
  (it contains the host user name in the kernel version string); the digests in it are reproducible from the image.

## Next (see the registry)

1. The kernel's 45 s cut the hash at 33 MB/s; the whole image needs 75 s at that rate, which `loader_return_after` (maximum 63 s) cannot cover. The
   cheap fixes are in the probe (SHA-256 instructions of the CPU instead of plain C; read and hash timed separately to see which one costs the time) and,
   later, the kernel keepalive of NAT-071. NAT-081 does the analyser fix and the probe.
2. The next native run should carry more than a re-hash, because every run re-delivers the image (RAM is volatile): the whole-image digest plus a
   read-only APFS mount of `/dev/md1` by the project's own stage 0 and a read of named files, compared with the host. NAT-082 builds it.
