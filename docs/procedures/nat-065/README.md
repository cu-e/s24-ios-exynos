# NAT-065: a root device (md0) and a probe PID 1 for the payload kernel (host-test image `loader-diag-xnu-md0-usb`)

Evidence kind: **host-test**. Nothing in this directory has run on the S24. The image was built, inspected and exercised on the host only: static reads of the built payload, a host build of the
loader's real `adt_patch.c` with a C harness (ASAN/UBSAN), a unicorn simulation of the probe init with a fake system-call table, and the NAT-062 driver/analyser run against simulated archives.
A simulated run is not hardware evidence, and unicorn is not an Exynos model or an XNU.

## Why

NAT-063 (decision 0026, native-device) showed that the payload kernel, once resumed at C checkpoint 21, runs by itself to `IOFindBSDRoot` and panics there because `rd=md0` names a RAM device and
the payload has no ramdisk. NAT-064 (source review + host-test) worked out the path from a `/chosen/memory-map` `RAMDisk` property to `md0`, the mount, `load_init_program` and the init's exit.
This task builds the image that tests that path on the phone: the same loader, the same kernel, a ramdisk with a tiny user-mode program, and a command line that lets the kernel exec it.

## What was built

`build.py` is NAT-062's build (the loader, stub, `KL` log dump and the run on after C checkpoint 21 are re-derived and unchanged) with the image name `loader-diag-xnu-md0-usb` and a different XNU payload.

* **The payload** is rebuilt from NAT-020's pinned `kernel.no-storage` and `e1s.adt` by the pinned `mkpayload.py --ramdisk` (without a ramdisk it is byte-identical to the NAT-020 payload, NAT-064):
  one more segment holding the ramdisk (16635 bytes, 0x8000 vm size, at the old `kernel_end`) and a 52-byte `/chosen/memory-map` `RAMDisk` property. The ADT becomes 14008 bytes, a multiple of 8, so NAT-022's
  adt_size fix (13956 -> 13960) is **not** applied (the build refuses it).
* **The ramdisk** is `src/probe-init.S` through `clang -target arm64-apple-ios16.0` and the pinned `mkinit.py`: a static arm64 Mach-O that aligns SP, opens `/dev/console` (exit `0x60` if that fails),
  writes `\n*** SWEET userspace: init running as PID N ***\n`, calls `select` for 1 s, writes `SWEET probe: done, exiting\n` and calls `exit(0x50 + getpid())` (81 for PID 1). It maps nothing, opens nothing else and
  has no loop. It differs from the upstream `sweet-init.S` only as documented in `build.py` (the test checks this on comment-stripped text).
* **The command line** (203 bytes): `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT065-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1`.
  Against NAT-062: the `nat_attempt` tag, and `launchdsuffix=release cs_enforcement_disable=1` (the boot-args the pinned upstream test line uses for an ad-hoc-signed test `/sbin/launchd`).
