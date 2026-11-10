# Integration of 2026-11-10 (INT-004)

Owner `claude-integration-20261110-i1`, task INT-004, branch `integration/2026-11-10`,
worktree `worktrees/integration-20261110`. Authority: owner decision
[0002](../../decisions/0002-owner-autonomy-grant-2026-11-10.md), item 1 ("merging verified
branches into `main`"). Host-only work: no ADB, phone, package installation or registry edit of
another owner's task.

- `main` before: `e34c6668af58874f6f98a2e96c142f27fcd261fb` (registry snapshot on top of decision 0002).
- `main` after the merges: `1e36ed7ad864ca3b75ba84a11a70f4c2336dcfc5`, a fast-forward of
  `integration/2026-11-10` under `state/.integration.lock`. This README and `evidence.json` were
  added later in a docs-only commit.
- Result: 19 `--no-ff` merges, 111 files added, no existing file modified or deleted, and no
  registry or generated view (`state/`, `BOARD.md`, `STATUS.md`, `planning/tasks/`) touched.

## Method

1. Every local branch (296 at the final count) was classified against `main` with
   `git merge-base --is-ancestor`, `git cherry` (patch equivalence) and `git merge-tree --write-tree`
   (simulated merge; registry/generated paths ignored). The full table is in
   [branches.json](branches.json), with a reason for every unmerged branch.
2. A branch was a candidate only if its registry task was `done`, its evidence had
   `outcome: pass`, and the SHA256 recorded in the registry matched the evidence file *as committed*
   at the merged commit. The commit merged is the one that holds that evidence.
3. Each candidate diff was scanned for 15-digit IMEI-like numbers, MAC addresses, the device serial
   pattern `R[A-Z0-9]{10}`, `serialno`/`android_id`-style keys, binary files and files over 500 kB.
4. Merges ran in dependency order on `integration/2026-11-10`, with rechecks after each batch. The
   branch was fast-forwarded into `main` only after it was green, and `make check` and `make status`
   were then run in the primary checkout.

## Merged

| Merge | Branch tip merged | Task (owner) | Kind | Recheck after merge |
|---|---|---|---|---|
| 2a5e6e4 | b6a2654 `team/str-039-e1s-native-resource-20261110` | STR-039 (claude-e1s-native-resource-20261110-sr39) | source-review | `check_source_only.py` on the STR-039 plan: 50/50 checks pass; identical to the committed output except a random temp-directory name |
| 0b6722d | dee09f9 `team/str-040-e1s-native-bsd-a-tail-20261110` | STR-040 (claude-e1s-native-objects-20261110-sr40) | host-test | covered by the STR-041 image check |
| 85618b3 | dbd5d45 `team/str-041-e1s-native-link-image-20261110` | STR-041 (claude-e1s-native-link-20261110-sr41) | host-test | `verify_image.py`: pass, image SHA256 4c9536d8… equals the evidence, 0 undefined symbols, 69160 symbols |
| fad0dda | acf0acb `team/krn-040-export-coverage-20261110` | KRN-040 (claude-export-coverage-20261110-k40) | host-test | `export_coverage.py --run int004-recheck-001`: 22749 imports, 37 missing, overlap with KRN-026 37, the same as the evidence |
| dce5b1a | c071573 `team/drv-005-ufs-gpt-20261110` | DRV-005 (claude-ufs-gpt-20261110-d5) | host-test | covered by the DRV-006 check (same files, later revision) |
| 53eaaa3 | aef3677 `team/drv-006-ufs-gpt-hardening-20261110` | DRV-006 (claude-ufs-gpt-hardening-20261110-d6) | host-test | `gpt_check.py --run int004-001`: 14 tests pass, 72 mutants, 0 survivors (equal to the evidence) |
| 1a40ce1 | b56d472 `team/gpu-013-backend-core-20261110` | GPU-013 (claude-gpu-backend-20261110-g13) | host-test | `check.py --run int004-001`: 37 ASan/UBSan + 37 TSan tests pass, 138/138 mutants killed. `compile_arm64.py --run int004-arm64-001`: pass, same undefined-symbol sets |
| 9b211b3 | 32835b9 `team/gpu-015-timeline-20261110` | GPU-015 (claude-gpu-timeline-20261110-g15) | host-test | `check.py --run int004-001`: 46 + 46 tests pass, 130/130 mutants killed, 0 ARM64 undefined symbols |
| f2ac191 | 6dbfc60 `team/vm-001-interfaces-20261110` | VM-001 (claude-vm-interfaces-20261110-v1) | android-userland | static only (Python parses); device runs not repeated |
| 4f5bd54 | b813660 `team/vm-049-root-kvm-20261110` | VM-049 (claude-root-kvm-20261110-k49) | android-userland | static only; `kvm_caps.c` passes `cc -Wall -Wextra -fsyntax-only` |
| b7d36e2 | 283b1a0 `team/vm-050-root-kvm-api-20261110` | VM-050 (claude-root-kvm-api-20261110-k50) | android-userland | static only; `kvm_api.c` passes `cc -Wall -Wextra -fsyntax-only` |
| 7376f87 | ae59b43 `team/gpu-014-vulkan-inventory-20261110` | GPU-014 (claude-vulkan-inventory-20261110-g14) | android-userland | static only |
| 02934de | 93e32e4 `team/dev-003-boot-copies-20261110` | DEV-003 (claude-boot-copies-20261110-b3) | android-userland | static only. Partition images stay in local `artifacts/device-backup`; only hashes are in Git |
| 7a40521 | a96a743 `team/vm-051-minimal-guest-20261110` | VM-051 (claude-kvm-guest-20261110-k51) | android-userland | NDK `-fsyntax-only` on `kvm_guest.c` and assembly of `guest.S`: exit 0 |
| 040ff30 | bde2010 `team/vm-052-s24vmm-20261110` | VM-052 (claude-s24vmm-20261110-v52) | android-userland | `src/vmm/check.py --run int004-check-001`: 191 checks, 0 failures (equal to the evidence) |
| 9371a90 | f6ceb25 on `team/str-001-scion-20261106` | STR-001 (codex-strategy-scion-20261106-sr1) | source-review | docs only |
| 9790c93 | c1e3c4e `team/str-006-e1s-ramroot-20261106` | STR-006 (codex-e1s-ramroot-20261106-sr6) | source-review | adds the one missing file, `closure-evidence.json` |
| e14ba7f | 3affdff `team/str-034-e1s-kernel-log-20261106` | STR-034 (codex-e1s-kernel-log-20261106-sr34) | source-review | docs only |
| 1e36ed7 | 44cb657 `team/vm-022-pmap-diagnostic-20261106` | VM-022 (codex-guest-exec-20261106-cu) | host-test | docs/fixture records only; the related patches were already on main |

"Static only" means the device scripts were parsed and the C probes compiled for syntax. The
measurements themselves are android-userland evidence from their owners and were not repeated:
this task does not touch the phone.

The four Codex merges close gaps between `main` and the registry. Each task was done with pass
evidence, but the file holding that evidence, or content a done task cites, never reached `main`:

- `docs/strategy/2026-11-06/decision.md` cites the Scion audit commits `e06432f` + `f6ceb25`, but
  `docs/strategy/2026-11-06/scion/` was absent. The merge stops at `f6ceb25`, the last commit inside
  the STR-001 task window (finished 2026-11-06T08:25Z).
- The STR-035 (done) acceptance reads "future proposal3aff", i.e. STR-034 commit `3affdff`. That
  commit lies inside the STR-034 window on its recorded branch but was missing from `main`.
- The STR-006 and VM-022 closure evidence files were absent from `main`. Every other commit on those
  branches was already on `main` by patch equivalence.

### Conflict resolutions

None were needed. All 19 merges were clean. No merged diff contained a registry or generated
file, so there was no stale registry copy to discard.

## Not merged

39 branches with commits not on `main`; reasons per branch are in [branches.json](branches.json).

- **Task in progress (19).** Codex sessions, all stopped (last heartbeats 2026-11-05/06): INT-002
  `team/int-e1s-profile-20261106`; INT-003 `team/int-platform-20261106`; REV-047
  `team/rev-vm047-fd-20261106`; STR-024; VM-014 (2 branches); VM-019 (3); VM-042 (2); VM-043 (2);
  VM-047 (2). Codex integration branches that have no task of their own but carry in-progress work:
  `team/int-resource-profile-20261106` (INT-002 reviews) and `team/int-wave31-context-runtime-20261106`
  (VM-042/043/047, REV-047, INT-002/003). Claude sessions that are live: VM-002
  `team/vm-002-guest-20261110` and KRN-041 `team/krn-041-missing-exports-20261110`. These need their
  owner, or a recorded `task transfer` under decision 0002, before their work can be verified.
- **Superseded attempts of done tasks (19).** The recorded branch of each task, which holds the pass
  evidence, is already on `main`; these other branches are not bound to that evidence.
  - Preparation or failed wave20 runs: `team/vm-010-20261106`, `team/vm-010-profile-v1-20261106`,
    `team/vm-011-*`, `team/vm-012-*`, `team/vm-016-*`, `team/vm-017-*` (two each) and
    `team/vm-041-profile-v1-20261106`.
  - Intermediate VM-022 lines: `team/vm-022-{console-result,console-run,consolepack,diagnostic,final-wiring,image-result,stage2-products,stage2-target}-20261106`.
    They conflict with `main` in `tools/build/avf_guest_link_inputs.py`, where `main` holds the later
    version.

  These records of failed and intermediate work (for example, the first XNU panic console) are kept
  on their branches. If the owner wants them on `main`, they need a separate docs-only archival
  task; merging the VM-022 lines would also mean resolving code conflicts against newer code.
- **Commits after closure (1).** `team/str-001-scion-20261106` beyond `f6ceb25`: `9b8fc1c`, `4d02f4b`
  and `3770e0a` (Stage2 guard diagnosis, the two-TU packet review and the early IO PTE donor audit).
  No registry task or evidence covers them.

Another 257 branches are already on `main`: 60 are ancestors, and 197 are fully patch-equivalent or
change nothing on merge.

## Sensitive-data scan

The whole `e34c666..1e36ed7` diff contains 0 IMEI-like numbers, 0 MAC addresses, 0 serial-pattern
matches and 0 binary files. The only `imei`/`serial` hits are the redaction regexes in the VM-001 and
GPU-014 probes. The two largest files are text JSON plans, at 3.6 MB
(`docs/procedures/e1s-native-objects/bsd-a-tail/plan-001/plan.json`) and 1.8 MB
(`docs/procedures/e1s-native-link-image/plan-001/plan.json`); `main` already holds 19 MB plans of the
same kind. `src/vmm/avfboot/identity.h` holds only placeholder properties and no Apple device-tree data.

## Checks

- Integration worktree, after every batch: `python3 -m unittest discover -s tests`, 169 tests OK
  with 3 skipped. The skips need the gitignored `references/` checkouts, which a worktree lacks.
- `lab.py validate`, `board --check` and `capabilities.py --check` read the private
  `devices/local-*.json` inventory, which exists only in the primary checkout, so in the worktree
  they exit 2. They were run with `--root` against the primary and passed; none of the merges touch
  those tools or the registry.
- Primary checkout after the fast-forward: `make check` exit 0. validate reports 277 tasks and 666
  experiments, board and capabilities checks are OK, and 173 tests pass with 0 skipped. `make status`
  exit 0.
- Two runs failed because of mistakes in the rechecks, not in the merged code, and are kept in the log:
  - `compile_arm64.py --run int004-001` exited 1 because `check.py` had already created that run
    directory. It passed when rerun as `int004-arm64-001`.
  - `cc -std=c11 -fsyntax-only` failed on `kvm_api.c` (`O_CLOEXEC` is hidden by strict C11 on
    glibc). It passed in the default GNU dialect.
- The GPU-013 ARM64 object hashes differ from the recorded ones. The only argv difference is the
  absolute worktree/run directory, which `-g` embeds. Input source hashes, the compiler and the
  undefined-symbol sets are identical.

## Registry and project-state findings

1. **Evidence lives in worktrees.** 139 of 208 done tasks record their evidence path inside
   `worktrees/` (gitignored); 9 of the paths are absolute.
   - 86 of those files are now also committed on `main` with the same SHA256.
   - 50 are under a worktree's `artifacts/`, which never enters Git.
   - 3 are elsewhere: KRN-023 and KRN-028 under `tools/research/*/local/`, and VM-036 in the
     unmerged INT-003 worktree.

   `lab.py validate` therefore depends on those worktrees existing. Do not remove `worktrees/` until
   the paths are re-pointed. Re-pointing is the owners' change, and `lab.py` has no command for it.
2. **Committed tools hard-code other worktrees.** For example, `export_coverage.py` (KRN-040) reads
   the kernel image from `worktrees/str-041-…/artifacts` and inputs from `worktrees/krn-026-…`;
   `check_source_only.py` (STR-039) reads from the STR-030, STR-024 and STR-016 worktrees. These
   rechecks are reproducible only while those worktrees exist.
3. **Stale claims.** 16 tasks are `in_progress` under stopped Codex owners and still reserve their
   paths, with heartbeats from 2026-11-05/06: KRN-004, KRN-008, INT-002, INT-003, VM-014, VM-019,
   VM-023, VM-031, VM-032, VM-033, GPU-012, VM-042, VM-043, VM-047, REV-047 and STR-024. 8 tasks are
   blocked under Codex owners. Decision 0002 allows a recorded `task transfer`; this task did not
   change them.
4. The four missing files described under Merged are fixed by this integration. Validate, board and
   capability checks pass.

## Limits

This integration establishes that the merged trees are the content the done tasks' evidence was
recorded against, and that the host checks reproduce. It re-measures nothing on the phone. It does
not make the acceptance judgment for those tasks, which stays with their owners and reviewers, and
it adds no claim about native XNU, GPU under XNU or Exynos hardware.
