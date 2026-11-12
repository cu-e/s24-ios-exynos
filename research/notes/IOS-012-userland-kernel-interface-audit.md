# IOS-012 — What the iOS 16.5 userland expects from the kernel (static audit)

Evidence kind: **host-test / source-review**. Written 2026-11-12. Everything below was read from files on the host:
the owner's iPhone10,3 IPSW unpacked by the donor recipe (IOS-009), the project kernel tree (xnu-8796.121.2,
`DEVELOPMENT_ARM64_E1S`) and the NAT-068 notes. **Nothing here ran on the S24 and nothing ran in an emulator.** A name or
number match is not a behaviour match; a scan hit shows an access shape, not what the code does with it.

Machine-readable report (sanitized: counts, hashes, names, no Apple code): `docs/procedures/ios-012/interface-audit.json`.
Regenerate with `python3 -I docs/procedures/ios-012/make_reports.py OUT.json`. The auditor is
`tools/ios/macho_audit.py` (45 tests, 75 textual mutants all killed: `docs/procedures/ios-012/mutation.json`).

## 1. Why own code, and what it is

No ready tool was usable for this question: the cache is a split `dyld_shared_cache_arm64` set (43 files, 2,722,512,896 B,
2710 images) and the checks need the cache's images and exports read together with the project's own kernel tables. The
tool reads Mach-O, the split cache (mappings, image table, export tries), the kernel's `syscalls.master` with its `#if`
guards, `config/MASTER*` option states, `osfmk/kern/syscall_sw.c` and `osfmk/arm/cpu_capabilities.h`. For viewing code by
hand I used the Android NDK's `llvm-objdump` 19.0.1 (the owner's own SDK) on the local dyld; those hand readings are
labelled as such in the report and are not reproducible by the tool.

## 2. The six programs (acceptance 1)

All six are plain arm64 (not arm64e), platform iOS, `minos` = `sdk` = 16.5.0, chained fixups, `LC_LOAD_DYLINKER`
`/usr/lib/dyld` (dyld itself has none and no libraries).

| Program | Direct libs | Closure images in the cache | Required libs missing |
| --- | ---: | ---: | --- |
| `/usr/lib/dyld` | 0 | 0 | – |
| `/sbin/launchd` | 2 | 36 | none |
| `/usr/libexec/xpcproxy` | 3 | 85 | none |
| `/usr/libexec/amfid` | 17 | 365 | none |
| `/usr/libexec/backboardd` | 46 | 299 | none |
| `SpringBoard` | 4 | 1095 | none |

Missing but **weak/optional** (named, not needed to load): `/usr/appleinternal/lib/liblinkguard.dylib` (backboardd,
SpringBoard closure), `/usr/local/lib/libobjc-env.dylib` (libobjc), `Darwinup` (libtailspin), `MLCompilerRuntime`
(Espresso). Every other library of every closure resolves to an image of the cache, so the root needs no loose dylibs
besides the programs themselves. This says the files are present and arm64; it does not say dyld accepts them (R05/R07).

## 3. Syscall and Mach-trap numbers (acceptance 2) — static comparison

`libsystem_kernel` in the cache has 506 `svc #0x80`, 502 with a plain `mov x16,#N` before it (443 distinct BSD numbers,
58 distinct Mach traps). Against the project kernel's tables:

* **474 name matches**, **0 numbers absent** from the kernel table, **0 names that differ**, 0 entries that depend on an
  option the configuration does not define. Six stubs have no exported symbol at their address (numbers 2, 20, 26, 42, 116 ×2: the kernel names are fork,
  getpid, ptrace, pipe, gettimeofday); the buckets add up: 474 name matches + 22 nosys + 6 without export name = the 502 stubs that have an immediate.
