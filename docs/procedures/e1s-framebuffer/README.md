# E1S CPU framebuffer contract overlay

Owner codex-e1s-framebuffer-20261106-sr5, isolated STR005 worktree from cb3e2d3.
Donor c886/compatible57d blobs are unchanged. Apply immutable accepted STR002 RAM
patch23b31 first, then this attributed GPL2 display overlay. Memory patch,
existing builder/prepare_xnu and pinned references are not edited.

Actual faults inspected before authoring: fdt_find_framebuffer uses names and a
low-address heuristic, ignores status/format and doesn't check stride*height
against reg extent; loader keeps FB_BASE/default mode on missing metadata and
always initializes/flushed UI; rect() has no buffer extent. The overlay admits
one explicitly enabled simple-framebuffer directly under /chosen, exact
NUL-terminated a8r8g8b8/x8r8g8b8, complete dimensions/stride/single reg tuple and
nonwrapping covered extent. It preserves the donor's low-memory candidate range
as a numerical policy, never a proof of RAM ownership. Other32bit layouts, absent
format/status/geometry, unsupported translation/phandle or ambiguity are headless.
Status is deliberately explicit on the framebuffer node; parent status may be
absent, but a disabled ancestor refuses the candidate. This is a conservative
loader policy, not a claim that DTSpec requires an explicit status property.

UI stores carry size_bytes and validate the complete descriptor, including padded
stride and arithmetic bounds, before drawing. Missing/invalid discovery zeros
video state, skips UI writes/cache flush and advertises headless boot video.
The loader continues its existing log diagnostics instead of guessing a physical
framebuffer. No modeset, scanout programming, clocks, backlight or VSYNC is added.
The supported pixel bit layouts follow the Linux [simple-framebuffer binding](https://www.kernel.org/doc/Documentation/devicetree/bindings/display/simple-framebuffer.yaml).
Status conventions are described by the [Devicetree specification](https://devicetree-specification.readthedocs.io/en/stable/devicetree-basics.html).

Remaining preconditions are explicit. S-Boot must supply physically readable,
aligned DTB backing through its declared size; numeric validation cannot probe
unmapped physical memory. An admitted framebuffer must actually be mapped,
CPU-writable/reserved and already scanning the declared layout; the enclosing
cache lines used by existing clean() must also be safe for cache maintenance.
Neither numerical reg bounds nor host buffers establish this on S24. log_init /
log_char still write LOG_BASE0x91200000 and boot_mark_init still writes/cleans
MARK_BASE0x912ff000 before framebuffer discovery. Those fixed regions must be
independently mapped/owned/reserved; headless diagnostics do not make them safe.
GIC/MMIO, payload/RAM ownership and later handoff are outside this overlay.

The preparation checker only copies pinned donor source, applies RAM/display
patches, extracts actual loader UI bodies, checks hashes and writes a prospective
six-command plan. Four commands compile/run baseline and patched full FDT/UI
host controls with existing qualified NDK18 GNU ASan/UBSan; two commands compile
loader and FDT/UI AArch64 freestanding objects. No compiler/control is executed
by preparation; root must admit the exact frozen plan. No new executor exists.
Use RSS-only supervision for sanitizer controls, not a small RLIMIT_AS. Existing
host runtime archive/tool/input hashes are pinned in the plan. Keep all failures.

Root51 executed prepare-2 once: baseline compile and nine unsafe-behavior
controls passed, then patched compilation failed because a legacy-only fixture
branch referenced the removed FB_BASE macro. Commands after that failure were
not run. Original12047e0 physical source, prepare-2 and raw9f165f4a remain
unchanged; failure-001.json binds the actual failure. A separate fix1 worktree
preprocesses the legacy branch and adds a1080x2340 padded-stride buffer between
PROT_NONE guard pages. It checks changed logical pixels after actual init,
info, stage, progress, status and failure calls, unchanged row padding/prefix,
and the exact flush extent. The original16x16 controls still exercise clipped
and invalid descriptors. No additional algorithm implementation is substituted.

Root54 executed the selected retry once: artifacts/e1s-framebuffer/prepare-3/plan.json,
SHA136996ea5ad15c387c50db7e1585854d81b7fcb17ca4b4d4ddfb7ca544fa86e1,
with exactly six commands, all exit0. STR005FB-002 actual PASS: baseline9
unsafe-behavior reproductions, patched55 ASan/UBSan controls, and AArch64 loader,
FDT and UI objects. Raw evidence5c0e998d is bound by evidence.json; elapsed5.777s,
maximum sampled child-tree RSS99,930,112 bytes, controller HWM31,133,696 bytes,
zero owned survivors. No author rerun occurred. All selected input/output hashes
were read back unchanged after execution. The original failed run remains FAIL. The display overlay and RAM parent bytes
are unchanged. Read-only canonical57d comparisons match all eight donor source/
header/font blobs (compatible-source-proof.json). Overlay check/apply on owned
copies and exact post-overlay body hashes succeeded. Literal.patch context
lines trigger Git whitespace diagnostics as patch text; source/fixture/procedure
diff checking excludes that patch representation. No global Git policy changed.

Source publication/common and independent acceptance remain pending. This overlay
is not yet invoked by the ordinary E1S builder; a separate dependent hook must
apply immutable RAM23b31 then display0689 before ordinary loader compilation.
No native image, physical scanout or S24 boot success is claimed.
