# DRV-002 acceptance map (prepared by DRV-007, 2026-11-10)

Evidence category: **host-test** only. No phone, MMIO or storage access, and no hardware claim.

DRV-002 ("Validate the read-only UFS/MCQ contract on the host") is not marked done by this work:
- its reserved paths (`src/xnu/`, `patches/e1s/`, `tests/`, `fixtures/public/`) overlap the active NAT-006 reservation `tests/test_e1s_recovery.py`, so it cannot be claimed while NAT-006 is held;
- an owner of DRV-002 must still assess these criteria.

This map lists the existing checks for each criterion. They now run in `make check` through `tests/test_ufs_contract.py`.

| DRV-002 criterion | Where it is checked |
|---|---|
| **DMA boundaries** | `host.c` `policy_valid`: 128-byte UCD and 4-byte data alignment, minimum sizes, 64-bit wrap, disjoint UCD/data regions. Exact statuses are pinned in `tests/test_ufs_contract.py` (`test_exact_boundary_statuses_under_sanitizers`), including adjacent-but-disjoint → OK and a 4-byte overlap → `UFS_DMA_RANGE`. Further coverage: `fixture.c:75-85` and the source-qualified run of `check.py` (guard lengths, 100 000 random completions). |
| **GPT boundaries** | `gpt.c`. The 14 `gpt_test.c` tests (header/CRC/LBA/entry-array/last-slot/64-bit/partition/name rules, extent → READ(10) admission) run under ASan/UBSan in `test_gpt_admission_suite_under_sanitizers`. The 72-mutant run is `python3 src/platform/storage/ufs/gpt_check.py --run NAME` (2026-11-10 run `drv007-baseline-20261110`: pass, no survivors). |
| **LUN and extent boundaries** | LUN ≤ 127, SQID ≤ 31, epoch ≠ 0, 512/4096-byte blocks, extent ending on the last LUN block → OK and one block past it → `UFS_ARGUMENT`. READ(10) before, after, across the extent end and with a wrong byte count → `UFS_EXTENT`; the last extent block → OK. Exact statuses are in `tests/test_ufs_contract.py`. A response LUN mismatch → `UFS_STALE` is covered at `fixture.c:119`. |
| **Timeouts** | `ufs_host_reserve_device` refuses a zero timeout, a timeout above 5 s and a zero clock (`UFS_CLOCK`). `ufs_host_poll_timeout` gives `UFS_OK` at deadline − 1 and `UFS_TIMEOUT` at the deadline. A timed-out request is quarantined: it is never reclaimed (`UFS_OWNERSHIP`) and later requests are refused (`UFS_BUSY`). Exact statuses are in `tests/test_ufs_contract.py`; also `fixture.c:131-142`. |
| **Write rejection** | Any direction other than `UFS_FROM_DEVICE` → `UFS_WRITE_REJECTED` before the CDB is parsed. WRITE(10) and every opcode other than READ(10) are refused (`fixture.c:87-94`, `gpt_test.c` `test_extent_drives_read_admission`, `tests/test_ufs_contract.py`). |
| **Encrypted userdata not assumed readable** | `gpt.c` refuses to select `userdata` (`gpt_test.c` `test_userdata_refused`; DRV-005/DRV-006). `check.py` evidence records `userdata_decryption_qualified: false`. |
| **No PHY/IOMMU/MCQ hardware claim** | `check.py` evidence records `device_executed`, `native_qualified`, `BYH3_qualified` and `DMA_coherency_qualified` as false; `tests/test_ufs_contract.py` asserts the first three of these plus `userdata_decryption_qualified`. The MCQ tag oracle is a source differential, not a hardware result. |

## DRV-007 changes

- **`src/platform/storage/ufs/check.py`.** On main it failed (`exact-source-available-0`): its session caches existed only in the DRV-004 worktree, and the sparse `references/s24-linux` checkout has no working-tree copy of `include/ufs/*`.
  - It now also reads each pinned blob from the local object store with `GIT_NO_LAZY_FETCH=1`.
  - The existing sha256 and git blob-id checks still verify the exact bytes.
  - Run `drv007-objstore-20261110` passes 22/22 checks, with the same check names, fixture counts and input hashes as the accepted DRV-004 run `coordinator-integration-session1`.
- **`tests/test_ufs_contract.py`.** New. Wires the checks into `make check` (about 2.5 s) and adds the exact-status program. Six single-point mutations of `host.c` were each detected: UCD alignment, inclusive overlap, LUN 128, deadline off-by-one, timeout maximum, extent end.

## Not established

UFS PHY, UniPro link, SysMMU/IOMMU, MCQ queue behaviour and DMA coherency on Exynos 2400. The real GPT of this phone has not been examined against the strict rules. Reading Android userdata, which is encrypted, is not expected to work.
