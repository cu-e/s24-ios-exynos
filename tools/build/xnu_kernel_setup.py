#!/usr/bin/env python3
"""Generate genuine selected XNU assembly offsets and local version metadata."""
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
import struct
import subprocess
import sys

from xnu_kernel_syscalls import Syscalls,ObjectData,ROOT,KERNEL,KOBJECT,HOST,COMPILER,registered,sha,dump,NDK,macho


class Setup(Syscalls):
    def __init__(self,args):
        self.args=args
        self.out=ROOT/'artifacts/xnu-kernel-setup'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Use canonical fresh paths')
        self.out.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text())
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',
            recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),mode=args.mode,
            commands=[],checks=[],device_executed=False,sdk_used=False,
            full_kernel_qualified=False,apple_private_abi_qualified=False)

    def inputs(self):
        super().inputs()
        for name in ['KSYSC-002','KSYSC-004','KSYSC-006','KSYSC-007']:
            registered(name,self.ledger)
            e=next(e for e in self.ledger['experiments'] if e['id']==name)
            self.report['parents'][name]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.osfmk_config=KOBJECT/'configuration/osfmk/RELEASE/Makefile'
        self.report['setup_inputs']={str(p.relative_to(ROOT)):sha(p) for p in [
            self.osfmk_config,KERNEL/'osfmk/arm64/genassym.c',KERNEL/'config/newvers.pl',
            KERNEL/'config/MasterVersion',KERNEL/'config/version.c',KERNEL/'libkern/libkern/Makefile',
            KERNEL/'libkern/libkern/version.h.template',KERNEL/'makedefs/MakeInc.kernel']}
        if (KERNEL/'config/MasterVersion').read_text().splitlines()[0]!='22.5.0':raise ValueError('Selected source master version changed')
        self.reuse_generation();self.reuse_syscalls()

    def setup_make_args(self,directory):
        argv=super().make_args(directory)
        argv=[a for a in argv if not a.startswith(('TARGET=','CONFIG_DEFINES='))]
        text=self.osfmk_config.read_text()
        defs=re.findall(r'^export CONFIG_DEFINES = (.*)$',text,re.M)
        if len(defs)!=1:raise ValueError('Actual osfmk CONFIG_DEFINES missing')
        return [*argv,'TARGET='+str(self.out/'generated/osfmk'),'CONFIG_DEFINES='+defs[0],
            'NEWVERS='+str(KERNEL/'config/newvers.pl')]

    def query_setup(self):
        query=self.out/'query-osfmk.mk'
        text=self.osfmk_config.read_text()
        lines=text.splitlines()
        compile_line=next(line.strip() for line in lines if '${GENASSYM_KCC}' in line)
        sed_line=next(line.strip() for line in lines if line.strip().startswith('$(_v)sed ') and 'DEFINITION__define__' in line)
        keys=['GENASSYM_LOCATION','CFLAGS','INCFLAGS','CFLAGS_NOLTO_FLAG','GENASSYM_KCC']
        query.write_text('include '+str(self.osfmk_config)+'\n'+
            '\n'.join('$(info S24_SETUP|'+k+'|$('+k+'))' for k in keys)+
            '\n$(eval @ := genassym.o)\n$(eval < := $(SOURCE_DIR)/$(COMPONENT)/$(GENASSYM_LOCATION)/genassym.c)\n'+
            '$(info S24_SETUP|GENASSYM|'+compile_line+')\n$(eval @ := assym.s)\n'+
            '$(info S24_SETUP|EXTRACT|'+sed_line+')\n.PHONY: s24_query\ns24_query: ;\n')
        cwd=self.out/'generated/osfmk';cwd.mkdir(parents=True)
        output=self.must(['make','--no-print-directory','-rR','-f',query,*self.setup_make_args(KERNEL/'osfmk'),'s24_query'],'query-osfmk',cwd=cwd)
        values={a[1]:a[2] for line in output.splitlines() if line.startswith('S24_SETUP|') and len(a:=line.split('|',2))==3}
        if set(values)!=set(keys+['GENASSYM','EXTRACT']):raise ValueError('Incomplete actual setup query')
        self.report['setup_rules']=values
        return values,cwd

    def generate_setup(self):
        values,cwd=self.query_setup()
        source=KERNEL/'osfmk/arm64/genassym.c'
        argv=shlex.split(values['GENASSYM'])
        if Path(argv[0])!=COMPILER or Path(argv[-1])!=source or '-S' not in argv or '-fno-integrated-as' not in argv:
            raise ValueError('Genuine target genassym recipe differs')
        output=cwd/'genassym.o'
        argv[argv.index('-o')+1]=str(output)
        argv += ['-MF',str(cwd/'genassym.d')]
        extra=self.object_report['additional_witnessed_include_roots']
        old={str(ROOT/'artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/mach-server-headers'),
            str(ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/mach-headers')}
        roots=[self.syscalls_root,self.generated_root/'internal/osfmk',self.generated_root/'export/osfmk',self.osfmk_config.parent]
        argv=[argv[0],*[a for p in roots for a in ['-I',str(p)]],*argv[1:],*[a for p in extra if p not in old for a in ['-I',p]]]
        code,_,stderr=self.run(argv,'genassym-compile',cwd=cwd,timeout=120)
        self.check('real-target-genassym',code==0 and output.is_file(),exit_code=code,diagnostic=stderr[-4000:])
        if code:raise ValueError('Actual target genassym failed')
        command=shlex.split(values['EXTRACT'])
        if command[-2:]!=['>','assym.s'] or command[0]!='sed':raise ValueError('Actual extraction recipe differs')
        self.must(command[:-2],'assym-extract',cwd=cwd)
        assym=cwd/'assym.s'
        shutil.copyfile(self.out/'assym-extract.stdout.txt',assym)
        definitions=re.findall(r'^#define\s+([A-Za-z0-9_]+)\s+([^\n]+)$',assym.read_text(),re.M)
        self.check('real-extracted-definitions',bool(definitions) and len(definitions)==len(set(k for k,v in definitions)),count=len(definitions))
        self.report['assym']=dict(source=str(source.relative_to(ROOT)),assembly=str(output.relative_to(ROOT)),assembly_sha256=sha(output),
            header=str(assym.relative_to(ROOT)),header_sha256=sha(assym),definitions=dict(definitions))
        include=self.out/'generated/include/libkern';include.mkdir(parents=True)
        header=include/'version.h'
        shutil.copyfile(KERNEL/'libkern/libkern/version.h.template',header)
        version=self.out/'generated/version.c'
        shutil.copyfile(KERNEL/'config/version.c',version)
        stamp=['env','-u','RC_XBS','SRCROOT='+str(KERNEL),'OBJROOT='+str(self.out/'generated'),
            'TARGET='+str(cwd),'CURRENT_KERNEL_CONFIG_LC=release',
            'KERNEL_BUILD_DATE='+self.report['recorded_at'],'KERNEL_BUILD_OBJROOT=s24-ios-exynos-local/'+self.args.run+'/RELEASE_ARM64_E1S',
            'perl',str(KERNEL/'config/newvers.pl'),str(header),str(version)]
        self.must(stamp,'stamp-local-version',cwd=self.out)
        self.check('actual-version-placeholders-resolved',all('###KERNEL_' not in p.read_text() for p in [header,version]))
        self.report['local_version']=dict(master_version='22.5.0',kernel_profile='RELEASE/ARM64/E1S/iPhoneOS',
            build_origin='local development build, not an Apple release',date=self.report['recorded_at'],
            object_root='s24-ios-exynos-local/'+self.args.run+'/RELEASE_ARM64_E1S',header=str(header.relative_to(ROOT)),header_sha256=sha(header),
            source=str(version.relative_to(ROOT)),source_sha256=sha(version),builder_identity_retained_only_in_local_generated_artifacts=True)

    def reuse_setup(self):
        if not self.args.setup_evidence:raise ValueError('Supply recorded setup generation evidence')
        doc=registered(self.args.setup_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one setup generation report')
        previous=json.loads(paths[0].read_text())
        if previous['outcome']!='pass':raise ValueError('Require passing target offset/version generation')
        self.setup_root=paths[0].parent/'generated'
        for section,fields in [('assym',[('header','header_sha256'),('assembly','assembly_sha256')]),
            ('local_version',[('header','header_sha256'),('source','source_sha256')])]:
            for name,digest in fields:
                if sha(ROOT/previous[section][name])!=previous[section][digest]:raise ValueError('Generated setup input changed')
        self.report['setup_parent']=dict(evidence=self.args.setup_evidence,path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))

    def parent_profile(self):
        path=ROOT/'artifacts/xnu-kernel-syscalls/full-profile-session1/report.json'
        parent=json.loads(path.read_text())
        self.previous={r['id']:r for r in parent['compile_results']}
        self.previous_processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in parent['commands'] if Path(c['stdout']).name.startswith('compile-')}
        self.report['original_recipe_parent']=dict(evidence='KSYSC-004',path=str(path.relative_to(ROOT)),sha256=sha(path))

    def object_command(self,row,source,output):
        original=ROOT/self.previous[row['id']]['source']
        argv,cwd=super().object_command(row,original,output)
        if source!=original:
            if row['id']!='osfmk/startup.o' or source!=getattr(self,'startup',None):raise ValueError('Unexpected source port')
            argv[argv.index(str(original))]=str(source)
        # Parent recipes already consume the immutable syscall include root;
        # Syscalls adds it again, so retain the original once for exact reuse.
        if argv[1:3]==['-I',str(self.syscalls_root)]:del argv[1:3]
        return [argv[0],'-I',str(self.setup_root/'include'),'-I',str(self.setup_root/'osfmk'),*argv[1:]],cwd

    def source_for(self,row):
        if row['id']=='osfmk/startup.o' and hasattr(self,'startup'):return self.startup
        return super().source_for(row)

    def prepare_startup(self):
        root=self.out/'source-ports'
        self.startup=root/'osfmk/kern/startup.c'
        self.startup.parent.mkdir(parents=True)
        original=KERNEL/'osfmk/kern/startup.c'
        shutil.copyfile(original,self.startup)
        patch=ROOT/'patches/kernel-setup/0001-startup-minimac-declaration-guard.patch'
        shutil.copyfile(patch,self.out/patch.name)
        self.must(['git','-C',root,'apply','--check',patch],'startup-patch-check')
        self.must(['git','-C',root,'apply',patch],'startup-patch-apply')
        self.report['startup_source_port']=dict(original=str(original.relative_to(ROOT)),original_sha256=sha(original),
            source=str(self.startup.relative_to(ROOT)),source_sha256=sha(self.startup),patch=str(patch.relative_to(ROOT)),patch_sha256=sha(patch),
            actual_definition='bsd/kern/kern_minimac.c',definition_source_sha256=sha(KERNEL/'bsd/kern/kern_minimac.c'))

    def query_version(self):
        query=self.out/'query-version.mk'
        rules=(KERNEL/'makedefs/MakeInc.kernel').read_text()
        line=rules.split('version.o: $(OBJPATH)/version.c',1)[1].splitlines()[2].strip()
        if line!='${C_RULE_1A}$<':raise ValueError('Actual direct version compilation rule changed')
        query.write_text('include '+str(KERNEL/'makedefs/MakeInc.def')+'\ninclude '+str(KERNEL/'makedefs/MakeInc.rule')+
            '\n$(eval @ := version.o)\n$(eval < := '+str(self.setup_root/'version.c')+')\n'+
            '$(info S24_VERSION|COMPILE|'+line+')\n$(info S24_VERSION|C_RULE_4|$(C_RULE_4))\n'+
            '.PHONY: s24_query\ns24_query: ;\n')
        argv=self.setup_make_args(KERNEL)
        argv=[a for a in argv if not a.startswith('CONFIG_DEFINES=')]+['CONFIG_DEFINES=']
        output=self.must(['make','--no-print-directory','-rR','-f',query,*argv,'s24_query'],'query-version',cwd=self.out)
        values={a[1]:a[2] for line in output.splitlines() if line.startswith('S24_VERSION|') and len(a:=line.split('|',2))==3}
        if set(values)!=set(['COMPILE','C_RULE_4']) or values['C_RULE_4']:raise ValueError('Unqualified direct version postprocessor')
        self.report['direct_version_rules']=dict(source='makedefs/MakeInc.kernel',source_sha256=sha(KERNEL/'makedefs/MakeInc.kernel'),expanded=values)
        argv=shlex.split(values['COMPILE'])
        if Path(argv[0])!=COMPILER or Path(argv[-1])!=self.setup_root/'version.c':raise ValueError('Actual version compiler/source differs')
        output=self.out/'objects/kernel/version.o';output.parent.mkdir(parents=True,exist_ok=True)
        if '-o' in argv:argv[argv.index('-o')+1]=str(output)
        else:argv += ['-o',str(output)]
        argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
        argv=[argv[0],'-I',str(self.setup_root/'include'),*argv[1:]]
        return argv,output

    def compile_setup(self):
        self.parent_profile()
        if self.args.startup_declaration:self.prepare_startup()
        selected={r['id'] for r in json.loads((ROOT/'fixtures/public/xnu-kernel-syscalls/unresolved-objects.json').read_text())
            if any(h in ['assym.s','libkern/version.h'] for h in r.get('missing_headers',[]))}
        rows=[(r,self.source_for(r)) for r in self.object_report['inventory'] if self.source_for(r) and
            (self.args.selection=='all' or r['id'] in selected)]
        self.report['compile_selection']=self.args.selection
        self.report['compile_results']=[]
        def one(item):
            row,source=item
            directory=self.out/'objects'/row['component'];directory.mkdir(parents=True,exist_ok=True)
            output=directory/row['target']
            argv,cwd=self.object_command(row,source,output)
            code,_,stderr=self.run(argv,'compile-'+row['id'].replace('/','-'),cwd=cwd,timeout=120)
            good=code==0 and output.is_file() and macho(output)['filetype']==1
            return dict(id=row['id'],source=str(source.relative_to(ROOT)),source_sha256=sha(source),parent_status=self.previous[row['id']]['actual_arm64_object'],
                exit_code=code,actual_arm64_object=good,output=str(output.relative_to(ROOT)) if good else None,output_sha256=sha(output) if good else None,
                missing_headers=re.findall(r"fatal error: '([^']+)' file not found",stderr),errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$',stderr)[:16],diagnostic=stderr[-3000:])
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for index,result in enumerate(pool.map(one,rows),1):
                self.report['compile_results'].append(result)
                if index%40==0:dump(self.out/'progress.json',dict(completed=index,total=len(rows),actual_arm64=sum(r['actual_arm64_object'] for r in self.report['compile_results'])))
        argv,output=self.query_version()
        code,_,stderr=self.run(argv,'compile-kernel-version.o',cwd=self.out,timeout=120)
        good=code==0 and output.is_file() and macho(output)['filetype']==1
        self.report['direct_version_object']=dict(id='kernel/version.o',source=str((self.setup_root/'version.c').relative_to(ROOT)),source_sha256=sha(self.setup_root/'version.c'),
            exit_code=code,actual_arm64_object=good,output=str(output.relative_to(ROOT)) if good else None,output_sha256=sha(output) if good else None,diagnostic=stderr[-3000:])
        self.check('direct-version-object',good,exit_code=code,diagnostic=stderr[-2000:])
        values=self.report['compile_results']
        regressions=[r['id'] for r in values if r['parent_status'] and not r['actual_arm64_object']]
        self.check('no-crashes-timeouts',all(c['exit_code'] in [0,1] and not c['timed_out'] for c in self.report['commands']))
        self.check('prior-object-regressions',not regressions,regressions=regressions)
        selected_values=[r for r in values if r['id'] in selected]
        self.check('all-affected-selected-files-attempted',len(selected_values)==len(selected),count=len(selected))
        self.report['compile_counts']=dict(attempted=len(values),actual_arm64=sum(r['actual_arm64_object'] for r in values),
            affected_attempted=len(selected_values),affected_arm64=sum(r['actual_arm64_object'] for r in selected_values),
            prior_object_regressions=regressions,direct_version_arm64=good)
        dump(self.out/'compile-results.json',values)

    def setup_contract(self):
        parent_path=self.setup_root.parent/'report.json'
        parent=json.loads(parent_path.read_text())
        assembly=(ROOT/parent['assym']['assembly']).read_text()
        labels=re.findall(r'(?m)^\s*DEFINITION__define__([A-Za-z0-9_]+):',assembly)
        definitions=parent['assym']['definitions']
        if len(labels)!=len(set(labels)) or set(definitions)!={k for n in labels for k in [n,n+'_NUM']}:
            raise ValueError('Extracted definition set differs from real target assembly')
        for name in labels:
            if not re.fullmatch(r'-?[0-9]+',definitions[name+'_NUM']):raise ValueError('Invalid actual numeric offset')
            if int(definitions[name].lstrip('$#'))!=int(definitions[name+'_NUM']):raise ValueError('Primary/numeric definitions disagree')
        expected=self.out/'expected-offsets.h'
        def expected_header(changed=False):
            return '\n'.join('#define S24_ASSYM_'+name+' '+hex((int(definitions[name+'_NUM'])+(8 if changed and name=='TH_RECOVER' else 0))&((1<<64)-1))+'ULL' for name in labels)+'\n'
        expected.write_text(expected_header())
        original=KERNEL/'osfmk/arm64/genassym.c'
        text=original.read_text();begin=text.index('#define DECLARE(SYM, VAL)');end=text.index('\n\n',begin)
        anchor=text[begin:end]
        if '__asm(' not in anchor:raise ValueError('Actual DECLARE source changed')
        text=text.replace(anchor,'#include "expected-offsets.h"\n#define DECLARE(SYM,VAL) _Static_assert((u_long)(VAL)==(u_long)S24_ASSYM_##SYM,"actual-target-offset-mismatch")')
        text,count=re.subn(r'DECLARE\("([A-Za-z0-9_]+)"\s*,',r'DECLARE(\1,',text)
        if count<len(labels):raise ValueError('Actual DECLARE rewrite incomplete')
        source=self.out/'target-offset-check.c';source.write_text(text)
        process=next(c for c in parent['commands'] if c['stdout'].endswith('/genassym-compile.stdout.txt'))
        argv=[a for a in process['argv'] if a not in ['-S','-fno-integrated-as']]
        argv[argv.index(str(original))]=str(source)
        argv[argv.index('-o')+1]=str(self.out/'target-offset-check.o')
        argv[argv.index('-MF')+1]=str(self.out/'target-offset-check.d')
        argv += ['-c']
        code,_,stderr=self.run(argv,'target-offsets',cwd=Path(process['cwd']),timeout=120)
        self.check('all-active-target-layout-expressions',code==0 and (self.out/'target-offset-check.o').is_file(),exit_code=code,
            active_definition_count=len(labels),source_rewrites=count,diagnostic=stderr[-2600:])
        changed_dir=self.out/'changed-offset-inputs';changed_dir.mkdir()
        (changed_dir/'expected-offsets.h').write_text(expected_header(True))
        changed_source=changed_dir/source.name;shutil.copyfile(source,changed_source)
        command=argv.copy();command[command.index(str(source))]=str(changed_source)
        command[command.index('-o')+1]=str(self.out/'changed-target-offset.o')
        command[command.index('-MF')+1]=str(self.out/'changed-target-offset.d')
        code,_,stderr=self.run(command,'changed-target-offset',cwd=Path(process['cwd']),timeout=120)
        self.check('real-offset-mutation-rejected',code==1 and 'actual-target-offset-mismatch' in stderr,exit_code=code,diagnostic=stderr[-2600:])
        registered('KSETUP-002',self.ledger)
        path=ROOT/'artifacts/xnu-kernel-setup/affected-session1/objects/kernel/version.o'
        def version_check(obj):
            observed={n:obj.value('_'+n,'<i')[0] for n in ['version_major','version_minor','version_revision','version_stage','version_prerelease_level']}
            if observed!=dict(version_major=22,version_minor=5,version_revision=0,version_stage=0x80,version_prerelease_level=0):
                raise ValueError('Actual version data differs from source MasterVersion')
            def string(name):
                section,_,at=obj.location('_'+name,1)
                end=obj.data.find(b'\0',at,section['offset']+section['size'])
                if end<0:raise ValueError('Unterminated version string')
                return obj.data[at:end].decode('ascii')
            if string('osrelease')!='22.5.0' or string('osbuild_config')!='release' or 's24-ios-exynos-local/' not in string('version'):
                raise ValueError('Actual version strings lack selected/local provenance')
            return observed
        obj=ObjectData(path)
        self.check('actual-local-version-object',True,values=version_check(obj),local_build_label=True)
        changed=bytearray(obj.data);_,_,at=obj.location('_version_major',4);struct.pack_into('<i',changed,at,99)
        path=self.out/'changed-version.o';path.write_bytes(changed)
        try:version_check(ObjectData(path))
        except ValueError:self.check('actual-version-mutation-rejected',True)
        else:raise ValueError('Changed version accepted')
        fixture=self.out/'bad-version';(fixture/'config').mkdir(parents=True)
        (fixture/'config/MasterVersion').write_text('0.0.0\n')
        header=fixture/'version.h';shutil.copyfile(KERNEL/'libkern/libkern/version.h.template',header)
        env=['env','SRCROOT='+str(fixture),'OBJROOT='+str(fixture),'TARGET='+str(fixture),
            'CURRENT_KERNEL_CONFIG_LC=release','KERNEL_BUILD_OBJROOT=s24-ios-exynos-local/negative',
            'perl',str(KERNEL/'config/newvers.pl'),str(header)]
        code,_,stderr=self.run(env,'invalid-master-version',cwd=fixture)
        self.check('real-invalid-master-rejected',code!=0 and 'Invalid MasterVersion' in stderr,exit_code=code,diagnostic=stderr[-1200:])
        unknown=self.out/'unknown-placeholder';(unknown/'config').mkdir(parents=True)
        (unknown/'config/MasterVersion').write_text('22.5.0\n')
        header=unknown/'version.h';header.write_text('###KERNEL_VERSION_MAJOR###\n###KERNEL_VERSION_UNKNOWN###\n')
        env=['env','SRCROOT='+str(unknown),'OBJROOT='+str(unknown),'TARGET='+str(unknown),
            'CURRENT_KERNEL_CONFIG_LC=release','KERNEL_BUILD_OBJROOT=s24-ios-exynos-local/negative',
            'perl',str(KERNEL/'config/newvers.pl'),str(header)]
        code,_,stderr=self.run(env,'unknown-version-placeholder',cwd=fixture)
        self.check('unknown-placeholder-not-qualified',code==0 and '###KERNEL_' in header.read_text(),
            exit_code=code,production_placeholder_guard_rejects=True,upstream_script_itself_rejects=False)
        self.report['contract_input_snapshots']={str(p.relative_to(self.out)):sha(p) for p in
            [source,expected,changed_source,changed_dir/'expected-offsets.h',fixture/'config/MasterVersion',
             unknown/'config/MasterVersion',header]}

    def audit_setup(self):
        if not self.args.compilation_evidence:raise ValueError('Supply full compilation evidence')
        doc=registered(self.args.compilation_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one full setup compilation report')
        parent=json.loads(paths[0].read_text())
        if parent['compile_selection']!='all':raise ValueError('Require complete available-source profile')
        port=parent['startup_source_port']
        if sha(ROOT/port['original'])!=port['original_sha256'] or sha(ROOT/port['source'])!=port['source_sha256'] or sha(ROOT/port['patch'])!=port['patch_sha256']:
            raise ValueError('Qualified source port inputs changed')
        self.startup=ROOT/port['source'];self.report['startup_source_port']=port
        self.parent_profile()
        original={r['id']:r for r in self.object_report['inventory']}
        expected={r['id'] for r in original.values() if self.source_for(r)}
        results={r['id']:r for r in parent['compile_results']}
        processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in parent['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if set(results)!=expected or len(results)!=len(parent['compile_results']) or set(processes)!={n.replace('/','-') for n in expected|{'kernel/version.o'}}:
            raise ValueError('Full actual source/process selection incomplete')
        objects=[];compiled=[];unresolved=[];inputs={};dependencies={};groups=Counter();headers=Counter()
        def dependencies_for(identifier,source,process):
            dep=Path(process['argv'][process['argv'].index('-MF')+1]);cwd=Path(process['cwd'])
            line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(cwd/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            if source.resolve() not in files:raise ValueError('Actual dependency source mismatch')
            names=[]
            for p in files:
                n=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                if n not in inputs:inputs[n]=sha(p)
                names.append(n)
            dependencies[identifier]=dict(depfile=str(dep.relative_to(ROOT)),depfile_sha256=sha(dep),inputs=sorted(set(names)))
        for identifier,result in results.items():
            row=original[identifier];source=self.source_for(row);process=processes[identifier.replace('/','-')]
            output=Path(process['argv'][process['argv'].index('-o')+1])
            argv,cwd=self.object_command(row,source,output)
            if argv!=process['argv'] or str(cwd)!=process['cwd'] or str(source.relative_to(ROOT))!=result['source'] or sha(source)!=result['source_sha256']:
                raise ValueError('Full recipe/source changed beyond declared setup/port transformations')
            if process['exit_code']!=result['exit_code'] or process['timed_out'] or process['exit_code'] not in [0,1]:
                raise ValueError('Actual compiler status mismatch/crash/timeout')
            text=(ROOT/process['stderr']).read_text(errors='replace')
            if not result['actual_arm64_object']:
                missing=re.findall(r"fatal error: '([^']+)' file not found",text)
                category='missing_header' if missing else 'unsupported_metadata' if 'error: experimental XNU metadata does not support' in text else 'other_compile_error'
                groups[category]+=1;headers.update(missing)
                unresolved.append(dict(id=identifier,category=category,missing_headers=missing,errors=result['errors']))
                continue
            if process['exit_code']!=0 or output!=ROOT/result['output'] or sha(output)!=result['output_sha256'] or macho(output)['filetype']!=1:
                raise ValueError('Actual object bytes/format changed')
            objects.append(output)
            compiled.append({k:result[k] for k in ['id','source','source_sha256','output','output_sha256','parent_status']})
            dependencies_for(identifier,source,process)
        for row in original.values():
            if row['id'] not in expected:unresolved.append(dict(id=row['id'],category='missing_source_or_recipe',source=row['source']))
        version=parent['direct_version_object'];process=processes['kernel-version.o'];source=self.setup_root/'version.c'
        argv=shlex.split(parent['direct_version_rules']['expanded']['COMPILE'])
        output=ROOT/version['output']
        if '-o' in argv:argv[argv.index('-o')+1]=str(output)
        else:argv += ['-o',str(output)]
        argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
        argv=[argv[0],'-I',str(self.setup_root/'include'),*argv[1:]]
        if argv!=process['argv'] or Path(process['cwd'])!=paths[0].parent or process['exit_code']!=0 or process['timed_out'] or sha(output)!=version['output_sha256'] or macho(output)['filetype']!=1 or sha(source)!=version['source_sha256']:
            raise ValueError('Actual direct version source/recipe/object changed')
        dependencies_for('kernel/version.o',source,process)
        objects.append(output)
        self.report['direct_version_object']=version
        text=self.must([NDK/'llvm-readobj','--file-headers',*objects],'audit-llvm-headers',timeout=120)
        self.check('independent-arm64-headers',text.count('Format: Mach-O arm64')==len(objects),count=len(objects))
        text=self.must([NDK/'llvm-nm','--defined-only','--format=posix',*objects],'audit-llvm-symbols',timeout=120)
        counts=Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+',text))
        self.check('actual-code-symbols',counts['T']+counts['t']>0,defined_symbol_types=dict(counts))
        provider=next(ROOT/r['output'] for r in compiled if r['id']=='bsd/kern_minimac.o')
        caller=next(ROOT/r['output'] for r in compiled if r['id']=='osfmk/startup.o')
        defined=self.must([NDK/'llvm-nm','--defined-only','--just-symbol-name',provider],'minimac-provider-symbols')
        undefined=self.must([NDK/'llvm-nm','--undefined-only','--just-symbol-name',caller],'startup-caller-symbols')
        self.check('actual-startup-provider-symbol-agreement','_minimac_policy_init' in defined.splitlines() and '_minimac_policy_init' in undefined.splitlines())
        regressions=[r['id'] for r in results.values() if r['parent_status'] and not r['actual_arm64_object']]
        self.check('prior-object-regressions',not regressions,regressions=regressions)
        self.check('complete-component-inventory',len(compiled)+len(unresolved)==len(original))
        self.report['coverage']=dict(selected=len(original),attempted=len(expected),actual_arm64=len(compiled),unresolved=len(unresolved),
            direct_version_arm64=True,actual_known_direct_objects=len(objects),known_direct_objects=982,known_direct_unresolved=982-len(objects),
            additional_component_objects=sum(not r['parent_status'] for r in compiled),prior_successes=sum(r['parent_status'] for r in compiled),
            prior_object_regressions=regressions,failure_categories=dict(groups),missing_headers=dict(headers),
            unique_dependency_files=len(inputs),defined_symbol_types=dict(counts))
        self.report['compilation_parent']=dict(evidence=self.args.compilation_evidence,path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        for name,value in [('compiled-objects',compiled),('unresolved-objects',unresolved),('dependency-files',inputs),('object-dependencies',dependencies)]:
            dump(self.out/(name+'.json'),value)

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Genuine selected target assembly offsets/local version/setup object assessment; full kernel/Apple private ABI/native qualification remains false'
        dump(self.out/'report.json',self.report)
        files=[p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json']
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:16],commands_scope='Representative exact commands; every execution retained in hashed report.json',
            actual_command_count=len(self.report['commands']),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['generate','compile','contract','audit'],default='generate')
    p.add_argument('--generation-evidence',default='KMIG-003')
    p.add_argument('--syscalls-evidence',default='KSYSC-002')
    p.add_argument('--setup-evidence')
    p.add_argument('--compilation-evidence')
    p.add_argument('--selection',choices=['affected','all'],default='affected')
    p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--startup-declaration',action='store_true',help='Apply source-backed minimac declaration guard fix in a copied source')
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run) or not 1<=args.jobs<=3:p.error('Use fresh canonical run names and1..3 jobs')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    build=Setup(args)
    try:
        build.inputs()
        if args.mode=='generate':build.generate_setup()
        else:
            build.reuse_setup()
            if args.mode=='compile':build.compile_setup()
            elif args.mode=='contract':build.setup_contract()
            else:build.audit_setup()
    except Exception as error:build.report['error']=str(error)
    return build.finish()

if __name__=='__main__':sys.exit(main())
