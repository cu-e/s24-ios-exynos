# NAT-099: the Stage B small root, built on the host

Host code and tests. Evidence kind **host-test**. Nothing here ran on the phone, and nothing here shows that
the library is inserted, that `backboardd` starts or that anything is drawn.

## What it builds

`build_stage_b_root.py` takes NAT-096's quiet Stage A small root (md0 of `loader-diag-xnu-sq-md1`:
18 Apple LaunchDaemons plists without `lsd`, plus the `ps` heartbeat, 25 files, `root.apfs` SHA-256
`62801cec…7057`) and adds exactly three files and the `lib` directory:

| Path in the small root | What | Source |
| --- | --- | --- |
| `LaunchDaemons/com.apple.backboardd.plist` | Apple's `backboardd` job with one key added, `StandardErrorPath=/dev/console` (what the donor's `mkjobs.py` writes) | the 20F66 root's plist, SHA-256 `d5f1e51f…a6c0`, as written by `mkjobs.py` `e708b86f…c647d` |
| `lib/libhakios.dylib` (0755) | the donor's tracked prebuilt library | IOS-014, SHA-256 `530c2e68…4dad6`, 73,448 bytes |
| `etc/inject.conf` | `/redwood/lib/libhakios.dylib backboardd containermanagerd containermanagerd_system` | the donor's `build.sh` `INJECT` first line; read by the donor's `init` (`configure_inject`), which hands it to `sysctl kern.exec_inject` |

The builder refuses: a base `root.apfs` that is not the pinned one, a dylib that is not the pinned prebuilt, a
`backboardd` plist that is not Apple's plus the single `StandardErrorPath` key, an output directory that exists,
and a result whose tree differs from the base's in any path but the three. The image is written by the donor's
`mkapfs.py` with the arguments the chain tool uses, then read back twice (the donor's `verify.py` content
comparison and the kernel's own `apfs_lib`, 28 of 28 files, no mismatch).

Result (local, gitignored): `artifacts/nat-099/pid1-sb2/{root/,root.apfs,build.json}`; `root.apfs` is 4,194,304 bytes
(the md0 region size), SHA-256 `c22b3867…31d5`, 28 files, 916 of 1024 blocks free.

## Why separate from Stage A

The injection stays one removable step (this root differs from Stage A in three files), so a later run with and
without it can be compared. The image, its driver and its decision are **not** built here; they follow the reading
of the Stage A run (NAT-098), because that reading decides whether the log window can show `backboardd` at all.

## Checks

`test_nat099.py`, 19 tests, all pass:

* synthetic: `tree_diff` (added/removed/changed, mode change), `tree` (files, modes, symlinks), every refusal of
  `check_backboardd_plist` with its exact message (unpinned Apple plist, wrong error path, a second changed key,
  an extra key, unpinned `mkjobs` result), refusals of `build` (existing output, base without an image, base with
  another image);
* real artifacts (skipped when absent): the tree differs from NAT-096's in exactly the three files and `lib`
  (25 -> 28 files), `inject.conf` bytes and modes, its first token equals the dylib's `LC_ID_DYLIB` install name
  (read with `tools/ios/macho_audit.py`), every injected name is the program of a job plist in the image, the
  `backboardd` plist equals Apple's plus the error path, the record matches the image file, size equals the md0
  region, the kernel readback was clean, and the list fits the 4096-byte buffer the donor's `init` reads.

No mutation pass was run on `build_stage_b_root.py` or its tests. The refusal and tree tests are written
against hand-derived cases, but how many of their assertions would catch a mutated builder is **not measured**.

## Evidence levels

| Level | State |
| --- | --- |
| code written | yes |
| built | yes (the host image above) |
| checked in a model | tests above, plus the kernel `apfs_lib` readback of the image |
| ran on the S24 | no |
| showed real iOS UI | no |

## What this does not establish

* That the donor's `init` reaches `configure_inject` in this project's chain, or that the kernel accepts the list
  (strings in `Image.payload` only; IOS-014).
* That dyld inserts the library, that its hooks find the expected bytes in this phone's shared cache, or that
  `backboardd` starts and survives (`UserName=mobile`; B11 is the open hypothesis about missing privileges).
* That `backboardd`'s stderr leaves room in the 8 KiB + 32 KiB log window (the donor's `mkjobs` warns about about
  1 MB per 30 s from SpringBoard); the window may be filled again, as `lsd` filled it in NAT-093.
* Anything about display, input, GPU or a first frame.

## Files

`task.json`, `build_stage_b_root.py`, `test_nat099.py`, `README.md`, `evidence.json`.
