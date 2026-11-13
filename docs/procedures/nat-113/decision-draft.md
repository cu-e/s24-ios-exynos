# Decision DRAFT: one RECOVERY-only run of `loader-diag-xnu-sc3-md1` (NAT-113)

Status: DRAFT prepared by claude-opus-nat112-20261113 on 2026-11-13. Not a decision. The session driver refuses to touch the phone
until a file `docs/decisions/NNNN-nat113-loader-diag-xnu-sc3-md1-single-run-YYYY-MM-DD.md` exists that names both hashes below and
decision 0019, and `state/lab.json` has `native=true` set by `tools/lab.py` citing it.

## Question this run answers

NAT-111 showed `SpringBoard[13]` alive and two `MiniIOMobileFramebuffer` swaps of a 1125x2436 BGRA surface, but no pixel evidence:
`fb_pixel_diffs=[]` only means the 5 s statistics window never closed (two swaps 0.53 s apart, no third). The question is:
**at the end of the kernel window, does the memory the display scans hold a non-black picture, and do the swapped surfaces?**

## What changes relative to NAT-110 / NAT-111 (decision 0042)

1. **Loader, at the kernel's own return (why=2), before the KL log dump** (`src/glue113.h`, called from `glue62_impl.h`): reads,
   never writes, and sends as TEXT records over the same EP0 engine:
   * `PX`: the panel memory at `0xfa200000` (1080x2340, stride 4320 — the DTB framebuffer the loader hands to the kernel and that
     the kernel's `e1s-display` reported in NAT-111): non-black pixel count, FNV-1a over all words, and a 108x234 RGB332 thumbnail
     (every 10th pixel). 235 records, about 55 KB of text.
   * `PR`: the kernel's screen recording (below): header and, per frame (at most 96), time, non-zero bytes, FNV-1a.
   The recording address is read from the kernel's `loader_recording[]` (VA `0xfffffff007d10a08`, from the kernel's symbol table)
   and refused unless it is 4-byte aligned, inside the XNU window `0x8fe400000..0x9fe400000` measured in NAT-111, at most
   64 MiB + header, with a valid `RWREC003` header whose frames fit the length.
2. **Kernel command line**: `rec_secs=30 rec_mb=64` added (MiniIOMobileFramebuffer keeps one pixel of every 3: 375x812 RGB frames,
   913,508 B each, 73 fit in 64 MiB; recording stops when full or after 30 s, whichever first); `keepsyms=1` and `fb_diff=1` removed;
   `loader_return_after=63` unchanged; 247 B < 256 B. The kernel binary itself is NAT-110's (`kernel.no-storage`, unchanged): the
   recording code and `loader_recording[]` are already in it.
3. `--deadline-s 390` (rx cap 240 + kernel 63 + 60 + 25 for the pixel report), inside the 600 s collector/watcher window.

## Why 63 s and not 120 s (correction of an earlier draft)

An earlier draft claimed the hardware watchdog is paused while the kernel runs and proposed 120 s. That was taken from a different
loader (`references/hakios-scion-full`, Galaxy S9) and is **wrong for this image**: this loader arms the S5E9945 watchdog for 83 s
(`guard.c`), pets it for the last time right before the jump (`nat074_final_pet`), and nothing feeds it afterwards (no S5E9945 code
in the kernel tree; `hv_wdt_pet` is a Qualcomm hypervisor call). A kernel window above 63 s would end in SEC_UPLOAD before
`loader_return`, losing the log and the pixels. Making the kernel feed the watchdog is NAT-071's topic, not this run's.

The 63 s window is enough for this question: in NAT-111 the swaps happened 39 s into the kernel window (kernel time 234.9 s of 256.4 s
end), and the pixel report reads the final state, not a moving picture.

## Getting the data back (measured, not assumed)

The only return channel is the EP0 TEXT engine. NAT-111 measured it: 380 KB of KL records in 117 s, about **3.2 KB/s**. A full
recording (tens of MB) is therefore **not** transferable; that is why the loader sends statistics and a thumbnail, not frames.
Budget: PX ≈ 55 KB + PR ≤ 6 KB ≈ 20 s, then the unchanged 512 KiB KL dump. The PX/PR records come first, so a dump cut by the
deadline reset still has them.

