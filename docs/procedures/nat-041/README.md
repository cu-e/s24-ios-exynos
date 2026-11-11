# NAT-041 — EP0-only DWC3 device engine, its DWC3 model, and the unattended host collector

Evidence kind: **host-test**. Nothing here ran on the phone and nothing in this directory touches it. The engine is authored
code that compiles for `aarch64-freestanding`; the tests run it against a model that is *my reading* of the vendor `dwc3`
driver. Passing shows that the engine, the wire protocol, the collector and the NAT-016 archive agree with each other and with
that reading. It does not show how the S24's DWC3 behaves.

The channel design (why an EP0 control-pull monitor, why not S-Boot's USB code) is `docs/procedures/nat-038/README.md`. The
register sequence and the platform steps that must precede `usbmon_init()` are `docs/procedures/nat-040/` (source review, 120
literal citations at the pinned vendor kernel `417484173abc2c4fa93e738ea82ad9f2e84911b1`). The first run on the phone is NAT-043.

## Files

| path | role |
|---|---|
| `engine/usbmon.h`, `engine/usbmon.c` | the engine: polled, no interrupts, no allocation, no libc, one event buffer, at most two TRBs in flight; EP0 enumeration, vendor control-IN reads of a RAM log stream and an exception frame, `SET_NONCE` |
| `engine/usbmon_port.h`, `engine/port_aarch64.h` | the hardware contract (MMIO, delay, ticks, DMA accessors, one `sync` primitive) and the loader-side port (`dc civac` + `dsb sy`) |
| `engine/dwc3_regs.h` | register/TRB/event constants copied from the vendor `core.h`/`gadget.h` (GPL-2.0, attribution in the file); `test_engine.py` re-reads the pinned files and fails on any differing value |
| `model/model.c`, `model/host_port.h` | the DWC3 device-side model (register file, endpoint commands, event buffer, SETUP/data/status handling), a non-coherent cache model, and a USB host stub; every rule the engine must obey is a `viol()` |
| `modelhost.py` | ctypes front end: builds engine + model into a shared library, exposes the simulated machine |
| `usbmon_proto.py` | the wire protocol in Python (constants, CRC-8, parsers); `test_engine.py` fails if any constant differs from `usbmon.h` |
| `s24_logd.py` | the collector (libusb via pyusb) writing through `docs/procedures/nat-016/archive.py` |
| `test_engine.py` | 54 tests of the engine against the model, including 13 seeded engine defects that must each be caught |
| `test_logd.py` | 46 tests of the collector against the model and the real archive |
| `mutate_logd.py` | breaks one line of `s24_logd.py` at a time in a scratch copy; the suite must fail (43 mutants) |
| `evidence.json` | the task's evidence record |

Run (host only):

```sh
python3 -I docs/procedures/nat-041/test_engine.py        # needs `cc`, `zig` and references/s24-linux at the pin
python3 -I docs/procedures/nat-041/test_logd.py          # needs `cc`
python3 -I docs/procedures/nat-041/mutate_logd.py --out artifacts/nat-041/mutation-logd
```

## Wire protocol (`engine/usbmon.h`, `usbmon_proto.py`)

USB identity: VID `0x1209` / PID `0x0001` (the pid.codes test pair), class `0xff`, one configuration, one interface, **no
endpoints**, high speed only, no string descriptors. Requests are vendor/device; anything else, or anything malformed, gets an
EP0 stall and is counted.

| request | meaning |
|---|---|
| `0xC0/0x01 GET_INFO` | 112-byte `usbmon_info`: magic `S24L`, flags (nonce set, fault, hold, connected, configured), stage, device boot block, nonce echo, ring size, `written`, `oldest`, counters, last DEPCMD status |
| `0xC0/0x02 READ_RING` | `wValue`/`wIndex` = low/high 16 bits of a 32-bit stream offset (extended against `written`, clamped to `oldest`), `wLength` ≤ 4096; reply = 8-byte `{start, end}` header + stream bytes |
| `0xC0/0x03 GET_EXC` | 328-byte exception frame (ESR, ELR, FAR, SPSR, SP, x0–x30, stage, count); `valid` is written last, the first fault is kept |
| `0x40/0x04 SET_NONCE` | 16 bytes of host nonce, echoed by GET_INFO |
| `0xC0/0x05 PEEK` | reserved; this version stalls |

The log is one ever-growing **stream** in a RAM ring. A record is `[seq u32][len u16][kind u8][crc8]` + payload (kinds: text,
stage, fault, boot, mark, drop). When the ring is full the engine drops whole records from the old end (`oldest` moves to the next
header) and appends a `drop` record carrying the running count; an append interrupted by an exception is never served, because
the stream length is committed last and the exception path appends through the same function.

DMA discipline: the engine never dereferences its DMA block; it goes through `usbmon_dma_*` and one `usbmon_dma_sync()` (clean
**and** invalidate by line, then a full barrier). The model keeps 64-byte lines, flags a stale read, a missing clean, and a
device write landing in a dirty line, and runs a worst-case prefetcher after every register access, so a missing invalidate shows
up instead of passing by luck.

## Findings of the tests during development

* The vendor-request type test in `build_reply()` first compared against `0x20` (class) instead of `0x40` (vendor): every
  vendor request would have stalled on real hardware. The model's USB host stub found it; fixed, and a seeded-defect test
  (`test_vendor_requests_with_the_wrong_type_constant_are_caught`) keeps it fixed.
* I did not keep a complete log of the other defects the model and tests exposed while the suite was being brought up (most
  were model or test faults: a halted-controller rule the vendor driver does not have, a model crash on an out-of-region DMA
  address, mutants that did not discriminate; a few were engine fixes such as how a SETUP arriving during a data stage is
  handled). The vendor-type constant above is the one engine defect recorded as found by the model tests.

## Collector (`s24_logd.py`)

Waits unattended for VID `0x1209`/PID `0x0001`, sends a fresh nonce (`os.urandom(16)`), checks the echo, then polls
`GET_INFO`/`READ_RING`/`GET_EXC`. It writes through the NAT-016 `Archive` (new directory per invocation, raw bytes fsynced before
interpretation, one boot record per device run) and keeps every control transfer, with its IN data, in
`usb-transfers.jsonl` next to the framed view. A frame is `{boot_id, seq, kind, data_b64, ...}`; the extra fields (`dev_seq`,
`dev_kind`, `stage`, `text`, `esr`, ...) are a convenience, `data_b64` is the device's own bytes.

* `boot_id` = `<host nonce hex>-<device boot block hex>`; the host nonce is what makes it new (NAT-016's rule).
* Loss is always a named `drop` frame and a NAT-016 capture error: `lost-before-connect` (ring already wrapped), `ring-overrun`
  (exact `lost_bytes`), `device-seq-gap`, `header-crc` (with `skipped_bytes`, then resynchronisation on the next valid header),
  `device-reported` (the engine's own drop count), and `unread-at-end` when the last GET_INFO showed bytes that were never read.
* A device restart is detected by the nonce, the device boot block or the stream length no longer matching → the boot ends
  (`reset-detected`) and a new one starts, even without a USB disconnect and even when the image (and its boot block) is identical.
* A USB disconnect shorter than `--grace` (10 s) is bridged: the same boot continues with no gap and no duplicate if the device
  still shows our nonce and boot block; otherwise the old boot ends (`disconnect`) and a new one starts. A device that stops
  answering for `--dead-after` (30 s) ends its boot as `unresponsive`.
* Transient timeouts are retried and counted; they are not archive errors. A start failure is recorded once per distinct reason.
* **Stop semantics.** NAT-016's `finish()` records every stop reason except `eof` as a capture error. A deadline or interrupt after
  the collector drained the device and closed every boot is therefore passed to `finish()` as `eof`; the real reason is in the
  events log (`collector-note`) and in `collector-summary.json`, so the manifest's `stop` field reads `eof` for such a run. A size
  limit or backend error keeps its own name and stays an error.
* Safety: only VID/PID `0x1209:0x0001` is ever queried; VID `0x04e8` (Samsung, including Download Mode) is refused in the
  constructor; only requests 1–4 are sent; no `SET_CONFIGURATION`, reset or claim.

The collector needs pyusb. The system python has none; the project's venv does
(`artifacts/recovery-rescue-20261110-01/venv/bin/python -I docs/procedures/nat-041/s24_logd.py --out artifacts/nat-043/NEW
--provenance unqualified-live --seconds 600`). Device permissions (a udev rule or root) are not installed by this tool; a
permission failure is recorded once as `device-access-denied`. A smoke run of the CLI with the venv python and no device
(2 s) exits 2 with outcome `incomplete` (no boot), as it should: `artifacts/nat-041/smoke-002/`.

## Using the engine in the loader (NAT-043, not done)

```c
static struct usbmon g_mon __attribute__((aligned(64)));
static uint8_t g_ring[16384];
/* after the NAT-040 ladder (HSI0 power/clocks, eUSB2 PHY, DWC3 clocked) */
struct usbmon_cfg c = { .dwc3_base = 0x17900000, .ring = g_ring, .ring_size = sizeof g_ring, .boot_id = {...},
                        .refclk_hz = ..., .fladj = 0x20, .gfladj_refclk_lpm_sel = 1 };
if (usbmon_init(&g_mon, &c) == 0) { usbmon_stage(&g_mon, 1, "..."); }
/* call usbmon_poll(&g_mon) from every wait loop and log call; exception vectors end in usbmon_fault() */
```

The values above are the vendor device-tree/NAT-040 numbers; whether they are right for the running firmware is NAT-043's
question. The loader must also place `g_mon` in memory the controller can reach and tell the port which mapping it uses.

## Not established

* Anything about the real S24: that the DWC3 at `0x17900000` answers this register sequence, that the PHY/repeater/clock
  prerequisites (NAT-040 unknowns U1–U8, including the unproven high-speed-only inference U6) can be met by the loader, that
  `dc civac` is the right maintenance for the mapping the loader uses, that libusb accepts a device whose only configuration has
  no interface endpoints, or that the host sees VID `0x1209`/PID `0x0001` at all.
* That the model is faithful: it encodes one reading of the vendor driver; where both the engine and the model share a
  misreading the tests cannot notice.
* That unattended retrieval of a real native run works: that is the NAT-043 criterion (archive with a boot ID that did not exist
  before the run, a stage message only the new image can produce, and in a fault variant an exception frame).
* Polling stops once XNU runs unless the kernel keeps calling the engine; this version is a loader-time channel.
* `PEEK` (physical memory/MMIO reads, which GPU bring-up will want) is reserved, not implemented.
