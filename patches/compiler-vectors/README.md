# Fixed arithmetic-vector metadata attribution

This project-authored patch applies to the exact ATCOMP-004 experimental
`src/clang/include/clang/AST/XnuTypeMetadata.h`. It preserves the atomic/array,
Parser, constant evaluator and vendor-expression mangling parents.
Upstream LLVM/Clang17.0.6 comes from `tpoechtrager/apple-libtapi` at
`fa9443738c1a18accef4244732ec6d6ee97a8133`.

Preserve actual Clang/LLVM component Apache2.0 licenses with LLVM exceptions,
all per-file notices and separate Apple TAPI/top-level notices. `LICENSE.LLVM`
here is the component license; the helper and raw harness retain their SPDX
notices. Generated compiler binaries/archives stay in ignored local artifacts.

The patch reads real fixed arithmetic lane count/size and target storage from
ASTContext, marks value bits as data, and leaves extra storage as padding.
GenericVector and NeonVector are supported. Predicate/boolean, polynomial,
SVE/RVV and explicit vector/lane usage annotations remain rejected. Sizeless
types are rejected before querying a size. Reference/member-pointer/PAC and
existing layout/depth/element limits remain intact.

Public target AST/CodeGen source supplies storage/lane behavior. Selected XNU
allocator source supplies granule contracts. This is an experimental public
source implementation, without a matching Apple compiler/private ABI oracle.
Rebuild all three actual helper consumers and verify copied archive members.
See docs/procedures/xnu-compiler-vectors.md and VCOMP-001 through009.
