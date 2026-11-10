# VM-054: XNU guest to PID 1 on the S24 under s24vmm

Device work under decision 0002 (root diagnostics, bounded KVM test VMs). Nothing is written to
persistent storage, and the device serial is not recorded.

## Procedure

`run.py` delivers the VMM and its inputs as root into `/dev/s24-vm054` (tmpfs) and checks every
hash on the device. It runs the VMM under its own `--timeout` plus an outer `timeout`, then
removes the directory and confirms that:
- the directory is gone;
- no VMM process is left;
- device uptime increased, so the phone did not reboot.

```
A=/home/egor/dev/pet/s24-ios-exynos/artifacts; G=$A/vm-002-guest-20261110/guest
python3 -I docs/procedures/vm-054/run.py --run session-005-fpon --vmm $A/vm-055/check-007/s24vmm \
  --file image=$G/Image --file initrd=$G/payload.bin --timeout 60 -- \
  --image {image} --initrd {initrd} --mem 1024 --cpus 1 --pin 9 --fp-on
```

The CPACR synchronization probe (`fp_sync_probe.S`) is built with NDK 28.2 `clang -target
aarch64-linux-gnu -c`, then `ld.lld -e _head -Ttext=0`, then `llvm-objcopy -O binary`. It runs with
`--image {image} --mem 64 --cpus 1 --pin N`.

## Result

The guest reaches PID 1 and powers off with `--fp-on` on X4, A720 and A520 cores. Without it, the
guest hangs at its first FP instruction. The runs and the cause are in
`research/notes/virtualization/VM-054-xnu-guest-s24.md`.

Files:
- `fp_probe.S`: the earlier probe. FP works with FPEN 0b11 written with an ISB, and traps with
  0b00.
- `fp_sync_probe.S`: the decisive probe. It checks FPEN 0b11 written without an ISB.
