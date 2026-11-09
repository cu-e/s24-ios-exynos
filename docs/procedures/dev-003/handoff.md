# DEV-003 handoff

Six partitions (boot, init_boot, vendor_boot, dtbo, vbmeta, recovery) are copied to
`artifacts/device-backup/2026-11-10-session1/` in the main checkout. That directory is
Git-ignored; `manifest.json` holds size and device/host SHA-256 for each image.

Result: all six verified. Copy tool: `copy_partitions.py`. It reads through `su`, using a fixed
allowlist, and never writes to the device.

Not established: that these images can restore the phone. No restore was attempted, and they do
not include user data. Do not treat them as a recovery guarantee.

Next: NAT-001 needs hash-verified stock images and is held by another owner. This copy can be
offered as input to it, but only that owner can update that task.
