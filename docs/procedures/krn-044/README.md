# KRN-044: one-object rebuild loop for the kernel that runs on the phone

Date: 2026-11-13. Owner: `claude-opus-krn044-20261113`. Evidence kind: host-test. No phone action.

The kernel on the phone in NAT-062..113 is STR-041's link (`kernel.unstripped`, `4c9536d8...`) plus NAT-020's 29
`deny_storage` entry stubs (`kernel.no-storage`, `7ceda59b...`, pinned in `nat-065/build.py`). Until now every kernel
change on the NAT line was a binary patch or a boot-arg. `rebuild.py` closes the loop for source changes:

1. replays one object's compile exactly as it was executed (argv, cwd, environment from the compile evidence that
   produced STR-041's copy, e.g. `worktrees/str-027-.../build-002/evidence.json`), on the original source or on a copy
   changed by `--patch`; the source tree is never written;
2. relinks with STR-041's recorded driver argv in a private copy of the link directory;
3. reruns STR-041's independent image checks (`verify_image.parse`, segment order, link address, entry in
   `__TEXT_EXEC`, `nm -u` empty, unique `__start`, one `LC_UUID`);
4. applies NAT-020's `deny_storage` table to the result.

It runs only the project's own source-built clang/ld; no upstream build script.

## Results

| Run | Object | Kernel | Checks | Stubs |
| --- | --- | --- | --- | --- |
| `unchanged-001` | recompiled `iokit/MiniIOMobileFramebuffer.cpo` = `189a9585...`, **byte-identical** to the linked one | **byte-identical to `4c9536d8...` after replacing the link directory path** (0 bytes differ); raw: 78,078 bytes differ, all in debug-map path strings | pass | 29 applied; on the normalized image the result **equals NAT-020's `kernel.no-storage` `7ceda59b...`** |
| `marker-001` | `0001-krn044-marker-string.patch` (one IOLog string) → `44b2eb5a...` | `a36cfbcb...`, 21,539,872 B, the new string present once; segment VM layout unchanged | pass | 29 applied → `6f1c7477...` |

Reproducibility details found on the way:
* the linker writes each object's **absolute path** and **mtime** into the debug map (N_OSO stabs), so the private
  link directory has the same path length as STR-041's (padded with `x`) and copies keep their mtimes; the only
  remaining difference is the path text, which the tool normalizes for the comparison;
* the executed compile argv differs from the STR-016 recipe file (`consumer-005` vs `prepare-003` context paths): the
  executed one is used, and it reproduces the object.

## What this does not show

* That a rebuilt kernel boots: nothing ran on the phone.
* Changes to headers or to more than one object: the loop recompiles one object; a header change needs every object
  that includes it (the depfiles list them) — not done here.
* `check_all_exports` / private37 ABI: unchanged from STR-041.

## Use

```
python3 docs/procedures/krn-044/rebuild.py --out artifacts/<task>/kernel-NNN --object iokit/MiniIOMobileFramebuffer.cpo \
    --patch <diff for that source file> --expect-string "<new text>"
```
The output `kernel.no-storage` replaces `artifacts/nat-020/build-003/kernel.no-storage` in a NAT image build (its
SHA-256 pin in `nat-065/build.py` must be overridden by the wrapping build, as other NAT builds override fields).

## Later change to rebuild.py (2026-11-13, NAT-071/NAT-115)

The source argument is found by suffix instead of being assumed last (osfmk-b's compile records put `-o` after the source), and a
failing command reports its `error:` lines. With the changed tool the unchanged rebuild was rerun
(`artifacts/krn-044/recheck-002`): object identical, kernel identical after path normalization, NAT-020's stubs reproduce
`7ceda59b...`. The evidence hashes above refer to the first version of the tool.
