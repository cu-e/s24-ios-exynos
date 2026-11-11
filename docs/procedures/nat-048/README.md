# NAT-048 — Gated session driver, host USB event logger and verdict analyzer for the reset canary run (host-test)

Evidence kind: **host-test**. Nothing here ran on the phone. The driver was exercised only against a fake `adb` and a fake
sysfs tree; its real-tree tests prove that with no decision file it makes no adb call at all.

## Why this exists

NAT-046 (first native run of the NAT-044 reset canaries) measures four unknowns, U1-U4, **only through what the host can see**:
whether the loader's PMU stores reset the SoC at a deadline inside the 83 s watchdog (U1+U2) and whether S-Boot then honours
the Download/Bootloader word in INFORM3 (U3/U4). That needs (a) a driver that writes only RECOVERY, only the pinned package, only
after a recorded decision, with one reboot; (b) a timestamped host record of USB enumeration that is already running when the
reboot is requested; (c) one place where the verdict wording of `docs/procedures/nat-044/decision-template.md` is applied to
that record. Runs 001-009 had none of (b) and (c): the only USB observations were taken by hand.

## Files

| path | role |
|---|---|
| `usb_watch.py` | polls `/sys/bus/usb/devices` (default 10 Hz) and appends fsynced JSONL: `start` (devices present), `appear`, `disappear`, `change`, `stop`, each with wall-clock `t_unix` and `t_mono`. A device that re-enumerates between two polls is a `disappear` + `appear`. Reads only the sysfs attributes idVendor, idProduct, product, manufacturer, busnum, devnum; never opens a device node, never reads the serial number, never sends a request. Default vendor filter 04e8 / 18d1 / 1209 (the phone's identities and the NAT-041 monitor), so the log does not list other peripherals |
| `analyze_reset.py` | `--events usb-events.jsonl --report report.json --build artifacts/nat-044/build-002 --image NAME`: `supported` / `refuted` / `undetermined` for U1+U2 and U3/U4 with the timestamps they came from. Never infers from missing data |
| `session_reset_canary.py` | the NAT-037 driver (`--image {loader-diag-reset,loader-diag-reset-bl}`), pinned to the NAT-044 **package-002** hashes (RECOVERY, `Image.payload`, its length at offset 2048). Differences from NAT-037, all enumerated in a test: the pinned names, the decision gate, the one-shot marker per image, the watcher |
| `test_nat048.py` | 65 tests (UsbWatch, Analyzer, RealTreeGate, OpenGateFlow) |
| `mutate_nat048.py` | 68 mutants of the three scripts |
| `evidence.json` | the task's evidence record |

## Gate and sequence of the driver

1. Every mode (preflight, `--execute`, `--restore`) first checks the local pins (stock image, package-002 record, candidate hash) and
   then the **decision file**: exactly one `docs/decisions/*-nat046-<image>-single-run-*.md`, containing the RECOVERY SHA-256, the
   `Image.payload` SHA-256 and the words `decision 0019`. Without it the script stops with no adb call. It never creates the file:
   the agent writes it under decision 0019 from `docs/procedures/nat-044/decision-template.md` before the run.
2. Device checks as in NAT-037 (model, device, PDA, boot completed, RECOVERY is `/dev/block/sda18` with the known size, no remote
   `dd`, stock hash unchanged, battery >= 50 % and < 42 °C, no odin4/heimdall process).
3. **Watcher self-test** (preflight and `--execute`): `usb_watch.py` runs for one second into `usb-selftest.jsonl` and must log
   `start` ... `stop`. A broken watcher stops everything before the first write.
4. `--execute` only: one-shot marker `artifacts/nat-048/native-attempt-<image>-used.json` (`open('x')`), full-image write to RECOVERY,
   full-hash readback, then the watcher is started **detached** (`start_new_session`, 240 s) and the driver waits for its `start`
   record. If that does not appear: stock is written back, no reboot.
5. Exactly one `adb reboot recovery`; its timestamp `reboot_requested_at` is T0 in the analysis. The driver exits; the watcher keeps
   running for 240 s (the baseline SEC_UPLOAD window of runs 001-009 was +95 .. +118 s).
6. Any failure after the write and before the reboot restores the pinned stock RECOVERY (readback checked). No retry.

The restore after the run itself (NAT-013 with the pyusb venv python on a device whose iProduct is `SAMSUNG USB`) is not part of
this driver.

## Verdict rules (analyze_reset.py)

T0 = `reboot_requested_at` of the driver report. `deadline` and `wdt` come from the NAT-044 build record of the image
(45 s / 83 s). The phone left the bus when the first 04e8 device disappears after T0; its **first return** is the first 04e8
`appear` after that. Baseline of runs 001-009 (`docs/procedures/nat-022/README.md`, "USB vanish at +4 s and `SEC_UPLOAD` at +95 s"):
the loader sat in its hold loop until the 83 s watchdog and the host saw SEC_UPLOAD at about +95 s. The split point
between "reset at the deadline" and "watchdog reset" is `95 - (wdt - deadline)/2` = 76 s for 45/83.

| first return at dt | class | U1+U2 | U3/U4 |
|---|---|---|---|
| < deadline | any | undetermined (another cause) | undetermined |
| deadline .. split point | download or upload | **supported** | download: supported; upload: refuted |
| 95 s +- 10 s | upload (SEC_UPLOAD) | **refuted** (the baseline) | undetermined |
| any | android (a 04e8 Android identity) | undetermined | refuted (Download Mode not entered) |
| else | | undetermined | undetermined |

No return, or a log that does not cover the window (< 120 s after T0, no start record, a start after T0, no reboot request): `undetermined`
with the reason. Class: product `SAMSUNG USB` = download; `UPLOAD` in the product = upload; 04e8 with an Android PID = android.

## What is established, what is not

Established (host-test): the rules above on synthetic logs, including every boundary; the logger on a fake sysfs tree and as a real
process (SIGTERM = clean stop, SIGKILL leaves whole lines); the driver's gate and control flow against a fake adb: no adb call without
a decision file, in any mode and for either image, the order write -> readback -> watcher started and logging -> single reboot, one-shot
marker per image, stock restored on a readback mismatch or a watcher that cannot start, a detached watcher that outlives the driver and
sees later device events, the driver's safety lines equal to NAT-037's.

Not established, and not claimed: any behaviour of the S24. The fakes are not the phone. Whether `/sys/bus/usb/devices` shows a
Download Mode device the way the fake tree does is an assumption the first native run will test (the host did see SEC_UPLOAD and
SAMSUNG USB with `lsusb` in runs 001-009; the sysfs attributes are the same data). The log says nothing about **why** the phone
re-enumerated. A second Samsung device on the host's bus would be indistinguishable from the phone. The watcher covers 240 s;
Download Mode that appears later (an owner key entry) is outside the verdict window by design.

## Findings made while writing the tests

* The NAT-037 driver tests pin the real tree's root by `__file__`: a mutated copy of the driver outside the tree would see a
  different root and "fail" every real-tree test for the wrong reason (all mutants would look killed). `mutate_nat048.py` builds
  each mutant in a mirror tree with symlinks to the real `artifacts/`, `devices/` and `docs/decisions`.
* Two checks in the driver are redundant with the full-image hash pin and are **not** mutated: `digest(candidate[2048:2048+len]) ==
  CANARY_SHA` (if the whole image hash matches, the payload is where the package put it) and `pkg['stock_sha256'] == STOCK_SHA`.
  They stay as defence in depth; the property they protect (the payload, not the loader-only `Image`, is what is written) is tested by
  `test_the_candidate_packages_the_payload_not_the_loader_only_image` and the pinned-hash test.
* The first mutation run (`mutation-001`, 68 mutants) had one survivor, `W20-vid-case-sensitive-start`: nothing fed the watcher an
  upper-case sysfs vendor id, so dropping the `.lower()` on the recorded vid went unnoticed (the analyzer compares `vid == "04e8"`).
  `test_vendor_and_product_ids_are_recorded_in_lower_case_whatever_sysfs_says` was added (65 tests) and the whole run repeated as
  `mutation-002`: 68/68 killed, 0 invalid. `mutation-001` is kept unchanged.

## Run order for NAT-046 (needs the phone, the registry `native` permission under decision 0019, and the decision file)

```sh
# 1. decision file (agent-written, committed before the run): docs/decisions/00NN-nat046-loader-diag-reset-single-run-<date>.md
python3 -I docs/procedures/nat-048/session_reset_canary.py --image loader-diag-reset --out artifacts/nat-046/pre-001     # read-only preflight
python3 -I docs/procedures/nat-048/session_reset_canary.py --image loader-diag-reset --out artifacts/nat-046/run-001 --execute
# wait 240 s, then
python3 -I docs/procedures/nat-048/analyze_reset.py --events artifacts/nat-046/run-001/usb-events.jsonl --report artifacts/nat-046/run-001/report.json \
    --build artifacts/nat-044/build-002 --image loader-diag-reset --out artifacts/nat-046/run-001/analysis.json
# 2. restore stock RECOVERY with NAT-013 (pyusb venv python, Download Mode device whose iProduct is "SAMSUNG USB"), or
#    session_reset_canary.py --restore while Android is up
```
