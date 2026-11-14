# NAT-203: mediaserverd with the donor's media library (host-test)

**Evidence kind:** host-test. Nothing here ran on the phone. The native run is NAT-204.

## Why

NAT-202 recorded mediaserverd's fault: 46 times at one site, `pc 0`. It is a call through CoreImage's empty OpenGL ES dispatch
table, under CMCapture's portrait-filter prewarm, `+[BWCoreImageFilterRenderer prewarmPortraitFilterVersion:semanticStyleFilters:]`
(0x1a2115c0c). launchd restarts the daemon about every 5 s.

The donor, HackiOS (`references/hakios` 87bf4851bcc9cbb24fd79997820aa3661abe4ea5, MIT), describes this exact fault in
`userland/src/inject_media.c` and fixes it there. Its library `libhakios.media.dylib`, which the kernel inserts into mediaserverd
(`sysctl kern.exec_inject`), replaces the prewarm with an empty method. It does so only when the method is at its 20F66 address;
otherwise it prints "left alone".

Its other replacements act only in two cases:
- with `/dev/hakios-torch` or `/dev/hakios-camera`, which this kernel does not create;
- inside a capture graph, which nothing starts here.

Our md0 `etc/inject.conf` names libraries for backboardd, the containermanagerds and SpringBoard, but not mediaserverd. The
donor's default list has it.

SpringBoard's SMP-only abort (`routingContextUID`, NAT-200, NAT-202) asks for an audio routing context, and mediaserverd is the
audio server. Whether the abort goes away with a running mediaserverd is the question for NAT-204.

## Change

**md0 root `artifacts/nat-203/pid1-sc2-hbm`** (`build_hbm_root.py`). Against NAT-110's tree:
- **Added.** `lib/libhakios.media.dylib`, the donor's prebuilt (mode 0755):
  - read from the pinned commit's git object (blob 93a6028b…, SHA-256 d8680034e5f0cdecd396cd7488e9d0f30037223ebc57f5309f99a6cd45a4ad26);
  - added the same way NAT-108 added `libhakios.sb.dylib`.
- **Changed.** `etc/inject.conf` gains one line, `/redwood/lib/libhakios.media.dylib mediaserverd`.

The root APFS is 9a1eaab6f0a3fa278dc99ff6656a38658de8b212391eecf8dca5ba7d41c4d43d (4 MiB, 842 blocks free). `verify.py` and
apfs-tool read both files back as written.

**Image `loader-diag-xnu-e2m-md1`** (`build.py`). It is e2s (NAT-201), with:
- the same kernel, with the user-exception trace on;
- the same loader and command line, apart from the tag `nat_attempt=NAT203-e2m`;
- the new md0, swapped in through the chain's md0 pin, as NAT-187 did.

## Host checks

All on 2026-11-14.

**`test_nat203.py`: 11 tests, OK.**
- **Tree.** Exactly the one file added and the one file changed. The old inject lines are unchanged, and the list is under
  the kernel's 512 bytes.
- **Library.** Its hash, mode and APFS readback match. The blob is read from the pinned donor commit.
- **Donor source.** At the same commit, the library:
  - acts only in `mediaserverd`;
  - replaces the prewarm only at 0x1a2115c0c;
  - leaves a moved method alone.
- **Cache.** 0x1a2115c0c is a function start, after the previous function's `b`. Its tail branch at 0x1a2115c68 goes to
  0x1a2115cc4, the function that NAT-202's frame `+0x4e4` is in.
- **Image.** The kernel is NAT-201's, and the command line is e2s's with the tag changed. Loader sites are rc 0. The payload holds
  the new md0 and not the old one.
- **Session.** The counted derivation is current. Its docstring corrects the stale "boot-arg systrace=1" text of
  `session_nat202.py`.
- **`media204.py` verdicts.** NAT-202's own kernel text gives M-same (46 traps at the site, 10 SIGSEGV exits). Synthetic text
  gives M-fixed, M-other (a SIGABRT exit; pc not 0; a wrong slide) and M-none.

**Mutants of `media204.py`.** All three are killed:
- signal exits not counted;
- the slide not subtracted;
- the pc-0 condition dropped.

## Image

`loader-diag-xnu-e2m-md1`:
- RECOVERY `artifacts/nat-203/package-001/loader-diag-xnu-e2m-md1/recovery.img`, SHA-256
  6d27f0de85bcba195c7b6546315b0cbe4f5f3b9577020666cb694c20c6894c96;
- payload 1f71263d976311e204e034d43b49fbc17acea5f889290e23923ae49b026d92d3 (26208400 bytes);
- kernel no-storage dd5cbc7d9c6e58935b6bd1f3e0ad96632ad43bd174040c14d1c6b09e9861c07f (NAT-201's).

Session driver: `session_nat204.py`, SHA-256 64d4afefc6183899feb4b569b28671f674931b0dc2c94459565c31b215178f73.

```
python3 -B docs/procedures/nat-203/build_hbm_root.py
python3 -B docs/procedures/nat-203/build.py --out artifacts/nat-203/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-203/pid1-sc2-hbm/root.apfs
python3 -B -I docs/procedures/nat-044/package.py --build artifacts/nat-203/build-001 --out artifacts/nat-203/package-001
python3 -B docs/procedures/nat-203/derive204.py
python3 -B docs/procedures/nat-203/test_nat203.py
```

## Criteria registered for NAT-204 (before the run)

`media204.py` on the kernel text. The first match wins:

| verdict | condition |
|---|---|
| M-none | no mediaserverd line: inconclusive |
| M-same | a mediaserverd trap at NAT-202's site (pc 0, lr CoreImage 0x194b1458c unslid): the library did not take effect |
| M-other | a mediaserverd trap elsewhere, or an exit due to a signal |
| M-fixed | mediaserverd lines, no trap and no exit due to a signal |

Reported beside it, with these labels:
- **Abort question.** `reason200`: does SpringBoard still abort with `routingContextUID`?
  - **A-gone:** no abort line.
  - **A-same:** the same reason.
  - **A-other:** another reason.
- **CPUs.** `smp198`.
- **Boot CPU.** The scV measures: display, frames, busy share.
