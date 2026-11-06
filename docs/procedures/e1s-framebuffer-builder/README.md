# E1S framebuffer builder integration

STR008 owner codex-e1s-framebuffer-builder-20261106-sr8. Separate worktree from
accepted MAIN e4d1cf6030854dfc710ec32ba511ac04ce1a2460; original STR005 source,
controls and failed/passing physical witnesses remain unchanged.

The ordinary builder previously applied only RAM validation. Its existing loader
now also consumes the accepted CPU framebuffer contract: immutable RAM23b31 is
checked/applied first, then display0689 is read once, hashed against its exact
accepted identity, snapshotted in the fresh run directory, checked and applied
before the existing target loop. The report retains source_patch and adds
separate display_source_patch provenance and applied status. Missing/changed
bytes or unsuccessful check/apply produce the existing failed build report
before any target compile. No generic patch override exists.

Code freeze1f3e39d78c1dfdfcf67b8f5b422ceba8224555ca is exactly14 added lines.
Source readback/AST normalization confirms all accepted parent module behavior
is identical after removing only that display report entry and hook, including
RAM provenance/check/apply, source verification, Zig version/flags,120-second
child timeout, packaging and fresh-output semantics. Existing sources.verify
passed read-only on the unchanged pinned donor; preparation.json records this.
Missing/changed/nonapplicable refusal is source-reviewed, not separately executed.
No compiler or builder invocation occurred during preparation.

Prospective STR008BUILD-001 uses one command in build-plan-001.json, SHA
91fc80b86b56187684b36b4f5c167946be49c1fdfc14a18713a3500861d6a5fb:

```
/usr/bin/python3 /home/egor/dev/pet/s24-ios-exynos/worktrees/str-008-e1s-framebuffer-builder-20261106/tools/build/e1s.py --root /home/egor/dev/pet/s24-ios-exynos --run str008-framebuffer-20261106-001
```

The plan pins actual Python/Zig/Git, candidate builder, both source verifiers,
source registry, RAM23b31 and display0689 hashes. It requests one serial builder,
2GiB aggregate RSS and600seconds whole, with the existing120seconds per child.
Root must grant admission before execution. Use the existing root runner and
supervision; no new helper or matrix is added. Actual acceptance must verify both
patch snapshots/check/apply order before all8 target compiles and the existing8
products, record cleanup and preserve any failed run without automatic retry.

This builds freestanding probe and handoff-loader products only. It does not
build XNU or establish a native boot, safe physical framebuffer ownership,
scanout, MMIO, Android recovery or phone behavior. Earlier fixed log/boot-mark
writes and all physical preconditions documented by STR005 remain unchanged.
Independent review, publication/common and root acceptance precede SR8 closure.

Root60 executed STR008BUILD-001 once: all21 ordinary builder commands exited0.
RAM check/apply at indices1/2 precede display check/apply3/4 and all8 target
compiles5/6/11..16. Exact23b31/0689 snapshots report applied=true; all8 products,
post-overlay source bodies, tool and input hashes were read back exact. Raw
882ffb73 and actual report4419e266 are bound in evidence.json. Elapsed4.364s,
peak sampled owned-tree RSS137,654,272 bytes, root controller HWM30,789,632 bytes,
zero survivors. No author rerun or additional compiler control occurred.

Ready for independent review and minimal publication/common; originalSR8 claim
remains open until explicit root acceptance. Earlier STR003/STR005 physical
witnesses and all failed results remain unchanged.
