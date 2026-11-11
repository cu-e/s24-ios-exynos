# NAT-049: the unattended USB-log run (NAT-043) — session driver, collector launcher, host-access check and verdict analyzer

Evidence kind: **host-test**. Nothing in this directory has been run against the phone. The point of the task is that when
NAT-043 is run, the *computer* starts the collector before the single reboot, keeps the host USB log, and states the verdict from
what it received, without anyone filming the screen.

## What is here

| File | Role |
|---|---|
| `session_usblog.py` | The gated session driver. Derived from NAT-048's `session_reset_canary.py` (same RECOVERY-only write, full readback, one reboot, restore protocol). Differences: pinned names come from NAT-047 package-001; the decision file is `docs/decisions/*-nat043-<image>-single-run-*.md`; extra registry gate; udev check; collector self-test; **starts the USB watcher and the collector (both detached) after the readback and before the reboot, and waits for the watcher's `start` record and the collector's first `poll` of the bus.** |
| `collector_launch.py` | Runs the unmodified NAT-041 collector (`s24_logd.py`) with provenance `unqualified-live` and wraps its pyusb backend so every `find()` leaves an fsynced heartbeat (`start`, `poll` every 2 s, `found`, `error`). The collector writes nothing to its archive until a device appears, so the heartbeat is the only proof that it looks at the bus. `--selftest` opens no device. |
| `host_access.py` | Reads the udev rule text and says whether some rule gives this user write access to USB `1209:0001`. Reads files only; opens no device. |
| `70-s24-usbmon.rules` | The rule that gives group `adbusers` `0660` on `1209:0001`. **Not installed by anything in the project.** |
| `analyze_usblog.py` | The verdict: PASS / PARTIAL / FAIL / undetermined, in the wording of `docs/procedures/nat-047/decision-template.md`, from the collector archive, the NAT-048 host USB log and the driver's `report.json`. |
| `test_nat049.py`, `mutate_nat049.py` | Host tests and the mutation check. |

## One-time host step that needs the owner's root (NAT-050)

The collector opens `1209:0001` with libusb. Without a udev rule the usbfs node is `root:root 0664` and the open fails with EACCES
(`device-access-denied`); the single native run would be spent. This host has `51-android.rules` for `04e8` and `18d1` only, and the
collector refuses `04e8` by design (NAT-041). The invoking user is in `adbusers` (checked 2026-11-11). Install:

    sudo install -m 0644 docs/procedures/nat-049/70-s24-usbmon.rules /etc/udev/rules.d/70-s24-usbmon.rules
    sudo udevadm control --reload
    python3 -I docs/procedures/nat-049/host_access.py --check        # exit 0 once a rule grants access

The agent cannot do this (`sudo` asks for a password; using the `docker` group as a root bypass is not done). Until it is done
the driver's `--execute` stops at the udev check, before any adb call. `--check` reads the rule text only: it does not model
later rule files that override `MODE`/`GROUP`, name-based masking between rule directories, or `udevadm` itself. The proof that
the rule works is the first real open of the node.

## Running (after the gates are open)

    python3 -I docs/procedures/nat-049/session_usblog.py --image loader-diag-usbmon --out artifacts/nat-043/<attempt>            # read-only preflight
    python3 -I docs/procedures/nat-049/session_usblog.py --image loader-diag-usbmon --out artifacts/nat-043/<attempt> --execute  # the single run
    python3 -I docs/procedures/nat-049/session_usblog.py --image loader-diag-usbmon --out artifacts/nat-043/<attempt>-restore --restore
    python3 -I docs/procedures/nat-049/analyze_usblog.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json \
        --image loader-diag-usbmon --out RUN/analysis.json

The restore of the stock RECOVERY after the run is NAT-013's job (the pyusb venv python on a Download Mode device whose iProduct is
`SAMSUNG USB`), exactly as for NAT-046.

Gates, in the order the driver checks them (every one stops before the first adb call):

1. exactly one decision file `docs/decisions/*-nat043-<image>-single-run-*.md`, naming the RECOVERY and `Image.payload` hashes of the
   package and decision 0019 (this script never writes it);
2. the registry: `project.permissions.native` is true and its last `native` entry in `permission_decisions` cites that very file;
   `NAT-039` and `NAT-046` are `done`;
3. a udev rule that gives this user access to `1209:0001` (`host_access.py`);
4. the collector self-test with the pyusb venv python (pyusb imports, a libusb backend loads, nothing is on the bus yet);
5. the NAT-048 checks: pinned stock RECOVERY SHA-256, package record, device identity, battery, no other flasher, the watcher self-test.

After the readback: watcher start (record awaited) → collector start (first poll awaited) → the one `adb reboot recovery`. If any step
fails before the reboot the pinned stock image is written back (full readback) and the processes it started are stopped. After the
reboot nothing is retried and the driver exits; the watcher and the collector run for 360 s on their own.

## The verdict

Inputs: the archive directory (NAT-016 layout), the host USB event log, `report.json` (the reboot request time T0) and the image name
(the device boot id of an image ends with the FNV-1a-64 of its name, NAT-047).

