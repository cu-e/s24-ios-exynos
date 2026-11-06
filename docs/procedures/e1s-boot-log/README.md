# E1S loader-owned boot log proposal

STR-019 is source-first preparation by codex-e1s-boot-log-20261106-sr19, in an
isolated worktree from862b64a8b627c7b25f9103d36095335fd8d44810. This proposal is
not integrated into tools/build/e1s.py. No compiler, host C test, target, device,
MMIO, firmware or kernel execution has occurred in this task.

The ordinary builder currently checks/applies immutable RAM patch23b31c44 and
framebuffer patch0689fc94 before compiling the upstream loader. The proposal
applies after both. Canonical c886 and57d source identities agree for all13
inspected files. Source bindings include complete SHA256 and Git blob IDs.
GPL-2.0-only loader/UI notices remain unchanged; the new overlay is attributed
and licensed GPL-2.0-only. This does not extend a license to unrelated upstream
kernel additions.

See source-trace.md for exact composed-source line witnesses and
fixtures/public/e1s-boot-log/host-acceptance.json for prospective controls.

The proposed log is an initialized volatile object in .data.bootlog. Existing
loader.ld line7 includes *(.data*), before BSS and the aligned _payload_start
at line14; start.S lines7-8 and96-99 derive image size/payload address from that
symbol. No new fixed physical address, linker script, image header field,
register handoff, payload or boot_args layout is introduced. The section must
be verified in a future genuine target object/link before a build claim. The
loader's existing loaded-image writable mapping is an explicit prerequisite,
just as for its existing data/stack. Host source checks cannot establish it.

log_init, log_char, log_str, log_hex and log_kv continue to retain bounded early
text. The record keeps E1SXNU01, a16-byte header, little-endian32-bit length at+8,
reserved field at+12 and at most0xff00 text bytes at+16. An extra in-object byte
terminates the string at saturation. The original read_log.py searches for the
magic at any offset, so a separately obtained dump of the actual loader image
can still be decoded. This provides CPU-local retained diagnostics and the
existing validated framebuffer UI; it does not provide UART, USB, remote
retrieval, persistent crash RAM or a log visible on a headless phone. The exact
runtime address is not available from this source-only work. Cache persistence
through MMU/cache shutdown, XNU reuse or reset is deliberately unqualified.

The loader no longer initializes E1SMARK1, emits a fake relocated marker or
cleans the old fixed log/marker addresses. This changes the fixed-location
diagnostic convention: dumping0x91200000 is no longer a way to retrieve the
loader log, and no initialized marker can be decoded from0x912ff000. The boot
ABI is unchanged; the diagnostic-location convention is not preserved. It
would be misleading to call this a complete boot checkpoint implementation.

The unchanged XNU0012 E1S_BOOT_MARK macro still stores checkpoints at0x912ff008
before its MMU setup. XNU0011 later maps/writes its own ring at0x91300000.
Neither depends on the loader's magic to authorize its write. These are
separate unresolved native ownership/mapping gates and this task does not
modify the accepted native sourcecontext. Keep the existing numerical2MiB
LOG_BASE/LOG_RESERVE exclusion in choose_window for those consumers. Exclusion
is not proof of firmware reservation, accessibility, writability or safe cache
maintenance. No native run becomes authorized or safe merely by this patch.

The larger record cannot rely on the old0x40000 loader-size guess.
loader_reserved_size retains the old payload-offset+32MiB reserve (or old
0x40000+32MiB branch), rejects arithmetic overflow, and expands that exclusion
to at least payload_addr()-_head. payload_addr is the actual _payload_start
boundary, even when the selected payload p instead comes from an external
initrd. Only the larger numerical extent is excluded; no RAM window is invented.
The original choose_window body and FDT/UI validation bodies remain byte-identical.

First source preparation failed because57d was queried in the old c886-only
Git database. failure-001.json and source-001 remain immutable. The corrected
source-002 uses the canonical upstream.git named by accepted framebuffer
compatible-source-proof.json; no shared reference hydration was performed.
Its43 Git reads/checks/applications and two proposal check/applications pass.
This is source-review evidence, not C behavior or physical-memory evidence.

Next: independent review of this proposal and source closure. Only after that,
freeze actual-function host controls and a finite compiler/sanitizer execution
plan using existing qualified tools/supervision, then request root admission.
Do not rerun accepted framebuffer infrastructure for a string-only UI change.
Target image build/link and shared builder integration require separate review
and resource admission. STR-019 remains in_progress; no completion is requested.
