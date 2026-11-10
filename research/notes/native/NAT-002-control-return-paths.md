# NAT-002 source notes, 2026-11-10

Evidence category: source-review. No phone command was run for this note. The plan is
`docs/procedures/nat-002/README.md`.

- `docs/recovery.md` (NAT-001, measured 2026-11-10):
  - bootconfig says orange and vbmeta unlocked;
  - the stock `recovery` matches vbmeta and `init_boot` is Magisk-patched;
  - seven boot-chain backups are hash-checked;
  - restore is not tested;
  - Download Mode entry, forced restart, non-stock `recovery` boot and `install-recovery`
    behaviour are not observed.
- NAT-005 evidence: S-Boot runtime FDT with boot framebuffer 0xfa200000 (1080x2340) inside ordinary
  `/memory`, PSCI via SMC, GICv3. Recovery-boot fixups cannot be determined from Android.
- NAT-007 note (`research/notes/native/NAT-007-watchdog-return-path.md`):
  - S5E9945 watchdog registers and PMU routing come from `s24-linux`/`s24-bsp-reference`;
  - OSCCLK2 is 25.6 MHz;
  - `sec_reboot.c` writes reason 0x12345604 for recovery and 0x12345600 for normal through
    panic-inform (PMU offset 0xbc);
  - expiry, clock survival and S-Boot's next target are unmeasured.
- NAT-009 evidence: binary-derived reading of S-Boot `sbl_check_reboot_mode`/`load_boot_images` for
  S921BXXS9BYH3. It concludes that writing 0x12345600 makes the next watchdog reset boot normal
  Android. This is static analysis; no reset was observed.
- NAT-008 evidence: a pinned odin4 is provisioned on the host, and an offline parser accepts the
  exact stock archive. The restore itself is not run.
- `s24-port` c8860dec README:
  - The loader keeps a log record at 0x91200000. XNU patch 0011/0014 mirrors the console into a
    1 MiB ring at 0x91300000 inside `sec_debug_next`. The upstream reads it back with its own
    tool after a return.
  - The menu chainloader's Recovery/Download choices reset through PSCI and ask for the S-Boot key
    combination, "not verified on e1s".
  - Patch 0013's `rd=ufsroot0` path is untested.
  - `e1sdisp=2` DPU reads are opt-in because a read from a gated block can hang the interconnect.
- `watchdog-docs` (Linux watchdog API): a watchdog resets the system unless it is pinged. That
  makes it a liveness reset, not a guarantee that the next boot is the intended one.
- VM-054 (2026-11-10): the same XNU with `rd=md0` reaches PID 1 under s24vmm without storage, which
  supports the RAM-root design for the first native image.
