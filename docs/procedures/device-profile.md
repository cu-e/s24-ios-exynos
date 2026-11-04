# Extended device profile without changing the phone

Scope: android-readonly. Requires already-authorized ADB and an exact SM-S921B/e1s match. Root is not requested. The collector does not invoke su, reboot, install, flash or setprop, or write partitions.

```sh
python3 tools/device_inventory.py --output devices/local-NEW.json
python3 tools/device_profile.py --output-dir artifacts/device-profile/NEW
```

Use a fresh name for each run. Profile directories use mode 0700 and files use 0600. They are excluded from Git. For selected follow-up measurements:

```sh
python3 tools/device_profile.py --output-dir artifacts/device-profile/NEW-extra   --sections battery-service thermal-service display sensors input-capabilities
```

The collector saves selected OS/boot properties, CPU/memory, kernel config, partition and system mount maps, Vulkan/EGL, display modes, built-in input capabilities, sensor inventory, power and available sysfs facts. It does not retain battery usage history, active windows, applications or event history.

Vulkan UUID/LUID fields are removed before saving. Device-tree properties use an allowlist; chosen/bootargs, serial/MAC/seeds are omitted. Raw tar and complete dumpsys output are not saved. An empty tree is unavailable, not a successful result.

A Magisk binary does not establish root access for ADB. locked/green describes current Android properties, not Download Mode; properties may be overridden. CONFIG_KVM or a /dev/kvm node does not establish usable virtualization. Metadata snapshots are not BOOT/recovery backups and do not prove recovery.

Individual commands have 25–45 second timeouts. If connectivity is lost, preserve existing files and document missing data; do not reboot to continue collection. This profile alone is insufficient for native-device evidence.
