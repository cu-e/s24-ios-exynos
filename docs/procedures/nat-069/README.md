# NAT-069: `loader-diag-xnu-ne2-usb` — NAT-067's PID 1 image with a read-only dump of the display engine

Evidence kind: **host-test** (derivation, static reads of the real payload and of the pinned display patch, the derived driver and the extended analyser against simulated archives, the real NAT-068 log and text rendered from the patch's own format strings). Nothing ran on the phone.

## Why (the question, the observable, the decision)

`docs/strategy/2026-11-12-ios-critical-path.md` puts a working path from a user process to the physical panel at milestone 4. Which path depends on one fact the project has not measured: whether the display engine that S-Boot/the loader left
running scans out the framebuffer the kernel console draws into (physical `0xfa200000`, 1080x2340, stride 4320, reported on hardware in NAT-068). The pinned patch `0010-e1s-display.patch` already prints a read-only dump of the DECON, DECON0 window,
RDMA, DSIM0/1, DCPHY0 and DPU_MIPI_PHY_CON registers when the boot-arg `e1sdisp=2` is given; no image has had it set.

* **Question:** do those registers describe a running pipeline whose source is the loader's framebuffer?
* **Observable:** the `e1s-display:` lines in the log chain, read by `analyze_nat069.py` into `display.fork`.
* **Decision it feeds:** `scans-loader-framebuffer` keeps the framebuffer-copy path for milestone 4 and UI-003 (full display bring-up) off the critical path; the other complete readings (`pipeline-idle`, `decon-running-no-enabled-rdma`,
  `rdma-reads-framebuffer-decon-idle`, `scans-other-buffer`) move UI-003, or a closer look at the named register, ahead of the first SpringBoard attempt; `cannot-map`, an abort or a hang means a loader-side power/clock step or a one-window-per-run bisection image comes first.

## What was built

| item | value |
| --- | --- |
| image name | `loader-diag-xnu-ne2-usb` (same length as NAT-067's, so the loader moves nothing) |
| RECOVERY image | `artifacts/nat-069/package-001/loader-diag-xnu-ne2-usb/recovery.img`, SHA-256 `5abd894377a46bf67dcd17b494ef548944ee6201eea583b17a56f26a48c5b0de` |
| `Image.payload` | SHA-256 `192de4b60fc690f7bcd1f4cf45d75f224e1c39f6e70961015e56634e6ec84ac0`, 21878704 bytes |
| kernel command line (237 bytes) | NAT-067's with `NAT067-md0` -> `NAT069-md0` and ` e1sdisp=2` appended |
| everything else | NAT-067's: loader, stub, USB log chain, kernel, ADT, 16635-byte probe-init ramdisk (byte-identical) |

Byte diff against NAT-067's build: the loader `Image` differs in 12 bytes (five immediate words carrying the boot id and the image name), the XNU payload in 11 bytes (one tag digit and ` e1sdisp=2` inside the command-line field), the ramdisk in none.
`build.py` loads NAT-065's build and replaces three module values; two builds (`build-001`, `build-002`) give identical hashes. `derive.py` derives `session_nat069.py` (the driver) from NAT-067's by asserted text substitution (`derive.py --check`
compares the committed file with the derivation). `analyze_nat069.py` wraps NAT-065's analyser (which wraps NAT-062's) and adds the `display` reading.

## The display reading

`parse_display()` reads the `e1s-display:` lines into the framebuffer report, the four DECON instances, the DECON0 windows, the four RDMA channels, DSIM0/1, DCPHY0 and DPU_MIPI_PHY_CON, and `fork_of()` classifies them:
`no-display-text`, `no-usable-framebuffer`, `framebuffer-only`, `cannot-map`, `pipeline-partial`, `pipeline-idle`, `decon-running-no-enabled-rdma`, `rdma-reads-framebuffer-decon-idle`, `scans-loader-framebuffer`, `scans-other-buffer`.
A scan-out fork requires a complete pipeline (4 DECON, at least 4 windows, 4 RDMA, 2 DSIM or DSIM1 reported as unmappable with DSIM0 present, DCPHY0 and PHYCON); "inside the loader's framebuffer" means `phys <= address < phys + stride*height`.
Every reading that names a scan-out state carries the caveat that register values at one moment do not show that the panel presents CPU writes to that buffer.

## Host tests (`test_nat069.py`, 39 tests, 0 skipped) and mutation run (`mutants.py`)

* Build: two builds identical; the record carries the changes and NAT-065's pins; the command line is NAT-067's with the new tag and ` e1sdisp=2`; a command line that already has it is refused.
* Payload: five loader immediates differ from NAT-067's (six from NAT-065's); the XNU payload differs only in the command-line field; the ramdisk is NAT-067's; `Image.payload` is the loader followed by the payload; the package record's pins are the files'.
* Kernel (static, on the real payload kernel and the pinned patch): the patch's format strings are the ones the analyser reads and the payload kernel carries them; the probe and `bsd_init` are in the kernel's symbols; `bsd_init` calls the probe once and `e1sdisp` defaults to 1;
  the pipeline function makes only `ml_io_map`, one-load `e1s_display_read` and `printf` calls and no store through a mapped pointer; every offset read lies inside the window mapped for it; the pipeline runs after the framebuffer report and only for mode 2.
