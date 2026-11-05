#!/usr/bin/env python3
"""Build genuine selected kernel filelists/archives and measure link providers."""
from __future__ import annotations
import argparse
import hashlib
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import plistlib
import re
import resource
import shlex
import shutil
import subprocess
import sys
from xnu_kernel_iig_objects import IigObjects
from xnu_kernel_direct_tail import expected_rename,thin
from xnu_compiler_atomics import ROOT,KERNEL,NDK,registered,sha,dump
from xnu_kernel_firehose_headers import COMPILER as VECTOR_COMPILER

FIXTURES=ROOT/'fixtures/public/xnu-kernel-link-inputs'
AUDIT=ROOT/'artifacts/xnu-kernel-iig-objects/audit-session1'


def archive_members(data):
    """Read BSD ar member payloads by ordinal, including duplicate names."""
    if data[:8]!=b'!<arch>\n':raise ValueError('Not an ar archive')
    offset=8;result=[]
    while offset<len(data):
        header=data[offset:offset+60]
        if len(header)!=60 or header[58:]!=b'`\n':raise ValueError('Truncated ar header')
        if not header[48:58].strip().isdigit():raise ValueError('Invalid ar member length')
        length=int(header[48:58]);name=header[:16].decode('ascii').strip()
        payload=data[offset+60:offset+60+length]
        if len(payload)!=length:raise ValueError('Truncated ar member')
        if name.startswith('#1/'):
            size=int(name[3:])
            if size>len(payload):raise ValueError('Truncated BSD member name')
            name=payload[:size].rstrip(b'\0').decode('utf-8');payload=payload[size:]
        else:name=name.rstrip('/')
        if not name.startswith('__.SYMDEF'):result.append((name,payload))
        offset+=60+length+(length%2)
    if offset!=len(data):raise ValueError('Invalid archive padding')
    return result


