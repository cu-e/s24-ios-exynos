# NAT-102: `loader-diag-xnu-hb-md1` Build, Analyser, Unicorn ABI Checks, and Decision Draft

Host-side preparation and verification of the heartbeat diagnostic image `loader-diag-xnu-hb-md1` (tag `NAT102-hb1`) for the native run `NAT-103` under [Decision 0038](file:///home/egor/dev/pet/s24-ios-exynos/docs/decisions/0038-nat102-loader-diag-xnu-hb-md1-single-run-2026-11-12.md).

## What changed relative to NAT-096 (`loader-diag-xnu-sq-md1`)

- Small root `md0` replaced with `NAT-101`'s `artifacts/nat-101/pid1-hb/root.apfs` (`4,194,304` bytes, SHA-256 `97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c`), which adds static Mach-O `bin/hb` (`16,635` bytes, SHA-256 `1819a4a89ec06403fa21df2facd73ff9723c2debd03c2ec6df9d7f6717103163`) and 4 lines in `etc/rc` (`e1f7866c666d90f919dd1cd8aa468b557955a6137289a6ccd84b3e9860243e4c`) immediately before `exec /sbin/launchd.darwin`.
- Boot tag changed from `NAT096-sq1` to `NAT102-hb1` in the 236-byte kernel command line ending in `xrd=md0`:
  `rd=md1 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT102-hb1 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=60 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 xrd=md0`

## Pinned Build and Package Outputs

- `artifacts/nat-102/build-001/build.json`: SHA-256 `627465bd51330944c668da1e500a7527381a55f3af80376e8e29ab1d23273a1f`
- `artifacts/nat-102/build-001/loader-diag-xnu-hb-md1/Image`: SHA-256 `6f70f14eb266fbede5c34bdf44eee3195a04bebdab379816c38cbadb98ef7864`
- `artifacts/nat-102/build-001/loader-diag-xnu-hb-md1/Image.payload` (`26,134,288` B): SHA-256 `88d6217681784ab638025ad42cb0992672d84bd2b6d21af92c09d85e54e0cd1f`
- `artifacts/nat-102/package-001/package.json`: SHA-256 `fcff714a01ddb0eebb2690c01abf7ce75467f9870f206d4f8fdf9534636a0bcc`
- `artifacts/nat-102/package-001/loader-diag-xnu-hb-md1/recovery.img` (`100,663,296` B, payload at offset `2048`): SHA-256 `e938cb4a5578b404685feeb21c0a480285b57157f10f4573fba07f28f5afba94`

## Pre-registered Heartbeat Analyser (`analyze_nat102.py`)

Classifies the `why=2` dump from `NAT-097`'s `kl_reader2.py` into rows `H0`–`H5` without modifying `analyze_nat087.py` or `analyze_nat097.py`:
- `H5 hb-ps-lists`: at least one complete `ps` list after an `hb` round marker
- `H3 hb-rounds-no-list`: at least one `SWEET hb:` round marker, no recognisable `ps` list after it
- `H2 hb-start-only`: only the `SWEET hb: start` line
- `H1 no-hb-line`: no `SWEET hb:` line in the returned kernel text
- `H0 no-kernel-text`: no `why=2` kernel-log dump with text in the archive

## Host Verification Summary (`HOST_TEST` + Unicorn VM only; no phone run)

- `derive102.py --check`: exit `0` (`session_nat102.py` matches `session_nat096.py` via 9 counted substitutions).
- `test_nat102.py -v`: `39/39` OK (builder validation, payload/md0/cmdline byte diffs against `NAT-096`, heartbeat root contents, driver derivation and gate checks).
- `test_analyze102.py -v`: `30/30` OK (real `-DHOST_TEST` `hb.c` console output, boundary/cut/status parsing, real `NAT-098` `H1` baseline, synthetic `H0`/conflict/inferred-begin archives, CLI output).
- `test_hb_vm.py -v`: `23/23` OK (Unicorn execution of the real `16,635`-byte static Mach-O `hb` binary under the project XNU Darwin syscall ABI model).
- `artifacts/nat-102/abi-mutants.json`: `22` Darwin ABI mutants tested under the Unicorn model (`21` detected, `1` documented equivalent `fork-child-ignores-carry` citing `arm_prepare_u64_syscall_return()`, `0` undetected).
- `docs/procedures/nat-102/mutation.json`: `488` mutants across `analyze_nat102.py` (`377` total, `345` killed, `9` explained in `equivalent.json`, `23` invalid), `build.py` (`92` total, `88` killed, `3` explained, `1` invalid), `derive102.py` (`19` total, `19` killed, `0` survived, `0` invalid); `0` unexplained survivors, exit `0`.