* Driver: the committed file equals the derivation; the derivation changes only the listed lines and uses the values it is given; a drifted NAT-067 driver is refused; the pins, paths and gates on a temporary tree (decision file, both hashes, `decision 0019`, `native`, each required task done up to NAT-069).
* Display reading: text rendered from the patch's formats is read back field for field; each fork; a missing line in the middle is `pipeline-partial`; a scan-out that needs a running pipeline gets one; DSIM1 unmappable is a complete reading; no display text or a console without framebuffer;
  duplicate dumps collapse; a pipeline without the framebuffer report cannot be called the loader's buffer; the real NAT-068 text gives the framebuffer report and no pipeline, and rendered pipeline lines inserted into the real log are found with the root verdict unchanged.
* Analyser: NAT-065's under the new name; the real NAT-068 text is `probe-ran-to-exit`; a boot of the previous image is not accepted; the command-line tool runs under the new name.
* Mutants: 65 (source B/D/S/A/M, patch P1–P8, artifacts X1–X4); 63 killed, 2 equivalent (D9, M10; reasons in `mutants.py`), 0 survived, 0 invalid.

## Established, not established

* Established (host-test): the image is reproducible and differs from NAT-067's only where listed; `e1sdisp=2` is parsed by the pinned patch, which maps seven windows and only reads them (offsets inside the mapped sizes); the driver and analyser cannot be used for another image or without the decision file;
  the analyser separates the five scan-out readings from the findings that are not (cannot-map, partial, framebuffer-only, none).
* Not established: whether the seven windows are readable in the loader's power/clock state (a gated block can abort, SError or hang the bus); what the registers contain; that the patch's register layout (from UI-007's source derivation) matches the silicon; that the panel shows the framebuffer; anything about the GPU.
  Resolved, or not, by the run in NAT-070.

## Next

NAT-070 (native): promote `decision-draft.md` to decision 0029, commit it, open `native` citing it, one launch of `session_nat069.py --image loader-diag-xnu-ne2-usb --execute` (pyusb venv python), restore the pinned stock RECOVERY, check Android, analyse with `analyze_nat069.py`.
Pass rule: chain PASS and a complete reading in `display.fork`; `root.outcome` is reported next to it.

## Files

`build.py`, `derive.py`, `session_nat069.py`, `analyze_nat069.py`, `test_nat069.py`, `mutants.py`, `decision-draft.md`, `evidence.json`. Build/package/test/mutant artifacts are in the gitignored `artifacts/nat-069/`.
