#!/usr/bin/env python3
"""Resolve measured selected source symbol gaps without replacing behavior."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
from xnu_kernel_link_inputs import LinkInputs
from xnu_kernel_direct_tail import thin
from xnu_compiler_atomics import ROOT,KERNEL,NDK,registered,sha,dump
from xnu_kernel_firehose_headers import COMPILER as VECTOR_COMPILER
from xnu_kernel_syscalls import ObjectData

FIXTURES=ROOT/'fixtures/public/xnu-kernel-symbol-gaps'
PATCH=ROOT/'patches/kernel-symbol-gaps/0001-align-cache-alias-and-platform-guards.patch'
IDS=['osfmk/caches_asm.o','osfmk/start.o','osfmk/model_dep.o','pexpert/pe_init.o']


class SymbolGaps(LinkInputs):
    def __init__(self,args):
        self.args=args;self.out=ROOT/'artifacts/xnu-kernel-symbol-gaps'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Canonical fresh run required')
        self.out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text());self.ports={}
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',mode=args.mode,recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            commands=[],checks=[],kernel_cases=[],device_executed=False,sdk_used=False,global_install=False,experimental_generator=True,
            full_kernel_qualified=False,full_archive_link_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,
            apple_interoperability_qualified=False,native_device_qualified=False)

    def inputs(self):
        super().inputs()
        for identifier in ['KLINK-009','KLINK-012']:
            registered(identifier,self.ledger);entry=next(e for e in self.ledger['experiments'] if e['id']==identifier)
            self.report['parents'][identifier]=dict(path=entry['evidence'],sha256=entry['evidence_sha256'])
        self.current=json.loads((ROOT/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json').read_text())
        self.witness=json.loads((FIXTURES/'source-inputs.json').read_text())
        self.report['patch']=dict(path=str(PATCH.relative_to(ROOT)),sha256=sha(PATCH))

    def sources(self):
        self.source_root=self.out/'source';self.source_root.mkdir()
        for name,row in self.witness['files'].items():
            original=KERNEL/name
            if sha(original)!=row['original_sha256']:raise ValueError('Exact prepared source required')
            target=self.source_root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
        self.must(['git','-c','init.templateDir=','-c','core.hooksPath=/dev/null','-C',self.source_root,'init','--quiet'],'isolated-source-init')
        self.must(['git','-c','core.hooksPath=/dev/null','-C',self.source_root,'apply','--check',PATCH],'exact-patch-check')
        self.must(['git','-c','core.hooksPath=/dev/null','-C',self.source_root,'apply',PATCH],'exact-patch-apply')
        for name,row in self.witness['files'].items():
            if sha(self.source_root/name)!=row['patched_sha256']:raise ValueError('Exact intended source edit required')
        self.report['source_edits']=self.witness['files']

    def command(self,identifier,source,output,extra=()):
        before=self.by_id[identifier]
        process=next(c for c in self.current['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==str(ROOT/before['output']))
        argv=process['argv'].copy()
        if argv[0]!=str(self.compiler) or '-DXNU_NO_TYPE_BUILTINS=0' not in argv:raise ValueError('Actual current full compiler profile required')
        argv[argv.index(str(ROOT/before['source']))]=str(source)
        argv[argv.index('-o')+1]=str(output);argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
        argv+=list(extra)
        return argv,Path(process['cwd'])

    def compile_one(self,identifier,label,source=None,extra=()):
        before=self.by_id[identifier];relative=str((ROOT/before['source']).relative_to(KERNEL))
        source=source or self.source_root/relative;output=self.out/'objects'/(label+'.o');output.parent.mkdir(exist_ok=True)
        argv,cwd=self.command(identifier,source,output,extra)
        code,_,error=self.run(argv,'compile-'+label,cwd=cwd,timeout=120)
        good=code==0 and output.is_file() and thin(output)['filetype']==1
        self.check('actual-ARM64-'+label,good,exit_code=code,diagnostic=error[-3000:])
        row=dict(id=identifier,source=str(source.relative_to(ROOT)),source_sha256=sha(source),exit_code=code,actual_arm64_object=good,
            output=str(output.relative_to(ROOT)) if good else None,output_sha256=sha(output) if good else None,
            original_source=before['source'],original_source_sha256=before['source_sha256'],original_output=before['output'],original_output_sha256=before['output_sha256'])
        return row,argv,cwd

    @staticmethod
    def section_payloads(path):
        data=path.read_bytes();view=thin(path)
        return {(s['segment'],s['name']):(s['size'],data[s['offset']:s['offset']+s['size']] if not s['zerofill'] else None) for s in view['sections']}

    def production(self):
        self.sources();self.report['compile_results']=[]
        for identifier in IDS:
            row,_,_=self.compile_one(identifier,identifier.replace('/','-'));self.report['compile_results'].append(row)
        if not all(r['actual_arm64_object'] for r in self.report['compile_results']):raise ValueError('All four genuine target recipes required')
        rows={r['id']:r for r in self.report['compile_results']}
        for identifier in IDS[:2]:
            old=ROOT/rows[identifier]['original_output'];new=ROOT/rows[identifier]['output']
            self.check('unchanged-all-code-and-storage-'+identifier,self.section_payloads(old)==self.section_payloads(new))
            self.must([NDK/'llvm-readobj','--file-headers','--sections','--relocations','--symbols',new],'actual-object-'+identifier.replace('/','-'))
        cache=ROOT/rows[IDS[0]]['output'];view=thin(cache);symbols={s['name']:s for s in view['symbols']}
        alias=symbols['_clean_mmu_dcache'];real=symbols['_CleanPoC_Dcache']
        self.check('real-cache-alias-same-code-address',alias['type']&0xe==0xe and (alias['section'],alias['value'])==(real['section'],real['value']))
        dis=self.must([NDK/'llvm-objdump','-d','--no-show-raw-insn',cache],'actual-cache-instructions')
        self.check('actual-generic-cache-maintenance-remains',bool(re.search(r'\bdc\s+csw,',dis)) and 'CLIDR_EL1' in dis)
        start=self.external_symbols(ROOT/rows[IDS[1]]['output'])
        self.check('disabled-S2R-no-orphan-symbol',not any(s['name']=='_SleepToken' for s in start))
        for identifier in IDS[2:]:
            symbols=self.external_symbols(ROOT/rows[identifier]['output'])
            self.check('ios-no-macOS-stage2-symbol-'+identifier,not any(s['name']=='_iBoot_Stage_2_version' for s in symbols))
        self.audit(rows)

    def audit(self,replacements):
        compiled=[replacements.get(r['id'],r) for r in self.compiled]
        providers=defaultdict(list);consumers=defaultdict(list);expected={};objects=[];dependencies={};inputs=dict(self.source_inputs)
        for row in compiled:
            p=ROOT/row['output'];objects.append(p)
            if sha(p)!=row['output_sha256'] or sha(ROOT/row['source'])!=row['source_sha256']:raise ValueError('Actual source/object hash changed')
            external=self.external_symbols(p);expected[str(p)]={s['name'] for s in external if s['defined']}
            for symbol in external:
                (providers if symbol['defined'] else consumers)[symbol['name']].append(dict(object=row['id'],weak=symbol['weak'],common=symbol['common'],alias=symbol['alias']))
            if row['id'] in replacements:
                dep=p.with_suffix('.d');argv,cwd=self.command(row['id'],ROOT/row['source'],p)
                line=dep.read_text().replace('\\\n',' ').splitlines()[0]
                paths=[(cwd/n).resolve() for n in shlex.split(line.split(':',1)[1])]
                if (ROOT/row['source']).resolve() not in paths:raise ValueError('Actual replacement source absent from dependencies')
                names=[]
                for name in paths:
                    key=str(name.relative_to(ROOT)) if name.is_relative_to(ROOT) else str(name)
                    if key in inputs and inputs[key]!=sha(name):raise ValueError('Shared dependency changed')
                    inputs[key]=sha(name);names.append(key)
                dependencies[row['id']]=dict(depfile=str(dep.relative_to(ROOT)),sha256=sha(dep),inputs=sorted(set(names)))
        headers=self.must([NDK/'llvm-readobj','--file-headers',*objects],'all982-independent-headers',timeout=120)
        self.check('all982-real-ARM64-headers',headers.count('Format: Mach-O arm64')==982)
        text=self.must([NDK/'llvm-nm','--extern-only','--defined-only','--format=posix',*objects],'all982-independent-symbol-map',timeout=120)
        seen={};current=None
        for line in text.splitlines():
            if line.endswith(':') and line[:-1] in expected:current=line[:-1];seen[current]=set()
            elif current and len(a:=line.split())>=3 and len(a[1])==1:seen[current].add(a[0])
        self.check('all982-independent-symbol-map-agrees',seen==expected)
        missing={n:v for n,v in consumers.items() if n not in providers and any(not s['weak'] for s in v)}
        duplicates={n:v for n,v in providers.items() if len([s for s in v if not s['weak'] and not s['common']])>1}
        original=set(json.loads((ROOT/'artifacts/xnu-kernel-iig-objects/audit-session1/unresolved-symbols.json').read_text()))
        removed={'_clean_mmu_dcache','_SleepToken','_iBoot_Stage_2_version'}
        self.check('exact-three-source-gaps-resolved-no-new-name',set(missing)==original-removed and len(missing)==19)
        self.check('no-strong-duplicate-providers',not duplicates)
        self.check('all978-untouched-objects-retained',sum(r['id'] not in replacements for r in compiled)==978)
        self.report['link_symbol_status']=dict(external_providers=len(providers),external_consumer_names=len(consumers),unresolved_required_names=len(missing),
            strong_duplicates=len(duplicates),resolved_selected_source_gaps=sorted(removed),actual_full_link_attempted=False,full_link_closure_qualified=False)
        for name,value in [('compiled-objects',compiled),('dependency-files',inputs),('replacement-object-dependencies',dependencies),
            ('symbol-providers',dict(providers)),('symbol-consumers',dict(consumers)),('unresolved-symbols',missing),('strong-duplicates',duplicates)]:dump(self.out/(name+'.json'),value)

    def controls(self):
        registered('SGAP-001',self.ledger);self.sources()
        parent=ROOT/'artifacts/xnu-kernel-symbol-gaps/production-session1/report.json';production=json.loads(parent.read_text())
        self.report['parents']['SGAP-001']=dict(path=str(parent.relative_to(ROOT)),sha256=sha(parent))
        for row in production['compile_results']:
            if sha(ROOT/row['output'])!=row['output_sha256']:raise ValueError('Actual qualified replacement changed')
        # Revert actual source defects one at a time and inspect emitted ARM64.
        self.report['reverted_source_controls']=[]
        for identifier,name in [(IDS[0],'_clean_mmu_dcache'),(IDS[1],'_SleepToken'),(IDS[2],'_iBoot_Stage_2_version')]:
            original=ROOT/self.by_id[identifier]['source'];source=self.out/('reverted-'+original.name);shutil.copyfile(original,source)
            row,_,_=self.compile_one(identifier,'reverted-'+Path(identifier).name,source)
            if not row['actual_arm64_object']:raise ValueError('Actual source-reversion target object required')
            external=self.external_symbols(ROOT/row['output'])
            self.check('actual-reverted-gap-detected-'+name,any(s['name']==name and not s['defined'] for s in external))
            self.report['reverted_source_controls'].append(dict(name=name,source=row['source'],source_sha256=row['source_sha256'],object=row['output'],object_sha256=row['output_sha256']))
        cache=next(r for r in production['compile_results'] if r['id']==IDS[0]);source=self.out/'negative-noop-caches.s'
        text=(self.source_root/'osfmk/arm64/caches_asm.s').read_text()
        begin=text.index('#if  defined(APPLE_ARM64_ARCH_FAMILY)',text.index('LEXT(CleanPoC_Dcache)'))
        end=text.index('#endif /* defined(APPLE_ARM64_ARCH_FAMILY) */',begin)+len('#endif /* defined(APPLE_ARM64_ARCH_FAMILY) */')
        source.write_text(text[:begin]+'\tret /* NEGATIVE TEST ONLY: no cache maintenance */'+text[end:])
        row,_,_=self.compile_one(IDS[0],'negative-noop-cache',source)
        if not row['actual_arm64_object']:raise ValueError('Actual negative no-op target required')
        self.check('real-noop-cache-mutation-detected',self.section_payloads(ROOT/row['output'])!=self.section_payloads(ROOT/cache['output']))
        self.report['negative_noop_cache']=row
        row,_,_=self.compile_one(IDS[1],'explicit-S2R-disabled',extra=['-DWITH_CLASSIC_S2R=0'])
        self.check('explicit-disabled-S2R-no-symbol',row['actual_arm64_object'] and not any(s['name']=='_SleepToken' for s in self.external_symbols(ROOT/row['output'])))
        self.enabled_s2r()
        self.platform_controls()

    def enabled_s2r(self):
        registered('KSETUP-001',self.ledger)
        setup=json.loads((ROOT/'artifacts/xnu-kernel-setup/generate-session1/report.json').read_text())
        process=next(c for c in setup['commands'] if c['stdout'].endswith('/genassym-compile.stdout.txt'))
        root=self.out/'enabled-S2R';root.mkdir();assembly=root/'genassym.o'
        argv=process['argv'].copy();argv[0]=str(self.compiler);argv[argv.index('-o')+1]=str(assembly);argv[argv.index('-MF')+1]=str(root/'genassym.d')
        argv+=['-DWITH_CLASSIC_S2R=1']
        self.must(argv,'genuine-enabled-S2R-genassym',cwd=Path(process['cwd']),timeout=120)
        extraction=next(c for c in setup['commands'] if c['stdout'].endswith('/assym-extract.stdout.txt'))['argv'].copy();extraction[-1]=str(assembly)
        text=self.must(extraction,'genuine-enabled-S2R-assym-extraction',cwd=root)
        header=root/'assym.s';header.write_text(text)
        value=re.search(r'^#define stSize_NUM (\d+)$',text,re.M)
        declared=re.search(r'extern\s+uint8_t\s+SleepToken\[(\d+)\];',(KERNEL/'osfmk/arm/cpu_data_internal.h').read_text())
        self.check('enabled-size-from-genuine-target-declaration',value is not None and declared is not None and int(value.group(1))==int(declared.group(1)))
        if value is None:raise ValueError('Actual enabled stSize required')
        size=int(value.group(1));source=root/'start.s';shutil.copyfile(self.source_root/'osfmk/arm64/start.s',source)
        row,argv,cwd=self.compile_one(IDS[1],'genuine-S2R-enabled',source,extra=['-DWITH_CLASSIC_S2R=1'])
        if not row['actual_arm64_object']:raise ValueError('Real enabled S2R assembly required')
        obj=ObjectData(ROOT/row['output']);data=obj.value('_SleepToken','<'+str(size)+'B')
        self.check('actual-enabled-S2R-real-zero-storage',data==tuple([0]*size))
        pre=self.preprocess(argv,cwd,'enabled-S2R-start')
        self.check('actual-enabled-S2R-exact-space-directive',re.search(r'_SleepToken\s*:\s*\.space\s*\(?'+str(size)+r'\)?,\s*0',pre) is not None)
        self.report['enabled_S2R']=dict(object=row['output'],object_sha256=row['output_sha256'],genuine_assym=str(header.relative_to(ROOT)),assym_sha256=sha(header),
            genuine_genassym=str(assembly.relative_to(ROOT)),genassym_sha256=sha(assembly),size=size,actual_zero_storage=list(data),runtime_qualified=False)

    def preprocess(self,argv,cwd,label,extra=()):
        filtered=[];skip=False
        for a in argv:
            if skip:skip=False;continue
            if a in ['-o','-MF','-MT','-MQ']:skip=True;continue
            if a in ['-c','-MD','-MMD','-MP']:continue
            filtered.append(a)
        return self.must([*filtered,*extra,'-E'],'preprocess-'+label,cwd=cwd,timeout=120)

    def platform_controls(self):
        cases={'ios-default':[], 'ios-public-OSX-zero':['-DTARGET_OS_OSX=0'], 'ios-public-OSX-one':['-DTARGET_OS_OSX=1'],
            'OSX-build-selector':['-UXNU_TARGET_OS_IOS','-DXNU_TARGET_OS_OSX=1']}
        self.report['platform_branch_controls']=[]
        for label,extra in cases.items():
            texts={};macros={}
            for identifier in IDS[2:]:
                source=self.source_root/str((ROOT/self.by_id[identifier]['source']).relative_to(KERNEL))
                argv,cwd=self.command(identifier,source,self.out/'unused-preprocess-output.o')
                text=self.preprocess(argv,cwd,label+'-'+Path(identifier).name,extra);texts[identifier]=text
                defines=self.preprocess(argv,cwd,label+'-macros-'+Path(identifier).name,[*extra,'-dM'])
                macros[identifier]=[l for l in defines.splitlines() if re.match(r'#define (TARGET_OS_OSX|XNU_TARGET_OS_OSX|XNU_TARGET_OS_IOS)\b',l)]
            enabled=label=='OSX-build-selector';producer=texts[IDS[3]];consumer=texts[IDS[2]]
            found_definition=re.search(r'char\s+iBoot_Stage_2_version\[128\];',producer) is not None
            found_log='iBoot Stage 2 version: %.128s' in consumer
            found_producer='"system-firmware-version"' in producer
            found_extern=re.search(r'extern\s+char\s+iBoot_Stage_2_version\[\];',consumer) is not None
            self.check('actual-five-guard-platform-branches-'+label,all(x==enabled for x in [found_definition,found_log,found_producer,found_extern,'iBoot Stage 2 version: %s' in producer]))
            self.report['platform_branch_controls'].append(dict(case=label,extra_definitions=extra,stage2_definition=found_definition,stage2_producer=found_producer,
                stage2_panic_consumer=found_log,stage2_extern=found_extern,actual_macros=macros,scope='Actual full-source preprocessing only;not a supported full macOS/E1S profile'))

    def platform_storage(self):
        self.sources();original=self.source_root/'pexpert/arm/pe_init.c'
        declaration=re.search(r'^#define FW_VERS_LEN (\d+)$',original.read_text(),re.M)
        if declaration is None:raise ValueError('Actual FW_VERS_LEN required')
        size=int(declaration.group(1));source=self.out/'stage2-storage-probe.c'
        source.write_text(original.read_text()+'\n_Static_assert(sizeof(iBoot_Stage_2_version)=='+str(size)+',"stage2-declared-size-mismatch");\nconst unsigned long s24_stage2_size=sizeof(iBoot_Stage_2_version);\n')
        extra=['-UXNU_TARGET_OS_IOS','-DXNU_TARGET_OS_OSX=1']
        row,argv,cwd=self.compile_one(IDS[3],'stage2-storage-branch',source,extra)
        if not row['actual_arm64_object']:raise ValueError('Actual enabled producer-branch TU required')
        path=ROOT/row['output'];view=thin(path);symbol=next(s for s in view['symbols'] if s['name']=='_iBoot_Stage_2_version')
        section=view['sections'][symbol['section']-1]
        self.check('actual-stage2-128-byte-C-type',size==128 and ObjectData(path).value('_s24_stage2_size','<Q')==(128,))
        self.check('actual-stage2-zero-fill-range',symbol['type']&0xe==0xe and section['zerofill'] and section['address']<=symbol['value'] and symbol['value']+size<=section['address']+section['size'])
        rel=self.must([NDK/'llvm-readobj','--relocations','--symbols',path],'actual-stage2-producer-relocations')
        self.check('actual-stage2-producer-reference-relocations','_iBoot_Stage_2_version' in rel and '_SecureDTGetProperty' in rel and b'system-firmware-version\0' in path.read_bytes())
        negative=self.out/'negative-stage2-size.c';negative.write_text(source.read_text().replace('#define FW_VERS_LEN '+str(size),'#define FW_VERS_LEN '+str(size+1),1))
        output=self.out/'must-not-compile-stage2.o';bad,cwd=self.command(IDS[3],negative,output,extra)
        code,_,error=self.run(bad,'actual-stage2-size-mutation-rejection',cwd=cwd,timeout=120)
        self.check('actual-stage2-size-mutation-rejected',code!=0 and 'stage2-declared-size-mismatch' in error and not output.is_file(),exit_code=code)
        self.report['stage2_storage_control']=dict(object=row['output'],object_sha256=row['output_sha256'],size=size,scope='Actual ARM64 producer TU with macOS selector as bounded branch control;not a supported full macOS/E1S profile',
            zero_fill_section=section,extra_definitions=extra,negative_exit_code=code,full_platform_or_runtime_qualified=False)

    def acceptance(self):
        reports={}
        for identifier,prefix in [('SGAP-001','production-session1'),('SGAP-003','controls-session2'),('SGAP-004','storage-session1')]:
            registered(identifier,self.ledger);path=ROOT/'artifacts/xnu-kernel-symbol-gaps'/prefix/'report.json'
            reports[identifier]=json.loads(path.read_text());self.report['parents'][identifier]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
            self.check(identifier+'-actual-assessment-passes',reports[identifier]['outcome']=='pass' and all(c['pass_check'] for c in reports[identifier]['checks']))
        production=reports['SGAP-001'];controls=reports['SGAP-003'];storage=reports['SGAP-004']
        parent=ROOT/'artifacts/xnu-kernel-symbol-gaps/production-session1'
        compiled=json.loads((parent/'compiled-objects.json').read_text());inputs=json.loads((parent/'dependency-files.json').read_text())
        for row in compiled:
            if sha(ROOT/row['source'])!=row['source_sha256'] or sha(ROOT/row['output'])!=row['output_sha256'] or thin(ROOT/row['output'])['filetype']!=1:raise ValueError('Actual coherent982 source/object changed')
        for name,value in inputs.items():
            if sha(ROOT/name)!=value:raise ValueError('Actual combined source/header dependency changed')
        self.check('actual982-coherent-source-object-graph',len(compiled)==982 and len({r['id'] for r in compiled})==982)
        self.check('exact-four-full-recipe-replacements',len(production['compile_results'])==4 and {r['id'] for r in production['compile_results']}==set(IDS) and all(r['actual_arm64_object'] for r in production['compile_results']))
        for row in production['compile_results']:
            argv,cwd=self.command(row['id'],ROOT/row['source'],ROOT/row['output'])
            process=next(c for c in production['commands'] if c['stdout'].endswith('/compile-'+row['id'].replace('/','-')+'.stdout.txt'))
            self.check('exact-genuine-full-command-'+row['id'],process['argv']==argv and process['cwd']==str(cwd) and process['exit_code']==0 and not process['timed_out'])
        for name,witness in self.witness['files'].items():
            self.check('exact-patch-and-original-'+name,sha(KERNEL/name)==witness['original_sha256'] and sha(parent/'source'/name)==witness['patched_sha256'])
        original=next(r for r in production['compile_results'] if r['id']==IDS[0]);before=thin(ROOT/original['original_output']);after=thin(ROOT/original['output'])
        self.check('cache-section-symbol-layout-preserved',[(s['segment'],s['name'],s['address'],s['size'],s['nreloc']) for s in before['sections']]==[(s['segment'],s['name'],s['address'],s['size'],s['nreloc']) for s in after['sections']])
        self.check('actual-source-reversions-and-noop-controls',len(controls['reverted_source_controls'])==3 and controls['negative_noop_cache']['actual_arm64_object'])
        s2r=controls['enabled_S2R'];self.check('actual-enabled-S2R-size-storage',s2r['size']==8 and s2r['actual_zero_storage']==[0]*8 and sha(ROOT/s2r['object'])==s2r['object_sha256'])
        self.check('actual-all-four-platform-macro-cases',len(controls['platform_branch_controls'])==4 and all(bool(r['actual_macros']) for r in controls['platform_branch_controls']))
        stage2=storage['stage2_storage_control'];self.check('actual-preserved-stage2-producer-storage',stage2['size']==128 and stage2['negative_exit_code']!=0 and sha(ROOT/stage2['object'])==stage2['object_sha256'])
        status=production['link_symbol_status'];missing=json.loads((parent/'unresolved-symbols.json').read_text())
        self.check('actual19-unresolved-names-no-strong-duplicates',len(missing)==status['unresolved_required_names']==19 and status['strong_duplicates']==0)
        baseline=json.loads((ROOT/'fixtures/public/xnu-kernel-link-inputs/qualified-component.json').read_text())
        expected={n for n,r in baseline['unresolved_name_classification'].items() if r['category']!='selected_source_or_configuration_gap'}
        self.check('remaining-gates-exact-real-linker-and-components',set(missing)==expected)
        self.check('all-full-kernel-SDK-private-ABI-crypto-native-limits-false',all(not r[k] for r in reports.values() for k in ['full_kernel_qualified','full_archive_link_qualified','full_crypto_qualified','apple_private_abi_qualified','apple_interoperability_qualified','device_executed','sdk_used','native_device_qualified']))
        self.must(['rg','-n','clean_mmu_dcache|SleepToken|iBoot_Stage_2_version',KERNEL],'complete-original-source-reference-inventory')
        self.must(['make','check'],'repository-make-check',cwd=ROOT,timeout=300)
        self.check('required-repository-checks',True)
        good=all(c['pass_check'] for c in self.report['checks'])
        self.report['acceptance_assessment']=[dict(criterion=i+1,pass_check=good,evidence=e) for i,e in enumerate([
            'Complete original reference inventory;KLINK-009 baseline plus actual selected consumer/producer/platform macro controls',
            'Exact four-file APSL patch;unchanged cache/start bytes;real same-address cache alias;canonical five platform guards and conditional S2R export',
            'Four genuine current target recipes;982-object LLVM/nlist audit;real enabled8-byte S2R and128-byte stage2 storage;source reversion,no-op and size mutations',
            'All978 untouched objects and3152 original dependency witnesses preserved;coherent replacement manifest;19 exact remaining linker/library names;explicit SDK/private-ABI/crypto/runtime/native limits;make check'])]
        self.report['link_symbol_status']=status
        self.report['maintained_files_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'docs/procedures/xnu-kernel-symbol-gaps.md',*sorted(PATCH.parent.glob('*')),*sorted(FIXTURES.glob('*'))] if p.is_file()}

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Measured genuine selected source-symbol fixes and target/configuration controls;full kernel,SDK,Apple ABI,crypto,runtime,native unqualified'
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--mode',choices=['production','controls','storage','acceptance'],required=True);args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Canonical fresh run required')
    args.compiler,args.compiler_evidence,args.header_evidence,args.resource_evidence=VECTOR_COMPILER,'VCOMP-002','FHDR-003','RHDR-002'
    args.storage_evidence='CXXST-007';args.port_evidence='KDECL-004';args.object_evidence='IIGOBJ-003';args.jobs=1
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));build=SymbolGaps(args)
    try:
        build.inputs()
        if args.mode=='controls':build.controls()
        elif args.mode=='storage':build.platform_storage()
        elif args.mode=='acceptance':build.acceptance()
        else:build.production()
    except Exception as error:build.report['error']=str(error)
    # Capture the complete owned prefix and exact commands, including failures.
    return build.finish()


if __name__=='__main__':sys.exit(main())
