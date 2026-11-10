# VM-049 handoff

Done: `kvm_caps.c` (static NDK build) answered API 12, vCPU mmap 8192 and the capability list in research/notes/virtualization/VM-049-root-kvm.md. The RAM directory `/dev/s24-vm049` was removed and confirmed absent; uptime grew across the run (no reboot).

Reproduce: build with `aarch64-linux-android35-clang -static -O2 -Wall -Wextra -Werror docs/procedures/vm-049/kvm_caps.c -o artifacts/vm-049/build-NNN/kvm_caps`, then `python3 -I docs/procedures/vm-049/run.py --run session-NNN --helper artifacts/vm-049/build-NNN/kvm_caps` with exactly one authorized device attached.

Next: VM-051 creates one VM with one vCPU and a few bytes of guest code, under decision 0002.
