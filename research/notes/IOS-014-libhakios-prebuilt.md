# IOS-014: the donor's prebuilt `libhakios.dylib`, inspected statically (Stage B, blocker B10)

Evidence kind: **source-review** (host, read-only). Nothing was executed, nothing was run on the phone, and nothing here shows
that the library does what its source says.

## Correction of an earlier statement

`docs/strategy/2026-11-12-ios-critical-path.md` (B10 row) said the donor's `prebuilt/userland` "is not in the pinned checkout".
That was wrong. `references/hakios` is a sparse, blob-less clone; the files are tracked at the pinned donor commit
`87bf4851bcc9cbb24fd79997820aa3661abe4ea5` (`git ls-tree -r HEAD` lists `prebuilt/userland/libhakios.dylib`, `hello_dyn`, `libhakios.sb.dylib`
and others) and were simply outside the sparse set. They were added to the sparse set for this task (three blobs plus two headers and one
source file, all fetched from the pinned commit; `references/` is gitignored).

## What was fetched

| File (donor path at 87bf485) | Bytes | SHA-256 | In donor `prebuilt/SHA256SUMS` |
| --- | --- | --- | --- |
| `prebuilt/userland/libhakios.dylib` | 73,448 | `530c2e68…4dad6` (`530c2e681093ece2afe7f5180a4723bd46d92f7af39edc0a8c77136136a4dad6`) | yes, equal |
| `prebuilt/userland/hello_dyn` | 49,696 | `e5044262e71eb9277ccc2e4d58d9868a8b535aec0c3bf8c5b9f6ab604f978f46` | yes, equal |
| `prebuilt/SHA256SUMS` | 2,459 | `aefdece288609090352b20545039167a5f9cc9f9073163065f8ac073db2241e6` | (itself) |
| `userland/src/inject.c` | | `905e4556a7b3decd311850fee8eb78eba02b94535574412bb97b0617d1d5f490` | |
| `userland/src/hakios.input.h` | | `9d5b49d85c4aed8a79ca4af0b2c9545ae17ff7e896de4cbe603de29b924f8c8d` | |
| `userland/src/hakios.gl.h` | | `52aba74c5ea5ad2515c0f840d52a572420aae2dc98288db34b89a9ad3a02ddd9` | |
| `userland/src/hello_dyn.c` | | `9407b9b15482aa3b4d83255ab04ea335ca5bc3cfb2f0f8eb69019a8f5986ff71` | |

The equality with `SHA256SUMS` only shows that the blob is the one the donor listed; both come from the same repository. The listing says
`Built 2026-10-25 22:53 from this tree`; the pinned commit is dated 2026-11-04. The two are not the same moment.

## What the binary is (tools/ios/macho_audit.py `audit`, `docs/procedures/ios-014/inspect_dylib.py`)

* Mach-O 64-bit `DYLIB`, arm64 (plain, no pointer authentication), `LC_BUILD_VERSION` iOS minos 16.5.0, sdk 16.4.0, chained fixups, 19 load
  commands, UUID `cabf58fb06b437b8b1ea70ea4013172d`.
