# NAT-158: scJ, scH with nearest-neighbour scaling (host-test)

- **Evidence kind:** host-test. No device was used.
- **Next step:** NAT-159 runs scJ once on the phone. It compares MiniIOMobileFramebuffer's per-frame driver time and frame rate with
  NAT-153's single-core software path: 70.7 ms per frame, 6–7 frames/s.

## What changes against scH (NAT-152 build-001, ran in NAT-153)

The image takes one boot argument, `fb_filter=0`: the driver scales the 1125×2436 surface onto the 1080×2340 panel nearest-neighbour
instead of bilinear. This is NAT-156 lever 3. On the host, bilinear costs 3–11 times nearest, depending on content.

The 255-byte command line has no room for `fb_filter=0` next to scH's 253 bytes. So it takes the place of `rec_secs=270 rec_mb=64`, and
the line becomes 242 bytes. Dropping the recording does not change the frames NAT-153's figure came from:
- the recording filled its 64 MB at 345 s (`recording finished: 73 frames, 63 MB`);
- the steady windows of 70.66–70.69 ms per frame were all after that, with `record()` returning at once;
- while it was recording, the driver took 74–76 ms per frame.

The comparison baseline is therefore NAT-153's windows from 352 s on. What is lost is the screen recording (in NAT-153 it was not
transferred anyway: 2.5 MB received). The loader's PX panel-pixel report, which gives the P1 verdict, does not depend on it.

Also built in is NAT-157's loader message fix (`fix_msg.wrap_cc` on every nat-052 module of the chain), with `relocscan.py` as a gate.

| Part | scJ against scH |
| --- | --- |
| Kernel, ramdisk, root, ADT | byte-identical: every byte of `payload.adt8.bin` after the cmdline field |
| Command line | `rec_secs=270 rec_mb=64` → `fb_filter=0` in place; tag `NAT152-scH` → `NAT158-scJ`; 242 bytes |
| Loader objects | `10-ckpt3.c.o` (NAT-157 fix); `08-markerlib52.c.o` (image name compiled in, `-DNAT047_TAG`, same length) |
| Loader checkpoint check (`check_loader_sites.py`) | rc 0; all 13 constants on the same symbol+offset as in the NAT-143 kernel |
| Relocations (`relocscan.py`) | 1, the Image header's; 0 not allowed (scH: 6 not allowed) |

`build.py` wraps `nat-152/build.py` and changes three things:
1. the name and tag, each the same length;
2. NAT-143's recording-token slot (`b143.REC_TOKENS`), which becomes `('fb_filter=0',)`;
3. NAT-145's check `'rec_secs=270' in tokens`. `main145_source()` replaces exactly that one line (counted) with "`fb_filter=0` is
   present and no `rec_` token", and runs it on NAT-145's own module globals.

Afterwards it requires the final line to equal scH's built line with the same replacement.

## Image

| Item | Value |
| --- | --- |
| RECOVERY image (`artifacts/nat-158/package-001`) | `778300380b4ccd975d34e1cee89aca428db68db88d9e48232376399367a7003a`, 100663296 B |
| `Image.payload` | `cd9823e1ce5a4b4d38d7e6d63fc9e0fe2142bfded8bd1710b782664336089ce5`, 26206800 B |
| Loader Image | `7217ef2c2f5b2d2a0209054cc8643e44f91440c02d9ea7153b04a3cc6e917238` |
| Session | `session_nat159.py`, counted derivation from `nat-152/session_nat153.py` (`derive159.py --check`) |

The session differs from NAT-153's in 8 lines:
- the image, its two hashes and its length;
- the package;
- the decision glob (`*-nat159-…`) and the one-shot marker (`artifacts/nat-159/`);
- the precondition list (adds NAT-153, NAT-156, NAT-157 and NAT-158).

Time bounds are unchanged: loader deadline 595 s, `loader_return_after=270`, watcher/collector 720 s.

## Commands

| Command | Result |
| --- | --- |
| `python3 -B docs/procedures/nat-158/build.py --out artifacts/nat-158/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs` | rc 0, `{"cmdline_bytes": 242, "relocations": 1, "differing_objects": ["08-markerlib52.c.o", "10-ckpt3.c.o"]}` |
| `python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-158/build-001 --out artifacts/nat-158/package-001` | rc 0 |
| `python3 -B docs/procedures/nat-158/derive159.py --check` | pass |
| `python3 -B docs/procedures/nat-158/test_nat158.py` | 7 OK |

## What this does not show

The host does not run the driver, so it cannot predict the phone's time per frame. NAT-156's host ratio suggests nearest scaling
at about 6–24 ms in place of 70.7 (≈13 ms for home-screen-like content), and about 11–13 frames/s on one core. That is an inference
for NAT-159 to test.
