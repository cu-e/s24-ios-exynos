#!/usr/bin/env python3
"""Generate and qualify actual selected BSD syscall inputs, entirely on host."""
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

from xnu_kernel_mig import Mig,ROOT,KERNEL,KOBJECT,HOST,COMPILER
from xnu_compiler_hardening import registered,sha,dump,NDK
from xnu_macho_tools import macho


class ObjectData:
    """Bounded reader for real thin arm64 data and unsigned relocations."""
    def __init__(self,path):
        if macho(path)['filetype']!=1:raise ValueError('Expected actual arm64 object')
        self.data=path.read_bytes();self.sections=[];symtab=None;at=32
        for _ in range(struct.unpack_from('<I',self.data,16)[0]):
            cmd,length=struct.unpack_from('<II',self.data,at)
            if cmd==0x19:
                for i in range(struct.unpack_from('<I',self.data,at+64)[0]):
                    _,_,address,size,offset,_,reloc,nr,flags,_,_,_=struct.unpack_from('<16s16sQQ8I',self.data,at+72+i*80)
                    if offset>len(self.data) or size>len(self.data)-offset or reloc>len(self.data) or nr>(len(self.data)-reloc)//8:
                        raise ValueError('Invalid data/relocation extent')
                    self.sections.append(dict(address=address,size=size,offset=offset,reloc=reloc,nreloc=nr))
            if cmd==2:
                if symtab is not None:raise ValueError('Duplicate symbol table')
                symtab=struct.unpack_from('<4I',self.data,at+8)
            at+=length
        if symtab is None:raise ValueError('Missing symbol table')
        offset,count,strings,size=symtab
        if offset>len(self.data) or count>(len(self.data)-offset)//16 or strings>len(self.data) or size>len(self.data)-strings:
            raise ValueError('Invalid symbol/string extent')
        self.symbols=[];self.named={}
        for i in range(count):
            name,kind,section,_,value=struct.unpack_from('<IBBHQ',self.data,offset+i*16)
            end=self.data.find(b'\0',strings+name,strings+size) if name<size else -1
            if end<0:raise ValueError('Invalid symbol name')
            item=dict(name=self.data[strings+name:end].decode('ascii'),kind=kind,section=section,value=value)
            self.symbols.append(item)
            if kind&0x0e==0x0e:
                if not 1<=section<=len(self.sections):raise ValueError('Invalid defined symbol section')
                if item['name'] in self.named:raise ValueError('Duplicate defined symbol')
                self.named[item['name']]=item

    def location(self,name,length,delta=0):
        symbol=self.named[name];section=self.sections[symbol['section']-1]
        at=symbol['value']-section['address']+delta
        if at<0 or at>section['size'] or length>section['size']-at:raise ValueError('Symbol data exceeds section')
        return section,at,section['offset']+at

    def value(self,name,format,delta=0):
        _,_,at=self.location(name,struct.calcsize(format),delta)
        return struct.unpack_from(format,self.data,at)

    def relocation(self,name,delta):
        section,at,file_at=self.location(name,8,delta)
        found=[]
        for i in range(section['nreloc']):
            position=section['reloc']+8*i
            address,info=struct.unpack_from('<iI',self.data,position)
            if address==at:found.append((info,position+4))
        if len(found)!=1:raise ValueError('Expected one real pointer relocation')
        info,where=found[0]
        if info>>28 or (info>>24)&1 or (info>>25)&3!=3:raise ValueError('Expected unsigned absolute64 relocation')
        index=info&0xffffff
        if (info>>27)&1:
            if index>=len(self.symbols):raise ValueError('Invalid external relocation symbol')
            target=self.symbols[index]
            return dict(name=target['name'],section=target['section'],value=target['value'],
                addend=struct.unpack_from('<Q',self.data,file_at)[0],info=info,info_offset=where)
        if not 1<=index<=len(self.sections):raise ValueError('Invalid local relocation section')
        return dict(name=None,section=index,value=0,addend=struct.unpack_from('<Q',self.data,file_at)[0],info=info,info_offset=where)

    def string(self,name,delta):
        r=self.relocation(name,delta)
        if not 1<=r['section']<=len(self.sections):raise ValueError('String relocation lacks storage')
        section=self.sections[r['section']-1]
        at=r['value']+r['addend']-section['address']
        if at<0 or at>=section['size']:raise ValueError('String outside actual section')
        begin=section['offset']+at;end=self.data.find(b'\0',begin,section['offset']+section['size'])
        if end<0:raise ValueError('Unterminated actual string')
        return self.data[begin:end].decode('ascii')


