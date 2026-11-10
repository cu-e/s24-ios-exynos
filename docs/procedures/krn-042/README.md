# KRN-042 — KRN-041 export fixes rerun from main (2026-11-10)

Evidence category: **host-test**. Nothing was booted and the phone was not used.

## Result

`python3 -I docs/procedures/krn-041/missing_exports.py --run main-recheck-20261110 --guest-kernel references/hakios-scion-full/prebuilt/hakios-kernel`, run from the primary checkout at `78bec9b`:
- exit 0, `outcome: pass`, 39/39 checks, about 14 s;
- report `artifacts/krn-041/main-recheck-20261110/report.json`, SHA-256 `468e8e47…9d01`.

Comparison with the accepted run `artifacts/krn-041/run-003`:

| Output | Same bytes? | Explanation |
|---|---|---|
| `exports/profile/Private.arm64.exports` | yes | — |
| `kpi/profile-all-kpi.exp` | yes | — |
| `compile/patched/pmap.o` | no | Disassembly is identical (22 337 lines). Only `__cstring` (+14 B), `__debug_str` (+28 B) and `__debug_line` (+14 B) differ. The object embeds its absolute source path, which contains the run directory name: `run-003` has 7 characters and `main-recheck-20261110` has 21 (+14). |
| `relink/kernel.unstripped` | no | 21 540 112 → 21 540 144 bytes (+32, from the longer embedded path and alignment). Same cause. |
| `release-style-profile/kernel.unstripped` | no | Same cause. |

So the fixes reproduce from main with identical machine code. The images are not byte-reproducible across run directories because the compile does not map the source prefix. Adding `-ffile-prefix-map=<run>/compile/patched=.` to the stub compile would remove this difference; KRN-041's tool was not changed here.

## Integration status in main

- `0001-arm-pmap-unsupported-queries.patch` and `0002-no-apple-soc-library-exports.patch` are in main only under `docs/procedures/krn-041/`. `git grep` for both file names and for `no-apple-soc`, outside `worktrees/`, finds them only in KRN-041's own dossier, evidence, tool and note.
- No source-preparation or build tool in main (`tools/build/`, `patches/`) applies them.
- The STR-041 image remains the one without the stub object. The relinked image with 0001 and the 0002 profile exists only as KRN-041 artifacts: run-003 and this rerun.
- Making 0001/0002 part of the native E1S source preparation, and regenerating `all-kpi.exp`/`symbolsets.plist` from the profile, is still open. The KRN-041 note lists the same steps.

Nothing here shows that any of these kernels boots.