* Install name `/redwood/lib/libhakios.dylib` (the path the donor's job table injects). Dependents: CoreFoundation, IOKit, `libobjc.A.dylib`,
  `libSystem.B.dylib` (all four are images of the dyld shared cache; no Foundation, no QuartzCore).
* One initialiser: `__TEXT,__init_offsets` holds one offset (0x4000) and the defined symbol at that address is `_hakios_init`; inject.c has
  one `__attribute__((constructor))`, `hakios_init`.
* No `svc` instruction in `__TEXT,__text` (a raw system call would bypass the imports).
* 89 undefined symbols (the full list is in `docs/procedures/ios-014/inspection-libhakios.json`). Process-, file- and kernel-facing ones:
  `open`, `read`, `write`, `access`, `dlopen`, `dlsym`, `sysctlbyname`, `setenv`, `vm_protect`, `mach_task_self_`, `sigaction`, `signal`, `raise`,
  `pthread_create`, `sleep`, `usleep`, `notify_register_check`, `notify_set_state`. **Absent:** `unlink`, `rename`, `mkdir`, `chmod`, `mount`,
  `ioctl`, `fork`, `exec*`, `socket`, `connect`, `kill`.
* 8 imports are not named in inject.c; all are compiler or runtime artefacts (`___CFConstantStringClassReference`, `___error`,
  `___memcpy_chk`, `___stack_chk_fail`, `___stack_chk_guard`, `_bzero`, `_mach_task_self_`) except `__dyld_get_shared_cache_range`, which inject.c
  calls in `hakios_init` (`_dyld_get_shared_cache_range(&length)`, one leading underscore fewer in the source token).

## Source against binary, row by row

`inspect_dylib.py` searches every C string literal of inject.c and its two headers in the whole file (named by section) and every hex constant of
at least seven digits as a `movz`/`movk`/`movn` or `orr`-bitmask value. Full rows: `docs/procedures/ios-014/inspection-libhakios.json`.

| Group | Rows | Result |
| --- | --- | --- |
| String literals of inject.c + headers | 125 | 101 found (95 in `__cstring`, 5 in `__TEXT,__const`, 1 weak: `redwood` only as a substring of the install-name path in a load command), 24 not found |
| Strings of the binary that no literal of the source contains | 1 | `?` only; the rest is explained |
| Shared-cache constants (20F66 addresses) | 16 | 9 found exactly, 4 vtable bases found only as a nearby sum (`VSLOT(vtable, off)` is added by the compiler), 3 not found |
| Imports named in inject.c | 89 | 81 named, 8 listed above |

The 24 missing literals belong to exactly two source features, and the source says neither is on the default path:

1. `brightness_fixes()` (the `-[BLControl waitForALSArrival]` replacement: `BLControl`, `waitForALSArrival`, the "five seconds" message,
   constant `0x1af043734`) is `__attribute__((unused))` and its call site is commented as "not used for now" (inject.c lines 568 and 1223-1229).
   The binary has no trace of it, which fits.
2. `watch_metallib_lookups()` (`NSBundle`, `URLForResource:…`, `ca_metallib=`, `metal_watch=1`, `pipelinelib`, `default`, `metallib`, `path`, the
   `hakios: metallib lookups…` messages) runs only when the boot-args hold `metal_watch=1` or `ca_metallib=` (inject.c lines 1218-1220). The
   binary does not link Foundation, so it has no such code at all. This is the one visible difference between the binary and the pinned source
   that is not explained by dead code: the binary was built before this debugging aid existed, or without it.

Three constants are not found: `0x180000000` (`CACHE_BASE`, which may be encoded another way, e.g. folded into the `slide` arithmetic),
`0x1884a9350` (the `function_uniform` hook, which sits inside `if (gl_function_values != NULL)` after `if (gl_loaded)`) and `0x1af043734`
(item 1 above). "Not found" means this search did not find them, not that the code is absent. The six hooks of `window_server_fixes()` that are
installed whatever else is present (`is_ready`, `ignore_update_p`, `begin_update`, `finish_update`, `renderer`, `render_update`, addresses
`0x1882f0908`, `0x1882e0c90`, `0x1882ddda4`, `0x1882c8568`, `0x1882e2548`, `0x18835770c`) are all found exactly. One was checked by hand from
the raw words at `0x4254`-`0x425c`: `movz x2,#0x0908; movk x2,#0x882f,lsl #16; movk x2,#1,lsl #32` = `0x1882f0908`, followed by `mov x1,x19; bl`,
which fits `replace_virtual(name, slot, expected_original, replacement)`.

Whether those addresses are the right ones for **this** phone's 20F66 shared cache is not decided here; IOS-013 compared the donor's hook
addresses with the project's cache, and the library itself checks the bytes at run time before it patches (inject.c header comment, to be
observed on the phone, not assumed).

## What the source says the library can do (source-review of inject.c, not a measurement)

Writes only to file descriptor 2 (`say()`); opens `/dev/hakios-touch` read-only; reads `kern.bootargs` through `sysctlbyname` with no new value;
`dlopen`s `/redwood/lib/libhakios.gl.dylib` only if `access(R_OK)` succeeds (whether the project's root holds it was not checked here; the donor installs it only with its OpenGL build option, so without it `gl_loaded` stays
false and the GL hooks are not installed); `setenv`s `CA_*` variables named by boot-args; patches pages of its own process with `vm_protect`. The import set of the
binary is consistent with this (nothing that removes, renames, mounts, spawns or opens a socket). It cannot be proved from the imports alone that
the binary calls them only as the source does; an equal import set is a necessary condition, not a proof.

## `hello_dyn` (the donor's dynamic test program)

`prebuilt/userland/hello_dyn` is a 49,696-byte arm64 `EXECUTE` (iOS minos 16.5, sdk 16.4, chained fixups, `LC_MAIN`, `/usr/lib/dyld`, linked only
against `libSystem.B.dylib`). Its five C strings equal the five literals of the 20-line `userland/src/hello_dyn.c` byte for byte; it prints
pid, `uname`, heap and stack addresses and argv and returns 7. It is a ready dynamically linked test program **without** an SDK, which is what
B9's readiness row (c) asked for. It would not add evidence for the milestone "a dynamic Mach-O runs under this launchd" (Apple's own `launchd`
and `lsd` already did, NAT-084/093), but it is a small program that does not depend on any Apple daemon.

## What this does not establish

* That `libhakios.dylib` is a build of the pinned `inject.c`: it is older than the commit and lacks the metallib watcher; no rebuild is possible
  here. It is a binary supplied by the donor.
* That it runs: no run on this phone, no dyld insertion observed. The kernel side (`kern.exec_inject`; the strategy doc's string search of `Image.payload` found 7 hits) is also string evidence only.
* That a first frame appears. B9 is unchanged: no frame on the panel, no backboardd output yet.

## Decision

The prebuilt dylib **may be staged** into a Stage B small root by a later host task, with the residual risks named: unreproducible binary (older than
the pinned source), import set consistent with the source but not proven equal in behaviour, all effects inside the RAM-only userland of the test
image (the dylib is loaded into `backboardd`/`containermanagerd`, writes only to stderr and reads `/dev/hakios-touch`), 20F66 addresses checked by the
library at run time. Stage B must keep the injection a separate, removable step (one job-table change) so that a run with and without the library can
be compared. The alternatives remain: rebuild from source against the iPhoneOS 16.5 SDK (owner download, Apple licence) or against Apple's open
headers with `-undefined dynamic_lookup`.

Files: `docs/procedures/ios-014/{task.json,inspect_dylib.py,test_inspect_dylib.py,inspection-libhakios.json,evidence.json}`;
raw audits under `artifacts/ios-014/` (gitignored).
