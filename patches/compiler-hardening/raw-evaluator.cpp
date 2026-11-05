// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Directly exercise real Clang AST nodes normally lowered by Sema in source.
#include "clang/AST/ASTContext.h"
#include "clang/AST/Expr.h"
#include "clang/Basic/TargetInfo.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/CompilerInvocation.h"
#include <cstdio>
#include <string>

int main(int argc, char **argv) {
  if (argc != 2) return 64;
  std::string Mode(argv[1]);
  bool Signature = Mode.find("signature-") == 0;
  bool Pointer = Mode.find("pointer") != std::string::npos;
  bool Unsupported = Mode.find("reference") != std::string::npos;
  if (!Signature && Mode.find("summary-") != 0) return 65;
  clang::CompilerInstance CI;
  CI.createDiagnostics();
  CI.getLangOpts().CPlusPlus = true;
  CI.getLangOpts().CPlusPlus17 = true;
  auto TO = std::make_shared<clang::TargetOptions>();
  TO->Triple = "arm64-apple-ios16.5";
  CI.setTarget(clang::TargetInfo::CreateTargetInfo(CI.getDiagnostics(), TO));
  CI.createFileManager();
  CI.createSourceManager(CI.getFileManager());
  CI.createPreprocessor(clang::TU_Complete);
  CI.createASTContext();
  auto &C = CI.getASTContext();
  clang::QualType T = Pointer ? C.VoidPtrTy : C.UnsignedLongLongTy;
  if (Unsupported) T = C.getLValueReferenceType(T);
  auto *E = new(C) clang::UnaryExprOrTypeTraitExpr(
      Signature ? clang::UETT_XnuTypeSignature : clang::UETT_XnuTypeSummary,
      C.getTrivialTypeSourceInfo(T),
      Signature ? C.getPointerType(C.CharTy.withConst()) : C.UnsignedIntTy,
      clang::SourceLocation(), clang::SourceLocation());
  clang::Expr::EvalResult R;
  bool OK = E->EvaluateAsRValue(R, C);
  if (Unsupported) {
    std::printf("unsupported-reference evaluated=%d\n", OK);
    return OK ? 10 : 0;
  }
  if (!OK) { std::puts("evaluation-failed"); return 11; }
  if (Signature) {
    if (!R.Val.isLValue()) return 12;
    auto *SL = llvm::dyn_cast_or_null<clang::StringLiteral>(
        R.Val.getLValueBase().dyn_cast<const clang::Expr *>());
    if (!SL || !R.Val.getLValueOffset().isZero()) return 13;
    std::printf("signature=%s\n", SL->getString().str().c_str());
    return SL->getString() == (Pointer ? "1" : "2") ? 0 : 14;
  }
  if (!R.Val.isInt()) return 15;
  auto Actual = R.Val.getInt().getZExtValue();
  std::printf("summary=%llu; ordinary-sizeof=8\n", (unsigned long long)Actual);
  return Actual == (Pointer ? 2U : 4U) ? 0 : 16;
}
