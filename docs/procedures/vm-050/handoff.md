# VM-050 handoff

Result: as root, `/dev/kvm` opens and reports API version 12. See `research/notes/virtualization/VM-050-root-kvm-api.md`.
Reports: `artifacts/vm-050/session-00{1,2,3}/report.json` (only session-003 executed the helper).

Tool notes: `adb exec-in` can return before the device-side writer exits, which produced ETXTBSY and a
short file. `run.py` waits for the delivered hash, then executes a copy.

Open: VM-049 needs the owner's approval for two capability ioctls. `KVM_CREATE_VM` needs separate
approval and can crash the kernel.
