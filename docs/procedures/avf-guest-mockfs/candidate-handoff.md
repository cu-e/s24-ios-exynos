# VM-024 actual VM-034 candidate packaging handoff

Original owner `codex-guest-exec-20261106-df`, branch `team/vm-024-20261106`,
worktree `worktrees/vm-024-20261106`. Root explicitly resumed this owner and
authorized actual raw mockfs packaging without compilation or QEMU. The original
synthetic results and immutable evidence remain unchanged.

## Result and exact inputs

The unchanged frozen packager SHA256
`a850d42599874826deb512c36833557bfc90e2a2de905de74c19834f54e5bd0b`
successfully packages the actual source-built VM-034 PID1 reviewed by REV-026.
Code/control commit: `ff41a8ebb3cb00721af114491a7e235f50190b5f`.

All original candidate inputs remain at
`MAIN/worktrees/vm-034-20261106/artifacts/avf-guest-pid1-build/build-1/`:

| Input | SHA256 |
| --- | --- |
| `pid1` | `fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3` |
| `candidate.json` | `0bdfc24445a1a213790546a79a62975691c9ff334cd6bedb6f954859cf41f63e` |
| `mockfs-provenance.json` | `28ea3ec9dab6cc84b0dbd024271e6b41413e69e62f060830ee0426a6ff2c0b25` |
| Raw build `evidence.json` | `01488b5be195fe61a0e0880c60b51190a7cb38c33dd0ba7af3d68ac22bc266b2` |

The owned source SHA256 is
`68de57b2e27480f39cabdcf1372176ddbf8e275b9c5309c2ac529c6e0be01190`.
External REV-026 compiled admission SHA256 is
`72243a1fabe289cd5c313804be0ad187091fb9b4e668c3c992dc23cd4186cbf0`,
review evidence SHA256 is
`355fec37eddabb98edfdde1f4c8301366f7d9974ffff0ba23a3a3fe07e79d24c`.
Their paths and exact independent review-report binding are in
[`vm034-candidate.json`](../../../fixtures/public/avf-guest-mockfs/vm034-candidate.json).
The runner rehashes these nine candidate/review/warning files and all 13 original
source/license files before and after packaging, including canonical Git blob
SHA1 for the original source files. Content, size and permission snapshots match.

## Produced immutable handoff

Preferred package directory, relative to MAIN:

`worktrees/vm-024-20261106/artifacts/avf-guest-mockfs/candidate-fac53e7-1/package-one`

| Output | Bytes | SHA256 |
| --- | ---: | --- |
| `root.ramdisk` | 32,768 | `b26710980746c0fbc48f4d40f9b43533784617c7332ba54055e44da2d0f12b59` |
| `package.json` | 2,205 | `c8140c21b5fb72bfde6bf08d24af7a9b7b945fc914503bb0408c5899b746ef51` |

The image consists of the exact 16,512-byte executable prefix plus 16,256 zero
bytes, rounded to the selected AVF shim's 16 KiB memory-root alignment. The
original provenance object and descriptor hash are preserved exactly. A second
pristine package in sibling `package-two` has identical image and metadata hashes.
Separate tampered copies preserve every expected negative result; neither
pristine package nor any source/candidate/review input was modified by controls.
[`candidate-output-manifest.json`](candidate-output-manifest.json) binds all four
pristine output files to their exact MAIN-relative paths and all external pins.

The image is the raw mockfs backing bytes for `/sbin/launchd` and `rd=md0`.
Payload construction, kernel/loader selection, device tree and physical placement
remain separate integration responsibilities. Consumers must independently
rehash the output manifest and exact image/metadata before use.

## Actual checks and evidence

Registered experiment `MOCKFSPACK-002`, then executed at the code/control commit:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
python3 -s fixtures/public/avf-guest-mockfs/package_candidate.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-mockfs/candidate-fac53e7-1
```

Exit 0; all 94 source/binding/packaging controls passed, using 11 real serial CLI
children. Checks cover two actual pack/verify pairs, deterministic bytes/metadata,
independent full-prefix and zero-tail comparison, independent image hash,
provenance preservation, output-reuse rejection, changed prefix, truncated and
extended image, false qualification flag, wrong provenance input hash and nonzero
padding. Every command's actual argv, exit, duration and stdout/stderr hashes are
retained. No unexpected failure occurred. All 39 run artifacts are indexed.

Three one-second-spaced MemAvailable samples were 16,011,591,680,
16,028,889,088 and 16,030,035,968 bytes. The checker `/proc/self/status` VmHWM was
21,467,136 bytes; maximum child self-reported VmHWM was 20,127,744 bytes. Children
inherit a 256 MiB address-space limit and each has a finite ten-second deadline.
Only owned child process groups can be signalled. These are actual per-process
kernel HWM reports and sampled observations, not continuous aggregate RSS proof.

[`candidate-evidence.json`](candidate-evidence.json) binds the exact tested commit,
runner, descriptor, frozen packager, Python executable and measured report/index.
Report SHA256:
`26e65cec9ed1b22b6451a17184d29ce11c76d1e7d7872bbdea050a7805ca7c82`.
Artifact manifest SHA256:
`fff2d1c681758a63884b589594dc73bf1f18d3f0ad73d6059ed5cad95990cc14`.

The original source-build warning is retained verbatim and by source-file hash:

```text
ld: warning: directory not found for option '-F/System/Library/Frameworks/'
```

Packaging did not acquire or consume an SDK, proprietary filesystem tool or
proprietary image. It executed no compiler, linker, guest or physical device.

## Remaining acceptance boundaries

Every package retains `executable_qualified: false` and `guest_executed: false`.
REV-026 independently reviews compiled ABI/static structure; VM-025 separately
owns exact candidate preflight. Their results are separate evidence. Packaging
does not establish XNU mountroot, exec, initial stack, code-signing policy, PID1
identity, Darwin syscalls, console, panic/PSCI stop or any native S24 behavior.

Send this exact manifest and scoped commits to root and kernel integrator
`codex-integrator-kernel-20261106-cm`. Independent packaging review, integrator
acceptance, MAIN publication and fresh common checks remain pending. The original
VM-024 owner retains the task and does not record completion before acceptance.
