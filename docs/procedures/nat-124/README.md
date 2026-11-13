# NAT-124: native sc8 touch-power diagnostic

Owner `claude-opus-nat116-20261113`. One run under decision 0050, begun
2026-11-13T15:23:38.410400Z. Evidence kind: native-device.

## Established

- Full RECOVERY candidate readback matched the pinned package-002 hash before
  reboot. The 2475720704-byte root was delivered in 151.263 seconds, zero retries
  and RX errors. USB reached Download Mode (bus 5/address 56) at 15:32:01.199334Z.
- The corrected ACPM decoder found channel 2: queue length 5, element 16 bytes.
  The real PMIC replied with S2MPS27 COM revision 0x01 (matching Android).
- At kernel 195.651580 s LDO9_CTRL=0x30 and LDO18_CTRL=0x18; both had their
  enable bits clear. After authorized writes: LDO18 0x18 -> 0xd8 -> readback 0xd8;
  LDO9 0x30 -> 0xf0 -> readback 0xf0. Settled 100 ms. Analyzer P2-both-rails-verified.
  These are register observations, not electrically measured voltages.
- STM device ID remains 00 00 00 00 00. Step 3 attached low-level GIC SPI 42;
  the touch thread started and logged empty event buffers. T1-no-response.
- Kernel timed return and watchdog path worked; DECON FRAME_COUNT increased
  by 1200/1201 per approximately ten seconds. W-ok / D2-refreshing.
- Stock RECOVERY restored through nat-012, full readback hash matches
  96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
  Android boot_completed=1, SM-S921B/e1s/BYH3, user-data directories present;
  NAT-013 assess pass. Native permit closed. These minimal checks do not audit
  all account/settings/application content.

## Regression / experiment outcome: inconclusive

The returned kernel log is 19404 bytes with no log gap, no panic, but no launchd
lines or hakios-touch open. Screen recording contains zero frames (32-byte
header only). Thus this run does NOT re-establish the iOS home screen seen in
NAT-120, and does NOT establish working physical input. Existing nonzero panel
pixels are not evidence of a new iOS frame. Analyzer ios=S1-alive-no-frame is a
label, not proof that Apple userland started.

Owner observation, asked after restoration, verbatim: "Не наблюдал экран"
(English: "Did not observe the screen"). No physical screen/touch claim.

The native acceptance is not fully met: retain task in progress with this
inconclusive outcome, rather than passing it for the successful power sub-result.
Do not repeat sc8. The single-run PMIC authorization has been consumed.

## Host findings and next step

Compare sc8 with sc7: besides ACPM/PMIC there is a newly enabled touch IRQ/event
thread. S5E9945's IRQ line was low before setup; a low-level source is masked in
its handler but unmasked again after each empty poll. An IRQ/re-arm storm or
scheduler starvation is a hypothesis, not yet a proven cause of absent PID 1.
ACPM becoming ready also enables recurring power-key reads in e1s_input.c; this
is a separate candidate source of changed scheduling. No causal claim yet.

The donor touch driver does not implement Samsung's stm_ts_set_spi_mode startup
sequence. Study that sequence, read framing, pin mapping and ready-event delays
against pinned Samsung source. Host tests must reconstruct real SPI transfers,
not assume rails alone establish controller response. Prepare polling-only and
empty-IRQ backoff candidates on host; no new PMIC run without a fresh owner
choice after the concrete plan is available.

Artifacts: artifacts/nat-124/run-001, analysis/{kernel-text.txt,pixels.json,
verdict.json}, restore-001/{report.json,android-check.json,assess.json}.
