# Decision 0038: Authorize Single Native Recovery Run for NAT-102 (`loader-diag-xnu-hb-md1`)

- Date: 2026-11-12 (prepared 2026-11-13 local +05:00)
- Status: Approved under standing full-automatic recovery experiment authority
- Authority basis: `docs/decisions/0002-owner-autonomy-grant-2026-11-10.md` and `decision 0019` (`docs/decisions/0019-owner-full-automatic-mode-2026-11-11.md`)

## Decision

Authorize one bounded, single-run native recovery experiment on Samsung Galaxy S24 (`SM-S921B` / `e1s`, serial `RFCY10Z45KH`) using the `NAT-102` diagnostic image `loader-diag-xnu-hb-md1`, strictly confined to `/dev/block/sda18` (`RECOVERY`) with mandatory stock `RECOVERY` restoration and Android verification immediately after completion.

## Pinned Artifacts and Hashes

All hashes verified locally before execution:

- Recovery image: `artifacts/nat-102/package-001/loader-diag-xnu-hb-md1/recovery.img`
  - Size: `100,663,296` bytes (`96 MiB`)
  - SHA-256: `e938cb4a5578b404685feeb21c0a480285b57157f10f4573fba07f28f5afba94`
- Embedded payload (`recovery.img` slice `[2048 : 2048 + 26134288]`): `artifacts/nat-102/build-001/loader-diag-xnu-hb-md1/Image.payload`
  - Size: `26,134,288` bytes
  - SHA-256: `88d6217681784ab638025ad42cb0992672d84bd2b6d21af92c09d85e54e0cd1f`
- Unpacked kernel image: `artifacts/nat-102/build-001/loader-diag-xnu-hb-md1/Image`
  - SHA-256: `6f70f14eb266fbede5c34bdf44eee3195a04bebdab379816c38cbadb98ef7864`
- Embedded heartbeat initrd (`NAT-101`): `artifacts/nat-101/pid1-hb/root.apfs`
  - Size: `4,194,304` bytes
  - SHA-256: `97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c`
  - Contains `hb` (`16,635` bytes, SHA-256 `1819a4a89ec06403fa21df2facd73ff9723c2debd03c2ec6df9d7f6717103163`) and `etc/rc` (`1,152` bytes, SHA-256 `e1f7866c666d90f919dd1cd8aa468b557955a6137289a6ccd84b3e9860243e4c`)
- USB bulk-OUT target rootfs (`md1` / `xrd=md0`): `artifacts/nat-083/system-padded.apfs`
  - Size: `2,475,720,704` bytes
  - SHA-256: `4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6`
- Stock `RECOVERY` restore target: `devices/recovery/backups/2026-11-10/recovery.img`
  - SHA-256: `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`
- Session and tooling scripts:
  - `docs/procedures/nat-102/session_nat102.py` (`698bdf559a23c42ec7e0b7bf2eaea3961ac95408f6fff4de30bd58cb00f6ead4`)
  - `tools/ios/root_send.py` (`a07b9ba94a2b5c37723cac76439a305669d4825042d2e2c520e76a66b83e69ef`)
  - `docs/procedures/nat-080/deliver_nat080.py` (`dfa65d66378e5bc2701b92e268c4ccb46b753b3074e120bc98df540d6c79fbf6`)
- Pre-registered analysers:
  - `docs/procedures/nat-087/analyze_nat087.py` (`b3fa68b39fafe0309f225ca5e07fd1a95ec90c0154de724543ca9f59a0a907d7`)
  - `docs/procedures/nat-097/analyze_nat097.py` (`ac208e0b1bde2a59f6186c02b3f591311ee2d9c7ab85a35aca0096129793894d`)
  - `docs/procedures/nat-102/analyze_nat102.py` (`e96e22a06f19d01fb2acca00255477893da4d50c6a55597fc94a9f05f1312854`)

## Kernel Command Line (`236` bytes)

```text
rd=md1 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT102-hb1 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=60 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 xrd=md0
```

## Scope, Guardrails, and Mandatory Protocol

1. **Preconditions**:
   - `NAT-101` and `NAT-102` must be `done` in `state/lab.json`.
   - All host build, unit test, and mutation processes must have exited (`ps`) and host 1-minute load average must be `< 6.0` (`uptime`).
   - `adb devices` must report `RFCY10Z45KH` online in Android `device` mode.
   - Run read-only preflight `session_nat102.py --image loader-diag-xnu-hb-md1 --out artifacts/nat-103/preflight-001` before opening the `native` permit.
2. **Execution**:
   - Open `project.permissions.native = true` in `state/lab.json` citing this decision file.
   - Execute a single run via `docs/procedures/nat-102/session_nat102.py --image loader-diag-xnu-hb-md1 --out artifacts/nat-103/run-001 --execute`, which writes `RECOVERY` (`/dev/block/sda18`), performs full readback verification against `e938cb4a5578b404685feeb21c0a480285b57157f10f4573fba07f28f5afba94`, records the one-shot marker, launches the detached watcher/collector/delivery pipeline, and issues one `adb reboot recovery`.
   - Bounded kernel timeout `loader_return_after=60` governs automatic return to Android.
3. **Mandatory Restoration & Closure**:
   - Do not run post-analysis (`analyze_nat087.py`, `analyze_nat097.py`, `analyze_nat102.py`) until both watcher and collector processes have exited.
   - Immediately restore stock `RECOVERY` via `docs/procedures/nat-013/restore_stock.py restore` and verify full SHA-256 readback (`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) plus Android integrity via `docs/procedures/nat-012/check_android.py` and `restore_stock.py assess`.
   - Close `project.permissions.native = false` in `state/lab.json` immediately after restoration.
4. **Boundaries & Known Limits**:
   - No other partitions (`BOOT`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `USERDATA`, `super`, `EFS`, etc.), GPT, keys, or encryption may be modified.
   - This decision authorizes one run only; any follow-up run requires its own decision and `RECOVERY` image verification.
   - Pre-run `HOST_TEST` and Unicorn VM checks (`test_nat101.py`, `test_nat102.py`, `test_hb_vm.py`) do not prove Darwin/XNU syscall or APFS behavior on S24 hardware; only the hardware-observed `H0`–`H5` heartbeat rows and `kl_reader2` output establish hardware execution.
