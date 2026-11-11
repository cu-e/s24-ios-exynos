# NAT-047 — `loader-diag-usbmon` images (host build + host/simulator test)

Evidence kind: **host-test**. Nothing here ran on the phone and nothing was flashed. The images are built, hashed and tested on
the host only. The Aarch64 layer is an instruction-level simulation (unicorn) of the built loader against the NAT-041 DWC3 host
model and the unmodified NAT-041 collector. It shows that the code compiled into the loader honours the contracts it was
written against; it is not the S24 and says nothing about whether the HSI0 block, the PHY or the SMMU behave as modelled.

## Why this exists

Every native run so far (001-009) was read from a camera recording of the loader's coloured bands. NAT-041 wrote a USB
control-endpoint log monitor and its host collector `s24_logd.py`; NAT-045 derived a USB bring-up ladder (L0-L8) from the
pinned vendor sources. Neither had ever been linked into the loader. NAT-047 builds that loader: the first image in which the
computer, not a camera, can receive what the native code says, including the registers of a CPU exception. The run that tests it
is NAT-043 (native, needs the phone and the registry `native` permission under decision 0019); this task only builds and tests
the images.

## What the images do

Base: the NAT-044 reset canary (the run-006 loader family + NAT-022 markers + NAT-027 aligned ADT + NAT-026 payload fix +
NAT-044 deadline and reset). On top, `patch_loader5.py` applies 11 exact-match hunks (1 in `marker.h`, 7 in `markerlib.c`, 3 in `loader.c`) (each anchor exactly once or nothing is
written) that call into `src/markerlib47.c`:

| hook | where | what it does |
|---|---|---|
| `nat047_bringup(log, len)` | `loader_main`, right after `LOADER_MAIN` | `ladder` rungs L0-L2 (read-only), then L3-L8 (the writing rungs, `-DLAD_WRITING_RUNGS`) into the engine; starts the engine; replays the loader log written so far; waits up to 3 s for the bus reset |
| `nat047_log_char(c)` | `log_char` | every character the loader logs goes into the engine's ring, in lines of up to 200 characters |
| `nat047_stage(s)` | `mk_stage` | every stage number becomes a record (`stage 0x..`, `stage_name`) |
| `nat047_poll()` | `mk_draw` once per band, `mk_wait_tenths` (both loop forms; `mk_hold` waits through it) | one `usbmon_poll` of the engine (answers EP0 requests, moves events); the engine is polled from the bounded loops only, never from interrupts |
| `nat047_hold(stage, code)` | `mk_hold`, before its loop | waits up to 8 s for the host to configure the device so the first pull is not lost; in the `-fault` image it then executes one `brk #0x1234` |
| `nat047_fault(slot, esr, elr, far)` | `mk_exception_loop` | writes the exception record (`EXCEPTION slot=.. esr=.. elr=.. far=.. spsr=.. sp=..`) into the engine's exception frame *before* anything is drawn |
| `nat047_show` | `mk_hold`, `mk_exception_loop` | draws the USB status frames (kind 13, MK_USB) in addition to NAT-022/NAT-044's own |

The engine (`docs/procedures/nat-041/engine/`) and the ladder (`docs/procedures/nat-045/src/`) are compiled **unmodified** from
their own directories; so is the NAT-042 reset module. Hashes of all of them are in `build.json`.

Two images, differing only in `NAT047_FAULT`:

| image | `NAT047_FAULT` | purpose |
|---|---|---|
| `loader-diag-usbmon` | 0 | text and stages over USB; the NAT-044 reset at the deadline (45 s, inside the 83 s watchdog) ends the run |
| `loader-diag-usbmon-fault` | 1 | the same, plus one controlled `brk #0x1234` in `nat047_hold` at stage `MK_ST_PRE_JUMP`, after waiting up to 8 s for CONFIGURED; the loader's exception path must deliver the register frame |

