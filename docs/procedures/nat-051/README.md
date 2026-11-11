# NAT-051: HSI0/USB debugfs summaries of the running Android (android-userland) — partial, with a crash on `clk_summary`

Evidence category: **android-userland** (a measurement on this S24 through `adb shell su -c`). Date 2026-11-11, SM-S921B / e1s,
S921BXXS9BYH3, kernel 6.1.93-android14-11. Outcome: **fail** for the task as written (see "Incident"); two of the three summaries were read.

## What ran

`capture.py` (plan checked before the first adb call; the command lists are the specification): record state, `mount -t debugfs none
/sys/kernel/debug`, read `regulator/regulator_summary`, `pm_genpd/pm_genpd_summary`, then `timeout 20 cat clk/clk_summary` last, `umount`
in a `finally`, record state. Raw output: `artifacts/nat-051/capture-001/` (git-ignored); sanitized subset: `capture-extract/`.

Before the mount: only `tracefs` mounted (`/sys/kernel/tracing`), `/sys/kernel/debug` empty, `debugfs` listed in `/proc/filesystems`,
Enforcing, `sys.usb.config` = adb.

## Read: software state of the USB rails and pd_hsi0 in Android (not loader-entry state)

| Fact | Value read |
|---|---|
| `vdd075_usb` / `vdd12_usb` / `vdd18_usb` / `vdd33_usb` | each: `use 1`, `open 1` (enabled), 750 / 1200 / 1800 / 3100 mV, consumer `178a0000.phy-<rail>` (agrees with the NAT-039 sysfs values; now from the regulator core's own summary) |
| `17900000.dwc3-dwc3-vbus` | `use 0`, 0 mV (the controller's VBUS supply is not in use: peripheral role) |
| genpd `pd_hsi0` | **`on`** (NAT-039 only inferred this from the consumers' runtime status). Devices: `dbgdev-pd-hsi0` suspended, `17880000.drmdp` suspended, `178a0000.phy` **suspended**, `17900000.usb` **active** |

So in Android the HSI0 domain is powered and the controller is runtime-active while the combo PHY node is runtime-suspended; the four rails stay
enabled with one user each. This resolves the "domain state not read" gap of NAT-039 for the Android state only; U1/U2 at loader entry stay open.

## Incident: the `clk_summary` read ended in a phone restart

At about 12:48:16Z the `clk_summary` read returned exit 255 after 0.23 s with no output; from that moment `adb` reported
`no devices/emulators found` (all later commands, including the `umount`, failed for that reason). The host then saw the phone as
`04e8:6860` with product `SEC_UPLOAD` (Samsung upload mode, interface classes 0x02/0x0a) at about 12:48:30Z, it left the bus by itself,
and Android was back and `adb` was `device` at about 12:49:03Z (about 47 s in total); `sys.boot_completed=1`, Enforcing, `sys.usb.config=adb`,
no debugfs mount (the restart removed it; the `umount` of `capture.py` did not run). No owner action was needed. No partition was written;
the owner's apps and data were not touched by this step. Read after the restart: `ro.boot.bootreason=reboot`;
the kernel command line carries `sec_debug_reset_reason.reset_reason=3`, `sec_debug_reset_reason.pwrsrc=0x00000800`,
`sec_debug.upload_count=0`; `/sys/fs/pstore` is empty and `/proc/last_kmsg`, `/proc/reset_reason` are empty (0 bytes), so **the cause is not
established**. What is established is the order: debugfs mounted, two summaries read, `clk_summary` started, the phone left Android into upload
mode and rebooted. That is a correlation with one observation; no kernel log of the event exists.

Consequences:

* `clk_summary` is **not** to be read again on this phone without a new decision; the task's `timeout 20` does not protect against a fault
  that takes the kernel down in under a second. (In NAT-051's own words, "stop and record if it does not return" was not the failure mode that
  occurred.) My earlier assessment in NAT-039 that this was a hang risk was right in kind and I under-weighted it by running it.
* For NAT-040/043/045: a register read in a domain or clock that is not powered is a plausible source of the same crash on the native path.
  The ladder already checks pd_hsi0 before CMU_HSI0 reads; this incident is a reason to keep that order and not to read any CMU outside what
  the vendor driver reads.
* Per-clock rates for the HSI0/USB clocks remain unread (C11d of the NAT-039 comparison stays open).

## Not established

Clock rates or gates; why the phone restarted; anything about the loader-entry state; any register value.

## Files

`capture.py`, `capture-extract/` (sanitized: USB rails, pd_hsi0 block, state before the mount), `evidence.json`.