* **`analyze_nat065.py`** calls NAT-062's analyser unchanged under this image's name (boot id = FNV-1a-64 of the image name) and adds `root`: `probe-ran-to-exit` (panic "initproc failed to start ... exit
  status 8N"), `probe-no-console` (96), `init-exited-other`, `init-killed`, `root-device-missing` (the NAT-063 panic), `other-panic`, `no-panic-text`. It also normalises the kernel's microsecond field
  (runs to 1,024,000 per real second). `root` is a reading of delivered text, nothing more.
* **`session_nat065.py`** is the NAT-062 driver with only the pinned substitutions (image, hashes, package, required-done list incl. NAT-063/064/065, decision glob
  `*-nat065-loader-diag-xnu-md0-usb-single-run-*.md`, marker `artifacts/nat-065/native-attempt-*-used.json`); `test_nat065_run.py` derives the expected text from NAT-062's driver and tests, and
  compares them, so that nothing else differs. The derived tests run NAT-062's whole flow/real-tree-gate/verdict suites against the new names.

## Pins

* RECOVERY SHA-256 `c6f4a6e45806edf211ce7de16bf0882268b3f8d22f065a21e575bdb66b06f34d` (100663296 bytes, `artifacts/nat-065/package-001/loader-diag-xnu-md0-usb/recovery.img`, 19634 4 KiB pages differ from stock);
  `Image.payload` `60ca7fc9759efff584b9a13795a16b3a262310cd7823770a408fbac2109087ce` (21878704 bytes at offset 2048); loader-only `Image`
  `aa96893fb453dfee8bf2ce7f656f6ab2a94cb030aa700504d4ecf2698426d5dd` (307200 bytes; it differs from NAT-062's Image only in six boot-id/name immediate words); XNU payload
  `131bc977e12e0a72d8f45320e53676e7e64fada56147e753e6015fac8bbc0941` (21571504 bytes); ramdisk `b3decc846877fb1de608fcd2734e9c3cb5d2d4ed9e3388bf99d303a45e4761a6`.
* Sources: `build.py` `f2f964c068efa17f988752dee547d72dd1b0eaaec0d1344e924f8b13bf7698d8`, `src/probe-init.S` `e87b80759cb43f419e59a4370e65623634b0ad6f385f61faacefc593ae538e65`,
  `analyze_nat065.py` `b4b9d2f9440aa354dd2c8d0f1c99fe328669d92a763f4fdc3ea22e49a72c5569`, `session_nat065.py` `1cf8939bc75b90fbdd48b3765f1af814060ecf0d5c2d8cfc482f6d1754aa0caa`.
* Reproducible: two builds (`artifacts/nat-065/build-001`, `build-002`) gave the same hashes; `test_nat065.py` rebuilds the payload and the probe and compares them byte for byte.

## What the host tests establish (and what they do not)

* **`test_nat065.py`** (24 tests): the inputs are the pinned ones; the two builds agree; the build record pins everything; the command line is exactly the expected one and the builder refuses bad fields; the payload differs
  from NAT-062's only by the segment, the property and the header fields NAT-064 lists; the loader code that rebases the property (the real `adt_patch.c`, built for the host) moves it by `win_base - phys_base`, leaves
  the other properties alone, refuses malformed trees, and the resulting range lies in the kernel window and outside every other segment; the probe is a valid Mach-O with correct CodeDirectory page hashes and
  a simulated run gives exit 81/96/82 with the expected calls (`open`, `write`, `getpid`, `write`, `write`, `select`, `write`, `exit`), SP 16-aligned at every `svc`, all writes to fd 3; the package carries the payload at 2048 and
  changes the stock boot header only in the allowed fields.
* **`test_nat065_run.py`** (52 tests; 18 of them are this task's own): the driver differs from NAT-062's only where this task says; the analyser reuses NAT-062's and adds only `root`; `root` classifies each outcome above
  on text built from the real committed NAT-063 kernel log (root-device-missing) and on derived panic texts (probe exit 81, 96, other status, signal), also through the full analyser; the derived NAT-062 suites (driver flow, real-tree
  gate, verdicts) pass for the new image names.
* **Mutation check** (`mutants.py`): 58 mutants of the build, the loader rebase input, the probe, the analyser and the driver; 56 killed, 2 equivalent (M12: the multiple-of-8 check guards a property of the pinned inputs, which the pin check
  already fixes; M13: `mkpayload.py` always writes the `SWEETXNU` magic and the loader checks it again; both reasons are in `mutants.py`), none survived, none invalid
  (`artifacts/nat-065/mutants-001.{log,json}`). A10 is also listed as possibly equivalent in `mutants.py` but was killed. NAT-062's own loader/stub/dump mutants are not repeated, and the re-targeted
  `Verdicts` layer is not re-run per mutant (it takes minutes); it is in the full run test.
* **Not established on hardware:** that the ramdisk bytes land at the address the kernel computes (the loader's rebase has never run on the phone); that `vfs_mountroot` accepts the raw Mach-O through the mockfs; that exec of
  an ad-hoc-signed init is permitted; that PID 1's console text reaches `loader_log` live (the verdict therefore comes from the panic text, not from the banner); the absolute kernel clock rate; the timed `loader_return_after=8`
  return. NAT-066 would measure the first four; the decision file names them.

## Decision draft and the next task

`decision-draft.md` is the text of the future decision 0027 (`docs/decisions/0027-nat065-loader-diag-xnu-md0-usb-single-run-2026-11-12.md`); it names both hashes and decision 0019 as the driver requires, the limits above,
the pass/fail rule (`root.outcome == "probe-ran-to-exit"`) and that a failed mount loops with 5 s sleeps and no panic (PARTIAL). **No owner confirmation specific to this image is recorded and nothing was run on the phone.**
NAT-066 (native) promotes the draft, commits it, opens `native` citing it, and runs `session_nat065.py --image loader-diag-xnu-md0-usb --out artifacts/nat-066/run-001 --execute`.

## Run the tests

    TMPDIR=<dir outside artifacts/> artifacts/nat-065/venv/bin/python -W ignore -I docs/procedures/nat-065/test_nat065.py -v        # 24 tests, about 1 s
    TMPDIR=<dir outside artifacts/> artifacts/nat-065/venv/bin/python -W ignore -I docs/procedures/nat-065/test_nat065_run.py -v    # 52 tests, about 3.5 min
    artifacts/nat-065/venv/bin/python -W ignore -I docs/procedures/nat-065/mutants.py --json artifacts/nat-065/mutants-001.json     # 58 mutants

(The venv holds capstone, pyusb and unicorn; the system python has none of them.)
