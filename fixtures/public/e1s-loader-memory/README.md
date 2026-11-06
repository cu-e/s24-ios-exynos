# Actual E1S C memory-map controls

GPL-2.0-only project harness. `upstream.json` pins actual donor bodies and the
attributed patch; `controls.c` includes the exact extracted selection functions
and links the actual donor/patched `fdt.c`. No allocator algorithm is mirrored.

All DTBs and addresses here are host fixtures, not captured device memory maps
or measured safe RAM. The valid case has a 1GiB bank with two reserved256MiB
edges and expects the remaining512MiB gap; the capacity-boundary case preserves
92 static reservations. Header reservations count alongside reserved-memory.

Original mode reproduces six silent incorrect-map acceptances using bounded
valid structure: partial tuple, overflowing exclusion, capacity loss, excess
memory banks, overflowing memory bank and ignored header reservation map.
Patched mode checks35 results: valid gaps, malformed headers/blocks/strings/tags,
reservation truncation/capacity/overflow, unsupported dynamic/translated/nested
reservations, no-window refusal, auxiliary endpoint overflow, and empty-list
policy. Generic empty FDT reservations return0; E1S selection rejects that list.
Generated buffers have a trailing inaccessible host guard page. Invalid-map
results must leave selection outputs unchanged. This is source/host evidence;
S-Boot DTB backing and actual firmware carve-outs remain unmeasured.

The preparation checker emits commands but never starts compilers or controls.
Execution needs the separately registered STRMEM-001 experiment and exact root
small-run admission. No phone, guest, full loader link or kernel build.
