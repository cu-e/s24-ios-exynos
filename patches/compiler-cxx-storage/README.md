# Selected Apple ARM64 C++ storage extension

Local experimental source code under Apache-2.0 WITH LLVM-exception.
The parent is the immutable VCOMP-002 helper in
artifacts/xnu-compiler-vectors/source-build-session1/helper-source, with all
qualified GNU void, atomic, vector, Parser, AST and mangling fixes retained.
The public compiler source base is apple-libtapi
fa9443738c1a18accef4244732ec6d6ee97a8133 (Clang17.0.6).

The patch adds pointer storage for actual reference fields and two scalar
ptrdiff_t words for member-function pointers, only under the selected AppleARM64
64-bit ABI. Root references and data-member pointers remain rejected.
Detailed source justification, validation and limits are in
docs/procedures/xnu-compiler-cxx-storage.md. This is an experimental public-source
allocator metadata model, without a private Apple compiler or SDK oracle.
