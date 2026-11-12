# NAT-070: the display registers the loader leaves (native-device, 2026-11-12)

One native run of `loader-diag-xnu-ne2-usb` under decision 0031 (decision 0019 protocol). The image is NAT-067's with one extra boot-arg, `e1sdisp=2`:
after `devfs_kernel_mount` the payload kernel maps seven display register windows with `ml_io_map` and **only reads** them (DECON0, its windows, the RDMA channels,
DSIM0/1, DCPHY0, `DPU_MIPI_PHY_CON`), prints the values, and then runs the project's probe as PID 1 as in NAT-068. The host received the text through the
project's own log chain, with no camera and nothing for the owner to do. The phone was restored from the pinned stock RECOVERY with NAT-013 and Android was checked afterwards.

**Outcome of the pre-registered rule: PASS** (chain verdict PASS from `analyze_nat062.py` logic inside `analyze_nat069.py`, and a complete `display.fork`). The fork label is
`decon-running-no-enabled-rdma`, which the decision text maps to "revisit the dump window or the channel choice before any decision". Section "Reading" below says what the numbers
support beyond that label, and what they do not.

Everything below is native-device unless marked otherwise. No Apple code ran. No pixel of iOS was shown. Whether the panel shows what the CPU writes to the framebuffer
was **not** observed (nobody looked at the panel and the dump has no register that answers it).

## What happened (native-device)

