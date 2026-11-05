#!/usr/bin/env python3
"""Qualify genuine pthread kext installed headers, objects and native aliases."""
from __future__ import annotations
import argparse
from collections import Counter,deque
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import struct
import sys
from xnu_kernel_link_inputs import LinkInputs
from xnu_compiler_atomics import ROOT,KERNEL,NDK,registered,sha,dump
from xnu_kernel_firehose_headers import COMPILER as VECTOR_COMPILER
from xnu_kernel_firehose_headers import UNIFDEF
from xnu_kernel_direct_tail import thin
from xnu_kernel_link_inputs import archive_members
from xnu_kernel_syscalls import ObjectData

FIXTURES=ROOT/'fixtures/public/xnu-kernel-pthread-profile'
PTHREAD=ROOT/'references/xnu-kernel-pthread'
REVISION='a6c70ca0e544347a0377babf748f831577ec24f9'
SGAP=ROOT/'artifacts/xnu-kernel-symbol-gaps/production-session1'


class PthreadProfile(LinkInputs):
    def __init__(self,args):
        self.args=args;self.out=ROOT/'artifacts/xnu-kernel-pthread-profile'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Canonical fresh run required')
        self.out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text());self.ports={}
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',mode=args.mode,recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            commands=[],checks=[],kernel_cases=[],device_executed=False,sdk_used=False,global_install=False,experimental_generator=True,
            full_kernel_qualified=False,full_archive_link_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,
            apple_interoperability_qualified=False,native_device_qualified=False)

    def inputs(self):
        super().inputs()
        for identifier in ['SGAP-001','SGAP-006','KLINK-007','KLINK-011','KLINK-003','KLINK-006']:
            registered(identifier,self.ledger);entry=next(e for e in self.ledger['experiments'] if e['id']==identifier)
            self.report['parents'][identifier]=dict(path=entry['evidence'],sha256=entry['evidence_sha256'])
        self.compiled=json.loads((SGAP/'compiled-objects.json').read_text());self.by_id={r['id']:r for r in self.compiled}
        self.source_inputs=json.loads((SGAP/'dependency-files.json').read_text())
        for row in self.compiled:
            if sha(ROOT/row['source'])!=row['source_sha256'] or sha(ROOT/row['output'])!=row['output_sha256']:raise ValueError('Current coherent982 input changed')
        for name,value in self.source_inputs.items():
            if sha(ROOT/name)!=value:raise ValueError('Current3156 dependency witness changed')
        revision=self.must(['git','-C',PTHREAD,'rev-parse','HEAD'],'pthread-source-revision').strip()
        self.must(['git','-C',PTHREAD,'diff','--exit-code','HEAD'],'pthread-clean-source')
        if revision!=REVISION:raise ValueError('Pinned actual pthread source required')
        config=PTHREAD/'xcodescripts/kext.xcconfig'
        self.kext_definitions=re.search(r'^GCC_PREPROCESSOR_DEFINITIONS_kext = (.+)$',config.read_text(),re.M).group(1).split()
        self.report['pthread_native_sources']={str(p.relative_to(ROOT)):sha(p) for p in [config,PTHREAD/'libpthread.xcodeproj/project.pbxproj',PTHREAD/'kern/kern_init.c',PTHREAD/'kern/kern_support.c',PTHREAD/'kern/kern_synch.c']}
        self.report['native_kext_definitions']=self.kext_definitions
        self.native_aliases()

    def native_aliases(self):
        report=ROOT/'artifacts/xnu-kernel-link-inputs/link-session2/report.json';parent=json.loads(report.read_text())
        path=ROOT/'artifacts/xnu-kernel-link-inputs/link-session2/stage/all-alias.exp'
        if sha(path)!=parent['metadata']['outputs'][str(path.relative_to(ROOT))]:raise ValueError('Genuine selected alias list changed')
        aliases={a[1]:a[0] for l in path.read_text().splitlines() if len(a:=l.split())==2}
        providers=json.loads((SGAP/'symbol-providers.json').read_text())
        expected={'_mach_vm_allocate':'_mach_vm_allocate_external','_mach_vm_map':'_mach_vm_map_external','_vm_fault':'_vm_fault_external'}
        self.report['native_VM_aliases']={n:dict(target=t,actual_alias=aliases.get(n),current_providers=providers.get(t,[])) for n,t in expected.items()}
        self.check('all3-actual-selected-VM-alias-providers',all(aliases.get(n)==t and providers.get(t) for n,t in expected.items()))
        self.report['alias_list']=dict(path=str(path.relative_to(ROOT)),sha256=sha(path),total_aliases=len(aliases),actual_link_probe_required=True)

    def host_commands(self):
        self.shim=self.out/'host-commands.mk'
        cmd=(KERNEL/'makedefs/MakeInc.cmd').read_text().splitlines()
        keys=['SUPPORTED_EMBEDDED_PLATFORMS','SUPPORTED_SIMULATOR_PLATFORMS','SUPPORTED_PLATFORMS']
        platform='\n'.join(next(l for l in cmd if l.startswith(k+' :=')) for k in keys)
        logging='\n'.join(next(l for l in cmd if l.startswith(k+' = ')) for k in ['LOG_PFX_LEN','LOG_PFX_LEN_ADJ','LOG','_LOG_HOST','LOG_INSTALLHDR'])
        self.shim.write_text('TR = tr\nBASH = bash\nECHO = echo\nPRINTF = printf\nCAT = cat\nMKDIR = mkdir -p\nRM = rm -f\nINSTALL = /usr/bin/install\n_v =\n'+platform+'\n'+logging+'\n')
        self.report['host_query_shim']=dict(path=str(self.shim.relative_to(ROOT)),sha256=sha(self.shim),scope='Explicit Linux discovery/tools plus unchanged native platform/logging definitions;no SDK contents')

    def header_make_args(self,directory,query,cwd):
        process=next(c for c in self.object_report['commands'] if c['stdout'].endswith('/inventory-osfmk.stdout.txt'))
        args=process['argv'].copy();args[args.index('-f')+1]=str(query)
        values={'OBJROOT':str(self.out/'object-root'),'OBJPATH':str(self.out/'build'),'TARGET':str(cwd),'SOURCE':str(directory)+'/',
            'RELATIVE_SOURCE_PATH':'./'+str(directory.relative_to(KERNEL)),'CC':str(self.compiler),'CXX':str(self.compiler),'MakeInc_cmd':str(self.shim),'SDKROOT':str(self.out/'unavailable-sdk')}
        args=[next((k+'='+v for k,v in values.items() if a.startswith(k+'=')),a) for a in args]
        args+=['DSTROOT='+str(self.out/'installtree')]
        return args

    def inventory(self):
        self.host_commands();queue=deque(KERNEL/c for c in [*self.object_report['configurations'],'EXTERNAL_HEADERS']);seen=set();rows=[];queries=[];missing=[]
        lists=['INSTALL_KF_'+arch+suffix for arch in ['MI','MD'] for suffix in ['_LIST','_LCL_LIST','_GEN_LIST','_LCL_GEN_LIST']]
        keys=['INSTINC_SUBDIRS','INSTINC_SUBDIRS_ARM64','KINCFRAME_UNIFDEF','KPINCFRAME_UNIFDEF','KINCDIR','KPINCDIR',*lists]
        keys += [n.removesuffix('_LIST')+'_FILES' for n in lists]
        while queue:
            directory=queue.popleft().resolve()
            if directory in seen:continue
            if not directory.is_relative_to(KERNEL):raise ValueError('Genuine recursion escaped source')
            seen.add(directory);makefile=directory/'Makefile';relative=str(directory.relative_to(KERNEL))
            if not makefile.is_file():missing.append(relative);continue
            cwd=self.out/'header-build'/relative;cwd.mkdir(parents=True,exist_ok=True);query=cwd/'query.mk'
            query.write_text('include '+str(makefile)+'\n'+''.join('$(info S24_KHDR|'+k+'|$('+k+'))\n' for k in keys)+'\n.PHONY: s24_query\ns24_query: ;\n')
            args=self.header_make_args(directory,query,cwd)
            text=self.must(args,'headers-query-'+relative.replace('/','-'),cwd=cwd,timeout=60)
            values={a[1]:a[2] for l in text.splitlines() if l.startswith('S24_KHDR|') and len(a:=l.split('|',2))==3}
            if set(values)!=set(keys):raise ValueError('Complete genuine header variables required')
            for child in sorted(set((values['INSTINC_SUBDIRS']+' '+values['INSTINC_SUBDIRS_ARM64']).split())):queue.append(directory/child)
            query_rows=[]
            for key in lists:
                names=values[key].split();outputs=values[key.removesuffix('_LIST')+'_FILES'].split()
                if len(names)!=len(outputs):raise ValueError('Native header selection/output count differs')
                for name,destination in zip(names,outputs):
                    target=Path(destination).resolve()
                    if not target.is_relative_to(self.out/'installtree'):raise ValueError('Header install target escaped owned prefix')
                    generated='_GEN_LIST' in key or '_LCL_GEN_LIST' in key
                    source=(cwd if generated else directory)/name
                    row=dict(declaration=str(makefile.relative_to(ROOT)),declaration_sha256=sha(makefile),kind=key,name=name,
                        source=str(source.relative_to(ROOT)),source_exists=source.is_file(),source_sha256=sha(source) if source.is_file() else None,
                        output=str(target.relative_to(ROOT)),make_target=destination,generated_input=generated,private='_LCL' in key,
                        unifdef_flags=shlex.split(values['KPINCFRAME_UNIFDEF' if '_LCL' in key else 'KINCFRAME_UNIFDEF']))
                    rows.append(row);query_rows.append(len(rows)-1)
            queries.append(dict(source=relative,cwd=str(cwd.relative_to(ROOT)),query=str(query.relative_to(ROOT)),argv=args,values=values,rows=query_rows))
        self.report['header_inventory']=dict(directories=len(queries),source_backed=sum(not r['generated_input'] and r['source_exists'] for r in rows),
            generated_inputs=sum(r['generated_input'] for r in rows),missing_makefiles=missing,selection_count=len(rows),sdk_complete=False)
        self.report['header_queries']=queries
        self.check('genuine-header-selection-nonempty',bool(rows) and any(r['name']=='thread.h' and r['private'] for r in rows))
        self.check('genuine-installed-private-context-removes-XNU-bodies',all('-UXNU_KERNEL_PRIVATE' in r['unifdef_flags'] and '-UMACH_KERNEL_PRIVATE' in r['unifdef_flags'] and '-UBSD_KERNEL_PRIVATE' in r['unifdef_flags'] for r in rows))
        dump(self.out/'header-inventory.json',rows)

    def generated_header(self,source):
        relative=source.relative_to(self.out/'header-build')
        if relative.parts[0]=='osfmk':
            report=json.loads((ROOT/'artifacts/xnu-kernel-mig/coherent-session1/report.json').read_text())
            for mode in ['export','internal']:
                key=str(Path(mode)/relative)
                if key in report['generated_files']:
                    path=ROOT/'artifacts/xnu-kernel-mig/coherent-session1'/key
                    if sha(path)!=report['generated_files'][key]:raise ValueError('Genuine MIG output changed')
                    return path,'KMIG-003:'+key
        elif str(relative) in ['bsd/sys/syscall.h','bsd/sys/sysproto.h']:
            base=ROOT/'artifacts/xnu-kernel-syscalls/generate-session2';key=str(Path('generated')/relative);path=base/key
            report=json.loads((base/'report.json').read_text())
            if not path.is_file() or sha(path)!=report['generated_files'][key]:raise ValueError('Actual witnessed syscall generated input required')
            return path,'KSYSC-002'
        elif str(relative)=='libkern/libkern/version.h':
            path=ROOT/'artifacts/xnu-kernel-setup/generate-session1/generated/include/libkern/version.h'
            if not path.is_file():raise ValueError('Actual stamped version input required')
            return path,'KSETUP-001'
        return None,None

    def headers(self):
        self.inventory();rows=json.loads((self.out/'header-inventory.json').read_text())
        hostinc=self.out/'host-include';hostinc.mkdir();(hostinc/'libc.h').write_text('#include <stdlib.h>\n#include <string.h>\n#include <unistd.h>\n')
        decomment=self.out/'decomment';source=KERNEL/'SETUP/decomment/decomment.c'
        self.must(['/usr/bin/cc','-I',hostinc,source,'-o',decomment],'genuine-host-decomment-build')
        replace=ROOT/'artifacts/xnu-kernel-link-inputs/baseline-session5/replacecontents'
        baseline=json.loads((ROOT/'artifacts/xnu-kernel-link-inputs/baseline-session5/report.json').read_text())
        if sha(replace)!=baseline['replacecontents']['tool_sha256']:raise ValueError('Genuine replacecontents tool changed')
        self.report['header_install_tools']=dict(decomment_source=str(source.relative_to(ROOT)),decomment_source_sha256=sha(source),decomment_sha256=sha(decomment),
            libc_include_adapter_sha256=sha(hostinc/'libc.h'),replacecontents=str(replace.relative_to(ROOT)),replacecontents_sha256=sha(replace),unifdef=str(UNIFDEF.relative_to(ROOT)),unifdef_sha256=sha(UNIFDEF),
            host_install_flags='GNU install -c -m0444;BSD-only -S omitted in fresh owned output;target header bytes unchanged',sdk_binary_used=False)
        available=set();seeded={}
        for index,row in enumerate(rows):
            source=ROOT/row['source']
            if row['generated_input']:
                known,parent=self.generated_header(source)
                if known is None:row['status']='unavailable_generated_input';continue
                if source not in seeded:
                    source.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(known,source);seeded[source]=sha(source)
                elif seeded[source]!=sha(known):raise ValueError('Conflicting genuine generated input')
                row.update(source_exists=True,source_sha256=sha(source),generated_origin=str(known.relative_to(ROOT)),generated_evidence=parent)
            if not source.is_file():row['status']='missing_source';continue
            if sha(source)!=row['source_sha256']:raise ValueError('Header source changed before installation')
            available.add(index)
        for query in self.report['header_queries']:
            selected=[rows[i] for i in query['rows'] if i in available]
            if not selected:continue
            # GNU make keys are literal: a native double slash must survive
            # even though filesystem witnesses use canonical paths.
            goals=list(dict.fromkeys(r['make_target'] for r in selected));argv=query['argv'].copy()
            argv[argv.index('s24_query')]='-j2';argv+=goals
            argv+=['UNIFDEF='+str(UNIFDEF),'DECOMMENT='+str(decomment),'REPLACECONTENTS='+str(replace),'INSTALL_FLAGS=-c -m 0444']
            for source in sorted({r['source'] for r in selected if r['generated_input']}):
                path=ROOT/source
                # Native install rules name generated prerequisites relatively;
                # keep both make spellings for the already witnessed input.
                argv+=['-o',str(path),'-o',str(path.relative_to(ROOT/query['cwd']))]
            self.must(argv,'genuine-install-'+query['source'].replace('/','-'),cwd=ROOT/query['cwd'],timeout=180)
            for row in selected:
                path=ROOT/row['output']
                if path.is_file():
                    row.update(status='installed',output_sha256=sha(path),output_mode=oct(path.stat().st_mode&0o777))
                    if path.stat().st_mode&0o777!=0o444:raise ValueError('Native installed read-only header mode differs')
                else:row['status']='native_filtered_empty'
        self.report['header_install_counts']=dict(Counter(r['status'] for r in rows))
        self.report['header_roots']=dict(public=str((self.out/'installtree'/self.report['header_queries'][0]['values']['KINCDIR'].lstrip('/')).relative_to(ROOT)),
            private=str((self.out/'installtree'/self.report['header_queries'][0]['values']['KPINCDIR'].lstrip('/')).relative_to(ROOT)))
        private=ROOT/self.report['header_roots']['private'];thread=private/'kern/thread.h'
        self.check('actual-native-thread-private-body-removed',thread.is_file() and not re.search(r'\bstruct\s+thread\s*\{',thread.read_text()))
        self.check('actual-native-pthread-callback-header',(private/'sys/pthread_shims.h').is_file())
        self.check('no-invented-empty-generated-header',all(not (ROOT/r['output']).exists() for r in rows if r['status']=='unavailable_generated_input'))
        self.report['source_generated_kernel_headers_used']=True
        self.report['complete_SDK_qualified']=False
        dump(self.out/'installed-header-manifest.json',rows)

    def header_component(self):
        doc=registered(self.args.header_profile,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('One actual passing native installed-header report required')
        report=json.loads(paths[0].read_text());manifest=paths[0].parent/'installed-header-manifest.json'
        if not manifest.is_file():raise ValueError('Actual installed-header manifest required')
        rows=json.loads(manifest.read_text())
        for row in rows:
            if row['status']=='installed' and sha(ROOT/row['output'])!=row['output_sha256']:raise ValueError('Installed header changed or was overwritten')
        self.report['parents'][self.args.header_profile]=dict(path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        self.report['installed_header_profile']=dict(report=str(paths[0].relative_to(ROOT)),manifest=str(manifest.relative_to(ROOT)),manifest_sha256=sha(manifest),
            roots=report['header_roots'],counts=report['header_install_counts'],complete_SDK_qualified=False)
        return report

    def compile_pthread(self):
        header=self.header_component();root=self.out/'pthread-source'
        original=ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/pthread'
        old=json.loads((ROOT/'fixtures/public/open-kernel-inputs/typed-pthread-session1.json').read_text())
        shutil.copytree(original,root,ignore=shutil.ignore_patterns('.git'))
        hashes={}
        for path in root.rglob('*'):
            if not path.is_file():continue
            relative=str(path.relative_to(root));value=sha(path);hashes[relative]=value
            if relative in old['typed_source_sha256']:
                if value!=old['typed_source_sha256'][relative]:raise ValueError('Witnessed typed pthread source changed')
            elif not (PTHREAD/relative).is_file() or value!=sha(PTHREAD/relative):raise ValueError('Unpinned pthread source/header: '+relative)
        self.report['pthread_source_files']=hashes
        components=json.loads((ROOT/'fixtures/public/open-kernel-inputs/reusable-components.json').read_text())['pthread']
        availability=ROOT/components['header_root']
        if sha(availability/'TargetConditionals.h')!=components['target_header_sha256']:raise ValueError('Witnessed native iOS public target header required')
        native=(PTHREAD/'xcodescripts/kext.xcconfig').read_text()
        standard=re.search(r'^GCC_C_LANGUAGE_STANDARD = (.+)$',native,re.M).group(1)
        # Availability is supplied by the SDK's separate public header project,
        # not INSTALL_KF. Use only unchanged public files present in pinned XNU,
        # with independent git-blob identity;never a raw kernel include fallback.
        supplement=self.out/'public-availability';supplement.mkdir();self.report['public_header_supplements']={}
        for name in ['Availability.h','AvailabilityInternal.h','AvailabilityMacros.h']:
            source=KERNEL/'EXTERNAL_HEADERS'/name
            self.must(['git','-C',ROOT/'references/apple-xnu','show','c54f35ca767986246321eb901baf8f5ff7923f6a:EXTERNAL_HEADERS/'+name],'public-source-'+name)
            if sha(self.out/('public-source-'+name+'.stdout.txt'))!=sha(source):raise ValueError('Exact pinned public Availability source required')
            shutil.copyfile(source,supplement/name)
            self.report['public_header_supplements'][name]=dict(source=str(source.relative_to(ROOT)),sha256=sha(source),output=str((supplement/name).relative_to(ROOT)),scope='Pinned public source contribution;not a complete selected SDK')
        flags=['-target','arm64-apple-ios16.5','-mkernel','-nostdinc','-fno-builtin','-fno-common','-Os','-std='+standard,
            '-DKERNEL=1','-DKERNEL_PRIVATE=1','-DPRIVATE=1','-DARM64_BOARD_CONFIG_E1S','-D__DARWIN_64_BIT_INO_T=1',
            '-DXNU_TARGET_OS_IOS=1','-DXNU_NO_TYPE_BUILTINS=0','-Dpthread_kern=pthread_kext_kern','-Dcurrent_uthread=pthread_kext_current_uthread',
            '-Werror=implicit-function-declaration','-Werror=incompatible-pointer-types',*['-D'+d for d in self.kext_definitions]]
        include=[root/'private',root/'include',root,ROOT/header['header_roots']['private'],ROOT/header['header_roots']['public'],availability,supplement]
        flags+=[a for p in include for a in ['-I',str(p)]]
        self.report['pthread_compile_profile']=dict(flags=flags,native_definitions=self.kext_definitions,source_qualified_include_roots=[str(p.relative_to(ROOT)) for p in include],
            raw_internal_header_fallback=False,fake_metadata_header_used=False,metadata_checks_enabled=True,native_normal_LTO=True,
            measured_kernel_integration_LTO=False,LTO_scope='Current selected kernel BUILD_LTO=0 object/archive integration;not a stock Xcode release binary',
            namespace_adaptation='Two witnessed static-integration symbol remaps;all real source bodies retained')
        self.report['pthread_compile_results']=[];objects=[]
        for name in ['kern_init','kern_support','kern_synch']:
            source=root/'kern'/(name+'.c');output=self.out/(name+'.o')
            argv=[self.compiler,*flags,'-MD','-MF',output.with_suffix('.d'),'-c',source,'-o',output]
            code,_,error=self.run(argv,'native-profile-'+name,cwd=self.out,timeout=120)
            good=code==0 and output.is_file() and thin(output)['filetype']==1
            self.check('actual-native-profile-'+name,good,exit_code=code,diagnostic=error[-4000:])
            self.report['pthread_compile_results'].append(dict(name=name,source=str(source.relative_to(ROOT)),source_sha256=sha(source),exit_code=code,
                actual_arm64_object=good,output=str(output.relative_to(ROOT)) if good else None,output_sha256=sha(output) if good else None))
            if good:objects.append(output)
        if len(objects)!=3:raise ValueError('All three genuine current-profile pthread TUs required')
        archive=self.out/'libpthread_kext.a'
        self.must([self.libtool,'-static','-o',archive,*objects],'genuine-current-pthread-archive')
        members=archive_members(archive.read_bytes())
        self.check('all3-real-pthread-archive-members',len(members)==3 and all(name==p.name and data==p.read_bytes() for (name,data),p in zip(members,objects)))
        defined=self.must([NDK/'llvm-nm','--extern-only','--defined-only','--just-symbol-name',archive],'current-pthread-defined')
        required=self.must([NDK/'llvm-nm','--undefined-only','--just-symbol-name',archive],'current-pthread-required')
        defs={l for l in defined.splitlines() if l and not l.endswith(':')};imports={l for l in required.splitlines() if l and not l.endswith(':')}-defs
        providers=json.loads((SGAP/'symbol-providers.json').read_text());aliases={n:r['target'] for n,r in self.report['native_VM_aliases'].items()}
        unresolved=sorted(n for n in imports if n not in providers and aliases.get(n) not in providers)
        self.report['pthread_provider_closure']=dict(archive=str(archive.relative_to(ROOT)),sha256=sha(archive),defined=sorted(defs),external_imports=sorted(imports),
            resolved_by_native_VM_aliases=sorted(n for n in imports if n in aliases),unresolved=unresolved,actual_native_alias_link_required=True)
        self.check('actual-pthread-start-provider','_pthread_start' in defs)
        self.check('all-pthread-imports-have-real-kernel-or-alias-provider',not unresolved,unresolved=unresolved)
        inputs={};dependencies={}
        for row in self.report['pthread_compile_results']:
            output=ROOT/row['output'];dep=output.with_suffix('.d');line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(self.out/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            for path in files:inputs[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)]=sha(path)
            dependencies[row['name']]=dict(depfile=str(dep.relative_to(ROOT)),sha256=sha(dep),inputs=[str(p.relative_to(ROOT)) for p in files])
        dump(self.out/'pthread-dependency-files.json',inputs);dump(self.out/'pthread-object-dependencies.json',dependencies)

    def object_component(self):
        doc=registered(self.args.object_profile,self.ledger);paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('Actual current-profile pthread archive required')
        report=json.loads(paths[0].read_text())
        for row in report['pthread_compile_results']:
            if sha(ROOT/row['output'])!=row['output_sha256'] or sha(ROOT/row['source'])!=row['source_sha256']:raise ValueError('Qualified pthread source/object changed')
        inputs=json.loads((paths[0].parent/'pthread-dependency-files.json').read_text())
        for name,value in inputs.items():
            if sha(ROOT/name)!=value:raise ValueError('Qualified pthread header dependency changed')
        self.report['parents'][self.args.object_profile]=dict(path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        return report

    @staticmethod
    def preprocess_argv(argv):
        result=[];skip=False
        for a in argv:
            if skip:skip=False;continue
            if a in ['-o','-MF','-MT','-MQ']:skip=True;continue
            if a in ['-c','-MD','-MP','-MMD']:continue
            result.append(a)
        return [*result,'-E']

    @staticmethod
    def callback_fields(text):
        text=re.sub(r'^#.*$','',text,flags=re.M);result={}
        for name in ['pthread_functions_s','pthread_callbacks_s']:
            match=re.search(r'typedef\s+const\s+struct\s+'+name+r'\s*\{(.*?)\}\s*\*\s*\w+\s*;',text,re.S)
            if match is None:raise ValueError('Actual callback record definition required: '+name)
            fields=[]
            for declaration in match.group(1).split(';'):
                declaration=declaration.strip()
                if not declaration:continue
                pointer=re.search(r'\(\s*\*\s*(\w+)\s*\)',declaration)
                last=re.search(r'(\w+)\s*(?:\[\s*\d+\s*\])?\s*$',declaration)
                if not pointer and not last:raise ValueError('Unreviewed actual field syntax: '+declaration)
                fields.append(dict(name=(pointer or last).group(1),declaration=re.sub(r'\s+','',declaration),function_pointer=pointer is not None))
            result[name]=fields
        return result

    def probe_command(self,process,source,output):
        argv=process['argv'].copy();argv[argv.index('-o')+1]=str(output);argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
        old=argv[argv.index('-c')+1] if argv.index('-c')+1<len(argv) else None
        # Genuine full kernel recipes put flags after -c, so select the actual
        # translation-unit token rather than relying on flag adjacency.
        candidates=[a for a in argv if a.endswith('.c') and Path(a).is_file()]
        if len(candidates)!=1:raise ValueError('One actual C translation unit required')
        argv[argv.index(candidates[0])]=str(source)
        return argv,Path(process['cwd'])

    def controls(self):
        component=self.object_component();self.header_component()
        sdk_process=next(c for c in component['commands'] if c['stdout'].endswith('/native-profile-kern_init.stdout.txt'))
        current=json.loads((ROOT/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json').read_text())
        kernel_row=self.by_id['bsd/pthread_shims.o']
        kernel_process=next(c for c in current['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==str(ROOT/kernel_row['output']))
        texts={};fields={}
        for label,process in [('kext',sdk_process),('kernel',kernel_process)]:
            text=self.must(self.preprocess_argv(process['argv']),'actual-'+label+'-callback-preprocessing',cwd=Path(process['cwd']),timeout=120)
            texts[label]=text;fields[label]=self.callback_fields(text)
        self.check('actual-all-callback-field-declarations-match',fields['kext']==fields['kernel'],counts={k:len(v) for k,v in fields['kext'].items()})
        expressions=[];names=[]
        for record,members in fields['kext'].items():
            expressions += ['sizeof(struct '+record+')','_Alignof(struct '+record+')'];names += [record+'.size',record+'.alignment']
            for member in members:
                field=member['name'];expressions+=['__builtin_offsetof(struct '+record+','+field+')','sizeof(((struct '+record+'*)0)->'+field+')'];names += [record+'.'+field+'.offset',record+'.'+field+'.size']
        suffix='\n#include <kern/kalloc.h>\nconst unsigned long long s24_pthread_layout[]={'+','.join(expressions)+'};\n'
        suffix+='const unsigned long long s24_kalloc_layout[]={sizeof(struct kalloc_type_view),__builtin_offsetof(struct kalloc_type_view,kt_signature),__builtin_offsetof(struct kalloc_type_view,kt_flags),__builtin_offsetof(struct kalloc_type_view,kt_size)};\n'
        probes={};commands={};sources={}
        for label,process,original in [('kext',sdk_process,ROOT/component['pthread_compile_results'][0]['source']),('kernel',kernel_process,ROOT/kernel_row['source'])]:
            source=self.out/(label+'-callback-probe.c');source.write_text(original.read_text()+suffix);output=self.out/(label+'-callback-probe.o')
            argv,cwd=self.probe_command(process,source,output);argv+=['-Werror=incompatible-function-pointer-types']
            self.must(argv,'actual-'+label+'-callback-probe',cwd=cwd,timeout=120)
            obj=ObjectData(output);probes[label]=dict(layout=list(obj.value('_s24_pthread_layout','<'+str(len(names))+'Q')),allocator=list(obj.value('_s24_kalloc_layout','<4Q')),object=str(output.relative_to(ROOT)),sha256=sha(output))
            commands[label]=(argv,cwd);sources[label]=source
        self.check('all-target-callback-field-offsets-and-sizes-match',probes['kext']['layout']==probes['kernel']['layout'],values=len(names))
        self.check('actual-kalloc-descriptor-layout-matches',probes['kext']['allocator']==probes['kernel']['allocator'])
        argv,cwd=commands['kext'];independent=argv.copy();independent[0]=str(NDK/'clang');independent[independent.index('-o')+1]=str(self.out/'clang19-callback-probe.o');independent[independent.index('-MF')+1]=str(self.out/'clang19-callback-probe.d')
        self.must(independent,'independent-Clang19-callback-layout',cwd=cwd,timeout=120)
        observed=list(ObjectData(self.out/'clang19-callback-probe.o').value('_s24_pthread_layout','<'+str(len(names))+'Q'))
        self.check('independent-Clang19-all-layout-values-agree',observed==probes['kext']['layout'])
        self.report['callback_layout']=dict(fields=fields['kext'],names=names,probes=probes,clang19_values=observed,private_Apple_oracle_qualified=False)
        original=ROOT/self.report['installed_header_profile']['roots']['private']/'sys/pthread_shims.h'
        badroot=self.out/'wrong-layout';(badroot/'sys').mkdir(parents=True)
        (badroot/'sys/pthread_shims.h').write_text(original.read_text().replace('uint32_t config_thread_max;','uint64_t config_thread_max;',1))
        if sha(badroot/'sys/pthread_shims.h')==sha(original):raise ValueError('Actual layout mutation anchor changed')
        bad=argv.copy();bad[1:1]=['-I',str(badroot)];bad[bad.index('-o')+1]=str(self.out/'wrong-layout.o');bad[bad.index('-MF')+1]=str(self.out/'wrong-layout.d')
        self.must(bad,'real-wrong-callback-layout-compile',cwd=cwd,timeout=120)
        changed=list(ObjectData(self.out/'wrong-layout.o').value('_s24_pthread_layout','<'+str(len(names))+'Q'))
        self.check('real-wrong-header-layout-detected',changed!=probes['kernel']['layout'])
        badtype=self.out/'wrong-type';(badtype/'sys').mkdir(parents=True)
        (badtype/'sys/pthread_shims.h').write_text(original.read_text().replace('void (*pthread_init)(void);','int (*pthread_init)(void);',1))
        if sha(badtype/'sys/pthread_shims.h')==sha(original):raise ValueError('Actual function-type mutation anchor changed')
        bad=argv.copy();bad[1:1]=['-I',str(badtype)];bad[bad.index('-o')+1]=str(self.out/'must-not-compile-callback.o');bad[bad.index('-MF')+1]=str(self.out/'wrong-type.d')
        code,_,error=self.run(bad,'actual-wrong-callback-type-rejection',cwd=cwd,timeout=120)
        self.check('real-wrong-function-pointer-type-rejected',code!=0 and ('incompatible function pointer' in error or 'incompatible pointer' in error) and not (self.out/'must-not-compile-callback.o').exists(),exit_code=code)
        self.allocator_controls(component,probes['kext']['allocator'])
        self.alias_controls()

    def allocator_controls(self,component,layout):
        process=next(c for c in component['commands'] if c['stdout'].endswith('/native-profile-kern_synch.stdout.txt'))
        original=ROOT/next(r['source'] for r in component['pthread_compile_results'] if r['name']=='kern_synch')
        source=self.out/'allocator-probe.c';types=['struct ksyn_wait_queue','struct ksyn_waitq_element']
        suffix='\nconst unsigned long long s24_allocated_sizes[]={'+','.join('sizeof('+t+')' for t in types)+'};\n'
        suffix+='const unsigned long long s24_allocated_summaries[]={'+','.join('__builtin_xnu_type_summary('+t+')' for t in types)+'};\n'
        for i,t in enumerate(types):suffix+='const char *const s24_allocated_signature'+str(i)+'=__builtin_xnu_type_signature('+t+');\n'
        source.write_text(original.read_text()+suffix);output=self.out/'allocator-probe.o';argv,cwd=self.probe_command(process,source,output)
        self.must(argv,'actual-pthread-allocator-probe',cwd=cwd,timeout=120)
        def decode(path):
            obj=ObjectData(path);total,sig,flags,size=layout;result=[]
            for name in ['_kwq_zone','_kwe_zone']:
                obj.location(name,total)
                result.append(dict(name=name,signature=obj.string(name,sig),flags=obj.value(name,'<I',flags)[0],size=obj.value(name,'<I',size)[0]))
            return obj,result
        obj,records=decode(output);sizes=list(obj.value('_s24_allocated_sizes','<2Q'));summaries=list(obj.value('_s24_allocated_summaries','<2Q'));signatures=[obj.string('_s24_allocated_signature'+str(i),0) for i in range(2)]
        original_obj=ROOT/next(r['output'] for r in component['pthread_compile_results'] if r['name']=='kern_synch');_,original_records=decode(original_obj)
        self.check('real-two-allocation-descriptors-and-type-signatures',records==original_records and [r['size'] for r in records]==sizes and [r['signature'] for r in records]==signatures)
        negative=argv.copy();negative+=['-D__builtin_xnu_type_signature(type)="12"','-D__builtin_xnu_type_summary(type)=6'];negative[negative.index('-o')+1]=str(self.out/'fake-metadata-negative.o');negative[negative.index('-MF')+1]=str(self.out/'fake-metadata-negative.d')
        self.must(negative,'actual-old-fake-metadata-negative',cwd=cwd,timeout=120)
        _,fake=decode(self.out/'fake-metadata-negative.o')
        self.check('actual-old-fake-metadata-detected',fake!=records and all(r['signature']=='12' for r in fake))
        stock=argv.copy();stock[0]=str(NDK/'clang');stock[stock.index('-o')+1]=str(self.out/'must-not-compile-metadata.o');stock[stock.index('-MF')+1]=str(self.out/'stock-metadata.d')
        code,_,error=self.run(stock,'stock-compiler-missing-real-builtins',cwd=cwd,timeout=120)
        self.check('stock-compiler-cannot-silently-replace-metadata',code!=0 and '__builtin_xnu_type_' in error and not (self.out/'must-not-compile-metadata.o').exists(),exit_code=code)
        self.report['allocator_metadata']=dict(layout=layout,records=records,type_sizes=sizes,type_summaries=summaries,type_signatures=signatures,fake_records=fake,private_Apple_oracle_qualified=False)

    def alias_controls(self):
        subset=self.out/'real-VM-aliases.exp'
        subset.write_text(''.join(r['target']+' '+name+'\n' for name,r in self.report['native_VM_aliases'].items()))
        objects=[ROOT/self.by_id[n]['output'] for n in ['osfmk/vm_user.o','osfmk/vm_fault.o']];output=self.out/'genuine-VM-aliases.o'
        self.must([self.ld,'-r','-arch','arm64','-alias_list',subset,*objects,'-o',output],'actual-genuine-VM-alias-relocatable-link',timeout=180)
        view=thin(output);symbols={s['name']:s for s in view['symbols'] if s['type']&1 and s['type']&0xe==0xe}
        values={}
        for name,row in self.report['native_VM_aliases'].items():
            target=row['target'];same=name in symbols and target in symbols and (symbols[name]['section'],symbols[name]['value'])==(symbols[target]['section'],symbols[target]['value'])
            self.check('actual-real-VM-code-alias-'+name,same)
            values[name]=dict(target=target,same_real_code=same,alias=symbols.get(name),provider=symbols.get(target))
        self.report['actual_VM_alias_link']=dict(object=str(output.relative_to(ROOT)),sha256=sha(output),aliases=values,scope='Relocatable link of two genuine VM objects and exact native three-name subset;other kernel imports retained;not a full kernel')
        wrong=self.out/'wrong-real-provider-aliases.exp'
        wrong.write_text(subset.read_text().replace('_vm_fault_external _vm_fault','_mach_vm_allocate_external _vm_fault'))
        changed=self.out/'wrong-real-provider-aliases.o'
        self.must([self.ld,'-r','-arch','arm64','-alias_list',wrong,*objects,'-o',changed],'negative-wrong-real-VM-provider-link',timeout=180)
        negative={s['name']:s for s in thin(changed)['symbols'] if s['type']&1 and s['type']&0xe==0xe}
        name='_vm_fault';target='_vm_fault_external'
        mismatch=(negative[name]['section'],negative[name]['value'])!=(negative[target]['section'],negative[target]['value'])
        self.check('wrong-real-VM-provider-alias-detected',mismatch)
        self.report['negative_VM_alias']=dict(object=str(changed.relative_to(ROOT)),sha256=sha(changed),same_public_name_binds_wrong_real_function=mismatch,runtime_executed=False)

    def native_mig(self):
        self.object_component();header=self.header_component();self.host_commands()
        host=ROOT/'artifacts/xnu-host-tools/generators-session2/prefix/bin'
        directory=KERNEL/'osfmk/mach';cwd=self.out/'native-MIG';cwd.mkdir()
        query=cwd/'query.mk';query.write_text('include '+str(directory/'Makefile')+'\n$(info S24_NATIVE_MIG|$(MIG_UUHDRS))\n.PHONY: s24_query\ns24_query: ;\n')
        args=self.header_make_args(directory,query,cwd)
        args+=['MIG='+str(host/'mig'),'MIGCOM='+str(host/'migcom'),'MIGCC='+str(self.compiler)]
        installed=json.loads((ROOT/self.report['installed_header_profile']['manifest']).read_text())
        wrapper=self.out/'preprocess.py';shutil.copyfile(ROOT/'fixtures/public/xnu-kernel-mig/preprocess.py',wrapper);wrapper.chmod(0o755)
        tmp=self.out/'tmp';tmp.mkdir();results=[]
        for name in ['mach_port.h','task.h','mach_vm.h','thread_act.h']:
            goal=args.copy();goal[goal.index('s24_query')]='-n';goal.append(name)
            text=self.must(goal,'native-SDK-MIG-recipe-'+name,cwd=cwd,timeout=60)
            commands=[shlex.split(l) for l in text.replace('\\\n',' ').splitlines() if l.startswith(str(host/'mig')+' ')]
            if len(commands)!=1:raise ValueError('One genuine native SDK MIG command required')
            command=commands[0];source=Path(command[-1]).resolve()
            if not source.is_relative_to(KERNEL) or not source.is_file():raise ValueError('Actual pinned MIG defs source required')
            trace=self.out/'preprocessing'/name;trace.mkdir(parents=True)
            env=['env','MIGCC='+str(wrapper),'MIGCOM='+str(host/'migcom'),'SDKROOT=','TMPDIR='+str(tmp),
                'S24_MIG_COMPILER='+str(self.compiler),'S24_MIG_TRACE='+str(trace),'S24_MIG_SOURCE='+str(source)]
            self.must([*env,*command],'fresh-native-SDK-MIG-'+name,cwd=cwd,timeout=120)
            private=ROOT/header['header_roots']['private']/'mach'/name
            row=next(r for r in installed if (ROOT/r['output']).resolve()==private.resolve() and r['private'])
            output=self.out/('native-installed-'+name)
            code,_,error=self.run([UNIFDEF,*row['unifdef_flags'],'-o',output,cwd/name],'fresh-native-SDK-unifdef-'+name,cwd=cwd,timeout=60)
            good=code in [0,1] and output.is_file() and sha(output)==sha(private)
            self.check('actual-native-SDK-MIG-header-identical-'+name,good,exit_code=code,diagnostic=error[-1500:])
            results.append(dict(name=name,defs_source=str(source.relative_to(ROOT)),defs_sha256=sha(source),fresh_raw_header=str((cwd/name).relative_to(ROOT)),fresh_raw_sha256=sha(cwd/name),
                native_installed_header=str(output.relative_to(ROOT)),native_installed_sha256=sha(output),qualified_header=str(private.relative_to(ROOT)),qualified_sha256=sha(private),identical=good,
                preprocessor_provenance=str((trace/'provenance.json').relative_to(ROOT)),preprocessor_provenance_sha256=sha(trace/'provenance.json')))
        self.report['fresh_native_SDK_MIG_headers']=results

    def acceptance(self):
        """Revalidate measured bytes and assess this component's four criteria."""
        reports={};capsules={}
        for identifier in ['PTHP-005','PTHP-007','PTHP-008','PTHP-009','PTHP-011']:
            doc=registered(identifier,self.ledger)
            paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
            if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('Passing component capsule required: '+identifier)
            report=json.loads(paths[0].read_text())
            self.check('revalidated-capsule-'+identifier,report['outcome']=='pass' and all(c['pass_check'] for c in report['checks']))
            entry=next(e for e in self.ledger['experiments'] if e['id']==identifier)
            capsules[identifier]=dict(evidence=entry['evidence'],sha256=entry['evidence_sha256'],artifacts_verified=len(doc['sha256']))
            reports[identifier]=report
        header=self.header_component();component=self.object_component()
        manifest=json.loads((ROOT/self.report['installed_header_profile']['manifest']).read_text())
        self.check('all-header-sources-and-native-declarations-unchanged',all(
            (not row.get('source_sha256') or sha(ROOT/row['source'])==row['source_sha256']) and
            sha(ROOT/row['declaration'])==row['declaration_sha256'] for row in manifest))
        self.check('missing-generated-inputs-remain-explicitly-unavailable',all(
            not (ROOT/row['output']).exists() for row in manifest if row['status']=='unavailable_generated_input'))
        closure=component['pthread_provider_closure'];archive=ROOT/closure['archive']
        members=archive_members(archive.read_bytes())
        self.check('actual-three-archive-members-revalidated',sha(archive)==closure['sha256'] and len(members)==3 and all(
            name==Path(row['output']).name and data==(ROOT/row['output']).read_bytes()
            for (name,data),row in zip(members,component['pthread_compile_results'])))
        definitions=self.must([NDK/'llvm-nm','--extern-only','--defined-only','--just-symbol-name',archive],'acceptance-archive-definitions')
        required=self.must([NDK/'llvm-nm','--undefined-only','--just-symbol-name',archive],'acceptance-archive-imports')
        defs={n for n in definitions.splitlines() if n and not n.endswith(':')}
        imports={n for n in required.splitlines() if n and not n.endswith(':')}-defs
        providers=json.loads((SGAP/'symbol-providers.json').read_text())
        aliases={n:r['target'] for n,r in self.report['native_VM_aliases'].items()}
        unresolved=sorted(n for n in imports if n not in providers and aliases.get(n) not in providers)
        overlaps=sorted(defs & providers.keys())
        self.check('all-actual-imports-and-exports-match-witness',sorted(defs)==closure['defined'] and sorted(imports)==closure['external_imports'])
        self.check('all-imports-resolve-with-no-kernel-definition-overlap',not unresolved and not overlaps,unresolved=unresolved,overlaps=overlaps)
        layout=reports['PTHP-008']['callback_layout'];count=len(layout['names']);observed={}
        for label,probe in layout['probes'].items():
            obj=ObjectData(ROOT/probe['object']);observed[label]=list(obj.value('_s24_pthread_layout','<'+str(count)+'Q'))
            self.check('actual-callback-object-redecoded-'+label,observed[label]==probe['layout'] and list(obj.value('_s24_kalloc_layout','<4Q'))==[64,32,40,44])
        self.check('all-140-declarations-and-284-layout-values-covered',count==284 and
            {n:len(v) for n,v in layout['fields'].items()}=={'pthread_functions_s':45,'pthread_callbacks_s':95} and
            observed['kext']==observed['kernel']==layout['clang19_values'])
        controls={c['name']:c['pass_check'] for c in reports['PTHP-008']['checks']}
        self.check('real-header-type-and-metadata-controls-executed',all(controls.get(n) for n in [
            'real-wrong-header-layout-detected','real-wrong-function-pointer-type-rejected',
            'real-two-allocation-descriptors-and-type-signatures','actual-old-fake-metadata-detected',
            'stock-compiler-cannot-silently-replace-metadata']))
        self.check('genuine-aliases-and-wrong-real-provider-control-executed',all(
            c['pass_check'] for c in reports['PTHP-009']['checks']) and reports['PTHP-009']['negative_VM_alias']['same_public_name_binds_wrong_real_function'])
        mig=reports['PTHP-011']['fresh_native_SDK_MIG_headers']
        self.check('all-four-native-SDK-MIG-generated-bytes-revalidated',len(mig)==4 and all(
            r['identical'] and sha(ROOT/r['native_installed_header'])==sha(ROOT/r['qualified_header'])==r['qualified_sha256'] for r in mig))
        profile=component['pthread_compile_profile']
        self.check('genuine-metadata-and-native-definitions-remain-enabled',profile['metadata_checks_enabled'] and
            not profile['raw_internal_header_fallback'] and not profile['fake_metadata_header_used'] and
            profile['native_definitions']==self.kext_definitions)
        if not self.args.integration_evidence:raise ValueError('Acceptance requires --integration-evidence')
        check=ROOT/self.args.integration_evidence
        if not check.resolve().is_relative_to(ROOT):raise ValueError('Main-relative integration evidence required')
        common=json.loads(check.read_text())
        for name,value in common['sha256'].items():
            if sha(ROOT/name)!=value:raise ValueError('Common check artifact changed')
        self.check('integrated-repository-checks-pass',common['outcome']=='pass' and any(
            c['argv']==['make','check'] and c['exit_code']==0 for c in common['commands']))
        if any(not c['pass_check'] for c in self.report['checks']):raise ValueError('Acceptance checks failed;component is not accepted')
        self.report['acceptance']=dict(criteria=[
            dict(criterion=1,result='pass',scope='Pinned native definitions,installed-header rules and current provider declarations'),
            dict(criterion=2,result='pass',scope='Three genuine ARM64 TUs,source-qualified installed headers and actual metadata builtins'),
            dict(criterion=3,result='pass',scope='All callback declarations/layouts,allocation metadata,archive/import closure and actual negative controls'),
            dict(criterion=4,result='pass',scope='Revalidated coherent component capsules and integrated repository checks;all full-system limits retained')],
            capsules=capsules,common_checks=dict(path=str(check.relative_to(ROOT)),sha256=sha(check),commit=common['commit']),
            archive=closure['archive'],archive_sha256=sha(archive),definitions=len(defs),external_imports=len(imports),
            overlap=overlaps,unresolved=unresolved,header_counts=header['header_install_counts'],callback_fields=140,layout_values=count,
            complete_SDK_qualified=False,stock_Xcode_release_qualified=False,private_Apple_ABI_qualified=False,
            full_crypto_qualified=False,full_link_qualified=False,runtime_qualified=False,native_device_qualified=False)

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Genuine pthread installed-header/source/native-alias host qualification;full SDK,Apple ABI,crypto,kernel/runtime/native unqualified'
        self.report['compiler_sha256']=sha(self.compiler) if hasattr(self,'compiler') else None;dump(self.out/'report.json',self.report)
        files=sorted(p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json')
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20],commands_scope='Representative actual commands;all executions in hashed report.json',actual_command_count=len(self.report['commands']),
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc);print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--mode',choices=['inventory','headers','compile','controls','aliases','sdk-mig','acceptance'],required=True)
    p.add_argument('--integration-evidence')
    p.add_argument('--header-profile',default='PTHP-005');p.add_argument('--object-profile',default='PTHP-007');args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Canonical fresh run required')
    args.compiler,args.compiler_evidence,args.header_evidence,args.resource_evidence=VECTOR_COMPILER,'VCOMP-002','FHDR-003','RHDR-002'
    args.storage_evidence='CXXST-007';args.port_evidence='KDECL-004';args.object_evidence='IIGOBJ-003';args.jobs=1
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));build=PthreadProfile(args)
    try:
        build.inputs()
        if args.mode=='headers':build.headers()
        elif args.mode=='compile':build.compile_pthread()
        elif args.mode=='controls':build.controls()
        elif args.mode=='aliases':build.alias_controls()
        elif args.mode=='sdk-mig':build.native_mig()
        elif args.mode=='acceptance':build.acceptance()
        else:build.inventory()
    except Exception as error:build.report['error']=str(error)
    return build.finish()


if __name__=='__main__':sys.exit(main())
