// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Experimental source implementation of selected public XNU granule rules.
// Target AST layouts supply every bit offset/size. This is not an Apple oracle.
#ifndef LLVM_CLANG_AST_XNUTYPEMETADATA_H
#define LLVM_CLANG_AST_XNUTYPEMETADATA_H
#include "clang/AST/ASTContext.h"
#include "clang/AST/Attr.h"
#include "clang/AST/DeclCXX.h"
#include "clang/AST/RecordLayout.h"
#include "clang/Basic/TargetInfo.h"
#include "llvm/ADT/SmallVector.h"
#include <string>

namespace clang {
class XnuTypeMetadata {
  ASTContext &C;
  llvm::SmallVector<unsigned, 32> Granules;
  uint64_t TotalBits = 0;
  unsigned Depth = 0;

  bool mark(uint64_t Offset, uint64_t Bits, unsigned Encoding) {
    if (!Bits) return true;
    if (Offset > TotalBits || Bits > TotalBits - Offset) return false;
    for (uint64_t I = Offset / 64; I <= (Offset + Bits - 1) / 64; ++I)
      Granules[I] |= Encoding;
    return true;
  }

  static unsigned semantics(const Decl *D) {
    if (!D) return 0;
    unsigned Result = 0;
    for (const auto *A : D->specific_attrs<XnuUsageSemanticsAttr>())
      for (llvm::StringRef S : A->semantics()) {
        if (S == "pointer") Result |= 1;
        if (S == "data") Result |= 2;
      }
    return Result;
  }

  bool walk(QualType T, uint64_t Offset, unsigned Override = 0) {
    if (++Depth > 128) { --Depth; return false; }
    bool Result = walkImpl(T, Offset, Override);
    --Depth;
    return Result;
  }

  bool walkImpl(QualType T, uint64_t Offset, unsigned Override) {
    if (T->isDependentType() || T->isVariablyModifiedType() ||
        T->isFunctionType() || T->isVoidType()) return false;
    if (T->isIncompleteArrayType()) return true; // A flexible tail has no storage.
    if (T->isIncompleteType()) return false;
    if (Override) {
      if (!T->isScalarType()) return false; // Public scalar semantics only.
      return mark(Offset, C.getTypeSize(T), Override);
    }
    if (const auto *TT = dyn_cast<TypedefType>(T.getTypePtr())) {
      return walk(TT->desugar(), Offset, semantics(TT->getDecl()));
    }
    QualType Desugared = T.getSingleStepDesugaredType(C);
    if (Desugared != T) return walk(Desugared, Offset);
    if (T->isPointerType() || T->isBlockPointerType() || T->isObjCObjectPointerType())
      return mark(Offset, C.getTypeSize(T), 1);
    if (T->isReferenceType() || T->isMemberPointerType()) return false;
    if (T->isArithmeticType() || T->isEnumeralType())
      return mark(Offset, C.getTypeSize(T), 2);
    if (const auto *AT = C.getAsConstantArrayType(T)) {
      uint64_t Count = AT->getSize().getLimitedValue();
      uint64_t Stride = C.getTypeSize(AT->getElementType());
      if (Count > 131072 || (Stride && Count > TotalBits / Stride)) return false;
      for (uint64_t I = 0; I < Count; ++I)
        if (!walk(AT->getElementType(), Offset + I * Stride)) return false;
      return true;
    }
    if (const auto *RT = T->getAs<RecordType>()) {
      const RecordDecl *RD = RT->getDecl()->getDefinition();
      if (!RD) return false;
      const ASTRecordLayout &Layout = C.getASTRecordLayout(RD);
      if (const auto *CRD = dyn_cast<CXXRecordDecl>(RD)) {
        if (CRD->getNumVBases()) return false; // Complete-object vbase model pending.
        if (CRD->isDynamicClass() && !Layout.getPrimaryBase())
          if (!mark(Offset, C.getTargetInfo().getPointerWidth(LangAS::Default), 1))
            return false;
        for (const auto &Base : CRD->bases()) {
          const auto *BRD = Base.getType()->getAsCXXRecordDecl();
          if (!BRD || Base.isVirtual()) return false;
          uint64_t BaseOffset = C.toBits(Layout.getBaseClassOffset(BRD));
          if (!walk(Base.getType(), Offset + BaseOffset)) return false;
        }
      }
      unsigned Index = 0;
      for (const FieldDecl *F : RD->fields()) {
        uint64_t FieldOffset = Offset + Layout.getFieldOffset(Index++);
        if (F->isUnnamedBitfield()) continue;
        unsigned Override = semantics(F);
        if (F->isBitField()) {
          if (!mark(FieldOffset, F->getBitWidthValue(C), Override ? Override : 2))
            return false;
        } else if (!walk(F->getType(), FieldOffset, Override)) return false;
      }
      return true;
    }
    return false; // Unsupported categories fail; no blanket signature.
  }

public:
  explicit XnuTypeMetadata(ASTContext &Context) : C(Context) {}
  bool compute(QualType T, std::string &Signature, uint32_t &Summary) {
    const auto &Triple = C.getTargetInfo().getTriple();
    // Selected plain arm64 target only. PAC/arm64e is not inferred from it.
    if (Triple.getArch() != llvm::Triple::aarch64 || !Triple.isOSDarwin() ||
        Triple.isArm64e() || C.getCharWidth() != 8 || T->isIncompleteType() ||
        T->isDependentType() || T->isVariablyModifiedType() ||
        T->isFunctionType() || T->isReferenceType()) return false;
    TotalBits = C.getTypeSize(T);
    if (TotalBits > 8 * 1024 * 1024) return false;
    Granules.assign((TotalBits + 63) / 64, 0);
    if (!walk(T, 0)) return false;
    Signature.clear(); Summary = 0;
    for (unsigned G : Granules) {
      Signature.push_back("0123456789abcdef"[G]);
      Summary |= 1U << G;
    }
    return true;
  }
};
} // namespace clang
#endif
