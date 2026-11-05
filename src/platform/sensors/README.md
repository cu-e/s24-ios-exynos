# E1S sensor and GNSS transport boundary

This is an owned, allocation-free host parser, with no hardware backend or Apple service implementation. Run the [procedure](../../../docs/procedures/sen-001/README.md). `transport.h` defines borrowed GNSS buffer lifetime and atomic SHUB publication. Callers supply online state and same-epoch boot-time nanoseconds; parsing cannot discover a live service. No sensor enabling, firmware load, reset, ioctl, power or MMIO operations occur.

All protocol research is pinned to [dx4m/android-kernel-samsung-e1s](https://github.com/dx4m/android-kernel-samsung-e1s/tree/417484173abc2c4fa93e738ea82ad9f2e84911b1), full SHA `417484173abc2c4fa93e738ea82ad9f2e84911b1` from `research/sources.json` (`s24-linux`). This public BSP is not established as byte-identical to measured BYH3 firmware. The checker saves exact named Git objects, command exits and SHA256 digests under local artifacts. Source declarations retain upstream notices; no upstream driver implementation is copied into these MIT authored files. Upstream sensorhub files carry GPL2-or-later, GNSS files GPL2, with per-file notices controlling each snapshot. The isolated genuine SHUB header compile uses explicitly synthetic kernel support types and qualifies only offsets/command constants.

## Physical identity observations

The immutable existing capture `artifacts/device-profile/2026-11-05-session1-extra/sensors.txt` is Android HAL inventory from the measured SM-S921B/BYH3 device (see `research/notes/DEV-001-profile.md`). These are exact advertised names and handles, not probed silicon IDs or SHUB routing guarantees:

| HAL handle (hex) | Advertised name | HAL type | Manufacturer |
| --- | --- | --- | --- |
| 00000001 | LSM6DSVTR Accelerometer | 1 | STM |
| 00000004 | LSM6DSVTR Gyroscope | 4 | STM |
| 00000002 | AK09918C Magnetometer | 2 | Asahi Kasei Microdevices |
| 00000005 | STK33F11 Light | 5 | Sitronix |
| 00000008 | STK33F11 Proximity | 65592 | Sitronix |
| 00000006 | LPS22DFTR Barometer | 6 | STM |
| 03000001 | STK6D2X Rear ALS | 65577 | STK |

HAL handle8 is not its Android type65592; pinned SHUB enum proximity8 is a separate namespace. STK6D2X Rear ALS was present in the original inventory but omitted from the short DEV-001 table. It is not assumed to pass through SHUB. Virtual rotation/gravity/orientation/palm sensors are not additional silicon identities. No GNSS silicon model, firmware hash or working fix was measured in these inputs. KEPLER is the BSP device name, not a proven chip part number.

## Pinned hub contract

Paths below are relative to the pinned repository:

- `drivers/sensorhub/comm/shub_comm.h`: packed prefix is cmd:u8, type:u8, subcmd:u8, total_length:u16, length:u16, timestamp:u64; payload offset15. Commands use64-byte outgoing buffers. `comm/shub_cmd.h` enumerates REPORT5.
- `comm/shub_comm.c`: REPORT body contains tagged records, BYPASS tag0x37. Fragmented messages use total_length and timestamp token. This parser accepts only total_length==length and refuses fragments rather than guessing their ordering. Received transport bytes after declared length may be padding. Header timestamp is never substituted for sample time.
- `sensormanager/shub_sensor_manager.c`: BYPASS carries type:u8, count:u16 then samples. `sensor/accelerometer.c` and `sensor/gyroscope.c` initialize received event size6 for types1 and4; each sample then carries8-byte timestamp. These raw six bytes are preserved; no scale, mounting conversion or SI units are claimed. Unknown tags/types, extra body records and zero counts fail explicitly. No partial batch is published on error.
- `utility/shub_utility.c`: host timestamp uses `ktime_get_boottime()` converted to nanoseconds. `get_sensor_value` in manager records receipt time and clamps future sample timestamps to receipt. The adapter retains hub_ns as well as effective time and clamp flag. It makes no epoch conversion to Mach absolute time, UTC or CoreMotion and imposes no unwitnessed monotonicity rule across batches. Clock sync/reset/session handling remains a backend obligation.
- `vendor/shub_lsi.c` writes through `contexthub_ipc_write_call`; receive notifications call `handle_packet`. `drivers/staging/nanohub/chub_shub.c` connects these to CHUB IPC. LSI working state recognizes POWERON/ON, and reset/off stops service. `sensorhub_s5e9945.dtsi` identifies S921 and LSM6DSVTR/AK09918C mounting properties; revision-dependent positions differ, so no orientation is selected here.

## Pinned GNSS contract and source discrepancy

`arch/arm64/boot/dts/samsung/e1s/s5e9945-e1s_common.dtsi` includes `exynos/board/erd/s5e9945-erd9945-gnss.dtsi`. That file describes `samsung,exynos-gnss`, KEPLER, node `gnss_ipc`, shared memory and mailbox; code range0x580000 and IPC range0x80000, with RX0x40000, TX0x3ff80 and register block0x80. The alternate `gnss-s5400.dtsi`/`gnssif_spi` implementation is not selected by this E1S include. These source values authorize no mapping or access.

`drivers/soc/samsung/gnssif/include/exynos_ipc.h` helpers and `gnss_io_device.c:exynos_build_header` define little-endian marker0xabcd at0, frame sequence:u16 at2, fragment configuration:u16 at4, frame length:u16 at6, channel:u8 at8, channel sequence:u8 at9, body at12. Length includes header and excludes padding; transport extent rounds to4 bytes. Writer sets channel0; single-frame masks are0xc000. Body is opaque vendor GNSS data, not asserted to be NMEA, UBX or location records. No timestamp exists in this outer header.

The same header's `struct exynos_link_header` disagrees: it lacks the leading marker and places `reserved_1` before channel, producing channel offset8 coincidentally but other fields at different offsets. The adapter follows the explicit offset constants/helpers and actual writer, never overlays that inconsistent structure. It accepts one complete single frame/channel0 and reports consumed padded bytes, supporting caller-managed concatenated rings. Fragments and other channels are unsupported. Reserved bytes and padding are ignored, not assigned invented semantics.

## Missing inputs and acceptance limits

Unavailable: exact BYH3 hub/GNSS firmware and firmware ABI compatibility; live DT/reserved memory/mailbox/clock/power/IRQ qualification; authoritative per-sensor calibration, scale and revision-dependent orientation; GNSS vendor message/fix schema and assistance/control contract; native XNU transport, firmware trust/load policy and reset/suspend clock synchronization; selected iOS16.5 sensor/GNSS private daemon/service ABI and entitlement inputs. `sen_service` starts from caller truth, never assumes these exist. CoreMotion, locationd/CoreLocation, fused sensors, GNSS fixes, native transport and Apple compatibility are unqualified. Host fixtures and header compilation establish no phone operation.
