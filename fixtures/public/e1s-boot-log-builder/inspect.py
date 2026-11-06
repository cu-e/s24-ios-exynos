#!/usr/bin/env python3
"""Bounded read-only E1S ELF/Image inspector. Never execute a target or compiler.

ELF64/AArch64 relocation constants follow the local public /usr/include/elf.h.
The actual target is a genuine ordinary build, never a synthesized valid ELF.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

MAX = 16*1024*1024
LOG_SIZE = 0xff14  # 8-byte magic,2 uint32 fields,0xff01 chars, target tail padding.

class Invalid(ValueError): pass

def need(condition, message):
    if not condition: raise Invalid(message)

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path):
    need(Path(path).is_file(), 'missing artifact')
    with Path(path).open('rb') as stream: body=stream.read(MAX+1)
    need(len(body)<=MAX, 'artifact size bound')
    return body

class ELF:
    def __init__(self, data, kind):
        need(64 <= len(data) <= MAX, 'ELF size')
        self.data=data
        h=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
        ident,self.kind,machine,version,self.entry,phoff,shoff,flags,ehsize,phsize,phnum,shsize,shnum,strings=h
        need(ident[:7] == b'\x7fELF\x02\x01\x01' and machine == 183 and version == 1, 'ELF64 little AArch64')
        need(self.kind == kind and ehsize == 64 and shsize == 64 and 0 < shnum <= 512, 'ELF type/table')
        need(shoff+shnum*64 <= len(data) and strings < shnum, 'section table extent')
        self.sections=[]
        for i in range(shnum):
            fields=struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*64)
            keys=['nameoff','type','flags','addr','offset','size','link','info','align','entsize']
            row=dict(zip(keys,fields),index=i,header_offset=shoff+i*64)
            need(row['align'] == 0 or row['align'] & (row['align']-1) == 0, 'section alignment')
            need(row['type'] == 8 or row['offset']+row['size'] <= len(data), 'section file extent')
            self.sections.append(row)
        pool=self.section_bytes(self.sections[strings]);need(len(pool) <= 1024**2, 'section names bound')
        for row in self.sections: row['name']=self.string(pool,row['nameoff'])
        self.symbols=[];self.tables={}
        for section in self.sections:
            if section['type'] not in (2,11): continue
            need(section['entsize'] == 24 and section['size'] % 24 == 0 and section['size']//24 <= 8192, 'symbol bounds')
            need(len(self.symbols)+section['size']//24 <= 8192, 'total symbol bound')
            need(section['link'] < shnum and self.sections[section['link']]['type'] == 3, 'symbol strings')
            names=self.section_bytes(self.sections[section['link']]);need(len(names) <= 1024**2,'symbol names bound')
            rows=[]
            for at in range(section['offset'],section['offset']+section['size'],24):
                name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',data,at)
                row=dict(name=self.string(names,name),type=info&15,binding=info>>4,index=index,value=value,size=size,
                         entry_offset=at,table=section['index'])
                rows.append(row);self.symbols.append(row)
            self.tables[section['index']]=rows
        need(phnum <= 64 and (not phnum or phsize == 56 and phoff+phnum*56 <= len(data)), 'program table bounds')
        self.loads=[]
        for i in range(phnum):
            typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,phoff+56*i)
            need(off+filesz <= len(data) and filesz <= memsz, 'program file extent')
            if typ == 1:self.loads.append(dict(flags=flags,offset=off,addr=va,filesz=filesz,size=memsz))
    @staticmethod
    def string(pool,off):
        need(off < len(pool),'string offset');end=pool.find(b'\0',off)
        need(end >= off and end-off <= 1024,'string bounds');return pool[off:end].decode('ascii')
    def section_bytes(self,s):
        need(s['type'] != 8,'NOBITS is not file storage');return self.data[s['offset']:s['offset']+s['size']]
    def symbol(self,name):
        found=[s for s in self.symbols if s['name'] == name and s['index'] != 0]
        need(len(found)==1,'unique defined symbol '+name);return found[0]
    def bytes_at(self,address,size):
        found=[s for s in self.sections if s['flags']&2 and s['type'] != 8 and s['addr'] <= address and address+size <= s['addr']+s['size']]
        need(len(found)==1,'file-backed address extent')
        s=found[0];off=s['offset']+address-s['addr'];return self.data[off:off+size]
    def relocations(self):
        count=0
        for sec in self.sections:
            if sec['type'] != 4: continue
            need(sec['entsize']==24 and sec['size']%24==0 and sec['link'] in self.tables and sec['info']<len(self.sections),'relocation table')
            for at in range(sec['offset'],sec['offset']+sec['size'],24):
                count+=1;need(count<=8192,'total relocation bound')
                off,info,addend=struct.unpack_from('<QQq',self.data,at);symbols=self.tables[sec['link']]
                need(info>>32 < len(symbols),'relocation symbol index')
                yield dict(offset=off,type=info&0xffffffff,addend=addend,symbol=symbols[info>>32],section=self.sections[sec['info']])

def signed(value,bits): return value-(1<<bits) if value & (1<<(bits-1)) else value

def adr(word,pc):
    immediate=signed(((word>>5)&0x7ffff)<<2 | ((word>>29)&3),21)
    if word & 0x9f000000 == 0x10000000:return pc+immediate,'ADR'
    if word & 0x9f000000 == 0x90000000:return (pc&~4095)+(immediate<<12),'ADRP'
    raise Invalid('actual instruction is neither ADR nor ADRP')

def code_base(obj,sec,linked):
    candidates=set()
    for symbol in obj.symbols:
        if symbol['index'] != sec['index'] or symbol['type'] in (3,4) or not symbol['name']:continue
        matches=[s for s in linked.symbols if s['name']==symbol['name'] and s['index']!=0 and s['type']==symbol['type']]
        if len(matches)==1:candidates.add(matches[0]['value']-symbol['value'])
    need(len(candidates)==1,'unambiguous real object-to-linked code section mapping')
    return candidates.pop()

def inspect_relocations(linked,obj,object_log,linked_log):
    rows=[]
    relocations=list(obj.relocations())
    for r in relocations:
        sym=r['symbol']
        if sym['index'] != object_log['index']:continue
        need(sym['name']=='loader_log' or sym['type']==3,'unexpected log-section relocation provider')
        relative=sym['value']+r['addend']-object_log['value']
        need(0 <= relative <= linked_log['size'],'log relocation target extent')
        target=linked_log['value']+relative;pc=code_base(obj,r['section'],linked)+r['offset']
        need(r['offset']+4 <= r['section']['size'],'log relocation code extent')
        word=struct.unpack('<I',linked.bytes_at(pc,4))[0]
        original=struct.unpack_from('<I',obj.data,r['section']['offset']+r['offset'])[0]
        kind=r['type']
        if kind in (274,275,276):
            if word==0xd503201f:
                need(kind in (275,276) and r['offset']+8<=r['section']['size'],'relaxed ADRP pair extent')
                next_original=struct.unpack_from('<I',obj.data,r['section']['offset']+r['offset']+4)[0]
                need(next_original&0x7f000000==0x11000000 and (next_original>>5)&31==original&31,'real ADRP/ADD register pair')
                pairs=[n for n in relocations if n['section']['index']==r['section']['index'] and n['offset']==r['offset']+4 and n['type']==277 and n['symbol']['index']==object_log['index'] and n['symbol']['value']+n['addend']==sym['value']+r['addend']]
                need(len(pairs)==1,'source object ADRP/ADD relocation pair')
                next_word=struct.unpack('<I',linked.bytes_at(pc+4,4))[0]
                need(next_word&31==next_original&31,'relaxed ADR destination register')
                resolved,op=adr(next_word,pc+4)
                need(op=='ADR' and resolved==target,'relaxed NOP/ADR target')
                proof='relaxed NOP+ADR'
            else:
                resolved,op=adr(word,pc)
                need(word&31==original&31,'ADR/ADRP destination register')
                if kind==274:need(op=='ADR' and resolved==target,'log ADR target')
                else:need(resolved==target&~4095,'log ADRP page target')
                proof='ADRP relaxed to page ADR' if kind!=274 and op=='ADR' else op
        elif kind==277:
            if word&0x9f000000==0x10000000:
                need(word&31==original&31,'relaxed ADD destination register')
                resolved,op=adr(word,pc);need(resolved==target,'relaxed ADD-to-ADR target');proof='relaxed ADR'
            else:
                need(word&0x7f000000==0x11000000 and not word&(1<<22),'ADD immediate opcode')
                need(word&~(4095<<10)==original&~(4095<<10),'ADD nonrelocated operands')
                need(((word>>10)&4095)==target&4095,'ADD low12 target');proof='ADD low12'
        elif kind in (278,284,285,286,299):
            scale={278:0,284:1,285:2,286:3,299:4}[kind]
            need(word&0x3b000000==0x39000000,'unsigned load/store opcode')
            need(word&~(4095<<10)==original&~(4095<<10),'load/store nonrelocated operands')
            need((((word>>10)&4095)<<scale)==target&4095,'load/store low12 target');proof='LD/ST low12'
        else:
            raise Invalid('unsupported relevant actual log relocation '+str(kind))
        rows.append(dict(object_relocation=kind,linked_instruction_address=pc,target=target,proof=proof))
    need(rows and any(r['proof'] in ('ADR','ADRP','ADRP relaxed to page ADR','relaxed NOP+ADR') for r in rows),'actual log address relocation evidence')
    return rows

def inspect_layout(elf,image,obj,start_source):
    need(len(image)<=MAX and len(image)>=64 and image[56:60]==b'ARM\x64','real flat Image header')
    e=ELF(elf,2);o=ELF(obj,1)
    names=['_head','_payload_start','_end','_bss_start','_bss_end','_stack_top','_exc_stack_top','loader_log','payload_addr']
    s={name:e.symbol(name) for name in names};value=lambda name:s[name]['value']
    need(e.entry==value('_head')==0,'ordinary linker entry/base')
    end=value('_payload_start');need(end==value('_end') and end%4096==0 and 64<=end<=MAX,'actual payload boundary')
    need(len(image)==end and struct.unpack_from('<Q',image,16)[0]==end,'Image size/header/payload agreement')
    need(struct.unpack_from('<Q',image,8)[0]==0x80000 and struct.unpack_from('<Q',image,24)[0]==0xa,'unchanged boot header fields')
    log=s['loader_log'];need(log['index']<len(e.sections),'log section index');section=e.sections[log['index']]
    need(log['type']==1,'real target log object symbol')
    need(section['type']==1 and section['flags']&3==3 and not section['flags']&4,'writable allocated nonexecuting file-backed log')
    need(log['size']==LOG_SIZE and log['value']%16==0,'target log size/alignment')
    lo,hi=log['value'],log['value']+log['size']
    need(section['addr']<=lo<=hi<=section['addr']+section['size'] and hi<=end,'whole log before payload')
    need(any(p['flags']&2 and p['addr']<=lo and hi<=p['addr']+p['filesz'] for p in e.loads),'writable file-backed load segment')
    match=re.search(r'\.section \.data, "aw"\s+\.balign 16\s+\.space (0x[0-9a-f]+)\s+_stack_top:\s+\.space (0x[0-9a-f]+)\s+_exc_stack_top:',start_source)
    need(match is not None,'source-defined actual stack allocations')
    stack,exception=int(match[1],16),int(match[2],16)
    ranges={'stack':[value('_stack_top')-stack,value('_stack_top')],
            'exception_stack':[value('_stack_top'),value('_exc_stack_top')],
            'bss':[value('_bss_start'),value('_bss_end')]}
    need(value('_exc_stack_top')-value('_stack_top')==exception,'actual exception stack size')
    for name,(a,b) in ranges.items():
        need(0<=a<=b<=end and not(lo<b and a<hi),'log disjoint from '+name)
    initial=e.bytes_at(lo,LOG_SIZE)
    need(initial[:8]==b'E1SXNU01' and initial[8:]==bytes(LOG_SIZE-8),'initialized magic/header/text/extra terminator')
    need(image[lo:hi]==initial,'actual objcopy log bytes')
    # Reconstruct binary alloc sections, including source header, with the exact
    # zero padding performed by the existing fix_image.py. Do not invent payload.
    reconstructed=bytearray(end)
    for sec in e.sections:
        if not sec['flags']&2 or sec['type']==8 or not sec['size']:continue
        need(sec['addr']+sec['size']<=end,'allocated section exceeds image')
        reconstructed[sec['addr']:sec['addr']+sec['size']]=e.section_bytes(sec)
    need(bytes(reconstructed)==image,'genuine ELF-to-flat Image/padding agreement')
    pc=value('payload_addr');target,op=adr(struct.unpack('<I',e.bytes_at(pc,4))[0],pc)
    need(op=='ADR' and target==end,'real payload_addr ADR target/range')
    object_log=o.symbol('loader_log')
    need(object_log['index']<len(o.sections) and o.sections[object_log['index']]['name']=='.data.bootlog','genuine input log section')
    need(object_log['type']==1 and object_log['size']==LOG_SIZE,'genuine input log object size')
    relocations=inspect_relocations(e,o,object_log,log)
    return dict(log_symbol=log,merged_output_section=section['name'],log_extent=[lo,hi],payload_boundary=end,
                source_stacks_and_bss=ranges,payload_addr_ADR=dict(address=pc,target=target),
                checked_log_relocations=relocations,initial_record_sha256=hashlib.sha256(initial).hexdigest(),
                ELF_Image_padding_agreement=True,physical_mapping_qualified=False)


def recorded_vectors(actual,expected):
    need(actual==expected,'unchanged21 plus2 exact command/order vectors')

def product_binding(product,file):
    need(sha(file)==product['sha256'] and Path(file).stat().st_size==product['size'],'stale artifact binding')

def source_binding(file,digest):
    need(sha(file)==digest,'source ABI/exclusion/preimage binding '+str(file))

def verify_build(root,main,plan):
    need(root.resolve()==root and str(root)==plan['output']['root'],'fresh declared build namespace')
    report=json.loads(read(root/'report.json'))
    need(report['outcome']=='pass' and len(report['commands'])==23,'genuine23-command build report')
    recorded_vectors([r['argv'] for r in report['commands']],plan['expected_recorded_run_argv'])
    need(all(r['exit_code']==0 for r in report['commands']),'all actual builder exits')
    need(all(report['source'][k]==plan['expected_source'][k] for k in ['id','origin','revision']) and report['source']['clean'],'pinned source provenance')
    for key,digest in [('source_patch','23b31c44ed9dba9c2da2e5b56ccbe97cd67fa41efff3ec032130eabca6718ae1'),
        ('display_source_patch','0689fc94383efec7c83df44629df3b0e3e456cce48b08008e2226bc5189570d9'),
        ('boot_log_source_patch','569663074fb7de230b4760a613562841afe311352ed32e78275c55708aa21328')]:
        need(report[key]['applied'] and report[key]['sha256']==digest,'accepted overlay provenance '+key)
        need(sha(main/report[key]['snapshot'])==digest,'actual overlay snapshot '+key)
    expected_products=plan['expected_product_paths']
    need([r['path'] for r in report['products']]==expected_products,'exact genuine eight product paths')
    for product in report['products']:
        file=main/product['path']
        product_binding(product,file)
    source_hashes={}
    for relative,digest in plan['expected_post_source_sha256'].items():
        actual=sha(root/'source'/relative)
        source_binding(root/'source'/relative,digest)
        source_hashes[relative]=actual
    for binding in plan['input_bindings'].values():
        need(sha(binding['path'])==binding['sha256'],'changed frozen input '+binding['path'])
    return report,source_hashes

def negative_controls(directory,elf,image,obj,start,report,root,main,plan):
    """Only invalid derivatives of the genuine build; never a fabricated valid target."""
    need(not directory.exists(),'fresh negative control directory');directory.mkdir()
    linked=ELF(elf,2);log=linked.symbol('loader_log');section=linked.sections[log['index']]
    records=[]
    def rejected(name,call,reason,artifact=None):
        try:call()
        except Invalid as error:
            need(reason in str(error),'wrong rejection reason '+name)
            records.append(dict(id=name,outcome='expected-rejected',reason=str(error),
                                artifact=str(artifact) if artifact else None,
                                sha256=sha(artifact) if artifact else None))
        else:raise Invalid('invalid control accepted: '+name)
    def elf_case(name,offset,fmt,value,reason):
        changed=bytearray(elf);struct.pack_into(fmt,changed,offset,value)
        file=directory/(name+'.elf');file.write_bytes(changed)
        rejected(name,lambda:inspect_layout(changed,image,obj,start),reason,file)
    elf_case('wrong-log-size',log['entry_offset']+16,'<Q',LOG_SIZE+4,'target log size')
    elf_case('log-past-payload',log['entry_offset']+8,'<Q',linked.symbol('_payload_start')['value'],'whole log before payload')
    elf_case('readonly-log-section',section['header_offset']+8,'<Q',section['flags']&~1,'writable allocated')
    elf_case('NOBITS-log-section',section['header_offset']+4,'<I',8,'writable allocated')
    elf_case('payload-end-disagreement',linked.symbol('_end')['entry_offset']+8,'<Q',linked.symbol('_end')['value']+4096,'actual payload boundary')
    elf_case('log-overlaps-stack',log['entry_offset']+8,'<Q',linked.symbol('_stack_top')['value']-16,'log disjoint from stack')
    changed=bytearray(image);struct.pack_into('<Q',changed,16,len(image)+4096)
    file=directory/'header-size-mismatch.Image';file.write_bytes(changed)
    rejected('header-size-mismatch',lambda:inspect_layout(elf,changed,obj,start),'Image size/header/payload agreement',file)
    vectors=[r['argv'] for r in report['commands']]
    changed_vectors=vectors[:5]+vectors[7:]
    rejected('omitted-log-overlay',lambda:recorded_vectors(changed_vectors,plan['expected_recorded_run_argv']),'command/order vectors')
    changed_vectors=list(vectors);changed_vectors[3],changed_vectors[5]=changed_vectors[5],changed_vectors[3]
    rejected('reordered-overlay',lambda:recorded_vectors(changed_vectors,plan['expected_recorded_run_argv']),'command/order vectors')
    product=dict(report['products'][4]);product['sha256']='0'*64
    rejected('stale-product-binding',lambda:product_binding(product,main/product['path']),'stale artifact binding')
    body=read(root/'source/shim/e1s-xnu/loader.c')
    for name,old,new in [('changed-legacy-exclusion',b'0x91200000UL',b'0x91200010UL'),
                         ('changed-boot-ABI',b'sizeof(struct boot_args) == 736',b'sizeof(struct boot_args) == 744')]:
        need(old in body,'actual control source witness')
        file=directory/(name+'.c');file.write_bytes(body.replace(old,new,1))
        rejected(name,lambda:source_binding(file,plan['expected_post_source_sha256']['shim/e1s-xnu/loader.c']),'source ABI/exclusion/preimage binding',file)
    return records

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--main',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--controls',action='store_true')
    args=parser.parse_args();root=args.build_root
    need(not args.out.exists(),'fresh inspection output required')
    need(not args.out.parent.exists(),'fresh inspection namespace required')
    args.out.parent.mkdir(parents=True)
    need(sha(args.plan)==args.plan_sha256,'changed source plan')
    plan=json.loads(read(args.plan));report,sources=verify_build(root,args.main,plan)
    elf=read(root/'loader/loader.elf');image=read(root/'loader/Image')
    obj=read(root/'loader/loader.c.o');start=read(root/'source/shim/e1s-xnu/start.S').decode()
    result=inspect_layout(elf,image,obj,start)
    controls=negative_controls(args.out.parent/'negative-controls',elf,image,obj,start,report,root,args.main,plan) if args.controls else []
    args.out.write_text(json.dumps(dict(kind='host-test',outcome='pass',layout=result,
        source_report_sha256=sha(root/'report.json'),ELF_sha256=sha(root/'loader/loader.elf'),
        Image_sha256=sha(root/'loader/Image'),object_sha256=sha(root/'loader/loader.c.o'),
        source_sha256=sources,negative_controls=controls,target_executed=False,
        limitations=['Artifact layout only; independent review and kernel physical ownership gates remain.']),indent=2)+'\n')
    print(json.dumps({'outcome':'pass','target_executed':False,'checked_log_relocations':len(result['checked_log_relocations'])}))

if __name__=='__main__': main()