| Verdict | When |
|---|---|
| **PASS** | one boot of this image, first record the image's banner, device record numbers contiguous from 0, no drop frame, stages in order from `loader_main`, both ladder summaries `err=0` with one line per access, an end record with no unread bytes, a complete manifest with no capture error and no collector drops; fault image: exactly one exception record with ESR `0xF2001234`, the EXCEPTION text, an engine exception page that is valid and agrees, the exception stage last. |
| **PARTIAL** | the boot of this image is there but one of the PASS conditions fails (the reasons are listed). |
| **FAIL** | nothing readable was archived and the USB log shows `1209:0001` enumerated (the permission cause is named), **or** it never enumerated although the log shows the loader ran (the phone left the bus and came back as Download/Upload between the deadline and the watchdog ceiling). |
| **undetermined** | everything else: no archive, a damaged archive, an archive that is not this run's (created after T0, first record before T0 or more than 300 s after it, boot id of another image), a USB log that is missing or covers less than 120 s after T0, a device that was already on the bus, disagreement between archive and USB log, no sign that the loader ran. |

A `synthetic` archive never gets a verdict of its own (`undetermined`, or `simulated-*` with `--allow-synthetic` in host tests).
The verdict is the host's observation of the transport; it says nothing about why the phone behaved as it did.

## Tests

    python3 -I docs/procedures/nat-049/test_nat049.py                                  # system python: the simulator layer is skipped
    <venv with unicorn + capstone>/bin/python -I docs/procedures/nat-049/test_nat049.py   # adds the simulator layer

`TMPDIR` on a disk with room is advised (the NAT-041 model and the NAT-047 builds go there).

| Layer | What it shows |
|---|---|
| HostAccess, Launcher | rule reading; heartbeat cadence, error pass-through, exclusive create, fsync; the real collector end to end against a fake `usb.core` |
| Verdicts | the analyzer on archives written by the real NAT-041 collector from the NAT-041 DWC3 model, with the NAT-047 text formats scripted into the ring: every verdict of the template, every PARTIAL reason, every undetermined path, corrupted archives |
| Simulated | the same analyzer on the archives of the **real built `loader.elf`** of both images run in unicorn (NAT-047): plain, fault, late plug, no cable, stopped ladder. Expected values come from the simulator's own view of the loader |
| RealTreeGate | in the real tree, without the decision file, the driver stops before the first adb call in every mode and for both images; its pins are NAT-047 package-001's; its safety lines equal NAT-048's; it never creates the decision file |
| OpenGateFlow | the driver in a scratch tree with a fake decision file, fake registry, fake `adb` that models the RECOVERY block in a file, the real NAT-048 watcher on a fake sysfs and a stand-in collector launcher: both background processes are confirmed before the reboot, the fake `adb` checks both logs at the moment of the reboot; every gate and every failure path never reboots |

## Mutation check

`mutate_nat049.py` makes 195 single-edit mutants of the four modules (22 host_access, 25 collector_launch, 84 analyzer, 64 driver).
Driver mutants run twice: first without the source-text pins (`NAT049_BEHAVIOUR_ONLY=1`), then with them, so that a mutant only a text
pin sees (lines inherited unchanged from NAT-048 whose exact text is the safety argument) is reported separately.
| Run | Scope | Result |
|---|---|---|
| `artifacts/nat-049/mutation-001` | all 193 mutants of the first version (106 tests) | 148 killed, 4 killed only by a source pin (D04, D16, D47, D63), **41 survived** |
| `artifacts/nat-049/mutation-002` | H, L, A and D17 on the final sources and 25 added tests | 131 killed, D17 only by a source pin, 0 survived |
| `artifacts/nat-049/mutation-003` | D04, D47, D63 against three added behaviour tests | 3 of 3 killed by behaviour |

Final: **195 mutants, 193 killed by behaviour, 2 killed only by a source pin (D16, D17), 0 survived, 0 invalid.** The driver (D) group was
not re-run as a whole after run 001: `session_usblog.py` is unchanged since it started (the mutants and the pins read the same
text), and the tests added afterwards can only kill more.

What the first run found (and the changes it caused):

* `host_access.py` read only three udev directories; udev(7) names `/usr/local/lib/udev/rules.d` and (on systems where it is not a link)
  `/lib/udev/rules.d` too. Both are added and a test compares the list with udev(7)'s (H11, H12, H21, H22).
* The `except OSError` around `Path.glob` could not fire (glob yields nothing for a missing or unreadable directory) and was removed; a
  test covers a missing, an unreadable and a non-directory path.
* 40 analyzer, launcher and access mutants survived because the tests asserted only the verdicts of whole scenarios. They are now killed
  by one table-driven test per `judge_boot` reason, per-check archive-corruption tests (chunk offsets, hash, length, trailing bytes, strict base64,
  unreadable events), the USB-log edges (coverage boundary, early monitor, foreign vendor, return before leaving), the launcher's exact
  argument list and error statuses.
* D16 and D17 (the watcher's and the collector's own `terminate()` on a failed start) are behaviourally redundant: the abort handler
  stops every started process (D18 kills its removal). Their text is pinned (three `proc.terminate()` lines), which is all that can be said.

Limits of the check: the mutants are single textual edits chosen by the author, so it says nothing about a second bug in the same place; the
mutation runs used the system python, which skips the Simulated layer, so that layer adds no kills of its own.

## Established / not established

Established (host-test): the control flow of the driver under fakes, including that the watcher and the collector are running before the
reboot is sent; the gates; the heartbeat; the verdict rules; that the analyzer agrees with the archives of the compiled loader run in
the NAT-047 simulator.

Not established: that the udev rule is installed or works (needs the owner's root; NAT-050); that `usb.core` + libusb behave on this host
as the fake does; anything the DWC3 model does not model; the behaviour of the S5E9945 USB block, the PHY and the ladder writes; that the
phone enumerates `1209:0001` at all; that the reset at the deadline brings the phone back to Download Mode without keys (NAT-046); any
GPU or kernel behaviour. The simulated loader's thread is a queue of calls, not S-Boot.
