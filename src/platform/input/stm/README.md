# STM record parser and host adapter

`protocol.c` is project-owned C11 code. It has no bus, MMIO, IRQ, power,
firmware or HID operation. The parser interprets the pinned Samsung 16-byte
coordinate layout; the adapter reuses `src/platform/display/contract.c` for
normalized coordinates and the existing UI-001 contact rules. That boundary
is a project interface, not an Apple wire format.

Source protocol facts: Samsung s24-linux
`417484173abc2c4fa93e738ea82ad9f2e84911b1`, `stm_dev.h` coordinate/status
declarations, `stm_core.c` parsing/status handling and `stm_reg.h` constants.
The corrected E1S donor decoder at s24-port
`c8860decc62c6d6180e609036d027a2997972420` plus the existing local nibble fix
is a differential test input. Its full implementation is not copied here.
Upstream licenses remain with those sources; the existing E1S licensing
qualification is unchanged. See `fixtures/public/stm-touch/source-profile.json`.

The parser accepts exactly 16 bytes, contact IDs 0..9, actions 1/2/3 and the
selected normal/glove/palm/wet types 0/3/5/6. Byte3 bits7..4 belong to X;
bits3..0 belong to Y. Raw coordinates are 12 bits and must fit the caller's
inclusive maxima. Remaining-event count, pressure, major and minor are
decoded, not treated as transfer integrity or measured sensor quality.
Only an all-zero record is classified empty: a zero first byte with nonzero
tail is malformed under this owned admission policy. Status/gesture/vendor
records are not synthesized into touches. Error status and the known ready/
reset status invalidate the contact stream; ordinary non-coordinate records
are returned to the backend for separate interpretation.

Initialize fresh/retired storage with a nonzero epoch. First deliver
`stm_adapter_resync`, which emits UI_CANCEL_ALL. Feed complete records only
after that cancellation is acknowledged. A sink returns zero only for full
atomic acceptance, and nonzero only when it published nothing. Nonzero keeps
the exact pending event for `stm_adapter_retry`; new input is busy until
delivery or explicit cancellation. The backend must retain any packet passed
while busy, and stop draining the hardware FIFO or report loss. Silent lost
packets cannot be detected from this record layout alone.

MOVE/UP without DOWN and duplicate DOWN cause desynchronization, unlike the
donor's implicit MOVE-to-DOWN policy. Malformed records, unsupported coordinate
types, reported controller loss and backward time require cancellation before
new contacts. SPI errors, disconnects or backend-observed loss must call
resync/Stop and retain cancellation until accepted; this code does not detect
the physical bus state. Timestamps are caller-supplied monotonic nanoseconds,
not a fabricated conversion of a controller or Mach timebase.

Stop replaces a previously declined event with a cancellation of the last
acknowledged contact set. Active contacts and the stopped flag commit only
after that cancellation is accepted. A declined Stop cannot be undone by
resync. Reentrant dispatch returns busy. The last uint32 sequence is reserved
for cancellation; after it is acknowledged, retire the epoch before reuse.
No sequence wraps and no logical flag claims hardware quiescence.

The caller must serialize access. A synchronous callback may not retain the
event pointer or modify adapter storage. Native partial writes/copyout must
provide the stated atomic acceptance contract; it has not been implemented or
verified here. `stm_event_wire` serializes the exact existing 40-byte UI-001
record and does no dispatch.

Host tests cover malformed/bounded input and acknowledged lifecycle. The
fixture exercises guard pages and sanitizers. ARM64 output is compile-only.
Real SPI9 transfer/errors, IRQ, rails, firmware identity, calibration, sensor
behavior, wake/suspend and iOS16.5 HID delivery remain unverified in UI-004/005.