* **22 numbers exist in the table but are `nosys`/`enosys` in this configuration** (guards resolved from `config/MASTER*`):
  251-256, 258-265 (SysV `semsys`/`msgsys`/`shmsys`/`semctl`/`semget`/`semop`/`msg*`/`shm*`), 293 `__identitysvc`,
  337 `sendfile`, 418/419 `msgsnd`/`msgrcv$NOCANCEL`, 483 `__csrctl`, 493 `grab_pgo_data`, 519 `register_uexc_handler`,
  535 `objc_bp_assist_cfg_np`. Which of them the programs call is **not established**; `__csrctl` (behind `csr_check`) and
  `sendfile` are the ones worth watching.
* **dyld's own `svc` sites:** 158 distinct numbers, **all enabled** in the configuration.

Limit: the target kernelcache is `xnu-8796.122.4~1` (T8015); only 121.2 is public here. Numbers and names agree in this
audit; argument layouts and semantics were not compared. (IOS-003 R20.)

## 4. dyld's and launchd's expectations of the kernel (acceptance 3)

**Strings (R05/R07/R09/R19).** dyld carries 31 `DYLD_*` variables incl. `DYLD_AMFI_FAKE`, the cryptex paths
`/System/Cryptexes/OS` and `/System/Volumes/Preboot/Cryptexes/OS/`, `cryptex1/current`, `os.dmg.trustcache` /
`app.dmg.trustcache`, `XPC_USERSPACE_PIVOTEDROOT`/`REBOOTED`, `/System/Library/Caches/com.apple.dyld/`. launchd carries
21 sysctl-name strings (list in the report), among them `vm.shared_region_pivot` and `kern.syscall_rejection_masks`.

**libignition inside dyld (R07/R19/R01).** dyld 16.5 embeds Apple's boot-time "ignition" code (73 strings containing `libignition`, 87 mentioning "ignition"). Its
boot-args are `ignition_level`, `ignition_halt_after`, `ignition_force_dylib_root`, `ignition_live_app_graft`. Its steps, from the
messages: find the preboot volume, open the OS cryptex, **graft the cryptex image and load its trust cache** (`graftdmg`), then find
the shared cache; messages include "ignition level insufficient: operation = load trust cache, actual = %llu, required >= %llu",
"dylib cache directory present; not overriding" and "shared cache not found: root = %s, path = %s". The donor recipe's merged root
(cache under the root, no cryptex graft) relies on the "present; not overriding" branch; whether it is taken with this root is
**not established** and needs the first dyld run. launchd has the string "No service cache" and no `unsecure_cache`/`handshake`/
`ignition` string (R09).

**Sysctls (source review).** All 17 sysctls the report lists are declared in the project tree. Two have a condition:
`kern.syscall_rejection_masks` needs `CONFIG_DEBUG_SYSCALL_REJECTION`, which is **off** in this configuration, so that sysctl does not exist for
launchd (its reaction is unknown); `vm.footprint_suspend` is DEVELOPMENT-only (on). `vm.shared_region_pivot` is unguarded and returns
EPERM unless the caller is `initproc`. Generic BSD sysctls (`kern.maxproc`, `kern.hostname`, …) were not checked one by one.

**Commpage (R22, new).** A scan of `__text` for constants forming addresses in the 64-bit commpage (RW page 0xfffffc000,
RO page 0xfffff4000; heuristic, a miss proves nothing) finds, per image (full table in the report):

* fields the project header defines and the kernel fills: CPU_CAPABILITIES/64, NCPUS-area bytes, ACTIVE/PHYSICAL/LOGICAL
  CPUS, MEMORY_SIZE, CPUFAMILY, TIMEBASE_OFFSET, USER_TIMEBASE, CONT_TIMEBASE, BOOTTIME_USEC, APPROX_TIME, KDEBUG_ENABLE,
  ATM_DIAGNOSTIC_CONFIG, MULTIUSER_CONFIG, NEWTIMEOFDAY_DATA, DYLD_FLAGS, CPU_QUIESCENT_COUNTER, DTRACE_DOF_ENABLED,
  RO USER_PAGE_SHIFT_64, RO DEV_FIRM (also read by **launchd, xpcproxy, libxpc**);
