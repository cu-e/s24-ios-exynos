# NAT-133: Android read-only SuperSpeed facts (U1, U2, U3, U6, U8 of NAT-131)

Owner claude-opus-usb130-20261113. Evidence kind android-userland. Capture `capture133.py --out artifacts/nat-133/capture-001`
at 2026-11-13T17:3xZ, phone as plugged after the NAT-132 restore. Every phone command is a read through `su -c`, checked by the
NAT-039 deny-list before anything runs (the first attempt was refused by that guard because of a literal `->` in an echo string,
and nothing ran). No debugfs, no sysfs writes, no devmem.

| id | answer | source |
|---|---|---|
| U1 | **SuperSpeed is real on this cable/port:** Android `/sys/class/udc/17900000.dwc3` current=super-speed, max=super-speed, state=configured; host `8-1` speed 5000, bcdUSB 3.20, on bus 8 (root hub 10000M). Bus 7 is the same controller's 480M root hub. NAT-039's `high-speed` (2026-11-11) was a different cable or port | capture-001 `udc`, `host_before/after` |
| U2 | `exynos_usbdrd_phy_port` = "Used phy port : 0" in this plug orientation (read only; the attribute's store is never used). typec port0 has no orientation attribute value. The other orientation is not measured: that needs the owner to flip the plug | `phy-port`, `typec` |
| U3 | **Not available:** the dmesg ring starts at 521 s, so the PHY init lines (PMA/PCS/firmware IDs) have rolled out. Getting them needs a cable replug while Android runs (an owner action), then the same capture | `dmesg-phy` empty, `dmesg-first-ts` |
| U6 | Under Android all four USB rails are enabled at their DT values: vdd075_usb 0.75 V (regulator.93), vdd12_usb 1.2 V (.85), vdd18_usb 1.8 V (.38), vdd33_usb 3.1 V (.42), one user each, every consumer `178a0000.phy`. Suppliers of the PHY also include i2c 16-001d, 20-005f and 21-006f, plus pd_hsi0. The state at loader entry is still unknown (the native probe's indirect check) | `regulators`, `regulator-consumers`, `phy-attrs` |
| U8 | Download Mode (04e8:685d) for the NAT-132 restore enumerated at `8-1`, the 10000M root hub. A device on the USB3 root hub of an xHCI controller is SuperSpeed, so S-Boot's Download Mode uses SS on this cable (**inferred from the bus**; the speed file was not read at that moment). The stock 100663296-byte restore was acknowledged within about 0.5 s of trace time. S-Boot therefore can train SS; whether its normal RECOVERY boot leaves any of that state is not known | artifacts/nat-132/run-001/usb-events.jsonl seq 5, restore-001/restore-trace/trace.json |

Consequences for the SS work: the board, cable and host path support Gen1. Orientation 0 gives TCA_CONFIG 0x0 and the CR lane
offsets of port 0 (NAT-131 S8/S13/S15). The rails exist and are owned by the PHY driver. Whether they are on at loader entry decides
whether SS needs a PMIC decision: the read-only native probe (NAT-131 section 5) is next.