## Pass rule and outcomes (`decode113.py`, verdict of the first match)

| verdict | meaning | next step |
| --- | --- | --- |
| `X-incomplete` | the report did not arrive whole | inconclusive; fix transport, no conclusion about pixels |
| `P1-panel-has-pixels` | the scanned memory holds non-black pixels | look at the thumbnail; if it is iOS, open UI/input work; if it is the loader's/console text, see below |
| `R1-recording-has-pixels` | panel black, swapped surfaces were not | the copy to the panel (drawLayer/fBase/cache) is the break |
| `R0-recording-black` | the surfaces iOS swapped are black | CoreAnimation's software renderer output is the break |
| `P0-black-no-recording` | nothing anywhere | the recording never started (check the kernel log for `recording %u s of the screen`) |

`P1` alone is **not** proof of an iOS picture: the kernel text console draws into the same memory until the first swap. The
thumbnail and the KL log (`the text console has been told to stop`) decide which it is. PASS for NAT-113 = report complete +
stock RECOVERY restored with matching SHA-256 + Android booted. The pixel verdict is the measured result, whichever it is.

## Exact images

* `loader-diag-xnu-sc3-md1` RECOVERY (`artifacts/nat-113/package-001/loader-diag-xnu-sc3-md1/recovery.img`):
  100,663,296 B, SHA-256 `aedbf05f6ea72f8bd20b3ccbb8e6fa018194a224274bee607872a1ccd8ff5880`
* Embedded `Image.payload` at offset 2048: 26,138,384 B, SHA-256 `2c3624a1c26f38b7de8a6573e2efe28e9b06f73aeaec6261fb81c8a7f98d97e0`
* Loader `Image`: SHA-256 `6dff28e3159aad7bc36a4c4da37721eeb26770077f467d760b3ecbf7a4190fb6`
* md0 small root: NAT-110's, 4,194,304 B, `6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c`
* USB-delivered iOS root: NAT-083's, 2,475,720,704 B, `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`
* Stock RECOVERY restore target: `devices/recovery/backups/2026-11-10/recovery.img`,
  `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`

## Scope and limits

Only RECOVERY (`/dev/block/sda18`) is written, once, with full readback; then stock RECOVERY is restored unconditionally with full
readback and Android boot is verified (`sys.boot_completed=1`), exactly as in decision 0042 (`session_nat113.py` is
`session_nat110.py` with 10 counted substitutions: image, hashes, payload length, package path, decision glob, one-shot marker,
required tasks; `derive113.py --check`). BOOT, init_boot, vendor_boot, dtbo, vbmeta, super, USERDATA, EFS, GPT, keys and settings are
not touched. One attempt; no automatic retry.

Risks new relative to 0042: the loader reads 10 MB of panel memory and up to 64 MiB of RAM with the MMU off (reads only, aligned,
range-checked); the kernel allocates 64 MiB more (NAT-075/110 left about 1.6 GiB free). Recovery path unchanged from NAT-109/111,
both of which restored stock RECOVERY and booted Android.

## Commands (after the decision exists)

    python3 tools/lab.py project permit --scope native --value true --decision docs/decisions/NNNN-nat113-...md --owner OWNER
    python3 docs/procedures/nat-113/session_nat113.py --out artifacts/nat-113/run-001 --image loader-diag-xnu-sc3-md1 --execute
    python3 docs/procedures/nat-113/session_nat113.py --out artifacts/nat-113/restore-001 --image loader-diag-xnu-sc3-md1 --restore
    python3 docs/procedures/nat-113/decode113.py artifacts/nat-113/run-001/archive --json artifacts/nat-113/run-001/pixels.json --ppm artifacts/nat-113/run-001/thumb.ppm
    python3 docs/procedures/nat-110/analyze_nat110.py ...   # Stage C rows, as for NAT-111
    python3 tools/lab.py project permit --scope native --value false --decision docs/decisions/NNNN-nat113-...md --owner OWNER
