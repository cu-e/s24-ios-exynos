# Freestanding E1S host build

Prerequisites: Python 3.11+, Git, Zig **0.16.0**, and `python3 tools/sources.py fetch s24-port`. No SDK, firmware or Apple userland is used for the two freestanding loaders.

```sh
python3 tools/build/e1s.py --run session-unique-name
```

The command verifies upstream provenance, copies it into a new artifacts/e1s-build/ run, compiles the probe and XNU handoff loader, fixes their Image headers and packages boot v4 files/tars. It records actual compiler commands, failures, versions, sizes and SHA256s in report.json. SOURCE_DATE_EPOCH defaults to zero in upstream tar packing. Existing runs are never overwritten. Image build-format fields use the recorded Android 15 / 2025-08 baseline and do not establish boot compatibility.

These are host build products. The handoff loader has no XNU payload by itself. Native memory reservations and recovery are not validated. There is no flashing/install/reboot command. Keep images local and do not feed them to device tools.

Full XNU additionally requires the exact Apple XNU source, reviewed HakiOS tools/cctools, headers/dependencies and a locally supplied iPhoneOS16.5 SDK. Pin these inputs independently. Missing SDK or failed check_all_exports remains an incomplete kernel build.
