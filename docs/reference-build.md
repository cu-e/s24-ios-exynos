# Reference build at native UI resolution

Recorded on 2026-11-14 at the owner's instruction: no quality compromises such as reduced UI resolution. This build is the reference
every later SMP or GPU image is compared against.

## loader-diag-xnu-scV-md1 (NAT-185)

| item | value |
|---|---|
| RECOVERY | `artifacts/nat-185/package-001/loader-diag-xnu-scV-md1/recovery.img`, SHA-256 `57ab39447993b83b48e4afef2674ec0ead000de87f609729c9c9f01be907b27e`, 100663296 B |
| payload | `117aafcc15c8e78e1c04707c1921a962bd680678cd3b3090ed0a8803943c7a88`, 26208032 B at 2048 |
| loader Image | `d38398ebb0bece791e441bfec28026a17eea4a421e1e3a5a592e575e90f1d704` |
| kernel (no-storage) | `artifacts/nat-185/kernel-001`, `d7e7fee154104aaf9c59a4d2145c3901763259296ebd85cb373c388a4667c8b3` |
| md0 root | `artifacts/nat-110/pid1-sc2-hb/root.apfs`, `6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c` |
| session | `docs/procedures/nat-185/session_nat186.py`, `ef8ee127ca0ed506efd9938bfe47378b81a3a25488743fdcaf5827eec1919823` |

Every hash above was re-read from the files on 2026-11-14 and matches the package record.

The command line is 254 B:

```
rd=md1 e1sufs=0 nat_attempt=NAT185-scV debug=0xc serial=3 -v loader_return_after=270 launchdsuffix=release cs_enforcement_disable=1 e1sbattery=0 fb_filter=0 touch_lat=1 e1s_wdt_pet=1 e1s_decon_hw=1 e1spmic=2 e1skeys=0 msgbuf=1048576 small_cores=0 xrd=md0
```

## What it is

- **iOS 16.5 (20F66) userland at scale 3.** The surface is 1125×2436, scaled by the driver to the 1080×2340 panel (nearest-neighbour run
  table, K2 at 2.16 ms per frame).
- **One running core:** cpu0, A520 at 1958 MHz (C2).
- **Software rendering in backboardd.**
- **Touch:** working (P1).
- **Synthetic swipes** from 215 to 375 s.
- **e1s-top sampler:** per process, every 5 s.

## Measured baseline

From NAT-186, confirmed by NAT-188 with the same kernel:
- backboardd 0.77 of the core, 67.95 ms of CPU per frame (median over the swipe spans);
- the core saturated (busy 0.996);
- 60-Hz share of frame intervals 0.59;
- home-page swipe frames at about 30 ms of CPU, Today-view frames at about 190 ms.

## Not to be used as the reference

- **scY (NAT-191/192).** It adds the 1 ms user-pc sampler, which may perturb the frame rate.
- **scZ (NAT-193).** It uses `fbscale=2`, which the owner withdrew. It was never run.