* byte +0x23 (top byte of the CPU_CAPABILITIES word; 348 reads in libdispatch, 78 in libsystem_platform, 26 in pthread);
* **three offsets in dyld that the open header does not define: +0xd0 (50 reads), +0xd8 (28), +0x10c (14)**, and +0x105.

**Apple-specific system registers (R23, new).** Scanning every `mrs`/`msr` (op0 3, CRn 11 or 15 = implementation defined)
in the programs and 14 cache images finds exactly two registers, and only in two images:

* `S3_4_C15_C10_6`, `mrs` ×2 in `libsystem_kernel` and ×2 in dyld. Source: the project kernel's `user_timebase_type()`
  returns `USER_TIMEBASE_NOSPEC_APPLE` (3, the value that makes userland read this register) only when `HAS_ACNTVCT` is
  defined, and the only definition is `pexpert/pexpert/arm64/H13.h` (not part of the e1s configuration). So the e1s
  kernel publishes 1 or 2 at commpage +0x90. That is a source-level expectation, not an observation.
* `S3_6_C15_C1_5`, 65 `mrs` and 39 `msr`, **dyld only**.

**dyld's use of `S3_6_C15_C1_5` (hand-read, `dyld4::APIs::dlopen_from`, vm 0x7980-0x7a1c).** When a byte at +0x21 of
an allocator object is non-zero, dyld reads the commpage byte +0x10c; if it is 0 or `(b & 0xfe) != 2` the code reaches
`brk #1`; otherwise it writes the commpage u64 at +0xd0 (and, in the twin sequence at 0x7bb0, +0xd8) into
`S3_6_C15_C1_5`, `isb`, reads the register back and `brk`s on a mismatch. When the byte is zero the same function takes the
software path (`lsl::MemoryManager::lockGuard`; `MemoryManager::writeProtect` issues `mprotect` with PROT_READ and
PROT_READ|PROT_WRITE). The open `x86_64_commpage_t` in `osfmk/arm/cpu_x86_64_capabilities.h` has fields named
`cp_aprr_shadow_*`; that is a different (x86_64-translation) commpage, so it suggests, but does not show, what +0xd0/+0xd8
are. **Not established:** where the allocator byte is set non-zero, hence which path a run on the S24 takes. If it takes the
register path, the S24 CPU would have to implement an Apple register that Cortex cores do not (architectural expectation,
unverified here), and `brk #1` would follow with this kernel (+0x10c is never written). Nothing in this audit says
this happens; the first dyld run will.

**Shared-region mapping and code-signing checks (R05/R06/R07/R19; static).** dyld's own `svc` list (158 numbers, all enabled)
contains the whole shared-cache path: `shared_region_check_np` (294), `shared_region_map_and_slide_2_np` (536),
`map_with_linking_np` (550), plus `graftdmg` (549), `__mac_syscall` (381), `mremap_encrypted` (489), `fsgetpath` (427),
`proc_info` (336) and `process_policy` (323). It has **no `csops`**. Facts and what they do not show:

* The cache's shared region is 0x180000000 + 0xa9eec000 (2.66 GiB). The project kernel defines
  `SHARED_REGION_BASE_ARM64 0x180000000` and `SHARED_REGION_SIZE_ARM64 0x100000000` (4 GiB), so the cache fits the kernel's
  region by address and size. Whether `shared_region_map_and_slide_2_np` accepts the 43 cache files (slide info, the
  `.dyld_shared_cache` mapping flags, code-signature registration) was not checked beyond numbers; the kernel side of those
  checks is IOS-003 R19/R05.
