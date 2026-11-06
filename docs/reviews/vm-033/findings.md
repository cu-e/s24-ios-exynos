# REV-046 bounded independent verdict

Recommend accepting VM-033's read-only preflight for its two exact frozen
historical guest objects. Independent controls passed 35 checks in 2.066 seconds
with current-image VmHWM 25,300,992 bytes. No compiler, linker, archive utility,
section tool, generator, guest or broad source/dependency corpus was executed.
One resolver limitation is nonblocking for the current zero-addend witnesses.
Final source acceptance and review closure remain with INT002/root after the
required integration/common checks; original producer DO alone closes VM-033.

The exact original linear chain is 544ba087 -> 78cc7ad9 -> d9e236a4 -> 9248a9dc.
Final helper SHA256 is
`892db7f0f0764d2ab021a0468f498bd19a53455333e40259bd859007639b43a5`;
primary and supplemental fixture evidence match the independently assigned
`d1a03f41...` and `dedddab5...` full hashes in the procedure/evidence. The source
chain adds only its seven allocator preflight/helper/fixture/procedure files.

## Actual object facts

OSData is the existing 72,328-byte object SHA256
`0b7b02f0881ce38c08df27ebbb21dee03b251e1a5f8be85af3a18754d5276458`.
An independent raw Mach-O reader confirmed the single 192-byte
`__DATA_CONST,__kalloc_type` section, 8-byte alignment and exact flag 0x08000000.
Its six external, non-PC-relative ARM64_RELOC_UNSIGNED relocations have 64-bit
width and refer to defined real `__cstring` symbols. Their inline addends are
all zero. Relative offsets 16/80/144 resolve to `site.ExpansionData`, while
32/96/160 resolve to signature `12`. These agree byte-for-byte with the frozen
producer observations and the recorded payload hash.

kalloc is the existing 224,992-byte object SHA256
`006623101892d71322813c7f4c90bf24f09501ddf837ed60ae7a4bc3cf71d3c8`.
Its four undefined fixed/variable start/end symbols have 16 actual external
32-bit relocation references: four per boundary, with ARM64 GOT_LOAD_PAGE21 and
GOT_LOAD_PAGEOFF12 pairs. The independent address/type/width/PC-relative/target
tuples match all 16 exact supplement entries. kalloc consumes boundaries; this
does not assert that it emits an allocation record of its own.

Fourteen focused rejection cases passed using twelve bounded real-object
copies plus the existing wrong-compiler binary identity. They cover section,
live-support, relocation count/type/width/PC-relative flag/address, undefined and
out-of-range string targets, a damaged real ARM64 addend pair, missing consumer
boundary references, changed inline pointer addend and production object hash
admission. The actual historical stock-compiler metadata-builtin failure remains
hash-bound with target metadata flags and no output/fallback. It was not rerun.

## Resolver limitation for future reuse

The producer's `metadata()` string resolution computes the symbol-relative
offset without adding the inline pointer addend. An owned OSData copy with the
64-bit addend at metadata offset 16 changed from zero to one still produces the
unchanged `site.ExpansionData` string in that resolver. The independent decoder
includes the addend and rejects the changed expected string. The actual
production object hash precondition also rejects the changed copy.

All six real frozen pointers have zero addends, so this does not invalidate any
reported current witness string or allow the altered copy through the complete
preflight. Before generalizing the helper to other objects, the original author
should resolve inline addends or explicitly reject nonzero ones. This finding
was sent to INT002/root for relay to DO; no producer source was edited.

## Preserved limits and failure history

The initial producer run genuinely failed by treating ARM64_RELOC_ADDEND's
signed 24-bit addend as a local section index. Its failed capsule remains
unchanged; a damaged real following PAGE21/PAGEOFF12 pair is rejected by the
corrected parser. The public relocation definitions in the exact pinned
`EXTERNAL_HEADERS/mach-o/arm64/reloc.h` support the correction.

The pinned kalloc.h lines 1502-1508 request regular live-support placement and
initialize the name/signature pointers. loader.h lines 549-551 distinguish
unconditional no-dead-strip from live-support references. kalloc.c lines 433-445
declare all four boundaries, and the static-KC path starting at line 864 copies
the corresponding ranges. These are source declarations and object references,
with no startup execution measurement.

MakeInc.def lines 942-955 define dead stripping conditionally under USE_LTO=1;
the other branch clears those linker flags. The preflight's string-presence
check is evidence of that source rule, not a measurement of a final selected
LTO link. Reachability, record/string retention, section boundary extents,
allocator initialization and runtime consumption in a linked guest remain
unmeasured. No private ABI, complete kernel, new-profile object qualification,
QEMU console, PID1, stop or phone result is implied by this review.