Boot id (16 bytes, in the monitor's `GET_INFO`): first 8 bytes little-endian `mk_cnt()` at bring-up, last 8 bytes FNV-1a-64 of
`NAT047_TAG`. The collector names a boot directory `000001-<nonce>-<32 hex id>`.

USB status word (kind 13 idx 0, also readable as engine record `MK_USB`): bit 0 engine up, 1 host connected (bus reset seen),
2 configured, 3 nonce set, 4 a CPU exception was taken, 5 the exception happened inside the engine (engine taken out of
service), 6 the HSI0 power domain was already on, bits 8..11 phase (idle, ladder-ro, ladder-write, engine-start,
connect-wait, up, stopped), bits 12..15 last completed ladder rung. Decoder: `decode47.py` (on top of NAT-022's `decode.py`).

## Files

| path | role |
|---|---|
| `build.py` | builds both images from a copy of the NAT-020 build-003 loader source (`--loader-source`), applies the NAT-022, NAT-044 and NAT-047 patches, compiles the engine, the ladder and the glue with the loader flags, fixes the payload header, writes `build.json`; `--check-only` compiles and exits |
| `patch_loader5.py` | the 11-hunk source patch |
| `src/markerlib47.c`, `src/usb47.h` | the new code |
| `decode47.py` | decoder for kind 13 |
| `test_support/glue47.c`, `sim47.py`, `rig47.py` | unicorn harness: the built `loader.elf` against the NAT-041 DWC3 model (its host steps run the *aarch64* `usbmon_poll` through a callback) and `s24_logd.py` unmodified |
| `test_nat047.py` | the tests (Patch, Build, decoder, Aarch64 layers); layers skip themselves with a reason when `unicorn`/`capstone`/`zig` are missing |
| `mutate_nat047.py` | mutants of the new code, the patch, the build rules and the decoder; each must fail a test (a mutant that does not build is INVALID, not killed; a mutant that survives needs a test or a written equivalence reason) |
| `package.py` | packages `Image.payload` of each image into a RECOVERY candidate (the NAT-044 packager, with its record checks) |
| `decision-template.md` | the decision text the agent fills in under decision 0019 before the native run (NAT-043); not a decision record |
| `evidence.json` | the task's evidence record |

Build and test (host only; needs `cc`, `zig`, the loader source copy of NAT-020 build-003):

```sh
python3 -I docs/procedures/nat-047/build.py --out artifacts/nat-047/build-002 --loader-source <copy of the run-006 loader source tree>
<venv with unicorn+capstone>/bin/python -I docs/procedures/nat-047/test_nat047.py
<venv with unicorn+capstone>/bin/python -I docs/procedures/nat-047/mutate_nat047.py --out artifacts/nat-047/mutation-NNN --jobs 5
python3 -I docs/procedures/nat-047/package.py --build artifacts/nat-047/build-002 --out artifacts/nat-047/package-001    # needs the pinned stock RECOVERY (local, not committed)
```

Run `python -I` with a python whose working directory has no `dis.py`/`json.py`-like shadows; `TMPDIR` must have room for the
mutation run (each mutant copies the six procedure trees).

## What the tests establish and what they do not

Established on the host: the patch applies and the images build reproducibly; at power-on the loader brings the engine up and
the collector, using only vendor control transfers, receives the boot record with the id, the loader text in order, the stage
records, the ladder report and, for the fault image, the full exception frame (ESR `0xF2001234`, ELR inside the loader, FAR,
SPSR, SP) with no drop accounting gap; with no host the loader still reaches the reset deadline with the same timing within the
test's tolerance; an engine exception takes only the engine out of service; the screen path draws the same status as USB.

**Not established, and the reasons the NAT-043 run exists:**

* The sim's DWC3 is NAT-041's reading of the databook. Real HSI0 clocks, PHY, power domain, SMMU/DMA and cache behaviour are
  unmeasured (U1-U4 of NAT-040/NAT-042). `refclk_hz` is 0 in this build, so `LPM_SEL` has no effect.
* There is no cache or MMU model: the engine's cache discipline is NAT-041's x86 test, not exercised here.
* The loader vectors do not capture `x0..x30`: the `x[]` of the exception frame is all zero (a limitation of the loader's
  existing vector code, not of the transport).
* Un-polled stretches (long loader phases that call neither `mk_draw` nor `mk_wait_tenths`) may let the host time out during
  enumeration; the sim cannot show that on hardware. The real idle poll cost was not measured.
* Simulated polling happens only at `usbmon_poll` entries; stage `0x20` is sent only after the engine is up, so earlier stages
  appear only as the replayed loader log.
* There is no `-ro` image: the read-only ladder (rungs 1-2) cannot fail in the device model, so a safe "look but do not write"
  variant carries no measured advantage and was not built.
* The screen is only a fallback: after an exception the USB frames appear on screen about 20 s later, which is past the 45 s
  deadline (visible only in the 63 s test build).
* `brk #0x1234` in `mk_canary_loop` is inherited dead code of NAT-022, not part of this task.
* Nothing here changes the answer to "does the S-Boot Download request work" (NAT-046 measures that).

## Run gating

NAT-043 needs: the phone attached; the registry `native` permission (decision 0019, set with `lab.py` and a decision file);
NAT-046's result (whether the loader's reset returns the phone to Download Mode, because the run's only automatic exit is that
reset); NAT-039 (read-only inventory of the live Android USB stack to cross-check the bring-up plan); a session driver that
starts `s24_logd.py` detached before the reboot request. One image per decision file; the fault image is a second run.
