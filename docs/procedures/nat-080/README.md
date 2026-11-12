# NAT-080: session driver, delivery companion and analyser for the NAT-078 run (host-test)

Evidence category: **host-test**. Nothing in this directory was run on the phone, and no USB device is opened by any test. The companion
is exercised against the NAT-076 DWC3 model through the NAT-079 rig (the model machine with the engine up, the loader's receive phase
compiled from the loader sources, the real `tools/ios/root_send.py` sender). The analyser is fed texts that other code produced: the real
NAT-077 probe compiled for the host and run over images the tests choose, and records written by the real companion. None of that is the
Exynos 2400 controller, a real libusb stack, the S24's DRAM or a measurement of the host-to-phone rate.

## What this is for

NAT-079 built the loader image `loader-diag-xnu-rx-md1` that receives the 2.31 GiB root image over USB bulk-OUT into the md1 reserve and then
boots the payload kernel whose PID 1 is the NAT-077 hash probe. A native run of that image (NAT-078) needs three things on the host that the
NAT-075 run did not have:

1. a launcher that does what NAT-075's driver did (device checks, RECOVERY-only write with readback, watcher, collector, **one** reboot) and
   additionally starts the sender at the right moment;
2. a sender process that streams the root image only when the *device* says it is ready, survives a bus reset, stops at its own deadline and
   leaves a durable record;
3. an analyser that applies the pass table of `docs/procedures/nat-079/decision-template-nat078.md` (section 6) to what the run leaves behind,
   so the verdict is a function of the archive and not of a reader's impression.

Nothing here decides to run NAT-078. That needs its own decision file, written and committed before the run (the template names what it must
contain), and a `native` permit.

## Files

| file | purpose |
|---|---|
| `derive.py` | writes `session_nat078.py` from NAT-075's driver by asserted text substitution (`--check` compares the committed file with the derivation) |
| `session_nat078.py` | the derived session driver (committed, a plain file a reader can open; not run here) |
| `deliver_nat080.py` | the delivery companion: waits for the receive path, streams the image with `root_send.py`, records the device's own view |
| `analyze_nat080.py` | the verdict: rows 1-10 of the pass table from the NAT-065 chain, the loader's values, the companion's record, the probe's lines and the ending |
| `test_deliver80.py` | 85 tests of the companion |
| `test_analyze80.py` | 62 tests of the analyser (46 + 16 added after the first mutation pass) |
| `test_nat080.py` | 18 tests of the derivation and the driver's sequence |
| `test_coexist80.py` | 7 tests: the real NAT-041 collector and the companion's sender on one model device (see below) |
| `mutate_nat080.py`, `mutation.json`, `equivalent.json` | mutation pass over `deliver_nat080.py`, `analyze_nat080.py`, `derive.py` and the reasons for survivors |

## How to run

```
# all tests need the Unicorn/pyusb venv of NAT-065 and a C compiler; TMPDIR must not be on the quota-limited /tmp
TMPDIR=~/.cache/nat059-tmp artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-080/test_deliver80.py
TMPDIR=~/.cache/nat059-tmp artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-080/test_analyze80.py
TMPDIR=~/.cache/nat059-tmp artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-080/test_nat080.py
TMPDIR=~/.cache/nat059-tmp artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-080/test_coexist80.py
python3 docs/procedures/nat-080/derive.py --check          # exit 0: session_nat078.py is the derivation from the pinned package
```

`-B` matters: `-I` ignores `PYTHONDONTWRITEBYTECODE`, and a stale `.pyc` can make a rewritten module look unchanged.
`test_nat080.py` and parts of `test_analyze80.py` skip what needs `artifacts/` (the NAT-079 package, the padded root's record, the archived
NAT-068/NAT-075 runs) when it is absent; with the artifacts present nothing is skipped.

## The session driver (`session_nat078.py`)

It is NAT-075's driver with only documented substitutions, so the safety sequence is the one that already ran on the phone: the standing
checks, the RECOVERY-only write under decision 0019, readback, restore on failure, watcher, collector, one `adb reboot recovery`, no retry.
`derive.py` counts every substitution; a NAT-075 driver that drifted, or one with a NAT-075 name left over, fails the derivation instead of
being half translated. What differs from NAT-075's driver:

* the image, its pinned hashes (RECOVERY, Image.payload), the package path, the decision-file glob (`*-nat078-...-single-run-*.md`) and the
  one-shot marker are NAT-079's and NAT-078's;
* the registry gate needs NAT-075, NAT-076, NAT-077, NAT-079 and NAT-080 done as well;
* the preflight also checks the padded root (size and SHA-256, streamed), the companion's self-test and that the companion's send time plus a
  margin fits inside the loader's receive cap recorded in the build record (wait 300 s, send 225 s, margin 15 s, cap 240 s);