* dyld's strings name the checks it makes of the cache and of images itself: "code signature registration for shared cache
  failed", "code signature does not cover entire shared cache file", "shared cache code signature size is invalid",
  "code signing blocked mmap() of '%s'", "code signature in <%s> '%s' not valid for use in process: %s". So a kernel that
  returns an error for the code-signature registration of the cache stops dyld at these messages. dyld contains **no
  entitlement-check string** (0 matches for "entitle"); AMFI appears only as `DYLD_AMFI_FAKE` and the string `AMFI`.
* launchd, not dyld, contains the entitlement logic: "CoreEntitlements" DER parsing, "Service (pid %d) does not have spawn
  driver entitlement", "denied attach request from %s - missing entitlement %s", "_Cryptex requires %s entitlement",
  "setting persona requires an entitlement", 32 `com.apple.private.*` names, and the sysctl
  `security.mac.amfi.developer_mode_status`. launchd therefore asks the kernel for the process's entitlements; where the
  project kernel answers that (AMFI/`mac_*` policy, the code signature's entitlement blob) is the IOS-003 R05/R06 question and
  is still open.
* This audit does not say what the project kernel does when a signed Apple binary reaches `mac_vnode_check_signature`
  (declared in `security/mac_vfs.c`, called from `bsd/kern/ubc_subr.c`; `CONFIG_MACF` is on in `config/MASTER`) without an
  AMFI policy module. The source has code-signing boot-args that relax enforcement: `bsd/kern/kern_codesigning.c` parses
  `amfi_get_out_of_my_way`, `amfi_allow_any_signature` and `cs_enforcement_disable` and sets `CS_CONFIG_ALLOW_ANY_SIGNATURE` /
  `CS_CONFIG_GET_OUT_OF_MY_WAY` from them. Whether they apply to these binaries with this kernel build, and whether launchd's
  entitlement reads still succeed without them, is a first-run observation, not a static fact (R05/R06/R07).

## 5. Tie-in to the IOS-003 matrix

| Row | Before | After this audit |
| --- | --- | --- |
| R19 dyld / shared cache | cache size/location unknown | 43 files, 2,722,512,896 B, 2710 images, os 16.5.0, shared region 0x180000000 + 0xa9eec000; closures of all six programs resolve |
| R20 syscall numbering | unknown | static match for 474 stubs, 22 nosys listed, dyld's 158 numbers enabled; semantics and 122.4~1 differences unknown |
| R05/R07 AMFI, trust cache | strings only in the kernel image | dyld strings listed (`DYLD_AMFI_FAKE`, `*.dmg.trustcache`, cryptex paths, libignition trust-cache load gated by `ignition_level`); no runtime fact |
| R09 launchd handshake | 0 occurrences in image scan | launchd strings searched: "No service cache" present; `unsecure_cache`, `handshake`, `ignition` absent. dyld, not launchd, carries libignition |
| R22 (new) commpage fields | – | dyld reads +0xd0/+0xd8/+0x10c, undefined in the open header |
| R23 (new) Apple registers | – | `S3_6_C15_C1_5` (dyld), `S3_4_C15_C10_6` (dyld, libsystem_kernel); selection logic partly read |

## 6. What this changes about the path

* No missing userland file was found for the closures of launchd, backboardd and SpringBoard. The inputs the owner
  supplied (the IPSW) suffice; nothing else needs to be obtained for these six programs.
* The earliest dyld-specific risk is the allocator write-protection path of section 4. Open host item: find where the
  allocator byte at +0x21 is set (more dyld reading). The first dyld run on the S24 answers it directly: a `brk #1` at
  dyld vm 0x7d3c (SIGTRAP/EXC_BREAKPOINT) means the register path was taken.
* The commpage the project kernel builds lacks +0xd0/+0xd8/+0x10c (zero-filled). If the register path is chosen,
  patching the kernel to publish the values would not help because the register does not exist on the S24; the flag
  would have to be zero. That is a hypothesis for the first dyld run, not a plan.
* Delivery of the 2.31 GiB root to RAM within the run window remains the earliest blocker; this audit does not touch it.
