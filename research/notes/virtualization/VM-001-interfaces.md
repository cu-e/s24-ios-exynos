# VM-001: virtualization interfaces on this S24

Evidence category: android-userland. Measured 2026-11-10 through already-authorized ADB as the shell
user on SM-S921B/e1s, firmware S921BXXS9BYH3, Android 15, kernel 6.1.93-android14-11.
No su, install, setting change, reboot or partition access. `/dev/kvm` was not opened and no VM was started.

| Layer | Result | What it means |
| --- | --- | --- |
| Build option | `CONFIG_KVM=y` in the 2026-11-05 capture (DEV-001) | Built in; says nothing about access |
| Device node | `/dev/kvm` exists, mode 0666, SELinux label `kvm_device` | The node exists |
| Shell access | `test -r` and `test -w` both fail despite mode 0666 | Refused beyond file mode, most likely by SELinux; no denial record was captured |
| Android Virtualization Framework | Feature `android.software.virtualization_framework` is false, `android.system.virtualizationservice` is not found, `/apex/com.android.virt` has no `bin` directory, `vm` is absent | AVF is not offered to the shell on this firmware |
| Hypervisor properties | `ro.boot.hypervisor.vm.supported`, `.protected_vm.supported` and `.version` are empty | The device advertises no AVF hypervisor |
| Virtualization packages for user 0 | 0 listed: none | Installed package names only |

## Conclusion

The shell has no accessible VM interface here. A build option and a device node are not one.

## Not established

- Whether a root process can open `/dev/kvm`.
- Whether KVM works on this kernel: `open`, `ioctl` and VM execution remain untested.
- Whether any guest could run here, and at what performance.

Opening the node as root and calling `KVM_GET_API_VERSION` would answer the first two. That needs su,
which is not part of this task and needs the owner's separate authorization.
