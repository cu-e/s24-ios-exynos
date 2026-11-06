# Scion: reuse the existing guest path; do one link diagnostic

**Decision:** preserve the completed objects and finish one bounded diagnostic
link of the matching current inputs before considering a full upstream switch.
Scion already supplies the generic QEMU/AVF boot path. Reproducing it is not an
E1S implementation, and upgrading Scion does not fix our remaining guest-input
qualification automatically. Stop adding generic boot infrastructure without a
specific failing input that the next diagnostic needs.

On 2026-11-06, official `Scion-Project/hackios-xnu-kernel` redirects to
[`Scion-Project/scion-kernel`](https://github.com/Scion-Project/scion-kernel).
`git ls-remote` pins current main to
**8bee16f38f6e34751d2867a8945577edc7cd30c7**, committed 2026-11-05 20:53:44Z,
111 commits ahead of our **a6f4bc38aa244359cd365c976244a88c9d6b3304**.
The complete Git trees, not the truncated 300-file compare response, establish:
all 11 `avf/shim/` files, all 12 `qemu/` files, all three `userland/libmini/`
files, AVF launch/probe scripts, `mkpayload.py`, raw `hello.c`, `xnu-env.sh`
and `xnu-build.sh` have identical Git blob identities. No pin was updated.

| Component | Ready upstream solution | Current use / necessary local difference | Next useful S24 result |
|---|---|---|---|
| AVF-style host boot | [qemu-avf.sh](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/avf/qemu-avf.sh): `virt`, GICv3, PL011, Image + XNUP initrd, one CPU | Already selected. Retain our existing bounded serial/cleanup collection; upstream defaults to 2G and may build a missing shim. Timeout alone proves no guest shutdown. | A genuine kernel's first console/entry failure, not another harness. |
| Loader and package | [avfboot.c](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/avf/shim/avfboot.c) + [mkpayload.py](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/xnuloader/mkpayload.py) already load Mach-O, synthesize boot args/DT and embed ramdisk | Reuse the matched existing shim/source lineage. `console_quiet=0` is necessary for user output; `rd=md0` is inserted only with ramdisk. Packager uses whole-body memory: constrain payload size, do not rewrite it. | The same generic boot-argument/DT boundary later needs actual E1S memory, timer, interrupt and UART facts. |
| Minimal PID1/root | [hello.c](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/userland/src/hello.c) and mockfs `/sbin/launchd` already exist | Current hello still has input-only x1 across SVC. VM025 traced selected XNU's x1 return writes; keep the compiled/admitted VM034 correction. The upstream libmini assembly call boundary is a reusable pattern, not a reason for a third PID1. | Actual exec/console/sysctl identity from real XNU. This remains reproduction and an ABI fix, not S24 support. |
| Android AVF launch | [run-probe.sh](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/avf/run-probe.sh) exists unchanged | It assumes an installed debug probe, grants two VM permissions and changes hidden-API exemptions. None was run. S24 custom-VM permission/hypervisor availability is unknown. | A separately authorized capability check could decide whether AVF is usable on this owner's firmware; no automatic grants. |
| Kernel build/link | [Makefile](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/Makefile) already has kernel/loader-open/hello/qemu-open; [xnu-build.sh](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/xnu-build.sh) selects ARM64/BCM2837/DEVELOPMENT/non-LTO | Our 1080-object build reproduces that kernel with local Linux/resource fixes. Matched provider/runtime, allocator and profile checks guard real errors; they are not new kernel features. CM owns evaluating their overhead. | One real link result; reuse the existing exact source recipe, tools and object receipts. |
| Native platform structure | Current [loader.c](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/xnuloader/loader.c) includes per-device platform tables and separate DT/PCI/SMP/UFS/watchdog code | Useful organization for a later E1S loader. Complete tree has no named `e1s`/`exynos2400` file; S9/Exynos9810 tables do not supply Exynos2400 register facts. | CN's independent E1S source audit can map boot entry, memory, UART, GIC and timer now; QEMU need not block that work. |

Useful current changes are **selective**, not a mandatory upgrade:

* EFI loader split (`58194b031b11c18f2d39970caa77e87fc56c7201`) moves platform
  knowledge into files included by `loader.c`; the AVF shim is unchanged.
  Transition cost is medium: preserve complete includes/device tables, rebuild
  and validate the UEFI loader. It buys organization for native ports, not the
  missing current link or an S24 driver.
* OS profiles (`60f155a3a8665671f564943dbb94a90209921570`) make `xnu/apply.sh`
  resolve the base through `tools/os-profile.py`. [ios-16.5](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/profiles/ios-16.5.conf)
  still pins XNU c54f35ca767986246321eb901baf8f5ff7923f6a;
  [ios-27](https://github.com/Scion-Project/scion-kernel/blob/8bee16f38f6e34751d2867a8945577edc7cd30c7/profiles/ios-27.conf)
  explicitly says not-implemented, arm64e, new XNU and no patches/ADT.
  Switching a profile string cannot supply a compatible kernel/header/library/
  userland ABI. A whole-tree switch invalidates source/dependency qualification;
  do not relabel our existing objects.
* Current `Makefile` adds `soc-status`; QEMU defconfig changes only a storage
  source-path comment. New SoC tables/runtime selection are useful references,
  not measured E1S support. `init.c`/userland build add Bluetooth audio and
  first-boot self-test plumbing, irrelevant to the minimal generic PID1 check.

**One cheapest next diagnostic:** root should admit exactly one finite direct
link from the preserved
`worktrees/vm-022-20261106/artifacts/avf-guest-link-inputs/preparation-4/prepared-link-inputs.json`
`next_owned_link_argv_template`, with the matching 1080 inputs, actual four tails,
Firehose/pthread providers and selected genuine cc_kext resource route. Reuse
the existing source-built driver/linker and command collector. Record its real
exit, stderr/undefined symbols and any produced Mach-O entry; do not run the
archive/package/guest or call an image complete. A missing required input is a
specific blocker, not a request for another executor. This audit does not grant
or execute that target command.

From the Scion side, this makes **A** (one current link diagnostic) cheaper than
**B** (a fresh stock `make qemu-open`, which would rebuild and defaults to the
UEFI route with 6G guest memory). **C**, native E1S adaptation, must proceed as an
independent source/hardware-contract track; generic guest success cannot choose
S24 MMIO, boot-chain compatibility, display, storage or input drivers. Root's
HakiOS and CN's E1S findings may change the final project-wide choice.

No local guest/device run establishes Scion's published Pixel/S9 claims here.
Networking failures, rejected raw-content blob mismatches and API compare
truncation are retained in the evidence; exact Git blobs/complete trees and
verified existing donor copies resolved the needed source identities. One new
platform header fetch remained unavailable and is not used for a content claim.
