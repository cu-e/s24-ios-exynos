# 0008 — Owner-requested single 83-second RECOVERY diagnostic

2026-11-10. The owner requested a new RECOVERY image with diagnostics, a longer
watchdog, and one reboot, explicitly requiring preservation of the Android
system. After being informed that 120 seconds is unsupported by the current
watchdog implementation and that an independent native log channel is absent,
the owner replied: "ну давай : 83 секунды начинай" ("go ahead: 83 seconds, start").

This continues decision 0007 with the amended timeout. It authorizes preparation
and one attended attempt with the requested 83-second diagnostic, RECOVERY only,
and restoring the original RECOVERY afterward. It is not standing authorization
for retries or other native tasks. The agent must finish host checks before the
first write and record the exact selected image in the native experiment.

Prepared candidate:
`artifacts/nat-020/build-003/recovery.img`, 100663296 bytes, SHA-256
`b5ff3bf7e4d6bcd36cc518fbc4ab0daaaf8a1985056a65708f60b51f4f9a6a49`.
See `docs/procedures/nat-020/README.md` for the derivation and coverage limits.
This is the agent's concrete selection under the owner's request, not a claim
that the owner personally reviewed this digest or that the image ran already.

Bounded plan: check live stock RECOVERY identity, block-device bounds and Android
state; stream exactly the pinned 96 MiB candidate only to `/dev/block/sda18`;
fsync and require a full device hash matching the candidate before one
`adb reboot recovery`. If writing or readback fails while Android remains
reachable, restore the pinned stock image immediately and do not reboot into
the candidate. Save each command and passive USB event in a new attempt directory.

Stop waiting at 83 + 120 seconds, two observed resets, a data/recovery prompt,
unexpected screen or thermal warning. No native retry or further device command
after loss of ADB. The owner may need to force Download Mode physically; restore
only the fixed original RECOVERY with NAT-013 in one fresh session. If Android
returns directly, restore stock RECOVERY through the same bounded root write.
Verify `sys.boot_completed=1`, the full stock RECOVERY hash and minimal user
environment metadata. Never infer successful XNU execution or restored Android
from USB IDs or a successful upload alone.

Known limits disclosed before execution: timer calibration/clock survival,
automatic Android return, native log delivery and log retention over reset remain
unqualified. Host USB events are saved separately and do not resolve CPU-stage
progress. NAT-017 is not completed or bypassed as evidence: this remains a
limited-observability diagnostic and cannot satisfy the earlier "all logs" goal.

The preservation boundary is unchanged: no format, wipe, factory reset,
repartition, unlocking, or write to BOOT, init_boot, vendor_boot, dtbo, vbmeta,
param, USERDATA, super, EFS, keys, encryption state or any partition other than
RECOVERY. No direct persistent reboot-parameter write. Do not reopen the other
owner's reserved NAT-009 investigation.
