# Clang17 XNU AST hardening

Base: tpoechtrager/apple-libtapi
fa9443738c1a18accef4244732ec6d6ee97a8133, LLVM/Clang17.0.6, with the
private-source patches/header described in ../compiler-types/README.md.
The patch here changes only ExprConstant.cpp and ItaniumMangle.cpp, whose
original bytes are bound by the TYPECOMP-002 complete source witness.
Preserve the component's Apache2 with LLVM exceptions license (LICENSE.LLVM)
and original per-file notices. No Apple private compiler code is used.

0001-evaluate-and-mangle-xnu-traits.patch computes raw summary nodes with the
same real target-layout metadata analysis as Sema. Pointer evaluation of raw
signature nodes creates an AST-owned string literal and a proper array-element
lvalue. Unsupported types fail evaluation; signature never becomes sizeof.

The three XNU traits use the public Itanium vendor expression grammar with
their full builtin spellings and actual type arguments. Existing unsupported
type traits retain a diagnostic. This is an experimental ABI: readable,
distinct symbols and separate translation-unit agreement are measured, but
Apple's exact private builtin encoding and external binary interoperability
remain unknown. Do not export these objects as Apple-ABI-qualified outputs.

raw-evaluator.cpp is a native host compiler-API harness. It creates actual
Clang17 nodes that normal nondependent source expressions usually lower in
Sema. The original compiler traps on raw summary nodes and fails to evaluate
signature nodes; the new source-built AST library passes pointer/data and
unsupported-reference cases. This does not run ARM code.

See ../../docs/procedures/xnu-compiler-hardening.md for preserved failures,
incremental archive/member verification, PCH controls and actual kernel-unit
results. Original source/build prefixes and compiler binaries stay unchanged.
