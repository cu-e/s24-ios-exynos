# NAT-168: the touch half-bit is not the poll cost; the GPIO accesses are (native-device)

- **Decision:** 0068 under 0061, one attempt, consumed.
- **Image:** scN (NAT-167): scM with the kernel default `e1s_halfbit` 8 instead of 400.
- **Outcome:** pass as a measurement. The registered verdict is **P0** (no gain). Stock RECOVERY was restored with a full hash, and
  Android was verified.
- **Touch:** none.

## Results

| | NAT-166 (400 loops) | NAT-168 (8 loops) |
| --- | --- | --- |
| ID reads (`device id: ok`) | 3/3 | 3/3, same bytes |
| Seconds per 1000 polls (`touch168.py` slope) | 19.58 | **19.47** (verdict P0) |
| Device ID read, line to line | 5.246 ms | 5.241 ms |
| Hardware ID read, line to line | 6.608 ms | 6.554 ms |
| cpu0 busy (`load166.py`) | 100% (L2) | 100% in all 37 steady samples (L2) |
| `frames159` | 9.61/s, driver 26.00 ms | 9.55/s, driver 25.94 ms |
| Display (`analyze150.py`) | W-ok, D2, S1, P2 | the same |

Touch works at 8 loops, but nothing got faster.

## Why: the delay loop was never the cost

These were checked after the run:
- The run used NAT-167's kernel. Its UUID BABA6672… is in the delivered payload and NAT-165's is not, and the RECOVERY readback was
  `408e8ff3`.
- The linked kernel holds 8 at `_e1s_halfbit` (0xfffffff007af9524).
- `llvm-objdump` of `e1s_spi_transfer` shows the three volatile loops bounded by `e1s_halfbit`. So the loops were really shortened,
  and 400 of them cost only tens of µs per transfer.

The rest of each bit is GPIO MMIO:
- 4 loads and 3 stores of GPP9 `DAT`: a read-modify-write for each of MOSI, CLK high and CLK low, plus the MISO read;
- a device ID read is 88 bits, which is 616 accesses in 5.24 ms, about **8.5 µs per access** (inference);
- a 0x87 event read is 144 bits, about 1008 accesses, which accounts for the ~9.5 ms per poll.

NAT-166 had the right size for the cost and the wrong mechanism. Its "~4 kHz SPI from 400 loops" is corrected here: the bit rate is
set by the bus accesses, about 17 kbit/s.

## Next

These reduce the number of MMIO accesses, not the delay:
1. **Gate the poll on the IRQ line.** It is one GPA1 read per poll, and it is already done; the SPI read follows only when the line is
   low. At idle the line was low in 2 of 13 000 polls; under touch (NAT-142) in about a third. The stock STM driver treats the line as
   level-low, so it stays low while events are pending (not yet shown here). To verify, a full read stays every N-th poll, and a counter
   records events found while the line was high.
2. **Shadow `DAT` in a variable.** The output pins are written without reading back: 3 stores and 1 load per bit instead of 7
   accesses. The other bits of `DAT` belong to pins this driver owns or leaves alone; this has to be checked before the change.
3. Later, the hardware USI SPI (FIFO). It needs its clock and reset with stock parameters.

## Not established

- How the ~8.5 µs per access splits between reads and writes, and why it is so slow (the PERIC1 bus state under this loader).
- Whether the IRQ line stays low until the FIFO is empty.
- The per-thread split of cpu0.
