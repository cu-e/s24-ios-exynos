// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Real source Clang AST evaluation without the ordinary Sema lowering shortcut.
#include "clang/AST/ASTContext.h"
#include "clang/AST/Expr.h"
#include "clang/Basic/TargetInfo.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/CompilerInvocation.h"
#include <cstdio>
#include <string>
int main(int argc,char **argv) {
  if(argc!=2)return 64;
  std::string mode(argv[1]);
  bool signature=mode.find("signature-")==0;
  bool reject=mode.find("reject-")==0;
  clang::CompilerInstance ci;ci.createDiagnostics();
  ci.getLangOpts().CPlusPlus=true;ci.getLangOpts().CPlusPlus17=true;
  auto target=std::make_shared<clang::TargetOptions>();target->Triple="arm64-apple-ios16.5";
  ci.setTarget(clang::TargetInfo::CreateTargetInfo(ci.getDiagnostics(),target));
  ci.createFileManager();ci.createSourceManager(ci.getFileManager());
  ci.createPreprocessor(clang::TU_Complete);ci.createASTContext();
  auto &c=ci.getASTContext();
  unsigned lanes=mode.find("vec2")!=std::string::npos?2:3;
  clang::QualType type=c.getExtVectorType(c.UnsignedLongLongTy,lanes);
  if(mode.find("neon")!=std::string::npos)type=c.getVectorType(c.UnsignedLongLongTy,lanes,clang::VectorType::NeonVector);
  if(mode=="reject-bool")type=c.getExtVectorType(c.BoolTy,4);
  if(mode=="reject-poly")type=c.getVectorType(c.UnsignedCharTy,16,clang::VectorType::NeonPolyVector);
  if(mode=="reject-fixed-sve")type=c.getVectorType(c.UnsignedIntTy,4,clang::VectorType::SveFixedLengthDataVector);
  if(mode=="reject-sizeless")type=c.SveInt32Ty;
  if(mode=="reject-lanes")type=c.getExtVectorType(c.UnsignedCharTy,131073);
  if(mode=="reject-reference")type=c.getLValueReferenceType(type);
  auto *expr=new(c) clang::UnaryExprOrTypeTraitExpr(
      signature?clang::UETT_XnuTypeSignature:clang::UETT_XnuTypeSummary,c.getTrivialTypeSourceInfo(type),
      signature?c.getPointerType(c.CharTy.withConst()):c.UnsignedIntTy,
      clang::SourceLocation(),clang::SourceLocation());
  clang::Expr::EvalResult result;bool ok=expr->EvaluateAsRValue(result,c);
  if(reject){std::printf("%s evaluated=%d\n",mode.c_str(),ok);return ok?10:0;}
  if(!ok)return 11;
  if(signature){
    if(!result.Val.isLValue())return 12;
    auto *s=llvm::dyn_cast_or_null<clang::StringLiteral>(result.Val.getLValueBase().dyn_cast<const clang::Expr *>());
    if(!s || !result.Val.getLValueOffset().isZero())return 13;
    std::printf("signature=%s\n",s->getString().str().c_str());
    return s->getString()==(lanes==2?"22":"2220")?0:14;
  }
  if(!result.Val.isInt())return 15;
  unsigned long long actual=result.Val.getInt().getZExtValue();
  std::printf("summary=%llu; actual-sizeof=%llu\n",actual,(unsigned long long)c.getTypeSizeInChars(type).getQuantity());
  return actual==(lanes==2?4U:5U)?0:16;
}
