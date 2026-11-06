# STR-029 native support source slice

Original owner: `codex-e1s-native-objects-20261106-sr29`.
Atomic MAIN claim returned STR-029 with CLI exit 0. The separate worktree is
`worktrees/str-029-e1s-native-support-20261106`, branch
`team/str-029-e1s-native-support-20261106`, based on exact MAIN
`415c9a1fcad73cb47affcedbb037520ce973f888`. The context update also exited 0.

This phase freezes only the accepted source selection and provenance. The
manifest is `fixtures/public/e1s-native-objects/support/source-slice.json`, SHA256
`f32644f256710fb77d3874375d9b8d217531e5a67463f1469b4e25b651a5ed7d`.
It retains separate original component CWD/Makefile references and ordered rows:

| Component | Objects | Ordered position in support slice |
| --- | ---: | --- |
| pexpert | 11 | 0 through 10 |
| libsa | 1 | 11; original target `bootstrap.cpo` |
| security | 23 | 12 through 34 |
| san | 1 | 35; `ubsan_minimal.o` |

Every graph row and recipe descriptor retains the original native target,
selection index, source expression, source bytes and language. Exact original
selected compiler vectors remain in the hash-pinned STR016 recipes; the slice
also records their canonical JSON hashes without rewriting or executing them.
Original recipe lines and post-compile steps are retained. The selected language
counts are 35 C and one C++. This scheduling slice does not redefine link order.

The source-only extraction command ran once with exit 0:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s artifacts/e1s-native-objects/support/source-slice-001/prepare_slice.py
```

Its CWD was this worktree. The retained script is an ignored local artifact,
not an executor or shared helper. It verified 36 source hashes, 36 recipe hashes,
four original component Makefiles, exact component/selection order and the
accepted graph/context/profile/feature provenance. The evidence capsule is
`source-slice-evidence.json`, SHA256
`907ab76d3df69e4ed6c1b043abfdd4f7d5145d7da0023bc6265233fd55db7fab`.
Actual source extraction took 0.069 seconds and observed current-image VmHWM was
23,796 KiB. This verifies the source slice only; it does not establish compiler
input closure, actual MD closure or any Mach-O product.

Frozen upstream inputs are:

- MAIN qualified graph `c866f73c539870f87edbbb503de8c6418c0334541801ceb4d5cd56bac6f9a579`.
- Body graph `2fa82dd9fa160a1f6311ae60ce9a1fa2dec43fdc79a157f416b49d788aff853c`.
- Partitions `2519966081d650108e62e10734f8b23ac4bda51008930e7ec7dec8e53a98e31a`.
- Shared context descriptor `00a9d47cb973d0a3bb32426d8218f01bfe1b51038bcef39829e6a65c3780f638`.
- Portable profile `a65f70a1daf01c26399ca1034ff41dafbf790ef86bccc3caa8f84acd0df27581`.
- Accepted STR014 source manifest `f85b699020a36635a65f1e4304c218c2d216526835168ec02e397973a97101ac`.
- Actual shared BOUND_CHECKS0 receipt `01d70064392c72114d1ee10a9a5c55ceaa2b7bd3ce1a735a9b4fc06fe47f8332`.

Root reported the single minimal STR030 native caller correction `9c14780` as
source-reviewed PASS `92f0038e`, with its final capsule still pending. Wait for
the reviewed caller and explicit root budget before caller actual planning,
private CWD projection or target tools. Do not duplicate the caller/executor,
probe the compiler again, copy generated inputs yet or change native flags.
Later admitted compilation remains one job/512 MiB within the root global
six-job/6 GiB wave, using unchanged accepted generic helpers.

There are no new object files, actual compiler commands or experiment claims in
this phase. Historical RELEASE/BCM/guest objects and failures remain untouched.
Actual compilation, MD/Mach-O qualification, independent review and root common
acceptance remain outstanding. No archive, link, kernel image, QEMU, private ABI,
native runtime or phone result is established. Keep STR-029 in progress.
