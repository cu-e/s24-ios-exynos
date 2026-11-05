# Atomic metadata compiler patches

These project-authored changes extend the existing experimental helper and
Parser ports in `patches/compiler-types` and `patches/compiler-hardening`.
Upstream LLVM/Clang17.0.6 comes from `tpoechtrager/apple-libtapi` at
`fa9443738c1a18accef4244732ec6d6ee97a8133`. Preserve actual
`src/clang/LICENSE.TXT`, `src/llvm/LICENSE.TXT` and all per-file notices.
`LICENSE.LLVM` here contains the component Apache2.0 license with LLVM
exceptions. Separate Apple TAPI/top-level historical notices remain distinct.

Apply 0001 to the recorded experimental `XnuTypeMetadata.h`, then 0003 to that
result. Apply 0002 to qualified TYPECOMP-008 type-only `ParseExpr.cpp`.
The runner copies exact parents and verifies patch contexts.

- `0001-target-atomic-value-storage.patch`: unwrap actual AtomicType values,
  retain target storage/padding checks and scalar annotation precedence.
- `0002-builtin-postfix-expression.patch`: follow the ordinary postfix parser
  after custom summary/signature operands, permitting direct subscripts.
- `0003-scalar-array-usage-semantics.patch`: propagate explicit scalar field
  annotations to constant-array elements, as used in real ARM lock records.

ASTContext/CodeGenTypes supply target atomic sizes and value placement.
Selected public XNU allocator/lock source supplies usage contracts. There is no
private Apple compiler implementation/oracle here. Rebuild every actual helper
consumer and the Parser in isolated paths before qualifying a compiler binary.

See `docs/procedures/xnu-compiler-atomics.md` and ATCOMP-001 through010 for
failed baselines, archive/object witnesses, controls and limits. Keep failed
evidence unchanged. Built binaries/archives stay outside Git.
