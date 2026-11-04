# Recovery and autonomy boundaries

**Status: recovery is not prepared or tested on the owner's device.** This document is a research template, not a flashing procedure.

NAT-001 remains blocked on exact matching stock images and dated/hash-verified backups. [Session template](procedures/recovery/session-template.json) records the missing concrete inputs without authorizing operations. NAT-004 is the separately gated measured recovery qualification; NAT-003 now depends on it and the full kernel build KRN-001. The newly built freestanding loaders do not satisfy either gate.

| Requirement | Current state |
|---|---|
| Exact model/firmware/bootloader version | SM-S921B / S921BXXS9BYH3 measured through ADB; actual unlock state unresolved |
| Stock images matching this firmware | Not obtained |
| Backup with size, hash and location outside Git | Not obtained |
| Recovery/Download Mode entry | Not tested |
| Host recovery tool and USB permissions | Not tested |
| Verified Android restoration | Unavailable |
| Control channel from XNU | Unavailable |
| One-shot boot / hardware watchdog | Not implemented or tested |

Preserving Android partitions, retaining Android bootability and preserving data are separate properties. A backup does not prove recovery capability. A structurally valid BOOT image does not prove execution. Read-only UFS does not eliminate hardware hang risks.

The first native session requires the owner's explicit authorization for a concrete scope, initial state, image hash, return procedure, manual fallback availability and stop criteria. Record these in NAT-003. Ordinary host tasks do not require this hardware authorization.

Do not run an autonomous native loop before verified recovery. Do not repeatedly flash/reboot after losing connectivity. Stopping the agent does not undo hardware actions.

Long autonomous native experiments will require independent control/recovery and may require a separate test device. Such capabilities have not been established for the primary S24.
