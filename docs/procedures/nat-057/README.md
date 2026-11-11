# NAT-057: session driver and analyser for `loader-diag-xnu-ckpt3-usb` (NAT-052 image)

Evidence kind: **host-test**. Nothing here ran on the phone, no `adb` command was sent to a device, no RECOVERY was written, and the driver's
preflight was **not** run in the real tree (NAT-043 is not done in the registry; the one real-tree test below runs the driver with a fake
`adb` on `PATH`: with no decision file it stops at the decision gate in every mode, and with decision 0024 present `--execute` stops at the real
registry gate, in both cases before any `adb` call).

## What this is

| File | Role |
|---|---|
| `session_nat052.py` | The NAT-049 session driver (`docs/procedures/nat-049/session_usblog.py`, itself the NAT-048 driver plus a USB watcher and the NAT-041 collector) bound to the NAT-052 package: one image, its pinned hashes, its decision-file glob, its one-shot marker, and two more registry preconditions. |
| `analyze_nat052.py` | Verdict for one run of the image: the NAT-049 archive-integrity / T0 / boot-id / USB-log rules (imported read-only from `analyze_usblog.py`) plus the `CK` stop notes read through NAT-052's `decode52.progress`. |
| `test_nat057.py` | 45 host tests (see layers below). |
| `mutants.py` | 56-mutant check of the gates and the verdict rules. |

### Driver: what differs from the NAT-049 driver

Exactly these lines (pinned by `Derivation.test_the_driver_differs_from_the_nat049_driver_only_where_the_task_says`):

* `IMAGES`: only `loader-diag-xnu-ckpt3-usb`, RECOVERY `a8161cccddb4282796a848b2c5b464d5457dcc0bb9bc2e0c1fa9cb1014967d97`, `Image.payload`
  `9d9cb972496807177771febf819d783f0823ecd2fb44fad2f9fadbfc3027440e` (21857888 bytes at offset 2048), from `artifacts/nat-052/package-002`.
