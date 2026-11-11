# 0022: One native run of loader-diag-usbmon (2026-11-11)

Status: recorded by `claude-nat043-20261111-session` under decision 0019 (owner full-automatic mode) before the run. The file is committed before
any device access; an owner confirmation for the run itself is appended to it before the launch (the auto-mode classifier refused the unconfirmed
launch of NAT-046 on 2026-11-11, see decision 0021). Nothing here is run until the udev gate below is open.

## Preconditions checked when this file was written

* NAT-046 is done (commit 1f00d5f): after the loader's own PMU reset the phone re-enumerated as `SAMSUNG USB` at +73.0 s with no owner action, and
  the NAT-013 restore from that state returned Android with the stock RECOVERY (full-hash readback). The return path is therefore automatic.
* NAT-039 is done (9aa15ea): the live USB stack of the running Android was inventoried read-only and agrees with the NAT-040 plan (39 rows, 0
  mismatches); NAT-051 added that `pd_hsi0` is `on` in Android and that a debugfs `clk_summary` read restarted the phone through `SEC_UPLOAD`
  (disclosed below).
* **Not met yet:** the udev rule for the monitor identity 1209:0001 (`docs/procedures/nat-049/70-s24-usbmon.rules`, task NAT-050) is not installed;
  `docs/procedures/nat-049/host_access.py --check` exits 2. The NAT-049 driver refuses to start while that is so. The registry `native`
  permission is closed (false) after NAT-046 and is set again, citing this file, only when the run is about to start.

## Scope

Exactly one image: `loader-diag-usbmon`. The fault variant `loader-diag-usbmon-fault` is not part of this decision and needs its own file.

* RECOVERY SHA-256 `c6802dea4682a4bc993885bf525e2907e42e4eeebb964310da82ed79fef7212d` (100663296 bytes,
  `artifacts/nat-047/package-001/loader-diag-usbmon/recovery.img`).
* Packaged `Image.payload` (loader + XNU payload + ADT) SHA-256 `a90a93d77ea56d22b8af555d34bc91bf8871db8f12ed071bd534d16940d08b73`, 21853792 bytes
  at offset 2048.
* Loader-only `Image` SHA-256 `3b46f4e31488e7f58bf36a70fe0661d50cdae3d461877565bcbf2d5e9c529046`.
* Built by NAT-047 (`artifacts/nat-047/build-002/build.json`, packaged by `package.py`, repository commit `a667725`). The image is the NAT-044 reset
  canary (run-006 loader family) plus the NAT-047 patch, the NAT-041 usbmon engine (`usbmon.c`
  `37a53cbaa8887958107693f87e27e43c70b64a66ea791e10993d8f163fcdd205`), the NAT-045 ladder (`ladder.c`
  `211413b8a72a74bff67389a44dd8abfe3a7808f4d1b43f7ffca0aa7474515877`, `ladder_usb.c`
  `eedec2487f831424c6d378a0072dc736cd5ad81ef9cdd3dd187a5a6cfe1b3dcf`) and the unmodified NAT-042 reset module (`s5e9945_reset.c`
  `6be65500f2e4661b80f70b73c0c2bb21d5797a38257c6ec0ecaef7fcf307b391`). The kernel is not started: the run ends in the loader's hold loop and its
  reset at 45 s (reason `0x12345601`, as in NAT-046).

