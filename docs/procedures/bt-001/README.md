# BT-001: owned H4 and initialization-command boundary

Review the pinned E1S Bluetooth/UART/power sources and the controller/ROM unknowns in src/platform/bluetooth/profile.json. This task builds an independently authored byte-stream decoder and exclusive initialization-command model only. It neither implements Exynos UART services nor boots firmware or an iOS Bluetooth daemon.

```sh
python3 src/platform/bluetooth/check.py --run unique-bt-transport
python3 -m unittest discover -s tests -p test_bluetooth_transport.py -v
make check
```

Use this existing file as the experiment procedure and register before the explicit sanitizer/cross-target run. The build executes only owned host fixtures with ASan/UBSan; compile-only AArch64 ELF and arm64 Mach-O objects are never run. Default compilers are the installed host Clang 18, `cc`, and NDK28 Clang19 for cross compilation. A new run directory preserves source copies, command/exit logs, hashes, object headers and outcomes under ignored artifacts/bluetooth-transport/.

No serial device is opened. The caller supplies synthetic bytes and monotonic time; timeout/Stop do not establish physical drain or completed work. A new bookkeeping epoch cannot distinguish a late on-wire response from an earlier controller session. Native UART/power/wake/firmware and the selected iOS16.5 control/BlueTool/vendor adaptation remain separate gated implementation tasks. Keep unknown live ROM, firmware, baud and in-band-sleep mode explicit.
