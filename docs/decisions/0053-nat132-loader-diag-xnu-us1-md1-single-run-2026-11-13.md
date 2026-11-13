# Decision 0053: one NAT-132 run of loader-diag-xnu-us1-md1 (USB 2.0 delivery measurement)

Date: 2026-11-13. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052 (the owner's
standing permission of 2026-11-13 for prepared native USB experiments; consent recorded there, not asked again). No PMIC/ACPM
operation is used: the image keeps sc9's `e1spmic=0`.

## Image and boundary

Image loader-diag-xnu-us1-md1, built by NAT-130 (sc9 of NAT-126 with only the USB engine replaced):
- RECOVERY artifacts/nat-130/package-001/loader-diag-xnu-us1-md1/recovery.img,
  SHA-256 364f26f8413cb8801f71e29d883554a021bc577df435d48e079a2865664a9cb2 (100663296 bytes).
- Image.payload SHA-256 a338934c0f1363d2eb2ade3db72d9b71c6ab90293c48c533ccf1eb8a6748ea40 (26199536 bytes at offset 2048).
- Loader Image 7c9c413e618e8bfe17cbe973a4089ed1a560812f9b542d31b6170689f83ff424; kernel, ADT, md0, cmdline tokens and every bound are
  sc9's (kernel a31e746c961beae19a58deef24a9e0df72e3764fd66478eb0e369b936eba485a). Cmdline tag nat_attempt=NAT130-us1.
- Only RECOVERY /dev/block/sda18; full-hash readback before the single reboot (session_nat132.py, derived by derive132.py --check).
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67, devices/recovery/backups/2026-11-10/recovery.img.
- Root image artifacts/nat-083/system-padded.apfs, 2475720704 bytes, SHA-256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6.

## Changes against sc9 (the NAT-127 run)

Loader USB engine NAT-130: RX_BEGIN checksum modes (PLAIN as before, FAST unrolled uncached loads, CACHED: the loader turns SCTLR_EL1.M/C
on for the sum only through a private read-only 4 KiB-page identity table of exactly the chunk plus one code page, then off, then
clean+invalidate; NONE), SUM request, GET_RXT phase ticks. Host companion deliver130.py: one 8 MiB bulk write per chunk, host sums
precomputed in a background thread, policy auto (chunk 0 PLAIN, calibration SUM of chunk 0 in PLAIN/FAST/CACHED, chunks 1-4 NONE then
post-verified, the rest in the fastest mode whose sum matched).

## Time limit, stop mechanism, restore

Unchanged sc9 bounds: companion wait 300 s, delivery cap 225 s, loader receive cap 240 s, kernel timed return 150 s with watchdog feed,
loader deadline 475 s, return to Download Mode. A CACHED-mode fault leaves through the window's vectors to the loader's own fault
handler with the MMU off (host-tested under Unicorn only). Restore: docs/procedures/nat-012/restore_stock.py from the observed Download Mode
bus/address with the pyusb venv python, then check_android.py OUTPUT and nat-013 restore_stock.py assess; require boot_completed=1,
SM-S921B/e1s/S921BXXS9BYH3, full stock RECOVERY hash and user-data directories present; close the native permission. If Download Mode
does not appear within ten minutes, the owner is asked for the key combination. One attempt; no retry without a new verifiable reason.

## Interpretation registered before the run

From delivery.json (device-reported numbers only): outcome, committed bytes, total seconds and MB/s; per-phase sums (host sum, RX_BEGIN,
bulk write, commit poll) and device tot_arm/tot_wire/tot_sum/tot_gap; calibration ticks per mode on chunk 0 and which modes matched; the
NONE chunks' wire rate (write_s) as the HS wire ceiling of this setup. Speed-up is claimed only if delivered == 2475720704 with every chunk
verified (commit sum or post-verify) and the measured rate exceeds NAT-127's 16.146 MB/s. A CACHED mismatch, fallback count > 0 or fault is
recorded as a CACHED failure, not hidden by the FAST/PLAIN result. Userland/display verdicts use nat-123/analyze124.py as in NAT-127 and are
reported separately; no touch, acceleration or FPS claim follows.
