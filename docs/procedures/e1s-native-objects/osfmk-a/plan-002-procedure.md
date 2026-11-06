# STR022BUILD-002: remaining native osfmk-a155

STR022BUILD-001 remains FAIL with immutable raw SHA256
`74ac81f1fdcbfb22b42bd0c32687f8af767a7ba255887229475ec1e9b116dfa1`.
It produced five qualified objects, then deferred `osfmk/kdp_common.o` before
compiler because project admission reported a stale executor reservation.
The worker performed no repair or retry and did not release the global queue.
The [physical audit](build-001-physical-audit.json) independently checked those
five objects, exact argv, 412 unique actual dependency files and current zero
owned survivors. Original experiment FAIL was recorded through MAIN lab.py,
CLI exit 0, before any new manifest or plan.

Root separately authorized a new source-only suffix manifest and exactly one
plan with the same physical STR030 caller, SHA256
`2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f`.
No helper, source, generated provider, configuration or recipe flag changed.
The new eight-field `native-slice-002.json` manifest SHA256 is
`c7e10be7c2b480a2637729785a6763a73788d8edb87f552627007c0398c08a4f`.
Its ordered IDs are exactly original osfmk-a `[5:160]`, from
`osfmk/kdp_common.o` through `osfmk/atm.o`, excluding the five actual qualified
prefix IDs without relabeling their original failed parent experiment.

One source-only command ran with the same constrained Python environment and
physical caller as plan-001:

```sh
python3.12 -s /home/egor/dev/pet/s24-ios-exynos/worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py plan \
  --manifest /home/egor/dev/pet/s24-ios-exynos/worktrees/str-022-e1s-native-osfmk-a-20261106/fixtures/public/e1s-native-objects/osfmk-a/native-slice-002.json \
  --manifest-sha256 c7e10be7c2b480a2637729785a6763a73788d8edb87f552627007c0398c08a4f
```

Exit/raw exit was zero, stderr empty. The preserved plan is
`artifacts/e1s-native-compile/osfmk-a/plan-002/source-plan.json`, SHA256
`cb9247af83a76b1055d438f6b454dabb78be221a8b51e37f080885e5ef6d3d61`.
Raw stderr/exit are beside it, outside prospective output. Planning RSS was
not measured and is unqualified. The fresh actual output remains absent:
`worktrees/str-022-e1s-native-osfmk-a-20261106/artifacts/e1s-native-compile/osfmk-a/build-002`.

The new planned actual experiment is STR022BUILD-002 under original owner
`codex-e1s-native-objects-20261106-sr22`, whole bound 1,800 seconds. It includes
only the remaining 155 objects; no prefix reexecution, old-object resume or
automatic composition of the 160-object result is authorized. The unchanged
caller must later execute this exact manifest and source-plan path/hash under
root's exact new approval, outer watchdog and separate allocation. One serial
compiler / 512 MiB owned RSS and the accepted global six-job/six-GiB mechanism
remain mandatory even if root schedules fewer concurrent actual owners.

Wait for root reconciliation of wave85 and a new explicit execute grant.
Preserve build-001 and all source-plan/raw bytes. No new compilation, loader,
private projection, Make, global release, task closure, link, QEMU or device
operation ran during this preparation. Future physical object/MD/resource
qualification and independent review remain required.
