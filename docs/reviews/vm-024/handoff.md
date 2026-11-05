# REV-028 — independent VM-024 implementation and actual-data review

Verdict: PASS within raw packaging and structural host scope. No actionable
finding in the reviewed immutable-input workflow. Compilation, real kernel exec,
PID1 identity and signing policy remain outside this result.

Owner: `codex-review-boot-inputs-20261106-dw`, task `REV-028`, branch
`team/rev-boot-dw-20261106`, worktree `worktrees/rev-boot-dw-20261106`.
Only `docs/reviews/vm-024` changes. Original owner retains VM-024; this reviewer
retains REV-028 until root integration and fresh common-check acceptance.

## Exact reviewed implementation and package

Producer worktree: `MAIN/worktrees/vm-024-20261106`. Reviewed ordered commits:

- `19965c7a47c0123dfb2c8a746e35dba12b06bd91`
- `7a7123667c3df2e0beeabe2e09db934431783e2b`
- `ff41a8ebb3cb00721af114491a7e235f50190b5f`
- `b716bbde78f7223c12ab9f130ec1a7d4b398a831`
- `2257b31c248cafbc65b3a7824b6265a672e04f78`

The packager at **all five commits** and current immutable producer file has
SHA256 `a850d42599874826deb512c36833557bfc90e2a2de905de74c19834f54e5bd0b`.
Actual runner SHA256 is
`442016995020c45c07057e3c7644cd3d0111e732bc644f0150466f6c5aa9e426`.

Preferred package, relative to MAIN:
`worktrees/vm-024-20261106/artifacts/avf-guest-mockfs/candidate-fac53e7-1/package-one`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `root.ramdisk` | 32768 | `b26710980746c0fbc48f4d40f9b43533784617c7332ba54055e44da2d0f12b59` |
| `package.json` | 2205 | `c8140c21b5fb72bfde6bf08d24af7a9b7b945fc914503bb0408c5899b746ef51` |

The second original pristine package is identical. Independent byte comparison
finds the exact 16512-byte VM-034 executable at offset zero, followed by exactly
16256 zero bytes. Executable SHA256:
`fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3`.
Both flags remain `executable_qualified:false` and `guest_executed:false`.
The packaging metadata carries the original provenance object and descriptor hash
`28ea3ec9dab6cc84b0dbd024271e6b41413e69e62f060830ee0426a6ff2c0b25`.
The candidate descriptor is
`0bdfc24445a1a213790546a79a62975691c9ff334cd6bedb6f954859cf41f63e`.
External compiled admission
`72243a1fabe289cd5c313804be0ad187091fb9b4e668c3c992dc23cd4186cbf0`
and raw build evidence
`01488b5be195fe61a0e0880c60b51190a7cb38c33dd0ba7af3d68ac22bc266b2`
remain separate evidence. Packaging does not promote their scope.

The producer output manifest SHA256 is
`aa8c56bbdbad5190d3e2cb509a3ba62493d4fb56c0376ae4cf4cd219996fb0c7`;
rehash it and both preferred output files before downstream use. The manifest is
`docs/procedures/avf-guest-mockfs/candidate-output-manifest.json` in producer WT.

## Selected-source assessment

Every one of the thirteen source/license bindings matches both SHA256 and
canonical Git blob identity. Source lineage is accepted qemu composition from
public XNU `c54f35ca767986246321eb901baf8f5ff7923f6a` and Scion
`a6f4bc38aa244359cd365c976244a88c9d6b3304`. Composed files are explicitly
separate from unmodified public originals. Their pinned paths and identities are
in producer `fixtures/public/avf-guest-mockfs/sources.json` and this run's inputs.
No source tree, physical witness or original package was modified.

The reviewed declarations establish the **raw** format:

- `bsd/miscfs/mockfs/mockfs_fsnode.c:78–85` sets executable-node size to backing
  device size; lines338–349 map its memory pager using the memdev's fixed12-bit
  page units. No filesystem image header, inode or archive is expected.
- `mockfs_vfsops.c:83–86,118–126` creates/adopts root, dev and executable nodes.
  `mockfs_vnops.c:121–135` resolves `sbin` back to root and `launchd` to the file;
  `mockfs_blockmap` maps direct device offsets. Thus `/sbin/launchd` begins at
  backing-image offset zero and includes the padded device extent.
