# VM-050: root access to /dev/kvm on the S24

Evidence class: android-userland, measured 2026-11-10 on SM-S921B/e1s, S921BXXS9BYH3.

## Established

- Through su (`u:r:magisk:s0`), `open("/dev/kvm", O_RDWR)` succeeds.
- `KVM_GET_API_VERSION` returns 12, the value the Linux KVM API documents as the stable version.
- The phone did not reboot during the run (`/proc/uptime` before 392474.88 s, after 392475.43 s).
- VM-001 found that the shell user cannot use the node, and that AVF, the `vm` tool and
  virtualizationservice are absent on this firmware. Root access is therefore the only measured way in.

## Not established

- Whether a VM can be created. `KVM_CREATE_VM` was not called, so stage-2 setup, guest memory and
  vCPU creation are unmeasured.
- Which capabilities exist. `KVM_CHECK_EXTENSION` and `KVM_GET_VCPU_MMAP_SIZE` were not called.
- Whether Samsung's hypervisor configuration permits guests. An API version alone says nothing about this.
- Whether an iOS guest could boot. Nothing here runs XNU, and QEMU virt is not an Exynos model.

## Next check

VM-049 is blocked until the owner approves the two capability ioctls. `KVM_CREATE_VM` needs its own
approval because a failure there could crash the kernel and reboot the phone.
