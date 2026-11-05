#!/usr/bin/env python3
"""Build and audit source-backed fixed arithmetic-vector XNU metadata."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys

from xnu_compiler_atomics import Atomics,ROOT,PROFILE,HARDEN,KERNEL,KOBJECT,NDK,registered,sha,dump
from xnu_macho_tools import macho

ATOMIC=ROOT/'artifacts/xnu-compiler-atomics/atomic-arrays-session1'
FIXTURES=ROOT/'fixtures/public/xnu-compiler-vectors'
PATCHES=ROOT/'patches/compiler-vectors'


class Vectors(Atomics):
    def __init__(self,args):
        self.args=args
        self.out=ROOT/'artifacts/xnu-compiler-vectors'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Use canonical fresh paths')
        self.out.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text())
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',
            recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),mode=args.mode,
            commands=[],checks=[],device_executed=False,full_kernel_qualified=False,apple_private_abi_qualified=False,kernel_cases=[])

    def inputs(self):
        super().inputs()
        for name in ['ATCOMP-004','ATCOMP-005','ATCOMP-006','ATCOMP-008','ATCOMP-009','ATCOMP-010',
            'KSETUP-001','KSETUP-004','KSETUP-007','KSETUP-008']:
            registered(name,self.ledger)
            e=next(e for e in self.ledger['experiments'] if e['id']==name)
            self.report['parents'][name]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.compiler=ATOMIC/'clang'
        component=json.loads((ROOT/'fixtures/public/xnu-compiler-atomics/qualified-component.json').read_text())
        if sha(self.compiler)!=component['compiler']['sha256']:raise ValueError('Atomic source compiler changed')
        for before,after in [(PROFILE/'libclangSema.a',ATOMIC/'libclangSema.a'),
            (PROFILE/'libclangParse.a',ATOMIC/'libclangParse.a'),(HARDEN/'libclangAST.a',ATOMIC/'libclangAST.a')]:
            self.link[self.link.index(str(before))]=str(after)
        for p in [*FIXTURES.glob('*.c'),*FIXTURES.glob('*.cpp')]:shutil.copyfile(p,self.out/'fixture-inputs'/p.name)
        self.report['fixture_files_sha256']={p.name:sha(p) for p in (self.out/'fixture-inputs').iterdir()}
        self.report['atomic_parent_compiler_sha256']=sha(self.compiler)

    def rebuild_vectors(self):
        relative=Path('src/clang/include/clang/AST/XnuTypeMetadata.h')
        root=self.out/'helper-source';helper=root/relative;helper.parent.mkdir(parents=True)
        shutil.copyfile(ATOMIC/'helper-source'/relative,helper)
        patch=PATCHES/'0001-fixed-arithmetic-vector-layout.patch'
        shutil.copyfile(patch,self.out/patch.name)
        self.must(['git','-C',root,'apply','--check',patch],'vector-patch-check')
        self.must(['git','-C',root,'apply',patch],'vector-patch-apply')
        archives={name:self.out/('libclang'+name+'.a') for name in ['Sema','AST','Parse']}
        for name,path in archives.items():shutil.copyfile(ATOMIC/path.name,path)
        self.report['compiled_consumers']=[]
        for library,name in [('Sema','SemaExpr.cpp'),('Sema','SemaExprCXX.cpp'),('AST','ExprConstant.cpp')]:
            rel=Path('src/clang/lib')/library/name
            previous=ATOMIC/'consumer-source'/rel
            source=self.out/'consumer-source'/rel;source.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(previous,source)
            recipe=self.must([shutil.which('ninja'),'-C',self.build,'-t','commands',
                'tools/clang/lib/'+library+'/CMakeFiles/obj.clang'+library+'.dir/'+name+'.o'],name+'-recipe')
            argv=shlex.split(recipe.splitlines()[-1])
            if sha(argv[0])!=self.host_sha or str(self.private/rel) not in argv:raise ValueError('Original compiler TU recipe changed')
            argv[argv.index(str(self.private/rel))]=str(source);argv[1:1]=['-I',str(root/'src/clang/include')]
            obj=self.out/(name+'.o')
            for flag,value in [('-o',obj),('-MF',obj.with_suffix('.d')),('-MT',obj)]:
                if flag in argv:argv[argv.index(flag)+1]=str(value)
            self.must(argv,name+'-compile',cwd=self.build,timeout=180)
            self.must([NDK/'llvm-ar','r',archives[library],obj],name+'-archive')
            self.must([NDK/'llvm-ar','p',archives[library],obj.name],name+'-member')
            if sha(self.out/(name+'-member.stdout.txt'))!=sha(obj):raise ValueError('Actual copied archive member mismatch')
            self.report['compiled_consumers'].append(dict(source=str(source.relative_to(ROOT)),source_sha256=sha(source),
                retained_parent=str(previous.relative_to(ROOT)),retained_parent_sha256=sha(previous),object_sha256=sha(obj)))
        for archive,member,original in [('Parse','ParseExpr.cpp.o',ATOMIC/'ParseExpr.cpp.o'),
            ('AST','ItaniumMangle.cpp.o',HARDEN/'ItaniumMangle.cpp.o')]:
            label='retained-'+member
            self.must([NDK/'llvm-ar','p',archives[archive],member],label)
            self.check(label,sha(self.out/(label+'.stdout.txt'))==sha(original),original=str(original.relative_to(ROOT)),sha256=sha(original))
        link=self.link.copy()
        for name,path in archives.items():link[link.index(str(ATOMIC/path.name))]=str(path)
        self.compiler=self.out/'clang';link[link.index('-o')+1]=str(self.compiler)
        self.must(link,'vector-compiler-link',cwd=self.build,timeout=180)
        self.link=link
        self.report.update(vector_patch_sha256=sha(patch),vector_helper_sha256=sha(helper),
            vector_relink_inputs_sha256={str((self.build/p).resolve()):sha(self.build/p) for p in link if p.endswith(('.a','.o')) and (self.build/p).is_file()})

    def vector_controls(self):
        source=self.out/'fixture-inputs/vector-layout.c'
        for label,compiler in [('independent19',NDK/'clang'),('source17',self.compiler)]:
            obj=self.out/(label+'-vector-layout.o')
            code,_,stderr=self.run([compiler,'-target','arm64-apple-ios16.5','-ffreestanding','-nostdinc','-std=gnu11','-c',source,'-o',obj],'vector-layout-'+label)
            self.check('vector-layout-'+label,code==0 and obj.is_file() and macho(obj)['filetype']==1,exit_code=code,diagnostic=stderr[-2500:])
        source=self.out/'fixture-inputs/vector-contract.cpp';obj=self.out/'vector-contract.o'
        code,_,stderr=self.run([*self.flags(),'-Werror=unknown-attributes','-c',source,'-o',obj],'vector-contract')
        self.check('vector-contract',code==0 and obj.is_file() and macho(obj)['filetype']==1,exit_code=code,diagnostic=stderr[-3500:])

    def vector_negatives(self):
        cases={
            'vector-annotated-lane':'typedef unsigned long long Address __attribute__((xnu_usage_semantics("pointer"))); typedef Address V __attribute__((ext_vector_type(2))); constexpr auto n=__builtin_xnu_type_summary(V);',
            'vector-field-annotation':'typedef unsigned long long V __attribute__((ext_vector_type(2))); struct X { V v __attribute__((xnu_usage_semantics("pointer"))); }; constexpr auto n=__builtin_xnu_type_summary(X);',
            'vector-typedef-annotation':'typedef unsigned long long V __attribute__((ext_vector_type(2),xnu_usage_semantics("data"))); constexpr auto n=__builtin_xnu_type_summary(V);',
            'vector-bool':'typedef bool V __attribute__((ext_vector_type(4))); constexpr auto n=__builtin_xnu_type_summary(V);',
            'vector-arm64e':'typedef unsigned long long V __attribute__((ext_vector_type(2))); constexpr auto n=__builtin_xnu_type_summary(V);',
            'vector-reference':'typedef unsigned long long V __attribute__((ext_vector_type(2))); struct X { V &v; }; constexpr auto n=__builtin_xnu_type_summary(X);',
            'vector-member-pointer':'struct X { int n; }; constexpr auto n=__builtin_xnu_type_summary(int X::*);',
            'vector-sizeless-sve':'constexpr auto n=__builtin_xnu_type_summary(__SVInt32_t);',
        }
        for name,text in cases.items():
            source=self.out/(name+'.cpp');source.write_text(text+'\n');flags=self.flags()
            if name.endswith('arm64e'):flags[flags.index('arm64-apple-ios16.5')]='arm64e-apple-ios16.5'
            if name.endswith('sve'):flags += ['-march=armv8-a+sve']
            code,_,stderr=self.run([*flags,'-fsyntax-only',source],name)
            self.check(name,code==1 and 'experimental XNU metadata does not support' in stderr,exit_code=code,diagnostic=stderr[-2300:])

    def status_case(self):
        parent=json.loads((ROOT/'artifacts/xnu-kernel-setup/full-profile-session2/report.json').read_text())
        row=next(r for r in parent['compile_results'] if r['id']=='osfmk/status.o')
        process=next(c for c in parent['commands'] if c['stdout'].endswith('/compile-osfmk-status.o.stdout.txt'))
        if sha(ROOT/row['source'])!=row['source_sha256'] or Path(process['argv'][0])!=ATOMIC/'clang':raise ValueError('Genuine selected status recipe changed')
        argv=process['argv'].copy();argv[0]=str(self.compiler)
        obj=self.out/'genuine-status.o';argv[argv.index('-o')+1]=str(obj);argv[argv.index('-MF')+1]=str(self.out/'genuine-status.d')
        code,_,stderr=self.run(argv,'genuine-status',cwd=Path(process['cwd']),timeout=120)
        self.check('genuine-status',code==0 and obj.is_file() and macho(obj)['filetype']==1,exit_code=code,diagnostic=stderr[-3500:])
        self.report['genuine_status']=dict(source=row['source'],source_sha256=row['source_sha256'],output=str(obj.relative_to(ROOT)) if obj.is_file() else None,output_sha256=sha(obj) if obj.is_file() else None)

    def reuse_compiler(self):
        if not self.args.compiler or not self.args.compiler_evidence:raise ValueError('Supply explicit recorded vector compiler')
        doc=registered(self.args.compiler_evidence,self.ledger)
        key=str(self.args.compiler.relative_to(ROOT))
        if sha(self.args.compiler)!=doc['sha256'][key]:raise ValueError('Recorded compiler changed')
        prefix=self.args.compiler.parent
        report_path=prefix/'report.json'
        if sha(report_path)!=doc['sha256'][str(report_path.relative_to(ROOT))]:raise ValueError('Actual source compiler report changed')
        parent=json.loads(report_path.read_text())
        if {Path(c['source']).name for c in parent.get('compiled_consumers',[])}!={'SemaExpr.cpp','SemaExprCXX.cpp','ExprConstant.cpp'}:
            raise ValueError('Source build must contain every actual helper consumer')
        helper=prefix/'helper-source/src/clang/include/clang/AST/XnuTypeMetadata.h'
        if sha(helper)!=parent['vector_helper_sha256']:raise ValueError('Actual vector helper changed')
        self.compiler=self.args.compiler
        for name in ['Sema','AST','Parse']:
            original=ATOMIC/('libclang'+name+'.a')
            self.link[self.link.index(str(original))]=str(prefix/original.name)
        e=next(e for e in self.ledger['experiments'] if e['id']==self.args.compiler_evidence)
        self.report['vector_source_parent']=dict(experiment=self.args.compiler_evidence,evidence=e['evidence'],sha256=e['evidence_sha256'],
            report=str(report_path.relative_to(ROOT)),report_sha256=sha(report_path),helper_sha256=sha(helper))

    def vector_pch(self):
        original_out=self.out
        source_snapshot=self.out/'fixture-inputs/vector-contract.cpp'
        self.out=self.out/'vector-pch';self.out.mkdir()
        start=len(self.report['checks'])
        previous_equality=self.report.get('atomic_pch_whole_object_equal')
        try:
            header=self.out/'vector-header.h';shutil.copyfile(source_snapshot,header)
            source=self.out/'vector-consumer.cpp'
            source.write_text('''static_assert(VectorMetadata<V64x3>::value==5);
struct ReloadedVector { V64x3 lanes; void *pointer; };
static_assert(sizeof(ReloadedVector)==48 && __builtin_offsetof(ReloadedVector,pointer)==32);
static_assert(__builtin_xnu_type_summary(ReloadedVector)==7);
static_assert(__builtin_xnu_type_signature(ReloadedVector)[3]=='0' && __builtin_xnu_type_signature(ReloadedVector)[4]=='1');
unsigned use_vector(V64x3 *p) { return vector_contract()+vector_symbol(p); }
''')
            pch=self.out/'vector.pch'
            code,_,stderr=self.run([*self.flags(),'-x','c++-header',header,'-o',pch],'vector-pch-create')
            self.check('vector-pch-create',code==0,exit_code=code,diagnostic=stderr[-2300:])
            if code:return
            objects=[]
            for label,include in [('textual',['-include',header]),('serialized',['-include-pch',pch])]:
                obj=self.out/(label+'.o')
                code,_,stderr=self.run([*self.flags(),*include,'-c',source,'-o',obj],'vector-pch-'+label)
                self.check('vector-pch-'+label,code==0 and obj.is_file() and macho(obj)['filetype']==1,exit_code=code,diagnostic=stderr[-2300:])
                if code==0:objects.append(obj)
            if len(objects)==2:
                same=objects[0].read_bytes()==objects[1].read_bytes()
                self.report['vector_pch_whole_object_equal']=same
                self.report['atomic_pch_whole_object_equal']=same
                self.pch_code_equivalence(objects[0],objects[1])
                names=self.must([NDK/'llvm-nm','--defined-only','--just-symbol-name',objects[1]],'vector-symbols')
                symbols=[n for n in names.splitlines() if n.startswith('__Z') and 'vector_symbol' in n]
                if len(symbols)!=1:raise ValueError('Expected one genuine dependent vector symbol')
                demangled=self.must([NDK/'llvm-cxxfilt',symbols[0][1:]],'vector-demangle')
                self.check('vector-dependent-vendor-expression','__builtin_xnu_type_summary' in demangled,demangled=demangled.strip(),symbol=symbols[0])
        finally:
            for c in self.report['checks'][start:]:c['name']=c['name'].replace('atomic-pch-','vector-pch-')
            self.out=original_out
            if previous_equality is not None:self.report['atomic_pch_whole_object_equal']=previous_equality
            else:self.report.pop('atomic_pch_whole_object_equal',None)

    def vector_raw(self):
        source=self.out/'fixture-inputs/raw-vector-evaluator.cpp';obj=self.out/'raw-vector-evaluator.o'
        includes=[self.private/'src/clang/include',self.build/'tools/clang/include',self.private/'src/llvm/include',self.build/'include']
        self.must([NDK/'clang++','-std=c++17','-fno-rtti','-D_GNU_SOURCE','-D__STDC_CONSTANT_MACROS',
            '-D__STDC_FORMAT_MACROS','-D__STDC_LIMIT_MACROS',*[a for p in includes for a in ['-I',p]],'-c',source,'-o',obj],'vector-raw-compile',timeout=180)
        link=[a for a in self.link if not a.endswith('.o')];link.insert(1,str(obj))
        exe=self.out/'raw-vector-evaluator';link[link.index('-o')+1]=str(exe)
        self.must(link,'vector-raw-link',cwd=self.build,timeout=180)
        for mode in ['summary-vec2','signature-vec2','summary-vec3','signature-vec3',
            'summary-neon-vec2','signature-neon-vec2',
            'reject-bool','reject-poly','reject-fixed-sve','reject-sizeless','reject-lanes','reject-reference']:
            code,stdout,stderr=self.run([exe,mode],'raw-'+mode)
            self.check('raw-'+mode,code==0,exit_code=code,observed=stdout.strip(),diagnostic=stderr[-1000:])

    def kernel_profile(self):
        path=ROOT/'artifacts/xnu-kernel-setup/full-profile-session2/report.json'
        parent=json.loads(path.read_text())
        rows=[*parent['compile_results'],parent['direct_version_object']]
        processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in parent['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if len(rows)!=len({r['id'] for r in rows}) or len(processes)!=len(rows):raise ValueError('Complete parent object/recipe mapping required')
        self.report['kernel_recipe_parent']=dict(evidence='KSETUP-004',report=str(path.relative_to(ROOT)),sha256=sha(path))
        self.report['kernel_profile']=[]
        def one(row):
            process=processes[row['id'].replace('/','-')]
            argv=process['argv'].copy()
            if Path(argv[0])!=ATOMIC/'clang' or sha(ROOT/row['source'])!=row['source_sha256']:
                raise ValueError('Actual source/compiler context changed')
            if '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or any('xnu_clang_compat.h' in a for a in argv):
                raise ValueError('Real type-checking profile was not preserved')
            output=self.out/'objects'/row['id'];output.parent.mkdir(parents=True,exist_ok=True)
            argv[0]=str(self.compiler);argv[argv.index('-o')+1]=str(output)
            argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
            code,_,stderr=self.run(argv,'kernel-'+row['id'].replace('/','-'),cwd=Path(process['cwd']),timeout=120)
            good=code==0 and output.is_file() and macho(output)['filetype']==1
            return dict(id=row['id'],source=row['source'],source_sha256=row['source_sha256'],parent_status=row['actual_arm64_object'],
                exit_code=code,actual_arm64_object=good,output=str(output.relative_to(ROOT)) if good else None,output_sha256=sha(output) if good else None,
                missing_headers=re.findall(r"fatal error: '([^']+)' file not found",stderr),errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$',stderr)[:12],diagnostic=stderr[-2500:])
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for index,result in enumerate(pool.map(one,rows),1):
                self.report['kernel_profile'].append(result)
                if index%40==0:dump(self.out/'progress.json',dict(completed=index,total=len(rows),actual_arm64=sum(r['actual_arm64_object'] for r in self.report['kernel_profile'])))
        values=self.report['kernel_profile']
        regressions=[r['id'] for r in values if r['parent_status'] and not r['actual_arm64_object']]
        self.check('all-current-parent-recipes-attempted',len(values)==len(rows),count=len(rows))
        self.check('no-compiler-crashes-timeouts',all(c['exit_code'] in [0,1] and not c['timed_out'] for c in self.report['commands']))
        self.check('all-prior-successes-retained',not regressions,regressions=regressions)
        status=next(r for r in values if r['id']=='osfmk/status.o')
        self.check('real-status-profile-object',status['actual_arm64_object'])
        self.report['kernel_profile_counts']=dict(attempted=len(values),actual_arm64=sum(r['actual_arm64_object'] for r in values),
            actual_component_arm64=sum(r['actual_arm64_object'] and not r['id'].startswith('kernel/') for r in values),
            prior_successes=sum(r['actual_arm64_object'] and r['parent_status'] for r in values),prior_object_regressions=regressions)
        dump(self.out/'kernel-profile.json',values)

    def audit_profile(self):
        if not self.args.profile_evidence:raise ValueError('Supply recorded full vector profile')
        doc=registered(self.args.profile_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one full profile report')
        report=json.loads(paths[0].read_text())
        path=ROOT/'artifacts/xnu-kernel-setup/full-profile-session2/report.json'
        previous=json.loads(path.read_text())
        parents={r['id']:r for r in [*previous['compile_results'],previous['direct_version_object']]}
        original_processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in previous['commands'] if Path(c['stdout']).name.startswith('compile-')}
        results={r['id']:r for r in report['kernel_profile']}
        processes={Path(c['stdout']).name.removeprefix('kernel-').removesuffix('.stdout.txt'):c
            for c in report['commands'] if Path(c['stdout']).name.startswith('kernel-')}
        if set(results)!=set(parents) or len(results)!=len(report['kernel_profile']) or len(processes)!=len(parents):
            raise ValueError('Complete source/process selection differs')
        objects=[];compiled=[];unresolved=[];inputs={};dependencies={};groups=Counter();headers=Counter()
        for identifier,row in results.items():
            before=parents[identifier];process=processes[identifier.replace('/','-')]
            original=original_processes[identifier.replace('/','-')]
            expected=original['argv'].copy();expected[0]=str(self.compiler)
            for flag in ['-o','-MF']:expected[expected.index(flag)+1]=process['argv'][process['argv'].index(flag)+1]
            if expected!=process['argv'] or process['cwd']!=original['cwd'] or row['source']!=before['source'] or sha(ROOT/row['source'])!=before['source_sha256'] or row['source_sha256']!=before['source_sha256']:
                raise ValueError('Full recipe/source changed beyond compiler/output transformation')
            if process['timed_out'] or process['exit_code']!=row['exit_code'] or row['exit_code'] not in [0,1]:
                raise ValueError('Actual compiler result/crash/timeout differs')
            text=(ROOT/process['stderr']).read_text(errors='replace')
            if not row['actual_arm64_object']:
                missing=re.findall(r"fatal error: '([^']+)' file not found",text)
                category='missing_header' if missing else 'unsupported_metadata' if 'error: experimental XNU metadata does not support' in text else 'other_compile_error'
                groups[category]+=1;headers.update(missing)
                unresolved.append(dict(id=identifier,category=category,missing_headers=missing,errors=row['errors']))
                continue
            obj=ROOT/row['output']
            if process['exit_code']!=0 or sha(obj)!=row['output_sha256'] or macho(obj)['filetype']!=1:raise ValueError('Actual ARM64 object changed')
            objects.append(obj)
            compiled.append({k:row[k] for k in ['id','source','source_sha256','output','output_sha256','parent_status']})
            dep=Path(process['argv'][process['argv'].index('-MF')+1])
            line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(Path(process['cwd'])/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            if (ROOT/row['source']).resolve() not in files:raise ValueError('Dependency source mismatch')
            names=[]
            for p in files:
                n=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                if n not in inputs:inputs[n]=sha(p)
                names.append(n)
            dependencies[identifier]=dict(depfile=str(dep.relative_to(ROOT)),depfile_sha256=sha(dep),inputs=sorted(set(names)))
        for row in self.object_report['inventory']:
            if row['id'] not in results:unresolved.append(dict(id=row['id'],category='missing_source_or_recipe',source=row['source']))
        rules=(KERNEL/'makedefs/MakeInc.kernel').read_text()
        top=re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_]*\.o):[ \t]*(\$\((?:SRCROOT|OBJPATH)\)/[^\s]+\.c)[ \t]*$',rules)
        if {n for n,s in top}!={'nonlto.o','version.o','lastkerneldataconst.o','lastkernelconstructor.o'}:
            raise ValueError('Original direct object declarations changed')
        for name,source in top:
            if name!='version.o':unresolved.append(dict(id='kernel/'+name,category='not_attempted_top_level',source_expression=source))
        text=self.must([NDK/'llvm-readobj','--file-headers',*objects],'audit-llvm-headers',timeout=120)
        self.check('independent-arm64-headers',text.count('Format: Mach-O arm64')==len(objects),count=len(objects))
        text=self.must([NDK/'llvm-nm','--defined-only','--format=posix',*objects],'audit-llvm-symbols',timeout=120)
        counts=Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+',text))
        self.check('actual-code-symbols',counts['T']+counts['t']>0,defined_symbol_types=dict(counts))
        regressions=[r['id'] for r in results.values() if r['parent_status'] and not r['actual_arm64_object']]
        self.check('all-prior-successes-retained',not regressions,regressions=regressions)
        self.check('real-status-profile-object',results['osfmk/status.o']['actual_arm64_object'])
        self.check('complete-known-direct-inventory',len(compiled)+len(unresolved)==len(self.object_report['inventory'])+len(top))
        self.report['coverage']=dict(selected_components=len(self.object_report['inventory']),attempted=len(results),actual_arm64=len(objects),
            actual_component_arm64=sum(not r['id'].startswith('kernel/') for r in compiled),known_direct_objects=982,
            known_direct_unresolved=len(unresolved),component_unresolved=sum(not r['id'].startswith('kernel/') for r in unresolved),
            additional_objects=sum(not r['parent_status'] for r in compiled),prior_successes=sum(r['parent_status'] for r in compiled),
            prior_object_regressions=regressions,failure_categories=dict(groups),missing_headers=dict(headers),unique_dependency_files=len(inputs),defined_symbol_types=dict(counts))
        self.report['profile_parent']=dict(experiment=self.args.profile_evidence,path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        for name,value in [('compiled-objects',compiled),('unresolved-objects',unresolved),('dependency-files',inputs),('object-dependencies',dependencies)]:
            dump(self.out/(name+'.json'),value)

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Source-backed fixed arithmetic-vector compiler/target object assessment; full kernel/Apple private ABI/native qualification remains false'
        if hasattr(self,'compiler') and self.compiler.is_file():self.report['compiler_sha256']=sha(self.compiler)
        dump(self.out/'report.json',self.report)
        files=[p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json']
        if hasattr(self,'compiler') and self.compiler.is_file():files.append(self.compiler)
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20],commands_scope='Representative exact commands; every execution retained in hashed report.json',
            actual_command_count=len(self.report['commands']),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in sorted(set(files))],sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(files))})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['baseline','build','qualify','kernel','audit'],required=True)
    p.add_argument('--compiler',type=Path)
    p.add_argument('--compiler-evidence')
    p.add_argument('--profile-evidence')
    p.add_argument('--jobs',type=int,default=2)
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Use fresh canonical run names')
    if not 1<=args.jobs<=3:p.error('Use1..3 bounded host jobs')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    build=Vectors(args)
    try:
        build.inputs()
        if args.mode=='build':build.rebuild_vectors()
        if args.mode in ['qualify','kernel','audit']:build.reuse_compiler()
        if args.mode=='kernel':
            build.kernel_profile()
            return build.finish()
        if args.mode=='audit':
            build.audit_profile()
            return build.finish()
        build.controls();build.vector_controls()
        if args.mode in ['build','qualify']:
            build.allocator();build.negatives();build.vector_negatives();build.pch();build.harness();build.status_case()
            build.vector_pch();build.vector_raw()
    except Exception as error:build.report['error']=str(error)
    return build.finish()

if __name__=='__main__':sys.exit(main())
