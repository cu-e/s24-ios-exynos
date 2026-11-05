# Experimental public XNU compiler metadata

Base tpoechtrager/apple-libtapi fa9443738c1a18accef4244732ec6d6ee97a8133,
containing LLVM/Clang17.0.6 source. Preserve each component's notices; the
actual clang/LICENSE.TXT is retained here as LICENSE.LLVM (Apache2 with LLVM
exceptions). The repository's older top-level NCSA notice is not substituted
for the current Clang files' license.

0001 adds real compiler tokens, scalar usage attributes and semantic lowering.
XnuTypeMetadata.h is the owned header installed only into a private source
copy. It queries ASTContext/ASTRecordLayout for actual target sizes, offsets,
bitfields, arrays and nonvirtual bases. Pointer/data bits are merged within
8-byte granules; the summary records which granule encodings occur. Typedef
and field semantics override scalar classification; same-layout types may be
compatible without sharing a C/C++ name. Unsupported types fail compilation.
No allocator callback, constant signature or broad summary replaces the real
mechanism. No Apple private implementation or test archive is imported.

This experiment targets plain arm64 Darwin only. PAC/arm64e, member/reference
types, virtual bases, scalable/VLA layouts, excessive depth and very large
types remain unsupported. These limits must remain explicit; the private
Apple compiler's complete encoding/diagnostics/interoperability are unknown.
Actual build/compile evidence is required before a component is usable.

0002 adds the parser entry points for type-only builtin operands. The first
compiler build intentionally retains the original 0001 source inventory;
0002 is not applied to that running build. A separate experiment must check
and apply it to a verified private source copy after the first build stops.
Existing AST/PCH files from another compiler are not qualification inputs.

0003-gnu-unevaluated-void-typeof.patch permits void typeof indirection only
in GNU unevaluated C++ contexts, matching the genuine selected IOLib/kalloc
pointer-compatibility use. An evaluated runtime dereference remains an error.
TYPECOMP-006 retained the actual13 interface failures;007/008 compile all17
after this patch with real type checks enabled. Positive/dependent void-type
controls and a separate evaluated negative control exercise both branches.

The exact current compiler bytes and bounded profile are published in
fixtures/public/xnu-compiler-types/qualified-component.json. AST constant
evaluation/mangling fallback paths and broader whole-kernel cases remain
KRN-006; this component pass is not full Apple compiler or native acceptance.
