# NAT-160: scK, scJ with a 2× UI scale (host-test)

- **Evidence kind:** host-test. No device was used.
- **Next step:** NAT-161 runs scK once on the phone and compares it with NAT-159:
  - 26.0 ms per frame in the driver;
  - 9.26 frames/s;
  - about 82 ms per frame outside the driver (software rendering on one core).

## Change against scJ (NAT-158 build-001, ran in NAT-159)

The image adds one boot argument, `fbscale=2`, after `fb_filter=0`. Source:
`references/s24-port` c8860dec, `MiniIOMobileFramebuffer.cpp`.
- The driver reports 750×1624 (375×812 points at two pixels a point) instead of 1125×2436.
- It writes the scale, 2, to `/chosen display-scale` and `/product artwork-scale-factor`, where MobileGestalt reads it.
- iOS then renders 2.25 times fewer pixels.
- The driver still writes all 1080×2340 panel pixels, enlarging nearest-neighbour. Its read side shrinks, but its write side does
  not.

This is NAT-156 lever 4. It aims at the part NAT-159 left as the larger one, the ~82 ms outside the driver.

| Part | scK against scJ |
| --- | --- |
| Command line | `fbscale=2` added after `fb_filter=0`; tag `NAT158-scJ` → `NAT160-scK`; 252 bytes |
| Kernel, ramdisk, root, ADT | byte-identical after the cmdline field |
| Loader objects | only `08-markerlib52.c.o` (image name compiled in, same length) |
| Loader checkpoint check | rc 0; 13 constants on the NAT-143 symbols |
| relocscan | 1 relocation (allowed), 0 not allowed |

`build.py` wraps `nat-158/build.py`. It changes only the name, the tag and the token tuple (`NEW = ('fb_filter=0', 'fbscale=2')`).
It then requires the line to equal scJ's built line with `fbscale=2` inserted.

## Image

| Item | Value |
| --- | --- |
| RECOVERY (`artifacts/nat-160/package-001`) | `3fb15e16cb9ef20ca94c35c68abf66bbc52ca09c828f60d46b26b63c8cfdea5d` |
| `Image.payload` | `1073e982038250e9…` (full hash in `package.json` and `evidence.json`) |
| Session | `session_nat161.py`, counted derivation from `nat-158/session_nat159.py`: 8 lines change (image, hashes, length, package, decision glob, marker, preconditions + NAT-159/NAT-160) |

## Commands

| Command | Result |
| --- | --- |
| `python3 -B docs/procedures/nat-160/build.py --out artifacts/nat-160/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs` | rc 0 |
| `python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-160/build-001 --out artifacts/nat-160/package-001` | rc 0 |
| `python3 -B docs/procedures/nat-160/derive161.py --check` | pass |
| `python3 -B docs/procedures/nat-160/test_nat160.py` | 6 OK |

## Not shown by the host

These are open questions for the run:
- whether SpringBoard comes up and stays up at scale 2 on this image;
- how much rendering time the smaller surface saves.