* `PACKAGE`, `LAUNCHER`, `HOST_ACCESS` paths (the launcher and the udev check are NAT-049's, not copied).
* `REQUIRED_DONE = NAT-039, NAT-046, NAT-043, NAT-052`: the log channel must be proven on hardware (NAT-043) and the image must exist (NAT-052).
* the decision glob `*-nat052-loader-diag-xnu-ckpt3-usb-single-run-*.md` and the marker `artifacts/nat-057/native-attempt-<image>-used.json`.

Everything else (the write to `/dev/block/sda18` only, the full readback, the stock-hash and battery checks, the self-tests, the detached
watcher and collector confirmed before the single `adb reboot recovery`, restore-on-abort, the lock) is unchanged and its lines are pinned
by `Derivation.test_the_safety_lines_are_those_of_the_nat048_driver`. The driver never creates a decision file and never writes the registry.

### Analyser: verdicts

| Verdict | Condition |
|---|---|
| `PASS` | Live archive (`unqualified-live`), one boot of this image (boot-id tail = FNV-1a-64 of the image name), the banner `NAT047 loader-diag-xnu-ckpt3-usb deadline_s=.. fault=0`, contiguous frames and device sequence, no drops, both ladder summaries `err=0` with matching operation lines, manifest `complete-received-stream`, the end record with `unread_bytes=0`, the 22 notes `n=1..22` with the checkpoint values this image has at each position and the final-stop bit at `n=22` (checkpoint 16), and the `HOLD` record. |
| `PARTIAL` | The channel works (a boot of this image with records) but something above is missing; `why` names the last note (`n`, arrival, checkpoint) and the reasons list every gap. A final-stop bit before `n=22` or a wrong checkpoint value is a reason (this image has no shorter list). |
| `EXCEPTION` | The kernel's early-exception note (`esr= elr= far=`) or a loader exception frame/text/page arrived; the values are reported and transport problems are listed next to them. |
| `FAIL` | Nothing archived and the USB log shows that the loader ran (phone returned as Download Mode between the 60 s deadline and the ceiling, or as `SEC_UPLOAD` at the old watchdog time) but 1209:0001 never enumerated, or it enumerated and no record was archived. |
| `undetermined` | No T0, unreadable or corrupted archive, collector started after T0, first record before T0 or after 300 s, a boot of another image only, USB log and archive disagree, a monitor already on the bus, too short a watcher log. |
| `simulated-*` | `--allow-synthetic` on an archive whose provenance is not `unqualified-live`: never a plain verdict. |

A `PASS` here says that the host received a complete and orderly list of notes **as written by the image**. It does not say that XNU's
state is correct, only what the kernel reported at each stop.

## Tests (`test_nat057.py`, 45 tests, none skipped under the capture venv)

* **Derivation** (10): pinned hashes equal package-002 and the build-003 record; the diff against the NAT-049 driver is exactly the listed
  lines; the NAT-048 safety lines are present; the added lines add no device or host action; one reboot form, one RECOVERY path, two spawned
  processes; no decision file or registry writes; gates before the first `adb` call and the collector before the reboot; the analyser's stop list is the build record's.
* **RealTreeGate** (2): in the real tree the driver stops before any `adb` call: at the decision gate in preflight, `--execute` and `--restore` while no decision file exists (the state in which the driver was written), and, once decision 0024 exists, `--execute` at the real registry gate (`native` closed, NAT-043 not done); the test skips only if the real registry is open.
* **OpenGateFlow** (10): the driver in a scratch tree with a fake `adb` that models the RECOVERY block, the real NAT-048 watcher on a fake
  sysfs, and stand-ins for the collector launcher and the udev check: every decision, registry (10 cases), udev, self-test and device-check
  failure stops before the first write; a launch writes `/dev/block/sda18` only, reads it back, starts watcher and collector, and reboots once;
  a bad readback, a dead watcher or a dead collector restores stock and never reboots; the marker makes the run one-shot; `--restore` needs no registry.
* **Verdicts** (19): the analyser on archives written by the real NAT-041 collector from the DWC3 model with the ring seeded with this image's text formats.
* **Simulated** (4, needs unicorn, zig and the NAT-020 artifacts): the same analyser on archives of the real NAT-052 loader executed in the NAT-052 simulator; every verdict is `simulated-*`.

The Verdicts archives force the provenance label `unqualified-live` inside the fixture only to exercise the PASS path; they are not hardware evidence.

Run: `python3 -I docs/procedures/nat-057/test_nat057.py` (the Simulated layer is skipped without the capture venv); full:
`<venv with unicorn+capstone>/bin/python -W ignore -I docs/procedures/nat-057/test_nat057.py`. The 96 MiB RECOVERY copies of the flow tests go to the
gitignored `artifacts/nat-057/tmp` (the user's `/tmp` quota on this host was too small for them).

## Mutation check

`mutants.py` applies 56 single changes (28 to the driver: the registry preconditions, the decision gate, the marker, the readback, the
self-tests, the start order of watcher and collector, the restore-on-abort, the T0 ordering, the battery and `dd` checks; 28 to the
analyser: provenance, integrity, T0, boot-id, time windows, USB-log disagreement, the exception path, each note rule, the ladder, the end
record, the banner, the manifest, and the no-boot tail). Driver mutants run the flow tests with the source pins off, so a kill is behavioural.
See `evidence.json` for the numbers.

## Known limits

* The fakes are not the phone: the flow tests establish control flow and gates, not device behaviour; `adb`, the udev check and the collector launcher are stand-ins in the scratch tree (their real behaviour is NAT-049's).
* The analyser reads the text formats of NAT-052's `decode52.py`; the Simulated layer shows that the compiled loader produces them, not that the S24 does.
* NAT-043 is `in_progress` in the registry (the `task done` needs the `native` permit open, which was refused earlier this session); the driver's gate therefore refuses a launch until it is done. No run is possible, and none was attempted, before that and before a decision file and the owner's run-time confirmation exist.
