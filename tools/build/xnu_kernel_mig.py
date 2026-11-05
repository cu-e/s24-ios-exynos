#!/usr/bin/env python3
"""Generate genuine selected XNU MIG inputs in isolated host paths."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys

from xnu_compiler_hardening import Audit, ROOT, NDK, registered, sha, dump
from xnu_macho_tools import macho

KERNEL = ROOT / 'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'
KOBJECT = ROOT / 'artifacts/xnu-kernel-objects/compile-session2'
HOST = ROOT / 'artifacts/xnu-host-tools/generators-session2/prefix/bin'
COMPILER = ROOT / 'artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang'
KEYS = ['COMP_SUBDIRS','COMP_FILES','MIGFLAGS','MIGKUFLAGS','MIGKSFLAGS',
        'MIG_UUHDRS','MIG_USHDRS','MIG_KUHDRS','MIG_KSHDRS','MIG_KUSRC','MIG_KSSRC','DEVICE_FILES']


class Mig(Audit):
    def __init__(self,args):
        self.args=args
        self.out=ROOT/'artifacts/xnu-kernel-mig'/args.run
        if self.out.resolve()!=self.out: raise ValueError('Use canonical fresh paths')
        self.out.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text())
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',
            recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),mode=args.mode,
            commands=[],checks=[],device_executed=False,sdk_used=False,
            full_kernel_qualified=False,apple_private_abi_qualified=False)

    def inputs(self):
        super().inputs()
        self.report['parents']={}
        for name in ['HOSTGEN-002','KOBJECT-003','ATCOMP-004','ATCOMP-007','ATCOMP-009','ATCOMP-010','IIGABI-013']:
            registered(name,self.ledger)
            e=next(e for e in self.ledger['experiments'] if e['id']==name)
            self.report['parents'][name]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        component=json.loads((ROOT/'fixtures/public/xnu-compiler-atomics/qualified-component.json').read_text())
        if sha(COMPILER)!=component['compiler']['sha256']:raise ValueError('Candidate compiler changed')
        self.compiler=COMPILER
        self.report['compiler_sha256']=sha(COMPILER)
        witness=ROOT/'artifacts/xnu-dependencies/firehose-session1/kernel-source-files.json'
        parent=json.loads((ROOT/'fixtures/public/xnu-dependencies/firehose-session1.json').read_text())
        if sha(witness)!=parent['kernel_tree_manifest_sha256']:raise ValueError('Prepared source witness changed')
        files=json.loads(witness.read_text())
        actual={str(p.relative_to(KERNEL)) for p in KERNEL.rglob('*') if p.is_file() and '.git' not in p.relative_to(KERNEL).parts}
        if actual!=set(files) or any(sha(KERNEL/p)!=h for p,h in files.items()):raise ValueError('Prepared source changed')
        self.report['prepared_source_witness_sha256']=sha(witness)
        self.object_report=json.loads((KOBJECT/'report.json').read_text())
        self.shim=self.out/'host-commands.mk'
        shutil.copyfile(KOBJECT/'host-commands.mk',self.shim)
        self.config=KOBJECT/'configuration/osfmk/RELEASE/Makefile'
        found=re.findall(r'^export CONFIG_DEFINES = (.*)$',self.config.read_text(),re.M)
        if len(found)!=1:raise ValueError('Actual exported CONFIG_DEFINES not found')
        self.defines=found[0]
        self.report['config_defines']=dict(value=self.defines,makefile=str(self.config.relative_to(ROOT)),sha256=sha(self.config))
        self.report['generator_sha256']={n:sha(HOST/n) for n in ['mig','migcom']}

    def make_args(self,directory):
        relative=directory.relative_to(KERNEL)
        return ['SRCROOT='+str(KERNEL),'OBJROOT='+str(KOBJECT),'OBJPATH='+str(self.out/'build'),
            'TARGET='+str(self.out/'build/osfmk'),'SOURCE='+str(directory)+'/',
            'RELATIVE_SOURCE_PATH=./'+str(relative),'CURRENT_ARCH_CONFIG=ARM64',
            'CURRENT_ARCH_CONFIG_LC=arm64','CURRENT_KERNEL_CONFIG=RELEASE',
            'CURRENT_KERNEL_CONFIG_LC=release','CURRENT_MACHINE_CONFIG=E1S',
            'CURRENT_MACHINE_CONFIG_LC=e1s','PLATFORM=iPhoneOS',
            'SDKROOT='+str(self.out/'unavailable-sdk'),'CC='+str(COMPILER),
            'CXX='+str(COMPILER),'MIG='+str(HOST/'mig'),'MIGCOM='+str(HOST/'migcom'),
            'MIGCC='+str(COMPILER),'MakeInc_cmd='+str(self.shim),
            'ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64','BUILD_WERROR=0','BUILD_LTO=0',
            'DEPLOYMENT_TARGET_FLAGS=-target arm64-apple-ios16.5 -DXNU_TARGET_OS_IOS',
            'SEED_DEFINES=-DXNU_NO_TYPE_BUILTINS=0','CONFIG_DEFINES='+self.defines,
            'SHELL=/bin/bash','LOGCOLORS=n']

    def query(self,makefile,directory,name):
        output=self.out/'build'/directory.relative_to(KERNEL)
        output.mkdir(parents=True,exist_ok=True)
        query=self.out/('query-'+name+'.mk')
        query.write_text('include '+str(makefile)+'\n'+
            '\n'.join('$(info S24_MIG|'+k+'|$('+k+'))' for k in KEYS)+
            '\n.PHONY: s24_query\ns24_query: ;\n')
        argv=['make','--no-print-directory','-rR','-f',str(query),*self.make_args(directory)]
        text=self.must([*argv,'s24_query'],'query-'+name,cwd=output)
        values={a[1]:a[2] for line in text.splitlines() if line.startswith('S24_MIG|') and len(a:=line.split('|',2))==3}
        if set(values)!=set(KEYS):raise ValueError('Incomplete actual MIG variable query')
        return argv,output,values

    def inventory(self):
        _,_,top=self.query(self.config,KERNEL/'osfmk','osfmk')
        self.report['subdirectories']=top['COMP_SUBDIRS'].split()
        self.report['inventories']=[]
        self.report['recipes']=[]
        for child in self.report['subdirectories']:
            directory=KERNEL/'osfmk'/child
            makefile=directory/'Makefile'
            argv,output,values=self.query(makefile,directory,child)
            self.report['inventories'].append(dict(directory=child,makefile_sha256=sha(makefile),variables=values))
            # Dry-run each genuine source/header rule in a fresh directory.
            # No recursive build target is selected or executed.
            goals=sorted(set(values['COMP_FILES'].split()+values['MIG_UUHDRS'].split()+values['MIG_USHDRS'].split()))
            for goal in goals:
                text=self.must([*argv,'-n',goal],'recipe-'+child+'-'+goal,cwd=output)
                commands=[shlex.split(line) for line in text.replace('\\\n',' ').splitlines() if line.startswith(str(HOST/'mig')+' ')]
                if len(commands)!=1:raise ValueError('Expected exactly one actual MIG command: '+child+'/'+goal)
                command=commands[0]
                source=Path(command[-1]).resolve()
                if not source.is_relative_to(KERNEL) or source.suffix!='.defs' or not source.is_file():raise ValueError('Actual defs source invalid')
                files={flag:command[command.index(flag)+1] for flag in ['-user','-header','-server','-sheader'] if flag in command}
                row=dict(directory=child,goal=goal,argv=command,cwd=str(output),
                    source=str(source.relative_to(ROOT)),source_sha256=sha(source),outputs=files)
                self.report['recipes'].append(row)
        # Header/C goals occasionally have one multi-output recipe. Deduplicate
        # identical actual invocations, retaining every original goal above.
        unique={tuple(r['argv']):r for r in self.report['recipes']}
        self.recipes=list(unique.values())
        generated={(r['directory'],Path(v).name) for r in self.recipes for v in r['outputs'].values() if v!='/dev/null'}
        selected=[]
        for row in self.object_report['inventory']:
            if row['component']!='osfmk' or not row['generated_input']:continue
            path=(ROOT/row['source']).relative_to(KOBJECT/'configuration/osfmk/RELEASE')
            covered=(str(path.parent),path.name) in generated
            selected.append(dict(id=row['id'],path=str(path),has_generation_recipe=covered))
        self.check('all-selected-osfmk-generated-sources-mapped',bool(selected) and all(r['has_generation_recipe'] for r in selected),count=len(selected))
        self.report.update(selected_generated_sources=selected,unique_mig_commands=len(self.recipes))
        dump(self.out/'inventory.json',{k:self.report[k] for k in ['subdirectories','inventories','recipes','selected_generated_sources','unique_mig_commands']})

    def generate(self):
        self.report['generation']=[]
        tmp=self.out/'tmp';tmp.mkdir()
        wrapper=self.out/'preprocess.py'
        shutil.copyfile(ROOT/'fixtures/public/xnu-kernel-mig/preprocess.py',wrapper)
        wrapper.chmod(0o755)
        all_outputs={}
        dependency_inputs={}
        for index,row in enumerate(self.recipes):
            mode='internal' if any(v.endswith('.c') for v in row['outputs'].values() if v!='/dev/null') else 'export'
            directory=self.out/mode/'osfmk'/row['directory']
            directory.mkdir(parents=True,exist_ok=True)
            trace=self.out/'preprocessing'/str(index);trace.mkdir(parents=True)
            env=['env','MIGCC='+str(wrapper),'MIGCOM='+str(HOST/'migcom'),'SDKROOT=','TMPDIR='+str(tmp),
                 'S24_MIG_COMPILER='+str(COMPILER),'S24_MIG_TRACE='+str(trace),'S24_MIG_SOURCE='+str(ROOT/row['source'])]
            code,_,stderr=self.run([*env,*row['argv']],'generate-'+str(index),cwd=directory,timeout=90)
            outputs={}
            for name in row['outputs'].values():
                if name=='/dev/null':continue
                path=directory/name
                outputs[name]=dict(exists=path.is_file(),sha256=sha(path) if path.is_file() else None)
                if path.is_file():
                    relative=str(path.relative_to(self.out))
                    if relative in all_outputs and sha(path)!=all_outputs[relative]:raise ValueError('Conflicting same-mode generated output: '+relative)
                    all_outputs[relative]=sha(path)
            if code==0:
                record=json.loads((trace/'provenance.json').read_text())
                for p,h in record['inputs'].items():
                    if p in dependency_inputs and dependency_inputs[p]!=h:raise ValueError('Preprocessor dependency changed')
                    dependency_inputs[p]=h
            good=code==0 and bool(outputs) and all(p['exists'] for p in outputs.values())
            self.report['generation'].append(dict(recipe=index,mode=mode,directory=str(directory.relative_to(ROOT)),exit_code=code,outputs=outputs,diagnostic=stderr[-3000:]))
            self.check('generate-'+str(index),good,exit_code=code)
        self.check('all-mode-output-hashes-retained',all(sha(self.out/p)==h for p,h in all_outputs.items()),count=len(all_outputs))
        self.report['generated_files']=all_outputs
        self.report['preprocessor_dependency_count']=len(dependency_inputs)
        dump(self.out/'preprocessor-inputs.json',dependency_inputs)

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Actual selected MIG recipe/generation assessment; full kernel/IPC/Apple private ABI/native support remains unqualified'
        dump(self.out/'report.json',self.report)
        files=[p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json']
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:16],commands_scope='Representative exact commands; every execution retained in hashed report.json',
            actual_command_count=len(self.report['commands']),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),unique_mig_commands=self.report.get('unique_mig_commands'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1

    def reuse_generation(self):
        if not self.args.generation_evidence:raise ValueError('Supply recorded generation evidence')
        doc=registered(self.args.generation_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one generation report')
        self.generated_root=paths[0].parent
        previous=json.loads(paths[0].read_text())
        if previous['outcome']!='pass' or not previous.get('preprocessor_dependency_count'):
            raise ValueError('Require coherent generated mode trees and preprocessing provenance')
        self.generated=previous['generated_files']
        for path,h in self.generated.items():
            if not path.startswith(('internal/','export/')) or sha(self.generated_root/path)!=h:
                raise ValueError('Mode-separated generated input changed')
        inputs=json.loads((self.generated_root/'preprocessor-inputs.json').read_text())
        for path,h in inputs.items():
            if sha(Path(path))!=h:raise ValueError('Actual preprocessor dependency changed')
        self.report['generation_parent']=dict(experiment=self.args.generation_evidence,
            report=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))

    def compile_selected(self):
        processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in self.object_report['commands'] if Path(c['stdout']).name.startswith('compile-')}
        prior=json.loads((ROOT/'artifacts/xnu-compiler-atomics/full-existing-profile-session1/report.json').read_text())
        statuses={r['id']:r for r in prior['kernel_cases']}
        representatives={'osfmk/task.o','osfmk/host.o','iokit/IOMemoryDescriptor.cpo',
            'osfmk/resource_notify_user.o','osfmk/mach_vm_server.o','osfmk/device_server.o','osfmk/gssd_mach.o'}
        rows=[]
        for row in self.object_report['inventory']:
            gen=None
            if row['component']=='osfmk' and row['generated_input']:
                name=(ROOT/row['source']).relative_to(KOBJECT/'configuration/osfmk/RELEASE')
                gen=self.generated_root/'internal/osfmk'/name
                if not gen.is_file():raise ValueError('Selected generated MIG source absent: '+row['id'])
            if row['status']=='missing_source_or_recipe' and not gen:continue
            if self.args.selection=='representatives' and row['id'] not in representatives:continue
            rows.append((row,gen))
        if self.args.selection=='representatives' and {r['id'] for r,g in rows}!=representatives:
            raise ValueError('Required representative inventory incomplete')
        self.report['compile_selection']=self.args.selection
        old_roots={str(ROOT/'artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/mach-server-headers'),
            str(ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/mach-headers')}
        roots=[self.generated_root/'internal/osfmk',self.generated_root/'export/osfmk']
        self.report['generated_include_roots']=list(map(str,roots))

        def one(item):
            row,gen=item
            cwd=ROOT/self.object_report['configurations'][row['component']]['root']
            directory=self.out/'objects'/row['component'];directory.mkdir(parents=True,exist_ok=True)
            output=directory/row['target']
            if gen:
                argv=shlex.split(row['original_expanded_recipe'])
                if (cwd/argv[-1]).resolve()!=(ROOT/row['source']).resolve():raise ValueError('Original generated source rule mismatch')
                argv[-1]=str(gen)
                argv += [a for p in self.object_report['additional_witnessed_include_roots'] for a in ['-I',p]]
            else:
                original=processes[row['id'].replace('/','-')]
                if original['cwd']!=str(cwd) or sha(ROOT/row['source'])!=row['source_sha256']:
                    raise ValueError('Original source/context changed')
                argv=original['argv'].copy()
            if Path(argv[0])!=ROOT/'artifacts/xnu-compiler-hardening/ast-patch-session1/clang':
                raise ValueError('Original source compiler profile differs')
            argv[0]=str(COMPILER)
            for flag,value in [('-o',output),('-MF',output.with_suffix('.d'))]:
                if flag in argv:argv[argv.index(flag)+1]=str(value)
                else:argv += [flag,str(value)]
            filtered=[];at=0
            while at<len(argv):
                if argv[at]=='-I' and at+1<len(argv) and argv[at+1] in old_roots:at+=2;continue
                filtered.append(argv[at]);at+=1
            # osfmk's local generated tree precedes its exports. Other
            # components import the exported Mach interface; a private server
            # variant there imports types hidden without MACH_KERNEL_PRIVATE.
            ordered_roots=roots if row['component']=='osfmk' else list(reversed(roots))
            argv=[filtered[0],*[a for p in ordered_roots for a in ['-I',str(p)]],*filtered[1:]]
            if '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or any('xnu_clang_compat.h' in a for a in argv):
                raise ValueError('Real allocator checking profile lost')
            code,_,stderr=self.run(argv,'compile-'+row['id'].replace('/','-'),cwd=cwd,timeout=120)
            good=code==0 and output.is_file() and macho(output)['filetype']==1
            return dict(id=row['id'],generated_source=bool(gen),source=str((gen or ROOT/row['source']).relative_to(ROOT)),
                source_sha256=sha(gen or ROOT/row['source']),parent_status=statuses.get(row['id'],{}).get('actual_arm64_object'),
                exit_code=code,actual_arm64_object=good,output=str(output.relative_to(ROOT)) if good else None,
                output_sha256=sha(output) if good else None,missing_headers=re.findall(r"fatal error: '([^']+)' file not found",stderr),
                errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$' ,stderr)[:12],diagnostic=stderr[-2500:])
        self.report['compile_results']=[]
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for index,result in enumerate(pool.map(one,rows),1):
                self.report['compile_results'].append(result)
                if index%40==0:
                    dump(self.out/'progress.json',dict(completed=index,total=len(rows),actual_arm64=sum(r['actual_arm64_object'] for r in self.report['compile_results'])))
        values=self.report['compile_results']
        regressions=[r['id'] for r in values if r['parent_status'] is True and not r['actual_arm64_object']]
        self.report['compile_counts']=dict(attempted=len(values),actual_arm64=sum(r['actual_arm64_object'] for r in values),
            generated_attempted=sum(r['generated_source'] for r in values),generated_arm64=sum(r['generated_source'] and r['actual_arm64_object'] for r in values),
            prior_object_regressions=regressions)
        self.check('no-compiler-crashes-or-timeouts',all(c['exit_code'] in [0,1] and not c['timed_out'] for c in self.report['commands']))
        self.check('prior-object-regressions',not regressions,regressions=regressions)
        selected=[r for r in values if r['id'] in representatives]
        self.check('genuine-selected-representatives',len(selected)==len(representatives) and all(r['actual_arm64_object'] for r in selected),
            statuses={r['id']:r['actual_arm64_object'] for r in selected})
        dump(self.out/'compile-results.json',values)

    def contract(self):
        # Reuse the actual passing IOKit recipe, including original per-file
        # flags and all real exported/source include roots.
        doc=registered('KMIG-006',self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Representative source report missing')
        parent=json.loads(paths[0].read_text())
        process=next(c for c in parent['commands'] if c['stdout'].endswith('/compile-iokit-IOMemoryDescriptor.cpo.stdout.txt'))
        source=self.out/'header-contract.cpp'
        shutil.copyfile(ROOT/'fixtures/public/xnu-kernel-mig/header-contract.cpp',source)
        original=KERNEL/'iokit/Kernel/IOMemoryDescriptor.cpp'
        argv=process['argv'].copy();argv[argv.index(str(original))]=str(source)
        for name,extra,success,expected in [
            ('header-contract',[],True,''),
            ('wrong-size-type',['-DS24_WRONG_SIZE_TYPE=1'],False,'static assertion failed')]:
            command=[*argv,*extra]
            obj=self.out/(name+'.o');command[command.index('-o')+1]=str(obj)
            command[command.index('-MF')+1]=str(self.out/(name+'.d'))
            code,_,stderr=self.run(command,name,cwd=Path(process['cwd']),timeout=120)
            good=(code==0 and obj.is_file() and macho(obj)['filetype']==1) if success else code==1 and expected in stderr
            self.check(name,good,exit_code=code,diagnostic=stderr[-2500:])
        generated=json.loads((self.generated_root/'report.json').read_text())
        recipe=next(r for r in generated['recipes'] if r['directory']=='mach' and r['goal']=='mach_vm.h')
        mutation=self.out/'missing-private-define/mach';mutation.mkdir(parents=True)
        trace=self.out/'mutation-preprocessing';trace.mkdir()
        tmp=self.out/'tmp';tmp.mkdir()
        wrapper=self.out/'preprocess.py'
        shutil.copyfile(ROOT/'fixtures/public/xnu-kernel-mig/preprocess.py',wrapper);wrapper.chmod(0o755)
        command=[a for a in recipe['argv'] if a!='-DXNU_KERNEL_PRIVATE']
        command.insert(-1,'-UXNU_KERNEL_PRIVATE')
        env=['env','MIGCC='+str(wrapper),'MIGCOM='+str(HOST/'migcom'),'SDKROOT=','TMPDIR='+str(tmp),
            'S24_MIG_COMPILER='+str(COMPILER),'S24_MIG_TRACE='+str(trace),'S24_MIG_SOURCE='+str(ROOT/recipe['source'])]
        code,_,stderr=self.run([*env,*command],'regenerate-wrong-private-mode',cwd=mutation)
        self.check('regenerate-wrong-private-mode',code==0 and (mutation/'mach_vm.h').is_file(),exit_code=code)
        command=[argv[0],'-I',str(mutation.parent),*argv[1:]]
        command[command.index('-o')+1]=str(self.out/'wrong-private-mode.o')
        command[command.index('-MF')+1]=str(self.out/'wrong-private-mode.d')
        code,_,stderr=self.run(command,'wrong-private-mode',cwd=Path(process['cwd']),timeout=120)
        self.check('wrong-private-mode-rejected',code==1 and "conflicting types for 'mach_make_memory_entry'" in stderr,
            exit_code=code,diagnostic=stderr[-3000:])
        failure=self.out/'preprocessor-failure.defs'
        shutil.copyfile(ROOT/'fixtures/public/xnu-kernel-mig/preprocessor-failure.defs',failure)
        trace=self.out/'failure-preprocessing';trace.mkdir()
        failed=self.out/'failed-output';failed.mkdir()
        command=recipe['argv'].copy();command[-1]=str(failure)
        env=['env','MIGCC='+str(wrapper),'MIGCOM='+str(HOST/'migcom'),'SDKROOT=','TMPDIR='+str(tmp),
            'S24_MIG_COMPILER='+str(COMPILER),'S24_MIG_TRACE='+str(trace),'S24_MIG_SOURCE='+str(failure)]
        code,_,stderr=self.run([*env,*command],'preprocessor-failure',cwd=failed)
        self.check('real-preprocessor-failure-propagates',code==1 and 's24_expected_preprocessor_failure' in stderr,
            exit_code=code,partial_outputs_not_qualified=True,diagnostic=stderr[-1800:])

    def audit_compilation(self):
        if not self.args.compilation_evidence:raise ValueError('Supply full compilation evidence')
        doc=registered(self.args.compilation_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one full compilation report')
        report=json.loads(paths[0].read_text())
        if report['compile_selection']!='all':raise ValueError('Audit requires complete source selection')
        original={r['id']:r for r in self.object_report['inventory']}
        expected={r['id'] for r in original.values() if r['status']!='missing_source_or_recipe' or
            (r['component']=='osfmk' and r['generated_input'])}
        results={r['id']:r for r in report['compile_results']}
        if set(results)!=expected or len(results)!=len(report['compile_results']):raise ValueError('Full object attempt selection incomplete')
        old_processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in self.object_report['commands'] if Path(c['stdout']).name.startswith('compile-')}
        processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in report['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if len(processes)!=len(expected):raise ValueError('Full actual process inventory incomplete')
        old_roots={str(ROOT/'artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/mach-server-headers'),
            str(ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/mach-headers')}
        roots=[str(self.generated_root/'internal/osfmk'),str(self.generated_root/'export/osfmk')]
        objects=[];compiled=[];unresolved=[];inputs={};dependencies={};groups=Counter();headers=Counter()
        for identifier,result in results.items():
            row=original[identifier]
            process=processes[identifier.replace('/','-')]
            actual=process['argv']
            cwd=ROOT/self.object_report['configurations'][row['component']]['root']
            if str(cwd)!=process['cwd'] or process['exit_code']!=result['exit_code'] or process['timed_out'] or process['exit_code'] not in [0,1]:
                raise ValueError('Actual process/source context mismatch: '+identifier)
            if result['generated_source']:
                argv=shlex.split(row['original_expanded_recipe'])
                if (cwd/argv[-1]).resolve()!=(ROOT/row['source']).resolve():raise ValueError('Generated recipe source mismatch')
                name=(ROOT/row['source']).relative_to(KOBJECT/'configuration/osfmk/RELEASE')
                source=self.generated_root/'internal/osfmk'/name
                argv[-1]=str(source)
                argv += [a for p in self.object_report['additional_witnessed_include_roots'] for a in ['-I',p]]
            else:
                argv=old_processes[identifier.replace('/','-')]['argv'].copy()
                source=ROOT/row['source']
            if source!=ROOT/result['source'] or sha(source)!=result['source_sha256']:raise ValueError('Actual source bytes mismatch')
            argv[0]=str(COMPILER)
            for flag in ['-o','-MF']:
                value=actual[actual.index(flag)+1]
                if flag in argv:argv[argv.index(flag)+1]=value
                else:argv += [flag,value]
            filtered=[];at=0
            while at<len(argv):
                if argv[at]=='-I' and argv[at+1] in old_roots:at+=2;continue
                filtered.append(argv[at]);at+=1
            ordered=roots if row['component']=='osfmk' else list(reversed(roots))
            argv=[filtered[0],*[a for p in ordered for a in ['-I',p]],*filtered[1:]]
            if argv!=actual:raise ValueError('Full original recipe differs beyond declared changes: '+identifier)
            text=(ROOT/process['stderr']).read_text(errors='replace')
            if "conflicting types for 'mach_make_memory_entry'" in text:raise ValueError('Known conflicting declaration remains')
            if not result['actual_arm64_object']:
                missing=re.findall(r"fatal error: '([^']+)' file not found",text)
                category='missing_header' if missing else 'unsupported_metadata' if 'error: experimental XNU metadata does not support' in text else 'other_compile_error'
                groups[category]+=1;headers.update(missing)
                unresolved.append(dict(id=identifier,category=category,missing_headers=missing,errors=result['errors']))
                continue
            obj=ROOT/result['output']
            if process['exit_code']!=0 or sha(obj)!=result['output_sha256'] or macho(obj)['filetype']!=1:raise ValueError('Actual object changed')
            objects.append(obj)
            compiled.append({k:result[k] for k in ['id','source','source_sha256','output','output_sha256','generated_source','parent_status']})
            dep=Path(actual[actual.index('-MF')+1])
            line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(cwd/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            if source.resolve() not in files:raise ValueError('Dependency source association mismatch')
            names=[]
            for path in files:
                if any(path.is_relative_to(Path(old)) for old in old_roots):raise ValueError('Obsolete mixed-mode MIG header consumed')
                name=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
                if name not in inputs:inputs[name]=sha(path)
                names.append(name)
            dependencies[identifier]=dict(depfile=str(dep.relative_to(ROOT)),depfile_sha256=sha(dep),inputs=sorted(set(names)))
        for row in original.values():
            if row['id'] not in expected:unresolved.append(dict(id=row['id'],category='missing_source_or_recipe',source=row['source']))
        text=self.must([NDK/'llvm-readobj','--file-headers',*objects],'audit-llvm-headers',timeout=120)
        self.check('independent-arm64-headers',text.count('Format: Mach-O arm64')==len(objects),count=len(objects))
        text=self.must([NDK/'llvm-nm','--defined-only','--format=posix',*objects],'audit-llvm-symbols',timeout=120)
        counts=Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+',text))
        self.check('actual-code-symbols',counts['T']+counts['t']>0,defined_symbol_types=dict(counts))
        regressions=[r['id'] for r in results.values() if r['parent_status'] is True and not r['actual_arm64_object']]
        self.check('prior-object-regressions',not regressions,regressions=regressions)
        self.check('all-selected-generated-objects',all(r['actual_arm64_object'] for r in results.values() if r['generated_source']))
        self.check('complete-object-inventory',len(compiled)+len(unresolved)==len(original),selected=len(original),attempted=len(expected))
        self.report['coverage']=dict(selected=len(original),attempted=len(expected),actual_arm64=len(objects),unresolved=len(unresolved),
            generated_arm64=sum(r['generated_source'] for r in compiled),prior_successes=sum(r['parent_status'] is True for r in compiled),
            additional_objects=sum(r['parent_status'] is not True for r in compiled),prior_object_regressions=regressions,
            failure_categories=dict(groups),missing_headers=dict(headers),unique_dependency_files=len(inputs),defined_symbol_types=dict(counts))
        self.report['compilation_parent']=dict(experiment=self.args.compilation_evidence,report=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        for name,value in [('compiled-objects',compiled),('unresolved-objects',unresolved),('dependency-files',inputs),('object-dependencies',dependencies)]:
            dump(self.out/(name+'.json'),value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['inventory','generate','compile','contract','audit'],default='inventory')
    p.add_argument('--generation-evidence')
    p.add_argument('--compilation-evidence')
    p.add_argument('--selection',choices=['representatives','all'],default='representatives')
    p.add_argument('--jobs',type=int,default=2)
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Use fresh canonical run names')
    if not 1<=args.jobs<=3:p.error('Use1..3 host jobs')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    build=Mig(args)
    try:
        build.inputs()
        if args.mode in ['compile','contract','audit']:
            build.reuse_generation()
            if args.mode=='compile':build.compile_selected()
            elif args.mode=='contract':build.contract()
            else:build.audit_compilation()
        else:
            build.inventory()
            if args.mode=='generate':build.generate()
    except Exception as error:build.report['error']=str(error)
    return build.finish()

if __name__=='__main__':sys.exit(main())
