# STR022BUILD-001 native osfmk-a procedure

Original STR-022 owner `codex-e1s-native-objects-20261106-sr22` uses the
unchanged physical STR030 caller:
`/home/egor/dev/pet/s24-ios-exynos/worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py`,
SHA256 `2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f`.
Root explicitly authorized one source-only export after CM final functional
review, while publication/common84 was still pending. No executor is copied.

The strict eight-field manifest is
`fixtures/public/e1s-native-objects/osfmk-a/native-slice-v1.json`, SHA256
`1cce7c75216417d6dde3811cdcd07c501ab3198537af7df612d8bddd92144d43`.
It selects all 160 accepted osfmk-a IDs, owner/task/experiment STR022BUILD-001,
a 1,800-second whole bound and the fresh MAIN-relative output
`worktrees/str-022-e1s-native-osfmk-a-20261106/artifacts/e1s-native-compile/osfmk-a/build-001`.
The earlier source-only slice and its evidence remain unchanged.

One invocation ran from the original worker worktree with environment
`LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1`:

```sh
python3.12 -s /home/egor/dev/pet/s24-ios-exynos/worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py plan \
  --manifest /home/egor/dev/pet/s24-ios-exynos/worktrees/str-022-e1s-native-osfmk-a-20261106/fixtures/public/e1s-native-objects/osfmk-a/native-slice-v1.json \
  --manifest-sha256 1cce7c75216417d6dde3811cdcd07c501ab3198537af7df612d8bddd92144d43
```

Stdout, stderr and raw exit code are preserved outside the prospective output
in `artifacts/e1s-native-compile/osfmk-a/plan-001/`. The plan SHA256 is
`ad5e964ed3fb7ab347f5b50dc35f8fff4393ad5d09b6565bbe7a8e92221be287`.
Exit was zero, stderr empty. The plan binds 160 commands, 6,649 inputs and 139
future CWD projection files. The prospective output remains absent. Planning
RSS was not measured and is unqualified; plan profile and future limits are
not measurements or an execution allocation.

Future execution must use this same physical caller with mode `execute`, the
same manifest path/hash, `--source-plan` equal to the absolute preserved plan
path above and `--source-plan-sha256` equal to its exact SHA256. Add only root's
exact `--approval` path and `--approval-sha256`, using root's required outer
watchdog and exact grant. Wait for publication/common84 PASS and separate
native allocation first. One serial compiler / 512 MiB combined owned RSS
within the exact root six-job/six-GiB project allocation remains mandatory.
No loader, Make, compiler or private projection ran during planning.

The unchanged caller preserves original source/recipe flags, native
DEVELOPMENT / ARM64 / E1S, BOUND_CHECKS=0 and the explicit portable
`-DXNU_NO_TYPE_BUILTINS=0` input. Only reviewed context/output projection is
declared. No source/provider/flag edits, old objects, resume or automatic retry
are authorized. Preserve actual failures and MD/resource/cleanup evidence;
independent review and root acceptance precede owner closure. No link, QEMU,
hardware operation or native runtime/ABI claim follows.