* **after the collector is confirmed polling and before the single reboot** the companion is started detached and its `loaded` record (the
  image read into memory and verified) is awaited; a companion that does not report it stops the launch like the watcher and the collector do;
* the watcher and collector run for 600 s (the loader holds to its 360 s deadline and Download Mode follows about 30 s later).

The driver was **not run**. `test_nat080.py` pins the derivation (the committed file is the derivation from the package's values), the list
of replaced lines (every other line of NAT-075's driver is kept, in order), what is added (no device access of its own, no second reboot,
no retry, the companion started with options it accepts), the constants against the package and the padded root's record, and the refusals.

## The companion (`deliver_nat080.py`)

* Opens nothing until the file is checked: the file must be exactly the named size and SHA-256, a multiple of 16 KiB, and `--out` must not exist.
* **Readiness is a property of the device.** It polls GET_RX with the device *unconfigured* (endpoint 0 only, the same kind of control transfer
  the NAT-041 collector uses) and sends nothing until the reply says the receive path is present, the capacity is exactly the image size
  (before the loader's handoff the engine reports a 512-byte placeholder), nothing is committed and the state is IDLE. Any other capacity,
  committed bytes or an armed transfer is *refused*, not waited out.
* Then it configures the device **once** (the bulk endpoint exists after `SET_CONFIGURATION(1)`) and runs the unmodified sender through a
  metering transport: bytes the device accepted, progress records with the host clock and rates, the delivery deadline (counted from the moment
  the device was ready) enforced before each write and `RX_BEGIN`. The deadline is not an error the sender would retry.
* After the sender returns or gives up it reads the device's own view (GET_RX) and ends a chunk left armed with `RX_ABORT`. Only the device's
  committed offset is reported as delivered.
* The record is `delivery.jsonl` (fsynced JSON lines: start, loaded, waiting, ready, progress, sender, reconnect, final) and `delivery.json` (the
  summary, written last). Exit status 0 delivered, 1 failed, 2 refused before opening anything, 3 cap-reached, 4 never-ready, 5 refused by the device.
* It never reboots anything and does not retry the sender. The collector only issues vendor control transfers on endpoint 0 (requests
  0x01-0x05); the sender uses 0x06-0x08 and the bulk-OUT endpoint. `test_coexist80.py` runs the two together on the model (next section).

## The analyser (`analyze_nat080.py`)

It decides nothing about the phone; it reads delivered text and host-side observations and applies the pass table. Inputs: the NAT-065
chain's verdict for the boot (under this image's name), the loader's own values (`nat079_status`, `nat079_committed`, ... as `key=0xHEX`
records and `NAT079 rx MiB=...` progress lines), the companion's record, the probe's lines in the kernel text compared line by line with the
host's SHA-256 of the corresponding **prefix** of the root file (recomputed from the file, in one pass), and the ending (the host's first
return of the phone classified against the NAT-068/NAT-075 deadline clock scaled to 360 s: cap reset 364.0-405.0 host seconds).

Rows (the numbers are the decision template's): 1 pass; 2 digest or length mismatch inside the delivered span; 3 short transfer (3a: delivery
complete, hash cut short, reported as row 3 with `variant="a"`); 4 SEC_UPLOAD ending with a cut hash; 5 `/dev/rmd1` cannot be opened; 6 read
failure or empty device; 7 the delivery path never worked; 8 anything else; 9 the loader refused or distrusted the receive phase; 10 a chunk
failed its checksum repeatedly. The rows are tried in the order 9, 7, 10, 2, 5/6, 3, then 1/3a/4/8 and everything the rule used is in
`facts`. Row 1 needs all of: chain verdict PASS, companion delivered, loader status done, loader reserve equal to the image size, the probe's
final line equal to the host digest of the whole image, every progress line equal to its host prefix digest, PID 1 exit 81, ending cap-reset.
A line that covers bytes the device never reported as committed is not judged. The probe's exit classes are checked against the numbers in
the NAT-077 source, not against a copy of them.

## The collector and the sender together (`test_coexist80.py`)

The unmodified NAT-041 collector (`s24_logd.Collector`, writing a real archive) follows the model device through a backend that forwards its
control transfers to the model, while `deliver()` streams the image with the real `root_send.py` sender. The model is one C state machine, so the
two take strict turns: before every bulk write (and every 0.2 s wait) the sender gives the bus to the collector for one cycle. The order of events
is the same on every run. The tests show, for a chunk that has just been armed and for a chunk that is half received:

* every transfer the collector makes is one of GET_INFO / READ_RING / GET_EXC / SET_NONCE / PEEK on endpoint 0 and returns ok (no timeout, no
  stall), one run (`sessions == boots == 1`, no reset detected), and the nonce is set once;
