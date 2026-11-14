# NAT-167: scN — the touch SPI half-bit default cut from 400 to 8 loops (host build)

- **Evidence kind:** host-test. No device was used.
- **Why:** NAT-166 (native, L2-saturated) measured cpu0 busy in every 1 s `cpuload` sample. The e1s touch event thread polls every
  10 ms (`e1s_poll_us=10000`), and each poll bit-bangs SPI with `spi_delay()` = `e1s_halfbit` volatile loops, three per bit. With the
  default 400 loops the 1000-poll period was ~19.3 s instead of 10 s: ~9.3 ms of busy CPU per poll, about half of cpu0. The stock
  DTS gives this touch chip a 10 MHz SPI limit; 400 loops is about 4 kHz.
- **Change:** one line in the touch driver, `static uint32_t e1s_halfbit = 400;` → `8;` (with a comment). The boot-arg
  `e1stouch_delay` still overrides it, but the scM command line is already at the 255-byte limit, so the default had to change.
  At 8 loops a poll is expected to take about 1/50 of the old busy time, still far slower than 10 MHz (**inference**, to be measured
  in NAT-168).

## What was built

| Item | Value |
| --- | --- |
| Kernel | `artifacts/nat-167/kernel-001`, no-storage SHA-256 `eb0f0a1ee4ed7e1c101a64015c90f08498ba39d223f649f35b57f4375f778144` |
| Kernel delta | NAT-165's record with only `bsd/e1s_touch.o` changed: patch `e1s_touch_combined.patch` = NAT-143's patch + the default line (`build.py` `patch_delta()`/`check_kernel()`) |
| Object check | cctools `nm`/`otool -d`: `_e1s_halfbit` in `__DATA,__data` holds 0x190 (400) in NAT-165's `e1s_touch.o` and 0x8 in this one |
| Image | `loader-diag-xnu-scN-md1`, loader Image `da620fd8…54c0` (446464 B), payload `a36f0405ab89eb66…a56c` (26206800 B) |
| RECOVERY | `408e8ff3d6202ae2df9e5bde3dc6a2a06ce94f5ac9d0ed89c3acd83e3c203b6b` (100663296 B) |
| Command line | scM's with the tag changed to `nat_attempt=NAT167-scN`, 255 B (`cpuload=1000` kept to measure the effect) |
| Gates | NAT-152 loader check rc 0 on NAT-143 symbols; relocscan, 0 not allowed |
| Session | `session_nat168.py` `8dfb76a449abea74ab01f1c152d6b6c23565681e01f138056bd482a0f6083231`, derived from `session_nat159.py` by counted replacement (`derive168.py --check`) |

Commands:

```
python3 -B docs/procedures/krn-044/rebuild.py $(python3 -c 'import json;print(" ".join(json.load(open("docs/procedures/nat-167/rebuild-args.json"))))')   # see rebuild-args.json (arguments with spaces)
python3 -B docs/procedures/nat-167/build.py --out artifacts/nat-167/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-167/build-001 --out artifacts/nat-167/package-001
python3 -B docs/procedures/nat-167/derive168.py --check
python3 -B docs/procedures/nat-167/test_nat167.py
```

## What NAT-168 must show

- Touch still works: the chip ID read (`device id: ok`) and `event thread started`; at 8 loops the SPI is much faster, and the STM
  chip might not tolerate it. If the ID read fails, the result is a fail for this default, not for the line of work.
- The 1000-poll period drops from ~19.3 s toward 10 s.
- cpu0 busy share (`load166.py`) falls below L2 (90%).
- Frames (`frames159.py`) against NAT-166 (9.61/s, driver 26.00 ms).

## Not established

- Whether the touch chip reads correctly at this speed; whether a faster poll changes the frame rate at all (NAT-164 found the idle
  home screen paced by userland, not by the CPU).