- Selected `avf/shim/avfboot.c:39,756–757,803–805` rounds RAMDisk size to0x4000,
  copies raw input and zeroes trailing bytes. Lines932–934 emit two uint64 values
  for physical base/rounded size in `/chosen/memory-map/RAMDisk`.
- `IOKitBSDInit.cpp:770–781` reads that property and creates memdev with base/size
  shifted12. This validates the 16KiB padded image versus 4KiB memdev-unit facts,
  without asserting any physical allocation or actual mount.
- `vfs_conf.c:260–294` attempts APFS before mockfs; `kern_exec.c:7059–7066`
  includes `/sbin/launchd` after development candidates. Real fallback/exec is
  unmeasured. Shim lines859–862 default `console_quiet=1` and add `rd=md0` only
  when no explicit root argument exists: integration must choose its own actual
  console/root arguments and must not infer marker visibility from this image.

Original licenses remain in the thirteen source bindings; review copies no Apple
binary or SDK. The image contains the owned source-built test executable, not
Apple's launchd.

## Independent controls and measured results

Planned `REVMOCKFS-001` before execution. `verify.py` independently compares
actual bytes, rehashes all146 original structural-run artifacts and39 actual
packaging-run artifacts, checks thirteen canonical source/license identities and
nine candidate/review/warning pins. It does not run either producer test suite.

`runs/review-1/report.json`: **465 checks and19 rejection controls PASS**, with
six bounded serial readonly subprocesses (five guarded `git show` commands and
one real packager CLI verification). All exited0 and were reaped. Every subprocess
has three >=4GiB admission samples spaced >=1s; lowest was15,837,200,384 bytes.
The controller's actual `/proc/self/status` VmHWM was23,044,096 bytes. Controller
and children inherit a256MiB address-space limit; child deadline10s/owned process
session cleanup and outer timeout120s. This is current-process HWM, not a claim
of continuously measured aggregate RSS. No compiler/linker/VM was executed.

Controls reject changed prefix, truncation, extension, nonzero padding even with
an updated image hash, false qualification/execution flags, wrong root/path or
alignment, wrong provenance input hash, wrong CPU, malformed command extent,
invalid entry and a dynamic command. Final-component symlink and nonblocking FIFO
input are rejected. Existing destination/sentinel is preserved. A deterministic
in-process seam invokes the **real parser**, then changes a **local copied file
on disk** before the real copy: inode timestamps detect the mutation and reject;
its partial image remains without success metadata. No producer input is edited.

An additional positive boundary probe adds opaque invalid signature bytes with
a bounded LC_CODE_SIGNATURE: the parser accepts them structurally, as documented.
This explicitly demonstrates that code-signature validation is **not** claimed.
No unexpected test failure occurred. A preparation CLI invocation mistakenly
used unsupported `--kind`/`--timeout`; exit2 and correction are retained in
`preparation.json`. It ran no experiment and changed no registry state.

## Trust and remaining gates

Input bytes use O_NOFOLLOW/O_NONBLOCK plus fstat regular-file admission, bounded
parsing, streamed hash and before/after inode size/mtime/ctime comparison.
O_NOFOLLOW protects the final path component; caller-controlled parent directories
are not a sandbox. Output creation requires a new final directory and exclusive
image creation; a failed copy remains inspectable. Producer before/after snapshots
and this review's post-checks preserve exact original content/size/mode.

Provenance is caller attribution, not authenticated build/licensing evidence.
The parser/verify pair is a local structural consistency check; self-consistent
replacement metadata is not cryptographic authorization. Immutable trusted
provenance/output directories plus external fixed candidate/manifest hashes are
required. Concurrent hostile writers to metadata or output parent paths are
outside this reviewed workflow; no filesystem race-proof sandbox claim is made.

Missing runtime evidence remains: actual kernel/mockfs configuration and image,
mountroot, default initial stack, exec/code-signing policy, actual PID1/Darwin
syscalls and console, panic/PSCI stop, and any native S24 behavior. VM-025 owns
candidate preflight. Original VM-002 and all other reservations remain untouched.
