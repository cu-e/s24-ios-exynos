# Device access

An already-authorized ADB endpoint is required. Local inventory does not pair, request su, reboot, install APKs or write partitions. Bootloader unlock and root access are separate facts.

```sh
python3 tools/device_inventory.py --output devices/local-2026-11-05.json
```

For multiple devices, explicitly pass `--device`. The serial is used for selection but is not saved. Use a fresh filename for each observation; do not overwrite an earlier capture.

Selected getprop values, shell uid, uname and screen dimensions are saved. IMEI, serial, MAC, accounts, app lists, full getprop and complete logs are not collected. `matches_reference_target` checks SM-S921B/e1s; false requires reviewing code applicability and does not authorize flashing another model.

Wireless ADB can be configured separately with the owner. It does not survive entry into a kernel without its own USB/Wi-Fi driver. A connected USB cable alone does not provide control over hung XNU.

The android-app stage is authorized since 2026-11-10 ([decision 0002](decisions/0002-owner-autonomy-grant-2026-11-10.md)): the project's own test APKs may be installed, run, updated and removed, with documented removal, time bounds and a stop path. Root diagnostics and read-only partition copies are allowed; partition writes, reboots and data-erasing actions are not. GPU-003/GPU-005 depend on that stage.

Extended profile: [procedure](procedures/device-profile.md), `tools/device_profile.py --output-dir artifacts/device-profile/NEW`. Captures include CPU/GPU, kernel config, partitions and available hardware metadata, with commands, timestamps, SHA256 and availability statuses. Device-tree properties and /proc/iomem are unavailable to shell on this phone; do not automatically invoke su to bypass this restriction.

Session 2026-11-05: [sanitized findings](../research/notes/DEV-001-profile.md). The local English report is `devices/local-2026-11-05-session1.en.md`; the original report remains at `devices/local-2026-11-05-session1.md`. Profiles are in `artifacts/device-profile/2026-11-05-session1/` and `2026-11-05-session1-extra/`. Private captures and reports are excluded from Git.