class Syscalls(Mig):
    def __init__(self,args):
        self.args=args
        self.out=ROOT/'artifacts/xnu-kernel-syscalls'/args.run
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
        for name in ['KMIG-003','KMIG-007','KMIG-009','KMIG-010']:
            registered(name,self.ledger)
            e=next(e for e in self.ledger['experiments'] if e['id']==name)
            self.report['parents'][name]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.bsd_config=KOBJECT/'configuration/bsd/RELEASE/Makefile'
        self.report['config_defines']=dict(makefile=str(self.bsd_config.relative_to(ROOT)),sha256=sha(self.bsd_config),
            value=re.findall(r'^export CONFIG_DEFINES = (.*)$',self.bsd_config.read_text(),re.M)[0])
        self.script=KERNEL/'bsd/kern/makesyscalls.sh'
        self.master=KERNEL/'bsd/kern/syscalls.master'
        self.report['generator_inputs']={str(p.relative_to(ROOT)):sha(p) for p in [self.script,self.master,self.bsd_config,KERNEL/'bsd/sys/Makefile',KERNEL/'makedefs/MakeInc.rule']}
        self.report['generator_tools']={str(Path(shutil.which(p)).resolve()):sha(Path(shutil.which(p))) for p in ['sh','sed','awk','cat','rm','touch']}
        self.report['unifdef_sha256']=sha(HOST/'unifdef')

    def make_args(self,directory):
        argv=super().make_args(directory)
        argv=[a for a in argv if not a.startswith(('TARGET=','CONFIG_DEFINES='))]
        found=re.findall(r'^export CONFIG_DEFINES = (.*)$',self.bsd_config.read_text(),re.M)
        if len(found)!=1:raise ValueError('Selected BSD CONFIG_DEFINES missing')
        return [*argv,'TARGET='+str(self.out/'generated/bsd'),'UNIFDEF='+str(HOST/'unifdef'),'CONFIG_DEFINES='+found[0]]

    def query_syscalls(self,makefile,directory,label,goals):
        cwd=self.out/'query-build'/label;cwd.mkdir(parents=True,exist_ok=True)
        query=self.out/('query-'+label+'.mk')
        keys=['MAKESYSCALLS','SEED_DEFINES','UNIFDEF','TARGET','CONFIG_DEFINES','EXPORT_MI_GEN_LIST']
        query.write_text('include '+str(makefile)+'\n'+'\n'.join('$(info S24_SYSC|'+k+'|$('+k+'))' for k in keys)+'\n.PHONY: s24_query\ns24_query: ;\n')
        argv=['make','--no-print-directory','-rR','-f',str(query),*self.make_args(directory)]
        text=self.must([*argv,'s24_query'],'query-'+label,cwd=cwd)
        values={a[1]:a[2] for line in text.splitlines() if line.startswith('S24_SYSC|') and len(a:=line.split('|',2))==3}
        if set(values)!=set(keys):raise ValueError('Incomplete actual variable query')
        recipes={}
        for goal in goals:
            text=self.must([*argv,'-n',goal],'recipe-'+label+'-'+Path(goal).name,cwd=cwd)
            recipes[goal]=text
        return values,recipes

    def generate_syscalls(self):
        generated=self.out/'generated/bsd';(generated/'sys').mkdir(parents=True)
        master=generated/'bsd.syscalls.master'
        values,recipes=self.query_syscalls(self.bsd_config,KERNEL/'bsd','bsd',[str(master)])
        if Path(values['MAKESYSCALLS'])!=self.script or Path(values['UNIFDEF'])!=HOST/'unifdef':raise ValueError('Unexpected selected generator')
        self.report['master_rule']=dict(variables=values,expanded_recipe=recipes[str(master)])
        code,_,stderr=self.run([HOST/'unifdef',*shlex.split(values['SEED_DEFINES']),self.master],'select-master')
        self.check('select-master',code in [0,1],exit_code=code,diagnostic=stderr[-1200:])
        if code not in [0,1]:raise ValueError('Genuine master selection failed')
        shutil.copyfile(self.out/'select-master.stdout.txt',master)
        source_values,source_recipes=self.query_syscalls(self.bsd_config,KERNEL/'bsd','sources',['init_sysent.c','syscalls.c'])
        header_values,header_recipes=self.query_syscalls(KERNEL/'bsd/sys/Makefile',KERNEL/'bsd/sys','headers',['syscall.h','sysproto.h'])
        self.report['actual_generation_rules']=dict(sources=source_recipes,headers=header_recipes)
        self.report['selected_master']=dict(path=str(master.relative_to(ROOT)),sha256=sha(master),
            source_sha256=sha(self.master),seed_defines=values['SEED_DEFINES'],conditionals_preserved='#if' in master.read_text())
        self.report['generated_files']={}
        for output,kind,directory,rule in [
            ('init_sysent.c','table',generated,source_recipes['init_sysent.c']),
            ('syscalls.c','names',generated,source_recipes['syscalls.c']),
            ('syscall.h','header',generated/'sys',header_recipes['syscall.h']),
            ('sysproto.h','proto',generated/'sys',header_recipes['sysproto.h'])]:
            lines=rule.replace('\\\n',' ').splitlines()
            invocations=[shlex.split(line) for line in lines if line.startswith(str(self.script)+' ')]
            if len(invocations)!=1 or invocations[0]!=[str(self.script),str(master),kind,'>','/dev/null']:
                raise ValueError('Actual generator invocation differs from selected rule')
            code,_,stderr=self.run(['env','TARGET='+str(generated),'/bin/sh',*invocations[0][:-2]],'generate-'+output,cwd=directory)
            path=directory/output
            self.check('generate-'+output,code==0 and path.is_file() and path.stat().st_size>0,exit_code=code,diagnostic=stderr[-1800:])
            if code==0 and path.is_file():self.report['generated_files'][str(path.relative_to(self.out))]=sha(path)
        selected=[r for r in self.object_report['inventory'] if r['component']=='bsd' and r['status']=='missing_source_or_recipe']
        self.check('selected-generated-source-mapping',{r['target'] for r in selected}=={'init_sysent.o','syscalls.o'} and
            all((generated/Path(r['source']).name).is_file() for r in selected))
        self.report['generated_prefix']=str(generated.relative_to(ROOT))
        self.report['existing_bsd_generated_inputs']=[{k:r[k] for k in ['id','source','source_sha256','status']}
            for r in self.object_report['inventory'] if r['component']=='bsd' and r['generated_input'] and r['status']!='missing_source_or_recipe']

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Genuine selected BSD syscall generator/type/table/object assessment; full kernel/Apple private ABI/native support remains unqualified'
        dump(self.out/'report.json',self.report)
        files=[p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json']
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:16],commands_scope='Representative exact commands; every execution retained in hashed report.json',
            actual_command_count=len(self.report['commands']),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),compile_counts=self.report.get('compile_counts'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1

    def reuse_syscalls(self):
        if not self.args.syscalls_evidence:raise ValueError('Supply recorded syscall generation evidence')
        doc=registered(self.args.syscalls_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one syscall generation report')
        previous=json.loads(paths[0].read_text())
        if previous['outcome']!='pass':raise ValueError('Require passing genuine generation')
        self.syscalls_root=ROOT/previous['generated_prefix']
        for path,h in previous['generated_files'].items():
            if sha(paths[0].parent/path)!=h:raise ValueError('Generated syscall file changed')
        self.report['syscalls_parent']=dict(experiment=self.args.syscalls_evidence,path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))

    def parent_profile(self):
        path=ROOT/'artifacts/xnu-kernel-mig/full-profile-session1/report.json'
        parent=json.loads(path.read_text())
        self.previous={r['id']:r for r in parent['compile_results']}
        self.previous_processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in parent['commands'] if Path(c['stdout']).name.startswith('compile-')}
        self.report['original_recipe_parent']=dict(evidence='KMIG-007',path=str(path.relative_to(ROOT)),sha256=sha(path))

    def source_for(self,row):
        if row['id'] in self.previous:return ROOT/self.previous[row['id']]['source']
        if row['id'] in ['bsd/init_sysent.o','bsd/syscalls.o']:return self.syscalls_root/Path(row['source']).name
        return None

    def object_command(self,row,source,output):
        cwd=ROOT/self.object_report['configurations'][row['component']]['root']
        if row['id'] in self.previous:
            process=self.previous_processes[row['id'].replace('/','-')]
            if process['cwd']!=str(cwd) or sha(source)!=self.previous[row['id']]['source_sha256']:
                raise ValueError('Recorded parent source/context changed')
            argv=process['argv'].copy()
        else:
            argv=shlex.split(row['original_expanded_recipe'])
            if (cwd/argv[-1]).resolve()!=(ROOT/row['source']).resolve():raise ValueError('Original generated source rule differs')
            argv[-1]=str(source);argv[0]=str(COMPILER)
            extra=self.object_report['additional_witnessed_include_roots']
            old={str(ROOT/'artifacts/xnu-iig-abi/nyktis-invoke-guard-session1/mach-server-headers'),
                str(ROOT/'artifacts/open-kernel-inputs/typed-pthread-session1/mach-headers')}
            roots=[self.generated_root/'export/osfmk',self.generated_root/'internal/osfmk']
            argv=[argv[0],*[a for p in roots for a in ['-I',str(p)]],*argv[1:],
                *[a for p in extra if p not in old for a in ['-I',p]]]
        if Path(argv[0])!=COMPILER:raise ValueError('Exact candidate compiler changed')
        for flag,value in [('-o',output),('-MF',output.with_suffix('.d'))]:
            if flag in argv:argv[argv.index(flag)+1]=str(value)
            else:argv += [flag,str(value)]
        argv=[argv[0],'-I',str(self.syscalls_root),*argv[1:]]
        if '-DXNU_NO_TYPE_BUILTINS=0' not in argv or '-w' in argv or any('xnu_clang_compat.h' in a for a in argv):
            raise ValueError('Real allocator checking profile lost')
        return argv,cwd

    def compile_syscalls(self):
        self.parent_profile()
        representatives={'bsd/init_sysent.o','bsd/syscalls.o','bsd/kern_descrip.o','bsd/kern_exec.o',
            'bsd/vfs_syscalls.o','osfmk/bsd_arm64.o','bsd/audit_syscalls.o'}
        rows=[(r,self.source_for(r)) for r in self.object_report['inventory'] if self.source_for(r)]
        if self.args.selection=='representatives':
            rows=[(r,s) for r,s in rows if r['id'] in representatives]
            if {r['id'] for r,s in rows}!=representatives:raise ValueError('Representative inventory incomplete')
        self.report['compile_selection']=self.args.selection
        self.report['compile_results']=[]
        def one(item):
            row,source=item
            directory=self.out/'objects'/row['component'];directory.mkdir(parents=True,exist_ok=True)
            output=directory/row['target']
            argv,cwd=self.object_command(row,source,output)
            code,_,stderr=self.run(argv,'compile-'+row['id'].replace('/','-'),cwd=cwd,timeout=120)
            good=code==0 and output.is_file() and macho(output)['filetype']==1
            return dict(id=row['id'],source=str(source.relative_to(ROOT)),source_sha256=sha(source),
                syscall_generated=row['id'] in ['bsd/init_sysent.o','bsd/syscalls.o'],
                parent_status=self.previous.get(row['id'],{}).get('actual_arm64_object'),exit_code=code,
                actual_arm64_object=good,output=str(output.relative_to(ROOT)) if good else None,
                output_sha256=sha(output) if good else None,missing_headers=re.findall(r"fatal error: '([^']+)' file not found",stderr),
                errors=re.findall(r'(?m)^.*(?:fatal error:|error:).*$',stderr)[:12],diagnostic=stderr[-2500:])
        with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
            for index,result in enumerate(pool.map(one,rows),1):
                self.report['compile_results'].append(result)
                if index%40==0:dump(self.out/'progress.json',dict(completed=index,total=len(rows),actual_arm64=sum(r['actual_arm64_object'] for r in self.report['compile_results'])))
        results=self.report['compile_results']
        regressions=[r['id'] for r in results if r['parent_status'] is True and not r['actual_arm64_object']]
        self.report['compile_counts']=dict(attempted=len(results),actual_arm64=sum(r['actual_arm64_object'] for r in results),
            syscall_generated_arm64=sum(r['syscall_generated'] and r['actual_arm64_object'] for r in results),prior_object_regressions=regressions)
        self.check('no-crashes-timeouts',all(c['exit_code'] in [0,1] and not c['timed_out'] for c in self.report['commands']))
        self.check('prior-object-regressions',not regressions,regressions=regressions)
        selected=[r for r in results if r['id'] in representatives]
        self.check('genuine-representatives',len(selected)==len(representatives) and all(r['actual_arm64_object'] for r in selected),
            statuses={r['id']:r['actual_arm64_object'] for r in selected})
        dump(self.out/'compile-results.json',results)

    def syscall_contract(self):
        self.parent_profile()
        row=next(r for r in self.object_report['inventory'] if r['id']=='bsd/kern_exec.o')
        source=self.out/'layout-contract.c'
        shutil.copyfile(ROOT/'fixtures/public/xnu-kernel-syscalls/layout-contract.c',source)
        argv,cwd=self.object_command(row,self.source_for(row),self.out/'layout.o')
        argv[argv.index(str(self.source_for(row)))]=str(source)
        for label,extra,expected in [('layout',[],0),('wrong-layout',['-DS24_WRONG_LAYOUT=1'],1)]:
            command=[*argv,*extra]
            command[command.index('-o')+1]=str(self.out/(label+'.o'))
            command[command.index('-MF')+1]=str(self.out/(label+'.d'))
            code,_,stderr=self.run(command,label,cwd=cwd,timeout=120)
            self.check(label,code==expected and (expected==0 or 'deliberately wrong argument layout' in stderr),exit_code=code,diagnostic=stderr[-2200:])
        if not (self.out/'layout.o').is_file():raise ValueError('Real target layout fixture failed')
        layout=ObjectData(self.out/'layout.o').value('_s24_syscall_layout','<6Q')
        self.check('actual-layout-bytes',layout==(24,16,20,22,24,556),observed=list(layout))
        registered('KSYSC-003',self.ledger)
        prefix=ROOT/'artifacts/xnu-kernel-syscalls/representatives-session1/objects/bsd'
        table=ObjectData(prefix/'init_sysent.o');names=ObjectData(prefix/'syscalls.o')
        def assess(table,names):
            if table.value('_nsysent','<I')[0]!=layout[5]:raise ValueError('Actual dispatch count differs from header')
            table.location('_sysent',layout[0]*layout[5]);names.location('_syscallnames',8*layout[5])
            expected=[(3,'_read','read',6,3,12),(4,'_write','write',6,3,12),(5,'_open','open',1,3,12),(6,'_sys_close','close',1,1,4)]
            observed=[]
            for number,target,text,ret,nargs,nbytes in expected:
                reloc=table.relocation('_sysent',number*layout[0])
                values=table.value('_sysent','<ihH',number*layout[0]+layout[1])
                actual=names.string('_syscallnames',8*number)
                if reloc['name']!=target or reloc['addend'] or values!=(ret,nargs,nbytes) or actual!=text:
                    raise ValueError('Actual selected dispatch/name/argument contract differs')
                observed.append(dict(number=number,target=reloc['name'],name=actual,return_type=values[0],argument_slots=values[1],argument_bytes32=values[2]))
            return observed
        observed=assess(table,names)
        self.check('actual-generated-table-and-names',True,dispatch_count=layout[5],entries=observed)
        changed=bytearray(table.data)
        _,_,position=table.location('_nsysent',4);struct.pack_into('<I',changed,position,555)
        path=self.out/'changed-count.o';path.write_bytes(changed)
        try:assess(ObjectData(path),names)
        except ValueError:self.check('actual-count-mutation-rejected',True)
        else:raise ValueError('Count mutation accepted')
        changed=bytearray(table.data)
        first=table.relocation('_sysent',3*layout[0]);second=table.relocation('_sysent',5*layout[0])
        if first['info']&0xffffff==second['info']&0xffffff:raise ValueError('Expected distinct actual handler symbols')
        struct.pack_into('<I',changed,first['info_offset'],(first['info']&0xff000000)|(second['info']&0xffffff))
        path=self.out/'changed-handler.o';path.write_bytes(changed)
        try:assess(ObjectData(path),names)
        except ValueError:self.check('actual-handler-relocation-mutation-rejected',True)
        else:raise ValueError('Handler mutation accepted')
        master=self.master.read_text()
        gap,count=re.subn(r'(?m)^0(\s+AUE_NULL)',r'7\1',master,count=1)
        syntax,n=re.subn(r'\{ int nosys\(void\); \}','{ int nosys(void) }',master,count=1)
        if count!=1 or n!=1:raise ValueError('Actual malformed-source anchors changed')
        for label,text,expected in [('number-gap',gap,'out of sync'),('missing-semicolon',syntax,'unexpected')]:
            directory=self.out/label;directory.mkdir()
            path=directory/'syscalls.master';path.write_text(text)
            code,stdout,stderr=self.run(['/bin/sh',self.script,path,'table'],label,cwd=directory)
            self.check(label,code==1 and expected in stdout+stderr,exit_code=code,partial_outputs_not_qualified=True,diagnostic=(stdout+stderr)[-1800:])
        path=self.out/'unterminated.master';path.write_text(master+'\n#if S24_UNTERMINATED\n')
        code,_,stderr=self.run([HOST/'unifdef','-DXNU_NO_TYPE_BUILTINS=0',path],'unterminated-master')
        self.check('unifdef-parse-failure',code==2 and 'Premature EOF' in stderr,exit_code=code,diagnostic=stderr[-1800:])

    def audit_syscalls(self):
        if not self.args.compilation_evidence:raise ValueError('Supply full compilation evidence')
        doc=registered(self.args.compilation_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if len(paths)!=1:raise ValueError('Expected one compilation report')
        parent=json.loads(paths[0].read_text())
        if parent['compile_selection']!='all':raise ValueError('Require full available-source selection')
        self.parent_profile()
        original={r['id']:r for r in self.object_report['inventory']}
        expected={r['id'] for r in original.values() if self.source_for(r)}
        results={r['id']:r for r in parent['compile_results']}
        processes={Path(c['stdout']).name.removeprefix('compile-').removesuffix('.stdout.txt'):c
            for c in parent['commands'] if Path(c['stdout']).name.startswith('compile-')}
        if set(results)!=expected or len(results)!=len(parent['compile_results']) or len(processes)!=len(expected):
            raise ValueError('Actual full source/process selection incomplete')
        objects=[];compiled=[];unresolved=[];inputs={};dependencies={};groups=Counter();headers=Counter()
        for identifier,result in results.items():
            row=original[identifier];source=self.source_for(row)
            process=processes[identifier.replace('/','-')]
            output=Path(process['argv'][process['argv'].index('-o')+1])
            argv,cwd=self.object_command(row,source,output)
            if argv!=process['argv'] or str(cwd)!=process['cwd'] or str(source.relative_to(ROOT))!=result['source'] or sha(source)!=result['source_sha256']:
                raise ValueError('Recorded recipe/source differs from permitted original transformations')
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
                raise ValueError('Actual ARM64 object changed')
            objects.append(output)
            compiled.append({k:result[k] for k in ['id','source','source_sha256','output','output_sha256','parent_status','syscall_generated']})
            dep=Path(argv[argv.index('-MF')+1]);line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(cwd/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            if source.resolve() not in files:raise ValueError('Actual dependency source mismatch')
            names=[]
            for path in files:
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
        self.check('generated-syscall-objects',sum(r['syscall_generated'] for r in compiled)==2)
        self.check('complete-object-inventory',len(compiled)+len(unresolved)==len(original),selected=len(original),attempted=len(expected))
        self.report['coverage']=dict(selected=len(original),attempted=len(expected),actual_arm64=len(objects),unresolved=len(unresolved),
            generated_syscall_arm64=sum(r['syscall_generated'] for r in compiled),prior_successes=sum(r['parent_status'] is True for r in compiled),
            additional_objects=sum(r['parent_status'] is not True for r in compiled),prior_object_regressions=regressions,
            failure_categories=dict(groups),missing_headers=dict(headers),unique_dependency_files=len(inputs),defined_symbol_types=dict(counts))
        self.report['compilation_parent']=dict(experiment=self.args.compilation_evidence,path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))
        for name,value in [('compiled-objects',compiled),('unresolved-objects',unresolved),('dependency-files',inputs),('object-dependencies',dependencies)]:
            dump(self.out/(name+'.json'),value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['generate','compile','contract','audit'],default='generate')
    p.add_argument('--generation-evidence',default='KMIG-003')
    p.add_argument('--syscalls-evidence')
    p.add_argument('--compilation-evidence')
    p.add_argument('--selection',choices=['representatives','all'],default='representatives')
    p.add_argument('--jobs',type=int,default=2)
    args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run) or not 1<=args.jobs<=3:p.error('Use fresh canonical run and1..3 jobs')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    build=Syscalls(args)
    try:
        build.inputs()
        if args.mode=='generate':build.generate_syscalls()
        else:
            build.reuse_generation();build.reuse_syscalls()
            if args.mode=='compile':build.compile_syscalls()
            elif args.mode=='contract':build.syscall_contract()
            else:build.audit_syscalls()
    except Exception as error:build.report['error']=str(error)
    return build.finish()

if __name__=='__main__':sys.exit(main())
