#!/usr/bin/env python3
"""Measure experimental IIG sources in genuine selected full IOKit recipes."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
from xnu_compiler_cxx_storage import Storage
from xnu_kernel_firehose_headers import COMPILER as VECTOR_COMPILER
from xnu_compiler_atomics import ROOT, KERNEL, KOBJECT, NDK, registered, sha, dump
from xnu_macho_tools import macho
from xnu_kernel_syscalls import ObjectData
import struct

FIXTURES=ROOT/'fixtures/public/xnu-kernel-iig-objects'
PARENT=ROOT/'artifacts/xnu-iig-abi/nyktis-invoke-guard-session1'
CURRENT=ROOT/'artifacts/xnu-compiler-cxx-storage/full-profile-session2'


class IigObjects(Storage):
    def __init__(self,args):
        self.args=args;self.out=ROOT/'artifacts/xnu-kernel-iig-objects'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Canonical fresh run required')
        self.out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text());self.ports={}
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',mode=args.mode,recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            commands=[],checks=[],kernel_cases=[],device_executed=False,sdk_used=False,global_install=False,
            experimental_generator=True,full_kernel_qualified=False,full_archive_link_qualified=False,full_crypto_qualified=False,
            apple_private_abi_qualified=False,apple_interoperability_qualified=False,native_device_qualified=False)

    def inputs(self):
        super().inputs();self.reuse_storage()
        for identifier in ['IIGABI-013','CXXST-006','CXXST-009','CXXST-010','CXXST-011','KTAIL-003','KTAIL-005','KTAIL-007','KTAIL-008']:
            registered(identifier,self.ledger);e=next(e for e in self.ledger['experiments'] if e['id']==identifier)
            self.report['parents'][identifier]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.current=json.loads((CURRENT/'report.json').read_text())
        self.missing=[r for r in self.object_report['inventory'] if r['id'].endswith('.iig.cpo')]
        if len(self.missing)!=17 or any(r['original_expanded_recipe'] is None for r in self.missing):raise ValueError('All17 genuine generated-object recipes required')
        manifest=json.loads((ROOT/'fixtures/public/xnu-kernel-direct-tail/unresolved-objects.json').read_text())
        if {r['id'] for r in manifest}!={r['id'] for r in self.missing}:raise ValueError('Exact current17 unresolved identities required')
        self.pair_root=self.out/'candidate/DriverKit';self.pair_root.mkdir(parents=True)
        self.report['candidate_pairs']=[]
        old=json.loads((PARENT/'report.json').read_text())
        for r in self.missing:
            name=Path(r['target']).name.removesuffix('.iig.cpo');pair={}
            idl=KERNEL/'iokit/DriverKit'/(name+'.iig')
            entry=next(e for e in old['selected_interfaces'] if e['name']==name)
            if sha(idl)!=entry['source_sha256']:raise ValueError('Selected IDL bytes changed')
            for suffix,key in [('.h','header_sha256'),('.iig.cpp','implementation_sha256')]:
                original=PARENT/'generated/DriverKit'/(name+suffix);copy=self.pair_root/original.name
                if sha(original)!=entry[key]:raise ValueError('Witnessed candidate pair changed')
                shutil.copyfile(original,copy)
                pair[suffix]=dict(original=str(original.relative_to(ROOT)),copy=str(copy.relative_to(ROOT)),sha256=sha(copy))
            self.report['candidate_pairs'].append(dict(name=name,idl=str(idl.relative_to(ROOT)),idl_sha256=sha(idl),files=pair))
        self.report['generator']=dict(path=str((PARENT/'iig').relative_to(ROOT)),sha256=sha(PARENT/'iig'),evidence='IIGABI-013',
            upstream_revision='ea6d147d668ca15d490da638012243fcd705f30d',selected_apple_oracle=False)
        for p in [*FIXTURES.glob('*.cpp'),*FIXTURES.glob('*.c')]:shutil.copyfile(p,self.out/'fixture-inputs'/p.name)
        self.report['fixture_files_sha256']={p.name:sha(p) for p in (self.out/'fixture-inputs').iterdir()}
        self.bind_profile()

    @staticmethod
    def canonical(argv):
        argv=argv.copy()
        for f in ['-o','-MF']:argv[argv.index(f)+1]='OUTPUT'+f
        source=next((i for i,a in enumerate(argv) if a.endswith('.cpp')),None)
        if source is None:raise ValueError('One original C++ source argument required')
        argv[source]='SOURCE'
        return argv

    def bind_profile(self):
        oldrow=next(r for r in self.object_report['inventory'] if r['id']=='iokit/IOService.cpo')
        old=next(c for c in self.object_report['commands'] if c['stdout'].endswith('/compile-iokit-IOService.cpo.stdout.txt'))
        new=next(c for c in self.current['commands'] if c['stdout'].endswith('/compile-iokit-IOService.cpo.stdout.txt'))
        self.cwd=Path(new['cwd'])
        if old['cwd']!=new['cwd']:raise ValueError('Current IOKit cwd must match genuine original')
        raw=shlex.split(oldrow['original_expanded_recipe'])
        self.old_raw=raw
        oldargv=old['argv'].copy();newargv=new['argv'].copy()
        if oldargv[1]!='-o' or newargv.count('-o')!=1:raise ValueError('Original actual compile shape changed')
        first_o=newargv.index('-o');self.prefix=newargv[:first_o]
        if self.prefix[0]!=str(self.compiler) or any(a!='-I' for a in self.prefix[1::2]):raise ValueError('Current global include prefix differs')
        # The genuine old compiler appended witnessed source include roots.
        # Current coherent MIG replaced the two old partial Mach roots only.
        source=oldargv.index(str(ROOT/oldrow['source']))
        if source!=len(raw)-1:raise ValueError('Original raw/actual C++ source position differs')
        self.extra=oldargv[source+1:]
        old_mach=[PARENT/'mach-server-headers',ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/mach-headers']
        for path in old_mach:
            index=self.extra.index(str(path))
            if index<1 or self.extra[index-1]!='-I':raise ValueError('Exact former partial MIG root required')
            del self.extra[index-1:index+1]
        check=raw.copy();check[0:1]=self.prefix
        check[check.index('-o')+1]=newargv[newargv.index('-o')+1]
        check[check.index('-MF')+1]=newargv[newargv.index('-MF')+1]
        check[-1]=str(ROOT/oldrow['source']);check+=self.extra
        if check!=newargv:raise ValueError('Derived genuine current compiler/header delta does not reproduce actual IOKit recipe')
        self.report['full_profile_binding']=dict(original_reference='iokit/IOService.cpo',original_recipe=oldrow['original_expanded_recipe'],
            current_argv=newargv,cwd=str(self.cwd),compiler_include_prefix=self.prefix,retained_appended_includes=self.extra,
            removed_former_Mach_roots=list(map(str,old_mach)),source='Genuine original expanded recipe plus exact current global-only compiler/header delta')
        self.check('derived-profile-exactly-reproduces-current-IOKit-command',True)

    def command_iig(self,row,output,source=None):
        argv=shlex.split(row['original_expanded_recipe'])
        forced=[argv[i+1] for i,a in enumerate(argv) if a=='-include']
        genuine=[self.old_raw[i+1] for i,a in enumerate(self.old_raw) if a=='-include']
        if argv[0]!=self.old_raw[0] or '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or forced!=genuine:
            raise ValueError('Keep actual source compiler profile and enabled metadata checks')
        original=Path(row['source']);indices=[i for i,a in enumerate(argv) if (self.cwd/a).resolve()==(ROOT/original).resolve()]
        if len(indices)!=1:raise ValueError('One actual source binding required')
        argv[indices[0]]=str(source or self.pair_root/Path(row['source']).name)
        argv[argv.index('-o')+1]=str(output);argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
        argv[0:1]=self.prefix;argv+=self.extra
        return argv

    def compile_iig(self):
        self.report['compile_results']=[]
        for row in self.missing:
            output=self.out/'objects/iokit'/row['target'];output.parent.mkdir(parents=True,exist_ok=True)
            argv=self.command_iig(row,output);source=self.pair_root/Path(row['source']).name
            code,_,error=self.run(argv,'compile-'+row['target'],cwd=self.cwd,timeout=120)
            good=code==0 and output.is_file() and macho(output)['filetype']==1
            self.report['compile_results'].append(dict(id=row['id'],source=str(source.relative_to(ROOT)),source_sha256=sha(source),
                output=str(output.relative_to(ROOT)) if good else None,output_sha256=sha(output) if good else None,
                exit_code=code,actual_arm64_object=good,errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$',error)[:12],diagnostic=error[-3000:]))
        rows=self.report['compile_results']
        self.check('all17-genuine-full-recipes-attempted',len(rows)==17 and all(r['exit_code'] in [0,1] for r in rows))
        self.report['coverage']=dict(attempted=17,actual_arm64=sum(r['actual_arm64_object'] for r in rows),parent_direct_objects=965,
            experimental_private_ABI_qualified=False)
        self.check('all17-actual-full-profile-objects',all(r['actual_arm64_object'] for r in rows))

    def regenerate(self):
        parent=json.loads((PARENT/'report.json').read_text());root=self.out/'regenerated/DriverKit';root.mkdir(parents=True)
        self.report['regenerated_pairs']=[]
        for pair in self.report['candidate_pairs']:
            name=pair['name'];command=next(c for c in parent['commands'] if c['argv'][0]==str(PARENT/'iig') and
                '--def' in c['argv'] and c['argv'][c['argv'].index('--def')+1]==str(ROOT/pair['idl']))
            argv=command['argv'].copy();header=root/(name+'.h');source=root/(name+'.iig.cpp')
            argv[argv.index('--header')+1]=str(header);argv[argv.index('--impl')+1]=str(source)
            self.must(argv,'regenerate-'+name,timeout=90)
            same=sha(header)==pair['files']['.h']['sha256'] and sha(source)==pair['files']['.iig.cpp']['sha256']
            self.check('exact-pair-regeneration-'+name,same)
            self.report['regenerated_pairs'].append(dict(name=name,header=str(header.relative_to(ROOT)),header_sha256=sha(header),
                implementation=str(source.relative_to(ROOT)),implementation_sha256=sha(source),matches_witnessed_pair=same))
        if not all(p['matches_witnessed_pair'] for p in self.report['regenerated_pairs']):
            raise ValueError('Header/source semantics changed;do not reuse965 old objects as a coherent graph')
        self.pair_root=root

    def reuse_objects(self):
        if not self.args.object_evidence:raise ValueError('Explicit passing regenerated full-recipe experiment required')
        doc=registered(self.args.object_evidence,self.ledger);paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('One passing regenerated full-recipe report required')
        r=json.loads(paths[0].read_text())
        if r['compiler_sha256']!=sha(self.compiler) or len(r.get('regenerated_pairs',[]))!=17 or len(r['compile_results'])!=17:
            raise ValueError('Exact current experimental compiler,17 regenerated pairs and17 full objects required')
        for row in r['compile_results']:
            if not row['actual_arm64_object'] or sha(ROOT/row['source'])!=row['source_sha256'] or sha(ROOT/row['output'])!=row['output_sha256']:
                raise ValueError('Recorded actual IIG source/output changed')
        self.object_parent=r;self.object_path=paths[0]
        self.report['object_parent']=dict(experiment=self.args.object_evidence,report=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        self.pair_root=ROOT/Path(r['regenerated_pairs'][0]['implementation']).parent

    def controls(self):
        observed={}
        for cls,method,service,wanted in [('OSObject','CopyDispatchQueue',0,(348,84,52,296,32,1)),
                                        ('IOService','Start',1,(108,60,68,40,32,2))]:
            text=self.must([PARENT/'selected-hash',cls,method],'source-hash-'+cls)
            identifier=int(text.strip(),16)
            expected=(24,0,8,16,20,36,16,24,*wanted,identifier)
            row=next(r for r in self.missing if r['target']==cls+'.iig.cpo')
            obj=self.out/(cls+'-message-layout.o')
            argv=self.command_iig(row,obj,source=self.out/'fixture-inputs/message-layout.cpp')
            argv+=['-DS24_SERVICE='+str(service),'-DS24_GENERATED_IMPLEMENTATION="'+str(self.pair_root/(cls+'.iig.cpp'))+'"']
            self.must(argv,'actual-message-layout-'+cls,cwd=self.cwd)
            values=ObjectData(obj).value('_s24_iig_layout','<15Q')
            self.check('selected-public-generated-layout-'+cls,values==expected,observed=values,expected=expected,
                private_Apple_oracle=False)
            observed[cls]=dict(object=str(obj.relative_to(ROOT)),sha256=sha(obj),values=values,source_algorithm_ID=identifier)
            for mode,index in [('layout',0),('id',14)]:
                data=ObjectData(obj);_,_,position=data.location('_s24_iig_layout',120)
                raw=bytearray(data.data);struct.pack_into('<Q',raw,position+8*index,values[index]^8)
                path=self.out/(cls+'-wrong-'+mode+'.o');path.write_bytes(raw)
                self.check(cls+'-reject-real-'+mode+'-mutation',ObjectData(path).value('_s24_iig_layout','<15Q')!=expected)
            if service:
                stale=self.out/'stale-header/DriverKit';stale.mkdir(parents=True)
                header=self.pair_root/'IOService.h';text=header.read_text()
                target=re.search(r'(?m)^(#define IOService_Start_ID\s+)0x([0-9a-fA-F]+)ULL',text)
                if not target:raise ValueError('Exact actual generated Start ID macro required')
                text=text[:target.start()]+target[1]+hex(identifier^1)+'ULL'+text[target.end():]
                (stale/header.name).write_text(text)
                mutated=self.out/'stale-header-probe.o';args=argv.copy()
                args[1:1]=['-I',str(stale.parent)];args[args.index('-o')+1]=str(mutated);args[args.index('-MF')+1]=str(mutated.with_suffix('.d'))
                self.must(args,'actual-stale-header-compile',cwd=self.cwd)
                changed=ObjectData(mutated).value('_s24_iig_layout','<15Q')
                self.check('compiled-stale-header-ID-detected',changed[:-1]==expected[:-1] and changed[-1]==identifier^1 and changed!=expected)
        self.report['actual_message_representations']=observed
        public=self.out/'fixture-inputs/public-message-layout.cpp'
        row=next(r for r in self.missing if r['target']=='IOService.iig.cpo')
        for label,compiler in [('source17',self.compiler),('independent19',NDK/'clang')]:
            obj=self.out/(label+'-public-layout.o');argv=self.command_iig(row,obj,source=public);argv[0]=str(compiler)
            if label=='independent19':argv.remove('-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang')
            self.must(argv,label+'-public-message-layout',cwd=self.cwd)
            values=ObjectData(obj).value('_s24_public_layout','<19Q')
            self.check(label+'-independent-public-message-layout',values==(24,0,8,16,20,36,16,24,108,68,40,348,52,296,8,4,32,4,12),observed=values)
        self.host_decoder()

    def host_decoder(self):
        parent=json.loads((PARENT/'report.json').read_text());commands={Path(c['stdout']).name:c for c in parent['commands']}
        obj=self.out/'host-runtime.o';page=self.out/'host-guard-page.o';exe=self.out/'copy-dispatch-runtime'
        replacements={str(PARENT/'generated'):str(self.pair_root.parent),str(PARENT/'host-runtime.o'):str(obj),
            str(PARENT/'host-guard-page.o'):str(page),str(PARENT/'copy-dispatch-runtime'):str(exe)}
        for label in ['host-guard-page-compile','host-runtime-compile','host-runtime-link']:
            key=label+'.stdout.txt'
            if key not in commands:
                matches=[k for k in commands if 'guard-page' in k]
                raise ValueError('Exact recorded host command required: '+key+' available '+str(matches))
            c=commands[key];argv=[replacements.get(a,a) for a in c['argv']]
            self.must(argv,label,timeout=120)
        cases=[]
        for mode in ['g','s','r','d','o','n','e','t','z','u','f']:
            code,_,error=self.run([exe,mode],'host-decoder-'+mode,timeout=20)
            self.check('actual-host-decoder-'+mode,code==0,exit_code=code,diagnostic=error[-1000:]);cases.append(dict(mode=mode,exit_code=code))
        self.report['host_decoder']=dict(cases=cases,architecture='x86_64-linux',actual_ARM_execution=False,
            selected_Apple_ABI_qualified=False,sanitizers_used=False,scope='Only actual CopyDispatchQueue_Invoke with genuine guard-page helper')

    @staticmethod
    def external_symbols(path):
        data=path.read_bytes();macho(path);at=32;symtab=None
        for _ in range(struct.unpack_from('<I',data,16)[0]):
            cmd,length=struct.unpack_from('<II',data,at)
            if cmd==2:symtab=struct.unpack_from('<4I',data,at+8)
            at+=length
        if symtab is None:raise ValueError('Actual symbol table required')
        offset,count,strings,size=symtab
        if offset>len(data) or count>(len(data)-offset)//16 or strings>len(data) or size>len(data)-strings:
            raise ValueError('Actual symbol extent')
        result=[]
        for i in range(count):
            index,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,offset+16*i)
            if kind&0xe0 or not kind&1:continue
            end=data.find(b'\0',strings+index,strings+size) if index<size else -1
            if end<0:raise ValueError('External symbol string extent')
            name=data[strings+index:end].decode('ascii');typ=kind&0xe
            definition=typ in {2,0xe,0xa} or (typ==0 and value!=0)
            if typ not in {0,2,0xe,0xa}:raise ValueError('Unreviewed external symbol type')
            result.append(dict(name=name,defined=definition,weak=bool(desc&(0x80 if definition else 0x40)),
                type=typ,value=value,section=section,common=typ==0 and value!=0,alias=typ==0xa))
        return result

    def audit(self):
        parent=ROOT/'artifacts/xnu-kernel-direct-tail/audit-session1'
        compiled=json.loads((parent/'compiled-objects.json').read_text());unresolved=json.loads((parent/'unresolved-objects.json').read_text())
        inputs=json.loads((parent/'dependency-files.json').read_text());dependencies=json.loads((parent/'object-dependencies.json').read_text())
        if len(compiled)!=965 or len(unresolved)!=17 or len(dependencies)!=965:raise ValueError('Complete current965/17 inventory required')
        for name,h in inputs.items():
            if sha(ROOT/name)!=h:raise ValueError('Previous965 input changed')
        objects=[]
        for row in compiled:
            p=ROOT/row['output']
            if sha(p)!=row['output_sha256'] or sha(ROOT/row['source'])!=row['source_sha256']:raise ValueError('Prior965 source/object changed')
            objects.append(p)
        missing={r['id']:r for r in self.missing};new_ids=set()
        for row in self.object_parent['compile_results']:
            identifier=row['id'];before=missing[identifier];obj=ROOT/row['output'];new_ids.add(identifier)
            command=next(c for c in self.object_parent['commands'] if c['stdout'].endswith('/compile-'+before['target']+'.stdout.txt'))
            expected=self.command_iig(before,obj,source=ROOT/row['source'])
            if command['argv']!=expected or command['cwd']!=str(self.cwd) or command['exit_code']!=0 or command['timed_out']:
                raise ValueError('Actual new IIG recipe differs from genuine current profile')
            if sha(obj)!=row['output_sha256'] or sha(ROOT/row['source'])!=row['source_sha256']:raise ValueError('Current actual IIG bytes changed')
            dep=obj.with_suffix('.d');line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(self.cwd/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            own_header=PARENT/'generated/DriverKit'/(before['target'].removesuffix('.iig.cpo')+'.h')
            if own_header.resolve() not in files or (ROOT/row['source']).resolve() not in files:
                raise ValueError('Actual per-class header/source absent from new dependency graph')
            names=[]
            for p in files:
                name=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                if name in inputs and inputs[name]!=sha(p):raise ValueError('Shared header semantics changed')
                inputs[name]=sha(p);names.append(name)
            dependencies[identifier]=dict(depfile=str(dep.relative_to(ROOT)),depfile_sha256=sha(dep),inputs=sorted(set(names)))
            compiled.append(row);objects.append(obj)
        for pair in self.object_parent['regenerated_pairs']:
            old=PARENT/'generated/DriverKit'/(pair['name']+'.h')
            if not sha(ROOT/pair['header'])==sha(old)==pair['header_sha256']:
                raise ValueError('Regenerated/shared header mismatch')
            self.check('unchanged-shared-header-'+pair['name'],sha(ROOT/pair['header'])==sha(old)==pair['header_sha256'])
        self.check('all982-known-direct-object-accounting',len(compiled)==982 and len({r['id'] for r in compiled})==982 and new_ids=={r['id'] for r in unresolved})
        text=self.must([NDK/'llvm-readobj','--file-headers',*objects],'all982-independent-headers',timeout=120)
        self.check('all982-real-ARM64-headers',text.count('Format: Mach-O arm64')==982)
        text=self.must([NDK/'llvm-nm','--defined-only','--format=posix',*objects],'all982-independent-code-symbols',timeout=120)
        kinds=Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+',text))
        providers=defaultdict(list);consumers=defaultdict(list);expected_defs={}
        for row,p in zip(compiled,objects):
            external=self.external_symbols(p);expected_defs[str(p)]={s['name'] for s in external if s['defined']}
            for s in external:
                item=dict(object=row['id'],weak=s['weak'],common=s['common'],alias=s['alias'])
                (providers if s['defined'] else consumers)[s['name']].append(item)
        text=self.must([NDK/'llvm-nm','--extern-only','--defined-only','--format=posix',*objects],'all982-independent-external-symbols',timeout=120)
        seen={};current=None
        for line in text.splitlines():
            if line.endswith(':') and line[:-1] in expected_defs:current=line[:-1];seen[current]=set()
            elif current and len(a:=line.split())>=3 and len(a[1])==1:seen[current].add(a[0])
        self.check('all982-independent-external-symbol-map',seen==expected_defs,objects=len(seen))
        duplicate={n:v for n,v in providers.items() if len([s for s in v if not s['weak'] and not s['common']])>1}
        baseline_duplicate={n:v for n,v in providers.items() if len([s for s in v if s['object'] not in new_ids and not s['weak'] and not s['common']])>1}
        introduced={n:v for n,v in duplicate.items() if n not in baseline_duplicate}
        missing_required={n:v for n,v in consumers.items() if n not in providers and any(not s['weak'] for s in v)}
        missing_new={n:v for n,v in missing_required.items() if any(s['object'] in new_ids and not s['weak'] for s in v)}
        self.report['link_symbol_status']=dict(external_providers=len(providers),external_consumer_names=len(consumers),
            unresolved_required_names=len(missing_required),unresolved_new_IIG_names=len(missing_new),
            existing_strong_duplicate_names=len(baseline_duplicate),all_strong_duplicate_names=len(duplicate),introduced_strong_duplicate_names=len(introduced),
            actual_link_attempted=False,full_link_closure_qualified=False)
        self.report['coverage']=dict(selected_components=978,actual_component_arm64=978,actual_direct_arm64=982,known_direct_objects=982,
            unresolved_direct_objects=0,new_generated_objects=17,prior_objects_retained=965,prior_objects_recompiled=False,
            unique_dependency_files=len(inputs),defined_symbol_types=dict(kinds),experimental_generator=True,full_Apple_ABI_qualified=False)
        for name,value in [('compiled-objects',compiled),('unresolved-objects',[]),('dependency-files',inputs),('object-dependencies',dependencies),
            ('symbol-providers',dict(providers)),('symbol-consumers',dict(consumers)),('unresolved-symbols',missing_required),('new-IIG-unresolved-symbols',missing_new),
            ('strong-duplicate-symbols',duplicate),('introduced-strong-duplicate-symbols',introduced)]:dump(self.out/(name+'.json'),value)

    def acceptance(self):
        reports={}
        for identifier in [self.args.object_evidence,self.args.controls_evidence,self.args.audit_evidence]:
            doc=registered(identifier,self.ledger);paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
            if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('One passing actual source/control/audit report required')
            reports[identifier]=(paths[0],json.loads(paths[0].read_text()))
        source=reports[self.args.object_evidence][1];controls=reports[self.args.controls_evidence][1]
        audit_path,audit=reports[self.args.audit_evidence]
        self.check('all17-genuine-full-recipe-objects',len(source['compile_results'])==17 and all(r['actual_arm64_object'] for r in source['compile_results']))
        self.check('all34-regenerated-source-and-header-bytes',len(source['regenerated_pairs'])==17 and all(p['matches_witnessed_pair'] for p in source['regenerated_pairs']))
        public=ROOT/'references/apple-xnu';revision='c54f35ca767986246321eb901baf8f5ff7923f6a'
        for i,pair in enumerate(source['candidate_pairs']):
            relative=str((ROOT/pair['idl']).relative_to(KERNEL));label='actual-public-IDL-'+str(i)
            self.must(['git','-C',public,'show',revision+':'+relative],label)
            self.check('selected-public-IDL-'+pair['name'],sha(self.out/(label+'.stdout.txt'))==pair['idl_sha256']==sha(ROOT/pair['idl']))
        self.check('all22-current-protocol-and-host-controls',len(controls['checks'])==22 and all(c['pass_check'] for c in controls['checks']))
        for cls,data in controls['actual_message_representations'].items():
            p=ROOT/data['object']
            self.check('actual-target-message-probe-'+cls,sha(p)==data['sha256'] and list(ObjectData(p).value('_s24_iig_layout','<15Q'))==data['values'])
        self.check('all11-actual-host-decoder-cases',len(controls['host_decoder']['cases'])==11 and all(c['exit_code']==0 for c in controls['host_decoder']['cases']))
        dependencies=json.loads((audit_path.parent/'dependency-files.json').read_text())
        for path,h in dependencies.items():
            if sha(ROOT/path)!=h:raise ValueError('Actual current complete982 dependency changed')
        compiled=json.loads((audit_path.parent/'compiled-objects.json').read_text())
        for row in compiled:
            if sha(ROOT/row['source'])!=row['source_sha256'] or sha(ROOT/row['output'])!=row['output_sha256'] or macho(ROOT/row['output'])['filetype']!=1:
                raise ValueError('Complete982 actual source/object bytes changed')
        self.check('actual982-object-and-source-header-graph',len(compiled)==982 and len({r['id'] for r in compiled})==982 and
            audit['coverage']['prior_objects_retained']==965 and audit['coverage']['unresolved_direct_objects']==0)
        links=audit['link_symbol_status']
        self.check('independent-symbol-audit-retained-with-real-limits',links['all_strong_duplicate_names']==0 and links['unresolved_new_IIG_names']==0 and
            links['unresolved_required_names']==22 and not links['actual_link_attempted'] and not links['full_link_closure_qualified'])
        self.check('all-private-Apple-runtime-crypto-native-limits-false',all(not r[key] for p,r in reports.values() for key in
            ['apple_private_abi_qualified','apple_interoperability_qualified','full_kernel_qualified','full_archive_link_qualified','full_crypto_qualified','device_executed','native_device_qualified']))
        self.report['coverage']=audit['coverage'];self.report['link_symbol_status']=links
        self.report['acceptance_reports']={k:dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for k,(p,r) in reports.items()}
        self.must(['make','check'],'repository-check',timeout=300);self.check('required-repository-checks',True)
        self.must(['git','diff','--check'],'whitespace-check');self.must(['git','diff','--cached','--check'],'staged-whitespace-check')
        good=all(c['pass_check'] for c in self.report['checks'])
        self.report['acceptance_assessment']=[dict(criterion=i+1,pass_check=good,evidence=e) for i,e in enumerate([
            [self.args.object_evidence,'full_profile_binding','public-IDL checks'],
            [self.args.object_evidence,'all17 genuine current commands,unchanged34 candidate bytes'],
            [self.args.controls_evidence,self.args.audit_evidence,'actual982 source/header/dependency/object/symbol graph'],
            [self.args.audit_evidence,'qualified-component.json','explicit source/generator/SDK/link/Apple-ABI/native gates','make check']])]

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Experimental candidate IIG full-recipe integration;Apple ABI/full kernel/archive/link/crypto/native qualification remains false'
        self.report['compiler_sha256']=sha(self.compiler) if hasattr(self,'compiler') else None
        dump(self.out/'report.json',self.report)
        files=sorted(p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json')
        if self.args.mode=='acceptance':
            files=sorted(set(files+[Path(__file__),ROOT/'docs/procedures/xnu-kernel-iig-objects.md',
                *[p for base in [FIXTURES,ROOT/'patches/kernel-iig-objects'] for p in base.rglob('*') if p.is_file()]]))
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20],commands_scope='Representative actual commands;all executions in hashed report.json',actual_command_count=len(self.report['commands']),
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),coverage=self.report.get('coverage'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['baseline','regenerate','controls','audit','acceptance'],required=True)
    p.add_argument('--object-evidence');p.add_argument('--controls-evidence');p.add_argument('--audit-evidence');args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Canonical fresh run required')
    args.compiler,args.compiler_evidence,args.header_evidence,args.resource_evidence=VECTOR_COMPILER,'VCOMP-002','FHDR-003','RHDR-002'
    args.storage_evidence='CXXST-007';args.port_evidence='KDECL-004';args.jobs=1
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));build=IigObjects(args)
    try:
        build.inputs()
        if args.mode in ['controls','audit','acceptance']:
            build.reuse_objects()
            if args.mode=='controls':build.controls()
            elif args.mode=='audit':build.audit()
            else:build.acceptance()
        else:
            if args.mode=='regenerate':build.regenerate()
            build.compile_iig()
    except Exception as error:build.report['error']=str(error)
    return build.finish()


if __name__=='__main__':sys.exit(main())
