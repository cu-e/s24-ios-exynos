# Actual E1S framebuffer C controls

The fixture links full donor fdt.c/ui.c and extracts only the unchanged spelling
of loader framebuffer globals/ui_init/fb_flush into loader_ui.inc. Baseline is
original donor plus accepted RAM patch23b31; patched adds this display overlay.
FDT bytes and synthetic registers exercise actual C decoding, not a Python model.

Baseline controls use bounded, structurally valid DTBs to reproduce acceptance
of unsupported/absent metadata. Actual initial FB_BASE retention on no-node is
checked, then the pointer is replaced with an allocated host buffer before any
UI call. Extent-blind writes beyond advertised16bytes are observed within a
512byte backing allocation, so no real MMIO or sanitizer-invalid write is needed.

Patched cases include padded stride, both supported formats, exact small extent,
short/wrapped regions, bad dimensions/stride, missing/malformed/duplicate metadata,
disabled ancestor, late properties, wrong path/reg shape, phandle/translation,
ambiguous nodes and malformed DTB bounds. Rendering uses actual full UI with an
owned mapping ending at PROT_NONE plus untouched row padding/prefix guards. The
actual loader initialization/flush bodies verify headless no-write/no-flush and
invalid-extent refusal. The host clean() stub records calls only; ARM cache/MMIO
instructions and full loader_main are never executed. Physical mapping/cache
preconditions and DPU behavior remain unmeasured.
