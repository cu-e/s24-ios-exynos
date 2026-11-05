# UI-001: display/input contract checks

This builds owned arithmetic and event/state validation only. Read src/platform/display/README.md and profile.json first. No framebuffer is mapped and no HID event is dispatched.

```sh
python3 -m unittest discover -s tests -p test_display_contract.py -v
python3 src/platform/display/check.py --run unique-display-contract
make check
```

Register UICONTRACT-001 before the explicit sanitizer/cross-target run. Logs, copied owned inputs, hashes and object headers go to a new ignored artifacts/display-contract/ directory. Host Clang18 runs the ASan/UBSan fixture; installed NDK28 Clang19 only compiles AArch64 ELF/arm64 Mach-O C/C++ objects. No Apple SDK, XNU link or ARM execution is involved. Each subprocess has a 45-second deadline; ledger timeout is metadata, not a phone watchdog.

Validate byte extents against Python arbitrary-precision arithmetic, row padding, subrect bounds, corners/rotation/mirroring, distinct physical/logical dimensions, exact unaligned wire records, replay/loss/clock/session errors, cancellation and Stop. Tests do not qualify trusted mappings, GPU fences, hardware scanout, backboardd, kernel input queue or native touch behavior. The actual E1S nibble correction is tested separately under UI-006.