Sequence (the protocol of runs 001-009, NAT-046 and the NAT-049 driver `session_usblog.py`): gates (this file, the registry, the udev rule,
collector self-test, device checks, watcher self-test); one-shot marker `artifacts/nat-049/native-attempt-loader-diag-usbmon-used.json`;
full-image write to RECOVERY (`/dev/block/sda18`) only; full readback; the USB event watcher and the collector (`s24_logd`, pyusb venv python)
started detached and confirmed running; one `adb reboot recovery`; the run; then restore of the pinned stock RECOVERY (SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose iProduct is
`SAMSUNG USB`, followed by full-hash readback and an Android check. Any failure after the write and before the reboot restores stock and does not
reboot. No retry.

What the image does, in order: the loader start and the 83 s watchdog arm; at `loader_main` the ladder rungs L0-L2 (reads of the PMU status of
`pd_hsi0` and of CMU_TOP mux/gate/divider), then the writing rungs L3-L8: L3 powers the HSI0 domain only if the read says it is off and runs the
vendor CMU init rows, L4 reads the DWC3 `GSNPSID`, L5 releases the PHY isolation and runs USBCON `init_link`, the pipe3 detach and the eUSB2 PHY
initiation with read-backs (111 ops in L1-L5, `docs/procedures/nat-045/ladder_ops.json`), L6-L8 start the NAT-041 DWC3 engine at `0x17900000` and
wait up to 3 s for the bus reset. Every rung stops at its first failed read-back, timeout or liveness check with a code that names the rung and the
table row, never retries, and never writes a block that the domain state says is off. From then on the engine is polled from the loader's bounded
loops, and text, stages and the ladder report are served to the host collector over EP0 vendor control requests; the NAT-044 reset follows at 45 s.

## Device access granted (and nothing else)

As in decision 0017 for the base image, the PMU window `0x12860000` (offsets 0xb8, 0xbc, 0x190, 0x3c00 and the `pd_hsi0` window `0x12862000`
as the ladder table names it), CMU_TOP `0x22b20000` (the three read addresses of L2), CMU_HSI0 `0x17800000`, SYSREG_HSI0 `0x17820000`, the USB
control and PHY blocks `0x178a0000-0x178e0000` and the DWC3 `0x17900000-0x1790ffff`, exactly as the 111-op table lists them. No storage device and
no partition other than RECOVERY is written. On the host side the run opens only USB 1209:0001 (the monitor identity of the image) and reads
`/sys/bus/usb/devices` attributes; the NAT-013 restore opens the Download Mode device as in runs 001-009 and NAT-046.

## Pass/fail, fixed in advance

Observation is by the host only: the collector archive `artifacts/nat-043/<attempt>/` and the USB event log; the camera is not used. The rules are
those of `docs/procedures/nat-049/analyze_usblog.py`, unchanged after the run.

* PASS (transport): the archive holds one boot with the id of this image, the loader log lines in order, stage records and the ladder report, with
  a zero drop count and fsynced raw bytes.
* PARTIAL: the device enumerated as VID 0x1209 PID 0x0001 but fewer records arrived than the engine wrote (the archive states how many), or the
  ladder stopped at a rung (the report names the rung and the op).
* FAIL: no enumeration of VID 0x1209 although the loader was running (the host USB log says how far it got), or enumeration with no readable record.
* Undetermined: no host observation, or the host log does not cover the window.

The return path (reset at 45 s, then NAT-013 restore) is judged as in NAT-046; its failure does not change the log verdict. Nothing is retried within
the run. A result other than PASS is evidence, not a reason to run again.

## Addendum 2026-11-11 (before the run): what the NAT-053 audit changes for this run

The independent audit NAT-053 found that no native EP0 record has ever reached the host (NAT-046 saw USB enumeration only, with no collector
running). For this run that means, with no change to the image, the hashes or the granted access above:

* Coverage is shown, not assumed: the driver starts the USB watcher and the collector after the readback and before the reboot and refuses to
  reboot unless the watcher logged `start` and the collector logged its first `poll` of the bus (`collector-heartbeat.jsonl`). After the run the
  verdict uses those files, the collector's raw transfers and its terminal process status together; a collector that died early, or a USB log
  that does not cover the window, makes the run undetermined.
* Observation and inference stay separate. The USB return timing alone (the phone leaving the bus and coming back as `SAMSUNG USB`, or as
  `SEC_UPLOAD`) does not show that the loader executed, and the 95 s +/- 10 s `SEC_UPLOAD` band is a heuristic that attempt 007 (109.8 s) already
  broke. Only a valid `S24L` record in the archive is a message from the real run. Enumeration of 1209:0001 with no valid record is
  reported by what the collector saw (device absent, `EACCES`, timeout/STALL, or a record that fails validation), never as success.
* The analyser rules (`analyze_usblog.py`) are used as committed; its known overstatement (NAT-055) is corrected by reading the raw files, not by
  changing the rules after the run.

## Not granted

Any other image or partition, a second run, the fault image, HSI0 or other MMIO beyond the table above, the ACPM or any SMC call, GPU bring-up,
kexec, flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain changes, and any use of the udev rule or of `sudo` by the
agent (the rule is installed by the owner). The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay
intact.

## Known limits disclosed

* Source review, host and simulator tests only (NAT-041, NAT-045, NAT-047). The clock/PHY/PD sequence and the DMA/SMMU assumptions are untested on
  the S24; the HSI0 writes are the first writes to that block from this loader.
* NAT-051 (2026-11-11) showed that this kernel took the phone into `SEC_UPLOAD` and an automatic restart during a debugfs `clk_summary` read, cause
  not established. A register access to a clock or power domain that is not up is a plausible way to fault the bus; the ladder checks the domain
  state first, but that check is also untested on the S24. If the loader hangs, the 83 s watchdog is the failsafe; the phone then goes through
  `SEC_UPLOAD` and, as on 2026-11-11, restarted into Android by itself after about 47 s (one observation); Download Mode by keys is the fallback.
* x0..x30 are not captured by the loader's exception vectors.
* A run with no host observation is inconclusive. RAM contents are volatile.