| quantity | value |
| --- | --- |
| image | `loader-diag-xnu-ne2-usb`, RECOVERY SHA-256 `5abd8943...b0de`, written to `/dev/block/sda18` only, read back equal; stock `96620b8b...bf67` before and after |
| reboot requested | 2026-11-12T10:21:01.448Z |
| Android left the bus / `1209:0001` appeared / left / Download Mode | +6.57 s / +18.78 s / +76.01 s / **+79.84 s** (`04e8:685d`, iProduct `SAMSUNG USB`, not SEC_UPLOAD) |
| collector | 1 boot, 450 frames, 448 records, no drop, no fault, no reset; 191,770 bytes received; end `disconnect`, 0 unread |
| loader | 27 checkpoint stops (n=1..27, final 21), the kernel's own return (reason-0 note n=28), then HOLD; banner `NAT047 loader-diag-xnu-ne2-usb deadline_s=60` |
| kernel log | 25,456 bytes returned (266 records); `SWEET userspace: init running as PID 1`, `SWEET probe: done, exiting`, then `initproc failed to start ... exit status 81` (the probe's designed exit, as in NAT-068) |
| `display` reading | 24 lines, read once at kernel time 40.5 s; **no abort, no SError, no hang; no `cannot-map`**; all seven windows were readable in the loader's power/clock state |
| restore | NAT-013 `restore_stock.py restore` exit 0 at 10:23:29Z (Download Mode device `5/115`); Android booted (`sys.boot_completed=1` by 10:24:08Z); `check_android.py` pass: RECOVERY equals the pinned stock hash, user data directories present; `assess` pass |

## The registers (as the kernel printed them)

| group | printed | decoded by the patch / UI-007 note |
| --- | --- | --- |
| framebuffer | 1080x2340, depth 32, stride 4320, phys `0xfa200000`; first words `0xffffffff 0xffffffff 0 0` | the console buffer of NAT-068 |
| DECON0 | version `0x7030100`, frame counter **1686**, `GLOBAL_CON` `0x133`, opmode 0 | bit 8 command mode, bit 4 run status, bits 1/0 enable |
| DECON1-3 | version `0x7030100`, frames 0, `GLOBAL_CON` `0x20` | not running |
| DECON0 windows | win0, win1: `con 0` off; **win2 `con 0x1` on, win3 `con 0x11` on**, both (0,0)-(1079,2339), secure `0x1` | `WIN_EN` bit 0, `CHMAP` bits 7:4 = channel 0 and channel 1 |
| RDMA0, RDMA1 | enable word `0x40000000`, format 0, **1080x2340, base `0xfa200000`**, stride word 0 | frame size and base address equal the console framebuffer |
| RDMA2, RDMA3 | enable word `0x40000000`, size 0x0, base 0 | unused channels |
| DSIM0 / DSIM1 | version `0x2090300`, link `0x42000 0 0 0x20` / `... 0x10`, video 0, PLL 0, stable 0, HS clock 0, stop-clock 1, stop-data `0xf` | no video mode, link in stop state |
| DCPHY0 | PLL `0x1`, lock 1, ready 1, enable 1 | D-PHY powered |
| `DPU_MIPI_PHY_CON` | `0x1` | |

## Reading

* **Formal result (analyser unchanged since before the run):** `display.fork = decon-running-no-enabled-rdma`, because no RDMA enable word has bit 0 set. Decision text for the label: the dump window or channel choice has to be revisited before any decision.
* **That label depends on an assumption the sources do not support.** The patch decodes bit 0 of the RDMA word at offset 0 as "on". The UI-007 note (derived from the pinned Samsung kernel source) lists no enable bit for that word, and the Galaxy S9 donor driver
  (`references/hakios-scion-full/drivers/gpu/hakios.exynos_dpu.c`, itself read from Samsung's `dpu_9810`) defines only bit 2 (busy) and bit 4 (SFR update force) for it. The value `0x40000000` is identical on the configured channels (0, 1) and on the empty ones (2, 3), so it carries no
  "enabled" information; bit 30 is not explained by any source read so far. The same applies to the DSIM status-bit decode (the patch's assumption) and to the stride word (UI-007: it is written only for SBWC, so 0 is expected for a linear buffer).
* **What the other numbers say (source-review of measured values, not a new measurement).** DECON0 is running in MIPI command mode (`GLOBAL_CON` bit 8, bit 4) and has sent 1,686 frames; two full-screen windows are on and map to channels 0 and 1; both channels are set to 1080x2340 at the console framebuffer's address;
  DSIM0/1 are not in video mode. That is the same structure the S9 donor documents for what Samsung's bootloader leaves ("DECON0 in MIPI command mode, its frames started by the panel's TE, one window on one DMA channel whose IDMA reads the boot framebuffer"). It is consistent with the loader's framebuffer being the scan-out source; it is not a proof.
* **Not established:** that a CPU write to `0xfa200000` becomes visible on the panel; that the frame counter is still advancing after the loader (it was read once); that the trigger/shadow-update registers behave as on the S9. The dump did not include `HW_SW_TRIG_CONTROL` (0x070), `SHADOW_REG_UPDATE_REQ` (0x060), `DATA_PATH_CONTROL_0/1` (0x214/0x218), the IDMA IRQ word, or a second read of the frame counter.

## Decision this feeds (milestone 4, `docs/strategy/2026-11-12-ios-critical-path.md`)

Working assumption, provisional: S-Boot's scan-out is reusable. Milestone 4 starts from the donor's baseline (a user-space frame is copied into the boot framebuffer through `MiniIOMobileFramebuffer`, accepting tearing); the tear-free refinement (a new base address plus a shadow update) needs the registers listed above. UI-003 (a full DECON/DSIM bring-up)
stays off the critical path **until a visibility check fails**. The check that can flip it: a frame written by the kernel or a user process shows on the panel (one look at the panel during a run, or a second observable). The next display dump should (a) decode the RDMA word as bits 2/4, (b) add the trigger/shadow/data-path registers and the IDMA IRQ word, (c) read the frame counter twice a known time apart. That dump can ride on the same boot as the NAT-083 run.

## Files

* `artifacts/nat-070/` (gitignored): `preflight-001`, `run-001` (driver report, USB events, collector archive, analysis, kernel text), `restore-001`, `check-android.stdout`, `assess-001.stdout`. The kernel text is not committed (its version string contains the host user name).
* This directory: `README.md`, `numbers.json` (the figures above, from `analysis.json`), `evidence.json`.
