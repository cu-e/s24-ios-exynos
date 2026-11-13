# NAT-141: scC touch image: Samsung's STM screen-on start and a polled event thread

Evidence kind: host-test. No device was used. Owner claude-opus-usb130-20261113. It follows NAT-140, where the STM answered its ID on
the USI pins with both rails verified.

## What the kernel does after the three ID polls

The sequence runs only if the last ID poll returned "ok" (NAT-125's admission rule), and the boot-arg `e1stouch_ev=0` disables it.
It is the order of Samsung's screen-on path, taken from the pinned `references/s24-linux` at 417484173abc:
`stm_core.c:1091 stm_ts_start_device` → `ts->plat_data->init` = `stm_core.c:296 stm_ts_reinit` → `stm_fn.c` helpers.

| Step | Bytes on the wire | Samsung source |
| --- | --- | --- |
| system reset | `FA 20 00 00 24 81`, then 10 ms | stm_fn.c:323-340 `stm_ts_systemreset` |
| READY wait | `87` reads every 20 ms, at most 150, until stype 2 / id 0x00; `ff ff ff` = broken firmware; `F3` logged | stm_fn.c:429-506 |
| clear all events | `C0 62` | stm_reinit → `stm_ts_command(CLEAR_ALL_EVENT, false)` (stm_fn.c:308) |
| scan mode | `A0 00 01`, then echo wait for `43 01 A0 00 01` (same bound) | stm_fn.c:589 `stm_ts_set_scanmode`, 508 `wait_for_echo_event` |
| sense on | `C0 10` | stm_core.c:1129 |

Framing: writes get a `C0` prefix except for opcodes A0/A2/A4/A7/FA/FB/D0 (stm_spi.c `stm_ts_no_lock_spi_write`). Event reads are
`87` plus a dummy byte, with data from byte 2 (stm_spi.c:590).

Left out on purpose:
- force calibration 0x13 (hw_init only) and panel calibration;
- firmware update, the sponge/LP modes and the optional mode settings of reinit (grip, noise, cover).

No flash write is sent.

The event thread polls `87` every 10 ms (`e1s_poll_us` floor 10000), reads up to 31 events per poll and posts coordinate events
through the donor's `post_event` → `redwood_touch_post` (/dev/hakios-touch, NAT-121). It logs:
- the first 64 coordinates (raw 12-bit x/y);
- the first 16 other events;
- a summary every 10 s (at most 30): coordinates, presses, releases, other events, polls with gpa1-2 low.

gpa1-2's pull is set to NONE as in Android's `tsp_int_active` (e1s dts), so its level can be sampled. No IRQ is attached.

## Build

| Item | Value |
| --- | --- |
| Kernel | `artifacts/nat-141/kernel-001` (KRN-044), kernel.no-storage 9213cff4b675bb22d08aa7ef696ec82d8e0bf61c6206cfd6da0c537d4ae85914, 0 undefined, 29 stubs; after normalizing the path, loader_return/redwood_input/e1s_acpm/e1s_pmic objects equal NAT-139's |
| Image | `loader-diag-xnu-scC-md1`; RECOVERY 15b2d177cc0b3f061eec1a0064e3d1569a43b296ac2c8ca4a4ea4824da70b617, payload 416826b3221355df31cc6daecb6ac82470e1011df8f33a56c76b149ad0348263, loader Image 1dd223ef88494ff0947c80ef0f627f5bb027d0099e1582f1bd9ec779106690e8 |
| Cmdline | 246 B, identical to scB except the tag `nat_attempt=NAT141-scC` |
| Session | `session_nat142.py` ced8653c205fc7cfefe742d09cd252ccce059808cdd1d9fb5293ad604c9ac84c (`derive142.py --check`, counted from session_nat140.py) |

## Tests (host)

`TMPDIR=<scratch> python3 -B -I docs/procedures/nat-141/test_nat141.py`: 5 OK. The real driver and its real bit-banged transfers run
against `host/peer141.c`, which is NAT-139's pin model plus a synthetic event queue (READY after the reset frame, echo after
`A0 00 01`, a press/move/release after `C0 10`).

| Case | Checked |
| --- | --- |
| Answering peer | frames: the clock-less select, the nine ID frames, then exactly `FA 20 00 00 24 81`, `C0 62`, `A0 00 01`, `C0 10` in Samsung's order; READY and echo matched after 1 read; posts DOWN/MOVE/UP for finger 1 at the scaled x/y |
| Write audit | the only non-read writes are those four; every read is `87` + 17 zero bytes |
| Peer without READY | bounded at 150 reads, then the sequence continues and events still arrive |
| Summary | after 1000 polls: `coord 3 (press 1 release 1) other 0` |
| Old wiring (no ID) | no thread, no start writes |

`python3 -B docs/procedures/nat-141/test_analyze142.py`: 4 OK. On NAT-140's real text it gives S0-no-thread, E0 and R1-open. The
synthetic additions give S1/S2/S3 and E1.

## Not established

This is not electrical evidence. It does not show:
- whether this STM accepts the sequence;
- that a finger produces events;
- that iOS acts on them.

The native run NAT-142 under its own decision answers the first two if someone touches the screen during the run.
