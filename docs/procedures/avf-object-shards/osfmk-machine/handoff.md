# VM-015 source preparation handoff

Owner `codex-guest-exec-20261106-cz`; branch `team/vm-015-20261106`;
worktree `worktrees/vm-015-20261106`. Keep this task in progress. This is a
source-only handoff, with zero objects produced and no compiler, preprocessor,
generator, donor Make, guest or physical device operation.

Source implementation commits are `7316c790b2b9797c5579e87a7eab6e3e10448136`
and `fc608ced22c5e312fc4abd4e56b1996e3a031110`. The second commit canonicalizes
the output path before checking worktree ownership. The first successful audit
is retained unchanged; the final run binds the second source commit. Evidence,
selector and procedure updates are delivered separately after the measured run.

The MAIN-registered experiment is `VM015PREP-001`. Final invocation:

```sh
env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/avf-object-shards/osfmk-machine/preflight.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-015-20261106/artifacts/avf-object-shards/osfmk-machine/preparation-2
```

Exit 0, 4,427 assertions, 3.569 seconds, exactly 77 allocated objects: 53 C and
24 assembly sources, no generated source. The full selected rows preserve the
frozen recipes byte for byte as JSON data. Five in-memory tamper controls reject
duplicate/foreign IDs, mismatched source binding, escaped compiler output and
disabled allocator metadata. A sixth actual CLI traversal attempt exits 2 and
creates no escaped destination. Exact commands/exits and retained inspection
diagnostics are in `evidence.json`.

Three stable MemAvailable samples all exceeded 4GiB. Final executable-image
VmHWM was 98,922,496 bytes; VmRSS was 66,895,872 bytes. The separately recorded
inherited ru_maxrss was 1,834,459,136 bytes and is not used as current-image RSS.
All file hashes stream. No child process was launched or terminated.

Final report:
`artifacts/avf-object-shards/osfmk-machine/preparation-2/report.json`, SHA256
`807b5afe0e67c9d16153ef02c462d89669dee37485285de70684c0f8e74e8e01`.
Selected manifest SHA256:
`99bfbb0c965cbaa113e83b65c51c070516b2233a63624bd5b834dde75631ef0a`.
Both artifacts live inside this worktree. `source-preparation.json` binds their
MAIN-relative paths and the declared-input inventory. The original frozen
1,080-row VM-008 graph SHA256 remains
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.

All 77 direct source/configuration inputs match the qualified VM-008 index;
source composition, source tree/configuration, compiler, forced includes and
sanitizer inputs match their pins. The inventory preserves declared include
order. Three actual search roots are absent: `EXPORT_HDRS/libsa`, the public
context `usr/local/include/kernel`, and the public context Kernel.framework
`PrivateHeaders/platform`. No directory was invented and no flag was removed.

Five literal source includes do not resolve in that search order. The one in
`video_console.c` is `pexpert/i386/boot.h`, under the explicit i386/x86_64 guard.
The four `platform_tests.c` includes are `ddb/db_command.h`, `db_output.h`,
`db_sym.h` and `db_print.h`, under `#if MACH_KDB`. These are lexical observations:
conditional expressions and macro includes were not evaluated. The source
audit does not establish the active transitive preprocessor dependency closure.
No success or missing dependency conclusion is inferred from those observations.

Next: independent source/evidence review and integrator acceptance. After the
VM-008 namespace and VM-009 common executor are accepted, obtain an explicit root
heavy lease, register a new compile experiment, and use the accepted common
executor with `--shard osfmk-machine` and the pinned coordinator allocation.
Compile exactly these 77 IDs into new owned output/dependency directories. Keep
actual failures, diagnostics, output hashes and dependency files. No E1S object
reuse, profile weakening or shared-input writes. MAIN publication/common checks
belong to the permanent kernel integrator under `state/.integration.lock`.

No SDK/private ABI, full kernel/link, actual XNU console, boot/stop, native E1S or
phone qualification is established. Original owner completion requires root and
integrator acceptance following independent review and fresh MAIN common checks.
