#!/usr/bin/env python3
"""Bounded source-backed Apple ARM64 reference-field/method-pointer metadata."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import struct
import subprocess
import sys
from xnu_kernel_declarations import Declarations, PORTS
from xnu_kernel_firehose_headers import COMPILER
from xnu_compiler_vectors import ATOMIC
from xnu_compiler_atomics import ROOT, KERNEL, NDK, HARDEN, Atomics, registered, sha, dump
from xnu_kernel_syscalls import ObjectData
from xnu_macho_tools import macho
from xnu_compiler_types import allocator_metadata

FIXTURES=ROOT/'fixtures/public/xnu-compiler-cxx-storage'
PATCHES=ROOT/'patches/compiler-cxx-storage'
PARENT=ROOT/'artifacts/xnu-kernel-declarations/full-profile-session2'
CONSUMERS=['iokit/MiniIOSurface.cpo','iokit/IONVRAM.cpo']
PUBLIC=ROOT/'references/xnu-tapi'
REVISION='fa9443738c1a18accef4244732ec6d6ee97a8133'

class Storage(Declarations):
    def __init__(self,args):
        self.args=args
        self.out=ROOT/'artifacts/xnu-compiler-cxx-storage'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Canonical fresh run required')
        self.out.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text())
        self.ports={}
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',
            recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            mode=args.mode,commands=[],checks=[],kernel_cases=[],device_executed=False,
            sdk_used=False,full_kernel_qualified=False,full_crypto_qualified=False,
            apple_private_abi_qualified=False,native_device_qualified=False)

    def inputs(self):
        super().inputs()
        for name in ['KDECL-004','KDECL-005','KDECL-007','KDECL-008','KDECL-009']:
            registered(name,self.ledger)
            e=next(e for e in self.ledger['experiments'] if e['id']==name)
            self.report['parents'][name]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.reuse_ports()
        self.original=json.loads((PARENT/'report.json').read_text())
        self.rows={r['id']:r for r in self.original['compile_results']}
        self.recipes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in self.original['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if len(self.rows)!=962 or len(self.recipes)!=962 or sum(r['actual_arm64_object'] for r in self.rows.values())!=960:
            raise ValueError('Require actual complete 962-recipe/960-object parent')
        self.report['recipe_parent']=dict(experiment='KDECL-008',report=str((PARENT/'report.json').relative_to(ROOT)),sha256=sha(PARENT/'report.json'))
        self.compiler=COMPILER
        names=['src/clang/lib/AST/ASTContext.cpp','src/clang/lib/AST/ItaniumCXXABI.cpp',
            'src/clang/lib/CodeGen/CodeGenTypes.cpp','src/clang/lib/CodeGen/CGRecordLayoutBuilder.cpp',
            'src/clang/lib/CodeGen/ItaniumCXXABI.cpp','src/clang/lib/Basic/Targets/AArch64.cpp',
            'src/clang/include/clang/Basic/TargetCXXABI.h']
        sources={}
        for i,name in enumerate(names):
            self.must(['git','-C',PUBLIC,'show',REVISION+':'+name],'storage-public-blob-'+str(i))
            if sha(self.out/('storage-public-blob-'+str(i)+'.stdout.txt'))!=sha(self.private/name):
                raise ValueError('Actual public C++ ABI source mismatch: '+name)
            sources[str((self.private/name).relative_to(ROOT))]=sha(self.private/name)
        for name in ['osfmk/kern/kalloc.h','iokit/IOKit/IOUserClient.h',
            'iokit/Kernel/IONVRAMCHRPHandler.cpp','iokit/Kernel/IONVRAMV3Handler.cpp']:
            sources[str((KERNEL/name).relative_to(ROOT))]=sha(KERNEL/name)
        self.report['storage_rule_inputs']=sources
        for p in FIXTURES.iterdir():
            if p.suffix in {'.cpp','.h'}:shutil.copyfile(p,self.out/'fixture-inputs'/p.name)
        self.report['fixture_files_sha256']={p.name:sha(p) for p in (self.out/'fixture-inputs').iterdir()}

    def command(self,row,output,source=None,header=True):
        argv,cwd,selected=super().command(row,output,source,header)
        argv[0]=str(self.compiler)
        return argv,cwd,selected

    def compile_rows(self,identifiers):
        super().compile_rows(identifiers)
        for check in self.report['checks']:check['name']=check['name'].replace('all-prior958','all-prior960')
        if self.args.mode=='kernel':
            rows={r['id']:r for r in self.report['compile_results']}
            self.check('both-genuine-cxx-storage-consumers',all(rows[n]['actual_arm64_object'] for n in CONSUMERS))

    def reuse_storage(self):
        if not self.args.storage_evidence:raise ValueError('Explicit recorded storage compiler required')
        doc=registered(self.args.storage_evidence,self.ledger)
        reports=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome']!='pass' or len(reports)!=1:raise ValueError('One passing source compiler build required')
        parent=json.loads(reports[0].read_text());prefix=reports[0].parent
        if {Path(c['source']).name for c in parent.get('compiled_consumers',[])}!={'SemaExpr.cpp','SemaExprCXX.cpp','ExprConstant.cpp'}:
            raise ValueError('Every actual helper consumer required')
        helper=prefix/'helper-source/src/clang/include/clang/AST/XnuTypeMetadata.h'
        if sha(helper)!=parent['storage_helper_sha256']:raise ValueError('Actual helper changed')
        self.compiler=prefix/'clang'
        if sha(self.compiler)!=parent['compiler_sha256']:raise ValueError('Actual source compiler changed')
        for name in ['Sema','AST','Parse']:
            old=COMPILER.parent/('libclang'+name+'.a');self.link[self.link.index(str(old))]=str(prefix/old.name)
        self.report['storage_source_parent']=dict(experiment=self.args.storage_evidence,
            report=str(reports[0].relative_to(ROOT)),report_sha256=sha(reports[0]),helper_sha256=sha(helper))

    def rebuild_storage(self):
        relative=Path('src/clang/include/clang/AST/XnuTypeMetadata.h')
        root=self.out/'helper-source';helper=root/relative;helper.parent.mkdir(parents=True)
        shutil.copyfile(COMPILER.parent/'helper-source'/relative,helper)
        patch=PATCHES/'0001-selected-apple-arm64-cxx-storage.patch'
        shutil.copyfile(patch,self.out/patch.name)
        self.must(['git','-C',root,'apply','--check',patch],'storage-patch-check')
        self.must(['git','-C',root,'apply',patch],'storage-patch-apply')
        archives={name:self.out/('libclang'+name+'.a') for name in ['Sema','AST','Parse']}
        for name,path in archives.items():shutil.copyfile(COMPILER.parent/path.name,path)
        self.report['compiled_consumers']=[]
        for library,name in [('Sema','SemaExpr.cpp'),('Sema','SemaExprCXX.cpp'),('AST','ExprConstant.cpp')]:
            rel=Path('src/clang/lib')/library/name
            previous=COMPILER.parent/'consumer-source'/rel
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
        for name,path in archives.items():link[link.index(str(COMPILER.parent/path.name))]=str(path)
        self.compiler=self.out/'clang';link[link.index('-o')+1]=str(self.compiler)
        self.must(link,'storage-compiler-link',cwd=self.build,timeout=180)
        self.link=link
        self.report.update(storage_patch_sha256=sha(patch),storage_helper_sha256=sha(helper),
            storage_relink_inputs_sha256={str((self.build/p).resolve()):sha(self.build/p) for p in link if p.endswith(('.a','.o')) and (self.build/p).is_file()})

    def audit_profile(self):
        if not self.args.profile_evidence:
            raise ValueError('Supply recorded full profile evidence')
        doc = registered(self.args.profile_evidence, self.ledger)
        paths = [ROOT / p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome'] != 'pass' or len(paths) != 1:
            raise ValueError('Require one passing complete selected profile')
        profile = json.loads(paths[0].read_text())
        if profile['source_ports'] != self.ports or profile['compiler_sha256'] != sha(self.compiler) or profile['resource_bundle'] != self.report['resource_bundle']:
            raise ValueError('Exact source ports/compiler/resources must agree')
        rows = {r['id']:r for r in profile['compile_results']}
        commands = {Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in profile['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if set(rows) != set(self.rows) or len(rows) != 962 or len(commands) != 962:
            raise ValueError('Complete actual recipe inventory required')
        compiled, unresolved, objects, inputs, dependencies = [], [], [], {}, {}
        groups, headers = Counter(), Counter()
        for identifier, row in rows.items():
            before = self.rows[identifier]; process = commands[identifier.replace('/', '-')]
            output = Path(process['argv'][process['argv'].index('-o') + 1])
            expected, cwd, source = self.command(before, output)
            if process['argv'] != expected or process['cwd'] != str(cwd) or row['source'] != str(source.relative_to(ROOT)) or sha(source) != row['source_sha256'] or row['original_source'] != before['source'] or row['original_source_sha256'] != before['source_sha256']:
                raise ValueError('Actual source/full recipe changed beyond declared source ports and outputs')
            if process['timed_out'] or process['exit_code'] != row['exit_code'] or row['exit_code'] not in [0, 1]:
                raise ValueError('Actual exit/crash/timeout mismatch')
            if not row['actual_arm64_object']:
                text = (ROOT / process['stderr']).read_text(errors='replace')
                missing = re.findall(r"fatal error: '([^']+)' file not found", text)
                category = 'missing_header' if missing else 'unsupported_metadata' if 'error: experimental XNU metadata does not support' in text else 'other_compile_error'
                groups[category] += 1; headers.update(missing)
                unresolved.append(dict(id=identifier, category=category, missing_headers=missing, errors=row['errors']))
                continue
            obj = ROOT / row['output']
            if process['exit_code'] != 0 or sha(obj) != row['output_sha256'] or macho(obj)['filetype'] != 1:
                raise ValueError('Actual ARM64 output differs')
            objects.append(obj)
            compiled.append({k:row[k] for k in ['id', 'source', 'source_sha256', 'original_source', 'original_source_sha256', 'output', 'output_sha256', 'parent_status']})
            dep = Path(process['argv'][process['argv'].index('-MF') + 1])
            line = dep.read_text().replace('\\\n', ' ').splitlines()[0]
            files = [(cwd / p).resolve() for p in shlex.split(line.split(':', 1)[1])]
            if source.resolve() not in files:
                raise ValueError('Actual source missing from dependency graph')
            names = []
            for path in files:
                name = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
                if name not in inputs: inputs[name] = sha(path)
                names.append(name)
            dependencies[identifier] = dict(depfile=str(dep.relative_to(ROOT)), depfile_sha256=sha(dep), inputs=sorted(set(names)))
        for row in self.object_report['inventory']:
            if row['id'] not in rows:
                unresolved.append(dict(id=row['id'], category='missing_source_or_recipe', source=row['source']))
        rules = (KERNEL / 'makedefs/MakeInc.kernel').read_text()
        top = re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_]*\.o):[ \t]*(\$\((?:SRCROOT|OBJPATH)\)/[^\s]+\.c)[ \t]*$', rules)
        if {n for n, s in top} != {'version.o', 'nonlto.o', 'lastkerneldataconst.o', 'lastkernelconstructor.o'}:
            raise ValueError('Known direct source declarations changed')
        unresolved.extend(dict(id='kernel/' + n, category='not_attempted_top_level', source_expression=s) for n, s in top if n != 'version.o')
        text = self.must([NDK / 'llvm-readobj', '--file-headers', *objects], 'audit-llvm-headers', timeout=120)
        self.check('independent-arm64-headers', text.count('Format: Mach-O arm64') == len(objects), count=len(objects))
        text = self.must([NDK / 'llvm-nm', '--defined-only', '--format=posix', *objects], 'audit-llvm-symbols', timeout=120)
        symbols = Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+', text))
        self.check('actual-code-symbols', symbols['T'] + symbols['t'] > 0, defined_symbol_types=dict(symbols))
        regressions = [r['id'] for r in rows.values() if r['parent_status'] and not r['actual_arm64_object']]
        self.check('all-prior960-retained', not regressions, regressions=regressions)
        self.check('both-genuine-source-ports', all(rows[n]['actual_arm64_object'] for n in PORTS))
        self.check('complete982-known-direct-inventory', len(compiled) + len(unresolved) == len(self.object_report['inventory']) + len(top) == 982)
        header = self.report['quoted_include_copy']
        self.check('actual-quoted-header-copy', header['copy'] in dependencies['osfmk/mc_provider.o']['inputs'] and sha(ROOT / header['copy']) == sha(ROOT / header['source']) == header['source_sha256'])
        self.check('opaque-mach-bsd-bridge-preserved', not any(n.endswith('/sys/proc.h') for n in dependencies['osfmk/user_exception_trace.o']['inputs']) and 'extern int proc_pid(struct proc *);' in (ROOT / self.ports['osfmk/user_exception_trace.o']['source']).read_text())
        self.report['coverage'] = dict(selected_components=len(self.object_report['inventory']), attempted=len(rows),
            actual_arm64=len(objects), actual_component_arm64=sum(not r['id'].startswith('kernel/') for r in compiled),
            known_direct_objects=982, known_direct_unresolved=len(unresolved), component_unresolved=sum(not r['id'].startswith('kernel/') for r in unresolved),
            additional_objects=sum(not r['parent_status'] for r in compiled), prior_successes=sum(r['parent_status'] for r in compiled),
            prior_object_regressions=regressions, failure_categories=dict(groups), missing_headers=dict(headers),
            unique_dependency_files=len(inputs), defined_symbol_types=dict(symbols))
        self.report['profile_parent'] = dict(experiment=self.args.profile_evidence, report=str(paths[0].relative_to(ROOT)), sha256=sha(paths[0]))
        for name, value in [('compiled-objects', compiled), ('unresolved-objects', unresolved), ('dependency-files', inputs), ('object-dependencies', dependencies)]:
            dump(self.out / (name + '.json'), value)

    def representations(self):
        source=self.out/'fixture-inputs/storage-layout.cpp'
        expected=(1,4,16,8,8,16,8,24,8,8,8,9,1)
        observed={}
        for label,compiler in [('independent19',NDK/'clang++'),('source17',self.compiler)]:
            obj=self.out/(label+'-storage-layout.o')
            argv=[compiler,'-target','arm64-apple-ios16.5','-ffreestanding','-nostdinc','-std=gnu++17','-Wno-invalid-offset-of','-c',source,'-o',obj]
            self.must(argv,'storage-layout-'+label)
            data=ObjectData(obj);values=data.value('_storage_layout','<13Q')
            self.check('independent-storage-layout-'+label,values==expected,observed=values)
            null=data.value('_null_method','<2q');direct=data.value('_direct_method','<2q')
            virtual=data.value('_virtual_method','<2q');adjusted=data.value('_adjusted_method','<2q')
            self.check('arm-method-representation-'+label,null==(0,0) and direct==(0,0) and virtual==(0,1) and adjusted==(0,8),
                null=null,direct=direct,virtual=virtual,adjusted=adjusted)
            relocs=[data.relocation('_direct_method',0)['name'],data.relocation('_adjusted_method',0)['name']]
            self.check('actual-method-code-relocations-'+label,relocs==['__ZN7Service4trapEv','__ZN5Right6adjustEv'],relocations=relocs)
            ir=self.out/(label+'-storage.ll');args=argv.copy();args.remove('-c');args+=['-S','-emit-llvm'];args[args.index('-o')+1]=str(ir)
            self.must(args,'storage-ir-'+label)
            text=ir.read_text()
            self.check('method-integer-pair-and-reference-load-'+label,
                bool(re.search(r'@direct_method =.*\{ i64, i64 \}.*ptrtoint',text)) and
                bool(re.search(r'(?s)define[^\n]*@reference_address\(.*?load ptr',text)))
            observed[label]=dict(layout=values,null=null,direct=direct,virtual=virtual,adjusted=adjusted,relocations=relocs)
        self.check('independent-method-storage-agreement',observed['independent19']==observed['source17'])
        self.report['representations']=observed

    def storage_contract(self,baseline=False):
        source=self.out/'fixture-inputs/storage-contract.cpp';obj=self.out/'storage-contract.o'
        code,_,stderr=self.run([*self.flags(),'-Werror=unknown-attributes','-Wno-invalid-offset-of','-c',source,'-o',obj],'storage-contract')
        self.check('retained-parent-rejects-new-storage' if baseline else 'actual-storage-metadata',
            code==1 and 'experimental XNU metadata does not support' in stderr if baseline else code==0 and obj.is_file() and macho(obj)['filetype']==1,
            exit_code=code,diagnostic=stderr[-3500:])

    def baseline(self):
        self.representations();self.storage_contract(baseline=True)
        self.compile_rows(CONSUMERS)
        # The genuine baseline is expected to reject these types.
        for check in self.report['checks']:
            if check['name'].startswith('actual-iokit/'):
                row=next(r for r in self.report['compile_results'] if 'actual-'+r['id']==check['name'])
                check['name']='baseline-reject-'+row['id']
                check['pass_check']=row['exit_code']==1 and bool(row['errors']) and all('experimental XNU metadata does not support' in e for e in row['errors'])

    def storage_negatives(self):
        cases={
          'root-reference':'constexpr auto x=__builtin_xnu_type_summary(int&);',
          'data-member':'struct X { int n; }; constexpr auto x=__builtin_xnu_type_summary(int X::*);',
          'function-reference':'struct X { int (&r)(); }; constexpr auto x=__builtin_xnu_type_summary(X);',
          'annotated-reference-field':'struct X { int &r __attribute__((xnu_usage_semantics("data"))); }; constexpr auto x=__builtin_xnu_type_summary(X);',
          'annotated-reference-alias':'typedef int &R __attribute__((xnu_usage_semantics("pointer"))); struct X { R r; }; constexpr auto x=__builtin_xnu_type_summary(X);',
          'annotated-method':'struct X {}; typedef int (X::*M)() __attribute__((xnu_usage_semantics("data"))); constexpr auto x=__builtin_xnu_type_summary(M);',
          'virtual-base':'struct X { int &r; }; struct Y: virtual X {}; constexpr auto x=__builtin_xnu_type_summary(Y);',
          'arm64e-reference':'struct X { int &r; }; constexpr auto x=__builtin_xnu_type_summary(X);',
          'arm64e-method':'struct X {}; constexpr auto x=__builtin_xnu_type_summary(int (X::*)());',
          'foreign-abi':'struct X {}; constexpr auto x=__builtin_xnu_type_summary(int (X::*)());',
          'address-space':'typedef int G __attribute__((address_space(1))); struct X { G &r; }; constexpr auto x=__builtin_xnu_type_summary(X);',
          'scalable-reference':'struct X { __SVInt32_t &r; }; constexpr auto x=__builtin_xnu_type_summary(X);',
        }
        # Only vector-reference deliberately leaves the earlier unsupported set.
        old=(ROOT/'tools/build/xnu_compiler_vectors.py').read_text()
        import ast
        module=ast.parse(old);cls=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='Vectors')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='vector_negatives')
        previous=ast.literal_eval(fn.body[0].value);previous.pop('vector-reference');cases.update(previous)
        self.report['versioned_control_changes']={'vector-reference':'Supported actual default-AS reference field; storage-contract.cpp tests summary2 instead of rejecting'}
        for name,text in cases.items():
            source=self.out/(name+'.cpp');source.write_text(text+'\n');flags=self.flags()
            if 'arm64e' in name:flags[flags.index('arm64-apple-ios16.5')]='arm64e-apple-ios16.5'
            if name=='foreign-abi':flags+=['-Xclang','-fc++-abi=itanium']
            if 'scalable' in name or name.endswith('sve'):flags+=['-march=armv8-a+sve']
            code,_,stderr=self.run([*flags,'-fsyntax-only',source],'reject-'+name)
            self.check('reject-'+name,code==1 and 'experimental XNU metadata does not support' in stderr,exit_code=code,diagnostic=stderr[-1800:])

    def storage_raw(self):
        source=self.out/'fixture-inputs/raw-storage-evaluator.cpp';obj=self.out/'raw-storage-evaluator.o'
        includes=[self.private/'src/clang/include',self.build/'tools/clang/include',self.private/'src/llvm/include',self.build/'include']
        self.must([NDK/'clang++','-std=c++17','-fno-rtti','-D_GNU_SOURCE','-D__STDC_CONSTANT_MACROS',
            '-D__STDC_FORMAT_MACROS','-D__STDC_LIMIT_MACROS',*[a for p in includes for a in ['-I',p]],'-c',source,'-o',obj],'storage-raw-compile',timeout=180)
        link=[a for a in self.link if not a.endswith('.o')];link.insert(1,str(obj))
        exe=self.out/'raw-storage-evaluator';link[link.index('-o')+1]=str(exe)
        self.must(link,'storage-raw-link',cwd=self.build,timeout=180)
        for mode in ['summary-reference','signature-reference','summary-method','signature-method','summary-trap','signature-trap',
            'reject-root-reference','reject-data-member','reject-function-reference','reject-address-reference','reject-foreign-abi']:
            code,stdout,stderr=self.run([exe,mode],'storage-raw-'+mode)
            self.check('storage-raw-'+mode,code==0,exit_code=code,observed=stdout.strip(),diagnostic=stderr[-1000:])

    def storage_pch(self):
        pch_flags=[*self.flags(),'-fno-exceptions','-fno-unwind-tables','-fno-asynchronous-unwind-tables']
        original_out=self.out;self.out=self.out/'storage-pch';self.out.mkdir()
        try:
            header=self.out/'storage-header.h';shutil.copyfile(original_out/'fixture-inputs/storage-pch.h',header)
            source=self.out/'consumer.cpp'
            source.write_text('static_assert(StoredMetadata<PchStorage>::value==6);\nstruct ReloadedStorage { int &reference; int (PchService::*method)(); };\nstatic_assert(sizeof(ReloadedStorage)==24 && __builtin_xnu_type_summary(ReloadedStorage)==6);\nextern unsigned external_storage_two();\nunsigned use_storage(PchStorage *p) { return external_storage_two()+storage_contract()+stored_symbol(p); }\n')
            pch=self.out/'storage.pch'
            self.must([*pch_flags,'-x','c++-header',header,'-o',pch],'storage-pch-create')
            objects=[]
            for label,include in [('textual',['-include',header]),('serialized',['-include-pch',pch])]:
                obj=self.out/(label+'.o');self.must([*pch_flags,*include,'-c',source,'-o',obj],'storage-pch-'+label);objects.append(obj)
            self.report['atomic_pch_whole_object_equal']=objects[0].read_bytes()==objects[1].read_bytes()
            start=len(self.report['checks']);self.pch_code_equivalence(*objects)
            for c in self.report['checks'][start:]:c['name']=c['name'].replace('atomic-pch','storage-pch')
            names=self.must([NDK/'llvm-nm','--defined-only','--just-symbol-name',objects[1]],'storage-pch-symbols')
            symbol=next(n for n in names.splitlines() if n.startswith('__Z') and 'stored_symbol' in n)
            demangled=self.must([NDK/'llvm-cxxfilt',symbol[1:]],'storage-pch-demangle')
            self.check('storage-dependent-vendor-expression','__builtin_xnu_type_summary' in demangled,demangled=demangled.strip())
            flags=pch_flags.copy();flags[flags.index('arm64-apple-ios16.5')]='arm64e-apple-ios16.5'
            code,_,stderr=self.run([*flags,'-include-pch',pch,'-fsyntax-only',source],'storage-pch-wrong-target')
            self.check('storage-pch-wrong-target',code==1 and 'target' in stderr and 'error:' in stderr)
        finally:self.out=original_out

    def storage_allocator(self):
        obj=self.out/'storage-allocator.o'
        row=self.rows['libkern/OSData.cpo']
        argv,cwd,_=self.command(row,obj,source=self.out/'fixture-inputs/allocator-storage.cpp')
        self.must(argv,'storage-real-allocator',cwd=cwd)
        self.report['storage_allocator_metadata']=allocator_metadata(obj)
        self.check('storage-real-allocator-records',True,records=self.report['storage_allocator_metadata']['records'])
        raw=obj.read_bytes();record=self.report['storage_allocator_metadata']['records'][0]
        for mode in ['truncated','wrong-flags','escaped-signature']:
            bad=bytearray(raw)
            if mode=='truncated':bad=bad[:16]
            if mode=='wrong-flags':bad[record['flags_file_offset']]^=8
            if mode=='escaped-signature':
                struct.pack_into('<Q',bad,record['record_file_offset']+self.report['storage_allocator_metadata']['header_layout']['signature'],(1<<64)-1)
            path=self.out/('storage-allocator-'+mode+'.o');path.write_bytes(bad)
            try:allocator_metadata(path);rejected=False
            except (ValueError,KeyError,UnicodeError,struct.error):rejected=True
            self.check('storage-allocator-reject-'+mode,rejected)

        probe=self.out/'genuine-trap.cpp'
        probe.write_text('#include <IOKit/IOUserClient.h>\nstatic_assert(sizeof(IOExternalTrap)==24 && alignof(IOExternalTrap)==8);\nstatic_assert(__builtin_offsetof(IOExternalTrap,object)==0 && __builtin_offsetof(IOExternalTrap,func)==8);\nstatic_assert(__builtin_xnu_type_summary(IOExternalTrap)==6);\nstatic_assert(__builtin_xnu_type_signature(IOExternalTrap)[0]==\'1\' && __builtin_xnu_type_signature(IOExternalTrap)[1]==\'2\' && __builtin_xnu_type_signature(IOExternalTrap)[2]==\'2\');\n')
        argv,cwd,_=self.command(self.rows['iokit/MiniIOSurface.cpo'],self.out/'genuine-trap.o',source=probe)
        self.must(argv,'genuine-trap-storage',cwd=cwd)
        self.check('actual-genuine-IOExternalTrap-storage',True)

    def controls(self):
        self.compile_rows(CONSUMERS)
        self.representations();self.storage_contract();self.storage_negatives()
        Atomics.controls(self);self.negatives();self.allocator();self.harness();self.pch()
        self.vector_controls();self.vector_raw();self.vector_pch()
        self.storage_raw();self.storage_pch();self.storage_allocator()
        self.qualify()

    def retained_profile(self):
        name='cxx-storage-'+self.args.run
        self.must([sys.executable,ROOT/'tools/build/xnu_compiler_types.py',
            '--run',name,'--clang',self.compiler,'--expanded-controls','--e1s-profile',
            '--compile-interfaces','--qualify-supported-profile','--unevaluated-void-port',
            '--frontend-evidence',ROOT/next(e for e in self.ledger['experiments'] if e['id']==self.args.storage_evidence)['evidence']],
            'retained-supported-profile',timeout=300)
        path=ROOT/'artifacts/xnu-compiler-types'/name/'report.json'
        parent=json.loads(path.read_text());candidate=parent['compilers'][0]
        self.check('retained-seven-real-controls-six-negatives-and17-interfaces',
            parent['outcome']=='pass' and candidate['supported_profile_qualified'])
        self.report['retained_profile']=dict(report=str(path.relative_to(ROOT)),sha256=sha(path),
            evidence=str(path.with_name('evidence.json').relative_to(ROOT)),evidence_sha256=sha(path.with_name('evidence.json')),
            limits_note='Legacy report reference/member-pointer rejection prose is historical; field-reference and method-pointer cases deliberately expanded only by this component')

    def acceptance(self):
        reports={}
        for identifier in ['CXXST-001',self.args.storage_evidence,self.args.controls_evidence,
                           self.args.retained_evidence,self.args.profile_evidence,self.args.audit_evidence]:
            doc=registered(identifier,self.ledger)
            paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
            if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('One passing report required: '+identifier)
            reports[identifier]=(paths[0],json.loads(paths[0].read_text()))
        source_path,source=reports[self.args.storage_evidence]
        prefix=source_path.parent
        if sha(prefix/'clang')!=sha(self.compiler):raise ValueError('Exact current source compiler required')
        # Replay the final patch against the immutable vector helper.
        rel=Path('src/clang/include/clang/AST/XnuTypeMetadata.h')
        replay=self.out/'patch-replay';(replay/rel).parent.mkdir(parents=True)
        shutil.copyfile(COMPILER.parent/'helper-source'/rel,replay/rel)
        patch=PATCHES/'0001-selected-apple-arm64-cxx-storage.patch'
        self.must(['git','-C',replay,'apply','--check',patch],'final-patch-check')
        self.must(['git','-C',replay,'apply',patch],'final-patch-apply')
        self.check('actual-final-patch-replay',sha(replay/rel)==source['storage_helper_sha256']==sha(prefix/'helper-source'/rel))
        old=registered('CXXST-002',self.ledger)
        original=ROOT/'artifacts/xnu-compiler-cxx-storage/source-build-session1/clang'
        if sha(original)!=old['sha256'][str(original.relative_to(ROOT))]:raise ValueError('Preserved first candidate changed')
        probe=self.out/'explicit-foreign-abi.cpp'
        probe.write_text('struct X {}; constexpr auto x=__builtin_xnu_type_summary(int (X::*)());\n')
        for label,compiler,expected in [('original-gap',original,0),('final-rejection',self.compiler,1)]:
            flags=self.flags();flags[0]=compiler
            code,_,error=self.run([*flags,'-Xclang','-fc++-abi=itanium','-fsyntax-only',probe],label+'-effective-abi')
            self.check(label+'-effective-abi',code==expected and (code==0 or 'experimental XNU metadata does not support' in error),exit_code=code)

        def archive_members(path):
            data=path.read_bytes()
            if data[:8]!=b'!<arch>\n':raise ValueError('Regular actual archive required')
            at=8;long_names=b'';members={}
            while at<len(data):
                if at+60>len(data) or data[at+58:at+60]!=b'`\n':raise ValueError('Invalid archive header')
                header=data[at:at+60];size=int(header[48:58]);name=header[:16].decode().strip();begin=at+60
                if size>len(data)-begin:raise ValueError('Archive member extent')
                payload=data[begin:begin+size]
                if name=='//':long_names=payload
                elif name not in {'/','/SYM64/'}:
                    if name.startswith('#1/'):
                        n=int(name[3:]);name=payload[:n].rstrip(b'\0').decode();payload=payload[n:]
                    elif name.startswith('/'):
                        pos=int(name[1:]);end=long_names.find(b'/\n',pos)
                        if end<0:raise ValueError('Invalid archive long name')
                        name=long_names[pos:end].decode()
                    else:name=name.removesuffix('/')
                    if name in members:raise ValueError('Ambiguous duplicate archive member')
                    members[name]=hashlib.sha256(payload).hexdigest()
                at=begin+size+(size&1)
            if at!=len(data):raise ValueError('Archive final extent')
            return members

        manifests={}
        expected={'AST':{'ExprConstant.cpp.o'},'Sema':{'SemaExpr.cpp.o','SemaExprCXX.cpp.o'},'Parse':set()}
        for lib,changes in expected.items():
            old=archive_members(COMPILER.parent/('libclang'+lib+'.a'))
            new=archive_members(prefix/('libclang'+lib+'.a'))
            modified={n for n in old if n in new and old[n]!=new[n]}
            self.check('exact-'+lib+'-archive-member-delta',set(old)==set(new) and modified==changes,
                members=len(new),changed=sorted(modified),expected=sorted(changes))
            for name in changes:
                if new[name]!=sha(prefix/name):raise ValueError('Actual rebuilt member mismatch')
            manifests[lib]=dict(parent=old,current=new)
        dump(self.out/'archive-members.json',manifests)

        dependencies={};inputs={}
        for consumer in source['compiled_consumers']:
            name=Path(consumer['source']).name
            if sha(ROOT/consumer['source'])!=consumer['source_sha256'] or sha(ROOT/consumer['retained_parent'])!=consumer['retained_parent_sha256']:
                raise ValueError('Compiled source parent changed')
            process=next(c for c in source['commands'] if Path(c['stdout']).name==name+'-compile.stdout.txt')
            argv=process['argv'];dep=Path(argv[argv.index('-MF')+1]);cwd=Path(process['cwd'])
            line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            paths=[(cwd/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            if (prefix/'helper-source'/rel).resolve() not in paths:raise ValueError('Actual helper missing from consumer dependency graph')
            for p in paths:inputs[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)]=sha(p)
            dependencies[name]=dict(depfile=str(dep.relative_to(ROOT)),sha256=sha(dep),inputs=[str(p) for p in paths])
            self.check('actual-three-consumer-dependencies-'+name,process['exit_code']==0 and not process['timed_out'] and
                sha(prefix/(name+'.o'))==consumer['object_sha256'])
        for path,h in source['storage_relink_inputs_sha256'].items():
            if sha(path)!=h:raise ValueError('Actual compiler link input changed')
        self.check('exact-complete-compiler-link-inputs',True,count=len(source['storage_relink_inputs_sha256']))
        dump(self.out/'compiler-dependency-files.json',inputs);dump(self.out/'compiler-object-dependencies.json',dependencies)

        audit_path,audit=reports[self.args.audit_evidence]
        profile_path,profile=reports[self.args.profile_evidence]
        self.check('all962-current-objects-and960-prior-successes',profile['coverage']['attempted']==962 and
            profile['coverage']['actual_arm64']==962 and profile['coverage']['prior_successes']==960 and not profile['coverage']['prior_object_regressions'])
        self.check('complete982-direct-object-accounting',audit['coverage']['known_direct_objects']==982 and
            audit['coverage']['actual_arm64']==962 and audit['coverage']['known_direct_unresolved']==20)
        self.check('same-qualified-current-compiler',all(r['compiler_sha256']==sha(self.compiler) for k,(_,r) in reports.items() if k!='CXXST-001'))
        controls=reports[self.args.controls_evidence][1]
        self.check('all-actual-controls-pass',len(controls['checks'])>100 and all(c['pass_check'] for c in controls['checks']))
        self.report['acceptance_reports']={k:dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for k,(p,r) in reports.items()}
        self.report['acceptance_assessment']=[dict(criterion=i+1,pass_check=True,evidence=names) for i,names in enumerate([
            ['CXXST-001',self.args.controls_evidence,'source-review.json'],
            [self.args.storage_evidence,self.args.controls_evidence],
            [self.args.storage_evidence,self.args.controls_evidence,self.args.retained_evidence,'archive-members.json','compiler-dependency-files.json'],
            [self.args.profile_evidence,self.args.audit_evidence]])]
        self.report['coverage']=audit['coverage']
        self.must(['make','check'],'repository-check',timeout=300)
        self.check('required-repository-checks',True)
        self.must(['git','diff','--check'],'whitespace-check')
        self.must(['git','diff','--cached','--check'],'staged-whitespace-check')

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Selected public-source C++ storage/real compiler objects; full kernel/link/private ABI/crypto/native support remains unqualified'
        self.report['compiler_sha256']=sha(self.compiler) if hasattr(self,'compiler') else None
        dump(self.out/'report.json',self.report)
        files=sorted(p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json')
        if self.args.mode=='acceptance':
            files=sorted(set(files+[Path(__file__),ROOT/'docs/procedures/xnu-compiler-cxx-storage.md',
                *[p for base in [FIXTURES,PATCHES] for p in base.rglob('*') if p.is_file()]]))
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','full_crypto_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20],commands_scope='Representative exact commands; every actual execution in hashed report.json',
            actual_command_count=len(self.report['commands']),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['baseline','build','controls','profile','consumers','kernel','audit','acceptance'],required=True)
    p.add_argument('--storage-evidence')
    p.add_argument('--profile-evidence')
    p.add_argument('--controls-evidence')
    p.add_argument('--retained-evidence')
    p.add_argument('--audit-evidence')
    p.add_argument('--jobs',type=int,default=2)
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Canonical fresh run name required')
    if not 1<=args.jobs<=3:p.error('Use 1..3 bounded host jobs')
    args.compiler,args.compiler_evidence,args.header_evidence,args.resource_evidence=COMPILER,'VCOMP-002','FHDR-003','RHDR-002'
    args.port_evidence='KDECL-004'
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));build=Storage(args)
    try:
        build.inputs()
        if args.mode=='baseline':build.baseline()
        elif args.mode=='build':build.rebuild_storage()
        else:
            build.reuse_storage()
            if args.mode=='controls':build.controls()
            elif args.mode=='profile':build.retained_profile()
            elif args.mode=='acceptance':build.acceptance()
            elif args.mode=='audit':build.audit_profile()
            else:build.compile_rows(list(build.rows) if args.mode=='kernel' else CONSUMERS)
    except Exception as error:build.report['error']=str(error)
    return build.finish()


if __name__=='__main__':sys.exit(main())
