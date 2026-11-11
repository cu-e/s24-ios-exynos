# IOS-001: the iOS 16.5 (20F66) restore archive for iPhone10,3, inspected offline

Evidence class: **source-review** of an Apple-signed archive's metadata, produced by the host-tested inspector
`tools/ios/ipsw_inspect.py` (IOS-002). Nothing in this directory was run on the S24, and an `accepted` verdict is not a
compatibility statement (the report says `compatibility: "not-assessed"`).

What is local and never committed: `artifacts/apple-inputs/iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw` (the owner
placed it; its SHA-256 `c1091c40…d52f2` was re-hashed independently of the acquisition record) and
`artifacts/apple-inputs/ios-16.5-20F66-inventory.json` (the full inspector report). What is committed:
`ipsw-summary.json`, which carries versions, sizes and SHA-256 of Apple's public files and nothing else.

Command (about 24 s on the host, one pass over the 7.5 GB archive):

    python3 -I tools/ios/ipsw_inspect.py <ipsw> --kernel --sha256 --json > artifacts/apple-inputs/ios-16.5-20F66-inventory.json

## Established

* `ProductBuildVersion` 20F66, `ProductVersion` 16.5, `SupportedProductTypes` iPhone10,3 and iPhone10,6, BuildIdentities
  for device classes d22ap and d221ap in Erase and Update flavours.
* For D22AP every path the manifest lists exists in the archive: root filesystem `096-04088-077.dmg` (4.73 GB, stored),
  Cryptex SystemOS `096-04666-078.dmg` (2.73 GB), Cryptex AppOS `096-03536-083.dmg` (10.5 MB), RestoreRamDisk
  `096-03566-084.dmg` (Erase) and `096-04690-083.dmg` (Update), DeviceTree `Firmware/all_flash/DeviceTree.d22ap.im4p`,
  kernelcache `kernelcache.release.iphone10b`, plus the matching trust caches. SHA-256 of each is in the summary.
* The kernelcache is an unencrypted IM4P (`krnl`, builder `KernelCacheBuilder_release-2429.120.2`) whose payload is
  LZFSE (the pure-Python decoder in `tools/ios/lzfse_py.py` was checked byte for byte against the pinned reference C
  decoder on this very file: 50,888,732 bytes, equal to the size the IM4P trailer states). Inside: a one-slice fat
  wrapper around a 64-bit Mach-O, cputype 0x0100000c, cpusubtype 0, `MH_EXECUTE`, 25 load commands: plain arm64, not
  arm64e.
* Its banner: `Darwin Kernel Version 22.5.0: Mon Apr 24 21:10:12 PDT 2023; root:xnu-8796.122.4~1/RELEASE_ARM64_T8015`.

## Compared with the project kernel

| | Darwin | xnu revision | Configuration |
|---|---|---|---|
| IPSW kernelcache | 22.5.0 | 8796.122.4~1 | RELEASE_ARM64_T8015 (iPhone X, A11) |
| Project kernel (NAT-068 log; source `apple-xnu` c54f35ca) | 22.5.0 | 8796.121.2 | DEVELOPMENT_ARM64_E1S |

The Darwin release matches; the xnu revision does not. The public repository carries `xnu-8796.101.5`,
`xnu-8796.121.2` and `xnu-8796.141.3` only (`git ls-remote --tags`, 2026-11-12), so the source of 122.4~1 is not
available and the difference cannot be read from a diff. Whether it affects the userland ABI (syscall and Mach trap
tables, commpage, sysctl names, kernel-exported structures) is **unknown**; the first check that resolves it is a
comparison of the real kernelcache's tables with the project kernel's (host work, IOS-003).

## Not established

* What is inside the disk images. They are APFS (rootfs) and Cryptex images; no APFS/UDIF reader exists on the host
  yet, so dyld, the dyld shared cache (expected in the SystemOS Cryptex: a hypothesis), launchd, backboardd and
  SpringBoard have not been located or hashed.
* Whether any file from this build runs on the S24's kernel and CPU.
