# NAT-169: scO — fewer touch GPIO accesses (host build)

- **Evidence kind:** host-test. No device was used.
- **Why:** NAT-168 showed that the touch poll's ~9.5 ms is spent on GPIO MMIO, not in the half-bit delay. Each bit does 4 loads and
  3 stores of GPP9 `DAT`, about 8.5 µs per access (inference), and a 0x87 event read is ~1008 accesses. The poll runs every 10 ms
  whether or not the chip has anything.

## Changes (only `bsd/e1s_touch.o`; patch = NAT-167's driver plus these)

1. **`e1s_spi_transfer()` shadows `DAT`.** It reads `DAT` once per transfer, then writes the bits from that copy: 3 stores and 1
   load (MISO) per bit.
   - The written values and their order are those of the read-modify-write version. Only the latch bit of the MISO input can differ,
     and it drives nothing.
   - No other driver of this kernel touches GPP9: battery uses gpp8 and is disabled with `e1sbattery=0`; camera uses gpc2/gpc4 and is
     off.
2. **The event thread is gated on gpa1-2.** It reads the STM only when gpa1-2 is low, or on every 25th poll as a check
   (`e1s_full_every`, boot-arg `e1stouch_full`; 0 gives the old read on every poll).
   - Stock `stm_core.c:1431-1432` requests `IRQF_TRIGGER_LOW | IRQF_ONESHOT` (`references/s24-linux` 417484173abc), so the line is
     level-low while events are pending.
   - The 10 s summary line keeps its old prefix and adds `; skipped S, high-line reads H with E events`. E > 0 would show that the
     line was high while events were waiting.
   - The start line now says `no IRQ, read on a low gpa1-2 or every 25 polls`.

Poll period (10 ms), the start sequence, the ID reads and the event handling are unchanged.

## Host tests (`test_nat169.py`, 9 OK)

The real patched driver runs against `host/peer169.c`: NAT-141's pin-level peer plus a level-low IRQ model (gpa1-2 low exactly while
the event queue is non-empty), GPP9 access counters, a hash of the DAT write sequence with the MISO bit masked, and a second
press/move/release queued during the idle polls.

| Check | NAT-167 driver | NAT-169 driver |
| --- | --- | --- |
| Frames on the wire, 2100 delays | identical | identical |
| DAT writes and their masked hash | 913543, `4a8d713d` | 913543, `4a8d713d` |
| DAT reads | 1216651 (4 per bit + 2 per transfer + 7) | 305226 (1 per bit + 1 per transfer + 8) |
| With the IRQ model: posts | 6 (finger 1 and the late finger 2) | the same 6 |
| With the IRQ model: 0x87 reads | 2103 | 93 |
| Summary after 2000 polls | — | low 2, skipped 1918, high-line reads 80 with 0 events |

The analyser `touch170.py` is tested on NAT-168's real text (P0, 19.47 s, 5.241 ms) and on synthetic gate lines (P1, G-fail). The
build record and the object's strings are tested too.

The peer and its IRQ model are synthetic. Only the phone shows whether the STM really holds the line low.

## Build

| Item | Value |
| --- | --- |
| Kernel | `artifacts/nat-169/kernel-001`, no-storage `e32e36c1ad958c28e26ce58ad979fe408bafe1035d94987ce183ee79dce39ba0`; NAT-167's record with only `bsd/e1s_touch.o` changed (`build.py check_kernel`); `patch_delta()` limits the source change to `e1s_spi_transfer`, `e1s_touch_ev_thread`, one boot-arg in `e1s_touch_init` and one static |
| Gates | loader sites rc 0, verdict ok, 0 bad (the kernel grew; the 13 constants still match); relocscan, 0 not allowed |
| Image | `loader-diag-xnu-scO-md1`, loader Image `662f78b7…2a01`, payload `70119f75…12f0` (26206864 B) |
| RECOVERY | `8f67d7df1c9ed616add76f9fb873b76e3e78d972d92d6acbb25e99d916a28b4e` |
| Command line | scN's with the tag `nat_attempt=NAT169-scO`, 255 B |
| Session | `session_nat170.py` `0aaa35e44bbbefb180e2ce313d145858322935610606394be94a6aa8ada367e1` (`derive170.py --check`) |

```
python3 -c 'import json,subprocess,sys;a=json.load(open("docs/procedures/nat-169/rebuild-args.json"));sys.exit(subprocess.run([sys.executable,"-B","docs/procedures/krn-044/rebuild.py",*a]).returncode)'
python3 -B docs/procedures/nat-169/build.py --out artifacts/nat-169/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-169/build-001 --out artifacts/nat-169/package-001
python3 -B docs/procedures/nat-169/derive170.py --check
python3 -B docs/procedures/nat-169/test_nat169.py
```

## Not established

- Whether the STM holds gpa1-2 low while events are pending on this phone. NAT-170 counts high-line events at idle; a touch run
  is needed for the full check.
- How much of cpu0 the gate frees, and whether frames change.
