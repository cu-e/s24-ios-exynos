# Exact source trace

Line references below refer to artifacts/e1s-boot-log/source-002/baseline,
which is pinned c886 plus accepted RAM23b31 and framebuffer0689. Their hashes
are in source-bindings.json. Donor and canonical57d bytes match for all13 files.

| Source and lines | Concrete behavior and precondition |
|---|---|
| loader.c:394-396 | Accepted fdt_validate rejects malformed declared DTB before these log calls. It still requires actually readable DTB backing. |
| loader.c:397-401 | log_init, boot_mark_init and banner text all execute before framebuffer discovery at403. Valid DTB does not authorize unrelated fixed writes. |
| loader.c:77-85 | log_init writes eight magic bytes at0x91200000,32-bit fields at+8/+12, and a byte at+16. No RAM ownership or mapping check precedes them. |
| loader.c:88-93 | Each log_char writes to0x91200010+log_pos and then updates0x91200008; saturation limits length, not destination ownership. |
| loader.c:139-146 | boot_mark_init writes magic at0x912ff000 and64-bit zero at+8; clean() touches enclosing cache lines through+64. |
| loader.c:129-136 | clean derives line size from CTR_EL0 and issues dc civac plus dsb; it is not a memory ownership/mapping check. |
| loader.c:403-410,149-153 | Accepted framebuffer descriptor controls UI and framebuffer flush. Its failure suppresses those writes while existing log writes continue. No framebuffer regression retest is needed for the proposal's UI text edit. |
| loader.c:335-356 | choose_window excludes framebuffer, legacy diagnostic2MiB, loader extent and DTB; this later calculation cannot justify already completed early physical writes. |
| loader.c:479-482 | Old loader exclusion uses0x40000+32MiB or selected payload offset+32MiB, without the actual linker image end and without checked addition before this step. |
| loader.c:694 | A second fixed log cache clean occurs immediately before hold/return. |
| loader.c:700-719 | loader_exception also appends through the same log_str/hex/kv; it can encounter the same destination failure. No separate safe logging backend exists. |
| loader.ld:5-15 | .text, .rodata, .data (including .data.bootlog), then BSS, then4096-aligned _payload_start/_end. Storage is part of the loader image by the real rule, not a guessed spare physical page. |
| start.S:7-8,66-77,96-99 | Linux-style header contains _payload_start, BSS is cleared, loader_main receives DTB/EL/SCTLR, and payload_addr returns that linker boundary. Initialized .data avoids relying on a new BSS allocation. |
| start.S:78-89 | Success loads boot_args_pa into x0, switches cache/MMU state as before and branches via x16. This entire source is unchanged. |
| loader.c:22-58 | payload and boot_args declarations retain all byte identities/assertions: segs0x2a8, Video40, CommandLine108, sizeof boot_args736. |
| xnu/e1s/patches/0012-e1s-boot-marker.patch | Unchanged kernel E1S_BOOT_MARK materializes0x912ff000 and str x10,[x9,#8] at checkpoints1-4. It neither reads loader magic nor takes a marker pointer in boot_args. Moving the loader's magic would not redirect these writes. |
| xnu/e1s/patches/0011-e1s-log.patch | Unchanged e1s_log_init defaults on unless e1slog=0, calls ml_io_map(0x91300000,1MiB), then writes header/ring; mapping success alone does not prove reservation ownership. |
| tools/e1s/read_log.py:29-49,75-87 | extract() locates E1SXNU01 anywhere in input and uses+8 length/+16 text; extract_boot_mark independently searches E1SMARK1. A relocated record is parseable only if its actual bytes are obtained. The proposal intentionally emits no relocated marker. |

Proposal source-only identities and unchanged-function comparisons are recorded
in proposal-bindings.json. Loader local record is not passed to the kernel;
no field is added to the payload, ADT or boot_args and no pointer is smuggled
through bootFlags or an undocumented register. Legacy kernel diagnostics and
physical mapping/cache semantics remain explicit pending prerequisites.
