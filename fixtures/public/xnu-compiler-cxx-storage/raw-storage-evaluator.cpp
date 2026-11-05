// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Build actual reference/member-pointer AST nodes and invoke constant evaluation.
#include "clang/AST/ASTContext.h"
#include "clang/AST/DeclCXX.h"
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
  auto target=std::make_shared<clang::TargetOptions>();
  target->Triple="arm64-apple-ios16.5";
  if(mode=="reject-foreign-abi")ci.getLangOpts().CXXABI=clang::TargetCXXABI::GenericItanium;
  ci.setTarget(clang::TargetInfo::CreateTargetInfo(ci.getDiagnostics(),target));
  ci.createFileManager();ci.createSourceManager(ci.getFileManager());
  ci.createPreprocessor(clang::TU_Complete);ci.createASTContext();auto &c=ci.getASTContext();
  auto *service=clang::CXXRecordDecl::Create(c,clang::TTK_Struct,c.getTranslationUnitDecl(),{}, {},&c.Idents.get("Service"));
  service->startDefinition();service->completeDefinition();
  auto function=c.getFunctionType(c.IntTy,{},clang::FunctionProtoType::ExtProtoInfo());
  auto method=c.getMemberPointerType(function,c.getRecordType(service).getTypePtr());
  auto reference=c.getLValueReferenceType(c.CharTy);
  clang::QualType type=method;std::string expected="22";unsigned summary=4;
  if(mode.find("root-reference")!=std::string::npos)type=reference;
  else if(mode=="reject-data-member")type=c.getMemberPointerType(c.IntTy,c.getRecordType(service).getTypePtr());
  else if(mode.find("reference")!=std::string::npos || mode.find("trap")!=std::string::npos) {
    auto *record=clang::CXXRecordDecl::Create(c,clang::TTK_Struct,c.getTranslationUnitDecl(),{}, {},&c.Idents.get("Stored"));
    record->startDefinition();
    clang::QualType field=reference;
    if(mode.find("trap")!=std::string::npos)field=c.getPointerType(c.getRecordType(service));
    if(mode=="reject-function-reference")field=c.getLValueReferenceType(function);
    if(mode=="reject-address-reference")field=c.getLValueReferenceType(c.getAddrSpaceQualType(c.CharTy,clang::LangAS::opencl_global));
    auto *f=clang::FieldDecl::Create(c,record,{}, {},&c.Idents.get("value"),field,nullptr,nullptr,false,clang::ICIS_NoInit);
    record->addDecl(f);expected="1";summary=2;
    if(mode.find("trap")!=std::string::npos) {
      record->addDecl(clang::FieldDecl::Create(c,record,{}, {},&c.Idents.get("method"),method,nullptr,nullptr,false,clang::ICIS_NoInit));
      expected="122";summary=6;
    }
    record->completeDefinition();type=c.getRecordType(record);
  }
  auto *expr=new(c) clang::UnaryExprOrTypeTraitExpr(
      signature?clang::UETT_XnuTypeSignature:clang::UETT_XnuTypeSummary,c.getTrivialTypeSourceInfo(type),
      signature?c.getPointerType(c.CharTy.withConst()):c.UnsignedIntTy,{},{});
  clang::Expr::EvalResult result;bool ok=expr->EvaluateAsRValue(result,c);
  if(reject){std::printf("%s evaluated=%d\n",mode.c_str(),ok);return ok?10:0;}
  if(!ok)return 11;
  if(signature){
    if(!result.Val.isLValue())return 12;
    auto *s=llvm::dyn_cast_or_null<clang::StringLiteral>(result.Val.getLValueBase().dyn_cast<const clang::Expr *>());
    if(!s || !result.Val.getLValueOffset().isZero())return 13;
    std::printf("signature=%s\n",s->getString().str().c_str());return s->getString()==expected?0:14;
  }
  if(!result.Val.isInt())return 15;
  auto actual=result.Val.getInt().getZExtValue();
  std::printf("summary=%llu; AST-storage=%llu\n",(unsigned long long)actual,(unsigned long long)c.getTypeSizeInChars(type).getQuantity());
  return actual==summary?0:16;
}
