# VM-024: raw executable memory-root packaging

Owner: `codex-guest-exec-20261106-df`. Worktree `worktrees/vm-024-20261106`,
branch `team/vm-024-20261106`. This is source review and structural host tooling.
No compiler, linker, QEMU or physical phone is used.

## Actual selected source contract

The selected mockfs does not parse a filesystem container. Its mountroot creates
three in-memory nodes: root, a devfs directory, and one executable file backed by
the entire root device. `mockfs_lookup` resolves `sbin` to root and `launchd` to
that file. Thus `/sbin/launchd` exposes raw backing-device bytes starting at zero;
`mockfs_fsnode_create` takes the file size from the backing device, and
`mockfs_blockmap` maps file offsets directly to device blocks. There is no archive,
inode table, executable filename or mode to write into the image.

The selected Scion AVF shim (`avf/shim/avfboot.c`) accepts the XNUP `ramdisk`
entry, rounds its size to `PAGE_SIZE_MAX = 0x4000`, copies it after the kernel,
zeroes the trailing bytes, emits `/chosen/memory-map/RAMDisk` as two uint64 values
(physical base and rounded size), and adds `rd=md0` unless already supplied.
`iokit/bsddev/IOKitBSDInit.cpp` converts that property into an mdev. The memdev
base and size use 4 KiB units; mockfs's pager compensates with a 12-bit shift.
The packager produces an already zero-padded 16 KiB multiple; the shim's next
rounding therefore preserves its exact size. It does not select a physical
address, create a device tree, alter boot arguments or construct an XNUP payload.

APFS is tried before mockfs by the composed `vfs_conf.c`; raw executables must
reach the mockfs fallback. `kern_exec.c` eventually selects `/sbin/launchd` after
unavailable development paths. These source facts do not establish a successful
mount, code-signing admission, exec, syscall, PID1 or stop result.

All 13 source/license identities are bound in
[`sources.json`](../../../fixtures/public/avf-guest-mockfs/sources.json), including
streamed SHA256, canonical Git blob SHA1, original full commit and public URL.
Unchanged public files and Scion-composed files are distinguished explicitly.
The lineage is accepted VM-007 source composition with VM-008's immutable copy;
no native E1S object or header is consumed. Original XNU APSL/per-file and Scion
component notices remain in their original source locations. This independently
authored Python tool does not copy source implementation or replace those licenses.

## CLI and handoff

Given a separately qualified **owned, source-built** static ARM64 executable,
write a provenance descriptor identifying its exact source pins and build evidence:

```json
{
  "origin": "owned-source-built",
  "input_sha256": "EXACT_EXECUTABLE_SHA256",
  "sources": [{"repository": "PUBLIC_OR_OWNED_SOURCE", "commit": "FULL_COMMIT"}],
  "build_evidence": {"path": "EXISTING_EVIDENCE", "sha256": "EXACT_EVIDENCE_SHA256"}
}
```

```sh
python3 -s tools/build/avf_guest_mockfs.py pack \
  --input OWNED_PID1 --input-sha256 EXACT_EXECUTABLE_SHA256 \
  --provenance PROVENANCE_JSON --out NEW_DIRECTORY
python3 -s tools/build/avf_guest_mockfs.py verify --package NEW_DIRECTORY
```

`root.ramdisk` contains only the exact executable prefix and zero padding.
`package.json` binds its size/hash, executable prefix size/hash, structural
description, descriptor bytes hash, tool/source-binding hashes, intended
`rd=md0` and `/sbin/launchd`, and the unchanged provenance object. Identical
inputs and metadata produce identical images and package metadata. Parent
directories may be created; the final output directory must not exist. A failed
copy remains available for inspection, without success metadata. Input is opened
without following a symlink; inode size/timestamps and bound content hash are
checked during the streamed copy. All hashes stream in 64 KiB chunks.

Provenance fields are attribution supplied by the caller. Their presence and
input hash are checked; this tool does not audit a build log, licensing, toolchain,
source completeness or ABI. Package metadata always states
`executable_qualified: false` and `guest_executed: false`. VM-025's current legacy
PID1 has a separately diagnosed x1 syscall-clobber defect; it is not consumed here.
The new VM-034 candidate needs its own build and independent qualification before
any real candidate packaging/guest integration. The blocked VM-002 harness stays
unchanged. Pass the eventual `root.ramdisk` as the guest payload's `ramdisk` member
only through its owning task and after applicable acceptance/resource gates.

The parser deliberately admits a narrow static format: thin little-endian
ARM64_ALL `MH_EXECUTE`, one `LC_UNIXTHREAD` with `ARM_THREAD_STATE64`, file-backed
executable entry, bounded command/segment/section/linkedit ranges, and supported
metadata commands. Dynamic/unknown commands, LC_MAIN, arm64e, kernel entries,
overlapping segments and malformed/truncated extents are rejected. Maximum input
16 MiB, command table 1 MiB and 1024 commands are local minimal-PID1 policy limits,
not limits asserted for XNU. Code-signature bytes may be carried but are not
cryptographically validated. This is not a general Mach-O validator or SDK tool.

## Reproduce bounded controls

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
python3 -s fixtures/public/avf-guest-mockfs/check.py \
  --main /home/egor/dev/pet/s24-ios-exynos --out NEW_CONTROL_DIRECTORY
```

The checker reads all pinned source files without modification, generates tiny
synthetic Mach-O structural inputs, and drives the actual CLI. Generated inputs
contain headers and zero bytes, no executable instruction payload, and are marked
`synthetic-structural-control`. Every child has a finite deadline, inherits a
256 MiB address-space limit, and reports actual `/proc/self/status` VmHWM. The
parent also samples each owned child's `/proc` and retains the highest observed
VmHWM, command, exit, elapsed time, stdout/stderr and their hashes. Only its own
process group is signalled on a deadline. No build or VM lease is used.

Measured evidence and preserved artifacts are listed in `evidence.json`. Review,
integrator acceptance, MAIN publication and fresh common checks remain separate;
the original owner alone completes the ledger after those gates.
