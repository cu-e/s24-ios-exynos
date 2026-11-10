# 0007 — Requested single RECOVERY experiment with logs and 120-second watchdog

2026-11-10. Source: the owner's current message asking to write a new RECOVERY
image with logging, set the watchdog to two minutes and reboot, while preserving
the system. This requests a new native attempt and supersedes the earlier pause
on XNU attempts for this requested work, subject to the preservation boundary.
The owner subsequently instructed the agent to investigate the log channel itself.

Authorized preparation: inspect existing interfaces, fix/build/test the candidate
and its logging, preserve separate attempt records, and prepare a concrete single
RECOVERY-only run with stock restoration. The requested target is RECOVERY only.
No reset-data operation, format, repartition, unlock, BOOT/init_boot/vendor_boot,
dtbo/vbmeta/param/USERDATA/super/EFS/key/encryption write is authorized.

This records intent, not a claim that a candidate satisfies it. No candidate hash
has been selected and no image-specific execution decision is recorded here.
A candidate must actually support the requested timer, expose a qualified early
log path and meet the no-internal-storage/return gates before it can be uploaded.
The native flag remains false during preflight. A flag does not establish safety.

NAT-009 is reserved by a different owner and blocked after that session's reported
classifier stop; this task does not resume, edit or repeat its S-Boot review.
NAT-019 examines the existing watchdog's pure host arithmetic and current logging
availability. Unsupported settings must be rejected before any image/phone write.
