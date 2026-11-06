# STR-006: reuse the accepted minimal RAM root

**The RAM-root bytes are ready now.** Reuse the existing 32,768-byte
`root.ramdisk` SHA256
`b26710980746c0fbc48f4d40f9b43533784617c7332ba54055e44da2d0f12b59` at
`MAIN/worktrees/vm-024-20261106/artifacts/avf-guest-mockfs/candidate-fac53e7-1/package-one/`.
It contains the exact 16,512-byte VM034 PID1
`fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3`
followed by 16,256 zero bytes. VM024 packaging, VM025 compiled admission and
VM034 source-built image are accepted and DONE. No rebuild, signing step,
filesystem conversion or new package format is needed.

The usable input packet is
[`accepted-input.json`](../../../fixtures/public/e1s-ramroot/accepted-input.json).
It binds those actual bytes, original capsules, current genuine kernel
`87496c21f41cdd56c748cb1cfad37dba8712b48a01a204dcbb298c0feac5e8fc`,
existing raw packager and original Scion XNUP packer. Its prospective argv adds
`ramdisk=ABSOLUTE_ROOT_PATH` to the existing kernel pack command, keeps
`--no-version`, and uses `-v avf_exit=1 console_quiet=0 rd=md0`. The command has
not run. A fresh output parent must exist before the original packer runs;
its output must be independently checked and resource admitted by root/CU.
After the pmap repair, adopt the actual new kernel through its reviewed lineage
rather than silently changing this historical kernel binding. Repacking the raw
root is unnecessary; a precise existing-packager argv is included for provenance.

The selected mockfs creates root/devfs/executable nodes in memory and exposes
raw device bytes as `/sbin/launchd`; its pager offsets are relative to the device.
The AVF shim's `ramdisk` member becomes `/chosen/memory-map/RAMDisk`, aligned to
16 KiB; IOKitBSDInit converts it to a 4 KiB-unit mdev. `rd=md0` selects that root.
APFS precedes mockfs, so fallback still must happen in the real boot. Selected
`kern_exec.c` falls back through development launchd names to `/sbin/launchd`.
The image is a static ARM64 Mach-O with UNIXTHREAD entry; no dyld or Apple
launchd is supplied. A successful mount, exec and initial-stack setup have not
been observed.

Source comparison uses actual VM008 guest sources and STR004's fresh prepared
E1S c886/c54+STM source root, not guest headers as E1S headers. All three mockfs
implementation files, memdev, syscall table, ARM64 syscall dispatch, locore
return assembly, syscall trap constant, open flags and initproc-exit source are
byte-identical. E1S `kern_exec.c` differs only in the inspected comments;
`vfs_conf.c` removes HFS entries and retains mockfs. IOKitBSDInit's native UFS
branch and guest virtio-root branches differ, while the RAMDisk/md path remains.
SLEH differences concern the guest's PSCI/cache-operation handling, not a new
PID1 syscall convention. These are narrow reuse facts; STR004's actual native
profile, compiled configuration and later E1S execution remain dependencies.
Native loader placement/DT and native shutdown are separate, not qualified here.

Preserve the actual code-signing policy. Scion's existing minimac defaults to
`bringup`; `security=full` enables process enforcement, while `kern_cs.c` also
respects the compiled configuration. Its null-signature hook returns success.
E1S lacks this Scion security-level selector and must be assessed against its
own final profile; its existing null-signature hook also returns success.
The fixture retains the actual guest kern_cs recipe flags. Do not add
`security=off`, `cs_enforcement_disable`, an authentication patch or a synthetic
qualification flag. Static compiled admission does not prove real exec policy.

Runtime success requires the **actual** PID1 line
`VM002: pid=1 ostype=Darwin owned-entry=v1`: `/dev/console` open succeeded,
getpid returned1, sysctlbyname returned Darwin plus NUL with length7, and write
completed. The source then calls exit0; failures use exit1/2 and a different
marker. Initproc exit intentionally panics. Require this identity marker,
matching initproc-exit panic, actual guest PSCI SYSTEM_OFF and terminal QEMU
result together. The earlier pmap panic followed by PSCIoff does not qualify.
The existing write loop makes bounded positive progress; **if exit returns,
PID1 loops forever on EL0 yield**. Keep the existing finite host watchdog.
A timeout or host QMP quit is never guest-stop success. The AVF stop source's
loader-return path is guest-specific; no native E1S stop claim follows.

Root/CU's next action is to combine the accepted root with the repaired genuine
kernel using the existing packer after independent admission, then perform one
bounded genuine guest experiment. This source-only packet executes no packager,
compiler, QEMU, phone or new harness. Original failures and accepted artifacts
remain unchanged. Original SR6 owns STR006 pending review/root acceptance.
