# NAT-132: USB 2.0 root delivery at 37.19 MB/s on the phone (us1 = sc9 + NAT-130 engine)

Owner claude-opus-usb130-20261113. Evidence kind native-device. One run under decision 0053 (standing permission 0052),
reboot requested 2026-11-13T17:14:41Z. No PMIC/ACPM operation (`e1spmic=0`, as sc9).

## Established (device-reported numbers, artifacts/nat-132/run-001/delivery/delivery.json)

- Full candidate RECOVERY readback matched 364f26f8…9cb2 before the reboot (session_nat132.py report.json).
- The loader enumerated as 1209:0001 on host bus 7 (the high-speed root hub) 14.7 s after the reboot request. Android had been
  on bus 8 (SuperSpeed hub) at 5000M before the run, and Download Mode came back on bus 8. The loader is USB 2.0 only.
- Delivery `delivered`: device GET_RX committed = rx_bytes = 2475720704 = root size; 296 TRBs, rx_errors/gaps/dups/rejects/
  resets/aborts all 0; host retries 0; root SHA-256 4377e988…62f6 (host side).
- **66.578 s, 37.185 MB/s** (NAT-127 sc9: 153.335 s, 16.146 MB/s; ×2.30). Root delivery ended 63.0 s after the reboot request, against 149.5 s in NAT-127.
- Every chunk verified. Chunk 0 PLAIN had its sum checked at commit. Chunks 1-4 were NONE, then post-verified with SUM in CACHED mode
  before the final chunk, all four matched. Chunks 5-295 used CACHED with the sum checked at commit. The sender raises on any mismatch.
- Calibration on chunk 0 (SUM, device ticks at 25.6 MHz): PLAIN 4729043 ticks = 184.7 ms, FAST 2344139 = 91.6 ms,
  CACHED 293598 = 11.47 ms. All three matched the host sum; CACHED was chosen. sum_fallbacks 0, sreq_refused 0, no fault.
  The CACHED sum is 16× faster than PLAIN (about 731 MB/s against 45 MB/s).
- Phase totals (device): tot_wire 61.34 s (92 % of the delivery), tot_sum 3.53 s, tot_gap 1.25 s, tot_arm 0.41 s. Host side:
  host_sum 0.003 s in total (SumCache had finished before it was needed), RX_BEGIN 0.50 s, bulk write 61.49 s, commit poll 3.53 s.
  Per-mode wire rate (host write_s) was 40.25-40.69 MB/s, and the device's own clock agrees (one chunk t_arm1→t_done = 205.4 ms = 40.8 MB/s).
  **The USB 2.0 wire of this host path is now the limit: about 40.5 MB/s, 325 Mbit/s.** All remaining overhead together is about 8 %.
- Userland: W-ok / D2-refreshing / F1-new-frame / T1-no-response / P0-no-verified-rails (nat-123/analyze124.py, the same
  verdict as NAT-127). backboardd opened hakios-touch at kernel 111.16 s, against 201.24 s in NAT-127. The recording ring held 73 frames.
  The framebuffer log reports 5-6 frames/s, 54 ms of CPU driver time per frame. **The owner did not observe the panel in this run, so there is no physical-display claim here.** No input, acceleration or FPS claim either.

## Restore

Download Mode (04e8:685d) appeared on bus 8 / address 3 at 2026-11-13T17:22:55Z (490.9 s after the reboot request: the loader
deadline). nat-012 restore_stock.py exited 0: 100663296 bytes acknowledged, session end and reboot confirmed. check_android at
17:23:52Z: SM-S921B/e1s/S921BXXS9BYH3, boot_completed=1, user 0, user-data directories present, full RECOVERY hash
96620b8b…bf67. NAT-013 assess: pass. Native permission closed (decision 0053). These are minimal checks, not an audit of every setting, account and app.

restore-001/report.json is derived from restore-trace/trace.json in the same shape as NAT-127's report: stages from the Odin
replies, 0x65 PIT 8192 B, 0x66/3 acknowledged bytes summed, 0x67/0 session end, 0x67/1 reboot.

## Interpretation and next step

The pre-registered speed-up criterion is met: every byte was committed and verified, and the measured rate exceeds 16.146 MB/s. The device's
uncached CPU checksum was the dominant bottleneck: NAT-127 spent about 150 s at 16 MB/s, and the sum took about 185 ms of each
chunk's time. The CACHED window removed it. What remains is HS wire time. A further USB 2.0 gain is bounded at about 8 % (sum
poll and gaps). The next speed step is SuperSpeed (NAT-131 plan), which needs its own host-built image and a register-probe run first.