* the image still arrives exactly (the reserve equals the image, nothing outside it changes, no model violation), and the collector's archive
  accounts for every byte of the device's log stream, including texts written while chunks were armed, and ends with `collector-stop`;
* one bus reset in the middle of a chunk, and three between chunks, are survived by the sender's reconnect and resume (as in the companion
  tests) and by the collector in the *same* run: the device's own reset counter, read by the collector, shows them.

What this does not show is libusb. The adapter cannot claim an interface, set a configuration or reset the device, and the model has no
interface claim to conflict with, so "no EBUSY" holds only in the sense that the collector's backend interface cannot cause one. Whether the
host's USB stack lets the collector keep issuing endpoint-0 transfers while pyusb runs `set_configuration` is decided on the real device.

## What the tests show

* The companion sends nothing before the device says it is ready, waits through the placeholder, refuses every other capacity or a device that
  holds state, configures once, delivers the exact image through the engine model (the reserve equals the image, nothing outside it changes),
  survives one and three bus resets, stops at the deadline without a retry and ends the armed chunk, reports lost DMA found by the sender, and
  leaves the record on disk for every ending with the exit status the driver expects. Waits, deadlines and rates come from a hand-driven
  clock with the arithmetic in the comments; rounding, clock offsets and boundaries are pinned with values that do not round on their own.
* The analyser gives each row of the table for a cause that is produced by the real probe or the real companion over a device the test
  chooses (a flipped byte localised to the first line that covers it, a stale tail, a read that fails, a device that does not open, a short
  transfer judged only over the delivered span, the precedence between rows), reads the archived NAT-068 and NAT-075 runs without
  mistaking them for this image's boot, and refuses a root file that is not the image the run is judged against.
* The derivation is the committed driver, replaces exactly the documented lines, and refuses a drifted NAT-075 driver.

## Mutation pass

`mutate_nat080.py` (generators from NAT-076's `mutate_rx.py`, a runner that kills the whole process group of a hung test, `TMPDIR` off `/tmp`,
sources snapshotted at the start, template text skipped). Final pass `artifacts/nat-080/mutation-run3` (copy: `mutation.json`), run against all four test files:

| target | candidates | killed | survived | invalid (do not parse) |
|---|---|---|---|---|
| `deliver_nat080.py` | 318 | 316 | 0 | 2 |
| `analyze_nat080.py` | 606 | 570 | 0 | 36 |
| `derive.py` | 105 | 101 | 1 (equivalent, reason in `equivalent.json`) | 3 |
| total | 1029 | 987 | 1 | 41 |

Invalid mutants are syntax errors only (checked: none was lost to a full disk or a timeout of the runner). The one survivor is
`main(sys.argv[1:])` -> `main(sys.argv[0:])` in `derive.py`: `main()` only asks whether `--check` is in its argument list and `argv[0]` is the
script's path, so the two calls behave identically.

The first pass (`mutation-run1`, 1035 candidates, 994 valid) had 107 survivors: 51 in the analyser, 41 in the companion, 15 in `derive.py`. They
were triaged, not waved through: most were real gaps (no test fixed a rounding, an exit-class number, a message, a boundary or what main()
writes) and were closed with tests whose expected values are worked out by hand; three lines were dead code and were removed (`classify_root`,
two initial assignments); the return-class expression was restructured so that it has no redundant comparison. The second pass (`mutation-run2`, same 1029 candidates) had three survivors: a boundary of the signed-status reading in the analyser, the
read-block size of the streaming hash in the companion (both closed with tests whose values are worked out by hand; the mutants were
re-applied and the new tests fail on them) and the `argv[0:]` one above (equivalent). The pass in the table was then run again on the
final sources and tests, with `test_coexist80.py` added to the suites the runner uses.

## Not established

* Anything on the S24, and anything about a real libusb stack: pyusb `set_configuration`/reset while the NAT-041 collector polls the same
  device (the model shows the protocols do not interfere, not that libusb allows two processes to use the device this way), the host-to-phone rate (the 225 s budget needs about 11 MB/s; the companion
  only measures), whether the DWC3 DMA reaches the reserve above 4 GiB (NAT-040 item U5), and how long the probe's hash of 2.31 GiB takes on the device.
* That the cache state leaves the delivered bytes visible to the kernel (row 2 is where that would show up).
* That the analyser's parsers match the *real* device log byte for byte: they match the NAT-077 probe's and the loader emitter's formats as
  written in their sources and as run on the host, and the `key=0xHEX` shape as archived from NAT-075. A new kind of line is a row 8, not a guess.
* The decision for NAT-078 itself, and anything about Apple userland.