class LinkInputs(IigObjects):
    def __init__(self,args):
        self.args=args;self.out=ROOT/'artifacts/xnu-kernel-link-inputs'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Canonical fresh run required')
        self.out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text());self.ports={}
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',mode=args.mode,recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            commands=[],checks=[],kernel_cases=[],device_executed=False,sdk_used=False,global_install=False,experimental_generator=True,
            full_kernel_qualified=False,full_archive_link_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,
            apple_interoperability_qualified=False,native_device_qualified=False)

    def inputs(self):
        super().inputs();self.reuse_objects()
        for identifier in ['IIGOBJ-005','IIGOBJ-006','IIGOBJ-007','FHDR-006','FHDR-008','OPENINPUT-004','MACHOTOOLS-004','KTAIL-003','KTAIL-008']:
            registered(identifier,self.ledger);e=next(e for e in self.ledger['experiments'] if e['id']==identifier)
            self.report['parents'][identifier]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.compiled=json.loads((AUDIT/'compiled-objects.json').read_text());self.by_id={r['id']:r for r in self.compiled}
        if len(self.by_id)!=982:raise ValueError('All982 current known direct entries required')
        for row in self.compiled:
            if sha(ROOT/row['output'])!=row['output_sha256'] or sha(ROOT/row['source'])!=row['source_sha256']:
                raise ValueError('Prior982 source/object changed')
        self.source_inputs=json.loads((AUDIT/'dependency-files.json').read_text())
        for name,h in self.source_inputs.items():
            if sha(ROOT/name)!=h:raise ValueError('Prior982 dependency changed')
        tool=json.loads((ROOT/'fixtures/public/xnu-host-tools/macho-session4.json').read_text())
        self.tool_prefix=ROOT/tool['prefix'];self.ld=self.tool_prefix/'bin/aarch64-apple-darwin-ld';self.libtool=self.tool_prefix/'bin/aarch64-apple-darwin-libtool'
        for p in [self.ld,self.libtool]:
            if sha(p)!=tool['prefix_files_sha256'][str(p.relative_to(self.tool_prefix))]:raise ValueError('Qualified cctools tool changed')
        tail=json.loads((ROOT/'artifacts/xnu-kernel-direct-tail/build-session3/report.json').read_text())
        self.segtool=ROOT/tail['setsegname']['tool']
        if sha(self.segtool)!=tail['setsegname']['sha256']:raise ValueError('Qualified genuine section processor changed')
        self.stage=self.out/'stage';self.stage.mkdir()
        self.report['tools']=dict(linker=str(self.ld.relative_to(ROOT)),linker_sha256=sha(self.ld),libtool=str(self.libtool.relative_to(ROOT)),
            libtool_sha256=sha(self.libtool),setsegname=str(self.segtool.relative_to(ROOT)),setsegname_sha256=sha(self.segtool))
        names=['Makefile','makedefs/MakeInc.def','makedefs/MakeInc.kernel','makedefs/MakeInc.rule','makedefs/MakeInc.cmd','config/Makefile','config/newvers.pl','config/MasterVersion',
            'config/generate_linker_exports.sh','config/generate_linker_aliases.sh','config/generate_symbolset_plist.sh',
            'config/generate_combined_symbolsets_plist.sh','osfmk/arm64/caches_asm.s','osfmk/arm64/start.s',
            'osfmk/arm/model_dep.c','pexpert/arm/pe_init.c']
        self.report['link_source_inputs']={str((KERNEL/n).relative_to(ROOT)):sha(KERNEL/n) for n in names}

    def make_args(self,component,script):
        process=next(c for c in self.object_report['commands'] if c['stdout'].endswith('/inventory-'+component+'.stdout.txt'))
        args=process['argv'].copy();args[args.index('-f')+1]=str(script)
        replacements={'TARGET':str(self.stage/component),'OBJPATH':str(self.stage),'CC':str(self.compiler),'CXX':str(self.compiler)}
        return [next((k+'='+v for k,v in replacements.items() if a.startswith(k+'=')),a) for a in args]

    def stage_filelists(self):
        source=KERNEL/'SETUP/replacecontents/replacecontents.c'
        adapter=self.out/'host-program-name.h'
        adapter.write_text('/* Host diagnostic name only; no target behavior. */\nstatic const char *getprogname(void) { return "replacecontents"; }\n')
        replace=self.out/'replacecontents'
        self.must(['/usr/bin/cc','-include',adapter,source,'-o',replace],'genuine-replacecontents-build')
        self.report['replacecontents']=dict(source=str(source.relative_to(ROOT)),source_sha256=sha(source),adapter_sha256=sha(adapter),tool_sha256=sha(replace))
        self.report['staged_objects']={};self.report['component_filelists']={};self.report['HIB_processing']=[];self.report['KLD_processing']=[]
        for row in self.compiled:
            comp,name=row['id'].split('/',1)
            target=self.stage/name if comp=='kernel' else self.stage/comp/'RELEASE'/name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/row['output'],target)
            self.report['staged_objects'][row['id']]=dict(original=row['output'],original_sha256=row['output_sha256'],
                output=str(target.relative_to(ROOT)),output_sha256=sha(target))
        for component,config in self.object_report['configurations'].items():
            directory=self.stage/component/'RELEASE';directory.mkdir(parents=True,exist_ok=True)
            original=ROOT/config['root']/'Makefile';script=directory/'filelists.mk'
            # The original query shim omits cosmetic logging functions. Copy
            # their real default definitions; otherwise the component name
            # itself would be invoked as a command by the genuine recipe.
            cmd=(KERNEL/'makedefs/MakeInc.cmd').read_text().splitlines()
            logging=[next(l for l in cmd if l.startswith(k+' = ')) for k in ['LOG_PFX_LEN','LOG_PFX_LEN_ADJ','LOG','LOG_LDFILELIST']]
            script.write_text('\n'.join(logging)+'\ninclude '+str(original)+'\n$(info S24_LIST|OBJS|$(OBJS))\n$(info S24_LIST|LIBOBJS|$(LIBOBJS))\n$(info S24_LIST|HIB_FILES|$(HIB_FILES))\n$(info S24_LIST|KLD_FILES|$(KLD_FILES))\n')
            # Only filelist generation is run. Every marked-old compile output
            # already exists and was independently source/hash qualified above.
            names=[Path(r['id']).name for r in self.compiled if r['id'].startswith(component+'/')]
            args=self.make_args(component,script);args[-1]=component+'.filelist';args+=['SEG_HACK='+str(self.segtool),'REPLACECONTENTS='+str(replace)]
            args += [a for n in names+['.CFLAGS','.CXXFLAGS','.SFLAGS'] for a in ['-o',n]]
            before={n:sha(directory/n) for n in names}
            text=self.must(args,'genuine-filelist-'+component,cwd=directory,timeout=120)
            values={a[1]:a[2].split() for line in text.splitlines() if line.startswith('S24_LIST|') and len(a:=line.split('|',2))==3}
            if set(values)!={'OBJS','LIBOBJS','HIB_FILES','KLD_FILES'} or set(values['OBJS'])!=set(names) or values['OBJS']!=config['expanded_variables']['OBJS'].split():
                raise ValueError('Genuine selected object inventory/order changed: '+component)
            path=directory/(component+'.filelist');listed=path.read_text().splitlines()
            if listed!=[str(directory/n) for n in values['OBJS']]:raise ValueError('Actual filelist values/order differ')
            for name in names:
                p=directory/name;previous=ROOT/self.by_id[component+'/'+name]['output']
                if name in values['HIB_FILES']:
                    wanted,sections=expected_rename(previous,old=None,new='__HIB')
                    if p.read_bytes()!=wanted:raise ValueError('Genuine HIB postprocessing differs')
                    self.report['HIB_processing'].append(dict(id=component+'/'+name,original_sha256=before[name],output_sha256=sha(p),renamed_sections=sections))
                elif name in values['KLD_FILES']:
                    first,sections=expected_rename(previous,old='__TEXT',new='__KLD')
                    temporary=self.out/('expected-first-KLD-'+name);temporary.write_bytes(first)
                    wanted,data_sections=expected_rename(temporary,old=None,new='__KLDDATA',ignore='__KLD')
                    if p.read_bytes()!=wanted:raise ValueError('Genuine KLD/KLDDATA postprocessing differs')
                    self.report['KLD_processing'].append(dict(id=component+'/'+name,original_sha256=before[name],output_sha256=sha(p),
                        code_sections=sections,data_sections=data_sections))
                elif sha(p)!=before[name]:raise ValueError('Non-HIB object modified')
                self.report['staged_objects'][component+'/'+name]['output_sha256']=sha(p)
            # LIBOBJS is a distinct library-only selection. Do not silently
            # label its unbuilt objects as members of the full-image profile.
            self.report['component_filelists'][component]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path),objects=values['OBJS'],HIB_FILES=values['HIB_FILES'],KLD_FILES=values['KLD_FILES'],
                library_only_objects=[dict(name=n,existing_staged_object=(directory/n).is_file()) for n in values['LIBOBJS']])
        self.check('all982-staged-originals-preserved',len(self.report['staged_objects'])==982)
        self.check('all978-genuine-component-filelist-entries',sum(len(r['objects']) for r in self.report['component_filelists'].values())==978)
        self.check('actual-genuine-HIB-processing',True,objects=len(self.report['HIB_processing']))

    def query_link(self):
        parent=json.loads((ROOT/'artifacts/xnu-kernel-setup/full-profile-session2/report.json').read_text())
        process=next(c for c in parent['commands'] if c['stdout'].endswith('/query-version.stdout.txt'))
        query=self.out/'query-link.mk'
        keys=['COMPONENT_LIST','USE_LTO','BUILD_STATIC_LINK','BUILD_XNU_LIBRARY','LDFLAGS_KERNEL','LDFLAGS_KERNEL_ONLY','LD_KERNEL_LIBS','LD_KERNEL_ARCHIVES',
            'LDFILES_KERNEL_ONLY','EXTRA_KC_LINKARGS','KERNEL_FILE_NAME']
        cmd=(KERNEL/'makedefs/MakeInc.cmd').read_text().splitlines()
        platforms='\n'.join(next(l for l in cmd if l.startswith(k+' :=')) for k in ['SUPPORTED_EMBEDDED_PLATFORMS','SUPPORTED_SIMULATOR_PLATFORMS','SUPPORTED_PLATFORMS'])
        query.write_text('include '+str(ROOT/'artifacts/xnu-kernel-setup/full-profile-session2/host-commands.mk')+'\n'+platforms+'\ninclude '+str(KERNEL/'makedefs/MakeInc.def')+'\ninclude '+str(KERNEL/'makedefs/MakeInc.kernel')+'\n'+
            '\n'.join('$(info S24_LINK|'+k+'|$('+k+'))' for k in keys)+'\n.PHONY: s24_query\ns24_query: ;\n')
        args=process['argv'].copy();args[args.index('-f')+1]=str(query)
        replacements={'TARGET':str(self.stage),'OBJPATH':str(self.stage),'CC':str(self.compiler),'CXX':str(self.compiler)}
        args=[next((k+'='+v for k,v in replacements.items() if a.startswith(k+'=')),a) for a in args]
        text=self.must(args,'genuine-top-level-link-query',cwd=self.stage)
        values={a[1]:a[2] for line in text.splitlines() if line.startswith('S24_LINK|') and len(a:=line.split('|',2))==3}
        if set(values)!=set(keys) or values['USE_LTO']!='0':raise ValueError('Complete genuine selected non-LTO link profile required')
        if set(values['COMPONENT_LIST'].split())!=set(self.object_report['configurations']):raise ValueError('Genuine component list changed')
        self.report['link_variables']=values;self.report['link_query_argv']=args
        return values

    def archive(self):
        variables=self.query_link();lists=[self.stage/c/'RELEASE'/(c+'.filelist') for c in variables['COMPONENT_LIST'].split()]
        filelist=self.stage/'link.filelist'
        self.must(['cat',*lists],'genuine-concatenate-filelists')
        shutil.copyfile(self.out/'genuine-concatenate-filelists.stdout.txt',filelist)
        if len(filelist.read_text().splitlines())!=978:raise ValueError('Exact genuine full-image filelist required')
        kernel=(KERNEL/'makedefs/MakeInc.kernel').read_text()
        line=next(l for l in kernel.splitlines() if '$(LIBTOOL) -ca -filelist link.filelist version.o' in l)
        archive=self.stage/'kernel.link/kernel.a';archive.parent.mkdir()
        script=self.out/'genuine-static-archive.mk'
        script.write_text('LIBTOOL := '+str(self.libtool)+'\n.PHONY: build\nbuild: '+str(archive)+'\n'+str(archive)+':\n'+line+'\n')
        self.must(['make','--no-print-directory','-rR','-f',script,'build'],'genuine-kernel-link-archive',cwd=self.stage,timeout=180)
        self.must([NDK/'llvm-ar','t',archive],'independent-archive-members')
        self.report['archive']=dict(path=str(archive.relative_to(ROOT)),sha256=sha(archive),filelist=str(filelist.relative_to(ROOT)),filelist_sha256=sha(filelist),
            actual_recipe=line,tail=['version.o','lastkerneldataconst.o','lastkernelconstructor.o'],expected_objects=981,nonlto_object_outside_archive=True)
        self.check('genuine-real-static-link-archive',archive.read_bytes()[:8]==b'!<arch>\n')
        expected=[Path(p) for p in filelist.read_text().splitlines()]+[self.stage/n for n in self.report['archive']['tail']]
        members=archive_members(archive.read_bytes())
        if len(members)!=len(expected):raise ValueError('Exact ordinal archive member count required')
        for ordinal,((name,payload),original) in enumerate(zip(members,expected)):
            if name!=original.name or hashlib.sha256(payload).hexdigest()!=sha(original):raise ValueError('Ordinal archive member bytes/order changed: '+str(ordinal))
        manifest=[dict(ordinal=i,name=name,sha256=hashlib.sha256(payload).hexdigest(),input=str(original.relative_to(ROOT))) for i,((name,payload),original) in enumerate(zip(members,expected))]
        dump(self.out/'archive-members.json',manifest)
        self.report['archive']['members']=str((self.out/'archive-members.json').relative_to(ROOT))
        self.check('all981-independent-ordinal-member-payloads',len(manifest)==981)

    def providers(self):
        unresolved=json.loads((AUDIT/'unresolved-symbols.json').read_text())
        fire=json.loads((ROOT/'fixtures/public/xnu-kernel-firehose-headers/qualified-component.json').read_text())['provider']
        pthread=json.loads((ROOT/'fixtures/public/open-kernel-inputs/reusable-components.json').read_text())['pthread']['archive']
        archives={'firehose':(ROOT/fire['archive'],fire['archive_sha256']),'pthread':(ROOT/pthread['path'],pthread['sha256'])}
        defined={};required={}
        for name,(p,h) in archives.items():
            if sha(p)!=h:raise ValueError('Witnessed real provider archive changed')
            defs=self.must([NDK/'llvm-nm','--extern-only','--defined-only','--just-symbol-name',p],name+'-defined')
            undef=self.must([NDK/'llvm-nm','--undefined-only','--just-symbol-name',p],name+'-required')
            defined[name]={l for l in defs.splitlines() if l and not l.endswith(':')}
            required[name]={l for l in undef.splitlines() if l and not l.endswith(':')}
        facts={};original_providers=json.loads((AUDIT/'symbol-providers.json').read_text())
        for name,consumers in unresolved.items():
            if name.startswith(('section$','segment$')) or name in {'___dso_handle','__mh_execute_header'}:
                category='linker_synthesized_candidate';source='Pinned ld64 boundary/image atom rules;actual target probe required'
            elif name in defined['firehose']:category='matched_firehose_archive';source=str(archives['firehose'][0].relative_to(ROOT))
            elif name in defined['pthread']:category='historical_pthread_archive_only';source=str(archives['pthread'][0].relative_to(ROOT))
            else:
                category='selected_source_or_configuration_gap';source={'_clean_mmu_dcache':'osfmk/arm64/caches_asm.s orphan global beside CleanPoC_Dcache',
                    '_SleepToken':'osfmk/arm64/start.s definition under WITH_CLASSIC_S2R',
                    '_iBoot_Stage_2_version':'pexpert/arm/pe_init.c definition under TARGET_OS_OSX+arm64'}[name]
            facts[name]=dict(category=category,source=source,consumers=consumers)
        self.report['provider_classification']={k:dict(path=str(p.relative_to(ROOT)),sha256=h,defined_symbols=sorted(defined[k]),
            required_symbols=sorted(required[k]),required_not_in_direct_objects=sorted(required[k]-set(original_providers))) for k,(p,h) in archives.items()}
        self.report['provider_classification']['pthread']['current_profile_ABI_qualified']=False
        self.report['unresolved_name_classification']=facts
        counts=Counter(v['category'] for v in facts.values())
        self.check('all22-actual-unresolved-names-classified',len(facts)==22 and sorted(counts.values())==[1,3,5,13],categories=dict(counts))
        dump(self.out/'unresolved-name-classification.json',facts)

    def build_pthread(self):
        old=json.loads((ROOT/'fixtures/public/open-kernel-inputs/typed-pthread-session1.json').read_text())
        original_root=ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/pthread'
        root=self.out/'pthread-source';shutil.copytree(original_root,root)
        self.report['pthread_source_files']={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
        for name,h in old['typed_source_sha256'].items():
            if sha(root/name)!=h:raise ValueError('Witnessed typed pthread source changed')
        current=json.loads((ROOT/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json').read_text())
        before=next(r for r in current['compile_results'] if r['id']=='bsd/pthread_kext_static.o')
        process=next(c for c in current['commands'] if c['stdout'].endswith('/compile-bsd-pthread_kext_static.o.stdout.txt'))
        if self.args.mode=='pthread-kext':
            config=ROOT/'references/xnu-kernel-pthread/xcodescripts/kext.xcconfig'
            text=config.read_text()
            definitions=re.search(r'^GCC_PREPROCESSOR_DEFINITIONS_kext = (.+)$',text,re.M).group(1).split()
            self.report['pthread_component_context']=dict(path=str(config.relative_to(ROOT)),sha256=sha(config),definitions=definitions,
                removed_caller_internal_definitions=['DRIVER_PRIVATE','_KERNEL_BUILD','KERNEL_BUILD','MACH_KERNEL','BSD_BUILD','BSD_KERNEL_PRIVATE','LP64_DEBUG'])
        self.report['pthread_compile_results']=[]
        objects=[]
        for name in ['kern_init','kern_support','kern_synch']:
            source=root/'kern'/(name+'.c');obj=self.out/(name+'.o');argv=process['argv'].copy()
            if argv[0]!=str(self.compiler) or '-DXNU_NO_TYPE_BUILTINS=0' not in argv or any('xnu_clang_compat' in a for a in argv):
                raise ValueError('Current real BSD allocator/compiler profile required')
            argv[argv.index(str(ROOT/before['source']))]=str(source)
            argv[argv.index('-o')+1]=str(obj);argv[argv.index('-MF')+1]=str(obj.with_suffix('.d'))
            argv[1:1]=['-I',str(root),'-I',str(root/'include'),'-I',str(root/'private')]
            argv+=['-D__PTHREAD_EXPOSE_INTERNALS__=1','-Dpthread_kern=pthread_kext_kern','-Dcurrent_uthread=pthread_kext_current_uthread','-D__DARWIN_64_BIT_INO_T=1']
            if self.args.mode=='pthread-kext':
                removed=self.report['pthread_component_context']['removed_caller_internal_definitions']
                argv=[a for a in argv if not (a.startswith('-D') and a[2:].split('=')[0] in removed)]
                argv+=['-D'+d for d in definitions if d!='__PTHREAD_EXPOSE_INTERNALS__']
            code,_,error=self.run(argv,'current-pthread-'+name,cwd=Path(process['cwd']),timeout=120)
            good=code==0 and obj.is_file() and thin(obj)['filetype']==1
            self.check('actual-current-pthread-'+name,good,exit_code=code,diagnostic=error[-3500:])
            self.report['pthread_compile_results'].append(dict(name=name,source=str(source.relative_to(ROOT)),source_sha256=sha(source),
                output=str(obj.relative_to(ROOT)) if good else None,output_sha256=sha(obj) if good else None,exit_code=code,actual_arm64_object=good))
            if good:objects.append(obj)
        if len(objects)!=3:raise ValueError('All3 real current-profile pthread objects required')
        archive=self.out/'current-profile-libpthread_kext.a'
        self.must([NDK/'llvm-ar','rcs',archive,*objects],'current-pthread-archive')
        self.must([NDK/'llvm-nm','--extern-only','--defined-only','--just-symbol-name',archive],'current-pthread-providers')
        self.must([NDK/'llvm-nm','--undefined-only','--just-symbol-name',archive],'current-pthread-required')
        self.report['current_pthread']=dict(archive=str(archive.relative_to(ROOT)),archive_sha256=sha(archive),
            source_original=str(original_root.relative_to(ROOT)),compiler_sha256=sha(self.compiler),metadata_checks_enabled=True,
            old_fake_metadata_header_used=False,full_private_ABI_qualified=False,runtime_qualified=False)

    def link_controls(self):
        registered('KLINK-007',self.ledger)
        parent=ROOT/'artifacts/xnu-kernel-link-inputs/baseline-session5/report.json'
        baseline=json.loads(parent.read_text())
        self.report['parents']['KLINK-007']=dict(path=str(parent.relative_to(ROOT)),sha256=sha(parent))
        names=sorted(n for n,r in baseline['unresolved_name_classification'].items() if r['category']=='linker_synthesized_candidate')
        if len(names)!=13:raise ValueError('All13 actual linker candidate names required')
        source=self.out/'boundary-probe.s';obj=self.out/'boundary-probe.o';image=self.out/'boundary-probe'
        assembly='.section __TEXT,__text,regular,pure_instructions\n.globl _probe_entry\n_probe_entry:\n ret\n'
        for segment,section in [('__DATA','__percpu'),('__DATA_CONST','__kalloc_type'),('__DATA_CONST','__kalloc_var'),('__BOOTDATA','__init_entry_set'),('__TEXT','__thread_starts')]:
            assembly+='.section '+segment+','+section+'\n .quad 0\n'
        assembly+='.section __DATA,__data\n.globl _boundary_references\n_boundary_references:\n'+''.join(' .quad '+n+'\n' for n in names)
        source.write_text(assembly)
        self.must([self.compiler,'-target','arm64-apple-ios16.5','-c',source,'-o',obj],'boundary-target-assemble')
        before=thin(obj);undefined={s['name'] for s in before['symbols'] if s['type']&0xe==0}
        self.check('all13-real-target-undefined-relocations',set(names)<=undefined and sum(s['nreloc'] for s in before['sections'])==13)
        argv=[self.ld,'-arch','arm64','-static','-e','_probe_entry','-platform_version','ios','16.5','16.5',obj,'-o',image]
        self.must(argv,'boundary-actual-static-link')
        view=thin(image);symbols={s['name']:s for s in view['symbols']};data=image.read_bytes()
        expected={}
        for name in names:
            if name.startswith('section$'):
                _,end,segment,section=name.split('$');record=next(s for s in view['sections'] if s['segment']==segment and s['name']==section)
                expected[name]=record['address']+(record['size'] if end=='end' else 0)
            elif name.startswith('segment$'):
                _,end,segment=name.split('$');record=next(s for s in view['segments'] if s['name']==segment)
                expected[name]=record['address']+(record['size'] if end=='end' else 0)
            else:expected[name]=next(s for s in view['segments'] if s['name']=='__TEXT')['address']
        refs=symbols['_boundary_references'];section=view['sections'][refs['section']-1]
        offset=section['offset']+refs['value']-section['address']
        import struct
        actual=struct.unpack_from('<13Q',data,offset)
        self.report['linker_boundary_values']=[dict(name=n,expected=expected[n],actual=v,defined_in_image=n in symbols) for n,v in zip(names,actual)]
        self.check('all13-independent-image-boundary-values',all(expected[n]==v for n,v in zip(names,actual)))
        self.check('boundary-image-no-undefined',not [s for s in view['symbols'] if s['type']&0xe==0 and s['type']&1])
        self.must([NDK/'llvm-readobj','--file-headers','--sections','--symbols',image],'independent-boundary-image-inspection')
        bad=self.out/'missing-provider.s';bad.write_text(assembly+'\n .quad _s24_missing_real_provider\n');badobj=bad.with_suffix('.o')
        self.must([self.compiler,'-target','arm64-apple-ios16.5','-c',bad,'-o',badobj],'missing-provider-assemble')
        negative=argv.copy();negative[negative.index(obj)]=badobj;negative[-1]=self.out/'must-not-link'
        code,_,error=self.run(negative,'missing-provider-real-link-rejection')
        self.check('ordinary-missing-provider-rejected',code!=0 and '_s24_missing_real_provider' in error and not negative[-1].exists(),exit_code=code)
        self.source_gaps()

    def source_gaps(self):
        current=json.loads((ROOT/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json').read_text())
        records={}
        for identifier in ['osfmk/caches_asm.o','osfmk/start.o','osfmk/model_dep.o','pexpert/pe_init.o']:
            row=self.by_id[identifier];source=ROOT/row['source'];obj=ROOT/row['output']
            command=next(c for c in current['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==str(obj))
            argv=[];skip=False
            for a in command['argv']:
                if skip:skip=False;continue
                if a in ['-o','-MF','-MT','-MQ']:skip=True;continue
                if a in ['-c','-MMD','-MD','-MP']:continue
                argv.append(a)
            argv+=['-E']
            text=self.must(argv,'source-preprocess-'+identifier.replace('/','-'),cwd=Path(command['cwd']),timeout=120)
            macros=self.must(argv+['-dM'],'source-macros-'+identifier.replace('/','-'),cwd=Path(command['cwd']),timeout=120)
            defined=self.must([NDK/'llvm-nm','--extern-only','--defined-only','--just-symbol-name',obj],'source-defined-'+identifier.replace('/','-'))
            undefined=self.must([NDK/'llvm-nm','--undefined-only','--just-symbol-name',obj],'source-required-'+identifier.replace('/','-'))
            self.must([NDK/'llvm-readobj','--relocations','--symbols',obj],'source-relocations-'+identifier.replace('/','-'))
            records[identifier]=dict(source=row['source'],source_sha256=sha(source),object=row['output'],object_sha256=sha(obj),
                defined=defined.splitlines(),undefined=undefined.splitlines(),selected_macros=[l for l in macros.splitlines() if re.match(r'#define (WITH_CLASSIC_S2R|TARGET_OS_OSX|XNU_TARGET_OS_IOS|ARM64_BOARD_CONFIG_E1S|MAX_CPUS|MAX_CPU_CLUSTERS)\b',l)])
            if identifier=='osfmk/caches_asm.o':
                self.check('clean-mmu-orphan-global-actual-profile','_clean_mmu_dcache' in undefined.splitlines() and '_CleanPoC_Dcache' in defined.splitlines() and not re.search(r'^_clean_mmu_dcache\s*:',text,re.M) and re.search(r'^_CleanPoC_Dcache\s*:',text,re.M) is not None)
            elif identifier=='osfmk/start.o':
                condition=re.search(r'^#define WITH_CLASSIC_S2R(?: (.*))?$',macros,re.M)
                records[identifier]['WITH_CLASSIC_S2R']=condition.group(1) if condition else 'undefined; #if evaluates to zero'
                self.check('sleep-token-actual-definition-excluded','_SleepToken' in undefined.splitlines() and not re.search(r'^_SleepToken\s*:',text,re.M) and (condition is None or condition.group(1)=='0'))
            elif identifier=='osfmk/model_dep.o':
                self.check('iboot-stage2-real-consumer','_iBoot_Stage_2_version' in undefined.splitlines() and re.search(r'extern\s+char\s+iBoot_Stage_2_version\s*\[',text) is not None)
            else:
                self.check('iboot-stage2-provider-excluded-ios','_iBoot_Stage_2_version' not in defined.splitlines() and not re.search(r'char\s+iBoot_Stage_2_version\s*\[',text) and '#define XNU_TARGET_OS_IOS' in macros)
        self.report['source_gaps']=records
        dump(self.out/'source-gap-evidence.json',records)

    def full_link_attempt(self):
        """Generate real export metadata, then retain the unabridged link result."""
        registered('KLINK-007',self.ledger)
        parent=ROOT/'artifacts/xnu-kernel-link-inputs/baseline-session5/report.json';baseline=json.loads(parent.read_text())
        self.report['parents']['KLINK-007']=dict(path=str(parent.relative_to(ROOT)),sha256=sha(parent))
        query=self.out/'query-exports.mk'
        components=['BSDKernel','IOKit','Libkern','Mach','MACFramework','Unsupported','Private']
        keys=['EXPORTS_FILES','SYMBOL_COMPONENT_LIST','SYMBOL_SET_PLIST_COMPONENT_LIST','Kasan_EXPORTS','Kcov_EXPORTS']+[c+'_EXPORTS' for c in components]
        query.write_text('include '+str(KERNEL/'config/Makefile')+'\n'+''.join('$(info S24_EXPORT|'+k+'|$('+k+'))\n' for k in keys)+'\n.PHONY: s24_query\ns24_query: ;\n')
        args=baseline['link_query_argv'].copy();args[args.index('-f')+1]=str(query)
        replacements={'OBJPATH':str(self.stage),'TARGET':str(self.stage),'SOURCE':str(KERNEL/'config')+'/','RELATIVE_SOURCE_PATH':'./config'}
        args=[next((k+'='+v for k,v in replacements.items() if a.startswith(k+'=')),a) for a in args]
        text=self.must(args,'genuine-config-export-query',cwd=self.out)
        values={a[1]:a[2].split() for l in text.splitlines() if l.startswith('S24_EXPORT|') and len(a:=l.split('|',2))==3}
        if set(values)!=set(keys) or values['SYMBOL_COMPONENT_LIST']!=components:raise ValueError('Exact genuine export selection required')
        exports=[KERNEL/'config'/n for n in values['EXPORTS_FILES']]+[Path(n) for k in ['Kasan_EXPORTS','Kcov_EXPORTS'] for n in values[k]]
        for name,script in [('all-kpi.exp','generate_linker_exports.sh'),('all-alias.exp','generate_linker_aliases.sh')]:
            self.must(['sh',KERNEL/'config'/script,self.stage/name,*exports],'genuine-'+name,cwd=KERNEL/'config')
        metadata_inputs={str(p.relative_to(ROOT)):sha(p) for p in exports}
        generated=[]
        for component in values['SYMBOL_SET_PLIST_COMPONENT_LIST']:
            original=KERNEL/'config/System.kext/PlugIns'/(component+'.kext')/'Info.plist'
            info=self.out/(component+'-Info.plist');shutil.copyfile(original,info)
            self.must(['env','SRCROOT='+str(KERNEL),'OBJROOT='+str(self.out),'TARGET='+str(self.stage),'CURRENT_KERNEL_CONFIG_LC=release',
                'perl',KERNEL/'config/newvers.pl',info],'genuine-newvers-'+component,cwd=self.out)
            output=self.out/(component+'.symbolset.plist')
            selected=[Path(n) for n in values[component+'_EXPORTS']]
            self.must(['sh',KERNEL/'config/generate_symbolset_plist.sh',output,info,*selected],'genuine-symbolset-'+component,cwd=KERNEL/'config')
            plistlib.loads(output.read_bytes());generated.append(output)
            metadata_inputs[str(original.relative_to(ROOT))]=sha(original)
        xml=self.out/'symbolsets.xml.plist'
        self.must(['sh',KERNEL/'config/generate_combined_symbolsets_plist.sh',xml,*generated],'genuine-combined-symbolsets')
        value=plistlib.loads(xml.read_bytes());binary=self.stage/'symbolsets.plist'
        binary.write_bytes(plistlib.dumps(value,fmt=plistlib.FMT_BINARY,sort_keys=False))
        self.check('genuine-nine-symbolsets-and-fallback',len(value['SymbolsSets'])==9 and value['WeakRefFallbackSymbol']=={'SymbolName':'_gOSKextUnresolved'})
        self.check('host-plist-semantic-roundtrip',plistlib.loads(binary.read_bytes())==value)
        self.report['metadata']=dict(inputs=metadata_inputs,query_values=values,outputs={str(p.relative_to(ROOT)):sha(p) for p in [self.stage/'all-kpi.exp',self.stage/'all-alias.exp',xml,binary]},
            binary_converter='Python stdlib plistlib; semantic roundtrip only',native_plutil_oracle_qualified=False)
        variables=baseline['link_variables'];oldstage=str((ROOT/baseline['archive']['filelist']).parent)
        flags=shlex.split(variables['LDFLAGS_KERNEL'])+shlex.split(variables['LDFLAGS_KERNEL_ONLY'].replace(oldstage,str(self.stage)))
        staged=Path(oldstage);filelist=ROOT/baseline['archive']['filelist']
        for row in baseline['staged_objects'].values():
            if sha(ROOT/row['output'])!=row['output_sha256']:raise ValueError('Qualified staged link input changed')
        output=self.out/'mach.release.e1s.unstripped'
        argv=[self.compiler,'--ld-path='+str(self.ld),'-nostdlib',*flags,'-filelist',filelist,staged/'version.o',
            staged/'lastkerneldataconst.o',staged/'lastkernelconstructor.o',staged/'nonlto.o','-o',output,
            *shlex.split(variables['LD_KERNEL_LIBS']),*shlex.split(variables['LD_KERNEL_ARCHIVES'])]
        self.must([*argv,'-###'],'genuine-link-driver-expansion',cwd=self.out)
        code,_,error=self.run(argv,'genuine-full-link-attempt',cwd=self.out,timeout=180)
        # A real source-built component is available outside the absent SDK.
        # Supply only that qualified archive in a fresh owned search directory.
        # Missing pthread/corecrypto inputs remain absent, with no empty files.
        fire=json.loads((ROOT/'fixtures/public/xnu-kernel-firehose-headers/qualified-component.json').read_text())['provider']
        archive=ROOT/fire['archive']
        if sha(archive)!=fire['archive_sha256']:raise ValueError('Matched firehose archive changed')
        library=self.out/'available-libraries';library.mkdir();copy=library/'libfirehose_kernel.a';shutil.copyfile(archive,copy)
        with_provider=[argv[0],'-L'+str(library),*argv[1:]]
        pcode,_,perror=self.run(with_provider,'genuine-full-link-matched-firehose-attempt',cwd=self.out,timeout=180)
        self.report['available_provider_attempt']=dict(exit_code=pcode,image_exists=output.is_file(),search_directory=str(library.relative_to(ROOT)),
            firehose_archive_sha256=sha(copy),diagnostic=perror[-6000:],historical_pthread_supplied=False,empty_or_stub_library_supplied=False)
        self.check('qualified-firehose-supplied-missing-inputs-exposed',pcode!=0 and not output.is_file() and '-lfirehose_kernel' not in perror)
        self.report['full_link_attempt']=dict(exit_code=code,image_exists=output.is_file(),image_sha256=sha(output) if output.is_file() else None,
            actual_982_object_inputs=True,required_libraries_preserved=['cc_kext','firehose_kernel','pthread_kext'],
            diagnostic=error[-6000:],metadata_serialization_qualification='Host only; no Apple plutil oracle')
        self.check('full-link-unavailable-inputs-retained',code!=0 and not output.is_file(),exit_code=code)

    def acceptance(self):
        reports={}
        for identifier,prefix in [('KLINK-007','baseline-session5'),('KLINK-009','controls-session2'),('KLINK-011','link-session2')]:
            registered(identifier,self.ledger)
            path=ROOT/'artifacts/xnu-kernel-link-inputs'/prefix/'report.json'
            reports[identifier]=json.loads(path.read_text())
            self.report['parents'][identifier]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
            self.check(identifier+'-actual-host-assessment-passes',reports[identifier]['outcome']=='pass' and all(c['pass_check'] for c in reports[identifier]['checks']))
        baseline=reports['KLINK-007'];controls=reports['KLINK-009'];link=reports['KLINK-011']
        members=archive_members((ROOT/baseline['archive']['path']).read_bytes())
        manifest=json.loads((ROOT/baseline['archive']['members']).read_text())
        self.check('all981-ordinal-members-reverified',len(members)==len(manifest)==981 and all(name==r['name'] and hashlib.sha256(data).hexdigest()==r['sha256']==sha(ROOT/r['input']) for (name,data),r in zip(members,manifest)))
        archive_bytes=(ROOT/baseline['archive']['path']).read_bytes()
        for name,damaged in [('magic',b'bad'+archive_bytes[3:]),('header',archive_bytes[:30]),('payload',archive_bytes[:-17])]:
            try:archive_members(damaged)
            except (ValueError,UnicodeError):rejected=True
            else:rejected=False
            self.check('real-archive-'+name+'-damage-rejected',rejected)
        objects=[]
        for identifier,row in baseline['staged_objects'].items():
            path=ROOT/row['output'];view=thin(path)
            if sha(path)!=row['output_sha256']:raise ValueError('Actual staged982 bytes changed')
            objects.append(dict(id=identifier,output=row['output'],sha256=sha(path),filetype=view['filetype'],
                sections=len(view['sections']),relocations=sum(s['nreloc'] for s in view['sections']),symbols=len(view['symbols'])))
        dump(self.out/'all982-staged-mach-o-audit.json',objects)
        self.check('all982-real-staged-ARM64-objects',len(objects)==982 and all(o['filetype']==1 for o in objects))
        self.report['staged_totals']=dict(objects=len(objects),sections=sum(o['sections'] for o in objects),relocations=sum(o['relocations'] for o in objects),symbols=sum(o['symbols'] for o in objects))
        self.check('genuine-14-HIB-and1-KLD-edits',len(baseline['HIB_processing'])==14 and len(baseline['KLD_processing'])==1)
        # An archive member's undefined symbol can be provided by another
        # member. Compute the closure before reporting external imports.
        provider_map=json.loads((AUDIT/'symbol-providers.json').read_text())
        closures={}
        for name,row in baseline['provider_classification'].items():
            imports=set(row['required_symbols'])-set(row['defined_symbols'])
            closures[name]=dict(external_imports=sorted(imports),missing_from982=sorted(imports-set(provider_map)),
                current_profile_ABI_qualified=(name=='firehose'))
        self.report['provider_import_closure']=closures
        self.check('matched-firehose-all-real-imports-supplied',not closures['firehose']['missing_from982'])
        for identifier,prefix in [('KLINK-003','pthread-session1'),('KLINK-006','pthread-session2')]:
            registered(identifier,self.ledger);path=ROOT/'artifacts/xnu-kernel-link-inputs'/prefix/'report.json';r=json.loads(path.read_text())
            self.check(identifier+'-actual-pthread-failure-retained',r['outcome']=='fail' and len(r['pthread_compile_results'])==3 and all(c['exit_code']!=0 for c in r['pthread_compile_results']))
            self.report['parents'][identifier]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
        argv=next(c['argv'] for c in link['commands'] if c['stderr'].endswith('/genuine-full-link-attempt.stderr.txt'))
        driver=(ROOT/next(c['stderr'] for c in link['commands'] if c['stderr'].endswith('/genuine-link-driver-expansion.stderr.txt'))).read_text()
        self.check('actual-linker-selected-through-real-driver',str(self.ld) in driver and '--ld-path='+str(self.ld) in argv)
        self.check('all3-genuine-required-libraries-retained',all('-l'+n in argv for n in ['cc_kext','firehose_kernel','pthread_kext']))
        self.check('actual-full-link-failed-no-image',link['full_link_attempt']['exit_code']!=0 and not link['full_link_attempt']['image_exists'])
        self.check('actual-qualified-firehose-link-failed-no-image',link['available_provider_attempt']['exit_code']!=0 and not link['available_provider_attempt']['image_exists'])
        self.check('13-boundary-addresses-and3-source-gaps-actual',len(controls['linker_boundary_values'])==13 and len(controls['source_gaps'])==4)
        self.check('all-experimental-and-native-limitations-preserved',all(not r[k] for r in reports.values() for k in ['full_kernel_qualified','full_archive_link_qualified','full_crypto_qualified','apple_private_abi_qualified','apple_interoperability_qualified','native_device_qualified','device_executed','sdk_used']))
        self.must(['make','check'],'repository-make-check',cwd=ROOT,timeout=300)
        self.report['acceptance_criteria']=[
            dict(number=1,assessed=True,evidence='KLINK-007 genuine978 filelists,14HIB+1KLD,981ordinal archive,all982 staged provenance and exact top-level flags'),
            dict(number=2,assessed=True,evidence='KLINK-009 actual13 target-boundary addresses+negative rejection+real4-TU preprocessing/symbol/relocation evidence;KLINK-003/006 pthread failures;provider closure explicitly distinguishes historical archive'),
            dict(number=3,assessed=True,evidence='KLINK-007 real -ca archive;KLINK-009 real static target link;KLINK-011 genuine metadata generators and two actual unabridged982-object link failures including available qualified firehose;damaged archive rejection'),
            dict(number=4,assessed=True,evidence='Procedure/handoff and false full-link,SDK,Apple ABI,crypto,runtime,native claims;original982 source/object/dependency hashes verified')]
        self.report['maintained_files_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'docs/procedures/xnu-kernel-link-inputs.md',ROOT/'patches/kernel-link-inputs/README.md',*sorted(FIXTURES.glob('*'))] if p.is_file()}

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Genuine selected kernel archive/link-input/provider host assessment;full kernel/SDK/Apple ABI/crypto/native qualification false'
        self.report['compiler_sha256']=sha(self.compiler) if hasattr(self,'compiler') else None
        dump(self.out/'report.json',self.report)
        files=sorted(p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json')
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20],commands_scope='Representative actual commands;all executions in hashed report.json',actual_command_count=len(self.report['commands']),
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--mode',choices=['baseline','pthread','pthread-kext','controls','link','acceptance'],required=True);args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Canonical fresh run required')
    args.compiler,args.compiler_evidence,args.header_evidence,args.resource_evidence=VECTOR_COMPILER,'VCOMP-002','FHDR-003','RHDR-002'
    args.storage_evidence='CXXST-007';args.port_evidence='KDECL-004';args.object_evidence='IIGOBJ-003';args.jobs=1
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));build=LinkInputs(args)
    try:
        build.inputs()
        if args.mode.startswith('pthread'):build.build_pthread()
        elif args.mode=='controls':build.link_controls()
        elif args.mode=='link':build.full_link_attempt()
        elif args.mode=='acceptance':build.acceptance()
        else:build.stage_filelists();build.archive();build.providers()
    except Exception as error:build.report['error']=str(error)
    return build.finish()


if __name__=='__main__':sys.exit(main())
