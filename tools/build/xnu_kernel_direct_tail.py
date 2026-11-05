#!/usr/bin/env python3
"""Qualify genuine selected XNU top-level objects and LAST section processing."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import re
import resource
import shlex
import shutil
import struct
import subprocess
import sys
from xnu_compiler_cxx_storage import Storage
from xnu_kernel_firehose_headers import COMPILER as VECTOR_COMPILER
from xnu_compiler_atomics import ROOT, KERNEL, NDK, registered, sha, dump
from xnu_macho_tools import macho
from xnu_kernel_syscalls import ObjectData

FIXTURES=ROOT/'fixtures/public/xnu-kernel-direct-tail'
PATCHES=ROOT/'patches/kernel-direct-tail'
CURRENT=ROOT/'artifacts/xnu-compiler-cxx-storage/full-profile-session2'
PUBLIC=ROOT/'references/apple-xnu'
CCTOOLS=ROOT/'references/xnu-cctools'
REVISION='c54f35ca767986246321eb901baf8f5ff7923f6a'
TAIL=['nonlto.o','lastkerneldataconst.o','lastkernelconstructor.o']


def thin(path):
    """Independently bound the selected little-endian thin ARM64 representation."""
    data=Path(path).read_bytes()
    if len(data)<32:raise ValueError('Truncated Mach-O header')
    magic,cpu,subtype,kind,ncmds,cmdbytes,flags,reserved=struct.unpack_from('<8I',data)
    if magic!=0xfeedfacf or cpu!=0x100000c or kind not in {1,2,6}:
        raise ValueError('Selected thin ARM64 object/image required')
    if cmdbytes>len(data)-32 or ncmds>cmdbytes//8:raise ValueError('Load command extent')
    at=32;end=32+cmdbytes;sections=[];segments=[];symtab=None
    for _ in range(ncmds):
        if at+8>end:raise ValueError('Load command header extent')
        cmd,length=struct.unpack_from('<II',data,at)
        if length<8 or length%8 or length>end-at:raise ValueError('Load command size')
        if cmd==0x19:
            if length<72:raise ValueError('Segment header extent')
            segment=data[at+8:at+24].split(b'\0')[0].decode('ascii')
            vmaddr,vmsize,fileoff,filesize=struct.unpack_from('<4Q',data,at+24)
            count=struct.unpack_from('<I',data,at+64)[0]
            if count>(length-72)//80 or fileoff>len(data) or filesize>len(data)-fileoff:
                raise ValueError('Segment/section extent')
            segments.append(dict(name=segment,address=vmaddr,size=vmsize,fileoff=fileoff,filesize=filesize))
            for i in range(count):
                pos=at+72+80*i
                name,seg,address,size,offset,align,reloc,nr,attrs,r1,r2,r3=struct.unpack_from('<16s16sQQ8I',data,pos)
                zero=attrs&0xff in {1,0xc,0x12}
                if align>63 or (not zero and (offset>len(data) or size>len(data)-offset)) or reloc>len(data) or nr>(len(data)-reloc)//8:
                    raise ValueError('Section data/relocation extent')
                for j in range(nr):
                    address_r,info=struct.unpack_from('<iI',data,reloc+8*j)
                    if address_r<0 or address_r>=size:raise ValueError('Selected relocation address extent')
                sections.append(dict(name=name.split(b'\0')[0].decode('ascii'),segment=seg.split(b'\0')[0].decode('ascii'),
                    address=address,size=size,offset=offset,align=align,reloc=reloc,nreloc=nr,flags=attrs,
                    segment_name_offset=pos+16,zerofill=zero))
        if cmd==2:
            if length!=24 or symtab is not None:raise ValueError('Symbol command extent')
            symtab=struct.unpack_from('<4I',data,at+8)
        at+=length
    if at!=end or symtab is None:raise ValueError('Complete commands/symbol table required')
    offset,count,strings,ssize=symtab
    if offset>len(data) or count>(len(data)-offset)//16 or strings>len(data) or ssize>len(data)-strings:
        raise ValueError('Symbol/string extent')
    symbols=[]
    for i in range(count):
        name,typ,sect,desc,value=struct.unpack_from('<IBBHQ',data,offset+16*i)
        finish=data.find(b'\0',strings+name,strings+ssize) if name<ssize else -1
        if finish<0 or sect>len(sections):raise ValueError('Symbol name/section extent')
        symbols.append(dict(name=data[strings+name:finish].decode('ascii'),type=typ,section=sect,value=value))
    return dict(filetype=kind,sections=sections,segments=segments,symbols=symbols)


def expected_rename(source,old='__DATA',new='__LASTDATA_CONST',ignore=None):
    view=thin(source);data=bytearray(Path(source).read_bytes());changed=[]
    encoded=new.encode('ascii')[:16].ljust(16,b'\0')
    for s in view['sections']:
        if s['flags']&0x02000000 or s['segment']==ignore:continue
        if old is None or s['segment']==old:
            at=s['segment_name_offset'];data[at:at+16]=encoded;changed.append(s['name'])
    return bytes(data),changed


class Tail(Storage):
    def __init__(self,args):
        self.args=args;self.out=ROOT/'artifacts/xnu-kernel-direct-tail'/args.run
        if self.out.resolve()!=self.out:raise ValueError('Canonical fresh run required')
        self.out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,self.out/'builder.py')
        self.ledger=json.loads((ROOT/'state/lab.json').read_text());self.ports={}
        self.report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
            mode=args.mode,commands=[],checks=[],kernel_cases=[],device_executed=False,sdk_used=False,global_install=False,
            full_kernel_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,native_device_qualified=False)

    def inputs(self):
        super().inputs();self.reuse_storage()
        for identifier in ['CXXST-006','CXXST-008','CXXST-009','CXXST-010','CXXST-011','MACHOTOOLS-004']:
            registered(identifier,self.ledger)
            e=next(e for e in self.ledger['experiments'] if e['id']==identifier)
            self.report['parents'][identifier]=dict(path=e['evidence'],sha256=e['evidence_sha256'])
        self.profile=json.loads((CURRENT/'report.json').read_text())
        self.version=next(c for c in self.profile['commands'] if c['stdout'].endswith('/compile-kernel-version.o.stdout.txt'))
        self.cwd=Path(self.version['cwd'])
        old=json.loads((ROOT/'artifacts/xnu-kernel-setup/full-profile-session2/report.json').read_text())
        self.query_parent=next(c for c in old['commands'] if c['stdout'].endswith('/query-version.stdout.txt'))
        names=['libsa/'+n.replace('.o','.c') for n in TAIL]+['SETUP/setsegname/setsegname.c','SETUP/setsegname/Makefile',
            'Makefile','makedefs/MakeInc.kernel','makedefs/MakeInc.rule','makedefs/MakeInc.def','makedefs/MakeInc.cmd','APPLE_LICENSE']
        self.report['tail_source_inputs']={};self.report['public_source_comparison']={}
        for i,n in enumerate(names):
            self.must(['git','-C',PUBLIC,'show',REVISION+':'+n],'tail-public-blob-'+str(i))
            public=self.out/('tail-public-blob-'+str(i)+'.stdout.txt')
            same=sha(public)==sha(KERNEL/n)
            self.report['public_source_comparison'][n]=dict(public_sha256=sha(public),selected_sha256=sha(KERNEL/n),equal=same)
            if not same:
                if n not in {'Makefile','makedefs/MakeInc.def','makedefs/MakeInc.rule','makedefs/MakeInc.cmd'}:
                    raise ValueError('Unreviewed target source/rule delta: '+n)
                delta=self.out/('public-to-selected-'+n.replace('/','-')+'.diff')
                delta.write_text(''.join(difflib.unified_diff(public.read_text().splitlines(True),(KERNEL/n).read_text().splitlines(True),fromfile='public/'+n,tofile='prepared/'+n)))
                self.report['public_source_comparison'][n].update(delta=str(delta.relative_to(ROOT)),delta_sha256=sha(delta),
                    prepared_tree_witness=self.report['prepared_source_witness_sha256'])
            self.report['tail_source_inputs'][str((KERNEL/n).relative_to(ROOT))]=sha(KERNEL/n)
        if self.must(['git','-C',CCTOOLS,'rev-parse','HEAD'],'cctools-revision').strip()!='904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb':raise ValueError('Pinned public cctools headers required')
        for p in FIXTURES.glob('*.c'):shutil.copyfile(p,self.out/'fixture-inputs'/p.name)
        self.report['fixture_files_sha256']={p.name:sha(p) for p in (self.out/'fixture-inputs').iterdir()}
        self.report['research_access']=dict(reddit=dict(subreddit='hackios',query='Exynos',limit=5,
            result='Arctic Shift timeout; inconclusive, no absence claim'),primary_urls=[
            'https://github.com/apple-oss-distributions/xnu/blob/'+REVISION+'/SETUP/setsegname/setsegname.c',
            'https://github.com/apple-oss-distributions/xnu/blob/'+REVISION+'/makedefs/MakeInc.kernel'])

    def query(self,variant='selected'):
        text=(KERNEL/'makedefs/MakeInc.kernel').read_text();lines=text.splitlines()
        remove=next(l for l in lines if l.startswith('lastkernelconstructor.o_CFLAGS_RM ='))
        if remove!='lastkernelconstructor.o_CFLAGS_RM = -fprofile-instr-generate':raise ValueError('Constructor profile policy changed')
        instructions={}
        for name in [*TAIL,'version.o']:
            expression='$(OBJPATH)/version.c' if name=='version.o' else '$(SRCROOT)/libsa/'+name.replace('.o','.c')
            part=text.split(name+': '+expression,1) if name!='nonlto.o' else text.split(name+':   '+expression,1)
            if len(part)!=2:raise ValueError('Exact genuine direct-source rule required: '+name)
            code=part[1].splitlines()[2].strip()
            expected='${C_RULE_1A}$<'+(' $(CFLAGS_NOLTO_FLAG)' if name in {'nonlto.o','lastkernelconstructor.o'} else '')
            if code!=expected:raise ValueError('Genuine compile recipe changed: '+name)
            instructions[name]=code
        q=self.out/('query-'+variant+'.mk')
        out=['include '+str(KERNEL/'makedefs/MakeInc.def'),'include '+str(KERNEL/'makedefs/MakeInc.rule'),remove]
        if variant=='lto-profile':out+=['CFLAGS += -fprofile-instr-generate']
        for name,code in instructions.items():
            source=next(r['source'] for r in self.profile['compile_results'] if r['id']=='kernel/version.o') if name=='version.o' else str((KERNEL/'libsa'/name.replace('.o','.c')).relative_to(ROOT))
            out+=['$(eval @ := '+name+')','$(eval < := '+str(ROOT/source)+')',
                '$(info S24_TAIL|'+name+'|COMPILE|'+code+')']
        for key in ['CFLAGS_NOLTO_FLAG','C_RULE_3','C_RULE_4','C_RULE_2']:
            out+=['$(info S24_TAIL|GLOBAL|'+key+'|$('+key+'))']
        out+=['.PHONY: s24_query','s24_query: ;'];q.write_text('\n'.join(out)+'\n')
        old=self.query_parent['argv'];argv=old[:];argv[argv.index('-f')+1]=str(q)
        argv=[('CC='+str(self.compiler) if a.startswith('CC=') else 'CXX='+str(self.compiler) if a.startswith('CXX=') else 'MIGCC='+str(self.compiler) if a.startswith('MIGCC=') else a) for a in argv]
        if variant=='lto-profile':argv=[a if a!='BUILD_LTO=0' else 'BUILD_LTO=1' for a in argv]
        stdout=self.must(argv,'query-'+variant,cwd=Path(self.query_parent['cwd']))
        rows={}
        for line in stdout.splitlines():
            if line.startswith('S24_TAIL|'):
                _,obj,key,value=line.split('|',3);rows.setdefault(obj,{})[key]=value
        if set(rows)!={*TAIL,'version.o','GLOBAL'} or any(rows['GLOBAL'][n] for n in ['C_RULE_2','C_RULE_3','C_RULE_4']):raise ValueError('Unsupported direct-rule postprocessor')
        if variant=='selected':
            argv=shlex.split(rows['version.o']['COMPILE'])
            # Match the previously qualified version recipe before its two
            # later genuine setup/firehose include roots and output bindings.
            current=self.version['argv'].copy()
            # Prefix include roots are explicit, unchanged qualified additions.
            prefix=['-I',str(ROOT/self.report['header_export']['root']),'-I',str(ROOT/'artifacts/xnu-kernel-setup/generate-session1/generated/include')]
            if current[1:5]!=prefix:raise ValueError('Current version header binding changed')
            current=current[:1]+current[5:]
            current=current[:current.index('-o')]
            current[current.index('-MF')+1]='version.d'
            if argv!=current:raise ValueError('Expanded current top-level profile differs from qualified version recipe')
        self.report.setdefault('expanded_rules',{})[variant]=rows
        return rows

    def build_tool(self):
        source=self.out/'setsegname.c';shutil.copyfile(KERNEL/'SETUP/setsegname/setsegname.c',source)
        compat=self.out/'host-compat.h';shutil.copyfile(PATCHES/'host-compat.h',compat)
        self.tool=self.out/'setsegname';include=CCTOOLS/'cctools/include'
        self.must([NDK/'clang','-std=gnu11','-D_GNU_SOURCE','-Wall','-Wextra','-g','-O1',
            '-I',include,'-idirafter',include/'foreign','-include',compat,'-MD','-MF',self.out/'setsegname.d',source,'-o',self.tool],
            'build-genuine-setsegname',timeout=120)
        self.report['setsegname']=dict(tool=str(self.tool.relative_to(ROOT)),sha256=sha(self.tool),
            source=str(source.relative_to(ROOT)),source_sha256=sha(source),original_sha256=sha(KERNEL/'SETUP/setsegname/setsegname.c'),
            compatibility_header=str(compat.relative_to(ROOT)),compatibility_header_sha256=sha(compat))
        self.check('unchanged-genuine-setsegname-source',sha(source)==sha(KERNEL/'SETUP/setsegname/setsegname.c'))

    def compile_tail(self):
        rows=self.query();self.report['compile_results']=[]
        for name in TAIL:
            argv=shlex.split(rows[name]['COMPILE']);obj=self.out/'objects/kernel'/name;obj.parent.mkdir(parents=True,exist_ok=True)
            argv[argv.index('-MF')+1]=str(obj.with_suffix('.d'))
            argv=[argv[0],*self.version['argv'][1:5],*argv[1:],'-o',str(obj)]
            self.must(argv,'compile-'+name,cwd=self.cwd,timeout=120)
            self.check('genuine-arm64-'+name,macho(obj)['filetype']==1)
            self.report['compile_results'].append(dict(id='kernel/'+name,source=str((KERNEL/'libsa'/name.replace('.o','.c')).relative_to(ROOT)),
                source_sha256=sha(KERNEL/'libsa'/name.replace('.o','.c')),output=str(obj.relative_to(ROOT)),output_sha256=sha(obj),actual_arm64_object=True))
        self.report['selected_profile']=dict(build_lto=0,type_checks_enabled=True,compiler_sha256=sha(self.compiler),source_patch=False)

    def postprocess(self):
        row=next(r for r in self.report['compile_results'] if r['id']=='kernel/lastkernelconstructor.o')
        obj=ROOT/row['output'];raw=self.out/'raw/lastkernelconstructor.o';raw.parent.mkdir()
        shutil.copyfile(obj,raw);expected,names=expected_rename(raw)
        if names!=['__mod_init_func']:raise ValueError('Actual constructor section policy changed')
        text=(KERNEL/'makedefs/MakeInc.kernel').read_text()
        first=text.index('\t$(_v)for last_file in ${LAST_FILES};')
        recipe=text[first:text.index('\nEXTRA_KC_LINKARGS',first)]
        rename=next(l for l in text.splitlines() if l.startswith('EXTRA_KC_LINKARGS ='))
        if rename!='EXTRA_KC_LINKARGS = -Wl,-rename_segment,__LASTDATA_CONST,__LAST':raise ValueError('Actual final rename policy changed')
        script=self.out/'genuine-postprocess.mk'
        script.write_text('SHELL := /bin/bash\n.SHELLFLAGS := -x -c\nSEG_HACK := '+str(self.tool)+'\nLAST_FILES := '+str(obj)+'\n.PHONY: post\npost:\n'+recipe+'\n')
        self.must(['make','--no-print-directory','-rR','-f',script,'post'],'genuine-last-postprocess',cwd=self.out)
        trace=(self.out/'genuine-last-postprocess.stderr.txt').read_text()
        tool_argv=[str(self.tool),'-s','__DATA','-n','__LASTDATA_CONST','-o',str(obj)+'__',str(obj)]
        commands=[shlex.split(l[2:]) for l in trace.splitlines() if l.startswith('+ ') and str(self.tool) in l]
        self.check('genuine-shell-tool-argv',tool_argv in commands,observed=commands)
        self.check('genuine-constructor-only-section-name-edits',obj.read_bytes()==expected,renamed_sections=names)
        row.update(raw_output=str(raw.relative_to(ROOT)),raw_output_sha256=sha(raw),output_sha256=sha(obj),postprocessed=True)
        self.report['last_processing']=dict(makefile=str(script.relative_to(ROOT)),makefile_sha256=sha(script),tool_argv=tool_argv,
            raw=str(raw.relative_to(ROOT)),raw_sha256=sha(raw),output=str(obj.relative_to(ROOT)),output_sha256=sha(obj),renamed_sections=names,
            linker_rename=rename.split(' = ',1)[1])

    def reuse_tail(self):
        if not self.args.object_evidence:raise ValueError('Explicit passing tail build required')
        doc=registered(self.args.object_evidence,self.ledger)
        paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
        if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('One passing tail source/tool/object report required')
        r=json.loads(paths[0].read_text())
        if r['compiler_sha256']!=sha(self.compiler):raise ValueError('Exact source compiler required')
        for name in ['setsegname','last_processing','compile_results','selected_profile','expanded_rules']:
            self.report[name]=r[name]
        self.tool=ROOT/r['setsegname']['tool']
        if sha(self.tool)!=r['setsegname']['sha256'] or len(r['compile_results'])!=3:raise ValueError('Actual tool/objects required')
        for row in r['compile_results']:
            if sha(ROOT/row['output'])!=row['output_sha256'] or not row['actual_arm64_object'] or sha(ROOT/row['source'])!=row['source_sha256']:
                raise ValueError('Actual selected tail source/output changed')
        self.report['tail_parent']=dict(experiment=self.args.object_evidence,report=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]))

    def process_file(self,source,output,label,old='__DATA',new='__LASTDATA_CONST',ignore=None):
        expected,names=expected_rename(source,old,new,ignore) # Bounds before legacy execution.
        argv=[self.tool]
        if old is not None:argv+=['-s',old]
        if ignore is not None:argv+=['-i',ignore]
        self.must([*argv,'-n',new,'-o',output,source],label)
        thin(output)
        self.check(label+'-only-required-name-bytes',output.read_bytes()==expected,renamed_sections=names)
        return names

    def inspect_tail(self,paths,label):
        result={};data_path=paths['lastkerneldataconst.o'];obj=ObjectData(data_path)
        size=obj.value('__lastkerneldataconst_padsize','<Q')[0]
        _,_,pos=obj.location('_data_const_padding',size)
        reloc=obj.relocation('__lastkerneldataconst',0)
        marker=obj.named['_data_const_padding']
        target=reloc['value']+reloc['addend']
        if reloc['section']!=marker['section'] or target!=marker['value'] or size!=16384 or obj.data[pos:pos+size]!=b'\xff'*size:
            raise ValueError('Genuine selected page padding/marker/relocation differs')
        self.check(label+'-actual-page-padding-and-pointer',True,size=size,relocation=reloc)
        result['padding_size']=size
        tiny=thin(paths['nonlto.o'])
        symbols=[s for s in tiny['symbols'] if s['name']=='___not_used_at_all__']
        if len(symbols)!=1:raise ValueError('Genuine no-LTO forcing data symbol missing')
        data=tiny['sections'][symbols[0]['section']-1]
        self.check(label+'-actual-nonlto-data-marker',data['size']==4 and data['zerofill'])
        ctor=paths['lastkernelconstructor.o'];view=thin(ctor);raw=ctor.read_bytes()
        init=next(s for s in view['sections'] if s['name']=='__mod_init_func')
        last=next(s for s in view['sections'] if s['name']=='__last')
        function=next(s for s in view['symbols'] if s['name']=='_last_kernel_constructor')
        address,info=struct.unpack_from('<iI',raw,init['reloc'])
        index=info&0xffffff;addend=struct.unpack_from('<Q',raw,init['offset'])[0]
        destination=view['symbols'][index] if info&(1<<27) else dict(section=index,value=0,name=None)
        self.check(label+'-actual-constructor-init-pointer',init['size']==8 and init['flags']&0xff==9 and init['nreloc']==1 and
            init['segment']=='__LASTDATA_CONST' and address==0 and info>>28==0 and (info>>25)&3==3 and
            destination['section']==function['section'] and destination['value']+addend==function['value'])
        self.check(label+'-actual-LAST-zero-marker',last['segment']=='__LAST' and last['size']==0 and last['zerofill'] and
            any(s['name']=='_last_kernel_symbol' and s['section']==view['sections'].index(last)+1 for s in view['symbols']))
        decoded=self.must([NDK/'llvm-objdump','-dr',ctor],label+'-constructor-disassembly')
        self.check(label+'-actual-iokit-branch-relocation','ARM64_RELOC_BRANCH26' in decoded and '_iokit_post_constructor_init' in decoded)
        result.update(init_pointer_size=init['size'],init_pointer_type=init['flags']&0xff,init_pointer_segment=init['segment'],
            last_marker_size=last['size'],last_marker_segment=last['segment'])
        return result

    def controls(self):
        paths={Path(r['id']).name:ROOT/r['output'] for r in self.report['compile_results']}
        observed=self.inspect_tail(paths,'source17')
        independent={}
        for name in TAIL:
            c=next(c for c in json.loads((ROOT/self.report['tail_parent']['report']).read_text())['commands'] if c['stdout'].endswith('/compile-'+name+'.stdout.txt'))
            argv=c['argv'].copy();argv[0]=str(NDK/'clang');obj=self.out/('independent19-'+name)
            # Clang19 removed this Clang17 permission flag. Keep the actual
            # zero-initialization policy and every selected source/type check.
            argv.remove('-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang')
            argv[argv.index('-o')+1]=str(obj);argv[argv.index('-MF')+1]=str(obj.with_suffix('.d'))
            self.must(argv,'independent19-'+name,cwd=Path(c['cwd']),timeout=120)
            if name=='lastkernelconstructor.o':
                processed=self.out/('independent19-processed-'+name)
                self.process_file(obj,processed,'independent19-constructor-process');obj=processed
            independent[name]=obj
        expected=self.inspect_tail(independent,'independent19')
        self.check('independent-genuine-tail-representations-agree',observed==expected)
        self.report['independent_representations']=dict(source17=observed,independent19=expected)
        self.report['independent19_flag_delta']=['Removed obsolete Clang17 permission flag; retained -ftrivial-auto-var-init=zero']

        fixture=self.out/'segment-fixture.o'
        self.must([*self.flags('c'),'-g','-c',self.out/'fixture-inputs/segment-fixture.c','-o',fixture],'compile-segment-fixture')
        for label,old,new,ignore in [('selected','__DATA','__LASTDATA_CONST',None),
            ('ignore',None,'__MOVED','__OTHER'),('truncated-name','__DATA','0123456789ABCDEF-extra',None),('missing-old','__MISSING','__MOVED',None)]:
            output=self.out/(label+'.o');self.process_file(fixture,output,'segment-'+label,old,new,ignore)
        marked=self.out/'debug-in-data.o';bytes_=bytearray(fixture.read_bytes())
        debug=next(s for s in thin(fixture)['sections'] if s['flags']&0x02000000)
        debug_index=thin(fixture)['sections'].index(debug)
        at=debug['segment_name_offset'];bytes_[at:at+16]=b'__DATA'.ljust(16,b'\0');marked.write_bytes(bytes_)
        output=self.out/'debug-in-data-processed.o';self.process_file(marked,output,'matching-debug-skip')
        self.check('debug-attribute-preserved-despite-matching-name',thin(output)['sections'][debug_index]['segment']=='__DATA')

        base=(self.out/'selected.o').read_bytes();expected,_=expected_rename(fixture)
        view=thin(self.out/'selected.o');text=next(s for s in view['sections'] if s['name']=='__text')
        for mode in ['code','call','name']:
            modified=bytearray(base)
            if mode=='code':modified[text['offset']]^=0x20
            if mode=='name':modified[view['sections'][0]['segment_name_offset']]^=1
            if mode=='call':
                entries=[text['reloc']+8*i for i in range(text['nreloc']) if struct.unpack_from('<I',base,text['reloc']+8*i+4)[0]>>28==2]
                if len(entries)<2:raise ValueError('Two genuine external branch relocations required')
                a,b=entries[:2];one,two=struct.unpack_from('<I',base,a+4)[0],struct.unpack_from('<I',base,b+4)[0]
                if one&0xffffff==two&0xffffff:raise ValueError('Distinct genuine call targets required')
                struct.pack_into('<I',modified,a+4,(one&0xff000000)|(two&0xffffff))
            path=self.out/('changed-'+mode+'.o');path.write_bytes(modified);thin(path)
            self.check('reject-actual-'+mode+'-mutation',path.read_bytes()!=expected)
        for mode in ['header','commands','section','symbols','relocations','bitcode']:
            modified=bytearray(fixture.read_bytes());v=thin(fixture)
            if mode=='header':modified=modified[:16]
            if mode=='commands':struct.pack_into('<I',modified,20,0xffffffff)
            if mode=='section':struct.pack_into('<I',modified,v['sections'][0]['segment_name_offset']+44,0xffffffff)
            if mode=='symbols':
                at=32
                while struct.unpack_from('<I',modified,at)[0]!=2:at+=struct.unpack_from('<I',modified,at+4)[0]
                struct.pack_into('<I',modified,at+16,0xffffffff)
            if mode=='relocations':struct.pack_into('<i',modified,next(s for s in v['sections'] if s['nreloc'])['reloc'],0x7fffffff)
            if mode=='bitcode':modified[:4]=b'BC\xc0\xde'
            path=self.out/('invalid-'+mode+'.o');path.write_bytes(modified)
            try:thin(path);rejected=False
            except (ValueError,UnicodeError,struct.error):rejected=True
            self.check('guard-reject-'+mode+'-before-legacy-tool',rejected)
        code,_,error=self.run([self.tool],'tool-missing-arguments')
        self.check('genuine-tool-missing-arguments',code==1 and 'Usage:' in error)
        self.lto_controls()
        self.link_control(paths)

    def lto_controls(self):
        rows=self.query('lto-profile')
        self.check('genuine-LTO-noLTO-flag',rows['GLOBAL']['CFLAGS_NOLTO_FLAG']=='-fno-lto')
        for name in ['nonlto.o','lastkernelconstructor.o']:
            argv=shlex.split(rows[name]['COMPILE'])
            self.check(name+'-genuine-noLTO-policy',argv[-1]=='-fno-lto' and '-flto' in argv)
            self.check(name+'-genuine-profile-policy',('-fprofile-instr-generate' in argv)==(name!='lastkernelconstructor.o'))
            obj=self.out/('lto-profile-'+name);argv[argv.index('-MF')+1]=str(obj.with_suffix('.d'))
            self.must([argv[0],*self.version['argv'][1:5],*argv[1:],'-o',obj],'compile-lto-profile-'+name,cwd=self.cwd)
            self.check(name+'-actual-forced-MachO',thin(obj)['filetype']==1)
            if name=='lastkernelconstructor.o':
                symbols=self.must([NDK/'llvm-nm','--just-symbol-name',obj],'constructor-profile-symbols')
                self.check('actual-constructor-has-no-profiling-symbols',not any(n in symbols for n in ['__llvm_prf','__profc','__profd','__llvm_profile']))

    def link_control(self,paths):
        doc=json.loads((ROOT/'fixtures/public/xnu-host-tools/macho-session4.json').read_text())
        ld=ROOT/doc['prefix']/'bin/aarch64-apple-darwin-ld'
        if sha(ld)!=doc['prefix_files_sha256']['bin/aarch64-apple-darwin-ld']:raise ValueError('Qualified linker changed')
        obj=self.out/'link-provider.o'
        self.must([*self.flags('c'),'-c',self.out/'fixture-inputs/link-provider.c','-o',obj],'compile-owned-link-provider')
        linked={}
        for label,rename in [('renamed',['-rename_segment','__LASTDATA_CONST','__LAST']),('unrenamed',[])]:
            output=self.out/(label+'-fixture.macho')
            self.must([ld,'-arch','arm64','-static','-pie','-platform_version','ios','16.5','16.5',
                '-image_base','0xfffffff007004000','-pagezero_size','0','-e','_iokit_post_constructor_init','-no_uuid',*rename,
                '-o',output,*paths.values(),obj],'link-only-'+label,timeout=120)
            view=thin(output)
            init=next(s for s in view['sections'] if s['name']=='__mod_init_func')
            function=next(s for s in view['symbols'] if s['name']=='_last_kernel_constructor')
            target=struct.unpack_from('<Q',output.read_bytes(),init['offset'])[0]
            names=[s['name'] for s in view['segments']]
            expected='__LAST' if rename else '__LASTDATA_CONST'
            self.check(label+'-actual-link-segment-and-init-pointer',view['filetype']==2 and expected in names and
                init['segment']==expected and target==function['value'],segments=names,target=target,function=function['value'])
            self.must([NDK/'llvm-readobj','--file-headers','--sections','--symbols',output],'independent-linked-'+label)
            linked[label]=dict(path=str(output.relative_to(ROOT)),sha256=sha(output),segments=names,init_segment=init['segment'])
        self.check('link-rename-negative-detects-required-step',linked['renamed']['init_segment']!=linked['unrenamed']['init_segment'])
        self.report['link_only_fixture']=dict(objects=[str(p.relative_to(ROOT)) for p in paths.values()],owned_provider=str(obj.relative_to(ROOT)),outputs=linked,
            full_kernel=False,device_executed=False,private_abi_qualified=False)

    def audit(self):
        parent=ROOT/'artifacts/xnu-compiler-cxx-storage/object-audit-session1'
        compiled=json.loads((parent/'compiled-objects.json').read_text())
        unresolved=json.loads((parent/'unresolved-objects.json').read_text())
        inputs=json.loads((parent/'dependency-files.json').read_text())
        dependencies=json.loads((parent/'object-dependencies.json').read_text())
        if len(compiled)!=962 or len(unresolved)!=20 or len(dependencies)!=962:raise ValueError('Complete current parent inventory required')
        for name,h in inputs.items():
            if sha(ROOT/name)!=h:raise ValueError('Original profile dependency changed: '+name)
        objects=[]
        for row in compiled:
            if sha(ROOT/row['source'])!=row['source_sha256'] or sha(ROOT/row['output'])!=row['output_sha256'] or not macho(ROOT/row['output'])['filetype']==1:
                raise ValueError('Prior962 source/object witness changed')
            objects.append(ROOT/row['output'])
        current_rules=self.query('selected')
        source=json.loads((ROOT/self.report['tail_parent']['report']).read_text())
        if current_rules!=source['expanded_rules']['selected']:raise ValueError('Actual genuine compile expansion changed')
        for row in self.report['compile_results']:
            name=Path(row['id']).name;obj=ROOT/row['output']
            command=next(c for c in source['commands'] if c['stdout'].endswith('/compile-'+name+'.stdout.txt'))
            argv=shlex.split(current_rules[name]['COMPILE']);argv[argv.index('-MF')+1]=str(obj.with_suffix('.d'))
            expected=[argv[0],*self.version['argv'][1:5],*argv[1:],'-o',str(obj)]
            if command['argv']!=expected or command['cwd']!=str(self.cwd) or command['exit_code']!=0 or command['timed_out']:
                raise ValueError('Actual target compile differs from genuine current recipe')
            if row['id']=='kernel/lastkernelconstructor.o':
                raw=ROOT/row['raw_output'];wanted,names=expected_rename(raw)
                if sha(raw)!=row['raw_output_sha256'] or names!=['__mod_init_func'] or obj.read_bytes()!=wanted:
                    raise ValueError('Actual genuine LAST processing changed')
            thin(obj);objects.append(obj);compiled.append(row)
            dep=obj.with_suffix('.d');line=dep.read_text().replace('\\\n',' ').splitlines()[0]
            files=[(self.cwd/p).resolve() for p in shlex.split(line.split(':',1)[1])]
            if (ROOT/row['source']).resolve() not in files:raise ValueError('Actual target source missing from dependencies')
            names=[]
            for p in files:
                key=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                if key in inputs and inputs[key]!=sha(p):raise ValueError('Shared dependency changed')
                inputs[key]=sha(p);names.append(key)
            dependencies[row['id']]=dict(depfile=str(dep.relative_to(ROOT)),depfile_sha256=sha(dep),inputs=sorted(set(names)))
        self.check('all962-prior-successes-retained-by-actual-provenance',True,retained=962,new=3,prior_recompiled=False)
        unresolved=[r for r in unresolved if r['id'] not in {row['id'] for row in self.report['compile_results']}]
        self.check('complete982-known-direct-accounting',len(compiled)==965 and len(unresolved)==17 and len(compiled)+len(unresolved)==982 and
            all(r['category']=='missing_source_or_recipe' for r in unresolved))
        text=self.must([NDK/'llvm-readobj','--file-headers',*objects],'all965-independent-headers',timeout=120)
        self.check('all965-independent-ARM64-headers',text.count('Format: Mach-O arm64')==965)
        text=self.must([NDK/'llvm-nm','--defined-only','--format=posix',*objects],'all965-independent-symbols',timeout=120)
        types=Counter(re.findall(r'(?m)^\S+ ([A-Za-z]) [0-9a-f]+',text))
        self.check('genuine-defined-code-and-data',types['T']+types['t']>=29740)
        self.report['coverage']=dict(selected_components=978,actual_component_arm64=961,known_direct_objects=982,
            actual_arm64=965,known_direct_unresolved=17,prior_successes=962,prior_object_regressions=[],new_direct_objects=3,
            unique_dependency_files=len(inputs),defined_symbol_types=dict(types),parent_recompiled=False,
            missing_IIG_sources=17,full_archive_link_qualified=False)
        for name,value in [('compiled-objects',compiled),('unresolved-objects',unresolved),('dependency-files',inputs),('object-dependencies',dependencies)]:
            dump(self.out/(name+'.json'),value)

    def acceptance(self):
        reports={}
        for identifier in [self.args.object_evidence,self.args.controls_evidence,self.args.audit_evidence]:
            doc=registered(identifier,self.ledger);paths=[ROOT/p for p in doc['artifacts'] if p.endswith('/report.json')]
            if doc['outcome']!='pass' or len(paths)!=1:raise ValueError('One passing actual component report required: '+identifier)
            reports[identifier]=(paths[0],json.loads(paths[0].read_text()))
        source_path,source=reports[self.args.object_evidence]
        if sha(ROOT/source['setsegname']['source'])!=sha(KERNEL/'SETUP/setsegname/setsegname.c'):
            raise ValueError('Unchanged genuine tool source required')
        dep=source_path.parent/'setsegname.d'
        paths=[(ROOT/p).resolve() for p in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])]
        tool_inputs={};public_count=0
        for p in paths:
            name=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p);tool_inputs[name]=sha(p)
            if p.is_relative_to(CCTOOLS):
                relative=str(p.relative_to(CCTOOLS));label='public-host-header-'+str(public_count)
                self.must(['git','-C',CCTOOLS,'show','904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb:'+relative],label)
                if sha(self.out/(label+'.stdout.txt'))!=sha(p):raise ValueError('Actual host header differs from pinned public blob')
                public_count+=1
        self.check('complete-host-tool-dependencies-and-public-headers',len(tool_inputs)>100 and public_count>20,
            unique_inputs=len(tool_inputs),public_headers=public_count)
        dump(self.out/'host-tool-dependencies.json',tool_inputs)
        abi=self.out/'host-macho-abi.c'
        abi.write_text('#include <mach-o/loader.h>\n#include <mach-o/nlist.h>\n_Static_assert(sizeof(struct mach_header_64)==32,"header ABI");\n_Static_assert(sizeof(struct segment_command_64)==72,"segment ABI");\n_Static_assert(sizeof(struct section_64)==80,"section ABI");\n_Static_assert(sizeof(struct nlist_64)==16,"symbol ABI");\nint main(void) { return 0; }\n')
        include=CCTOOLS/'cctools/include'
        self.must([NDK/'clang','-std=gnu11','-I',include,'-idirafter',include/'foreign',abi,'-o',self.out/'host-macho-abi'],'actual-public-host-macho-ABI')
        self.must([self.out/'host-macho-abi'],'run-host-macho-ABI')
        self.check('independent-reader-struct-widths-match-public-C-ABI',True)

        raw=ROOT/source['last_processing']['raw'];replay=self.out/'replay-lastkernelconstructor.o'
        self.process_file(raw,replay,'final-genuine-tool-replay')
        current=ROOT/source['last_processing']['output']
        self.check('actual-tool-replay-matches-genuine-Make-output',replay.read_bytes()==current.read_bytes())
        current_rules=self.query()
        self.check('actual-current-Make-expansion-replayed',current_rules==source['expanded_rules']['selected'])
        controls=reports[self.args.controls_evidence][1]
        self.check('all40-actual-controls-pass',len(controls['checks'])==40 and all(c['pass_check'] for c in controls['checks']))
        linked=ROOT/controls['link_only_fixture']['outputs']['renamed']['path'];view=thin(linked)
        init=next(s for s in view['sections'] if s['name']=='__mod_init_func')
        last=next(s for s in view['symbols'] if s['name']=='_last_kernel_symbol')
        self.check('actual-linked-LAST-marker-after-init-pointer',last['value']==init['address']+init['size'] and
            view['sections'][last['section']-1]['segment']=='__LAST',init_address=init['address'],init_size=init['size'],last_symbol=last['value'])
        audit_path,audit=reports[self.args.audit_evidence];coverage=audit['coverage']
        inputs=json.loads((audit_path.parent/'dependency-files.json').read_text())
        for name,h in inputs.items():
            if sha(ROOT/name)!=h:raise ValueError('Current complete965 dependency changed')
        self.check('all965-current-object-source-dependency-witnesses',coverage['actual_arm64']==965 and coverage['prior_successes']==962 and
            coverage['known_direct_unresolved']==17 and not coverage['prior_object_regressions'] and len(inputs)==coverage['unique_dependency_files'])
        self.check('all-full-kernel-native-crypto-private-ABI-limits-retained',all(
            not r[key] for _,r in reports.values() for key in ['full_kernel_qualified','full_crypto_qualified','apple_private_abi_qualified','device_executed']))
        self.report['acceptance_reports']={identifier:dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for identifier,(p,r) in reports.items()}
        self.report['coverage']=coverage
        self.must(['make','check'],'repository-check',timeout=300)
        self.check('required-repository-checks',True)
        self.must(['git','diff','--check'],'whitespace-check')
        self.must(['git','diff','--cached','--check'],'staged-whitespace-check')
        good=all(c['pass_check'] for c in self.report['checks'])
        self.report['acceptance_assessment']=[dict(criterion=i+1,pass_check=good,evidence=e) for i,e in enumerate([
            [self.args.object_evidence,'public_source_comparison','actual-current-Make-expansion-replayed'],
            [self.args.object_evidence,self.args.controls_evidence,'final-genuine-tool-replay'],
            [self.args.audit_evidence,self.args.controls_evidence,'host-tool-dependencies.json'],
            [self.args.audit_evidence,'qualified-component.json','required-repository-checks']])]

    def finish(self):
        self.report['outcome']='pass' if self.report['checks'] and all(c['pass_check'] for c in self.report['checks']) and 'error' not in self.report else 'fail'
        self.report['summary']='Genuine top-level object/LAST host assessment; full kernel/link/private ABI/crypto/native support remains unqualified'
        self.report['compiler_sha256']=sha(self.compiler) if hasattr(self,'compiler') else None
        dump(self.out/'report.json',self.report)
        files=sorted(p for p in self.out.rglob('*') if p.is_file() and p.name!='evidence.json')
        if self.args.mode=='acceptance':
            files=sorted(set(files+[Path(__file__),ROOT/'docs/procedures/xnu-kernel-direct-tail.md',
                *[p for base in [FIXTURES,PATCHES] for p in base.rglob('*') if p.is_file()]]))
        doc={k:self.report[k] for k in ['kind','origin','outcome','recorded_at','summary','device_executed','full_kernel_qualified','full_crypto_qualified','apple_private_abi_qualified']}
        doc.update(commands=self.report['commands'][:20],commands_scope='Representative commands; every actual command in hashed report.json',actual_command_count=len(self.report['commands']),
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),artifacts=[str(p.relative_to(ROOT)) for p in files],sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
        dump(self.out/'evidence.json',doc)
        print(json.dumps(dict(outcome=self.report['outcome'],error=self.report.get('error'),failed_checks=[c['name'] for c in self.report['checks'] if not c['pass_check']])))
        return 0 if self.report['outcome']=='pass' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True)
    p.add_argument('--mode',choices=['build','controls','audit','acceptance'],required=True)
    p.add_argument('--object-evidence');p.add_argument('--controls-evidence');p.add_argument('--audit-evidence');args=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):p.error('Canonical fresh run name required')
    args.compiler,args.compiler_evidence,args.header_evidence,args.resource_evidence=VECTOR_COMPILER,'VCOMP-002','FHDR-003','RHDR-002'
    args.storage_evidence='CXXST-007';args.port_evidence='KDECL-004';args.jobs=1
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));build=Tail(args)
    try:
        build.inputs()
        if args.mode=='build':build.build_tool();build.compile_tail();build.postprocess()
        else:
            build.reuse_tail()
            if args.mode=='controls':build.controls()
            elif args.mode=='audit':build.audit()
            elif args.mode=='acceptance':build.acceptance()
    except Exception as error:build.report['error']=str(error)
    return build.finish()


if __name__=='__main__':sys.exit(main())
